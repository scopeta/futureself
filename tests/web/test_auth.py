"""Entra auth: JWT validation (self-signed) + per-user isolation (authz invariant)."""
from __future__ import annotations

import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from futureself.web import auth

TENANT = "708e9037-test"
CLIENT = "ee0da6bc-test"
_ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"


@pytest.fixture
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return priv, key.public_key()


class _FakeSigningKey:
    def __init__(self, key):  # noqa: ANN001
        self.key = key


class _FakeJWKS:
    def __init__(self, key):  # noqa: ANN001
        self._key = key

    def get_signing_key_from_jwt(self, _token):  # noqa: ANN001, ANN202
        return _FakeSigningKey(self._key)


def _enable(monkeypatch, pub):  # noqa: ANN001
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setattr(auth, "_jwks_client", lambda _t: _FakeJWKS(pub))


def _token(priv, **overrides):  # noqa: ANN001
    claims = {"iss": _ISS, "aud": CLIENT, "oid": "user-1", "exp": int(time.time()) + 3600}
    claims.update(overrides)
    return jwt.encode(claims, priv, algorithm="RS256")


def test_auth_enabled_flag(monkeypatch):
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    monkeypatch.delenv("ENTRA_CLIENT_ID", raising=False)
    assert auth.auth_enabled() is False
    monkeypatch.setenv("ENTRA_TENANT_ID", "t")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "c")
    assert auth.auth_enabled() is True


def test_bearer_token_parsing():
    assert auth.bearer_token("Bearer abc.def") == "abc.def"
    assert auth.bearer_token("Basic xyz") is None
    assert auth.bearer_token(None) is None


def test_validate_token_ok(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    assert auth.validate_token(_token(priv))["oid"] == "user-1"


def test_validate_token_accepts_api_audience(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    assert auth.validate_token(_token(priv, aud=f"api://{CLIENT}"))["oid"] == "user-1"


def test_validate_token_rejects_expired(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    with pytest.raises(auth.AuthError):
        auth.validate_token(_token(priv, exp=int(time.time()) - 10))


def test_validate_token_rejects_wrong_audience(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    with pytest.raises(auth.AuthError):
        auth.validate_token(_token(priv, aud="some-other-app"))


def test_validate_token_rejects_wrong_issuer(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    with pytest.raises(auth.AuthError):
        auth.validate_token(_token(priv, iss="https://evil.example/v2.0"))


def test_validate_token_requires_oid(monkeypatch, rsa_keys):
    priv, pub = rsa_keys
    _enable(monkeypatch, pub)
    tok = jwt.encode({"iss": _ISS, "aud": CLIENT, "exp": int(time.time()) + 3600}, priv, algorithm="RS256")
    with pytest.raises(auth.AuthError):
        auth.validate_token(tok)


# ---------------------------------------------------------------------------
# Authorization invariant: in Entra mode, data is isolated per oid (cross-user
# denial) — one user's token can never read another user's blueprint.
# ---------------------------------------------------------------------------


@patch("futureself.web.routes.api.validate_token")
async def test_entra_mode_isolates_users_by_oid(mock_validate, client, monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "t")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "c")
    # Bearer "A" → alice, "B" → bob (validation mocked; resolution is real)
    mock_validate.side_effect = lambda tok: {"oid": "alice" if tok == "A" else "bob"}

    # Alice writes her age
    r = await client.patch(
        "/api/blueprint/bio",
        json={"age": 30, "sex": "F", "height_cm": 160, "weight_kg": 55},
        headers={"Authorization": "Bearer A"},
    )
    assert r.status_code == 200
    assert r.json()["bio"]["age"] == 30

    # Bob must NOT see Alice's data (his is a fresh blank blueprint)
    r = await client.get("/api/blueprint", headers={"Authorization": "Bearer B"})
    assert r.status_code == 200
    assert r.json()["bio"]["age"] is None

    # Alice still sees hers
    r = await client.get("/api/blueprint", headers={"Authorization": "Bearer A"})
    assert r.json()["bio"]["age"] == 30


async def test_entra_mode_rejects_missing_token(client, monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "t")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "c")
    resp = await client.get("/api/blueprint")
    assert resp.status_code == 401

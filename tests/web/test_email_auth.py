"""Tests for email/password auth, onboarding, and account reset."""
from __future__ import annotations

from futureself.web.passwords import hash_password, verify_password


def _creds(email: str = "user@example.com", password: str = "password123") -> dict:
    return {"email": email, "password": password}


# ---------------------------------------------------------------------------
# passwords
# ---------------------------------------------------------------------------


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)
    # random salt → different encoded hash each time, but both verify
    assert h != hash_password("s3cret-pass")


def test_verify_rejects_garbage():
    assert verify_password("x", "not-a-valid-hash") is False


# ---------------------------------------------------------------------------
# register / login
# ---------------------------------------------------------------------------


async def test_register_returns_token(client):
    r = await client.post("/api/auth/register", json=_creds())
    assert r.status_code == 200
    assert len(r.json()["session_token"]) >= 30


async def test_register_duplicate_email_409(client):
    await client.post("/api/auth/register", json=_creds("dup@example.com"))
    r = await client.post("/api/auth/register", json=_creds("dup@example.com"))
    assert r.status_code == 409


async def test_register_invalid_email_422(client):
    r = await client.post("/api/auth/register", json=_creds("notanemail"))
    assert r.status_code == 422


async def test_register_short_password_422(client):
    r = await client.post("/api/auth/register", json={"email": "a@b.co", "password": "short"})
    assert r.status_code == 422


async def test_login_success(client):
    await client.post("/api/auth/register", json=_creds("c@example.com"))
    r = await client.post("/api/auth/login", json=_creds("c@example.com"))
    assert r.status_code == 200
    assert r.json()["session_token"]


async def test_login_wrong_password_401(client):
    await client.post("/api/auth/register", json=_creds("d@example.com"))
    r = await client.post("/api/auth/login", json=_creds("d@example.com", "wrongpass1"))
    assert r.status_code == 401


async def test_login_unknown_email_401(client):
    r = await client.post("/api/auth/login", json=_creds("nobody@example.com"))
    assert r.status_code == 401


async def test_email_is_normalized(client):
    await client.post("/api/auth/register", json=_creds("MixedCase@Example.com"))
    r = await client.post("/api/auth/login", json=_creds("mixedcase@example.com"))
    assert r.status_code == 200


async def test_two_users_coexist(client):
    t1 = (await client.post("/api/auth/register", json=_creds("u1@example.com"))).json()["session_token"]
    t2 = (await client.post("/api/auth/register", json=_creds("u2@example.com"))).json()["session_token"]
    assert t1 != t2


# ---------------------------------------------------------------------------
# onboarding + reset + logout
# ---------------------------------------------------------------------------


async def _register(client, email: str = "flow@example.com") -> dict:
    tok = (await client.post("/api/auth/register", json=_creds(email))).json()["session_token"]
    return {"Authorization": f"Bearer {tok}"}


async def test_new_account_starts_not_onboarded(client):
    h = await _register(client, "onb1@example.com")
    bp = (await client.get("/api/blueprint", headers=h)).json()
    assert bp["onboarded"] is False


async def test_onboarding_complete_sets_flag(client):
    h = await _register(client, "onb2@example.com")
    assert (await client.post("/api/onboarding/complete", headers=h)).status_code == 200
    bp = (await client.get("/api/blueprint", headers=h)).json()
    assert bp["onboarded"] is True


async def test_account_reset_clears_blueprint_and_onboarding(client):
    h = await _register(client, "reset@example.com")
    await client.patch("/api/blueprint/bio", json={"age": 42}, headers=h)
    await client.post("/api/onboarding/complete", headers=h)
    bp = (await client.get("/api/blueprint", headers=h)).json()
    assert bp["bio"]["age"] == 42 and bp["onboarded"] is True

    assert (await client.post("/api/account/reset", headers=h)).status_code == 200
    bp2 = (await client.get("/api/blueprint", headers=h)).json()
    assert bp2["bio"]["age"] is None
    assert bp2["onboarded"] is False


async def test_logout_invalidates_token(client):
    h = await _register(client, "logout@example.com")
    assert (await client.get("/api/blueprint", headers=h)).status_code == 200
    assert (await client.post("/api/auth/logout", headers=h)).status_code == 200
    assert (await client.get("/api/blueprint", headers=h)).status_code == 401

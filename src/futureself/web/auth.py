"""Microsoft Entra ID (Azure AD) access-token validation.

Active only when ``ENTRA_TENANT_ID`` and ``ENTRA_CLIENT_ID`` are set; otherwise
the BFF stays in anonymous session-token mode (so the app keeps working until the
frontend is wired to MSAL). When active, every protected request must carry a
valid Entra Bearer token: signature verified against the tenant JWKS, plus
issuer / audience / expiry. The immutable ``oid`` claim is the canonical user key
(see futureself-spec.md §6.5) — never trust a user_id from request input.

PyJWT[crypto] is provided transitively by ``msal`` / ``mcp`` (both prod deps).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient


class AuthError(Exception):
    """Raised when a token is missing, malformed, or fails validation."""


def auth_enabled() -> bool:
    """True when Entra auth is configured (both tenant and client IDs present)."""
    return bool(os.getenv("ENTRA_TENANT_ID") and os.getenv("ENTRA_CLIENT_ID"))


@lru_cache(maxsize=4)
def _jwks_client(tenant_id: str) -> PyJWKClient:
    """Cached JWKS client for a tenant (PyJWKClient caches keys internally)."""
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    )


def validate_token(token: str) -> dict[str, Any]:
    """Validate an Entra token and return its claims, or raise :class:`AuthError`.

    Verifies the RS256 signature against the tenant JWKS and checks issuer,
    audience, and expiry. Accepts both ID tokens (``aud = <client>``) and API
    access tokens (``aud = api://<client>``); override with ``ENTRA_AUDIENCE``.
    """
    tenant = os.environ["ENTRA_TENANT_ID"]
    client = os.environ["ENTRA_CLIENT_ID"]
    audiences = [client, f"api://{client}"]
    if extra := os.getenv("ENTRA_AUDIENCE"):
        audiences.append(extra)

    try:
        signing_key = _jwks_client(tenant).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
        )
    except Exception as exc:  # noqa: BLE001 — any decode/JWKS failure is an auth failure
        raise AuthError(str(exc)) from exc

    if not claims.get("oid"):
        raise AuthError("token missing required 'oid' claim")
    return claims


def bearer_token(authorization: str | None) -> str | None:
    """Extract the Bearer token from an Authorization header value."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer ") :]

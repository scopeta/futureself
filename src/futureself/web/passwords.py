"""Password hashing for email/password auth — stdlib only (no native deps).

Uses PBKDF2-HMAC-SHA256 with a per-user random salt. Format:
``pbkdf2_sha256$<iterations>$<b64 salt>$<b64 hash>``. Suitable for a
self-hosted trial app; swap for argon2/bcrypt if this grows.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    """Return an encoded PBKDF2 hash for ``password``."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return (
        f"pbkdf2_sha256${_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored encoded hash."""
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

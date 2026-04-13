"""Server-side session management for the FutureSelf web UI.

Sessions are stored in-memory on ``app.state``. No persistence — sessions
are lost on server restart.  Phase 4 will replace this with a database.
"""
from __future__ import annotations

import uuid
from typing import Any

from starlette.requests import Request

from futureself.schemas import UserBlueprint


def create_session(
    app_state: Any,
    blueprint: UserBlueprint,
) -> str:
    """Create a new session and return its token."""
    token = str(uuid.uuid4())
    app_state.sessions[token] = blueprint
    app_state.conversations[token] = []
    return token


def get_blueprint(request: Request) -> UserBlueprint | None:
    """Return the session's blueprint, or ``None`` if no valid session."""
    token = request.cookies.get("fs_session")
    if not token:
        return None
    return request.app.state.sessions.get(token)


def get_token(request: Request) -> str | None:
    """Return the session token from the cookie, or ``None``."""
    token = request.cookies.get("fs_session")
    if token and token in request.app.state.sessions:
        return token
    return None


def get_blueprint_from_bearer(request: Request) -> UserBlueprint | None:
    """Return the session's blueprint from an ``Authorization: Bearer`` header.

    Used by the JSON API layer (React SPA) instead of cookie-based auth.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    return request.app.state.sessions.get(token)


def get_token_from_bearer(request: Request) -> str | None:
    """Return the validated token from an ``Authorization: Bearer`` header, or ``None``."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    return token if token in request.app.state.sessions else None

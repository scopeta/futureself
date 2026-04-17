"""Server-side session management for the FutureSelf web UI.

Sessions are persisted in PostgreSQL via SQLAlchemy.
Each session token maps to a User row; the User has one Blueprint row
that stores the full UserBlueprint as JSONB.
"""
from __future__ import annotations

import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from futureself.db.models import Blueprint, Session, User
from futureself.schemas import UserBlueprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_from_request(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return auth[len("Bearer "):]


# ---------------------------------------------------------------------------
# Public API — called by api.py routes
# ---------------------------------------------------------------------------


async def create_session(db: AsyncSession, blueprint: UserBlueprint) -> str:
    """Create a session and return the token."""
    token = secrets.token_urlsafe(24)  # 32 URL-safe chars, cryptographically random
    async with db.begin():  # atomic: all three inserts commit together or not at all
        user = User()
        db.add(user)
        await db.flush()  # populate user.id within the transaction
        db.add(Blueprint(user_id=user.id, data=blueprint.model_dump()))
        db.add(Session(token=token, user_id=user.id))
    return token


async def get_blueprint_from_bearer(
    request: Request, db: AsyncSession
) -> UserBlueprint | None:
    """Load UserBlueprint for the token in the Authorization header."""
    token = _token_from_request(request)
    if not token:
        return None
    row = await db.scalar(
        select(Blueprint)
        .join(Session, Session.user_id == Blueprint.user_id)
        .where(Session.token == token)
    )
    if row is None:
        return None
    return UserBlueprint.model_validate(row.data)


async def get_token_from_bearer(
    request: Request, db: AsyncSession
) -> str | None:
    """Return the token if it exists in the session store, else None."""
    token = _token_from_request(request)
    if not token:
        return None
    return await db.scalar(select(Session.token).where(Session.token == token))


async def save_blueprint(
    token: str, blueprint: UserBlueprint, db: AsyncSession
) -> None:
    """Persist the updated blueprint after a turn."""
    session_row = await db.scalar(select(Session).where(Session.token == token))
    if session_row is None:
        return
    await db.execute(
        update(Blueprint)
        .where(Blueprint.user_id == session_row.user_id)
        .values(data=blueprint.model_dump())
    )
    await db.commit()

"""Server-side session management for the FutureSelf web UI.

Sessions are persisted in PostgreSQL via SQLAlchemy.
Each session token maps to a User row; the User has one Blueprint row
that stores the full UserBlueprint as JSONB.
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from futureself.db.models import Blueprint, Message, Session, User
from futureself.schemas import ConversationTurn, UserBlueprint


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


# ---------------------------------------------------------------------------
# Identity resolution by internal user_id (used by both auth modes)
#
# The authorization invariant (spec §6.5): every user-data query is filtered by
# a `user_id` resolved server-side — from a validated Entra token (oid → user_id)
# or from the anonymous session token — never from client-supplied input.
# ---------------------------------------------------------------------------


async def get_user_id_from_token(
    request: Request, db: AsyncSession
) -> uuid.UUID | None:
    """Anonymous mode: map the Bearer session token to its internal user_id."""
    token = _token_from_request(request)
    if not token:
        return None
    return await db.scalar(select(Session.user_id).where(Session.token == token))


async def get_or_create_user_by_oid(db: AsyncSession, oid: str) -> uuid.UUID:
    """Entra mode: resolve an Entra `oid` to its internal user_id, creating the
    user (and a blank blueprint) on first login. The oid is the only trusted key."""
    user_id = await db.scalar(select(User.id).where(User.oid == oid))
    if user_id is not None:
        return user_id

    user = User(oid=oid)
    db.add(user)
    try:
        await db.flush()  # assign user.id
        db.add(Blueprint(user_id=user.id, data=UserBlueprint().model_dump()))
        await db.commit()
        return user.id
    except IntegrityError:
        # Concurrent first-login for the same oid — the other writer won.
        await db.rollback()
        existing = await db.scalar(select(User.id).where(User.oid == oid))
        if existing is None:
            raise
        return existing


async def get_blueprint_by_user_id(
    db: AsyncSession, user_id: uuid.UUID
) -> UserBlueprint | None:
    """Load the blueprint for a resolved user_id."""
    row = await db.scalar(select(Blueprint).where(Blueprint.user_id == user_id))
    return UserBlueprint.model_validate(row.data) if row is not None else None


async def save_blueprint_by_user_id(
    user_id: uuid.UUID, blueprint: UserBlueprint, db: AsyncSession
) -> None:
    """Persist the blueprint for a resolved user_id."""
    await db.execute(
        update(Blueprint)
        .where(Blueprint.user_id == user_id)
        .values(data=blueprint.model_dump())
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Conversation transcript (append-only ``messages`` table, decoupled from the
# Blueprint). Isolated per user by the server-resolved user_id (auth invariant).
# ---------------------------------------------------------------------------


async def append_messages(
    db: AsyncSession, user_id: uuid.UUID, turns: list[ConversationTurn]
) -> None:
    """Append conversation turns for a user (in order)."""
    for turn in turns:
        db.add(Message(user_id=user_id, role=turn.role, content=turn.content))
    await db.commit()


async def get_recent_messages(
    db: AsyncSession, user_id: uuid.UUID, limit: int
) -> list[ConversationTurn]:
    """Return the user's most recent ``limit`` turns, oldest→newest."""
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
    ).all()
    return [ConversationTurn(role=r.role, content=r.content) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Email/password accounts. Login/registration issue the same Bearer session
# token the anonymous flow uses; the auth invariant (user_id resolved from the
# server-side session token) is unchanged.
# ---------------------------------------------------------------------------


async def register_user(
    db: AsyncSession, email: str, password_hash: str
) -> str | None:
    """Create an email/password user + blank blueprint + session.

    Returns the session token, or ``None`` if the email is already registered
    (enforced by the unique index on ``users.email``).
    """
    token = secrets.token_urlsafe(24)
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    try:
        await db.flush()  # assign user.id + trip the unique index if email taken
        db.add(Blueprint(user_id=user.id, data=UserBlueprint().model_dump()))
        db.add(Session(token=token, user_id=user.id))
        await db.commit()
        return token
    except IntegrityError:
        await db.rollback()
        return None


async def get_user_credentials(
    db: AsyncSession, email: str
) -> tuple[uuid.UUID, str] | None:
    """Return ``(user_id, password_hash)`` for an email, or ``None``."""
    row = (
        await db.execute(
            select(User.id, User.password_hash).where(User.email == email)
        )
    ).first()
    if row is None or row.password_hash is None:
        return None
    return row.id, row.password_hash


async def create_session_for_user(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Issue a new session token for an existing user (login)."""
    token = secrets.token_urlsafe(24)
    db.add(Session(token=token, user_id=user_id))
    await db.commit()
    return token


async def delete_session(db: AsyncSession, token: str) -> None:
    """Invalidate a session token (logout)."""
    await db.execute(delete(Session).where(Session.token == token))
    await db.commit()


async def reset_user_data(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete the user's transcript and reset their Blueprint to blank.

    The account (login) is kept so the user stays signed in and can re-onboard.
    """
    await db.execute(delete(Message).where(Message.user_id == user_id))
    await db.execute(
        update(Blueprint)
        .where(Blueprint.user_id == user_id)
        .values(data=UserBlueprint().model_dump())
    )
    await db.commit()


async def set_onboarded(
    db: AsyncSession, user_id: uuid.UUID, value: bool = True
) -> None:
    """Set the Blueprint's ``onboarded`` flag."""
    row = await db.scalar(select(Blueprint).where(Blueprint.user_id == user_id))
    if row is None:
        return
    updated = UserBlueprint.model_validate(row.data).model_copy(
        update={"onboarded": value}
    )
    await db.execute(
        update(Blueprint)
        .where(Blueprint.user_id == user_id)
        .values(data=updated.model_dump())
    )
    await db.commit()

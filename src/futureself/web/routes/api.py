"""JSON REST API routes for the FutureSelf React frontend."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from futureself.db.engine import get_db
from futureself.schemas import (
    BioData,
    BiomarkerEntry,
    ContextData,
    ConversationTurn,
    PsychData,
    Supplement,
    UserBlueprint,
)
from futureself.web.agent_client import _HISTORY_WINDOW, synthesize
from futureself.web.auth import AuthError, auth_enabled, bearer_token, validate_token
from futureself.web.passwords import hash_password, verify_password
from futureself.web.session import (
    append_messages,
    create_session,
    create_session_for_user,
    delete_session,
    get_blueprint_by_user_id,
    get_or_create_user_by_oid,
    get_recent_messages,
    get_user_credentials,
    get_user_id_from_token,
    register_user,
    reset_user_data,
    save_blueprint_by_user_id,
    set_onboarded,
)

router = APIRouter()
logger = logging.getLogger(__name__)

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_identity(request: Request, db: DB) -> tuple[uuid.UUID, UserBlueprint]:
    """Resolve the caller's internal user_id and load their blueprint, or raise 401.

    Authorization invariant (spec §6.5): the user_id is derived **only** from the
    server-validated credential — a validated Entra token's ``oid`` when auth is
    enabled, otherwise the anonymous session token — never from request input.
    """
    if auth_enabled():
        token = bearer_token(request.headers.get("Authorization"))
        if not token:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        try:
            claims = validate_token(token)
        except AuthError:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from None
        user_id = await get_or_create_user_by_oid(db, claims["oid"])
    else:
        user_id = await get_user_id_from_token(request, db)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid or missing session token")

    blueprint = await get_blueprint_by_user_id(db, user_id)
    if blueprint is None:
        raise HTTPException(status_code=401, detail="No blueprint for this user")
    return user_id, blueprint


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@router.post("/session/create")
async def session_create(db: DB) -> dict:
    """Create a blank anonymous session and return the session token."""
    blueprint = UserBlueprint()
    token = await create_session(db, blueprint)
    return {"session_token": token}


# ---------------------------------------------------------------------------
# Email/password auth
# ---------------------------------------------------------------------------


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")
    return email


@router.post("/auth/register")
async def auth_register(body: AuthRequest, db: DB) -> dict:
    """Register a new email/password account; returns a session token."""
    email = _normalize_email(body.email)
    token = await register_user(db, email, hash_password(body.password))
    if token is None:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists."
        )
    return {"session_token": token}


@router.post("/auth/login")
async def auth_login(body: AuthRequest, db: DB) -> dict:
    """Log in with email/password; returns a fresh session token."""
    email = _normalize_email(body.email)
    creds = await get_user_credentials(db, email)
    if creds is None or not verify_password(body.password, creds[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = await create_session_for_user(db, creds[0])
    return {"session_token": token}


@router.post("/auth/logout")
async def auth_logout(request: Request, db: DB) -> dict:
    """Invalidate the current session token."""
    token = bearer_token(request.headers.get("Authorization"))
    if token:
        await delete_session(db, token)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Account: onboarding completion + data reset
# ---------------------------------------------------------------------------


@router.post("/onboarding/complete")
async def onboarding_complete(request: Request, db: DB) -> dict:
    """Mark the user's onboarding as complete."""
    user_id, _ = await _require_identity(request, db)
    await set_onboarded(db, user_id, True)
    return {"ok": True}


@router.post("/account/reset")
async def account_reset(request: Request, db: DB) -> dict:
    """Delete all of the user's data (Blueprint + transcript) and reset onboarding.

    Keeps the account/login so the user stays signed in and re-onboards.
    """
    user_id, _ = await _require_identity(request, db)
    await reset_user_data(db, user_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    # Cap input size: rejects empty and oversized messages (cost/abuse control on
    # the anonymous, paid-LLM endpoint). Oversize/empty → 422 before any LLM call.
    message: str = Field(min_length=1, max_length=8000)


@router.post("/chat/send")
async def chat_send(body: ChatRequest, request: Request, db: DB) -> dict:
    """Process a user message and return the Future Self reply.

    Delegates synthesis to the deployed Foundry hosted agent (spec §11) with a
    bounded recent-turns window, then appends the exchange to the ``messages``
    store. The Blueprint (domain state) is **not** written by a chat turn.
    Requires ``Authorization: Bearer <token>`` header.
    """
    user_id, blueprint = await _require_identity(request, db)
    try:
        recent = await get_recent_messages(db, user_id, _HISTORY_WINDOW)
        reply = await synthesize(blueprint, recent, body.message)
        await append_messages(
            db,
            user_id,
            [
                ConversationTurn(role="user", content=body.message),
                ConversationTurn(role="assistant", content=reply),
            ],
        )
    except Exception:
        # Transient failures — hosted-agent overload/timeout, or the serverless
        # Azure SQL DB resuming from auto-pause (error 40613). Don't surface a raw
        # 500; log the traceback and return a retryable 503. (401s from
        # _require_identity are raised above and unaffected.)
        logger.exception("chat/send failed")
        raise HTTPException(
            status_code=503,
            detail="I'm having trouble gathering my thoughts right now — give me a moment and try again.",
        ) from None
    return {"reply": reply}


# ---------------------------------------------------------------------------
# Blueprint — read
# ---------------------------------------------------------------------------


@router.get("/blueprint")
async def blueprint_get(request: Request, db: DB) -> dict:
    """Return the current user blueprint as JSON."""
    _, blueprint = await _require_identity(request, db)
    return blueprint.model_dump()


# ---------------------------------------------------------------------------
# Blueprint — mutations
# ---------------------------------------------------------------------------


@router.patch("/blueprint/bio")
async def blueprint_patch_bio(body: BioData, request: Request, db: DB) -> dict:
    """Update bio fields (age, sex, height, weight, conditions, medications)."""
    user_id, blueprint = await _require_identity(request, db)
    updated = blueprint.model_copy(update={"bio": body})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


@router.patch("/blueprint/context")
async def blueprint_patch_context(body: ContextData, request: Request, db: DB) -> dict:
    """Update context fields (location, occupation, income, family)."""
    user_id, blueprint = await _require_identity(request, db)
    updated = blueprint.model_copy(update={"context": body})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


@router.patch("/blueprint/psych")
async def blueprint_patch_psych(body: PsychData, request: Request, db: DB) -> dict:
    """Update psychological fields (goals, fears, stress, flags)."""
    user_id, blueprint = await _require_identity(request, db)
    updated = blueprint.model_copy(update={"psych": body})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


@router.post("/blueprint/biomarkers")
async def blueprint_add_biomarker(
    body: BiomarkerEntry, request: Request, db: DB
) -> dict:
    """Add a biomarker entry to the history."""
    user_id, blueprint = await _require_identity(request, db)
    new_bio = blueprint.bio.model_copy(
        update={"biomarker_history": list(blueprint.bio.biomarker_history) + [body]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


@router.post("/blueprint/supplements")
async def blueprint_add_supplement(body: Supplement, request: Request, db: DB) -> dict:
    """Add or replace a supplement (matched by name)."""
    user_id, blueprint = await _require_identity(request, db)
    existing = [s for s in blueprint.bio.supplements if s.name != body.name]
    new_bio = blueprint.bio.model_copy(
        update={"supplements": existing + [body]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


@router.delete("/blueprint/supplements/{name}")
async def blueprint_remove_supplement(
    name: str, request: Request, db: DB
) -> dict:
    """Remove a supplement by name."""
    user_id, blueprint = await _require_identity(request, db)
    new_bio = blueprint.bio.model_copy(
        update={"supplements": [s for s in blueprint.bio.supplements if s.name != name]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint_by_user_id(user_id, updated, db)
    return updated.model_dump()


# ---------------------------------------------------------------------------
# Blueprint — data quality
# ---------------------------------------------------------------------------


@router.get("/blueprint/quality")
async def blueprint_quality(request: Request, db: DB) -> dict:
    """Return a data quality report for the current blueprint."""
    from futureself.blueprint_quality import check_quality  # noqa: PLC0415

    _, blueprint = await _require_identity(request, db)
    return check_quality(blueprint).model_dump()

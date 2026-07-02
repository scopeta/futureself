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
from futureself.web.session import (
    append_messages,
    create_session,
    get_blueprint_by_user_id,
    get_or_create_user_by_oid,
    get_recent_messages,
    get_user_id_from_token,
    save_blueprint_by_user_id,
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
    """Create a blank session and return the session token."""
    blueprint = UserBlueprint()
    token = await create_session(db, blueprint)
    return {"session_token": token}


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
    recent = await get_recent_messages(db, user_id, _HISTORY_WINDOW)
    try:
        reply = await synthesize(blueprint, recent, body.message)
    except Exception:
        # The hosted agent / LLM provider can return transient errors (overload,
        # timeouts) or the endpoint may be briefly unreachable. Don't surface a
        # raw 500 — log the full traceback and return a retryable 503.
        logger.exception("hosted agent synthesis failed for chat/send")
        raise HTTPException(
            status_code=503,
            detail="I'm having trouble gathering my thoughts right now — give me a moment and try again.",
        ) from None

    await append_messages(
        db,
        user_id,
        [
            ConversationTurn(role="user", content=body.message),
            ConversationTurn(role="assistant", content=reply),
        ],
    )
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

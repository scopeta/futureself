"""JSON REST API routes for the FutureSelf React frontend."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from futureself.db.engine import get_db
from futureself.orchestrator import run_turn
from futureself.schemas import (
    BioData,
    BiomarkerEntry,
    ContextData,
    PsychData,
    Supplement,
    UserBlueprint,
)
from futureself.web.session import (
    create_session,
    get_blueprint_from_bearer,
    get_token_from_bearer,
    save_blueprint,
)

router = APIRouter()

DB = Annotated[AsyncSession | None, Depends(get_db)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_blueprint(request: Request, db: DB) -> tuple[str, UserBlueprint]:
    """Return (token, blueprint) or raise 401."""
    token = await get_token_from_bearer(request, db)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid or missing session token")
    blueprint = await get_blueprint_from_bearer(request, db)
    if blueprint is None:
        raise HTTPException(status_code=401, detail="Invalid or missing session token")
    return token, blueprint


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
    message: str


@router.post("/chat/send")
async def chat_send(body: ChatRequest, request: Request, db: DB) -> dict:
    """Process a user message and return the Future Self reply.

    Requires ``Authorization: Bearer <token>`` header.
    """
    token, blueprint = await _require_blueprint(request, db)
    result = await run_turn(blueprint, body.message)
    await save_blueprint(token, result.updated_blueprint, db)
    return {"reply": result.user_facing_reply}


# ---------------------------------------------------------------------------
# Blueprint — read
# ---------------------------------------------------------------------------


@router.get("/blueprint")
async def blueprint_get(request: Request, db: DB) -> dict:
    """Return the current user blueprint as JSON."""
    _, blueprint = await _require_blueprint(request, db)
    return blueprint.model_dump()


# ---------------------------------------------------------------------------
# Blueprint — mutations
# ---------------------------------------------------------------------------


@router.patch("/blueprint/bio")
async def blueprint_patch_bio(body: BioData, request: Request, db: DB) -> dict:
    """Update bio fields (age, sex, height, weight, conditions, medications)."""
    token, blueprint = await _require_blueprint(request, db)
    updated = blueprint.model_copy(update={"bio": body})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


@router.patch("/blueprint/context")
async def blueprint_patch_context(body: ContextData, request: Request, db: DB) -> dict:
    """Update context fields (location, occupation, income, family)."""
    token, blueprint = await _require_blueprint(request, db)
    updated = blueprint.model_copy(update={"context": body})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


@router.patch("/blueprint/psych")
async def blueprint_patch_psych(body: PsychData, request: Request, db: DB) -> dict:
    """Update psychological fields (goals, fears, stress, flags)."""
    token, blueprint = await _require_blueprint(request, db)
    updated = blueprint.model_copy(update={"psych": body})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


@router.post("/blueprint/biomarkers")
async def blueprint_add_biomarker(
    body: BiomarkerEntry, request: Request, db: DB
) -> dict:
    """Add a biomarker entry to the history."""
    token, blueprint = await _require_blueprint(request, db)
    new_bio = blueprint.bio.model_copy(
        update={"biomarker_history": list(blueprint.bio.biomarker_history) + [body]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


@router.post("/blueprint/supplements")
async def blueprint_add_supplement(body: Supplement, request: Request, db: DB) -> dict:
    """Add or replace a supplement (matched by name)."""
    token, blueprint = await _require_blueprint(request, db)
    existing = [s for s in blueprint.bio.supplements if s.name != body.name]
    new_bio = blueprint.bio.model_copy(
        update={"supplements": existing + [body]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


@router.delete("/blueprint/supplements/{name}")
async def blueprint_remove_supplement(
    name: str, request: Request, db: DB
) -> dict:
    """Remove a supplement by name."""
    token, blueprint = await _require_blueprint(request, db)
    new_bio = blueprint.bio.model_copy(
        update={"supplements": [s for s in blueprint.bio.supplements if s.name != name]}
    )
    updated = blueprint.model_copy(update={"bio": new_bio})
    await save_blueprint(token, updated, db)
    return updated.model_dump()


# ---------------------------------------------------------------------------
# Blueprint — data quality
# ---------------------------------------------------------------------------


@router.get("/blueprint/quality")
async def blueprint_quality(request: Request, db: DB) -> dict:
    """Return a data quality report for the current blueprint."""
    from futureself.blueprint_quality import check_quality  # noqa: PLC0415

    _, blueprint = await _require_blueprint(request, db)
    return check_quality(blueprint).model_dump()

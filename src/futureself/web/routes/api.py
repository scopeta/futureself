"""JSON REST API routes for the FutureSelf React frontend."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from futureself.orchestrator import run_turn
from futureself.schemas import UserBlueprint
from futureself.web.session import (
    create_session,
    get_blueprint_from_bearer,
    get_token_from_bearer,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@router.post("/session/create")
async def session_create(request: Request) -> dict:
    """Create a blank session and return the session token.

    Called by the React frontend when the user clicks "Begin the conversation".
    """
    blueprint = UserBlueprint()
    token = create_session(request.app.state, blueprint)
    return {"session_token": token}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


@router.post("/chat/send")
async def chat_send(body: ChatRequest, request: Request) -> dict:
    """Process a user message and return the Future Self reply.

    Requires ``Authorization: Bearer <token>`` header.
    """
    token = get_token_from_bearer(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid or missing session token")

    blueprint = get_blueprint_from_bearer(request)

    result = await run_turn(blueprint, body.message)

    # Persist updated state
    request.app.state.sessions[token] = result.updated_blueprint

    return {"reply": result.user_facing_reply}


# ---------------------------------------------------------------------------
# Blueprint (stub — wired up fully in Phase 6)
# ---------------------------------------------------------------------------


@router.get("/blueprint")
async def blueprint_get(request: Request) -> dict:
    """Return the current user blueprint as JSON.

    Requires ``Authorization: Bearer <token>`` header.
    """
    blueprint = get_blueprint_from_bearer(request)
    if blueprint is None:
        raise HTTPException(status_code=401, detail="Invalid or missing session token")

    return blueprint.model_dump()

"""WhatsApp channel routes — link management (auth'd) + the Twilio webhook.

The webhook carries no Bearer token; Twilio's request signature is the trust
boundary (see ``web/whatsapp.py``). The webhook ACKs with empty TwiML **before
any database work** — Twilio times out at ~15s while a serverless Azure SQL
resume takes 30–60s and an agent turn longer still — so ALL processing (link
codes, phone lookup, the turn) happens in a background task that retries across
the DB resume and replies via Twilio's REST API.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from sqlalchemy.exc import DBAPIError

from futureself.db.engine import session_factory
from futureself.schemas import ConversationTurn
from futureself.web import whatsapp
from futureself.web.agent_client import _HISTORY_WINDOW, synthesize
from futureself.web.routes.api import DB, _require_identity
from futureself.web.session import (
    append_messages,
    consume_link_code,
    get_blueprint_by_user_id,
    get_linked_phone,
    get_recent_messages,
    get_user_id_by_phone,
    set_link_code,
    unlink_whatsapp,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"^\s*link\s+([a-z0-9]{4,12})\s*$", re.IGNORECASE)

_NOT_LINKED_MSG = (
    "This number isn't linked to a FutureSelf account yet. Sign in on the web "
    "app, open Settings → Link WhatsApp, and text me: LINK <your code>"
)
_LINKED_MSG = (
    "You're linked! This chat is now a direct line to your future self — "
    "same profile, same conversation. Ask me anything."
)
_BAD_CODE_MSG = (
    "That code didn't match. Generate a fresh one in the web app "
    "(Settings → Link WhatsApp) and try again."
)
_ERROR_MSG = (
    "I'm having trouble gathering my thoughts right now — give me a moment "
    "and message me again."
)

T = TypeVar("T")


async def _with_db(fn: Callable[..., Awaitable[T]]) -> T:
    """Run ``fn(db)`` in a fresh session, retrying across a serverless DB resume.

    Azure SQL serverless auto-pauses when idle; the resume can take 30–60s and
    surfaces as ``DBAPIError``. Background WhatsApp processing can afford to
    wait it out — the web path's fail-fast 503 doesn't apply here.
    """
    factory = session_factory()
    for attempt in range(4):
        try:
            async with factory() as db:
                return await fn(db)
        except DBAPIError:
            if attempt == 3:
                raise
            logger.warning("whatsapp: DB resuming, retry %d/3 in 15s", attempt + 1)
            await asyncio.sleep(15)
    raise RuntimeError("unreachable")


async def _send_or_log(phone: str, message: str) -> None:
    """Best-effort outbound send — a failed notification must not raise."""
    try:
        await whatsapp.send_whatsapp(phone, message)
    except Exception:
        logger.exception("whatsapp send failed")


# ---------------------------------------------------------------------------
# Link management (called by the web UI, Bearer-authenticated)
# ---------------------------------------------------------------------------


@router.post("/whatsapp/link")
async def whatsapp_link(request: Request, db: DB) -> dict:
    """Generate a one-time link code for the signed-in user."""
    if not whatsapp.enabled():
        raise HTTPException(status_code=409, detail="WhatsApp channel is not configured.")
    user_id, _ = await _require_identity(request, db)
    code = whatsapp.new_link_code()
    await set_link_code(db, user_id, code)
    return {
        "code": code,
        "instructions": f"Send this message on WhatsApp: LINK {code}",
    }


@router.get("/whatsapp/status")
async def whatsapp_status(request: Request, db: DB) -> dict:
    """Whether the channel is configured and this user's linked number."""
    user_id, _ = await _require_identity(request, db)
    phone = await get_linked_phone(db, user_id)
    return {"enabled": whatsapp.enabled(), "phone": phone}


@router.post("/whatsapp/unlink")
async def whatsapp_unlink(request: Request, db: DB) -> dict:
    """Remove the user's WhatsApp binding."""
    user_id, _ = await _require_identity(request, db)
    await unlink_whatsapp(db, user_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Twilio webhook (signature-authenticated; no Bearer token)
# ---------------------------------------------------------------------------


async def _run_whatsapp_turn(user_id: uuid.UUID, phone: str, text: str) -> None:
    """Run the agent turn and deliver the reply via Twilio (background)."""

    async def _load(db):  # noqa: ANN001, ANN202
        return (
            await get_blueprint_by_user_id(db, user_id),
            await get_recent_messages(db, user_id, _HISTORY_WINDOW),
        )

    blueprint, recent = await _with_db(_load)
    if blueprint is None:
        await _send_or_log(phone, _NOT_LINKED_MSG)
        return
    reply = await synthesize(blueprint, recent, text)

    async def _persist(db):  # noqa: ANN001, ANN202
        await append_messages(
            db,
            user_id,
            [
                ConversationTurn(role="user", content=text),
                ConversationTurn(role="assistant", content=reply),
            ],
        )

    await _with_db(_persist)
    await whatsapp.send_whatsapp(phone, reply)


async def _process_inbound(phone: str, text: str) -> None:
    """Background task for EVERYTHING after the ACK: link codes, lookup, turn.

    No DB work happens in the webhook request itself — Twilio's ~15s timeout
    can't survive a serverless DB resume. All replies go via the REST API.
    Any failure degrades to a best-effort apology.
    """
    try:
        if match := _LINK_RE.match(text):
            code = match.group(1)
            user_id = await _with_db(lambda db: consume_link_code(db, code, phone))
            await _send_or_log(phone, _LINKED_MSG if user_id else _BAD_CODE_MSG)
            return

        user_id = await _with_db(lambda db: get_user_id_by_phone(db, phone))
        if user_id is None:
            await _send_or_log(phone, _NOT_LINKED_MSG)
            return

        await _run_whatsapp_turn(user_id, phone, text)
    except Exception:
        logger.exception("whatsapp inbound processing failed")
        await _send_or_log(phone, _ERROR_MSG)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    """Inbound Twilio message: validate the signature, ACK, process in background."""
    if not whatsapp.enabled():
        raise HTTPException(status_code=404, detail="Not found")

    form = {k: str(v) for k, v in (await request.form()).items()}
    url = whatsapp.webhook_url(str(request.url))
    if not whatsapp.validate_signature(
        url, form, request.headers.get("X-Twilio-Signature")
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")

    phone = whatsapp.normalize_phone(form.get("From", ""))
    text = (form.get("Body") or "").strip()
    if phone and text:
        background.add_task(_process_inbound, phone, text)
    return Response(content=whatsapp.EMPTY_TWIML, media_type="text/xml")

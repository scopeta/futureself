"""WhatsApp channel routes — link management (auth'd) + the Twilio webhook.

The webhook carries no Bearer token; Twilio's request signature is the trust
boundary (see ``web/whatsapp.py``). Chat turns are answered asynchronously via
Twilio's REST API because an agent turn can exceed the webhook timeout.
"""
from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

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
_ERROR_MSG = (
    "I'm having trouble gathering my thoughts right now — give me a moment "
    "and message me again."
)


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
    """Background task: run the agent turn and deliver the reply via Twilio.

    Owns its DB sessions (the webhook request's session is gone by now). Any
    failure degrades to a best-effort apology message.
    """
    try:
        factory = session_factory()
        async with factory() as db:
            blueprint = await get_blueprint_by_user_id(db, user_id)
            recent = await get_recent_messages(db, user_id, _HISTORY_WINDOW)
        if blueprint is None:
            await whatsapp.send_whatsapp(phone, _NOT_LINKED_MSG)
            return
        reply = await synthesize(blueprint, recent, text)
        async with factory() as db:
            await append_messages(
                db,
                user_id,
                [
                    ConversationTurn(role="user", content=text),
                    ConversationTurn(role="assistant", content=reply),
                ],
            )
        await whatsapp.send_whatsapp(phone, reply)
    except Exception:
        logger.exception("whatsapp turn failed")
        try:
            await whatsapp.send_whatsapp(phone, _ERROR_MSG)
        except Exception:
            logger.exception("whatsapp error notification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    """Inbound Twilio message: link codes reply inline; chat turns reply async."""
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
    if not phone or not text:
        return Response(content=whatsapp.EMPTY_TWIML, media_type="text/xml")

    # The webhook manages its own DB session (no Depends — signature-auth path).
    factory = session_factory()

    if match := _LINK_RE.match(text):
        async with factory() as db:
            user_id = await consume_link_code(db, match.group(1), phone)
        msg = _LINKED_MSG if user_id else "That code didn't match. Generate a fresh one in the web app (Settings → Link WhatsApp) and try again."
        return Response(content=whatsapp.reply_twiml(msg), media_type="text/xml")

    async with factory() as db:
        user_id = await get_user_id_by_phone(db, phone)
    if user_id is None:
        return Response(content=whatsapp.reply_twiml(_NOT_LINKED_MSG), media_type="text/xml")

    background.add_task(_run_whatsapp_turn, user_id, phone, text)
    return Response(content=whatsapp.EMPTY_TWIML, media_type="text/xml")

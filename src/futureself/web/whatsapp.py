"""WhatsApp channel via Twilio — webhook validation + outbound sends.

Spec §11.1 channel model: WhatsApp is a second **channel onto the same user** —
one Blueprint, one transcript, resolved by the server-side ``users.phone``
binding. Linking is code-based: the signed-in web user generates a one-time code
and texts ``LINK <code>`` to the sandbox/business number; the webhook binds the
sending phone to their account.

Feature-flagged: active only when ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN``
and ``TWILIO_WHATSAPP_FROM`` are set. Inbound webhooks are authenticated with
Twilio's ``X-Twilio-Signature`` (HMAC-SHA1 over URL + sorted form params) — the
webhook has no Bearer token, so the signature is the trust boundary.

Replies are sent **asynchronously** via Twilio's REST API (plain httpx, no SDK):
an agent turn can exceed Twilio's ~15s webhook timeout, so the webhook ACKs with
empty TwiML immediately and a background task delivers the reply.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

import httpx

_TWILIO_API = "https://api.twilio.com/2010-04-01"
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L ambiguity


def enabled() -> bool:
    """True when the Twilio WhatsApp channel is configured."""
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID")
        and os.getenv("TWILIO_AUTH_TOKEN")
        and os.getenv("TWILIO_WHATSAPP_FROM")
    )


def new_link_code() -> str:
    """Generate a short, unambiguous one-time link code (e.g. ``K7PQ2M``)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def normalize_phone(raw: str) -> str:
    """``whatsapp:+65912…`` → ``+65912…`` (E.164, no channel prefix)."""
    return raw.removeprefix("whatsapp:").strip()


def validate_signature(url: str, form: dict[str, str], signature: str | None) -> bool:
    """Check Twilio's request signature (HMAC-SHA1, base64).

    Twilio signs ``url + key1value1key2value2…`` with keys sorted
    alphabetically, using the account auth token as the HMAC key.
    """
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token or not signature:
        return False
    payload = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    digest = hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def webhook_url(request_url: str) -> str:
    """The exact URL Twilio signed.

    Behind the Container Apps proxy the app sees ``http://…`` while Twilio signed
    ``https://…``; ``TWILIO_WEBHOOK_URL`` (the URL configured in the Twilio
    console) overrides when set, else we upgrade the scheme.
    """
    override = os.getenv("TWILIO_WEBHOOK_URL", "")
    if override:
        return override
    if request_url.startswith("http://"):
        return "https://" + request_url[len("http://") :]
    return request_url


async def send_whatsapp(to_phone: str, body: str) -> None:
    """Send a WhatsApp message via Twilio's REST API (async, no SDK).

    Twilio caps message bodies at 1600 chars; longer replies are truncated with
    an ellipsis rather than failing the send.
    """
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    from_ = os.environ["TWILIO_WHATSAPP_FROM"]  # e.g. whatsapp:+14155238886
    if len(body) > 1600:
        body = body[:1597] + "..."
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_TWILIO_API}/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"From": from_, "To": f"whatsapp:{to_phone}", "Body": body},
        )
        resp.raise_for_status()


EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def reply_twiml(message: str) -> str:
    """Inline TwiML reply (used for instant responses like link confirmation)."""
    from xml.sax.saxutils import escape  # noqa: PLC0415

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{escape(message)}</Message></Response>"
    )

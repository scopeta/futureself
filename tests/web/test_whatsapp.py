"""Tests for the WhatsApp channel: linking, webhook auth, and chat turns."""
from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest

from futureself.web import whatsapp

SID = "ACtest"
TOKEN = "twilio-auth-token"
FROM = "whatsapp:+14155238886"
WEBHOOK = "https://test/api/whatsapp/webhook"


@pytest.fixture
def twilio_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", SID)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", FROM)


def _sign(url: str, form: dict[str, str]) -> str:
    payload = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    return base64.b64encode(
        hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


async def _register(client, email: str) -> dict:
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _post_webhook(client, form: dict[str, str], signature: str | None = None):
    headers = {}
    if signature is not None:
        headers["X-Twilio-Signature"] = signature
    return await client.post("/api/whatsapp/webhook", data=form, headers=headers)


# ---------------------------------------------------------------------------
# unit: helpers
# ---------------------------------------------------------------------------


def test_enabled_flag(monkeypatch, twilio_env):
    assert whatsapp.enabled() is True
    monkeypatch.delenv("TWILIO_AUTH_TOKEN")
    assert whatsapp.enabled() is False


def test_normalize_phone():
    assert whatsapp.normalize_phone("whatsapp:+6591234567") == "+6591234567"
    assert whatsapp.normalize_phone("+123") == "+123"


def test_validate_signature_roundtrip(twilio_env):
    form = {"From": "whatsapp:+65123", "Body": "hi"}
    good = _sign(WEBHOOK, form)
    assert whatsapp.validate_signature(WEBHOOK, form, good) is True
    assert whatsapp.validate_signature(WEBHOOK, form, "bad-signature") is False
    assert whatsapp.validate_signature(WEBHOOK, form, None) is False


def test_reply_twiml_escapes():
    xml = whatsapp.reply_twiml("a<b & c>d")
    assert "<Message>a&lt;b &amp; c&gt;d</Message>" in xml


def test_link_code_shape():
    code = whatsapp.new_link_code()
    assert len(code) == 6
    assert all(c in whatsapp._CODE_ALPHABET for c in code)


# ---------------------------------------------------------------------------
# link management endpoints
# ---------------------------------------------------------------------------


async def test_link_endpoint_requires_channel(client):
    h = await _register(client, "wa-off@example.com")
    r = await client.post("/api/whatsapp/link", headers=h)
    assert r.status_code == 409  # channel not configured


@patch("futureself.web.whatsapp.send_whatsapp", new_callable=AsyncMock)
async def test_link_status_unlink_flow(mock_send, client, twilio_env):
    h = await _register(client, "wa-link@example.com")
    r = await client.post("/api/whatsapp/link", headers=h)
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6

    status = (await client.get("/api/whatsapp/status", headers=h)).json()
    assert status == {"enabled": True, "phone": None}

    # Simulate the user texting LINK <code> from their phone (signed webhook).
    # The webhook ACKs with empty TwiML; the confirmation arrives via REST send.
    form = {"From": "whatsapp:+6591112222", "Body": f"link {code}"}
    r = await _post_webhook(client, form, _sign(WEBHOOK, form))
    assert r.status_code == 200
    assert "<Response></Response>" in r.text
    to_phone, body = mock_send.await_args.args
    assert to_phone == "+6591112222" and "You're linked" in body

    status = (await client.get("/api/whatsapp/status", headers=h)).json()
    assert status["phone"] == "+6591112222"

    assert (await client.post("/api/whatsapp/unlink", headers=h)).status_code == 200
    status = (await client.get("/api/whatsapp/status", headers=h)).json()
    assert status["phone"] is None


# ---------------------------------------------------------------------------
# webhook auth + turn flow
# ---------------------------------------------------------------------------


async def test_webhook_404_when_disabled(client):
    r = await _post_webhook(client, {"From": "whatsapp:+65123", "Body": "hi"})
    assert r.status_code == 404


async def test_webhook_rejects_bad_signature(client, twilio_env):
    form = {"From": "whatsapp:+65123", "Body": "hi"}
    r = await _post_webhook(client, form, "forged")
    assert r.status_code == 403


@patch("futureself.web.whatsapp.send_whatsapp", new_callable=AsyncMock)
async def test_webhook_unlinked_phone_gets_instructions(mock_send, client, twilio_env):
    form = {"From": "whatsapp:+6599990000", "Body": "hello there"}
    r = await _post_webhook(client, form, _sign(WEBHOOK, form))
    assert r.status_code == 200
    assert "<Response></Response>" in r.text  # ACK-first; reply goes via REST
    assert "isn't linked" in mock_send.await_args.args[1]


@patch("futureself.web.whatsapp.send_whatsapp", new_callable=AsyncMock)
async def test_webhook_bad_link_code_message(mock_send, client, twilio_env):
    form = {"From": "whatsapp:+6599990000", "Body": "LINK ZZZZZZ"}
    await _post_webhook(client, form, _sign(WEBHOOK, form))
    assert "didn't match" in mock_send.await_args.args[1]


@patch("futureself.web.whatsapp.send_whatsapp", new_callable=AsyncMock)
@patch("futureself.web.routes.whatsapp.synthesize", new_callable=AsyncMock)
async def test_webhook_linked_phone_runs_turn(
    mock_syn, mock_send, client, db, twilio_env
):
    from sqlalchemy import select  # noqa: PLC0415

    from futureself.db.models import Message  # noqa: PLC0415

    mock_syn.return_value = "Hello from your future self."

    # Link a phone to a registered user (confirmation send: 1st REST call).
    h = await _register(client, "wa-turn@example.com")
    code = (await client.post("/api/whatsapp/link", headers=h)).json()["code"]
    link = {"From": "whatsapp:+6597770000", "Body": f"LINK {code}"}
    await _post_webhook(client, link, _sign(WEBHOOK, link))
    mock_send.reset_mock()

    # Now a chat message → empty TwiML immediately, reply sent async via REST.
    form = {"From": "whatsapp:+6597770000", "Body": "How do I sleep better?"}
    r = await _post_webhook(client, form, _sign(WEBHOOK, form))
    assert r.status_code == 200
    assert "<Response></Response>" in r.text

    # Background task ran: turn persisted to the shared transcript + reply sent.
    mock_syn.assert_awaited_once()
    mock_send.assert_awaited_once()
    to_phone, body = mock_send.await_args.args
    assert to_phone == "+6597770000"
    assert body == "Hello from your future self."
    rows = (await db.scalars(select(Message).order_by(Message.id))).all()
    assert [(m.role, m.content) for m in rows] == [
        ("user", "How do I sleep better?"),
        ("assistant", "Hello from your future self."),
    ]

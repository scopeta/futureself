"""Tests for the FutureSelf JSON REST API routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from futureself.schemas import OrchestratorResult, UserBlueprint
from futureself.web.app import create_app


@pytest.fixture
def app():
    """Fresh FastAPI app per test."""
    return create_app()


@pytest.fixture
def client(app):
    """httpx AsyncClient wired to the app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _seed_session(app, blueprint: UserBlueprint | None = None) -> str:
    """Insert a session directly into app state and return the token."""
    import uuid

    token = str(uuid.uuid4())
    app.state.sessions[token] = blueprint or UserBlueprint()
    app.state.conversations[token] = []
    return token


def _mock_result(reply: str = "Hello from the future.", blueprint: UserBlueprint | None = None) -> OrchestratorResult:
    """Build a minimal OrchestratorResult for testing."""
    return OrchestratorResult(
        user_facing_reply=reply,
        updated_blueprint=blueprint or UserBlueprint(inferred_facts=["User greeted"]),
    )


# ---------------------------------------------------------------------------
# POST /api/session/create
# ---------------------------------------------------------------------------


async def test_session_create_returns_token(client):
    resp = await client.post("/api/session/create")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_token" in data
    assert len(data["session_token"]) == 36  # UUID format


async def test_session_create_stores_blank_blueprint(app, client):
    resp = await client.post("/api/session/create")
    token = resp.json()["session_token"]
    assert token in app.state.sessions
    assert isinstance(app.state.sessions[token], UserBlueprint)


async def test_session_create_each_call_returns_unique_token(client):
    r1 = await client.post("/api/session/create")
    r2 = await client.post("/api/session/create")
    assert r1.json()["session_token"] != r2.json()["session_token"]


# ---------------------------------------------------------------------------
# POST /api/chat/send
# ---------------------------------------------------------------------------


async def test_chat_send_without_auth_returns_401(client):
    resp = await client.post("/api/chat/send", json={"message": "hello"})
    assert resp.status_code == 401


async def test_chat_send_with_invalid_token_returns_401(client):
    resp = await client.post(
        "/api/chat/send",
        json={"message": "hello"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


@patch("futureself.web.routes.api.run_turn", new_callable=AsyncMock)
async def test_chat_send_returns_reply(mock_run_turn, app, client):
    mock_run_turn.return_value = _mock_result("I remember when we faced this too.")
    token = _seed_session(app)

    resp = await client.post(
        "/api/chat/send",
        json={"message": "I feel stuck"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "I remember when we faced this too."
    mock_run_turn.assert_called_once()


@patch("futureself.web.routes.api.run_turn", new_callable=AsyncMock)
async def test_chat_send_updates_session_blueprint(mock_run_turn, app, client):
    updated_bp = UserBlueprint(inferred_facts=["User feels stuck"])
    mock_run_turn.return_value = _mock_result(blueprint=updated_bp)
    token = _seed_session(app)

    await client.post(
        "/api/chat/send",
        json={"message": "I feel stuck"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app.state.sessions[token].inferred_facts == ["User feels stuck"]


@patch("futureself.web.routes.api.run_turn", new_callable=AsyncMock)
async def test_chat_send_does_not_expose_internal_data(mock_run_turn, app, client):
    mock_run_turn.return_value = _mock_result("Wise words from the future.")
    token = _seed_session(app)

    resp = await client.post(
        "/api/chat/send",
        json={"message": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert set(data.keys()) == {"reply"}


# ---------------------------------------------------------------------------
# GET /api/blueprint
# ---------------------------------------------------------------------------


async def test_blueprint_without_auth_returns_401(client):
    resp = await client.get("/api/blueprint")
    assert resp.status_code == 401


async def test_blueprint_returns_json(app, client):
    bp = UserBlueprint(inferred_facts=["User is 34"])
    token = _seed_session(app, blueprint=bp)

    resp = await client.get(
        "/api/blueprint",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inferred_facts"] == ["User is 34"]

"""Tests for the FutureSelf web routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from futureself.schemas import (
    AgentResponse,
    BioData,
    ContextData,
    OrchestratorResult,
    PsychData,
    UserBlueprint,
)
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
    bp = blueprint or UserBlueprint()
    app.state.sessions[token] = bp
    app.state.conversations[token] = []
    return token


def _mock_result(reply: str = "Hello from the future.", blueprint: UserBlueprint | None = None) -> OrchestratorResult:
    """Build a minimal OrchestratorResult for testing."""
    return OrchestratorResult(
        agents_consulted=["mental_health"],
        initial_responses={
            "mental_health": AgentResponse(
                confidence=0.8, domain="mental_health", advice="internal memo", urgency="low"
            )
        },
        refined_responses={},
        conflict_detected=False,
        conflict_summary="",
        user_facing_reply=reply,
        updated_blueprint=blueprint or UserBlueprint(inferred_facts=["User greeted"]),
    )


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


async def test_root_returns_onboarding_form(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "age" in resp.text


async def test_root_redirects_to_chat_if_session_exists(app, client):
    token = _seed_session(app)
    resp = await client.get("/", cookies={"fs_session": token}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/chat"


async def test_step1_returns_step2_form(client):
    resp = await client.post(
        "/onboard/step1",
        data={"age": "34", "sex": "male"},
    )
    assert resp.status_code == 200
    assert "goals" in resp.text
    assert 'value="34"' in resp.text  # step1 data carried as hidden field


async def test_onboard_complete_creates_session_and_redirects(client):
    resp = await client.post(
        "/onboard/complete",
        data={
            "age": "34",
            "sex": "male",
            "height_cm": "178",
            "weight_kg": "75",
            "goals": "run a marathon, sleep better",
            "stress_level": "medium",
            "location_city": "London",
            "location_country": "UK",
            "occupation": "engineer",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/chat"
    assert "fs_session" in resp.cookies


async def test_onboard_complete_builds_correct_blueprint(app, client):
    resp = await client.post(
        "/onboard/complete",
        data={
            "age": "28",
            "sex": "female",
            "goals": "meditate daily, reduce debt",
            "stress_level": "high",
            "location_city": "Berlin",
            "location_country": "Germany",
            "occupation": "designer",
        },
        follow_redirects=False,
    )
    token = resp.cookies["fs_session"]
    bp = app.state.sessions[token]
    assert bp.bio.age == 28
    assert bp.bio.sex == "female"
    assert bp.psych.goals == ["meditate daily", "reduce debt"]
    assert bp.psych.stress_level == "high"
    assert bp.context.location_city == "Berlin"
    assert bp.context.occupation == "designer"


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


async def test_chat_without_session_redirects(client):
    resp = await client.get("/chat", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_chat_with_session_returns_page(app, client):
    token = _seed_session(app)
    resp = await client.get("/chat", cookies={"fs_session": token})
    assert resp.status_code == 200
    assert "chat-history" in resp.text


@patch("futureself.web.routes.chat.run_turn", new_callable=AsyncMock)
async def test_chat_send_returns_reply(mock_run_turn, app, client):
    mock_run_turn.return_value = _mock_result("I remember when we felt that way.")
    token = _seed_session(app)

    resp = await client.post(
        "/chat/send",
        data={"message": "I feel stuck"},
        cookies={"fs_session": token},
    )
    assert resp.status_code == 200
    assert "I remember when we felt that way." in resp.text
    assert "I feel stuck" in resp.text  # user message echoed in fragment
    mock_run_turn.assert_called_once()


@patch("futureself.web.routes.chat.run_turn", new_callable=AsyncMock)
async def test_chat_send_updates_blueprint(mock_run_turn, app, client):
    updated_bp = UserBlueprint(inferred_facts=["User feels stuck"])
    mock_run_turn.return_value = _mock_result(blueprint=updated_bp)
    token = _seed_session(app)

    await client.post(
        "/chat/send",
        data={"message": "I feel stuck"},
        cookies={"fs_session": token},
    )
    assert app.state.sessions[token].inferred_facts == ["User feels stuck"]


@patch("futureself.web.routes.chat.run_turn", new_callable=AsyncMock)
async def test_chat_send_appends_to_conversation_history(mock_run_turn, app, client):
    mock_run_turn.return_value = _mock_result("Future reply")
    token = _seed_session(app)

    await client.post(
        "/chat/send",
        data={"message": "Hello"},
        cookies={"fs_session": token},
    )
    history = app.state.conversations[token]
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Future reply"}


async def test_chat_send_without_session_redirects(client):
    resp = await client.post(
        "/chat/send",
        data={"message": "hi"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


@patch("futureself.web.routes.chat.run_turn", new_callable=AsyncMock)
async def test_chat_send_does_not_expose_internal_data(mock_run_turn, app, client):
    """The response must contain only the user-facing reply, not agent internals."""
    mock_run_turn.return_value = _mock_result("Wise future words")
    token = _seed_session(app)

    resp = await client.post(
        "/chat/send",
        data={"message": "test"},
        cookies={"fs_session": token},
    )
    assert "internal memo" not in resp.text
    assert "mental_health" not in resp.text
    assert "confidence" not in resp.text

"""Tests for the FutureSelf JSON REST API routes.

These tests exercise the real persistence layer against an in-memory SQLite
database (see ``conftest.py``). The MAF agent is the only component mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from futureself.schemas import OrchestratorResult, UserBlueprint


def _mock_result(
    reply: str = "Hello from the future.",
    blueprint: UserBlueprint | None = None,
) -> OrchestratorResult:
    return OrchestratorResult(
        user_facing_reply=reply,
        updated_blueprint=blueprint or UserBlueprint(inferred_facts=["User greeted"]),
    )


async def _create_session(client: AsyncClient) -> str:
    resp = await client.post("/api/session/create")
    assert resp.status_code == 200
    return resp.json()["session_token"]


# ---------------------------------------------------------------------------
# POST /api/session/create
# ---------------------------------------------------------------------------


async def test_session_create_returns_token(client):
    resp = await client.post("/api/session/create")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_token" in data
    assert len(data["session_token"]) >= 30  # secrets.token_urlsafe(24) → 32 chars


async def test_session_create_persists_blank_blueprint(client):
    token = await _create_session(client)
    resp = await client.get(
        "/api/blueprint", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bio"]["age"] is None
    assert data["psych"]["goals"] == []
    assert data["inferred_facts"] == []


async def test_session_create_each_call_returns_unique_token(client):
    t1 = await _create_session(client)
    t2 = await _create_session(client)
    assert t1 != t2


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
async def test_chat_send_returns_reply(mock_run_turn, client):
    mock_run_turn.return_value = _mock_result("I remember when we faced this too.")
    token = await _create_session(client)

    resp = await client.post(
        "/api/chat/send",
        json={"message": "I feel stuck"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "I remember when we faced this too."
    mock_run_turn.assert_called_once()


@patch("futureself.web.routes.api.run_turn", new_callable=AsyncMock)
async def test_chat_send_persists_updated_blueprint(mock_run_turn, client):
    updated_bp = UserBlueprint(inferred_facts=["User feels stuck"])
    mock_run_turn.return_value = _mock_result(blueprint=updated_bp)
    token = await _create_session(client)

    await client.post(
        "/api/chat/send",
        json={"message": "I feel stuck"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Re-read the blueprint via the API to confirm persistence.
    resp = await client.get(
        "/api/blueprint", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.json()["inferred_facts"] == ["User feels stuck"]


@patch("futureself.web.routes.api.run_turn", new_callable=AsyncMock)
async def test_chat_send_does_not_expose_internal_data(mock_run_turn, client):
    mock_run_turn.return_value = _mock_result("Wise words from the future.")
    token = await _create_session(client)

    resp = await client.post(
        "/api/chat/send",
        json={"message": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set(resp.json().keys()) == {"reply"}


# ---------------------------------------------------------------------------
# GET /api/blueprint
# ---------------------------------------------------------------------------


async def test_blueprint_without_auth_returns_401(client):
    resp = await client.get("/api/blueprint")
    assert resp.status_code == 401


async def test_blueprint_returns_json(client):
    token = await _create_session(client)
    resp = await client.get(
        "/api/blueprint", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert "bio" in resp.json()


# ---------------------------------------------------------------------------
# PATCH /api/blueprint/{bio,context,psych}
# ---------------------------------------------------------------------------


async def test_patch_bio(client):
    token = await _create_session(client)
    resp = await client.patch(
        "/api/blueprint/bio",
        json={"age": 42, "sex": "F", "height_cm": 170, "weight_kg": 65},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["bio"]["age"] == 42
    assert resp.json()["bio"]["sex"] == "F"


async def test_patch_context_persists(client):
    token = await _create_session(client)
    await client.patch(
        "/api/blueprint/context",
        json={"location_city": "Singapore", "location_country": "SG"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/blueprint", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.json()["context"]["location_country"] == "SG"


async def test_patch_psych_goals(client):
    token = await _create_session(client)
    resp = await client.patch(
        "/api/blueprint/psych",
        json={"goals": ["run a marathon"], "stress_level": "medium"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["psych"]["goals"] == ["run a marathon"]


# ---------------------------------------------------------------------------
# Biomarkers + supplements
# ---------------------------------------------------------------------------


async def test_add_biomarker_appends(client):
    token = await _create_session(client)
    resp = await client.post(
        "/api/blueprint/biomarkers",
        json={"marker": "LDL", "value": 120, "unit": "mg/dL", "date": "2026-04-01", "source": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    history = resp.json()["bio"]["biomarker_history"]
    assert len(history) == 1
    assert history[0]["marker"] == "LDL"


async def test_add_supplement_replaces_by_name(client):
    token = await _create_session(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/blueprint/supplements",
        json={"name": "Creatine", "dose": "3g", "started": None, "stopped": None, "reason": None},
        headers=headers,
    )
    resp = await client.post(
        "/api/blueprint/supplements",
        json={"name": "Creatine", "dose": "5g", "started": None, "stopped": None, "reason": None},
        headers=headers,
    )

    supplements = resp.json()["bio"]["supplements"]
    assert len(supplements) == 1
    assert supplements[0]["dose"] == "5g"


async def test_remove_supplement(client):
    token = await _create_session(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/blueprint/supplements",
        json={"name": "Creatine", "dose": "5g", "started": None, "stopped": None, "reason": None},
        headers=headers,
    )
    resp = await client.delete("/api/blueprint/supplements/Creatine", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["bio"]["supplements"] == []


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


async def test_quality_report_returns_score_and_flags(client):
    token = await _create_session(client)
    resp = await client.get(
        "/api/blueprint/quality", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "flags" in data
    assert "recommendations" in data
    # Blank blueprint has missing bio + context + goals → score < 100.
    assert data["score"] < 100

"""Tests for the memory lifecycle: clear-history + fact distillation/confirm."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from futureself.schemas import ConversationTurn, UserBlueprint
from futureself.web.facts import FactCandidates, extract_candidates


async def _register(client, email: str) -> dict:
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


# ---------------------------------------------------------------------------
# facts.extract_candidates (unit, injected client)
# ---------------------------------------------------------------------------


def _fake_anthropic(facts: list[str]):
    block = SimpleNamespace(type="tool_use", input={"facts": facts})
    response = SimpleNamespace(content=[block])
    return SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: response)
    )


def test_extract_candidates_returns_new_facts():
    bp = UserBlueprint(inferred_facts=["User is 40 years old"])
    turns = [ConversationTurn(role="user", content="I live in Singapore")]
    result = extract_candidates(
        bp, turns, _client=_fake_anthropic(["User lives in Singapore", "User is 40 years old"])
    )
    assert result.error is None
    # Already-known fact filtered out; new one kept.
    assert result.facts == ["User lives in Singapore"]


def test_extract_candidates_empty_transcript_short_circuits():
    result = extract_candidates(UserBlueprint(), [], _client=None)
    assert result.facts == [] and result.error is None


def test_extract_candidates_degrades_on_error():
    class Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):  # noqa: ANN003
                raise RuntimeError("api down")

    result = extract_candidates(
        UserBlueprint(), [ConversationTurn(role="user", content="hi")], _client=Boom()
    )
    assert result.facts == []
    assert "api down" in (result.error or "")


# ---------------------------------------------------------------------------
# DELETE /api/messages — clear history, keep blueprint
# ---------------------------------------------------------------------------


@patch("futureself.web.routes.api.synthesize")
async def test_clear_messages_keeps_blueprint(mock_syn, client, db):
    from sqlalchemy import func, select  # noqa: PLC0415

    from futureself.db.models import Message  # noqa: PLC0415

    async def fake(*args, **kwargs):  # noqa: ANN002, ANN003
        return "a reply"

    mock_syn.side_effect = fake
    h = await _register(client, "clear@example.com")
    await client.patch("/api/blueprint/bio", json={"age": 33}, headers=h)
    await client.post("/api/onboarding/complete", headers=h)
    await client.post("/api/chat/send", json={"message": "hello"}, headers=h)
    assert (await db.scalar(select(func.count()).select_from(Message))) == 2

    assert (await client.delete("/api/messages", headers=h)).status_code == 200
    assert (await db.scalar(select(func.count()).select_from(Message))) == 0

    # Blueprint + onboarding untouched → no re-onboarding.
    bp = (await client.get("/api/blueprint", headers=h)).json()
    assert bp["bio"]["age"] == 33
    assert bp["onboarded"] is True


# ---------------------------------------------------------------------------
# POST /api/facts/candidates + /api/facts/confirm
# ---------------------------------------------------------------------------


@patch("futureself.web.facts.extract_candidates")
async def test_facts_candidates_endpoint(mock_extract, client):
    mock_extract.return_value = FactCandidates(facts=["User lives in Singapore"])
    h = await _register(client, "cand@example.com")
    r = await client.post("/api/facts/candidates", headers=h)
    assert r.status_code == 200
    assert r.json() == {"candidates": ["User lives in Singapore"], "degraded": False}


async def test_facts_confirm_saves_chosen_and_dedupes(client):
    h = await _register(client, "confirm@example.com")
    r = await client.post(
        "/api/facts/confirm",
        json={"facts": ["User runs marathons", "User runs marathons", ""]},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["inferred_facts"] == ["User runs marathons"]

    # Confirming again does not duplicate.
    r = await client.post(
        "/api/facts/confirm", json={"facts": ["User runs marathons"]}, headers=h
    )
    assert r.json()["inferred_facts"] == ["User runs marathons"]


@patch("futureself.web.routes.api.synthesize")
async def test_facts_confirm_with_cleanup_prunes_history(mock_syn, client, db):
    from sqlalchemy import func, select  # noqa: PLC0415

    from futureself.db.models import Message  # noqa: PLC0415

    async def fake(*args, **kwargs):  # noqa: ANN002, ANN003
        return "a reply"

    mock_syn.side_effect = fake
    h = await _register(client, "prune@example.com")
    await client.post("/api/chat/send", json={"message": "I run marathons"}, headers=h)

    r = await client.post(
        "/api/facts/confirm",
        json={"facts": ["User runs marathons"], "clear_history": True},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["inferred_facts"] == ["User runs marathons"]
    assert (await db.scalar(select(func.count()).select_from(Message))) == 0

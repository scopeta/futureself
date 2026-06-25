"""Tests for the hosted-agent client (BFF-side turn assembly + synthesis).

The hosted agent itself (network + Azure auth) is mocked; these cover the pure
context/fact/turn helpers and that ``synthesize`` calls the stateless Responses
endpoint correctly.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from futureself.schemas import ConversationTurn, UserBlueprint
from futureself.web import agent_client


# ---------------------------------------------------------------------------
# build_user_context
# ---------------------------------------------------------------------------


def test_build_user_context_includes_message():
    ctx = agent_client.build_user_context(UserBlueprint(), "Tell me about sleep.")
    assert "Tell me about sleep." in ctx
    assert "USER MESSAGE" in ctx


def test_build_user_context_includes_facts():
    bp = UserBlueprint(inferred_facts=["User is 40", "User lives in London"])
    ctx = agent_client.build_user_context(bp, "test")
    assert "User is 40" in ctx
    assert "User lives in London" in ctx


def test_build_user_context_includes_history():
    bp = UserBlueprint(
        conversation_history=[ConversationTurn(role="user", content="earlier message")]
    )
    ctx = agent_client.build_user_context(bp, "now")
    assert "earlier message" in ctx
    assert "CONVERSATION HISTORY" in ctx


# ---------------------------------------------------------------------------
# extract_facts
# ---------------------------------------------------------------------------


def test_extract_facts_age():
    facts = agent_client.extract_facts(
        "I'm 35 years old and curious about longevity.", UserBlueprint()
    )
    assert any("35" in f for f in facts)


def test_extract_facts_no_duplicates():
    bp = UserBlueprint(inferred_facts=["User is 35 years old"])
    facts = agent_client.extract_facts("I'm 35 years old.", bp)
    assert not any("35" in f for f in facts)


def test_extract_facts_empty_reply():
    assert agent_client.extract_facts("", UserBlueprint()) == []


# ---------------------------------------------------------------------------
# apply_turn
# ---------------------------------------------------------------------------


def test_apply_turn_appends_history_and_facts():
    bp = UserBlueprint()
    updated = agent_client.apply_turn(bp, "I feel stuck", "I'm 42 years old now.")
    roles = [t.role for t in updated.conversation_history]
    assert roles == ["user", "assistant"]
    assert any("42" in f for f in updated.inferred_facts)


def test_apply_turn_preserves_immutability():
    bp = UserBlueprint()
    snapshot = bp.model_dump()
    agent_client.apply_turn(bp, "hi", "reply")
    assert bp.model_dump() == snapshot


# ---------------------------------------------------------------------------
# synthesize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_returns_output_text(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text="hello from the future"))
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(agent_client, "_client", lambda: fake_client)

    out = await agent_client.synthesize(UserBlueprint(), "hi")

    assert out == "hello from the future"
    create.assert_awaited_once()
    # Stateless endpoint: must not store server-side; input carries full context.
    assert create.await_args.kwargs["store"] is False
    assert "USER MESSAGE" in create.await_args.kwargs["input"]


@pytest.mark.asyncio
async def test_synthesize_handles_empty_output(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text=None))
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(agent_client, "_client", lambda: fake_client)

    assert await agent_client.synthesize(UserBlueprint(), "hi") == ""

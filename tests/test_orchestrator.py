"""Tests for the orchestrator pipeline (MAF agent mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from futureself.orchestrator import run_turn, _extract_facts_simple, _build_user_context
from futureself.schemas import OrchestratorResult, UserBlueprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_agent(reply: str) -> MagicMock:
    """Return a mock MAF agent that returns a fixed reply from agent.run()."""
    result = MagicMock()
    result.text = reply  # AgentResponse.text, not .value

    agent = MagicMock()
    agent.create_session = MagicMock(return_value=MagicMock())  # sync
    agent.run = AsyncMock(return_value=result)
    return agent


# ---------------------------------------------------------------------------
# 1. run_turn returns OrchestratorResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_returns_result(blank_blueprint):
    agent = _mock_agent("I remember when we struggled with this too...")
    result = await run_turn(blank_blueprint, "How do I sleep better?", _agent=agent, _model="test-model")

    assert isinstance(result, OrchestratorResult)
    assert result.user_facing_reply == "I remember when we struggled with this too..."
    assert result.updated_blueprint is not None
    assert len(result.llm_traces) == 1


@pytest.mark.asyncio
async def test_run_turn_non_empty_reply(blank_blueprint):
    agent = _mock_agent("Back when we were your age, we faced the same challenge...")
    result = await run_turn(blank_blueprint, "test message", _agent=agent, _model="test-model")

    assert result.user_facing_reply != ""


@pytest.mark.asyncio
async def test_run_turn_empty_model_reply(blank_blueprint):
    """Graceful handling when the model returns an empty string."""
    agent = _mock_agent("")
    result = await run_turn(blank_blueprint, "test", _agent=agent, _model="test-model")

    assert result.user_facing_reply == ""
    assert isinstance(result, OrchestratorResult)


# ---------------------------------------------------------------------------
# 2. Blueprint is preserved and updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_preserves_blueprint_immutability(sample_blueprint):
    snapshot = sample_blueprint.model_dump()
    agent = _mock_agent("Reply.")
    await run_turn(sample_blueprint, "test", _agent=agent, _model="test-model")

    assert sample_blueprint.model_dump() == snapshot, "Original blueprint was mutated"


@pytest.mark.asyncio
async def test_run_turn_updated_blueprint_has_conversation(blank_blueprint):
    agent = _mock_agent("Future self reply here.")
    result = await run_turn(blank_blueprint, "What should I eat?", _agent=agent, _model="test-model")

    # Conversation history should be appended
    history = result.updated_blueprint.conversation_history
    assert any(t.role == "user" for t in history)
    assert any(t.role == "assistant" for t in history)


# ---------------------------------------------------------------------------
# 3. Trace is recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_trace_recorded(blank_blueprint):
    agent = _mock_agent("A reply.")
    result = await run_turn(blank_blueprint, "test", _agent=agent, _model="test-model")

    assert len(result.llm_traces) == 1
    trace = result.llm_traces[0]
    assert trace.task == "orchestrator.run_turn"
    assert trace.model_requested == "test-model"
    assert trace.latency_ms >= 0


# ---------------------------------------------------------------------------
# 4. extract_facts_simple
# ---------------------------------------------------------------------------


def test_extract_facts_simple_age():
    bp = UserBlueprint()
    facts = _extract_facts_simple("I'm 35 years old and curious about longevity.", bp)
    assert any("35" in f for f in facts)


def test_extract_facts_simple_no_duplicates():
    bp = UserBlueprint(inferred_facts=["User is 35 years old"])
    facts = _extract_facts_simple("I'm 35 years old.", bp)
    # Should not duplicate
    assert not any("35" in f for f in facts)


def test_extract_facts_simple_empty_reply():
    bp = UserBlueprint()
    facts = _extract_facts_simple("", bp)
    assert facts == []


# ---------------------------------------------------------------------------
# 5. User context builder
# ---------------------------------------------------------------------------


def test_build_user_context_includes_message():
    bp = UserBlueprint()
    ctx = _build_user_context(bp, "Tell me about sleep.")
    assert "Tell me about sleep." in ctx
    assert "USER MESSAGE" in ctx


def test_build_user_context_includes_facts():
    bp = UserBlueprint(inferred_facts=["User is 40", "User lives in London"])
    ctx = _build_user_context(bp, "test")
    assert "User is 40" in ctx
    assert "User lives in London" in ctx

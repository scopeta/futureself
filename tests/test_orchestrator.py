"""Tests for the orchestrator pipeline (all LLM calls mocked)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from futureself.agents import AGENT_REGISTRY, MAX_CRITIQUE_ROUNDS
from futureself.llm.provider import LLMProvider
from futureself.llm.router import ModelRouter
from futureself.orchestrator import (
    _detect_conflicts,
    _extract_facts,
    _fan_out,
    _select_agents,
    run_turn,
)
from futureself.schemas import AgentResponse, OrchestratorResult, UserBlueprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _selection_json(agents: list[str]) -> str:
    return json.dumps({"selected_agents": agents})


def _conflict_json(detected: bool, summary: str = "", agents: list[str] | None = None) -> str:
    return json.dumps({
        "conflict_detected": detected,
        "conflict_summary": summary,
        "implicated_agents": agents or [],
    })


def _facts_json(facts: list[str] | None = None) -> str:
    return json.dumps({"new_facts": facts or []})


def _agent_json(domain: str, advice: str = "Test advice.", **extra) -> str:
    payload = {
        "confidence": 0.8,
        "domain": domain,
        "advice": advice,
        "urgency": "low",
    }
    payload.update(extra)
    return json.dumps(payload)


def _build_provider(*responses: str) -> AsyncMock:
    """Return a mock provider that returns responses in order."""
    provider = AsyncMock(spec=LLMProvider)
    provider.complete.side_effect = list(responses)
    return provider


# ---------------------------------------------------------------------------
# 1. Agent selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_agents_returns_valid_keys(blank_blueprint):
    provider = _build_provider(_selection_json(["physical_health", "time_management"]))
    result = await _select_agents(blank_blueprint, "I want to start running.", provider)
    assert result == ["physical_health", "time_management"]


@pytest.mark.asyncio
async def test_select_agents_filters_unknown_keys(blank_blueprint):
    provider = _build_provider(_selection_json(["physical_health", "astrology"]))
    result = await _select_agents(blank_blueprint, "test", provider)
    assert result == ["physical_health"]


@pytest.mark.asyncio
async def test_select_agents_invalid_json_falls_back_to_empty(blank_blueprint):
    provider = _build_provider("not-json")
    result = await _select_agents(blank_blueprint, "test", provider)
    assert result == []


# ---------------------------------------------------------------------------
# 2. Fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_out_calls_selected_agents(blank_blueprint):
    provider = _build_provider(
        _agent_json("physical_health"),
        _agent_json("financial"),
    )
    router = ModelRouter.from_single_provider(provider)
    result = await _fan_out(["physical_health", "financial"], blank_blueprint, "test", router)
    assert set(result.keys()) == {"physical_health", "financial"}
    assert result["physical_health"].domain == "physical_health"
    assert result["financial"].domain == "financial"


# ---------------------------------------------------------------------------
# 3. Conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_detection_returns_tuple():
    responses = {
        "physical_health": AgentResponse(
            confidence=0.8, domain="physical_health",
            advice="Get a gym membership.",
            urgency="medium",
        ),
        "financial": AgentResponse(
            confidence=0.9, domain="financial",
            advice="Cut discretionary spending.",
            urgency="high",
        ),
    }
    provider = _build_provider(
        _conflict_json(True, "gym cost vs budget", ["physical_health", "financial"])
    )
    detected, summary, agents = await _detect_conflicts(responses, provider)
    assert detected is True
    assert "gym" in summary.lower() or "budget" in summary.lower()
    assert "physical_health" in agents


@pytest.mark.asyncio
async def test_conflict_detection_invalid_json_falls_back_to_no_conflict():
    responses = {
        "physical_health": AgentResponse(
            confidence=0.8,
            domain="physical_health",
            advice="Test",
            urgency="low",
        ),
    }
    provider = _build_provider("not-json")
    detected, summary, agents = await _detect_conflicts(responses, provider)
    assert detected is False
    assert summary == ""
    assert agents == []


# ---------------------------------------------------------------------------
# 4. Conflict triggers critique
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_triggers_critique(blank_blueprint):
    # Call sequence:
    # 1. _select_agents → [physical_health, financial]
    # 2. _fan_out → 2 agent calls
    # 3. _detect_conflicts → conflict detected
    # 4. _run_critique_round (round 1) → 2 refined agent calls
    # 5. _run_critique_round (round 2) → 2 refined agent calls
    # 6. _synthesise → final reply
    responses_in_order = [
        # 1. selection
        _selection_json(["physical_health", "financial"]),
        # 2. fan-out (physical_health, financial)
        _agent_json("physical_health", "Get a gym."),
        _agent_json("financial", "Cut spending."),
        # 3. conflict detection
        _conflict_json(True, "gym cost vs budget", ["physical_health", "financial"]),
        # 4. critique round 1
        _agent_json("physical_health", "Use a cheaper gym.", confidence=0.7),
        _agent_json("financial", "Allocate $50 for fitness.", confidence=0.85),
        # 5. critique round 2
        _agent_json("physical_health", "Home workouts are valid.", confidence=0.75),
        _agent_json("financial", "Budget $50 for home equipment.", confidence=0.9),
        # 6. synthesis
        "I remember when we had this same struggle with money and health...",
        # 7. fact extraction
        _facts_json(["User considering gym membership"]),
    ]
    provider = _build_provider(*responses_in_order)

    result = await run_turn(blank_blueprint, "Should I get a gym membership?", provider=provider)

    assert result.conflict_detected is True
    assert len(result.refined_responses) > 0
    assert result.user_facing_reply != ""


# ---------------------------------------------------------------------------
# 5. No conflict skips critique
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conflict_skips_critique(blank_blueprint):
    responses_in_order = [
        # 1. selection
        _selection_json(["physical_health", "time_management"]),
        # 2. fan-out
        _agent_json("physical_health", "Run 3 times a week."),
        _agent_json("time_management", "Schedule runs before breakfast."),
        # 3. conflict detection (no conflict)
        _conflict_json(False),
        # 4. synthesis (no critique rounds)
        "I remember how energising those morning runs were...",
        # 5. fact extraction
        _facts_json(),
    ]
    provider = _build_provider(*responses_in_order)

    result = await run_turn(blank_blueprint, "How do I fit in exercise?", provider=provider)

    assert result.conflict_detected is False
    assert result.refined_responses == {}


# ---------------------------------------------------------------------------
# 6. Critique rounds capped at MAX
# ---------------------------------------------------------------------------


def test_max_critique_rounds_is_two():
    assert MAX_CRITIQUE_ROUNDS == 2


@pytest.mark.asyncio
async def test_critique_rounds_capped(blank_blueprint):
    """Even with persistent conflict, critique runs at most MAX_CRITIQUE_ROUNDS times."""
    responses_in_order = [
        _selection_json(["physical_health", "financial"]),
        _agent_json("physical_health"),
        _agent_json("financial"),
        _conflict_json(True, "cost tension", ["physical_health", "financial"]),
        # Round 1 critique
        _agent_json("physical_health"),
        _agent_json("financial"),
        # Round 2 critique
        _agent_json("physical_health"),
        _agent_json("financial"),
        # Synthesis
        "Here is the reply.",
        # Fact extraction
        _facts_json(),
    ]
    provider = _build_provider(*responses_in_order)

    result = await run_turn(blank_blueprint, "test", provider=provider)

    # Count the total LLM calls: selection(1) + fanout(2) + conflict(1)
    #   + critique_r1(2) + critique_r2(2) + synthesis(1) + facts(1) = 10
    assert provider.complete.call_count == 10


# ---------------------------------------------------------------------------
# 7. Blueprint immutability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blueprint_immutability_through_pipeline(sample_blueprint):
    snapshot = sample_blueprint.model_dump()
    responses_in_order = [
        _selection_json(["physical_health"]),
        _agent_json("physical_health"),
        _conflict_json(False),
        "Reply.",
        _facts_json(),
    ]
    provider = _build_provider(*responses_in_order)

    result = await run_turn(sample_blueprint, "test", provider=provider)

    assert sample_blueprint.model_dump() == snapshot, "Original blueprint was mutated"


# ---------------------------------------------------------------------------
# 8. Fact extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_facts_adds_new_facts():
    bp = UserBlueprint(inferred_facts=["existing fact"])
    responses = {
        "physical_health": AgentResponse(
            confidence=0.8, domain="physical_health",
            advice="test", urgency="low",
        ),
    }
    provider = _build_provider(_facts_json(["new fact 1", "new fact 2"]))
    updated = await _extract_facts(bp, "test", responses, provider)

    assert "existing fact" in updated.inferred_facts
    assert "new fact 1" in updated.inferred_facts
    assert "new fact 2" in updated.inferred_facts
    assert len(updated.inferred_facts) == 3


@pytest.mark.asyncio
async def test_extract_facts_deduplicates():
    bp = UserBlueprint(inferred_facts=["shared fact"])
    responses = {
        "mental_health": AgentResponse(
            confidence=0.7, domain="mental_health",
            advice="test", urgency="low",
        ),
    }
    provider = _build_provider(_facts_json(["shared fact", "new fact"]))
    updated = await _extract_facts(bp, "test", responses, provider)

    assert updated.inferred_facts.count("shared fact") == 1
    assert "new fact" in updated.inferred_facts


@pytest.mark.asyncio
async def test_extract_facts_empty_returns_same_blueprint():
    bp = UserBlueprint(inferred_facts=["existing"])
    responses = {
        "physical_health": AgentResponse(
            confidence=0.8, domain="physical_health",
            advice="test", urgency="low",
        ),
    }
    provider = _build_provider(_facts_json([]))
    updated = await _extract_facts(bp, "test", responses, provider)

    assert updated is bp  # no copy needed when nothing new


@pytest.mark.asyncio
async def test_extract_facts_invalid_json_returns_same_blueprint():
    bp = UserBlueprint(inferred_facts=["existing"])
    responses = {
        "physical_health": AgentResponse(
            confidence=0.8, domain="physical_health", advice="test", urgency="low"
        ),
    }
    provider = _build_provider("not-json")
    updated = await _extract_facts(bp, "test", responses, provider)
    assert updated is bp


# ---------------------------------------------------------------------------
# 9. Agent registry complete
# ---------------------------------------------------------------------------


def test_agent_registry_complete():
    expected = {"physical_health", "mental_health", "financial", "social_relations", "geopolitics", "time_management"}
    assert set(AGENT_REGISTRY.keys()) == expected


# ---------------------------------------------------------------------------
# 10. Updated blueprint merges facts from run_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_merges_facts(blank_blueprint):
    responses_in_order = [
        _selection_json(["physical_health"]),
        _agent_json("physical_health", "Walk daily."),
        _conflict_json(False),
        "I remember when we started walking...",
        _facts_json(["User wants to be healthier"]),
    ]
    provider = _build_provider(*responses_in_order)

    result = await run_turn(blank_blueprint, "I want to be healthier.", provider=provider)

    assert len(result.updated_blueprint.inferred_facts) > 0
    assert any("healthier" in f for f in result.updated_blueprint.inferred_facts)


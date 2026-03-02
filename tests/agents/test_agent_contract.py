"""Shared contract tests — parametrised across all 6 worker agents.

Tests 1-8 verify the base AgentResponse contract and are identical for every
domain.  Only the ``AGENTS`` table below varies (domain key, run function,
default mock payloads, and domain-specific extension fixtures).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from futureself.agents import AGENT_REGISTRY
from futureself.llm.provider import LLMProvider
from futureself.schemas import AgentResponse


# ---------------------------------------------------------------------------
# Agent table — everything that differs per domain lives here
# ---------------------------------------------------------------------------

_AGENTS = [
    pytest.param("physical_health", id="physical_health"),
    pytest.param("mental_health", id="mental_health"),
    pytest.param("financial", id="financial"),
    pytest.param("social_relations", id="social_relations"),
    pytest.param("geopolitics", id="geopolitics"),
    pytest.param("time_management", id="time_management"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_json(domain: str, **overrides) -> str:
    payload = {
        "confidence": 0.80,
        "domain": domain,
        "advice": f"Generic advice from {domain}.",
        "urgency": "low",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _provider(domain: str, **overrides) -> AsyncMock:
    p = AsyncMock(spec=LLMProvider)
    p.complete.return_value = _valid_json(domain, **overrides)
    return p


# ---------------------------------------------------------------------------
# 1. Schema validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_returns_valid_schema(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    response = await run(blank_blueprint, "test", provider=_provider(domain))

    assert isinstance(response, AgentResponse)
    assert isinstance(response.confidence, float)
    assert 0.0 <= response.confidence <= 1.0
    assert isinstance(response.advice, str)
    assert response.urgency in ("low", "medium", "high", "critical")
    assert isinstance(response.is_refined, bool)
    assert isinstance(response.extensions, dict)


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_confidence_is_clamped_to_contract_range(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    response = await run(blank_blueprint, "test", provider=_provider(domain, confidence=2.5))
    assert response.confidence == 1.0


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_invalid_urgency_defaults_to_low(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    response = await run(blank_blueprint, "test", provider=_provider(domain, urgency="urgent"))
    assert response.urgency == "low"



# ---------------------------------------------------------------------------
# 2. Blueprint immutability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_does_not_mutate_blueprint(domain, sample_blueprint):
    snapshot = sample_blueprint.model_dump()
    run = AGENT_REGISTRY[domain]
    await run(sample_blueprint, "test", provider=_provider(domain))
    assert sample_blueprint.model_dump() == snapshot


# ---------------------------------------------------------------------------
# 3. Critique round sets is_refined
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_critique_sets_is_refined(domain, blank_blueprint, make_critique_context):
    run = AGENT_REGISTRY[domain]
    ctx = make_critique_context(concern_area="cost")
    resp = await run(blank_blueprint, "test", critique_context=ctx, provider=_provider(domain))
    assert resp.is_refined is True


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_no_critique_not_refined(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    resp = await run(blank_blueprint, "test", provider=_provider(domain))
    assert resp.is_refined is False


# ---------------------------------------------------------------------------
# 4. Advice is an internal memo (not user-addressed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_advice_not_user_addressed(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    resp = await run(blank_blueprint, "test", provider=_provider(domain))
    lower = resp.advice.lower()
    for phrase in ("you should", "you need", "you must", "i recommend you", "please consider"):
        assert phrase not in lower, f"Advice addresses user: {resp.advice!r}"


# ---------------------------------------------------------------------------
# 6. Domain field matches module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_domain_field_matches(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    resp = await run(blank_blueprint, "test", provider=_provider(domain))
    assert resp.domain == domain


# ---------------------------------------------------------------------------
# 7. Extension fields captured
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_extension_fields_captured(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    resp = await run(
        blank_blueprint, "test",
        provider=_provider(domain, custom_ext="value"),
    )
    assert "custom_ext" in resp.extensions


@pytest.mark.parametrize("domain", _AGENTS)
@pytest.mark.asyncio
async def test_invalid_json_returns_safe_defaults(domain, blank_blueprint):
    run = AGENT_REGISTRY[domain]
    provider = AsyncMock(spec=LLMProvider)
    provider.complete.return_value = "not-json"
    resp = await run(blank_blueprint, "test", provider=provider)

    assert resp.confidence == 0.5
    assert resp.domain == domain
    assert resp.advice == ""
    assert resp.urgency == "low"


# ---------------------------------------------------------------------------
# 8. Domain-specific extension tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_social_relations_isolation_risk(blank_blueprint):
    run = AGENT_REGISTRY["social_relations"]
    resp = await run(blank_blueprint, "test", provider=_provider("social_relations", isolation_risk="high"))
    assert resp.extensions.get("isolation_risk") == "high"


@pytest.mark.asyncio
async def test_time_management_schedule_change(blank_blueprint):
    run = AGENT_REGISTRY["time_management"]
    resp = await run(
        blank_blueprint, "test",
        provider=_provider("time_management", proposed_schedule_change={"time": "9am", "activity": "work"}),
    )
    assert "proposed_schedule_change" in resp.extensions


@pytest.mark.asyncio
async def test_physical_health_contraindications(blank_blueprint):
    run = AGENT_REGISTRY["physical_health"]
    resp = await run(
        blank_blueprint, "test",
        provider=_provider("physical_health", contraindications=["high-impact with knee OA"]),
    )
    assert "contraindications" in resp.extensions

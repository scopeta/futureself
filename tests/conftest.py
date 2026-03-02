"""Shared pytest fixtures for FutureSelf tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from futureself.llm.provider import LLMProvider
from futureself.schemas import (
    BioData,
    ContextData,
    CritiqueContext,
    PsychData,
    UserBlueprint,
)


def build_provider(*responses: str) -> AsyncMock:
    """Standalone helper (not a fixture) — returns a mock provider yielding responses in order."""
    provider = AsyncMock(spec=LLMProvider)
    provider.complete.side_effect = list(responses)
    return provider


def _make_agent_json(
    domain: str = "physical_health",
    advice: str = "Increase Zone 2 cardio to 150 minutes per week.",
    urgency: str = "low",
    confidence: float = 0.80,
    tradeoffs: list | None = None,
    extra: dict | None = None,
) -> str:
    payload = {
        "confidence": confidence,
        "domain": domain,
        "advice": advice,
        "tradeoff_flags": tradeoffs or [],
        "urgency": urgency,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload)


@pytest.fixture
def make_blueprint():
    """Factory for UserBlueprint instances."""

    def _make(**kwargs) -> UserBlueprint:
        return UserBlueprint(**kwargs)

    return _make


@pytest.fixture
def blank_blueprint() -> UserBlueprint:
    """A fully empty UserBlueprint."""
    return UserBlueprint()


@pytest.fixture
def sample_blueprint() -> UserBlueprint:
    """A realistic UserBlueprint for scenario testing."""
    return UserBlueprint(
        bio=BioData(age=34, conditions=[]),
        psych=PsychData(goals=["adventure", "community"], stress_level="medium"),
        context=ContextData(occupation="software engineer", income_usd_annual=95000),
    )


@pytest.fixture
def make_message():
    """Returns a simple test user message."""
    return lambda: "I want to start exercising but I have no time."


@pytest.fixture
def make_critique_context():
    """Factory for CritiqueContext instances."""

    def _make(concern_area: str = "cost", round_number: int = 1) -> CritiqueContext:
        return CritiqueContext(
            conflicting_advice="The other domain recommends an expensive approach.",
            concern_area=concern_area,
            orchestrator_question="Can you achieve the same outcome more affordably?",
            round_number=round_number,
        )

    return _make


@pytest.fixture
def mock_provider():
    """A fake LLMProvider that returns a valid physical_health AgentResponse JSON."""
    provider = AsyncMock(spec=LLMProvider)
    provider.complete.return_value = _make_agent_json()
    return provider


@pytest.fixture
def make_mock_provider():
    """Factory: returns a mock provider that returns custom JSON."""

    def _make(domain: str = "physical_health", **kwargs) -> AsyncMock:
        provider = AsyncMock(spec=LLMProvider)
        provider.complete.return_value = _make_agent_json(domain=domain, **kwargs)
        return provider

    return _make


@pytest.fixture
def make_selection_json():
    def _make(agents: list[str]) -> str:
        return json.dumps({"selected_agents": agents})
    return _make


@pytest.fixture
def make_conflict_json():
    def _make(detected: bool, summary: str = "", agents: list[str] | None = None) -> str:
        return json.dumps({
            "conflict_detected": detected,
            "conflict_summary": summary,
            "implicated_agents": agents or [],
        })
    return _make

"""Integration test: verify that the orchestrator routes each task to the correct provider."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from futureself.llm.provider import LLMProvider
from futureself.llm.router import ModelRouter
from futureself.orchestrator import run_turn
from futureself.schemas import UserBlueprint


def _make_provider(label: str) -> AsyncMock:
    """Return a mock provider whose responses are tagged with *label*."""
    provider = AsyncMock(spec=LLMProvider)
    provider._label = label  # for assertion tracking

    def _complete(system: str, user: str, response_format=None) -> str:
        # Detect what kind of call this is by the system prompt content
        if "routing component" in system:
            return json.dumps({"selected_agents": ["physical_health"]})
        if "conflict detection" in system:
            return json.dumps({
                "conflict_detected": False,
                "conflict_summary": "",
                "implicated_agents": [],
            })
        if "fact-extraction" in system:
            return json.dumps({"new_facts": []})
        if response_format and response_format.get("type") == "json_object":
            # Agent call
            return json.dumps({
                "confidence": 0.8,
                "domain": "physical_health",
                "advice": f"Advice from {label}",
                "urgency": "low",
            })
        # Synthesis
        return f"Synthesis from {label}"

    provider.complete.side_effect = _complete
    return provider


@pytest.mark.asyncio
async def test_per_task_routing():
    """Different pipeline stages use different providers when configured."""
    p_default = _make_provider("default")
    p_synth = _make_provider("synthesis")

    router = ModelRouter(
        providers={"default": p_default, "synth": p_synth},
        tasks={"orchestrator.synthesise": "synth"},
        default_key="default",
    )

    bp = UserBlueprint()
    result = await run_turn(bp, "How should I exercise?", router=router)

    assert result.user_facing_reply == "Synthesis from synthesis"
    # Default provider handled: selection, fan-out, conflict, facts
    assert p_default.complete.call_count >= 3
    # Synthesis provider was called exactly once
    assert p_synth.complete.call_count == 1


@pytest.mark.asyncio
async def test_single_provider_router_backward_compat():
    """A single-provider router behaves like the old provider= parameter."""
    provider = _make_provider("only")
    router = ModelRouter.from_single_provider(provider)

    bp = UserBlueprint()
    result = await run_turn(bp, "Help me sleep better.", router=router)

    assert result.user_facing_reply != ""
    assert provider.complete.call_count >= 4  # selection + agent + conflict + synth + facts

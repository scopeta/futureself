"""Agent registry — maps domain keys to their run() coroutines.

The orchestrator imports AGENT_REGISTRY and MAX_CRITIQUE_ROUNDS from here.
No other module should need to know which agents exist.
"""
from __future__ import annotations

from collections.abc import Callable

from futureself.agents import (
    financial,
    geopolitics,
    mental_health,
    physical_health,
    social_relations,
    time_management,
)

AGENT_REGISTRY: dict[str, Callable] = {
    "physical_health": physical_health.run,
    "mental_health": mental_health.run,
    "financial": financial.run,
    "social_relations": social_relations.run,
    "geopolitics": geopolitics.run,
    "time_management": time_management.run,
}

MAX_CRITIQUE_ROUNDS: int = 2

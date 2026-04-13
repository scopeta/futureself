"""Deterministic evaluation of orchestrator results against scenario expectations.

No LLM calls — compares expected vs actual using scenario YAML declarations.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from futureself.schemas import OrchestratorResult


@dataclasses.dataclass
class TurnEval:
    """Evaluation metrics for a single turn."""

    scenario_name: str
    turn_index: int

    # Response quality signals
    reply_length: int
    reply_non_empty: bool

    # Latency from trace (if available)
    latency_ms: float


@dataclasses.dataclass
class ScenarioEval:
    """Aggregated evaluation for a full scenario."""

    scenario_name: str
    turns: list[TurnEval]
    all_replies_non_empty: bool


def evaluate_turn(
    scenario_name: str,
    turn_index: int,
    turn_spec: dict[str, Any],
    result: OrchestratorResult,
) -> TurnEval:
    """Build a TurnEval from scenario expectations and actual results."""
    latency = result.llm_traces[0].latency_ms if result.llm_traces else 0.0

    return TurnEval(
        scenario_name=scenario_name,
        turn_index=turn_index,
        reply_length=len(result.user_facing_reply),
        reply_non_empty=bool(result.user_facing_reply),
        latency_ms=latency,
    )


def evaluate_scenario(
    scenario_name: str,
    turns_spec: list[dict[str, Any]],
    results: list[OrchestratorResult],
) -> ScenarioEval:
    """Evaluate all turns in a scenario."""
    turn_evals = [
        evaluate_turn(scenario_name, i, spec, result)
        for i, (spec, result) in enumerate(zip(turns_spec, results), start=1)
    ]
    return ScenarioEval(
        scenario_name=scenario_name,
        turns=turn_evals,
        all_replies_non_empty=all(t.reply_non_empty for t in turn_evals),
    )


def format_report(evals: list[ScenarioEval]) -> str:
    """Render evaluations as a human-readable summary."""
    lines: list[str] = []
    for scenario_eval in evals:
        lines.append(f"\n{'=' * 60}")
        lines.append(f"  Evaluation: {scenario_eval.scenario_name}")
        lines.append(f"{'=' * 60}")
        for turn in scenario_eval.turns:
            lines.append(f"\nTurn {turn.turn_index}:")
            icon = "OK" if turn.reply_non_empty else "EMPTY"
            lines.append(f"  Reply:    [{icon}] {turn.reply_length} chars")
            lines.append(f"  Latency:  {turn.latency_ms:.0f}ms")
    return "\n".join(lines)


def to_json(evals: list[ScenarioEval]) -> str:
    """Serialize evaluations to JSON."""
    return json.dumps(
        [dataclasses.asdict(e) for e in evals],
        indent=2,
    )

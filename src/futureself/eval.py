"""Deterministic evaluation of orchestrator results against scenario expectations.

No LLM calls. Two layers:

- Smoke signals — reply length, non-empty, latency (always computed).
- Assertions — a scenario turn's optional ``expect`` block is checked against the
  actual reply (length bounds, required topical keywords, forbidden phrases).

Assertions are objective and repeatable, so they form the *hard* pass/fail gate.
Subjective quality scoring lives in :mod:`futureself.judge` (LLM-as-judge).

``expect`` block schema (all keys optional)::

    expect:
      min_length: 150            # reply must be at least N chars
      max_length: 4000           # reply must be at most N chars
      must_include_all:          # every phrase must appear (case-insensitive)
        - "..."
      must_include_any:          # each group must contribute >=1 match
        - ["rest", "recover", "sleep"]
        - ["debt", "finance", "money"]
      forbidden:                 # none of these may appear (case-insensitive)
        - "load_skill"
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from futureself.schemas import OrchestratorResult

# Narration / persona-break phrases that must never appear in any reply — the agent
# speaks only as the Future Self and must open directly in character, never narrating
# its process or tools. Applied to every scenario via the always-on `no_narration`
# check. Opus 4.8 is prone to these preambles and phrasing varies, so this is a
# best-effort net; the LLM-judge (futureself.judge) is the robust backstop for variants.
_DEFAULT_FORBIDDEN = [
    "load_skill",
    "load the skill",
    "load the relevant skill",
    "i'll load",
    "let me load",
    "i want to load",
    "i'll explore the relevant domain",
    "explore the relevant domain",
    "the skill content",
    "i'll think through this",
    "let me think about this",
    "let me reason",
    "i'll reason through",
    "i'll look into",
    # Structural markers — catch the "<meta preamble> before I answer" pattern
    # regardless of the verb the model chooses.
    "before i answer",
    "before answering",
    "before i respond",
    "before i reply",
    "as an ai",
    "language model",
    "system prompt",
]


@dataclasses.dataclass
class AssertionResult:
    """Outcome of a single deterministic check against a reply."""

    name: str
    passed: bool
    detail: str


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

    # Deterministic assertions from the turn's ``expect`` block
    assertions: list[AssertionResult] = dataclasses.field(default_factory=list)
    passed: bool = True


@dataclasses.dataclass
class ScenarioEval:
    """Aggregated evaluation for a full scenario."""

    scenario_name: str
    turns: list[TurnEval]
    all_replies_non_empty: bool
    all_passed: bool = True


def check_expectations(reply: str, expect: dict[str, Any] | None) -> list[AssertionResult]:
    """Check a reply against a turn's ``expect`` block. Deterministic, no LLM.

    Args:
        reply: The Future Self reply text.
        expect: The turn's optional ``expect`` mapping (see module docstring).

    Returns:
        One :class:`AssertionResult` per check. ``non_empty`` is always present.
    """
    low = reply.lower()
    results: list[AssertionResult] = [
        AssertionResult(
            "non_empty",
            bool(reply.strip()),
            f"{len(reply)} chars",
        )
    ]

    # Always-on persona/narration guard (every scenario, no opt-in needed).
    hit = next((p for p in _DEFAULT_FORBIDDEN if p in low), None)
    results.append(
        AssertionResult("no_narration", hit is None, f"leak phrase {hit!r}" if hit else "clean")
    )

    if not expect:
        return results

    if (min_length := expect.get("min_length")) is not None:
        results.append(
            AssertionResult(
                "min_length",
                len(reply) >= min_length,
                f"{len(reply)} >= {min_length}",
            )
        )

    if (max_length := expect.get("max_length")) is not None:
        results.append(
            AssertionResult(
                "max_length",
                len(reply) <= max_length,
                f"{len(reply)} <= {max_length}",
            )
        )

    for phrase in expect.get("must_include_all", []) or []:
        results.append(
            AssertionResult(
                "must_include_all",
                phrase.lower() in low,
                f"contains {phrase!r}",
            )
        )

    for group in expect.get("must_include_any", []) or []:
        hit = next((w for w in group if w.lower() in low), None)
        results.append(
            AssertionResult(
                "must_include_any",
                hit is not None,
                f"any of {group} -> {hit!r}",
            )
        )

    for phrase in expect.get("forbidden", []) or []:
        results.append(
            AssertionResult(
                "forbidden",
                phrase.lower() not in low,
                f"absent {phrase!r}",
            )
        )

    return results


def evaluate_turn(
    scenario_name: str,
    turn_index: int,
    turn_spec: dict[str, Any],
    result: OrchestratorResult,
) -> TurnEval:
    """Build a TurnEval from scenario expectations and actual results."""
    latency = result.llm_traces[0].latency_ms if result.llm_traces else 0.0
    reply = result.user_facing_reply
    assertions = check_expectations(reply, turn_spec.get("expect"))

    return TurnEval(
        scenario_name=scenario_name,
        turn_index=turn_index,
        reply_length=len(reply),
        reply_non_empty=bool(reply),
        latency_ms=latency,
        assertions=assertions,
        passed=all(a.passed for a in assertions),
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
        all_passed=all(t.passed for t in turn_evals),
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
            for a in turn.assertions:
                mark = "PASS" if a.passed else "FAIL"
                lines.append(f"  [{mark}] {a.name}: {a.detail}")
        verdict = "PASS" if scenario_eval.all_passed else "FAIL"
        lines.append(f"\n  Scenario verdict: {verdict}")
    return "\n".join(lines)


def to_json(evals: list[ScenarioEval]) -> str:
    """Serialize evaluations to JSON."""
    return json.dumps(
        [dataclasses.asdict(e) for e in evals],
        indent=2,
    )

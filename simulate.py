"""CLI simulation harness for FutureSelf scenario testing.

Usage:
    python simulate.py --scenario motorcycle_purchase
    python simulate.py --scenario burnout_and_debt --verbose
    python simulate.py --scenario motorcycle_purchase --eval
    python simulate.py --scenario motorcycle_purchase --eval --judge
    python simulate.py --scenario motorcycle_purchase --traces
    python simulate.py --scenario motorcycle_purchase --eval-json
    python simulate.py --list
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)  # reads .env from the project root; overrides system env vars

from futureself import judge
from futureself.eval import (
    ScenarioEval,
    evaluate_scenario,
    evaluate_turn,
    format_report,
    to_json,
)
from futureself.schemas import (
    LLMCallTrace,
    OrchestratorResult,
    UserBlueprint,
)
from futureself.web.agent_client import apply_turn, synthesize

SCENARIO_DIR = Path(__file__).parent / "scenarios"


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------


def list_scenarios() -> list[str]:
    """Return available scenario names (without .yaml extension)."""
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))


def load_scenario(name: str) -> dict:
    """Load a YAML scenario file by name."""
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.exists():
        print(f"Error: scenario '{name}' not found at {path}")
        print(f"Available scenarios: {', '.join(list_scenarios())}")
        sys.exit(1)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def print_header(text: str) -> None:
    width = max(60, len(text) + 4)
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def print_section(label: str, content: str) -> None:
    print(f"\n--- {label} ---")
    print(content)


def print_trace(trace: LLMCallTrace) -> None:
    """Print a single LLM call trace."""
    tokens = f"{trace.prompt_tokens}->{trace.completion_tokens}"
    print(f"\n  -- LLM Call: {trace.task} --")
    print(f"     Model: {trace.model_actual or trace.model_requested} | Tokens: {tokens} | Latency: {trace.latency_ms:.0f}ms")


def print_result(result: OrchestratorResult, turn_num: int, verbose: bool, show_traces: bool) -> None:
    print_header(f"Turn {turn_num}")

    print_section("Future Self Reply", result.user_facing_reply)

    if result.updated_blueprint.inferred_facts:
        print_section("Inferred Facts", "\n".join(
            f"  - {f}" for f in result.updated_blueprint.inferred_facts
        ))

    if show_traces and result.llm_traces:
        print_section("LLM Traces", "")
        for trace in result.llm_traces:
            print_trace(trace)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_scenario(
    name: str,
    verbose: bool,
    show_eval: bool,
    show_traces: bool,
    eval_json: bool,
    show_judge: bool,
) -> None:
    scenario = load_scenario(name)

    if not eval_json:
        print_header(f"Scenario: {scenario['name']}")
        print(f"Description: {scenario.get('description', 'N/A')}")

    blueprint = UserBlueprint.from_dict(scenario.get("user_blueprint", {}))
    turns_spec = scenario.get("turns", [])
    results: list[OrchestratorResult] = []

    for i, turn in enumerate(turns_spec, start=1):
        user_msg = turn["user_message"].strip()
        if not eval_json:
            print(f"\n>> User: {user_msg}")

        # Drive the deployed hosted agent (spec §11). Traces now live in the
        # agent's App Insights, not returned inline, so llm_traces is empty here.
        reply = await synthesize(blueprint, user_msg)
        new_blueprint = apply_turn(blueprint, user_msg, reply)
        result = OrchestratorResult(
            user_facing_reply=reply,
            updated_blueprint=new_blueprint,
            llm_traces=[],
        )
        results.append(result)

        if not eval_json:
            print_result(result, i, verbose, show_traces)

        # Carry forward updated blueprint
        blueprint = new_blueprint

    # Deterministic evaluation (assertions are computed from each turn's `expect`)
    scenario_eval = evaluate_scenario(scenario["name"], turns_spec, results)

    if eval_json:
        print(to_json([scenario_eval]))
    elif show_eval:
        print(format_report([scenario_eval]))

    # LLM-as-judge (opt-in: costs an extra completion per turn)
    if show_judge and not eval_json:
        print_judge(scenario, turns_spec, results)

    if not eval_json:
        print_header("Scenario Complete")


def print_judge(scenario: dict, turns_spec: list[dict], results: list[OrchestratorResult]) -> None:
    """Run the LLM-as-judge over each turn and print rubric scores."""
    rubric = judge.DEFAULT_RUBRIC + list(scenario.get("rubric", []))
    print_header("LLM-as-Judge")
    for i, (turn, result) in enumerate(zip(turns_spec, results), start=1):
        verdict = judge.judge_reply(
            user_message=turn["user_message"].strip(),
            reply=result.user_facing_reply,
            scenario_description=scenario.get("description", ""),
            rubric=rubric,
        )
        status = verdict.error or f"overall {verdict.overall_score}/5 (passed={verdict.passed})"
        print(f"\nTurn {i}: {status}")
        for c in verdict.criteria:
            print(f"  - {c.name}: {c.score}/5 — {c.comment}")
        if verdict.rationale:
            print(f"  rationale: {verdict.rationale}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FutureSelf simulation harness",
    )
    parser.add_argument(
        "--scenario", "-s",
        help="Name of the scenario to run (without .yaml extension)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output",
    )
    parser.add_argument(
        "--eval", "-e",
        action="store_true",
        dest="show_eval",
        help="Print structured evaluation report after the scenario",
    )
    parser.add_argument(
        "--eval-json",
        action="store_true",
        help="Output only the evaluation as JSON (for piping to jq or saving)",
    )
    parser.add_argument(
        "--traces", "-t",
        action="store_true",
        help="Print LLM call traces (model, tokens, latency)",
    )
    parser.add_argument(
        "--judge", "-j",
        action="store_true",
        dest="show_judge",
        help="Run the LLM-as-judge rubric scorer (extra LLM call per turn)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available scenarios and exit",
    )

    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name in list_scenarios():
            print(f"  - {name}")
        return

    if not args.scenario:
        parser.print_help()
        return

    asyncio.run(run_scenario(
        args.scenario, args.verbose, args.show_eval, args.traces, args.eval_json,
        args.show_judge,
    ))


if __name__ == "__main__":
    main()

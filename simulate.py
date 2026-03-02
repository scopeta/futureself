"""CLI simulation harness for FutureSelf Phase 1 prompt testing.

Usage:
    python simulate.py --scenario motorcycle_purchase
    python simulate.py --scenario burnout_and_debt --verbose
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

from futureself.orchestrator import run_turn
from futureself.schemas import (
    OrchestratorResult,
    UserBlueprint,
)

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


def print_agent_response(domain: str, resp, refined: bool = False) -> None:
    tag = " (REFINED)" if refined else ""
    print(f"\n  [{domain}]{tag}")
    print(f"    confidence: {resp.confidence}")
    print(f"    urgency:    {resp.urgency}")
    print(f"    advice:     {resp.advice[:200]}{'...' if len(resp.advice) > 200 else ''}")
    if resp.tradeoff_flags:
        for flag in resp.tradeoff_flags:
            print(f"    tradeoff:   [{flag.severity}] {flag.concern_area}: {flag.description}")
    if resp.extensions:
        print(f"    extensions: {resp.extensions}")


def print_result(result: OrchestratorResult, turn_num: int, verbose: bool) -> None:
    print_header(f"Turn {turn_num}")

    print(f"\nAgents consulted: {result.agents_consulted}")
    print(f"Conflict detected: {result.conflict_detected}")
    if result.conflict_summary:
        print(f"Conflict summary: {result.conflict_summary}")

    if verbose:
        print_section("Initial Responses", "")
        for domain, resp in result.initial_responses.items():
            print_agent_response(domain, resp)

        if result.refined_responses:
            print_section("Refined Responses (after critique)", "")
            for domain, resp in result.refined_responses.items():
                print_agent_response(domain, resp, refined=True)

    print_section("Future Self Reply", result.user_facing_reply)

    if result.updated_blueprint.inferred_facts:
        print_section("Inferred Facts", "\n".join(
            f"  - {f}" for f in result.updated_blueprint.inferred_facts
        ))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_scenario(name: str, verbose: bool) -> None:
    scenario = load_scenario(name)
    print_header(f"Scenario: {scenario['name']}")
    print(f"Description: {scenario.get('description', 'N/A')}")

    blueprint = UserBlueprint.from_dict(scenario.get("user_blueprint", {}))

    for i, turn in enumerate(scenario.get("turns", []), start=1):
        user_msg = turn["user_message"].strip()
        print(f"\n>> User: {user_msg}")

        result = await run_turn(blueprint, user_msg)
        print_result(result, i, verbose)

        # Check expectations (soft — just log, don't fail)
        expected_agents = turn.get("expected_agents_consulted")
        if expected_agents:
            actual = set(result.agents_consulted)
            expected = set(expected_agents)
            if actual != expected:
                print(f"\n  [!] Expected agents {expected}, got {actual}")

        expect_conflict = turn.get("expect_conflict")
        if expect_conflict is not None and result.conflict_detected != expect_conflict:
            print(
                f"\n  [!] Expected conflict={expect_conflict}, "
                f"got conflict={result.conflict_detected}"
            )

        # Carry forward updated blueprint
        blueprint = result.updated_blueprint

    print_header("Scenario Complete")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FutureSelf Phase 1 simulation harness",
    )
    parser.add_argument(
        "--scenario", "-s",
        help="Name of the scenario to run (without .yaml extension)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print all agent responses, not just the final synthesis",
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

    asyncio.run(run_scenario(args.scenario, args.verbose))


if __name__ == "__main__":
    main()

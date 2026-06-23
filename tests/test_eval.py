"""Tests for the eval module."""
from __future__ import annotations

import json

import pytest

from futureself.eval import (
    ScenarioEval,
    TurnEval,
    check_expectations,
    evaluate_scenario,
    evaluate_turn,
    format_report,
    to_json,
)
from futureself.schemas import LLMCallTrace, OrchestratorResult, UserBlueprint


def _make_result(reply: str = "Some reply.", latency_ms: float = 123.0) -> OrchestratorResult:
    trace = LLMCallTrace(task="orchestrator.run_turn", model_requested="claude-opus-4-6", latency_ms=latency_ms)
    return OrchestratorResult(
        user_facing_reply=reply,
        updated_blueprint=UserBlueprint(),
        llm_traces=[trace],
    )


def test_evaluate_turn_non_empty_reply():
    turn_spec = {"user_message": "How do I sleep better?"}
    result = _make_result("Sleep 8 hours.")
    ev = evaluate_turn("test_scenario", 1, turn_spec, result)

    assert ev.reply_non_empty is True
    assert ev.reply_length == len("Sleep 8 hours.")
    assert ev.latency_ms == 123.0


def test_evaluate_turn_empty_reply():
    turn_spec = {"user_message": "hello"}
    result = _make_result("")
    ev = evaluate_turn("test_scenario", 1, turn_spec, result)

    assert ev.reply_non_empty is False
    assert ev.reply_length == 0


def test_evaluate_turn_no_traces_latency_zero():
    turn_spec = {"user_message": "hello"}
    result = OrchestratorResult(
        user_facing_reply="A reply.",
        updated_blueprint=UserBlueprint(),
        llm_traces=[],
    )
    ev = evaluate_turn("test_scenario", 1, turn_spec, result)

    assert ev.latency_ms == 0.0


def test_evaluate_scenario_all_non_empty():
    turns_spec = [
        {"user_message": "turn 1"},
        {"user_message": "turn 2"},
    ]
    results = [_make_result("Reply A"), _make_result("Reply B")]
    ev = evaluate_scenario("test", turns_spec, results)

    assert ev.all_replies_non_empty is True
    assert len(ev.turns) == 2


def test_evaluate_scenario_empty_reply_fails():
    turns_spec = [{"user_message": "turn 1"}, {"user_message": "turn 2"}]
    results = [_make_result("Reply A"), _make_result("")]
    ev = evaluate_scenario("test", turns_spec, results)

    assert ev.all_replies_non_empty is False


def test_format_report_produces_output():
    ev = ScenarioEval(
        scenario_name="test",
        turns=[
            TurnEval(
                scenario_name="test",
                turn_index=1,
                reply_length=42,
                reply_non_empty=True,
                latency_ms=99.0,
            )
        ],
        all_replies_non_empty=True,
    )
    report = format_report([ev])
    assert "test" in report
    assert "OK" in report


# ---------------------------------------------------------------------------
# Deterministic assertions (check_expectations)
# ---------------------------------------------------------------------------


def test_check_expectations_always_has_non_empty():
    results = check_expectations("hello", None)
    assert results[0].name == "non_empty"
    assert results[0].passed is True


def test_check_expectations_non_empty_fails_on_blank():
    results = check_expectations("   ", None)
    assert results[0].name == "non_empty"
    assert results[0].passed is False


def test_check_expectations_forbidden_phrase_detected():
    reply = "Let me load the relevant skills first."
    results = check_expectations(reply, {"forbidden": ["let me load", "load_skill"]})
    forbidden = [r for r in results if r.name == "forbidden"]
    assert any(r.passed is False for r in forbidden)  # "let me load" present


def test_check_expectations_forbidden_absent_passes():
    results = check_expectations("A clean reply.", {"forbidden": ["load_skill"]})
    assert all(r.passed for r in results if r.name == "forbidden")


def test_check_expectations_min_and_max_length():
    results = check_expectations("short", {"min_length": 100, "max_length": 3})
    by_name = {r.name: r for r in results}
    assert by_name["min_length"].passed is False
    assert by_name["max_length"].passed is False


def test_check_expectations_must_include_any_group():
    reply = "You should rest and recover before taking on more debt."
    expect = {"must_include_any": [["rest", "sleep"], ["debt", "money"]]}
    results = check_expectations(reply, expect)
    groups = [r for r in results if r.name == "must_include_any"]
    assert len(groups) == 2
    assert all(r.passed for r in groups)


def test_check_expectations_must_include_any_missing_group_fails():
    reply = "You should rest."
    expect = {"must_include_any": [["rest"], ["debt", "money"]]}
    results = check_expectations(reply, expect)
    groups = [r for r in results if r.name == "must_include_any"]
    assert groups[0].passed is True
    assert groups[1].passed is False


def test_evaluate_turn_populates_assertions_and_passed():
    turn_spec = {
        "user_message": "I'm in debt and exhausted.",
        "expect": {
            "min_length": 5,
            "forbidden": ["load_skill"],
            "must_include_any": [["rest"]],
        },
    }
    result = _make_result("You should rest and recover.")
    ev = evaluate_turn("s", 1, turn_spec, result)
    assert ev.passed is True
    assert {a.name for a in ev.assertions} >= {"non_empty", "min_length", "forbidden", "must_include_any"}


def test_evaluate_turn_fails_when_assertion_fails():
    turn_spec = {"user_message": "x", "expect": {"forbidden": ["rest"]}}
    result = _make_result("You should rest.")
    ev = evaluate_turn("s", 1, turn_spec, result)
    assert ev.passed is False


def test_evaluate_scenario_all_passed_field():
    turns_spec = [
        {"user_message": "a", "expect": {"must_include_any": [["yes"]]}},
        {"user_message": "b", "expect": {"forbidden": ["no"]}},
    ]
    results = [_make_result("yes indeed"), _make_result("no way")]
    ev = evaluate_scenario("s", turns_spec, results)
    assert ev.turns[0].passed is True
    assert ev.turns[1].passed is False
    assert ev.all_passed is False


def test_to_json_produces_valid_json():
    ev = ScenarioEval(
        scenario_name="test",
        turns=[],
        all_replies_non_empty=True,
    )
    raw = to_json([ev])
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert parsed[0]["scenario_name"] == "test"

"""Tests for the eval module."""
from __future__ import annotations

import json

import pytest

from futureself.eval import (
    ScenarioEval,
    TurnEval,
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

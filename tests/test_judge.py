"""Unit tests for the LLM-as-judge — no network, via an injected fake client."""
from __future__ import annotations

from types import SimpleNamespace

from futureself.judge import DEFAULT_RUBRIC, judge_reply


def _fake_client(response: object):
    """A minimal Anthropic-style client whose messages.create returns `response`."""
    def create(**_kwargs):  # noqa: ANN003
        if isinstance(response, Exception):
            raise response
        return response
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def _tool_response(payload: dict) -> object:
    block = SimpleNamespace(type="tool_use", input=payload)
    return SimpleNamespace(content=[block])


def test_judge_parses_tool_output():
    resp = _tool_response(
        {
            "overall_score": 5,
            "criteria": [{"name": "persona", "score": 5, "comment": "warm"}],
            "rationale": "excellent",
        }
    )
    result = judge_reply(
        user_message="q",
        reply="a warm, in-character reply",
        _client=_fake_client(resp),
    )
    assert result.error is None
    assert result.overall_score == 5
    assert result.passed is True
    assert result.criteria[0].name == "persona"


def test_judge_below_threshold_not_passed():
    resp = _tool_response({"overall_score": 2, "criteria": [], "rationale": "weak"})
    result = judge_reply(user_message="q", reply="meh", _client=_fake_client(resp))
    assert result.passed is False


def test_judge_malformed_output_degrades():
    resp = _tool_response({"criteria": []})  # missing overall_score
    result = judge_reply(user_message="q", reply="x", _client=_fake_client(resp))
    assert result.error is not None
    assert result.overall_score == 0
    assert result.passed is False


def test_judge_no_tool_block_degrades():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="nope")])
    result = judge_reply(user_message="q", reply="x", _client=_fake_client(resp))
    assert result.error is not None
    assert result.passed is False


def test_judge_client_exception_degrades():
    result = judge_reply(
        user_message="q",
        reply="x",
        _client=_fake_client(RuntimeError("boom")),
    )
    assert result.error is not None
    assert "boom" in result.error
    assert result.overall_score == 0


def test_default_rubric_nonempty():
    assert len(DEFAULT_RUBRIC) >= 3

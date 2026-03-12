"""Tests for the telemetry module's no-op fallback behaviour."""
import futureself.telemetry as tel
from futureself.telemetry import set_span_attributes, span


def test_span_yields_none_without_init(monkeypatch):
    """span() should yield None when _tracer is None."""
    monkeypatch.setattr(tel, "_tracer", None)
    with span("test.noop") as s:
        assert s is None


def test_set_span_attributes_tolerates_none():
    """set_span_attributes(None, ...) must not raise."""
    set_span_attributes(None, {"key": "value", "list_key": ["a", "b"]})

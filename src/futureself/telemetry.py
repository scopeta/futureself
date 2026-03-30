"""OpenTelemetry bootstrap — call ``init_telemetry()`` once at app startup.

If the ``opentelemetry`` SDK is not installed (the ``otel`` extra was not
included), every public symbol in this module becomes a silent no-op.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

_tracer: Any = None


def init_telemetry(service_name: str = "futureself") -> None:
    """Configure TracerProvider, ConsoleSpanExporter, and FastAPI instrumentor.

    Safe to call when OTel packages are not installed (becomes a no-op).
    """
    if not _HAS_OTEL:
        return

    global _tracer  # noqa: PLW0603

    import os  # noqa: PLC0415

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Azure Monitor exporter: activate when APPLICATIONINSIGHTS_CONNECTION_STRING is set.
    appinsights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if appinsights_conn:
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter  # noqa: PLC0415

            azure_exporter = AzureMonitorTraceExporter(connection_string=appinsights_conn)
            provider.add_span_processor(BatchSpanProcessor(azure_exporter))
        except ImportError:
            pass  # azure-monitor-opentelemetry-exporter not installed

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("futureself", "0.1.0")

    # Auto-instrument FastAPI (patches ASGI middleware globally).
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
    except ImportError:
        pass


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Start a traced span.  Yields the span object, or ``None`` if OTel is absent.

    Usage::

        with span("orchestrator.select_agents") as s:
            result = await do_work()
            set_span_attributes(s, {"agents": result})
    """
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name, attributes=attributes or {}) as s:
        yield s


def set_span_attributes(span_obj: Any, attrs: dict[str, Any]) -> None:
    """Set attributes on a span, tolerating ``None`` (no-op case)."""
    if span_obj is None:
        return
    for k, v in attrs.items():
        if isinstance(v, list):
            v = ", ".join(str(item) for item in v)
        span_obj.set_attribute(k, v)

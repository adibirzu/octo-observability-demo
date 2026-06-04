"""Langfuse span filter accepts the agent-path span names we emit."""

from __future__ import annotations

import pytest

from app.observability.langfuse_bridge import _LANGFUSE_SPAN_PREFIXES, _should_export_span_to_langfuse
from app.observability.tracing import init_tracing


class _FakeSpan:
    def __init__(self, name, attributes=None):
        self.name = name
        self.attributes = attributes or {}


@pytest.mark.unit
@pytest.mark.parametrize(
    "span_name",
    [
        "studio.brief",
        "coordinator.supervisor",
        "agent.invoke.sales_analyst",
        "agent.invoke.presenter",
        "llm.invoke.chat",
        "tool.code_interpreter",
        "retrieval.evidence",
    ],
)
def test_agent_path_spans_export_to_langfuse(span_name):
    assert span_name.startswith(_LANGFUSE_SPAN_PREFIXES)
    assert _should_export_span_to_langfuse(_FakeSpan(span_name)) is True


@pytest.mark.unit
def test_infra_span_without_genai_attrs_is_not_exported():
    assert _should_export_span_to_langfuse(_FakeSpan("http.server.request")) is False


@pytest.mark.unit
def test_no_apm_fallback_uses_synchronous_console_exporter(monkeypatch):
    """Avoid delayed background exports after pytest/local stdout is closed."""
    from app.observability import tracing
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    monkeypatch.setattr(tracing, "_provider", None)
    provider = init_tracing(
        service_name="octo-genai-studio-test",
        service_version="test",
        service_namespace="octo-test",
        apm_endpoint="",
        apm_private_key="",
    )

    processors = provider._active_span_processor._span_processors  # type: ignore[attr-defined]
    assert any(isinstance(processor, SimpleSpanProcessor) for processor in processors)

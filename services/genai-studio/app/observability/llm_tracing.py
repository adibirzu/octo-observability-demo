"""GenAI semantic-convention span helper for LLM calls.

A focused port of oci-coordinator-oke/src/observability/llm_tracing.py: emits the
OpenTelemetry ``gen_ai.*`` attributes that both OCI APM and Langfuse understand.
Used to wrap each ChatOCIGenAI invocation inside an agent node.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from app.observability.tracing import get_tracer

# Capture prompt/completion text in spans only when explicitly allowed.
import os

_CAPTURE_CONTENT = os.getenv("OTEL_GENAI_CAPTURE_CONTENT", "false").lower() in {"1", "true", "yes", "on"}
_PREVIEW_CHARS = 600


class GenAISpan:
    """Thin wrapper exposing the gen_ai.* setters on an active span."""

    def __init__(self, span: Span) -> None:
        self.span = span
        self._started = time.monotonic()

    def set_request_params(
        self,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        if max_tokens is not None:
            self.span.set_attribute("gen_ai.request.max_tokens", int(max_tokens))
        if temperature is not None:
            self.span.set_attribute("gen_ai.request.temperature", float(temperature))
        if top_p is not None:
            self.span.set_attribute("gen_ai.request.top_p", float(top_p))

    def set_prompt(self, text: str, *, role: str = "user") -> None:
        self.span.set_attribute("gen_ai.prompt.role", role)
        if _CAPTURE_CONTENT and text:
            self.span.set_attribute("gen_ai.prompt", text[:_PREVIEW_CHARS])

    def set_completion(self, text: str) -> None:
        if _CAPTURE_CONTENT and text:
            self.span.set_attribute("gen_ai.completion", text[:_PREVIEW_CHARS])

    def set_tokens(self, *, input: int | None = None, output: int | None = None) -> None:
        total = 0
        if input is not None:
            self.span.set_attribute("gen_ai.usage.input_tokens", int(input))
            total += int(input)
        if output is not None:
            self.span.set_attribute("gen_ai.usage.output_tokens", int(output))
            total += int(output)
        if input is not None and output is not None:
            self.span.set_attribute("gen_ai.usage.total_tokens", total)

    def set_finish_reason(self, reason: str) -> None:
        if reason:
            self.span.set_attribute("gen_ai.response.finish_reasons", [reason])

    def record_error(self, exc: BaseException) -> None:
        self.span.record_exception(exc)
        self.span.set_attribute("gen_ai.error.type", exc.__class__.__name__)
        self.span.set_status(Status(StatusCode.ERROR, str(exc)))


@contextmanager
def llm_span(
    *,
    operation: str,
    model: str,
    system: str = "oci_genai",
    agent: str | None = None,
) -> Iterator[GenAISpan]:
    """Open a `llm.invoke.<operation>` span carrying gen_ai.* semantic attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(f"llm.invoke.{operation}") as span:
        span.set_attribute("gen_ai.operation.name", operation)
        span.set_attribute("gen_ai.system", system)
        span.set_attribute("gen_ai.request.model", model)
        if agent:
            span.set_attribute("gen_ai.agent.name", agent)
        yield GenAISpan(span)


def current_trace_id() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""

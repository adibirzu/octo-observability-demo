"""Bind run/session/user context onto every span created within a scope.

A span processor reads the active context vars and stamps them on each span as it
starts, so APM and Langfuse can correlate a whole multi-agent run by run_id/session.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from opentelemetry.context import Context
from opentelemetry.sdk.trace import Span, SpanProcessor

_run_id: ContextVar[str] = ContextVar("studio_run_id", default="")
_session_id: ContextVar[str] = ContextVar("studio_session_id", default="")
_user: ContextVar[str] = ContextVar("studio_user", default="")
_channel: ContextVar[str] = ContextVar("studio_channel", default="")


class ContextEnrichmentSpanProcessor(SpanProcessor):
    """Stamp active run/session/user context onto each span at start."""

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        run_id = _run_id.get()
        if run_id:
            span.set_attribute("studio.run_id", run_id)
            # Langfuse session grouping
            span.set_attribute("session.id", _session_id.get() or run_id)
        user = _user.get()
        if user:
            span.set_attribute("user.id", user)
        channel = _channel.get()
        if channel:
            span.set_attribute("studio.channel", channel)

    def on_end(self, span) -> None:  # noqa: D401 - no-op
        return

    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


@contextmanager
def run_scope(
    *,
    run_id: str,
    session_id: str = "",
    user: str = "",
    channel: str = "ai-studio",
) -> Iterator[None]:
    """Activate enrichment context for the duration of one studio run."""
    tokens = [
        _run_id.set(run_id),
        _session_id.set(session_id or run_id),
        _user.set(user),
        _channel.set(channel),
    ]
    try:
        yield
    finally:
        for var, tok in zip((_run_id, _session_id, _user, _channel), tokens):
            var.reset(tok)

"""Langfuse export attached to the shared OpenTelemetry tracer provider.

Ported from oci-coordinator-oke/src/observability/langfuse.py. Langfuse consumes
the same spans the APM exporter sees; a span-name/attribute filter restricts the
Langfuse stream to the agent + LLM execution path so infra spans stay out of it.
"""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    from langfuse import Langfuse
    from langfuse.span_filter import is_default_export_span
except Exception:  # pragma: no cover - optional dependency fallback
    Langfuse = None

    def is_default_export_span(_span: Any) -> bool:
        return False


logger = logging.getLogger(__name__)

_state: dict[str, Any] = {"client": None, "enabled": False}

# Span-name prefixes that belong to the agent execution path. The Drone Shop AI
# Studio names its spans with these prefixes (coordinator.*, agent.invoke.*, etc.)
# so this filter is the contract that keeps APM-only infra spans out of Langfuse.
_LANGFUSE_SPAN_PREFIXES = (
    "coordinator.",
    "studio.",
    "agent.invoke.",
    "llm.invoke.",
    "gen_ai.",
    "tool.",
    "retrieval.",
    "rag.",
    "vector_db.",
)


def _should_enable_langfuse() -> bool:
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _should_export_span_to_langfuse(span: Any) -> bool:
    try:
        if is_default_export_span(span):
            return True
    except Exception:
        pass

    span_name = str(getattr(span, "name", "") or "")
    if span_name.startswith(_LANGFUSE_SPAN_PREFIXES):
        return True

    attributes = getattr(span, "attributes", {}) or {}
    interesting = ("gen_ai.", "agent.", "tool.", "retrieval.", "rag.", "studio.")
    return any(str(key).startswith(interesting) for key in attributes)


def init_langfuse(tracer_provider: Any) -> bool:
    """Attach Langfuse export to the shared tracer provider. Returns True if enabled."""
    if _state["client"] is not None:
        return bool(_state["enabled"])
    if not _should_enable_langfuse():
        return False

    try:
        if Langfuse is None:
            raise RuntimeError("langfuse package is not available")
        _state["client"] = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL"),
            timeout=int(os.getenv("LANGFUSE_TIMEOUT", "5")),
            environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT")
            or os.getenv("DEPLOYMENT_ENV", "development"),
            release=os.getenv("LANGFUSE_RELEASE") or os.getenv("APP_VERSION") or "0.1.0",
            sample_rate=float(os.getenv("LANGFUSE_SAMPLE_RATE", "1.0")),
            should_export_span=_should_export_span_to_langfuse,
            tracer_provider=tracer_provider,
        )
        _state["enabled"] = True
        logger.info(
            "Langfuse tracing enabled (host=%s)",
            os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "cloud.langfuse.com",
        )
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Langfuse initialization failed: %s", exc)
        _state["client"] = None
        _state["enabled"] = False
        return False


def flush_langfuse() -> None:
    client = _state["client"]
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse flush failed: %s", exc)


def shutdown_langfuse() -> None:
    client = _state["client"]
    if client is None:
        _state["enabled"] = False
        return
    try:
        client.shutdown()
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse shutdown failed: %s", exc)
    finally:
        _state["client"] = None
        _state["enabled"] = False


def is_langfuse_enabled() -> bool:
    return bool(_state["enabled"])


__all__ = [
    "flush_langfuse",
    "init_langfuse",
    "is_langfuse_enabled",
    "shutdown_langfuse",
]

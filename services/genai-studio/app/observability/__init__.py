"""Observability bootstrap: one OTEL tracer provider feeding OCI APM and Langfuse."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.observability.langfuse_bridge import (
    flush_langfuse,
    init_langfuse,
    is_langfuse_enabled,
    shutdown_langfuse,
)
from app.observability.tracing import get_tracer, get_tracer_provider, init_tracing

logger = logging.getLogger(__name__)

_state = {"initialized": False}


def init_observability() -> None:
    """Initialize tracing and attach Langfuse to the shared tracer provider."""
    if _state["initialized"]:
        return
    settings = get_settings()
    provider = init_tracing(
        service_name=settings.otel_service_name,
        service_version=settings.app_version,
        service_namespace=settings.service_namespace,
        apm_endpoint=settings.apm_endpoint,
        apm_private_key=settings.apm_private_data_key,
    )
    if init_langfuse(provider):
        logger.info("AI Studio observability: APM + Langfuse active")
    else:
        logger.info("AI Studio observability: APM only (Langfuse disabled/unconfigured)")
    _state["initialized"] = True


def shutdown_observability() -> None:
    """Flush and shut down exporters on service stop."""
    flush_langfuse()
    shutdown_langfuse()


__all__ = [
    "get_tracer",
    "get_tracer_provider",
    "init_observability",
    "is_langfuse_enabled",
    "shutdown_observability",
]

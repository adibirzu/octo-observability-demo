"""OpenTelemetry tracer provider that exports to OCI APM via OTLP/HTTP.

Mirrors the OCTO Drone Shop's own APM wiring (server/observability/otel_setup.py)
so AI Studio spans land in the same APM domain and correlate with shop traces:
the OTLP endpoint shape and the ``Authorization: dataKey <key>`` header are identical.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_provider: TracerProvider | None = None


def _apm_traces_endpoint(apm_endpoint: str) -> str:
    """Normalize an APM upload endpoint to the OTLP private traces path."""
    base = apm_endpoint.rstrip("/").split("/20200101")[0]
    return f"{base}/20200101/opentelemetry/private/v1/traces"


def init_tracing(
    *,
    service_name: str,
    service_version: str,
    service_namespace: str,
    apm_endpoint: str,
    apm_private_key: str,
) -> TracerProvider:
    """Create and install the global tracer provider. Idempotent."""
    global _provider
    if _provider is not None:
        return _provider

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "service.namespace": service_namespace,
        }
    )
    provider = TracerProvider(resource=resource)

    # Stamp run/session/user context onto every span (added before exporters).
    from app.observability.enrichments import ContextEnrichmentSpanProcessor

    provider.add_span_processor(ContextEnrichmentSpanProcessor())

    if apm_endpoint and apm_private_key:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(
            endpoint=_apm_traces_endpoint(apm_endpoint),
            headers={"Authorization": f"dataKey {apm_private_key}"},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel OTLP exporter -> OCI APM (%s)", service_name)
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OTel console exporter (no APM configured): %s", service_name)

    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer_provider() -> TracerProvider | None:
    return _provider


def get_tracer(name: str = "octo-genai-studio") -> trace.Tracer:
    return trace.get_tracer(name)

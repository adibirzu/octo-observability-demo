"""Same-origin proxy for the AI Studio GenAI multi-agent service.

Modelled on ``server/modules/workflow_gateway.py``: admin/internal-service auth,
W3C trace-context forwarding (so APM shows one trace spanning shop → studio →
each agent → each LLM call), and upstream-attribute lifting onto the proxy span.
Returns 503 when AI Studio is not configured, so the shop is unaffected by default.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from opentelemetry.propagate import inject
from opentelemetry.trace import Status, StatusCode

from server.auth_security import require_admin_or_internal_service
from server.config import cfg
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-studio", tags=["ai-studio"])

_FORWARDED_HEADERS = (
    "authorization",
    "content-type",
    "traceparent",
    "tracestate",
    "x-correlation-id",
    "x-request-id",
    "x-session-id",
)
_MAX_PROXY_BODY_BYTES = 8_192
_MAX_REQUEST_CHARS = 1000


def _copy_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in _FORWARDED_HEADERS:
        value = request.headers.get(name)
        if value:
            headers[name] = value
    if cfg.ai_studio_internal_service_key:
        headers["x-internal-service-key"] = cfg.ai_studio_internal_service_key
    # Explicitly inject the active span context (W3C traceparent/tracestate) so the
    # studio continues THIS trace — one APM trace spans shop -> studio -> agents,
    # independent of httpx auto-instrumentation being active.
    inject(headers)
    return headers


def _validate_payload(content: bytes | None) -> dict:
    if content and len(content) > _MAX_PROXY_BODY_BYTES:
        raise HTTPException(status_code=413, detail="AI Studio request body is too large")
    if not content:
        return {}
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="AI Studio request must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="AI Studio request must be a JSON object")
    if len(str(payload.get("request") or "")) > _MAX_REQUEST_CHARS:
        raise HTTPException(status_code=400, detail=f"request exceeds {_MAX_REQUEST_CHARS} characters")
    return payload


def _lift_upstream_attributes(span, upstream: httpx.Response) -> None:
    try:
        payload = upstream.json()
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    for key, attr in (
        ("run_id", "ai_studio.run_id"),
        ("trace_id", "ai_studio.upstream_trace_id"),
        ("status", "ai_studio.status"),
        ("model_id", "gen_ai.request.model"),
    ):
        if payload.get(key):
            span.set_attribute(attr, str(payload[key])[:80])
    agents = payload.get("agents_run")
    if isinstance(agents, list):
        span.set_attribute("ai_studio.agents_run", ",".join(map(str, agents))[:200])
    usage = payload.get("token_usage") or {}
    if usage.get("input") is not None:
        span.set_attribute("gen_ai.usage.input_tokens", int(usage["input"]))
    if usage.get("output") is not None:
        span.set_attribute("gen_ai.usage.output_tokens", int(usage["output"]))


@router.post("/brief")
async def studio_brief(request: Request) -> Response:
    """Proxy a merchandising-brief run to the AI Studio service with trace context."""
    principal = require_admin_or_internal_service(request)
    if not cfg.ai_studio_configured:
        raise HTTPException(status_code=503, detail="AI Studio is not configured")

    content = await request.body()
    _validate_payload(content)
    target = f"{cfg.ai_studio_base_url}/api/studio/brief"
    tracer = get_tracer("octo-drone-shop.ai-studio")

    with tracer.start_as_current_span("ai_studio.brief") as span:
        span.set_attributes(
            {
                "app.module": "admin-ai-studio",
                "app.logical_endpoint": "admin.ai_studio.brief",
                "ai_studio.service_name": cfg.ai_studio_service_name,
                "ai_studio.admin_required": True,
                "http.request.method": "POST",
                "auth.role": str(principal.get("role", "unknown")),
            }
        )
        try:
            async with httpx.AsyncClient(timeout=cfg.ai_studio_timeout_seconds) as client:
                upstream = await client.post(target, content=content, headers=_copy_headers(request))
        except httpx.HTTPError as exc:
            span.record_exception(exc)
            span.set_attribute("ai_studio.error", exc.__class__.__name__)
            logger.warning("AI Studio proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail="AI Studio request failed") from exc

        span.set_attribute("http.response.status_code", upstream.status_code)
        span.set_attribute("ai_studio.response_bytes", len(upstream.content))
        _lift_upstream_attributes(span, upstream)
        if upstream.status_code >= 400:
            span.set_status(Status(StatusCode.ERROR, str(upstream.status_code)))

    push_log(
        "INFO",
        "AI Studio brief proxied",
        **{
            "ai_studio.status_code": upstream.status_code,
            "ai_studio.service_name": cfg.ai_studio_service_name,
            "auth.role": str(principal.get("role", "unknown")),
        },
    )
    headers = {}
    content_type = upstream.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)

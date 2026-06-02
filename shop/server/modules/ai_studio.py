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
from fastapi.responses import JSONResponse
from opentelemetry.propagate import inject
from opentelemetry.trace import Status, StatusCode

from server.auth_security import (
    SESSION_COOKIE_NAME,
    _is_internal_service_call,
    require_admin_or_internal_service,
)
from server.config import cfg
from server.modules.auth import login as _password_login
from server.observability.logging_sdk import push_log


def _request_host(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or (request.url.hostname or "")
    ).split(",", 1)[0].strip().lower()


def _enforce_admin_host(request: Request) -> None:
    """Browser calls to AI Studio must arrive on the admin host (else 404).

    Internal service-to-service calls (validated by the shared key) are exempt —
    they carry no browser host and run inside the cluster.
    """
    if _is_internal_service_call(request):
        return
    if not cfg.is_admin_host(_request_host(request)):
        raise HTTPException(status_code=404, detail="Not Found")
from server.observability.otel_setup import get_tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-studio", tags=["ai-studio"])


def _request_is_https(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower() == "https"
    )


@router.post("/login")
async def studio_login(request: Request) -> Response:
    """Cookie-issuing admin sign-in for AI Studio on the admin host.

    The shared shop login (``/api/auth/login``) only returns a localStorage
    bearer token; server-rendered admin pages authenticate via the
    ``octo_session`` cookie. This endpoint — reachable only on the admin host
    and routed to the shop by the LB ``/api/ai-studio`` rule — verifies
    credentials (reusing the password-login flow for rate-limiting + audit),
    requires the admin role, and sets the session cookie so a subsequent
    ``GET /ai-studio`` page navigation is authenticated.
    """
    _enforce_admin_host(request)

    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Login request must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Login request must be a JSON object")

    # Reuse the canonical password-login handler (raises 400/401/429 on failure)
    # so rate-limiting, the audit log, and auth telemetry stay in one place.
    result = await _password_login(request, payload)
    user = result.get("user") or {}
    if str(user.get("role")) != "admin":
        raise HTTPException(status_code=403, detail="AI Studio requires an admin account")

    response = JSONResponse(
        {
            "status": "success",
            "redirect": "/ai-studio",
            "user": {"username": user.get("username"), "role": user.get("role")},
        }
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        result["token"],
        httponly=True,
        secure=_request_is_https(request),
        samesite="lax",
        path="/",
    )
    return response

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
    field = str(payload.get("request") or payload.get("question") or payload.get("message") or "")
    if len(field) > _MAX_REQUEST_CHARS:
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


async def _proxy(request: Request, *, op: str, upstream_path: str) -> Response:
    """Shared admin-gated, trace-propagating proxy to the AI Studio service."""
    _enforce_admin_host(request)
    principal = require_admin_or_internal_service(request)
    if not cfg.ai_studio_configured:
        raise HTTPException(status_code=503, detail="AI Studio is not configured")

    content = await request.body()
    _validate_payload(content)
    target = f"{cfg.ai_studio_base_url}{upstream_path}"
    tracer = get_tracer("octo-drone-shop.ai-studio")

    with tracer.start_as_current_span(f"ai_studio.{op}") as span:
        span.set_attributes(
            {
                "app.module": "admin-ai-studio",
                "app.logical_endpoint": f"admin.ai_studio.{op}",
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
        f"AI Studio {op} proxied",
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


@router.post("/brief")
async def studio_brief(request: Request) -> Response:
    """Proxy a merchandising-brief run to the AI Studio service with trace context."""
    return await _proxy(request, op="brief", upstream_path="/api/studio/brief")


@router.post("/ask")
async def studio_ask(request: Request) -> Response:
    """Proxy a free-form Data Q&A (orders/products/analytics) to AI Studio."""
    return await _proxy(request, op="ask", upstream_path="/api/studio/ask")


@router.post("/rag")
async def studio_rag(request: Request) -> Response:
    """Proxy a retrieval-augmented Q&A (products/specs/policies) to AI Studio."""
    return await _proxy(request, op="rag", upstream_path="/api/studio/rag")


async def _proxy_get(request: Request, *, op: str, upstream_path: str) -> Response:
    """Admin-gated, trace-propagating GET proxy to the AI Studio service."""
    _enforce_admin_host(request)
    principal = require_admin_or_internal_service(request)
    if not cfg.ai_studio_configured:
        raise HTTPException(status_code=503, detail="AI Studio is not configured")

    target = f"{cfg.ai_studio_base_url}{upstream_path}"
    tracer = get_tracer("octo-drone-shop.ai-studio")
    with tracer.start_as_current_span(f"ai_studio.{op}") as span:
        span.set_attributes(
            {
                "app.module": "admin-ai-studio",
                "app.logical_endpoint": f"admin.ai_studio.{op}",
                "ai_studio.service_name": cfg.ai_studio_service_name,
                "ai_studio.admin_required": True,
                "http.request.method": "GET",
                "auth.role": str(principal.get("role", "unknown")),
            }
        )
        try:
            async with httpx.AsyncClient(timeout=cfg.ai_studio_timeout_seconds) as client:
                upstream = await client.get(
                    target, params=dict(request.query_params), headers=_copy_headers(request)
                )
        except httpx.HTTPError as exc:
            span.record_exception(exc)
            span.set_attribute("ai_studio.error", exc.__class__.__name__)
            logger.warning("AI Studio GET proxy failed: %s", exc)
            raise HTTPException(status_code=502, detail="AI Studio request failed") from exc
        span.set_attribute("http.response.status_code", upstream.status_code)
        if upstream.status_code >= 400:
            span.set_status(Status(StatusCode.ERROR, str(upstream.status_code)))

    headers = {}
    content_type = upstream.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


@router.get("/metrics")
async def studio_metrics(request: Request) -> Response:
    """Proxy the GenAI telemetry summary (admin observability page) from AI Studio."""
    return await _proxy_get(request, op="metrics", upstream_path="/api/studio/metrics/summary")


# ── Phase B: chat proxy ────────────────────────────────────────────────────
@router.post("/chat")
async def studio_chat(request: Request) -> Response:
    """Proxy a multi-turn chat turn (JSON) to the AI Studio service.

    Admin/internal-service gated; forwards W3C trace context so the conversation
    is one continuous trace shop -> studio -> chat_assistant -> OCI GenAI. The
    studio also supports SSE (stream=true); this buffered proxy serves the JSON
    path used by the admin UI.
    """
    return await _proxy(request, op="chat", upstream_path="/api/studio/chat")

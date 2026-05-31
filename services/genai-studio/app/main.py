"""AI Studio FastAPI service.

Endpoints:
  GET  /health            liveness
  GET  /readyz            readiness (GenAI configured?)
  POST /api/studio/brief  run the multi-agent merchandising-brief workflow
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.graph import get_compiled_graph, recursion_limit
from app.guardrails import bounded, scope_decision
from app.observability import (
    init_observability,
    is_langfuse_enabled,
    shutdown_observability,
)
from app.observability.enrichments import run_scope
from app.observability.llm_tracing import current_trace_id
from app.observability.tracing import get_tracer
from app.state import empty_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genai-studio")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_observability()
    try:
        yield
    finally:
        shutdown_observability()


app = FastAPI(title="OCTO Drone Shop — AI Studio", version="0.1.0", lifespan=lifespan)

# Initialize tracing and FastAPI instrumentation at construction time (NOT in
# lifespan): the ASGI middleware that extracts the inbound W3C ``traceparent``
# must be installed before the app starts serving, so the studio continues the
# shop's trace and APM shows one trace spanning shop -> studio -> agents.
init_observability()
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except Exception as exc:  # pragma: no cover
    logger.warning("FastAPI instrumentation unavailable: %s", exc)


class BriefRequest(BaseModel):
    request: str = Field(..., description="Merchandising instruction")
    category: str = Field("", description="Optional category focus")
    session_id: str = Field("", description="Conversation/session id for correlation")
    user: str = Field("", description="Requesting user (email or id)")


class AskRequest(BaseModel):
    question: str = Field(..., description="Free-form question about orders/products/analytics")
    session_id: str = Field("", description="Conversation/session id for correlation")
    user: str = Field("", description="Requesting user (email or id)")


def _require_internal_key(provided: str | None) -> None:
    expected = get_settings().internal_service_key
    if not expected:
        return  # unset in local/dev means open; set it in shared envs
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid internal service key")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    settings = get_settings()
    return {
        "status": "ready" if settings.genai_configured else "degraded",
        "genai_configured": settings.genai_configured,
        "apm_configured": settings.apm_configured,
        "langfuse_enabled": is_langfuse_enabled(),
        "db_kind": settings.db_kind,
    }


@app.post("/api/studio/brief")
async def studio_brief(
    body: BriefRequest,
    request: Request,
    x_internal_service_key: str | None = Header(default=None),
) -> dict:
    """Run the multi-agent workflow and return the merchandising brief."""
    _require_internal_key(x_internal_service_key)
    settings = get_settings()

    instruction = bounded(body.request, limit=settings.message_max_chars)
    allowed, reason = scope_decision(instruction)
    run_id = uuid.uuid4().hex
    session_id = bounded(body.session_id, limit=64) or run_id
    user = bounded(body.user, limit=200)

    tracer = get_tracer()
    with run_scope(run_id=run_id, session_id=session_id, user=user):
        with tracer.start_as_current_span("studio.brief") as span:
            span.set_attribute("studio.run_id", run_id)
            span.set_attribute("studio.guardrail.allowed", allowed)
            span.set_attribute("studio.guardrail.reason", reason)
            span.set_attribute("studio.category", bounded(body.category, limit=120))
            trace_id = current_trace_id()

            if not allowed:
                span.set_attribute("studio.outcome", "guardrail_blocked")
                return {
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "status": "refused",
                    "reason": reason,
                    "brief": (
                        "This studio only produces drone merchandising and operations briefs."
                    ),
                }

            state = empty_state(
                request=instruction,
                category=bounded(body.category, limit=120),
                run_id=run_id,
                session_id=session_id,
                user=user,
            )
            try:
                final = get_compiled_graph().invoke(
                    state, config={"recursion_limit": recursion_limit()}
                )
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("studio.outcome", "error")
                logger.exception("Studio run failed")
                raise HTTPException(status_code=502, detail="studio run failed") from exc

            usage = final.get("token_usage", {})
            span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
            span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))
            span.set_attribute("studio.agents_run", ",".join(final.get("completed", [])))
            span.set_attribute("studio.outcome", "success")

            return {
                "run_id": run_id,
                "trace_id": trace_id,
                "status": "ok",
                "agents_run": final.get("completed", []),
                "model_id": settings.genai_model_id,
                "token_usage": usage,
                "brief": final.get("brief", ""),
                "chart_png_base64": final.get("chart", {}).get("chart_png_base64", ""),
                "sales": final.get("sales", {}),
            }


@app.post("/api/studio/ask")
async def studio_ask(
    body: AskRequest,
    request: Request,
    x_internal_service_key: str | None = Header(default=None),
) -> dict:
    """Free-form Data Q&A over orders/products/analytics (single-agent path).

    Distinct from /brief: routes to the Data Analyst agent which reads a read-only
    ATP overview and answers the question. Traced under studio.ask with the same
    gen_ai.* / studio.run_id conventions, so it appears in OCI APM and Langfuse
    identically to a brief run.
    """
    _require_internal_key(x_internal_service_key)
    settings = get_settings()

    from app.agents.data_qa import answer_data_question

    question = bounded(body.question, limit=settings.message_max_chars)
    allowed, reason = scope_decision(question)
    run_id = uuid.uuid4().hex
    session_id = bounded(body.session_id, limit=64) or run_id
    user = bounded(body.user, limit=200)

    tracer = get_tracer()
    with run_scope(run_id=run_id, session_id=session_id, user=user):
        with tracer.start_as_current_span("studio.ask") as span:
            span.set_attribute("studio.run_id", run_id)
            span.set_attribute("studio.mode", "data_qa")
            span.set_attribute("studio.guardrail.allowed", allowed)
            span.set_attribute("studio.guardrail.reason", reason)
            trace_id = current_trace_id()

            if not allowed:
                span.set_attribute("studio.outcome", "guardrail_blocked")
                return {
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "status": "refused",
                    "reason": reason,
                    "answer": (
                        "I can only answer questions about OCTO drone-shop orders, "
                        "products, and sales analytics."
                    ),
                }

            try:
                result = answer_data_question(question)
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("studio.outcome", "error")
                logger.exception("Studio ask failed")
                raise HTTPException(status_code=502, detail="studio ask failed") from exc

            usage = result.get("token_usage", {})
            span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
            span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))
            span.set_attribute("studio.data_source", result.get("data_source", "unknown"))
            span.set_attribute("studio.outcome", "success")

            return {
                "run_id": run_id,
                "trace_id": trace_id,
                "status": "ok",
                "agents_run": ["data_analyst"],
                "model_id": settings.genai_model_id,
                "token_usage": usage,
                "answer": result.get("answer", ""),
                "data_source": result.get("data_source", ""),
            }

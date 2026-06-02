"""AI Studio FastAPI service.

Endpoints:
  GET  /health            liveness
  GET  /readyz            readiness (GenAI configured?)
  POST /api/studio/brief  run the multi-agent merchandising-brief workflow
"""

from __future__ import annotations

import json
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


class _StudioJsonFormatter(logging.Formatter):
    """One JSON object per line so OCI Logging Analytics can extract the
    gen_ai.* / studio.* fields. The GenAI dashboards query Log Source
    'octo-genai-studio' for exactly these fields (gen_ai.agent.name, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service.name": "octo-genai-studio",
        }
        fields = getattr(record, "studio_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# Dedicated structured-event logger: pure-JSON stdout lines, collected by the
# OKE Logging Analytics agent into the 'octo-genai-studio' Log Source so the
# GenAI Command Center dashboards render. propagate=False keeps these off the
# plain root handler (no double-logging).
_studio_event_handler = logging.StreamHandler()
_studio_event_handler.setFormatter(_StudioJsonFormatter())
_studio_event_logger = logging.getLogger("genai-studio.events")
_studio_event_logger.setLevel(logging.INFO)
_studio_event_logger.handlers = [_studio_event_handler]
_studio_event_logger.propagate = False


def log_studio_run(event: str, **fields: object) -> None:
    """Emit one structured gen_ai/studio run record (JSON line). Never raises —
    observability must not break a studio run."""
    try:
        _studio_event_logger.info(event, extra={"studio_fields": {"event": event, **fields}})
    except Exception:  # pragma: no cover - defensive
        logger.debug("structured studio log emit failed", exc_info=True)


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


class RagRequest(BaseModel):
    question: str = Field(..., description="Free-form product/spec/policy question (semantic RAG)")
    top_k: int = Field(0, description="Override the number of retrieved passages")
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
            log_studio_run(
                "studio.brief",
                **{
                    "studio.run_id": run_id,
                    "trace_id": trace_id,
                    "studio.mode": "brief",
                    "studio.outcome": "success",
                    "studio.agents_run": ",".join(final.get("completed", [])),
                    "gen_ai.agent.name": (final.get("completed") or ["supervisor"])[0],
                    "gen_ai.request.model": settings.genai_model_id,
                    "gen_ai.usage.input_tokens": int(usage.get("input", 0)),
                    "gen_ai.usage.output_tokens": int(usage.get("output", 0)),
                },
            )

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
            log_studio_run(
                "studio.ask",
                **{
                    "studio.run_id": run_id,
                    "trace_id": trace_id,
                    "studio.mode": "data_qa",
                    "studio.outcome": "success",
                    "studio.data_source": result.get("data_source", "unknown"),
                    "studio.agents_run": "data_analyst",
                    "gen_ai.agent.name": "data_analyst",
                    "gen_ai.request.model": settings.genai_model_id,
                    "gen_ai.usage.input_tokens": int(usage.get("input", 0)),
                    "gen_ai.usage.output_tokens": int(usage.get("output", 0)),
                },
            )

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


@app.post("/api/studio/rag")
async def studio_rag(
    body: RagRequest,
    request: Request,
    x_internal_service_key: str | None = Header(default=None),
) -> dict:
    """Retrieval-augmented Q&A over the 19c knowledge base (single-agent path).

    Routes to the RAG agent which embeds the question, runs an app-side cosine
    similarity search over ``genai_kb`` (catalog + curated docs; embeddings stored
    as JSON in a CLOB on Oracle 19c — no native VECTOR), and answers
    grounded on the retrieved passages. Traced under ``studio.rag`` with the
    retrieval.embed + vector_db.search child spans so the RAG pipeline is visible
    in OCI APM and Langfuse exactly like a brief/ask run.
    """
    _require_internal_key(x_internal_service_key)
    settings = get_settings()

    from app.agents.rag import answer_rag_question

    question = bounded(body.question, limit=settings.message_max_chars)
    allowed, reason = scope_decision(question)
    run_id = uuid.uuid4().hex
    session_id = bounded(body.session_id, limit=64) or run_id
    user = bounded(body.user, limit=200)

    tracer = get_tracer()
    with run_scope(run_id=run_id, session_id=session_id, user=user):
        with tracer.start_as_current_span("studio.rag") as span:
            span.set_attribute("studio.run_id", run_id)
            span.set_attribute("studio.mode", "rag")
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
                        "I can only answer questions about OCTO drone-shop products, "
                        "specs, orders, and policies."
                    ),
                }

            try:
                result = answer_rag_question(question, k=(body.top_k or None))
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("studio.outcome", "error")
                logger.exception("Studio rag failed")
                raise HTTPException(status_code=502, detail="studio rag failed") from exc

            usage = result.get("token_usage", {})
            span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
            span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))
            span.set_attribute("studio.data_source", result.get("data_source", "unknown"))
            span.set_attribute("retrieval.documents.count", int(result.get("retrieved_count", 0)))
            span.set_attribute("studio.outcome", "success")
            log_studio_run(
                "studio.rag",
                **{
                    "studio.run_id": run_id,
                    "trace_id": trace_id,
                    "studio.mode": "rag",
                    "studio.outcome": "success",
                    "studio.data_source": result.get("data_source", "unknown"),
                    "studio.agents_run": "rag_analyst",
                    "gen_ai.agent.name": "rag_analyst",
                    "gen_ai.request.model": settings.genai_model_id,
                    "gen_ai.usage.input_tokens": int(usage.get("input", 0)),
                    "gen_ai.usage.output_tokens": int(usage.get("output", 0)),
                    "retrieval.documents.count": int(result.get("retrieved_count", 0)),
                },
            )

            return {
                "run_id": run_id,
                "trace_id": trace_id,
                "status": "ok",
                "agents_run": ["rag_analyst"],
                "model_id": settings.genai_model_id,
                "token_usage": usage,
                "answer": result.get("answer", ""),
                "citations": result.get("citations", []),
                "retrieved_count": result.get("retrieved_count", 0),
                "data_source": result.get("data_source", ""),
            }


@app.get("/api/studio/metrics/summary")
async def studio_metrics_summary(
    hours: float = 24.0,
    limit: int = 25,
    x_internal_service_key: str | None = Header(default=None),
) -> dict:
    """GenAI telemetry summary for the admin observability page.

    Aggregates the token / cost / latency / judge-score analytics that Langfuse
    has collected for AI Studio runs, plus a recent-runs list. Read-only; this is
    the studio "using the collected telemetry" to power the in-app single pane.
    Degrades to zeros + an empty list when Langfuse is unconfigured/unreachable.
    """
    _require_internal_key(x_internal_service_key)
    settings = get_settings()
    window = max(0.1, min(float(hours), 168.0))
    summary: dict = {}
    recent: list = []
    langfuse_configured = is_langfuse_enabled()
    try:
        from app.sync.langfuse_apm_sync import collect_analytics, recent_generations

        summary = collect_analytics(hours=window)
        recent = recent_generations(hours=window, limit=max(1, min(int(limit), 100)))
    except Exception as exc:  # pragma: no cover - network/credential dependent
        logger.warning("metrics summary failed: %s", exc)
        summary = {"error": exc.__class__.__name__}

    return {
        "window_hours": window,
        "service_name": settings.otel_service_name,
        "model_id": settings.genai_model_id,
        "langfuse_configured": langfuse_configured,
        "summary": summary,
        "recent": recent,
    }

"""Evidence/RAG agent — grounds the brief in catalog context (+ optional web).

v1 RAG source is the Sales Analyst's category facts plus the request; an LLM
condenses them into evidence bullets. Web search is flag-gated (off by default)
and, when enabled, is a documented integration point rather than a hard dependency.
"""

from __future__ import annotations

import logging

from app.agents.common import call_llm
from app.config import get_settings
from app.observability.tracing import get_tracer
from app.state import StudioState

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an Evidence agent for a drone retailer. Given category sales facts and a "
    "request, produce 3-5 concise, factual bullet points of supporting context a "
    "merchandiser would cite (market positioning, use-case fit, stock posture). "
    "Only use the provided facts. Output bullets, no preamble."
)


def evidence_node(state: StudioState) -> StudioState:
    settings = get_settings()
    tracer = get_tracer()
    with tracer.start_as_current_span("retrieval.evidence") as span:
        span.set_attribute("gen_ai.agent.name", "evidence")
        span.set_attribute("studio.web_search_enabled", settings.web_search_enabled)

        sales = state.get("sales", {})
        facts = _facts_text(sales)
        span.set_attribute("rag.documents", len(sales.get("rows", [])))

        bullets = ""
        usage = {"input": 0, "output": 0}
        try:
            bullets, usage = call_llm(
                agent="evidence",
                operation="chat",
                system_prompt=_SYSTEM,
                user_prompt=f"Request: {state.get('request','')}\n\nCategory facts:\n{facts}",
            )
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("Evidence agent LLM failed: %s", exc)
            span.record_exception(exc)
            bullets = facts

        completed = list(state.get("completed", [])) + ["evidence"]
        return {
            "evidence": {"bullets": bullets, "web_search": settings.web_search_enabled},
            "completed": completed,
            "token_usage": {"input": usage.get("input", 0), "output": usage.get("output", 0)},
        }


def _facts_text(sales: dict) -> str:
    rows = sales.get("rows", [])
    return "\n".join(
        f"- {r.get('category')}: {r.get('units')} units, revenue {r.get('revenue')}" for r in rows
    )

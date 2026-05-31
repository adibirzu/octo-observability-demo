"""Product Copy agent — merchandising copy grounded on sales + evidence."""

from __future__ import annotations

import logging

from app.agents.common import call_llm
from app.observability.tracing import get_tracer
from app.state import StudioState

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a Product Copy writer for OCTO, a drone retailer. Using the category "
    "sales facts and evidence bullets, write merchandising copy: a punchy headline, "
    "a 2-3 sentence positioning paragraph, and 3 short bullet selling points for the "
    "top category. Keep it factual to the data; no invented specs."
)


def product_copy_node(state: StudioState) -> StudioState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.product_copy") as span:
        span.set_attribute("gen_ai.agent.name", "product_copy")
        sales = state.get("sales", {})
        evidence = state.get("evidence", {})
        stats = state.get("chart", {}).get("stats", {})
        prompt = (
            f"Request: {state.get('request','')}\n"
            f"Top category: {stats.get('top_category','(unknown)')} "
            f"({stats.get('top_category_share_pct','?')}% of revenue)\n\n"
            f"Evidence:\n{evidence.get('bullets','')}\n\n"
            f"Category facts:\n"
            + "\n".join(f"- {r.get('category')}: revenue {r.get('revenue')}" for r in sales.get("rows", []))
        )

        copy_text = ""
        usage = {"input": 0, "output": 0}
        try:
            copy_text, usage = call_llm(
                agent="product_copy", operation="chat", system_prompt=_SYSTEM, user_prompt=prompt
            )
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("Product Copy LLM failed: %s", exc)
            span.record_exception(exc)
            copy_text = f"Top category: {stats.get('top_category','')}"

        completed = list(state.get("completed", [])) + ["product_copy"]
        return {
            "copy": {"text": copy_text},
            "completed": completed,
            "token_usage": {"input": usage.get("input", 0), "output": usage.get("output", 0)},
        }

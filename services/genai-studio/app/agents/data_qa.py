"""Data Q&A agent — free-form questions about orders / products / analytics.

A single-agent path (distinct from the multi-agent merchandising brief): the
Data Analyst reads a read-only ATP overview (orders, products, analytics) and an
OCI Generative AI model answers the question grounded ONLY on that data. Traced
with the same span conventions (agent.invoke.* / tool.atp_query / llm.invoke.*)
so a Q&A run is correlatable in OCI APM and Langfuse exactly like a brief run.
"""

from __future__ import annotations

import json
import logging

from app.agents.common import call_llm
from app.db.atp_readonly import data_overview
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the OCTO Drone Shop Data Analyst. Answer the user's question about "
    "orders, products, and sales analytics using ONLY the JSON data provided "
    "(it is a read-only snapshot from the Autonomous Database). Be concise and "
    "specific; cite the numbers. If the data does not contain the answer, say so "
    "plainly — do not invent figures. Stay within drone-shop orders/products/"
    "analytics scope."
)


def answer_data_question(question: str) -> dict:
    """Run the Data Q&A path; return answer + token usage + data-source label."""
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.data_analyst") as span:
        span.set_attribute("gen_ai.agent.name", "data_analyst")
        span.set_attribute("studio.question_length", len(question))

        with tracer.start_as_current_span("tool.atp_query") as tool_span:
            tool_span.set_attribute("db.system", "oracle")
            tool_span.set_attribute("db.operation", "SELECT")
            tool_span.set_attribute("studio.tool", "data_overview")
            overview = data_overview()
            source = overview.get("source", "unknown")
            tool_span.set_attribute("studio.data_source", source)
            if overview.get("fallback_reason"):
                tool_span.set_attribute("studio.data_source.fallback_reason", str(overview["fallback_reason"])[:200])

        # Keep the grounding payload bounded for the prompt.
        grounding = {k: v for k, v in overview.items() if k not in {"source", "fallback_reason"}}
        prompt = (
            f"Question: {question}\n\n"
            f"Data (JSON, read-only from {source}):\n{json.dumps(grounding, default=str)[:4000]}"
        )
        answer, usage = "", {"input": 0, "output": 0}
        try:
            answer, usage = call_llm(
                agent="data_analyst", operation="chat", system_prompt=_SYSTEM, user_prompt=prompt
            )
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("Data Q&A LLM failed: %s", exc)
            span.record_exception(exc)
            answer = "The data assistant is temporarily unavailable. Please retry."

        span.set_attribute("studio.data_source", source)
        span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
        span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))
        return {
            "answer": answer,
            "token_usage": usage,
            "data_source": source,
            "fallback_reason": overview.get("fallback_reason"),
        }

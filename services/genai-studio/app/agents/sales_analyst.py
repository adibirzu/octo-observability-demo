"""Sales Analyst agent — read-only ATP query for category revenue trends."""

from __future__ import annotations

from app.db.atp_readonly import _TOP_CATEGORIES_SQL, top_categories
from app.observability.tracing import get_tracer
from app.state import StudioState


def sales_analyst_node(state: StudioState) -> StudioState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.sales_analyst") as span:
        span.set_attribute("gen_ai.agent.name", "sales_analyst")
        with tracer.start_as_current_span("tool.atp_query") as tool_span:
            # OTEL DB semantic conventions so the query is visible in APM/LA.
            tool_span.set_attribute("db.system", "oracle")
            tool_span.set_attribute("db.operation", "SELECT")
            tool_span.set_attribute("db.statement", _TOP_CATEGORIES_SQL)
            tool_span.set_attribute("studio.tool", "top_categories")
            result = top_categories(limit=5)
            source = result.get("source", "unknown")
            tool_span.set_attribute("db.row_count", len(result.get("rows", [])))
            tool_span.set_attribute("studio.data_source", source)
            # Surface why live ATP was not used (instead of a silent synthetic swap).
            if result.get("fallback_reason"):
                tool_span.set_attribute("studio.data_source.fallback_reason", str(result["fallback_reason"])[:200])
                tool_span.add_event("studio.sales.synthetic_fallback", {"reason": str(result["fallback_reason"])[:200]})

        span.set_attribute("studio.sales.categories", len(result.get("rows", [])))
        span.set_attribute("studio.sales.data_source", source)
        completed = list(state.get("completed", [])) + ["sales_analyst"]
        return {"sales": result, "completed": completed}

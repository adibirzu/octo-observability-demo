"""Sales Analyst agent — read-only ATP query for category revenue trends."""

from __future__ import annotations

from app.db.atp_readonly import top_categories
from app.observability.tracing import get_tracer
from app.state import StudioState


def sales_analyst_node(state: StudioState) -> StudioState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.sales_analyst") as span:
        span.set_attribute("gen_ai.agent.name", "sales_analyst")
        with tracer.start_as_current_span("tool.atp_query") as tool_span:
            tool_span.set_attribute("db.system", "oracle")
            tool_span.set_attribute("db.operation", "SELECT")
            tool_span.set_attribute("studio.tool", "top_categories")
            result = top_categories(limit=5)
            tool_span.set_attribute("db.row_count", len(result.get("rows", [])))
            tool_span.set_attribute("studio.data_source", result.get("source", "unknown"))

        span.set_attribute("studio.sales.categories", len(result.get("rows", [])))
        completed = list(state.get("completed", [])) + ["sales_analyst"]
        return {"sales": result, "completed": completed}

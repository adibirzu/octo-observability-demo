"""Code Interpreter agent — sandboxed trend analysis + chart over sales rows."""

from __future__ import annotations

from app.observability.tracing import get_tracer
from app.sandbox.runner import analyze_sales
from app.state import StudioState


def code_interpreter_node(state: StudioState) -> StudioState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.code_interpreter") as span:
        span.set_attribute("gen_ai.agent.name", "code_interpreter")
        with tracer.start_as_current_span("tool.code_interpreter") as tool_span:
            tool_span.set_attribute("studio.tool", "pandas_matplotlib")
            tool_span.set_attribute("studio.sandbox", "deterministic_local")
            rows = state.get("sales", {}).get("rows", [])
            result = analyze_sales(rows)
            tool_span.set_attribute("studio.chart.computed", bool(result.get("computed")))
            tool_span.set_attribute("studio.chart.has_png", bool(result.get("chart_png_base64")))

        span.set_attribute("studio.code_interpreter.stats", str(result.get("stats", {}))[:200])
        completed = list(state.get("completed", [])) + ["code_interpreter"]
        return {"chart": result, "completed": completed}

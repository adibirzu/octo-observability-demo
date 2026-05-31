"""Presenter agent — assembles the final merchandising brief (markdown)."""

from __future__ import annotations

from app.observability.tracing import get_tracer
from app.state import StudioState


def presenter_node(state: StudioState) -> StudioState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.presenter") as span:
        span.set_attribute("gen_ai.agent.name", "presenter")

        sales = state.get("sales", {})
        evidence = state.get("evidence", {})
        chart = state.get("chart", {})
        copy = state.get("copy", {})
        stats = chart.get("stats", {})

        brief = _assemble(state.get("request", ""), sales, evidence, chart, copy, stats)
        span.set_attribute("studio.brief.length", len(brief))
        span.set_attribute("studio.brief.has_chart", bool(chart.get("chart_png_base64")))

        completed = list(state.get("completed", [])) + ["presenter"]
        return {"brief": brief, "completed": completed, "next_agent": "done"}


def _assemble(request, sales, evidence, chart, copy, stats) -> str:
    lines: list[str] = []
    lines.append(f"# Merchandising Brief\n\n**Request:** {request or '(none)'}\n")
    lines.append(f"_Data source: {sales.get('source', 'unknown')}_\n")

    lines.append("## Sales snapshot\n")
    lines.append("| Category | Units | Revenue | Share |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in chart.get("table") or sales.get("rows", []):
        lines.append(
            f"| {row.get('category')} | {row.get('units','')} | "
            f"{row.get('revenue','')} | {row.get('revenue_share','')}% |"
        )
    if stats:
        lines.append(
            f"\nTop category **{stats.get('top_category','')}** drives "
            f"{stats.get('top_category_share_pct','')}% of revenue across "
            f"{stats.get('category_count','')} categories.\n"
        )

    if evidence.get("bullets"):
        lines.append("## Evidence\n")
        lines.append(evidence["bullets"] + "\n")

    if copy.get("text"):
        lines.append("## Merchandising copy\n")
        lines.append(copy["text"] + "\n")

    if chart.get("chart_png_base64"):
        lines.append("## Chart\n")
        lines.append("_Inline category-revenue chart attached as `chart_png_base64`._\n")

    return "\n".join(lines)

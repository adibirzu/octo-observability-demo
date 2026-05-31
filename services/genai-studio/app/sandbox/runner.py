"""Deterministic trend analysis + chart for the Code Interpreter agent.

v1 runs trusted, repo-owned pandas/matplotlib over the Sales Analyst rows (no
network, no filesystem writes, headless Agg backend). This avoids executing
model-generated code while still demonstrating tool-augmented analysis. The OCI
Responses-API managed sandbox is the hardening upgrade for arbitrary code.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def analyze_sales(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute trend stats and a bar-chart PNG (base64) from category rows."""
    if not rows:
        return {"stats": {}, "chart_png_base64": "", "table": [], "computed": False}

    try:
        import pandas as pd

        df = pd.DataFrame(rows)
        df["revenue"] = pd.to_numeric(df.get("revenue"), errors="coerce").fillna(0.0)
        df["units"] = pd.to_numeric(df.get("units"), errors="coerce").fillna(0).astype(int)
        df = df.sort_values("revenue", ascending=False)

        total_revenue = float(df["revenue"].sum())
        df["revenue_share"] = (df["revenue"] / total_revenue * 100).round(1) if total_revenue else 0.0
        df["avg_unit_revenue"] = (df["revenue"] / df["units"].replace(0, 1)).round(2)

        stats = {
            "total_revenue": round(total_revenue, 2),
            "top_category": str(df.iloc[0]["category"]),
            "top_category_share_pct": float(df.iloc[0]["revenue_share"]),
            "category_count": int(len(df)),
        }
        table = df[
            ["category", "units", "revenue", "revenue_share", "avg_unit_revenue"]
        ].to_dict(orient="records")
        chart_b64 = _render_chart(df)
        return {"stats": stats, "chart_png_base64": chart_b64, "table": table, "computed": True}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Code Interpreter analysis failed: %s", exc)
        return {"stats": {}, "chart_png_base64": "", "table": rows, "computed": False}


def _render_chart(df: Any) -> str:
    import matplotlib

    matplotlib.use("Agg")  # headless — never opens a display
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(df["category"].astype(str), df["revenue"], color="#673ab7")
    ax.set_ylabel("Revenue")
    ax.set_title("Drone category revenue")
    ax.tick_params(axis="x", labelrotation=20, labelsize=8)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=96)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")

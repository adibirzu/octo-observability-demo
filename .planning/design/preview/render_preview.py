#!/usr/bin/env python3
"""WS4c preview harness — render shop Jinja templates to static HTML with a
canned fetch() stub so JS-driven surfaces populate without the backend.

Output goes to shop/server/_preview/<page>.html; serve shop/server with
http.server so /static/* resolves, then screenshot with Playwright.
"""
import json
import pathlib
import sys

import jinja2

REPO = pathlib.Path(__file__).resolve().parents[3]
TPL_DIR = REPO / "shop" / "server" / "templates"
OUT_DIR = REPO / "shop" / "server" / "_preview"
OUT_DIR.mkdir(exist_ok=True)


class Silent(jinja2.Undefined):
    """Undefined that renders empty and is safely iterable/attr-accessible."""

    def __str__(self):
        return ""

    def __iter__(self):
        return iter(())

    def __getattr__(self, _name):
        return Silent()

    def __getitem__(self, _key):
        return Silent()

    def __bool__(self):
        return False

    def __call__(self, *_a, **_k):
        return ""


# Canned API payloads keyed by endpoint substring → injected as a fetch stub.
DASHBOARD_SUMMARY = {
    "products": {"total": 42, "low_stock": 5},
    "orders": {"total": 1284, "revenue": 248900},
    "recent_orders": [
        {"id": 4471, "customer_name": "A. Rivera", "total": 1299, "status": "completed"},
        {"id": 4470, "customer_name": "Demo shopper", "total": 849, "status": "processing"},
        {"id": 4469, "customer_name": "M. Chen", "total": 2150, "status": "delivered"},
        {"id": 4468, "customer_name": "Synthetic QA", "total": 410, "status": "cancelled"},
    ],
    "featured_products": [
        {"name": "Tactical Drone X1", "category": "Drones", "description": "Long-range tactical platform with thermal payload and redundant GPS.", "price": 2499, "stock": 12, "image_url": "/static/img/products/drn_004.jpg"},
        {"name": "Thermal Camera Pod", "category": "Payloads", "description": "High-res thermal imaging module for night operations.", "price": 899, "stock": 7, "image_url": "/static/img/products/cam_001.jpg"},
        {"name": "Field Link Controller", "category": "Control", "description": "Rugged field link controller with encrypted telemetry.", "price": 349, "stock": 20, "image_url": "/static/img/products/flc_001.jpg"},
    ],
}

FETCH_STUB = """<script>
(function () {
  const ROUTES = __ROUTES__;
  const real = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = async function (url, opts) {
    const u = String(url);
    for (const key in ROUTES) {
      if (u.indexOf(key) !== -1) {
        return { ok: true, status: 200, json: async () => ROUTES[key], text: async () => JSON.stringify(ROUTES[key]) };
      }
    }
    if (real) return real(url, opts);
    return { ok: true, status: 200, json: async () => ({}), text: async () => "{}" };
  };
})();
</script>"""

GENAI_METRICS = {
    "summary": {
        "genai_total_tokens": 184200,
        "genai_input_tokens": 120400,
        "genai_output_tokens": 63800,
        "genai_cost_usd": 0.4213,
        "genai_latency_p50_ms": 820,
        "genai_latency_p95_ms": 2140,
        "genai_judge_scores": 36,
        "genai_judge_score_avg": 0.871,
    },
    "recent": [
        {"time": "2026-06-04T14:22:07", "name": "agent.plan", "model": "cohere.command-r-plus", "input_tokens": 1820, "output_tokens": 540, "cost_usd": 0.0041, "latency_ms": 1840, "trace_id": "92fa17c4d9e0b3a1f7"},
        {"time": "2026-06-04T14:19:55", "name": "agent.answer", "model": "meta.llama-3.3-70b", "input_tokens": 2950, "output_tokens": 1120, "cost_usd": 0.0067, "latency_ms": 2210, "trace_id": "4471aa20ffbce81d3c"},
        {"time": "2026-06-04T14:15:31", "name": "judge.score", "model": "cohere.command-r", "input_tokens": 640, "output_tokens": 90, "cost_usd": 0.0008, "latency_ms": 540, "trace_id": "bd09c5e7712a44f0aa"},
    ],
    "langfuse_configured": True,
}

CONTEXT = {
    "title": "Workspace",
    "module": "dashboard",
    "csp_nonce": "preview",
    "rum_configured": False,
    "ai_studio_configured": False,
    "on_admin_host": False,
    "app_name": "OCTO Drone Commerce",
    "java_apm_enabled": False,
    "payment_gateway_simulation_enabled": True,
    # genai_observability.html deep-link targets (rendered as active link-cards)
    "apm_console_url": "#apm",
    "langfuse_url": "#langfuse",
    "grafana_url": "#grafana",
    "genai_command_center_url": "#command-center",
}

ROUTES = {
    "/api/dashboard/summary": DASHBOARD_SUMMARY,
    "/api/ai-studio/metrics": GENAI_METRICS,
}


def render(page: str) -> pathlib.Path:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TPL_DIR)), undefined=Silent, autoescape=True
    )
    html = env.get_template(page).render(**CONTEXT)
    stub = FETCH_STUB.replace("__ROUTES__", json.dumps(ROUTES))
    # Inject the fetch stub right after <body> so it precedes page scripts.
    html = html.replace("<body>", "<body>\n" + stub, 1)
    out = OUT_DIR / page
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    pages = sys.argv[1:] or ["dashboard.html"]
    for p in pages:
        path = render(p)
        print(f"rendered {p} -> {path.relative_to(REPO)}")

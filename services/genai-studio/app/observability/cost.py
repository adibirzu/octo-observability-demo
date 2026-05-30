"""Per-model token-cost estimation + a span processor that stamps cost on LLM spans.

Ported in spirit from oci-coordinator-oke's CostEnrichmentSpanProcessor: when an
LLM span ends carrying ``gen_ai.usage.input_tokens`` / ``output_tokens`` but no
cost, compute ``gen_ai.usage.cost_usd`` from per-model rates so OCI APM and
Langfuse both show cost without the call site having to know rates.
"""

from __future__ import annotations

import os

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

# USD per 1K tokens: (input_rate, output_rate). Substring-matched against the
# model id. Extend as models are added; unknown models cost 0 (never crash).
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "cohere.command-r-plus": (0.0030, 0.0150),
    "cohere.command-r": (0.0005, 0.0015),
    "meta.llama-3.3-70b": (0.00072, 0.00072),
    "meta.llama-3.1-405b": (0.0036, 0.0036),
    "meta.llama": (0.00072, 0.00072),
    "google.gemini-2.5-pro": (0.00125, 0.0050),
    "google.gemini-2.5-flash": (0.000075, 0.0003),
    "google.gemini": (0.000075, 0.0003),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD estimate from token counts; 0.0 for unknown models."""
    model_l = (model or "").lower()
    for name, (in_rate, out_rate) in MODEL_COSTS.items():
        if name in model_l:
            return round((input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate, 6)
    return 0.0


class CostEnrichmentSpanProcessor(SpanProcessor):
    """Stamp gen_ai.usage.cost_usd on LLM spans at end, from token counts."""

    _ENABLED = os.getenv("STUDIO_COST_ENRICHMENT", "true").lower() not in {"0", "false", "no"}

    def on_start(self, span, parent_context=None) -> None:  # noqa: D401
        return

    def on_end(self, span: ReadableSpan) -> None:
        if not self._ENABLED:
            return
        attrs = span.attributes or {}
        if "gen_ai.usage.cost_usd" in attrs:
            return
        model = attrs.get("gen_ai.request.model") or attrs.get("gen_ai.response.model")
        if not model:
            return
        in_tok = attrs.get("gen_ai.usage.input_tokens")
        out_tok = attrs.get("gen_ai.usage.output_tokens")
        if in_tok is None and out_tok is None:
            return
        cost = estimate_cost_usd(str(model), int(in_tok or 0), int(out_tok or 0))
        # ReadableSpan in on_end is read-only via .attributes, but the underlying
        # span object still accepts set_attribute before export completes.
        try:
            span._attributes["gen_ai.usage.cost_usd"] = cost  # type: ignore[attr-defined]
        except Exception:
            pass

    def shutdown(self) -> None:
        return

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

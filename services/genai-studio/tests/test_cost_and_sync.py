"""Phase 3: cost estimation, cost-enrichment span processor, and Langfuse->APM sync."""

from __future__ import annotations

import pytest

from app.observability.cost import CostEnrichmentSpanProcessor, estimate_cost_usd


@pytest.mark.unit
def test_estimate_cost_known_model():
    # meta.llama-3.3-70b: 0.00072/1k in+out
    cost = estimate_cost_usd("meta.llama-3.3-70b-instruct", 1000, 1000)
    assert cost == pytest.approx(0.00144, rel=1e-3)


@pytest.mark.unit
def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost_usd("some.unknown-model", 1000, 5000) == 0.0


@pytest.mark.unit
def test_estimate_cost_zero_tokens():
    assert estimate_cost_usd("cohere.command-r-08-2024", 0, 0) == 0.0


class _FakeSpan:
    def __init__(self, attributes):
        self.attributes = attributes
        self._attributes = dict(attributes)


@pytest.mark.unit
def test_cost_processor_stamps_cost_on_llm_span():
    proc = CostEnrichmentSpanProcessor()
    span = _FakeSpan(
        {
            "gen_ai.request.model": "meta.llama-3.3-70b-instruct",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 1000,
        }
    )
    proc.on_end(span)
    assert span._attributes["gen_ai.usage.cost_usd"] == pytest.approx(0.00144, rel=1e-3)


@pytest.mark.unit
def test_cost_processor_ignores_non_llm_span():
    proc = CostEnrichmentSpanProcessor()
    span = _FakeSpan({"http.method": "GET"})
    proc.on_end(span)
    assert "gen_ai.usage.cost_usd" not in span._attributes


@pytest.mark.unit
def test_collect_analytics_handles_no_langfuse(monkeypatch):
    # With Langfuse unconfigured, _langfuse_get returns None -> empty aggregates.
    from app.sync import langfuse_apm_sync as sync

    monkeypatch.setattr(sync, "_langfuse_get", lambda *a, **k: None)
    metrics = sync.collect_analytics(hours=1.0)
    assert metrics["genai_total_tokens"] == 0.0
    assert metrics["genai_cost_usd"] == 0.0
    assert metrics["genai_generations"] == 0.0


@pytest.mark.unit
def test_collect_analytics_aggregates_observations(monkeypatch):
    from app.sync import langfuse_apm_sync as sync

    def fake_get(path, params=None):
        if "observations" in path:
            return {
                "data": [
                    {"model": "meta.llama-3.3-70b", "usage": {"input": 100, "output": 50}, "latency": 1200},
                    {"model": "meta.llama-3.3-70b", "usage": {"input": 200, "output": 80},
                     "calculatedTotalCost": 0.5, "latency": 800},
                ]
            }
        if "scores" in path:
            return {"data": [{"value": 4}, {"value": 5}]}
        return None

    monkeypatch.setattr(sync, "_langfuse_get", fake_get)
    m = sync.collect_analytics(hours=1.0)
    assert m["genai_input_tokens"] == 300.0
    assert m["genai_output_tokens"] == 130.0
    assert m["genai_total_tokens"] == 430.0
    assert m["genai_generations"] == 2.0
    assert m["genai_cost_usd"] > 0.5  # 0.5 explicit + estimated for the first obs
    assert m["genai_judge_score_avg"] == pytest.approx(4.5)
    assert m["genai_judge_scores"] == 2.0

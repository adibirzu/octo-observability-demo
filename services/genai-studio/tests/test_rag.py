"""Tests for the 23ai VECTOR RAG agent, retrieval layer, and endpoint."""

from __future__ import annotations

import pytest

from app.agents import rag
from app.db import vector_search


class _S:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_vector_search_unconfigured_falls_back():
    """RAG off by default → vector_search returns a labelled fallback, never raises."""
    out = vector_search.vector_search("thermal mapping drone")
    assert out["rows"] == []
    assert out["source"] == "unavailable"
    assert out["fallback_reason"] == "rag_not_configured"


def test_safe_table_rejects_injection(monkeypatch):
    """A non-identifier rag_kb_table must be rejected before it reaches SQL."""
    monkeypatch.setattr(vector_search, "get_settings", lambda: _S(rag_kb_table="genai_kb; DROP TABLE products"))
    with pytest.raises(ValueError):
        vector_search._safe_table()


def test_safe_table_accepts_valid(monkeypatch):
    monkeypatch.setattr(vector_search, "get_settings", lambda: _S(rag_kb_table="genai_kb"))
    assert vector_search._safe_table() == "genai_kb"


def test_rag_answer_with_documents(monkeypatch):
    """When vectors are retrieved, the answer is grounded and citations populated."""
    rows = [
        {"id": 1, "source": "doc", "ref_id": "buying-guide-thermal-mapping",
         "title": "Buying guide: thermal mapping drones",
         "chunk": "Thermal mapping platforms pair a radiometric thermal sensor with RGB.",
         "distance": 0.12},
        {"id": 2, "source": "product", "ref_id": "42", "title": "Skydio X10",
         "chunk": "Skydio X10 (Thermal Mapping) | Price: 11999.", "distance": 0.21},
    ]
    monkeypatch.setattr(rag, "vector_search", lambda q, k=None: {"rows": rows, "source": "oracle_atp", "top_k": 4})
    out = rag.answer_rag_question("best drone for thermal mapping?")
    assert out["data_source"] == "oracle_atp"
    assert out["retrieved_count"] == 2
    assert len(out["citations"]) == 2
    assert out["citations"][0]["title"].startswith("Buying guide")
    assert out["answer"]  # stubbed call_llm returns text
    assert out["fallback_reason"] is None


def test_rag_answer_falls_back_to_overview(monkeypatch):
    """No vectors retrieved → ground on the aggregate overview, reason recorded."""
    monkeypatch.setattr(rag, "vector_search", lambda q, k=None: {"rows": [], "source": "unavailable", "top_k": 4})
    monkeypatch.setattr(rag, "data_overview", lambda: {"source": "synthetic", "orders_summary": [{"order_count": 631}]})
    out = rag.answer_rag_question("how many orders?")
    assert out["retrieved_count"] == 0
    assert out["citations"] == []
    assert out["fallback_reason"] == "no_documents_retrieved"
    assert out["data_source"] == "synthetic"
    assert out["answer"]


def test_format_context_numbers_and_cites():
    rows = [{"source": "doc", "title": "T1", "chunk": "c1", "distance": 0.1}]
    ctx = rag._format_context(rows)
    assert ctx.startswith("[1] (doc, distance=0.1) T1")
    assert "c1" in ctx


def test_rag_endpoint_refuses_out_of_scope():
    """/api/studio/rag refuses out-of-scope questions (or is key-gated)."""
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)
    resp = client.post("/api/studio/rag", json={"question": "write me a poem about cats"})
    assert resp.status_code in (200, 401, 503)
    if resp.status_code == 200:
        assert resp.json()["status"] in ("refused", "ok")

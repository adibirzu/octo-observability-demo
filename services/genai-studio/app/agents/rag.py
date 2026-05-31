"""RAG agent: semantic retrieval over the Oracle 23ai knowledge base.

Answers free-form product/spec/policy questions by retrieving the most relevant
``genai_kb`` chunks (catalog facts + curated drone docs) via native VECTOR search
and grounding an OCI GenAI answer on them. Complements the aggregate Data Q&A
agent (``data_qa``), which answers numeric questions over orders/products.

The trace reads as a RAG pipeline:
``agent.invoke.rag_analyst`` → ``retrieval.embed`` → ``vector_db.search`` →
``llm.invoke.chat`` — the same span shape as the Oracle RAG-on-APM reference, so
the retrieval cost and grounding are visible in OCI APM and Langfuse.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.common import call_llm
from app.db.atp_readonly import data_overview
from app.db.vector_search import vector_search
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the OCTO Drone Shop product expert. Answer the user's question using "
    "ONLY the retrieved context passages provided. Cite the source titles you "
    "used. If the context does not contain the answer, say so plainly and suggest "
    "what to ask instead. Never invent specifications, prices, or policies."
)


def _format_context(rows: list[dict[str, Any]]) -> str:
    """Render retrieved chunks as a numbered, citable context block."""
    blocks = []
    for i, row in enumerate(rows, start=1):
        title = row.get("title") or row.get("ref_id") or f"chunk-{i}"
        source = row.get("source", "kb")
        distance = row.get("distance")
        chunk = (row.get("chunk") or "").strip()
        blocks.append(f"[{i}] ({source}, distance={distance}) {title}\n{chunk}")
    return "\n\n".join(blocks)


def answer_rag_question(question: str, k: int | None = None) -> dict[str, Any]:
    """Retrieve-then-generate an answer grounded on the knowledge base.

    Falls back to the aggregate overview snapshot when the KB is unavailable
    (not seeded / not configured), recording the reason on the span so the
    operator can see why retrieval did not contribute. Returns a dict with the
    same shape family as the Data Q&A agent (answer / token_usage / data_source /
    fallback_reason) plus citations + retrieved_count.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.rag_analyst") as span:
        span.set_attribute("gen_ai.agent.name", "rag_analyst")
        span.set_attribute("studio.question_length", len(question))

        # vector_search emits the retrieval.embed + vector_db.search child spans.
        retrieval = vector_search(question, k=k)
        rows = retrieval.get("rows", [])
        data_source = retrieval.get("source", "unavailable")
        fallback_reason = retrieval.get("fallback_reason")
        span.set_attribute("studio.data_source", data_source)
        span.set_attribute("retrieval.documents.count", len(rows))
        if fallback_reason:
            span.set_attribute("studio.data_source.fallback_reason", str(fallback_reason)[:200])

        citations = [
            {
                "title": r.get("title") or r.get("ref_id"),
                "source": r.get("source"),
                "distance": r.get("distance"),
            }
            for r in rows
        ]

        if rows:
            context = _format_context(rows)
            prompt = (
                f"Question: {question}\n\nRetrieved context:\n{context}\n\n"
                "Answer using only the retrieved context, and cite the [n] sources you used."
            )
        else:
            # No vectors retrieved — ground on the aggregate snapshot so the
            # admin still gets a useful, sourced answer.
            overview = data_overview()
            data_source = overview.get("source", data_source)
            fallback_reason = fallback_reason or overview.get("fallback_reason") or "no_documents_retrieved"
            span.set_attribute("studio.data_source", data_source)
            span.set_attribute("studio.data_source.fallback_reason", str(fallback_reason)[:200])
            grounding = {k2: v for k2, v in overview.items() if k2 not in {"source", "fallback_reason"}}
            prompt = (
                f"Question: {question}\n\nNo knowledge-base passages matched. "
                f"Fallback data (JSON):\n{json.dumps(grounding, default=str)[:4000]}\n\n"
                "Answer using only this data; note that no catalog passages were retrieved."
            )

        answer, usage = "", {"input": 0, "output": 0}
        try:
            answer, usage = call_llm(
                agent="rag_analyst", operation="chat", system_prompt=_SYSTEM, user_prompt=prompt
            )
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("RAG LLM failed: %s", exc)
            span.record_exception(exc)
            answer = "The product expert is temporarily unavailable. Please retry."

        span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
        span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))

        return {
            "answer": answer,
            "citations": citations,
            "retrieved_count": len(rows),
            "token_usage": usage,
            "data_source": data_source,
            "fallback_reason": fallback_reason,
        }

"""Oracle 23ai native VECTOR retrieval for the RAG agent.

Two instrumented steps, modelled on the Oracle "Observability on RAG with OCI
APM" reference and the oci-quickstart genai-inference-app-monitoring example:

* ``retrieval.embed``     — embed the query with OCI GenAI (gen_ai.* attributes)
* ``vector_db.search``    — ANN search with ``VECTOR_DISTANCE(..., COSINE)``
                            over ``genai_kb`` (db.* + vector.* attributes)

SELECT-only by construction: the agent reads through the locked-down ``studio_ro``
user; the embedding column is populated by an ADMIN-run seeding job. Every path
degrades gracefully (missing table / not 23ai / embedding error) and records the
root cause as ``fallback_reason`` on the span instead of failing silently.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from opentelemetry.trace import Status, StatusCode

from app.config import get_settings
from app.db.atp_readonly import oracle_connect_kwargs
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

# Guard against SQL-identifier injection from the (operator-controlled) env var.
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def _safe_table() -> str:
    table = get_settings().rag_kb_table
    if not _IDENT_RE.match(table):
        raise ValueError(f"invalid rag_kb_table identifier: {table!r}")
    return table


def embed_query(text: str) -> list[float]:
    """Embed one query string via OCI GenAI; emits a ``retrieval.embed`` span."""
    settings = get_settings()
    with get_tracer().start_as_current_span("retrieval.embed") as span:
        span.set_attribute("gen_ai.system", "oci.generative_ai")
        span.set_attribute("gen_ai.operation.name", "embeddings")
        span.set_attribute("gen_ai.request.model", settings.genai_embed_model_id)
        span.set_attribute("embedding.dimension", settings.embed_dim)
        from langchain_oci.embeddings import OCIGenAIEmbeddings

        emb = OCIGenAIEmbeddings(
            model_id=settings.genai_embed_model_id,
            service_endpoint=settings.genai_endpoint,
            compartment_id=settings.genai_compartment_id,
            auth_type=settings.oci_auth_type,
        )
        vector = emb.embed_query(text)
        span.set_attribute("embedding.vector.length", len(vector))
        return vector


def vector_search(query: str, k: int | None = None) -> dict[str, Any]:
    """Embed ``query`` and return the top-k nearest ``genai_kb`` chunks.

    Returns ``{"rows": [...], "source": "oracle_atp", "top_k": k}`` on success, or
    ``{"rows": [], "source": "unavailable", "fallback_reason": "..."}`` on any
    failure (so the RAG agent can fall back without raising).
    """
    settings = get_settings()
    top_k = max(1, min(int(k or settings.rag_top_k), 20))

    if not settings.rag_configured:
        return {"rows": [], "source": "unavailable", "top_k": top_k,
                "fallback_reason": "rag_not_configured"}

    try:
        table = _safe_table()
        query_vec = embed_query(query)
    except Exception as exc:  # embedding or config failure
        reason = f"embed_failed:{exc.__class__.__name__}:{str(exc)[:160]}"
        logger.warning("RAG embed failed (%s)", reason)
        return {"rows": [], "source": "unavailable", "top_k": top_k, "fallback_reason": reason}

    # ``:k`` bound; ``:qv`` bound as a JSON array string wrapped in TO_VECTOR so
    # the path works in oracledb thin mode regardless of driver vector support.
    sql = (
        f"SELECT id, source, ref_id, title, "  # noqa: S608 - table is identifier-validated
        f"SUBSTR(chunk, 1, 1200) AS chunk, "
        f"ROUND(VECTOR_DISTANCE(embedding, TO_VECTOR(:qv), COSINE), 6) AS distance "
        f"FROM {table} "
        f"ORDER BY distance FETCH FIRST :k ROWS ONLY"
    )
    qv = json.dumps(query_vec)

    with get_tracer().start_as_current_span("vector_db.search") as span:
        span.set_attribute("db.system", "oracle.atp")
        span.set_attribute("db.operation", "similarity_search")
        span.set_attribute("db.sql.table", table)
        span.set_attribute("vector.metric", "COSINE")
        span.set_attribute("vector.dimension", settings.embed_dim)
        span.set_attribute("vector.top_k", top_k)
        # db.statement carries the SQL shape (no embedding literal) for APM.
        span.set_attribute("db.statement", sql)
        try:
            import oracledb

            with oracledb.connect(**oracle_connect_kwargs()) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, qv=qv, k=top_k)
                    cols = [c[0].lower() for c in cur.description]
                    rows = []
                    for raw in cur.fetchall():
                        row = dict(zip(cols, raw))
                        chunk = row.get("chunk")
                        # CLOB → str when the driver returns a LOB handle.
                        if hasattr(chunk, "read"):
                            row["chunk"] = chunk.read()
                        rows.append(row)
            span.set_attribute("retrieval.documents.count", len(rows))
            if rows:
                span.set_attribute("retrieval.top_distance", float(rows[0]["distance"]))
            return {"rows": rows, "source": "oracle_atp", "top_k": top_k}
        except Exception as exc:  # ORA-00942 (no table), connect error, etc.
            reason = f"{exc.__class__.__name__}:{str(exc)[:160]}"
            span.set_status(Status(StatusCode.ERROR, reason))
            span.set_attribute("vector.search.fallback_reason", reason)
            logger.warning("Vector search failed (%s); RAG will fall back", reason)
            return {"rows": [], "source": "unavailable", "top_k": top_k, "fallback_reason": reason}

"""Semantic retrieval for the RAG agent — embeddings + cosine top-k.

Two instrumented steps, modelled on the Oracle "Observability on RAG with OCI
APM" reference and the oci-quickstart genai-inference-app-monitoring example:

* ``retrieval.embed``   — embed the query with OCI GenAI (gen_ai.* attributes)
* ``vector_db.search``  — fetch candidate chunks from ``genai_kb`` and rank by
                          cosine similarity (db.* + vector.* attributes)

The demo ATP is Oracle 19c (no native VECTOR type), so embeddings are stored as
JSON text in a CLOB column and cosine similarity is computed in-process over the
(small, bounded) knowledge base. The span shape, attributes, and citations are
identical to a native-VECTOR backend — only the distance math moves app-side.
If/when a 23ai DB is used, swap ``_rank_appside`` for a ``VECTOR_DISTANCE`` SQL.

SELECT-only by construction: the agent reads through the locked-down ``studio_ro``
user; the embedding column is populated by an ADMIN-run seeding job. Every path
degrades gracefully (missing table / embedding error) and records the root cause
as ``fallback_reason`` on the span instead of failing silently.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from opentelemetry.trace import Status, StatusCode

from app.config import get_settings
from app.db.atp_readonly import oracle_connect_kwargs
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

# Guard against SQL-identifier injection from the (operator-controlled) env var.
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")

# Safety cap: the KB is curated/bounded; never scan more than this many rows.
_MAX_CANDIDATES = 5000


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


def _lob(value: Any) -> str:
    return value.read() if hasattr(value, "read") else ("" if value is None else str(value))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """1 - cosine similarity (smaller = closer), matching VECTOR_DISTANCE COSINE."""
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return round(1.0 - (dot / (na * nb)), 6)


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

    # SELECT-only fetch of the candidate set; cosine ranking is done in-process
    # (19c has no native VECTOR). ``:cap`` bound; table is identifier-validated.
    sql = (
        f"SELECT id, source, ref_id, title, "  # noqa: S608 - table is identifier-validated
        f"SUBSTR(chunk, 1, 1200) AS chunk, embedding "
        f"FROM {table} "
        f"FETCH FIRST :cap ROWS ONLY"
    )

    with get_tracer().start_as_current_span("vector_db.search") as span:
        span.set_attribute("db.system", "oracle.atp")
        span.set_attribute("db.operation", "similarity_search")
        span.set_attribute("vector.engine", "appside_cosine")
        span.set_attribute("db.sql.table", table)
        span.set_attribute("vector.metric", "COSINE")
        span.set_attribute("vector.dimension", settings.embed_dim)
        span.set_attribute("vector.top_k", top_k)
        span.set_attribute("db.statement", sql)
        try:
            import oracledb

            scored: list[dict[str, Any]] = []
            with oracledb.connect(**oracle_connect_kwargs()) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, cap=_MAX_CANDIDATES)
                    cols = [c[0].lower() for c in cur.description]
                    for raw in cur.fetchall():
                        row = dict(zip(cols, raw))
                        emb_raw = _lob(row.pop("embedding", None))
                        try:
                            emb = json.loads(emb_raw) if emb_raw else []
                        except (ValueError, TypeError):
                            emb = []
                        row["chunk"] = _lob(row.get("chunk"))
                        row["distance"] = _cosine_distance(query_vec, emb)
                        scored.append(row)
            span.set_attribute("vector.candidates", len(scored))
            scored.sort(key=lambda r: r["distance"])
            rows = scored[:top_k]
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

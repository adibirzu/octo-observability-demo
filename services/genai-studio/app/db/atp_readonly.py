"""Read-only catalog/sales queries for the Sales Analyst agent.

SELECT-only by construction: queries are module-level constants with bound
parameters, executed against a read-only DB user. Supports Oracle ATP (oracledb)
and a Postgres fallback for the local docker-compose stack. When no DB is
configured the agent falls back to a deterministic synthetic dataset so the demo
and tests run without a database.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Top categories by revenue. ``:lim`` bound parameter, no string interpolation.
_TOP_CATEGORIES_SQL = (
    "SELECT p.category AS category, "
    "COUNT(oi.id) AS units, "
    "SUM(oi.quantity * oi.unit_price) AS revenue "
    "FROM order_items oi JOIN products p ON p.id = oi.product_id "
    "GROUP BY p.category ORDER BY revenue DESC FETCH FIRST :lim ROWS ONLY"
)
_TOP_CATEGORIES_SQL_PG = (
    "SELECT p.category AS category, "
    "COUNT(oi.id) AS units, "
    "SUM(oi.quantity * oi.unit_price) AS revenue "
    "FROM order_items oi JOIN products p ON p.id = oi.product_id "
    "GROUP BY p.category ORDER BY revenue DESC LIMIT %(lim)s"
)

_SYNTHETIC = {
    "rows": [
        {"category": "Thermal Mapping", "units": 184, "revenue": 742000.0},
        {"category": "Survey / RTK", "units": 152, "revenue": 611500.0},
        {"category": "Public Safety", "units": 121, "revenue": 489250.0},
        {"category": "Cinema / FPV", "units": 98, "revenue": 270400.0},
        {"category": "Agriculture", "units": 76, "revenue": 198300.0},
    ],
    "source": "synthetic",
}

# Read-only summary queries for the free-form Data Q&A agent. SELECT-only, no
# string interpolation; each returns a single summary row the LLM grounds on.
# Oracle (ATP) variants; Postgres variants differ only in row-limit syntax.
_DATA_QUERIES = {
    "orders_summary": (
        "SELECT COUNT(*) AS order_count, "
        "NVL(SUM(total_amount),0) AS total_revenue, "
        "NVL(AVG(total_amount),0) AS avg_order_value, "
        "MAX(created_at) AS latest_order "
        "FROM orders"
    ),
    "orders_by_status": (
        "SELECT status, COUNT(*) AS orders, NVL(SUM(total_amount),0) AS revenue "
        "FROM orders GROUP BY status ORDER BY orders DESC"
    ),
    "product_summary": (
        "SELECT COUNT(*) AS product_count, "
        "SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) AS active_products, "
        "SUM(CASE WHEN stock < 10 THEN 1 ELSE 0 END) AS low_stock, "
        "NVL(AVG(price),0) AS avg_price "
        "FROM products"
    ),
    "top_products": (
        "SELECT p.name, p.category, p.price, p.stock, "
        "NVL(SUM(oi.quantity),0) AS units_sold "
        "FROM products p LEFT JOIN order_items oi ON oi.product_id = p.id "
        "GROUP BY p.name, p.category, p.price, p.stock "
        "ORDER BY units_sold DESC FETCH FIRST 10 ROWS ONLY"
    ),
}
_DATA_QUERIES_PG = {
    **_DATA_QUERIES,
    "top_products": (
        "SELECT p.name, p.category, p.price, p.stock, "
        "COALESCE(SUM(oi.quantity),0) AS units_sold "
        "FROM products p LEFT JOIN order_items oi ON oi.product_id = p.id "
        "GROUP BY p.name, p.category, p.price, p.stock "
        "ORDER BY units_sold DESC LIMIT 10"
    ),
}

_SYNTHETIC_OVERVIEW = {
    "orders_summary": [{"order_count": 631, "total_revenue": 2311450.0, "avg_order_value": 3663.2, "latest_order": "synthetic"}],
    "orders_by_status": [
        {"status": "completed", "orders": 488, "revenue": 1894200.0},
        {"status": "processing", "orders": 92, "revenue": 312050.0},
        {"status": "cancelled", "orders": 51, "revenue": 105200.0},
    ],
    "product_summary": [{"product_count": 52, "active_products": 50, "low_stock": 7, "avg_price": 4120.5}],
    "top_products": [
        {"name": "Skydio X10", "category": "Thermal Mapping", "price": 11999, "stock": 14, "units_sold": 71},
        {"name": "WingtraOne GEN II", "category": "Survey / RTK", "price": 23000, "stock": 6, "units_sold": 44},
    ],
    "source": "synthetic",
}


def _query_oracle(limit: int) -> list[dict[str, Any]]:
    import oracledb  # local import keeps the dependency optional

    settings = get_settings()
    # Thin mode (no Instant Client in the slim image): connect to ATP with the
    # wallet via config_dir/wallet_location + wallet_password (mTLS).
    connect_kwargs: dict[str, Any] = {
        "user": settings.db_user,
        "password": settings.db_password,
        "dsn": settings.db_dsn,
    }
    if settings.oracle_wallet_dir:
        connect_kwargs["config_dir"] = settings.oracle_wallet_dir
        connect_kwargs["wallet_location"] = settings.oracle_wallet_dir
    if settings.oracle_wallet_password:
        connect_kwargs["wallet_password"] = settings.oracle_wallet_password
    with oracledb.connect(**connect_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(_TOP_CATEGORIES_SQL, lim=limit)
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _query_postgres(limit: int) -> list[dict[str, Any]]:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore

    settings = get_settings()
    with psycopg2.connect(settings.db_dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_TOP_CATEGORIES_SQL_PG, {"lim": limit})
            return [dict(row) for row in cur.fetchall()]


def top_categories(limit: int = 5) -> dict[str, Any]:
    """Return top product categories by revenue with the data source label.

    On any failure the synthetic dataset is returned, but the root cause is
    logged AND returned as ``fallback_reason`` so the Sales Analyst span and the
    operator can see *why* live ATP data was not used (instead of a silent swap).
    """
    settings = get_settings()
    safe_limit = max(1, min(int(limit), 20))
    if settings.db_kind in {"oracle", "postgres"} and not settings.db_configured:
        logger.warning(
            "STUDIO_DB_KIND=%s but DB is not fully configured (dsn/user/password missing); "
            "using synthetic data",
            settings.db_kind,
        )
        return {**_SYNTHETIC, "fallback_reason": "db_not_configured"}
    try:
        if settings.db_kind == "oracle" and settings.db_configured:
            return {"rows": _query_oracle(safe_limit), "source": "oracle_atp"}
        if settings.db_kind == "postgres" and settings.db_configured:
            return {"rows": _query_postgres(safe_limit), "source": "postgres"}
    except Exception as exc:  # pragma: no cover - falls back to synthetic
        reason = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        logger.warning("Sales query failed (%s); using synthetic data", reason)
        return {**_SYNTHETIC, "fallback_reason": reason}
    return _SYNTHETIC


def _run_select(sql: str, pg: bool) -> list[dict[str, Any]]:
    """Execute one read-only SELECT and return rows as dicts."""
    settings = get_settings()
    if pg:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore

        with psycopg2.connect(settings.db_dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
    import oracledb

    connect_kwargs: dict[str, Any] = {
        "user": settings.db_user,
        "password": settings.db_password,
        "dsn": settings.db_dsn,
    }
    if settings.oracle_wallet_dir:
        connect_kwargs["config_dir"] = settings.oracle_wallet_dir
        connect_kwargs["wallet_location"] = settings.oracle_wallet_dir
    if settings.oracle_wallet_password:
        connect_kwargs["wallet_password"] = settings.oracle_wallet_password
    with oracledb.connect(**connect_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def data_overview() -> dict[str, Any]:
    """Read-only orders + products + analytics summary for the Data Q&A agent.

    Returns a dict of named result sets (orders_summary, orders_by_status,
    product_summary, top_products) + a `source` label. Falls back to a
    deterministic synthetic overview (with `fallback_reason`) on any failure, so
    Q&A degrades gracefully and the reason is visible on the span.
    """
    settings = get_settings()
    if not (settings.db_kind in {"oracle", "postgres"} and settings.db_configured):
        return {**_SYNTHETIC_OVERVIEW, "fallback_reason": "db_not_configured"}
    pg = settings.db_kind == "postgres"
    queries = _DATA_QUERIES_PG if pg else _DATA_QUERIES
    try:
        result = {name: _run_select(sql, pg) for name, sql in queries.items()}
        result["source"] = "oracle_atp" if not pg else "postgres"
        return result
    except Exception as exc:  # pragma: no cover - graceful fallback
        reason = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        logger.warning("Data overview query failed (%s); using synthetic", reason)
        return {**_SYNTHETIC_OVERVIEW, "fallback_reason": reason}

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

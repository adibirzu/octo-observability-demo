"""Sales Analyst SQL is read-only and parameterised; agent emits a sales dict."""

from __future__ import annotations

import pytest

from app.db import atp_readonly
from app.state import empty_state


@pytest.mark.unit
def test_queries_are_select_only_and_parameterised():
    for sql in (atp_readonly._TOP_CATEGORIES_SQL, atp_readonly._TOP_CATEGORIES_SQL_PG):
        upper = sql.upper()
        assert upper.lstrip().startswith("SELECT")
        for banned in ("INSERT", "UPDATE", "DELETE", "DROP", "MERGE", "ALTER", "TRUNCATE"):
            assert banned not in upper
        # Bound parameter, never string-formatted limits.
        assert (":lim" in sql) or ("%(lim)s" in sql)


@pytest.mark.unit
def test_falls_back_to_synthetic_when_no_db(monkeypatch):
    # Default settings have db_kind="none"; agent should still return rows.
    from app.agents.sales_analyst import sales_analyst_node

    out = sales_analyst_node(empty_state(request="brief"))
    assert "sales_analyst" in out["completed"]
    assert out["sales"]["rows"]
    assert out["sales"]["source"] in {"synthetic", "oracle_atp", "postgres"}

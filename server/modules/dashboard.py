"""Dashboard module — provides analytics and overview data.

Also includes performance simulation endpoints for APM testing.
"""

import asyncio
import time
import random

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log
from server.database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
tracer_fn = get_tracer


@router.get("/summary")
async def dashboard_summary(request: Request):
    """Dashboard summary with multiple DB queries — demonstrates span depth."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.summary") as span:
        async with get_db() as db:
            # Span: customer count
            with tracer.start_as_current_span("db.query.customer_count"):
                r = await db.execute(text("SELECT count(*) FROM customers"))
                customer_count = r.scalar()

            # Span: order stats
            with tracer.start_as_current_span("db.query.order_stats"):
                r = await db.execute(text(
                    "SELECT count(*), COALESCE(sum(total), 0), "
                    "COALESCE(avg(total), 0) FROM orders"
                ))
                row = r.fetchone()
                order_count, total_revenue, avg_order = row if row else (0, 0, 0)

            # Span: ticket stats
            with tracer.start_as_current_span("db.query.ticket_stats"):
                r = await db.execute(text(
                    "SELECT status, count(*) FROM support_tickets GROUP BY status"
                ))
                ticket_stats = {row[0]: row[1] for row in r.fetchall()}

            # Span: invoice stats
            with tracer.start_as_current_span("db.query.invoice_stats"):
                r = await db.execute(text(
                    "SELECT status, count(*), COALESCE(sum(amount), 0) "
                    "FROM invoices GROUP BY status"
                ))
                invoice_stats = [
                    {"status": row[0], "count": row[1], "total": float(row[2])}
                    for row in r.fetchall()
                ]

            # Span: top customers
            with tracer.start_as_current_span("db.query.top_customers"):
                r = await db.execute(text(
                    "SELECT c.name, c.revenue, count(o.id) as order_count "
                    "FROM customers c LEFT JOIN orders o ON c.id = o.customer_id "
                    "GROUP BY c.id, c.name, c.revenue ORDER BY c.revenue DESC LIMIT 5"
                ))
                top_customers = [dict(row._mapping) for row in r.fetchall()]

            # Span: recent orders
            with tracer.start_as_current_span("db.query.recent_orders"):
                r = await db.execute(text(
                    "SELECT o.id, o.total, o.status, o.created_at, c.name as customer_name "
                    "FROM orders o LEFT JOIN customers c ON o.customer_id = c.id "
                    "ORDER BY o.created_at DESC LIMIT 10"
                ))
                recent_orders = [dict(row._mapping) for row in r.fetchall()]

        return {
            "customers": {"total": customer_count},
            "orders": {
                "total": order_count,
                "revenue": float(total_revenue),
                "average": float(avg_order),
            },
            "tickets": ticket_stats,
            "invoices": invoice_stats,
            "top_customers": top_customers,
            "recent_orders": recent_orders,
        }


@router.get("/slow-query")
async def slow_query(
    request: Request,
    delay: float = Query(default=2.0, description="Simulated delay in seconds"),
):
    """Deliberate slow endpoint for APM threshold testing."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.slow_query") as span:
        span.set_attribute("performance.simulated_delay", delay)
        await asyncio.sleep(min(delay, 30.0))  # cap at 30s

        push_log("WARNING", "Slow query endpoint invoked", **{
            "performance.delay_seconds": delay,
            "performance.endpoint": "/api/dashboard/slow-query",
        })
        return {"status": "ok", "delay": delay}


@router.get("/n-plus-one")
async def n_plus_one_demo(request: Request):
    """Demonstrates N+1 query problem — visible as many DB spans in trace."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.n_plus_one") as span:
        async with get_db() as db:
            # First query: get all customers
            with tracer.start_as_current_span("db.query.all_customers"):
                r = await db.execute(text("SELECT id, name FROM customers"))
                customers = r.fetchall()

            # N+1: query orders for each customer individually
            results = []
            for cust in customers:
                with tracer.start_as_current_span("db.query.customer_orders") as q_span:
                    q_span.set_attribute("db.customer_id", cust[0])
                    r = await db.execute(
                        text("SELECT count(*), COALESCE(sum(total), 0) FROM orders WHERE customer_id = :cid"),
                        {"cid": cust[0]}
                    )
                    row = r.fetchone()
                    results.append({
                        "customer": cust[1],
                        "order_count": row[0] if row else 0,
                        "total": float(row[1]) if row else 0,
                    })

        span.set_attribute("performance.n_plus_one_queries", len(customers) + 1)
        push_log("WARNING", f"N+1 query demo: {len(customers)+1} queries executed", **{
            "performance.query_count": len(customers) + 1,
            "performance.pattern": "n_plus_one",
        })
        return {"results": results, "query_count": len(customers) + 1}


@router.get("/error-demo")
async def error_demo(
    request: Request,
    error_type: str = Query(default="exception", description="Type of error to simulate"),
):
    """Simulate various error conditions for observability testing."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.error_demo") as span:
        span.set_attribute("error.type", error_type)

        if error_type == "exception":
            raise ValueError("Simulated application exception for APM testing")
        elif error_type == "timeout":
            await asyncio.sleep(35)  # exceed typical timeout
        elif error_type == "memory":
            _ = bytearray(100 * 1024 * 1024)  # 100MB allocation
            return {"status": "allocated 100MB"}
        elif error_type == "db_error":
            async with get_db() as db:
                await db.execute(text("SELECT * FROM nonexistent_table"))
        else:
            return {"status": "unknown error type", "available": ["exception", "timeout", "memory", "db_error"]}

"""Order management module — OWASP A04: Insecure Design + A01: Broken Access Control.

Vulnerabilities:
- Business logic bypass (negative quantities for refund fraud)
- IDOR in order access
- Price manipulation via client-side total
- No authorization on order status changes
"""

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db

router = APIRouter(prefix="/api/orders", tags=["Orders"])
tracer_fn = get_tracer


@router.get("")
async def list_orders(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    customer_id: int = Query(default=0, description="Filter by customer"),
):
    """List orders — VULN: no tenant isolation, any user sees all orders."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("orders.list") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.orders_list"):
                query = "SELECT o.*, c.name as customer_name FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1"
                params = {}
                if status:
                    query += " AND o.status = :status"
                    params["status"] = status
                if customer_id:
                    query += " AND o.customer_id = :cid"
                    params["cid"] = customer_id
                query += " ORDER BY o.created_at DESC"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        orders = [dict(r._mapping) for r in rows]
        return {"orders": orders, "total": len(orders)}


@router.get("/{order_id}")
async def get_order(order_id: int, request: Request):
    """Get order details with items — VULN: IDOR (no ownership check)."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("orders.get") as span:
        span.set_attribute("orders.id", order_id)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.order_detail"):
                result = await db.execute(
                    text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}
                )
                order = result.fetchone()

            if not order:
                return {"error": "Order not found"}

            with tracer.start_as_current_span("db.query.order_items"):
                items_result = await db.execute(
                    text("SELECT oi.*, p.name as product_name FROM order_items oi "
                         "LEFT JOIN products p ON oi.product_id = p.id "
                         "WHERE oi.order_id = :oid"),
                    {"oid": order_id}
                )
                items = [dict(r._mapping) for r in items_result.fetchall()]

        return {"order": dict(order._mapping), "items": items}


@router.post("")
async def create_order(request: Request):
    """Create order — VULN: price manipulation, negative quantity."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("orders.create") as span:
        customer_id = body.get("customer_id")
        items = body.get("items", [])
        # VULN: Trust client-provided total instead of computing server-side
        client_total = body.get("total", 0)

        # Detect negative quantities
        for item in items:
            if item.get("quantity", 0) < 0:
                with security_span("mass_assignment", severity="high",
                                 payload=f"negative quantity: {item}",
                                 source_ip=client_ip):
                    log_security_event("mass_assignment", "high",
                        "Negative quantity in order (refund fraud attempt)",
                        source_ip=client_ip, payload=str(item))

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.order_insert"):
                result = await db.execute(
                    text("INSERT INTO orders (customer_id, total, status, notes, shipping_address) "
                         "VALUES (:cid, :total, 'pending', :notes, :addr) RETURNING id"),
                    {
                        "cid": customer_id,
                        "total": client_total,  # VULN: trusting client total
                        "notes": body.get("notes", ""),
                        "addr": body.get("shipping_address", ""),
                    }
                )
                order_row = result.fetchone()
                order_id = order_row[0] if order_row else None

            if order_id and items:
                with tracer.start_as_current_span("db.query.order_items_insert"):
                    for item in items:
                        await db.execute(
                            text("INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                                 "VALUES (:oid, :pid, :qty, :price)"),
                            {
                                "oid": order_id,
                                "pid": item.get("product_id"),
                                "qty": item.get("quantity"),
                                "price": item.get("unit_price", 0),  # VULN: client price
                            }
                        )

        push_log("INFO", f"Order #{order_id} created", **{
            "orders.id": order_id,
            "orders.total": client_total,
            "orders.items_count": len(items),
        })
        return {"status": "created", "order_id": order_id}


@router.patch("/{order_id}/status")
async def update_order_status(order_id: int, request: Request):
    """Update order status — VULN: no authorization, any user can change any order status."""
    tracer = tracer_fn()
    body = await request.json()
    new_status = body.get("status", "")

    with tracer.start_as_current_span("orders.update_status") as span:
        span.set_attribute("orders.id", order_id)
        span.set_attribute("orders.new_status", new_status)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.order_status_update"):
                await db.execute(
                    text("UPDATE orders SET status = :status WHERE id = :id"),
                    {"status": new_status, "id": order_id}
                )

        return {"status": "updated", "order_id": order_id, "new_status": new_status}

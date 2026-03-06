"""Integrations module — cross-service communication with MuShop Cloud Native Portal.

Calls MuShop endpoints via httpx with W3C traceparent propagation, creating
distributed traces visible in OCI APM. The HTTPXClientInstrumentor (already
configured in otel_setup.py) auto-injects trace context headers.

Endpoints:
  GET  /api/integrations/mushop/product-catalog
  GET  /api/integrations/mushop/order-history?customer_email=...
  POST /api/integrations/mushop/recommend-products
  GET  /api/integrations/mushop/health
  GET  /api/integrations/status
"""

import os
import logging

import httpx
from fastapi import APIRouter, Request
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])

MUSHOP_BASE_URL = os.getenv("MUSHOP_CLOUDNATIVE_URL", "")


def _mushop_url() -> str:
    return MUSHOP_BASE_URL or os.getenv("C28_MUSHOP_URL", "")


# ── Cross-service: CRM → MuShop ──────────────────────────────────

@router.get("/mushop/product-catalog")
async def mushop_product_catalog(category: str = "", request: Request = None):
    """Fetch MuShop product catalog from CRM context.

    Creates a distributed trace: CRM → HTTP → MuShop /api/products
    """
    tracer = get_tracer()
    mushop = _mushop_url()
    if not mushop:
        return {"error": "MuShop not configured", "products": []}

    with tracer.start_as_current_span("integration.mushop.product_catalog") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        span.set_attribute("integration.category", category)
        span.set_attribute("integration.mushop_url", mushop)

        try:
            params = {"category": category} if category else {}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{mushop}/api/products", params=params)
                span.set_attribute("integration.mushop.status_code", resp.status_code)

            if resp.status_code == 200:
                data = resp.json()
                push_log("INFO", "MuShop product catalog fetched", **{
                    "integration.type": "product_catalog",
                    "integration.product_count": len(data.get("products", [])),
                })
                return {
                    "products": data.get("products", []),
                    "source": "mushop-cloudnative",
                    "category": category,
                }

            return {"products": [], "reason": f"MuShop returned {resp.status_code}"}

        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"products": [], "reason": str(e)}


@router.get("/mushop/order-history")
async def mushop_order_history(customer_email: str = "", request: Request = None):
    """Fetch MuShop orders for a CRM customer.

    Creates a distributed trace: CRM → HTTP → MuShop /api/orders
    """
    tracer = get_tracer()
    mushop = _mushop_url()
    if not mushop:
        return {"error": "MuShop not configured"}

    with tracer.start_as_current_span("integration.mushop.order_history") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        span.set_attribute("integration.customer_email", customer_email)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{mushop}/api/orders")
                span.set_attribute("integration.mushop.status_code", resp.status_code)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "orders": data.get("orders", []),
                    "source": "mushop-cloudnative",
                    "customer_email": customer_email,
                }
            return {"orders": [], "reason": f"MuShop returned {resp.status_code}"}

        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"orders": [], "reason": str(e)}


@router.post("/mushop/recommend-products")
async def mushop_recommend_products(payload: dict, request: Request):
    """Recommend MuShop products based on CRM ticket/customer context.

    CRM → MuShop /api/shop/featured — fetches featured products as recommendations.
    """
    tracer = get_tracer()
    mushop = _mushop_url()
    if not mushop:
        return {"error": "MuShop not configured"}

    with tracer.start_as_current_span("integration.mushop.recommend_products") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        ticket_id = payload.get("ticket_id")
        customer_id = payload.get("customer_id")
        span.set_attribute("integration.ticket_id", ticket_id or 0)
        span.set_attribute("integration.customer_id", customer_id or 0)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{mushop}/api/shop/featured")
                span.set_attribute("integration.mushop.status_code", resp.status_code)

            if resp.status_code == 200:
                data = resp.json()
                push_log("INFO", "MuShop product recommendations fetched", **{
                    "integration.type": "recommend_products",
                    "integration.product_count": len(data.get("products", [])),
                    "integration.ticket_id": ticket_id,
                })
                return {
                    "recommendations": data.get("products", []),
                    "source": "mushop-cloudnative",
                    "context": {"ticket_id": ticket_id, "customer_id": customer_id},
                }
            return {"recommendations": [], "reason": f"MuShop returned {resp.status_code}"}

        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"recommendations": [], "reason": str(e)}


@router.get("/mushop/health")
async def mushop_health():
    """Check MuShop service health."""
    tracer = get_tracer()
    mushop = _mushop_url()
    if not mushop:
        return {"mushop_configured": False, "status": "not_configured"}

    with tracer.start_as_current_span("integration.mushop.health_check") as span:
        span.set_attribute("integration.target_service", "mushop-cloudnative")
        span.set_attribute("integration.mushop_url", mushop)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{mushop}/health")
                span.set_attribute("integration.mushop.status_code", resp.status_code)

            return {
                "mushop_configured": True,
                "mushop_url": mushop,
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "mushop_response": resp.json() if resp.status_code == 200 else None,
            }
        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"mushop_configured": True, "mushop_url": mushop,
                    "status": "unreachable", "error": str(e)}


# ── Integration status ────────────────────────────────────────────

@router.get("/status")
async def integration_status():
    """Show all configured integrations and their status."""
    mushop = _mushop_url()
    return {
        "integrations": [
            {
                "name": "mushop-cloudnative",
                "type": "cross-service",
                "configured": bool(mushop),
                "url": mushop or None,
                "endpoints": [
                    "/api/integrations/mushop/product-catalog",
                    "/api/integrations/mushop/order-history",
                    "/api/integrations/mushop/recommend-products",
                    "/api/integrations/mushop/health",
                ],
                "trace_propagation": "W3C traceparent (auto-injected by HTTPXClientInstrumentor)",
            },
        ],
    }

"""Invoice management module.

Invoices are generated as real PDF documents and stored **inside Oracle ATP**
as SecureFile BLOBs (``invoices.pdf_data``) — a showcase of the database's
native file-storage capability (no external object store). Generation is
triggered when an invoice is paid, and every step emits OTEL spans so a single
trace runs user -> CRM API -> Oracle DB (LOB write/read).

Security-demo surfaces are intentionally preserved (OWASP A02/A04): unauthenticated
reads, predictable numbers, no CSRF on pay, and an SSTI template hook (Lab 06).
"""

from datetime import datetime

from fastapi import APIRouter, Request, Query, Response
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import get_db

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])
tracer_fn = get_tracer


def _build_invoice_pdf(inv: dict) -> bytes:
    """Render a real invoice PDF (pure-Python fpdf2). Returns the PDF bytes."""
    from fpdf import FPDF

    amount = float(inv.get("amount") or 0)
    tax = float(inv.get("tax") or 0)
    total = amount + tax

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "OCTO Drone Commerce", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 7, "Enterprise CRM - Tax Invoice", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    def row(label: str, value: str, bold: bool = False) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", 11)
        pdf.cell(55, 8, label)
        pdf.set_font("Helvetica", "B" if bold else "", 11)
        pdf.cell(0, 8, value, new_x="LMARGIN", new_y="NEXT")

    row("Invoice number:", str(inv.get("invoice_number", "")))
    row("Customer:", str(inv.get("customer_name") or "—"))
    row("Order ID:", str(inv.get("order_id") or "—"))
    row("Status:", str(inv.get("status", "")).upper())
    due = inv.get("due_date")
    row("Due date:", str(due)[:10] if due else "—")
    pdf.ln(4)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    row("Amount:", f"${amount:,.2f}")
    row("Tax:", f"${tax:,.2f}")
    row("Total:", f"${total:,.2f}", bold=True)
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Generated {datetime.utcnow().isoformat(timespec='seconds')}Z "
                   "- stored in Oracle ATP as a SecureFile BLOB.",
             new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def _lob_to_bytes(value):
    """oracledb returns BLOBs as LOB objects under raw SQL; normalise to bytes."""
    if value is None:
        return None
    if hasattr(value, "read"):
        return value.read()
    return bytes(value)


async def _fetch_invoice(db, invoice_id: int) -> dict | None:
    result = await db.execute(
        text("SELECT i.id, i.order_id, i.invoice_number, i.amount, i.tax, i.status, "
             "c.name AS customer_name "
             "FROM invoices i LEFT JOIN orders o ON i.order_id = o.id "
             "LEFT JOIN customers c ON o.customer_id = c.id WHERE i.id = :id"),
        {"id": invoice_id},
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def _generate_and_store_pdf(db, tracer, invoice: dict) -> bytes:
    """Generate the invoice PDF and persist it into the Oracle BLOB column."""
    with tracer.start_as_current_span("invoices.pdf.generate") as gspan:
        pdf_bytes = _build_invoice_pdf(invoice)
        gspan.set_attribute("invoices.pdf.bytes", len(pdf_bytes))
    filename = f"{invoice.get('invoice_number', 'invoice')}.pdf"
    with tracer.start_as_current_span("db.write.invoice_pdf") as wspan:
        wspan.set_attribute("db.system", "oracle")
        wspan.set_attribute("db.operation", "UPDATE invoices SET pdf_data (SecureFile BLOB)")
        wspan.set_attribute("invoices.id", invoice["id"])
        await db.execute(
            text("UPDATE invoices SET pdf_data = :data, pdf_filename = :fn, "
                 "pdf_size = :sz, pdf_generated_at = :ts WHERE id = :id"),
            {"data": pdf_bytes, "fn": filename, "sz": len(pdf_bytes),
             "ts": datetime.utcnow(), "id": invoice["id"]},
        )
    return pdf_bytes


@router.get("")
async def list_invoices(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List invoices with real order/customer joins (VULN: no auth — demo)."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("invoices.list"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoices_list"):
                query = ("SELECT i.id, i.order_id, i.invoice_number, i.amount, i.tax, "
                         "i.status, i.created_at, i.pdf_filename, i.pdf_size, "
                         "i.pdf_generated_at, o.customer_id, c.name as customer_name "
                         "FROM invoices i LEFT JOIN orders o ON i.order_id = o.id "
                         "LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1")
                params = {}
                if status:
                    query += " AND i.status = :status"
                    params["status"] = status
                query += " ORDER BY i.created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()
        invoices = []
        for r in rows:
            d = dict(r._mapping)
            d["has_pdf"] = bool(d.get("pdf_generated_at"))
            d.pop("pdf_data", None)
            invoices.append(d)
        return {"invoices": invoices, "total": len(invoices), "limit": limit, "offset": offset}


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: int, request: Request):
    """Get invoice (VULN: IDOR + sensitive data exposure — demo)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    with tracer.start_as_current_span("invoices.get") as span:
        span.set_attribute("invoices.id", invoice_id)
        with security_span("sensitive_data", severity="medium",
                           payload=f"invoice_id={invoice_id}", source_ip=client_ip):
            pass
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoice_detail"):
                inv = await _fetch_invoice(db, invoice_id)
        if not inv:
            return {"error": "Invoice not found"}
        inv["has_pdf"] = None  # populated by /pdf
        return {"invoice": inv}


@router.post("/{invoice_id}/pay")
async def pay_invoice(invoice_id: int, request: Request):
    """Mark invoice paid AND auto-generate + store its PDF in Oracle (VULN: no CSRF)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    with tracer.start_as_current_span("invoices.pay") as span:
        span.set_attribute("invoices.id", invoice_id)
        with security_span("csrf", severity="medium",
                           payload=f"pay invoice {invoice_id}", source_ip=client_ip):
            log_security_event("csrf", "medium", "Invoice payment without CSRF protection",
                               source_ip=client_ip, payload=f"invoice_id={invoice_id}")

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoice_pay"):
                await db.execute(text("UPDATE invoices SET status = 'paid' WHERE id = :id"),
                                 {"id": invoice_id})
            invoice = await _fetch_invoice(db, invoice_id)
            generated = False
            if invoice:
                await _generate_and_store_pdf(db, tracer, invoice)
                generated = True

        business_metrics.record_invoice_paid(invoice_id)
        push_log("INFO", f"Invoice #{invoice_id} paid; PDF generated and stored in ATP",
                 **{"invoices.id": invoice_id, "invoices.action": "payment",
                    "invoices.pdf_generated": generated})
        return {"status": "paid", "invoice_id": invoice_id, "pdf_generated": generated}


@router.post("/generate-missing")
async def generate_missing(request: Request):
    """Backfill: store a PDF for every paid invoice that doesn't have one yet."""
    tracer = tracer_fn()
    generated = 0
    with tracer.start_as_current_span("invoices.generate_missing"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.paid_without_pdf"):
                result = await db.execute(
                    text("SELECT id FROM invoices WHERE status = 'paid' AND pdf_generated_at IS NULL"))
                ids = [row[0] for row in result.fetchall()]
            for invoice_id in ids:
                invoice = await _fetch_invoice(db, invoice_id)
                if invoice:
                    await _generate_and_store_pdf(db, tracer, invoice)
                    generated += 1
        push_log("INFO", f"Backfilled {generated} invoice PDFs into ATP",
                 **{"invoices.pdf_backfilled": generated})
    return {"generated": generated, "candidates": len(ids)}


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: int, request: Request):
    """Stream the invoice PDF stored in Oracle. Generates+stores on first access."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    template = request.query_params.get("template", "")

    with tracer.start_as_current_span("invoices.pdf") as span:
        span.set_attribute("invoices.id", invoice_id)
        # Preserved SSTI demo hook (Lab 06): flagged but never executed as a template.
        if "{{" in template or "{%" in template:
            with security_span("ssti", severity="critical", payload=template, source_ip=client_ip):
                log_security_event("ssti", "critical", "SSTI attempt in invoice PDF template",
                                   source_ip=client_ip, payload=template)

        async with get_db() as db:
            with tracer.start_as_current_span("db.read.invoice_pdf") as rspan:
                rspan.set_attribute("db.system", "oracle")
                rspan.set_attribute("db.operation", "SELECT invoices.pdf_data (SecureFile BLOB)")
                result = await db.execute(
                    text("SELECT pdf_data, pdf_filename FROM invoices WHERE id = :id"),
                    {"id": invoice_id})
                row = result.fetchone()
            if not row:
                return Response(content='{"error":"Invoice not found"}', status_code=404,
                                media_type="application/json")
            pdf_bytes = _lob_to_bytes(row._mapping.get("pdf_data"))
            filename = row._mapping.get("pdf_filename") or f"invoice-{invoice_id}.pdf"
            if not pdf_bytes:
                # Not generated yet — build, store, and serve in one shot.
                invoice = await _fetch_invoice(db, invoice_id)
                if not invoice:
                    return Response(content='{"error":"Invoice not found"}', status_code=404,
                                    media_type="application/json")
                pdf_bytes = await _generate_and_store_pdf(db, tracer, invoice)
                filename = f"{invoice.get('invoice_number', invoice_id)}.pdf"
                span.set_attribute("invoices.pdf.generated_on_read", True)

        span.set_attribute("invoices.pdf.bytes", len(pdf_bytes))
        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

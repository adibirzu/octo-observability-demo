"""Regression: a declined/review payment is a BUSINESS outcome, not a span fault.

Pins the PR #55 behavior so a future change can't reintroduce flagging a designed
antifraud DECLINE as ``otel.status_code = ERROR`` — which made declines look like
silent failures in OCI APM and hid them from the "Errored Traces" view. Only
genuine technical faults (``PAYMENT_FAULT_STATUSES``) may set the span error
status. See workshop Lab 18 and ``payments/base.py``.

RED proof (the fix is already in ``main``): temporarily reverting the
``_emit_step`` condition to ``if step.status not in {"completed","authorized","ok"}``
turns ``test_business_outcome_step_is_not_flagged_error`` RED for every business
status — confirming this test guards the behavior rather than tautologically
passing.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from server.modules.payments import gateway_emulator
from server.modules.payments.base import PAYMENT_FAULT_STATUSES
from server.modules.payments.checkout_workflow import build_payment_context
from server.modules.payments.gateway_emulator import PaymentGatewayStep

CARD_DETAILS = {"card": {"number": "4111111111111111", "expiry": "12/30", "cvv": "123"}}

BUSINESS_OUTCOMES = ["declined", "review", "pending", "cancelled"]
TECHNICAL_FAULTS = ["error", "failed", "timeout", "unreachable", "exception"]
SUCCESS = ["completed", "authorized", "ok"]


@pytest.fixture
def captured_spans(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Route the gateway emulator's tracer to an in-memory exporter so a test can
    read the exact attributes set on each emitted span."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(gateway_emulator, "get_tracer", lambda: provider.get_tracer("test"))
    return exporter


def _emit_step_span(status: str, exporter: InMemorySpanExporter):
    ctx = build_payment_context(
        payment_method="credit_card",
        payment_details=CARD_DETAILS,
        amount_minor_units=18890,
        customer_email="buyer@example.invalid",
    )
    step = PaymentGatewayStep(
        name="merchant_authorization_result",
        phase="authorization",
        message="final gateway decision",
        status=status,
    )
    gateway_emulator._emit_step(
        step,
        order_id=1,
        amount_minor_units=18890,
        currency="usd",
        context=ctx,
        gateway_request_id="gw_test",
        network="visa",
        step_index=0,
    )
    spans = exporter.get_finished_spans()
    assert spans, "expected _emit_step to emit a span"
    return spans[-1]


@pytest.mark.unit
@pytest.mark.parametrize("status", BUSINESS_OUTCOMES)
def test_business_outcome_step_is_not_flagged_error(status: str, captured_spans: InMemorySpanExporter) -> None:
    span = _emit_step_span(status, captured_spans)
    assert span.attributes.get("otel.status_code") != "ERROR", (
        f"business outcome {status!r} must NOT set otel.status_code=ERROR "
        "(a designed decline is not a technical fault)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("status", TECHNICAL_FAULTS)
def test_technical_fault_step_is_flagged_error(status: str, captured_spans: InMemorySpanExporter) -> None:
    span = _emit_step_span(status, captured_spans)
    assert span.attributes.get("otel.status_code") == "ERROR", (
        f"technical fault {status!r} must set otel.status_code=ERROR"
    )


@pytest.mark.unit
@pytest.mark.parametrize("status", SUCCESS)
def test_success_step_is_not_flagged_error(status: str, captured_spans: InMemorySpanExporter) -> None:
    span = _emit_step_span(status, captured_spans)
    assert span.attributes.get("otel.status_code") != "ERROR"


@pytest.mark.unit
def test_payment_fault_statuses_classification() -> None:
    for s in BUSINESS_OUTCOMES + SUCCESS:
        assert s not in PAYMENT_FAULT_STATUSES, f"{s!r} is not a technical fault"
    for s in TECHNICAL_FAULTS:
        assert s in PAYMENT_FAULT_STATUSES, f"{s!r} should be a technical fault"

"""End-to-end span status through ``authorize_simulated_payment``.

Covers the SECOND ``otel.status_code=ERROR`` site (``payment_gateway_simulation``)
plus the gateway emulator in the real authorize flow: a DECLINED authorize (a
business outcome) must emit NO ``otel.status_code=ERROR`` span; a TIMEOUT (a
technical fault) must emit one. Complements the focused ``_emit_step`` unit tests
in ``test_payment_decline_span_status.py`` (PR #55 + the log-level follow-up).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from server.modules import payment_gateway_simulation as pgs
from server.modules.payments import gateway_emulator
from server.modules.payment_gateway_simulation import authorize_simulated_payment


class _Rows:
    def mappings(self) -> "_Rows":
        return self

    def first(self) -> None:
        return None


class _FakeDb:
    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        return _Rows()


def _route_spans(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Route BOTH the simulation and gateway-emulator tracers to one exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(pgs, "get_tracer", lambda: provider.get_tracer("test"))
    monkeypatch.setattr(gateway_emulator, "get_tracer", lambda: provider.get_tracer("test"))
    return exporter


def _common_mocks(monkeypatch: pytest.MonkeyPatch, client: type) -> None:
    monkeypatch.setattr("server.modules.payment_gateway_simulation.JavaAppServerClient", client)
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.business_metrics.record_payment_authorization",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "server.modules.payment_gateway_simulation.cfg.payment_gateway_simulation_enabled", True
    )


def _error_spans(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.attributes.get("otel.status_code") == "ERROR"]


@pytest.mark.unit
def test_declined_authorize_emits_no_error_span(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        async def verify_payment(self, **kwargs):
            return {
                "status": "ok",
                "data": {
                    "verification_provider": "octo-antifraud-verification-app",
                    "decision": "declined",
                    "risk_score": 95,
                    "error_code": "ANTIFRAUD_DECLINED",
                    "latency_ms": 40,
                },
                "latency_ms": 40,
            }

        async def authorize_payment(self, **kwargs):
            return {"status": "ok", "data": {"decision": "approved", "risk_score": 10, "latency_ms": 30, "authorization_code": "SIM-OK"}, "latency_ms": 30}

    exporter = _route_spans(monkeypatch)
    _common_mocks(monkeypatch, _Client)
    result = asyncio.run(
        authorize_simulated_payment(
            order_id=88, total=250.0, currency="usd", customer_email="buyer@example.invalid",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440088",
            payment_method="credit_card",
            payment_details={"card": {"number": "4000000000000002", "expiry": "12/30", "cvv": "123"}},
            db=_FakeDb(),
        )
    )
    assert result["status"] == "declined"
    assert _error_spans(exporter) == [], "a declined (business) authorize must emit NO otel.status_code=ERROR span"


@pytest.mark.unit
def test_timeout_authorize_emits_error_span(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        async def verify_payment(self, **kwargs):
            return {"status": "disabled"}

        async def authorize_payment(self, **kwargs):
            return {"status": "disabled"}

    monkeypatch.setenv("PAYMENT_SIMULATION_MODE", "timeout")
    exporter = _route_spans(monkeypatch)
    _common_mocks(monkeypatch, _Client)
    result = asyncio.run(
        authorize_simulated_payment(
            order_id=89, total=250.0, currency="usd", customer_email="buyer@example.invalid",
            checkout_idempotency_key="550e8400-e29b-41d4-a716-446655440089",
            payment_method="credit_card",
            payment_details={"card": {"number": "4111111111111111", "expiry": "12/30", "cvv": "123"}},
            db=_FakeDb(),
        )
    )
    assert result["status"] in {"timeout", "failed"}, "timeout mode should produce a fault outcome"
    assert _error_spans(exporter), "a timeout (fault) authorize must emit an otel.status_code=ERROR span"

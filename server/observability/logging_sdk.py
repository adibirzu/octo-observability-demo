"""Structured logging with OCI Logging SDK + Splunk HEC integration."""

import json
import logging
import sys
import time
from datetime import datetime, timezone

import httpx
from opentelemetry import trace

from server.config import cfg

_security_logger = logging.getLogger("security.events")
_security_logger.setLevel(logging.INFO)
_security_logger.propagate = False

# JSON formatter for structured log output
class _JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        # Inject trace context
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_entry["trace_id"] = format(ctx.trace_id, "032x")
            log_entry["span_id"] = format(ctx.span_id, "016x")
        return json.dumps(log_entry, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JSONFormatter())
_security_logger.addHandler(_handler)

# OCI Logging SDK client (lazy init)
_oci_logging_client = None


def _get_oci_logging_client():
    global _oci_logging_client
    if _oci_logging_client is not None:
        return _oci_logging_client
    if not cfg.logging_configured:
        return None
    try:
        import oci
        if cfg.oci_auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            _oci_logging_client = oci.loggingingestion.LoggingClient(config={}, signer=signer)
        else:
            config = oci.config.from_file()
            _oci_logging_client = oci.loggingingestion.LoggingClient(config)
        return _oci_logging_client
    except Exception:
        return None


def push_log(level: str, message: str, **kwargs):
    """Push a structured log to OCI Logging and optionally Splunk."""
    # Inject trace context
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        kwargs["trace_id"] = format(ctx.trace_id, "032x")
        kwargs["span_id"] = format(ctx.span_id, "016x")

    kwargs["app.service"] = f"{cfg.otel_service_name}-{cfg.app_runtime}"
    kwargs["app.runtime"] = cfg.app_runtime

    # Write to structured logger (stdout)
    record = logging.LogRecord(
        name="security.events", level=getattr(logging, level.upper(), logging.INFO),
        pathname="", lineno=0, msg=message, args=(), exc_info=None,
    )
    record.extra_fields = kwargs
    _security_logger.handle(record)

    # Push to OCI Logging SDK
    _push_to_oci_logging(level, message, kwargs)

    # Push to Splunk HEC
    _push_to_splunk(level, message, kwargs)


def _push_to_oci_logging(level: str, message: str, extra: dict):
    client = _get_oci_logging_client()
    if client is None:
        return
    try:
        import oci
        from oci.loggingingestion.models import PutLogsDetails, LogEntryBatch, LogEntry
        entry = LogEntry(
            data=json.dumps({"message": message, **extra}, default=str),
            id=f"crm-{int(time.time() * 1000)}",
            time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )
        batch = LogEntryBatch(
            defaultloglevel=level.upper(),
            source=f"{cfg.otel_service_name}-{cfg.app_runtime}",
            type="enterprise-crm-portal",
            entries=[entry],
        )
        client.put_logs(
            log_id=cfg.oci_log_id,
            put_logs_details=PutLogsDetails(
                specversion="1.0",
                log_entry_batches=[batch],
            ),
        )
    except Exception:
        pass  # never break the request


def _push_to_splunk(level: str, message: str, extra: dict):
    if not cfg.splunk_hec_url or not cfg.splunk_hec_token:
        return
    try:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "message": message,
            **extra,
        }
        httpx.post(
            cfg.splunk_hec_url,
            json={"event": event, "sourcetype": "oci:crm:security"},
            headers={"Authorization": f"Splunk {cfg.splunk_hec_token}"},
            timeout=2.0,
        )
    except Exception:
        pass  # fire-and-forget


def log_security_event(
    vuln_type: str,
    severity: str,
    message: str,
    source_ip: str = "",
    username: str = "",
    payload: str = "",
    **extra,
):
    """Log a security event with standard attributes."""
    push_log(
        "WARNING" if severity in ("low", "medium") else "ERROR",
        message,
        **{
            "security.attack.detected": True,
            "security.attack.type": vuln_type,
            "security.attack.severity": severity,
            "security.source_ip": source_ip,
            "security.username": username,
            "security.attack.payload": payload[:512] if payload else "",
            **extra,
        },
    )

"""Periodic Langfuse -> OCI Monitoring sync so OCI APM/Monitoring shows the same
token / cost / latency / judge-score analytics that only exist server-side in
Langfuse.

The Langfuse OTEL bridge already mirrors raw spans into OCI APM. This job is the
complement: it pulls the *computed* analytics from the Langfuse public REST API
(`/api/public/{traces,observations,scores}`) and publishes them as OCI Monitoring
custom metrics in the ``octo_genai`` namespace, where APM dashboards and alarms
can read them. Read-only against Langfuse; idempotent; degrades gracefully when
either side is unconfigured (so it is safe to run on a timer).

Reuses the patterns from OCI-DEMO control_plane/api/observability/llm_observability.py
(REST client, Z-suffix datetimes, cost) and the shop's oci_monitoring.py publisher.

Run once:   python -m app.sync.langfuse_apm_sync --once --hours 1
Run a loop: python -m app.sync.langfuse_apm_sync --interval 3600
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Any

from app.observability.cost import estimate_cost_usd

logger = logging.getLogger("langfuse-apm-sync")

LANGFUSE_BASE = (os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "").rstrip("/")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")

OCI_MONITORING_NAMESPACE = os.getenv("OCI_GENAI_METRICS_NAMESPACE", "octo_genai")
OCI_MONITORING_COMPARTMENT = os.getenv("OCI_MONITORING_COMPARTMENT_ID") or os.getenv("OCI_COMPARTMENT_ID", "")
OCI_REGION = os.getenv("OCI_REGION", "")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "octo-genai-studio")


def _ingestion_endpoint(region: str) -> str | None:
    """OCI Monitoring has separate read vs WRITE endpoints. PostMetricData must
    target telemetry-INGESTION.<region>.oraclecloud.com or it 404s (KB-456).
    Returns None when region is unknown so the SDK default applies."""
    region = (region or "").strip()
    if not region:
        return None
    return f"https://telemetry-ingestion.{region}.oraclecloud.com"


# ── Langfuse REST (read-only) ──────────────────────────────────────────────
def _langfuse_datetime(hours: float) -> str:
    """UTC ISO timestamp `hours` ago with a Z suffix (Langfuse v4 rejects +00:00)."""
    import datetime as _dt

    ts = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _langfuse_get(path: str, params: dict | None = None) -> Any:
    if not (LANGFUSE_BASE and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        logger.warning("Langfuse not configured (LANGFUSE_BASE_URL / keys); skipping pull")
        return None
    import httpx

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{LANGFUSE_BASE}{path}",
                auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # pragma: no cover - network/credential dependent
        logger.warning("Langfuse GET %s failed: %s", path, exc)
        return None


def collect_analytics(hours: float = 1.0, limit: int = 200) -> dict[str, float]:
    """Aggregate token/cost/latency/score analytics from Langfuse over a window."""
    since = _langfuse_datetime(hours)
    observations = (_langfuse_get(
        "/api/public/observations",
        params={"fromStartTime": since, "type": "GENERATION", "limit": limit},
    ) or {}).get("data", [])
    scores = (_langfuse_get(
        "/api/public/scores", params={"fromTimestamp": since, "limit": limit}
    ) or {}).get("data", [])

    total_in = total_out = 0
    total_cost = 0.0
    latencies: list[float] = []
    for obs in observations:
        usage = obs.get("usage") or {}
        in_tok = int(usage.get("input") or usage.get("promptTokens") or 0)
        out_tok = int(usage.get("output") or usage.get("completionTokens") or 0)
        total_in += in_tok
        total_out += out_tok
        model = obs.get("model") or ""
        total_cost += float(obs.get("calculatedTotalCost") or estimate_cost_usd(model, in_tok, out_tok))
        if obs.get("latency") is not None:
            try:
                latencies.append(float(obs["latency"]))
            except (TypeError, ValueError):
                pass

    score_values = [float(s["value"]) for s in scores if isinstance(s.get("value"), (int, float))]

    def _pct(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = min(len(s) - 1, int(q * len(s)))
        return round(s[idx], 3)

    return {
        "genai_input_tokens": float(total_in),
        "genai_output_tokens": float(total_out),
        "genai_total_tokens": float(total_in + total_out),
        "genai_cost_usd": round(total_cost, 6),
        "genai_generations": float(len(observations)),
        "genai_latency_p50_ms": _pct(latencies, 0.50),
        "genai_latency_p95_ms": _pct(latencies, 0.95),
        "genai_judge_score_avg": round(sum(score_values) / len(score_values), 4) if score_values else 0.0,
        "genai_judge_scores": float(len(score_values)),
    }


# ── OCI Monitoring publish ─────────────────────────────────────────────────
def publish_to_oci_monitoring(metrics: dict[str, float]) -> bool:
    """Publish aggregated metrics to OCI Monitoring (octo_genai namespace)."""
    if not OCI_MONITORING_COMPARTMENT:
        logger.warning("OCI_MONITORING_COMPARTMENT_ID / OCI_COMPARTMENT_ID unset; skipping publish")
        return False
    try:
        import datetime as _dt

        import oci
    except Exception as exc:  # pragma: no cover
        logger.warning("oci SDK unavailable: %s", exc)
        return False

    auth_type = (os.getenv("OCI_AUTH_TYPE") or "INSTANCE_PRINCIPAL").upper()
    try:
        if auth_type == "INSTANCE_PRINCIPAL":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            region = OCI_REGION or getattr(signer, "region", "") or ""
            client = oci.monitoring.MonitoringClient(
                {}, signer=signer, service_endpoint=_ingestion_endpoint(region)
            )
        elif auth_type == "RESOURCE_PRINCIPAL":
            signer = oci.auth.signers.get_resource_principals_signer()
            region = OCI_REGION or os.getenv("OCI_RESOURCE_PRINCIPAL_REGION", "")
            client = oci.monitoring.MonitoringClient(
                {}, signer=signer, service_endpoint=_ingestion_endpoint(region)
            )
        else:
            cfg = oci.config.from_file(profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"))
            client = oci.monitoring.MonitoringClient(
                cfg, service_endpoint=_ingestion_endpoint(OCI_REGION or cfg.get("region", ""))
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not build OCI Monitoring client: %s", exc)
        return False

    now = _dt.datetime.now(_dt.timezone.utc)
    dimensions = {"service": SERVICE_NAME, "source": "langfuse"}
    series = [
        oci.monitoring.models.MetricDataDetails(
            namespace=OCI_MONITORING_NAMESPACE,
            compartment_id=OCI_MONITORING_COMPARTMENT,
            name=name,
            dimensions=dimensions,
            datapoints=[oci.monitoring.models.Datapoint(timestamp=now, value=float(value))],
        )
        for name, value in metrics.items()
    ]
    try:
        client.post_metric_data(
            oci.monitoring.models.PostMetricDataDetails(metric_data=series)
        )
        logger.info("Published %d GenAI metrics to OCI Monitoring (%s)", len(series), OCI_MONITORING_NAMESPACE)
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("post_metric_data failed: %s", exc)
        return False


def run_once(hours: float = 1.0) -> dict[str, float]:
    metrics = collect_analytics(hours=hours)
    logger.info("Collected GenAI analytics: %s", metrics)
    publish_to_oci_monitoring(metrics)
    return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Langfuse -> OCI Monitoring GenAI sync")
    parser.add_argument("--once", action="store_true", help="run a single sync and exit")
    parser.add_argument("--hours", type=float, default=1.0, help="lookback window in hours")
    parser.add_argument("--interval", type=int, default=3600, help="loop interval seconds")
    args = parser.parse_args()

    if args.once:
        run_once(hours=args.hours)
        return
    while True:
        try:
            run_once(hours=args.hours)
        except Exception as exc:  # pragma: no cover
            logger.warning("sync iteration failed: %s", exc)
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    main()

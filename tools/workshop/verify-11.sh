#!/usr/bin/env bash
# Lab 11 — OKE pod autoscaling.
# Usage: verify-11.sh <run_id>   (or set CERT_RUN_ID)
# Confirms: HPA scaled shop above its floor, the stress_run_count metric reached
# OCI Monitoring, and run_id-tagged app logs reached Log Analytics.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
RUN_ID="${1:-${CERT_RUN_ID:-}}"
[[ -z "${RUN_ID}" ]] && fail "usage: verify-11.sh <run_id> (or export CERT_RUN_ID)"

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
hour_ago=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)

# 1. HPA scaled the shop deployment above 2 replicas.
if command -v kubectl >/dev/null 2>&1; then
    reps=$(kubectl get hpa -n octo-drone-shop \
        -o jsonpath='{range .items[*]}{.status.currentReplicas}{"\n"}{end}' 2>/dev/null \
        | sort -rn | head -1)
    if [[ "${reps:-0}" -gt 2 ]]; then
        ok "HPA scaled shop to ${reps} replicas (> floor of 2)"
    else
        warn "HPA currentReplicas=${reps:-0} — run the stress journey to trigger scale-out"
    fi
else
    warn "kubectl not available — skipping HPA replica check"
fi

# 2. stress_run_count custom metric reached OCI Monitoring (namespace octo_apm_demo).
if [[ -n "${OCI_MONITORING_COMPARTMENT_ID:-}" ]]; then
    mq=$(oci monitoring metric-data summarize-metrics-data \
        --compartment-id "${OCI_MONITORING_COMPARTMENT_ID}" \
        --namespace octo_apm_demo \
        --query-text 'stress_run_count[1m].max()' \
        --start-time "${hour_ago}" --end-time "${now}" 2>&1)
    if echo "${mq}" | jq -e '.data // [] | length > 0' >/dev/null 2>&1; then
        ok "stress_run_count metric present in OCI Monitoring (octo_apm_demo)"
    else
        warn "no stress_run_count samples in the last hour"
    fi
else
    warn "OCI_MONITORING_COMPARTMENT_ID unset — skipping the metric check"
fi

# 3. run_id-tagged app logs reached Log Analytics.
if [[ -n "${LA_NAMESPACE:-}" ]]; then
    out=$(oci log-analytics query --namespace-name "${LA_NAMESPACE}" \
        --query-string "'Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal') | jsonextract field = Message 'Run ID' = '\$.run_id' | where 'Run ID' = '${RUN_ID}' | head limit = 1" 2>&1)
    if echo "${out}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
        ok "found app log records tagged run_id=${RUN_ID}"
    else
        warn "no records for run_id=${RUN_ID} yet (LA ingestion lag is 30–120 s)"
    fi
else
    warn "LA_NAMESPACE unset — skipping the Log Analytics check"
fi

pass_or_fail "11"

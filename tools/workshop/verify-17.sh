#!/usr/bin/env bash
# Lab 17 — Root cause: APM → Log Analytics → OPSI → DBM.
# Usage: verify-17.sh <trace_id>   (or set CERT_TRACE_ID_17)
# Confirms: the ERROR trace's broken_orders_probe span is in APM (via its log
# trail in Log Analytics), and the trace_id bridges into the app log records.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var LA_NAMESPACE
TRACE_ID="${1:-${CERT_TRACE_ID_17:-}}"
[[ -z "${TRACE_ID}" ]] && fail "usage: verify-17.sh <trace_id> (or export CERT_TRACE_ID_17)"

# 1. The trace's log records exist in Log Analytics (APM ↔ LA bridge on trace_id).
logs=$(oci log-analytics query --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal') | jsonextract field = Message 'Trace ID' = '\$.trace_id' | where 'Trace ID' = '${TRACE_ID}' | head limit = 1" 2>&1)
if echo "${logs}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "Log Analytics has records for trace_id=${TRACE_ID} (APM↔LA bridge intact)"
else
    warn "no LA records for trace_id=${TRACE_ID} yet (ingestion lag, or re-run the broken_orders_probe)"
fi

# 2. The broken_orders_probe ERROR signal is present in the window.
probe=$(oci log-analytics query --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal') and (Message like '%broken_orders_probe%' or Message like '%\"level\":\"ERROR\"%') | head limit = 1" 2>&1)
if echo "${probe}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "found a broken_orders_probe / ERROR signal to root-cause"
else
    warn "no broken_orders_probe / ERROR signal in the window — trigger the probe first"
fi

pass_or_fail "17"

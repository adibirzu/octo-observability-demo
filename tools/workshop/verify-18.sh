#!/usr/bin/env bash
# Lab 18 — Root cause: failed payment with APM.
# Usage: verify-18.sh <trace_id>   (or set CERT_TRACE_ID_18)
# Confirms the key teaching point: an antifraud DECLINE is a business outcome,
# not a technical fault — the payment-gateway span carries
# merchant_authorization_result=declined with is-fault=false, and the Java
# payment-verify path returns HTTP 200.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var LA_NAMESPACE
TRACE_ID="${1:-${CERT_TRACE_ID_18:-}}"
[[ -z "${TRACE_ID}" ]] && fail "usage: verify-18.sh <trace_id> (or export CERT_TRACE_ID_18)"

# 1. The declined authorization is recorded for this trace.
decline=$(oci log-analytics query --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal') | jsonextract field = Message 'Trace ID' = '\$.trace_id' | jsonextract field = Message 'Auth Result' = '\$.merchant_authorization_result' | where 'Trace ID' = '${TRACE_ID}' and 'Auth Result' = 'declined' | head limit = 1" 2>&1)
if echo "${decline}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "trace ${TRACE_ID} shows merchant_authorization_result=declined (business decline)"
else
    warn "no declined authorization found for trace ${TRACE_ID} (re-run the antifraud-decline checkout)"
fi

# 2. The decline is NOT a technical fault (is-fault=false on the payment span).
fault=$(oci log-analytics query --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal') | jsonextract field = Message 'Trace ID' = '\$.trace_id' | jsonextract field = Message 'Is Fault' = '\$.is_fault' | where 'Trace ID' = '${TRACE_ID}' and 'Is Fault' = true | head limit = 1" 2>&1)
if echo "${fault}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    fail "a span on trace ${TRACE_ID} is marked is-fault=true — a decline must NOT be a technical fault"
else
    ok "no is-fault=true span on the trace — the decline is a business outcome, not an error"
fi

# 3. The Java payment-verify path returns HTTP 200 (decline travels over a 200).
if [[ -n "${SHOP_BASE_URL:-}" ]] && command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null -w '%{http_code}' "${SHOP_BASE_URL%/}/api/java-apm/payment/verify" 2>/dev/null || echo "000")
    if [[ "${code}" == "200" ]]; then
        ok "Java payment-verify returned HTTP 200"
    else
        warn "Java payment-verify returned HTTP ${code} (expected 200; check SHOP_BASE_URL / sidecar)"
    fi
else
    warn "SHOP_BASE_URL unset or curl missing — skipping the Java payment-verify check"
fi

pass_or_fail "18"

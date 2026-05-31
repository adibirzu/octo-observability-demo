#!/usr/bin/env bash
# Deploy a low-footprint Grafana on OKE for OCTO-DEMO GenAI observability.
#
# Companion to deploy-langfuse.sh. Renders deploy/k8s/oke/grafana/grafana.yaml,
# builds the grafana-dashboards ConfigMap from deploy/k8s/oke/grafana/dashboards
# (GenAI FinOps / operations / observability dashboards ported from OCI-DEMO C32,
# Infinity + OCI Metrics datasources), and refuses to deploy to an OKE cluster
# outside the OCTO project VCN unless ALLOW_DIFFERENT_VCN=true. Admin password
# and the GenAI API token are generated/injected at deploy time — never committed.
#
# Usage:
#   ./deploy/oke/deploy-grafana.sh --check
#   GRAFANA_HOSTNAME=grafana.octodemo.cloud ./deploy/oke/deploy-grafana.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

MODE="apply"
case "${1:-}" in
    -h|--help) show_usage; exit 0 ;;
    --check) MODE="check" ;;
    --dry-run) MODE="dry-run" ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; show_usage >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST="${REPO_ROOT}/k8s/oke/grafana/grafana.yaml"
DASHBOARD_DIR="${REPO_ROOT}/k8s/oke/grafana/dashboards"
OUTPUTS_JSON="${OUTPUTS_JSON:-${REPO_ROOT}/../credentials/${OCI_PROFILE:-DEFAULT}/outputs.json}"

command_exists() { command -v "$1" >/dev/null 2>&1; }
require_cmd() { command_exists "$1" || { echo "Missing required command: $1" >&2; exit 1; }; }

json_value() {
    local expr="$1"
    if [[ -f "${OUTPUTS_JSON}" ]] && command_exists jq; then
        jq -r "${expr} // empty" "${OUTPUTS_JSON}" 2>/dev/null || true
    fi
}

random_base64() { openssl rand -base64 "${1:-24}" | tr -d '\n'; }

run_with_timeout() {
    local seconds="$1"; shift
    if command_exists timeout; then timeout "${seconds}" "$@"; return; fi
    if command_exists gtimeout; then gtimeout "${seconds}" "$@"; return; fi
    python3 - "${seconds}" "$@" <<'PY'
import subprocess, sys
seconds = float(sys.argv[1]); cmd = sys.argv[2:]
try:
    raise SystemExit(subprocess.run(cmd, check=False, timeout=seconds).returncode)
except subprocess.TimeoutExpired:
    print(f"Timed out after {seconds:g}s: {' '.join(cmd[:4])} ...", file=sys.stderr)
    raise SystemExit(124)
PY
}

oci_cmd() {
    run_with_timeout "${OCI_CMD_TIMEOUT}" oci \
        --connection-timeout "${OCI_CLI_CONNECTION_TIMEOUT}" \
        --read-timeout "${OCI_CLI_READ_TIMEOUT}" \
        "$@"
}

require_cmd oci
require_cmd kubectl
require_cmd jq
require_cmd envsubst
require_cmd openssl
if ! command_exists timeout && ! command_exists gtimeout; then
    require_cmd python3
fi

: "${OCI_PROFILE:=DEFAULT}"
: "${OCI_REGION:=us-phoenix-1}"
: "${OCI_CMD_TIMEOUT:=45}"
: "${OCI_CLI_CONNECTION_TIMEOUT:=10}"
: "${OCI_CLI_READ_TIMEOUT:=30}"
: "${COMPARTMENT_ID:=$(json_value '.deployment_compartment_id.value // .deployment_compartment_id')}"
: "${TARGET_VCN_ID:=$(json_value '.network.value.vcn_id')}"
: "${OCI_LB_SUBNET_OCID:=$(json_value '.network.value.lb_subnet_id')}"
: "${GRAFANA_NAMESPACE:=octo-grafana}"
: "${GRAFANA_HOSTNAME:=grafana.octodemo.cloud}"
: "${GRAFANA_PUBLIC_URL:=https://${GRAFANA_HOSTNAME}}"
: "${GRAFANA_STORAGE_CLASS:=oci-bv}"
: "${GRAFANA_STORAGE:=5Gi}"
: "${OCI_LB_SHAPE_FLEX_MIN:=10}"
: "${OCI_LB_SHAPE_FLEX_MAX:=10}"
: "${KUBE_ENDPOINT:=PUBLIC_ENDPOINT}"
: "${KUBECONFIG:=${REPO_ROOT}/../.tmp/oke-grafana-kubeconfig}"
: "${ALLOW_DIFFERENT_VCN:=false}"
# GenAI JSON/metrics API the Infinity datasource queries (e.g. AI Studio obs API).
: "${GENAI_API_BASE:=http://octo-genai-studio.octo-drone-shop.svc.cluster.local:8090}"

if [[ -z "${COMPARTMENT_ID}" || -z "${TARGET_VCN_ID}" || -z "${OCI_LB_SUBNET_OCID}" ]]; then
    echo "Missing COMPARTMENT_ID, TARGET_VCN_ID, or OCI_LB_SUBNET_OCID." >&2
    echo "Set them explicitly or provide OUTPUTS_JSON with the tenancy network outputs." >&2
    exit 2
fi

if [[ ! -d "${DASHBOARD_DIR}" ]] || ! ls "${DASHBOARD_DIR}"/*.json >/dev/null 2>&1; then
    echo "No dashboards found under ${DASHBOARD_DIR}." >&2
    exit 2
fi

echo "================================================================"
echo " OKE Grafana deploy — OCTO-DEMO GenAI observability"
echo "   OCI profile:   ${OCI_PROFILE}"
echo "   OCI region:    ${OCI_REGION}"
echo "   Namespace:     ${GRAFANA_NAMESPACE}"
echo "   Hostname:      ${GRAFANA_HOSTNAME}"
echo "   GenAI API:     ${GENAI_API_BASE}"
echo "   Dashboards:    $(ls "${DASHBOARD_DIR}"/*.json | wc -l | tr -d ' ')"
echo "================================================================"

echo
echo "[1/6] OCI rights and VCN checks..."
if [[ -z "${OKE_CLUSTER_ID:-}" ]]; then
    OKE_CLUSTER_ID="$(
        oci_cmd ce cluster list --profile "${OCI_PROFILE}" --region "${OCI_REGION}" \
            --compartment-id "${COMPARTMENT_ID}" --all --output json |
        jq -r --arg vcn "${TARGET_VCN_ID}" \
            '.data[] | select(."lifecycle-state"=="ACTIVE" and ."vcn-id"==$vcn) | .id' | head -1
    )"
fi
if [[ -z "${OKE_CLUSTER_ID}" ]]; then
    echo "No ACTIVE OKE cluster was found in TARGET_VCN_ID." >&2
    echo "Set ALLOW_DIFFERENT_VCN=true with OKE_CLUSTER_ID explicitly to override." >&2
    exit 4
fi

cluster_json="$(oci_cmd ce cluster get --profile "${OCI_PROFILE}" --region "${OCI_REGION}" --cluster-id "${OKE_CLUSTER_ID}" --output json)"
cluster_vcn="$(jq -r '.data."vcn-id"' <<<"${cluster_json}")"
cluster_name="$(jq -r '.data.name' <<<"${cluster_json}")"
cluster_state="$(jq -r '.data."lifecycle-state"' <<<"${cluster_json}")"

if [[ "${cluster_state}" != "ACTIVE" ]]; then
    echo "OKE cluster ${cluster_name} is ${cluster_state}, not ACTIVE." >&2
    exit 4
fi
if [[ "${cluster_vcn}" != "${TARGET_VCN_ID}" && "${ALLOW_DIFFERENT_VCN}" != "true" ]]; then
    echo "OKE cluster ${cluster_name} is not in TARGET_VCN_ID. Refusing by default." >&2
    exit 4
fi

echo "Using OKE cluster: ${cluster_name}"
mkdir -p "$(dirname "${KUBECONFIG}")"
oci_cmd ce cluster create-kubeconfig --profile "${OCI_PROFILE}" --region "${OCI_REGION}" \
    --cluster-id "${OKE_CLUSTER_ID}" --file "${KUBECONFIG}" --token-version 2.0.0 \
    --kube-endpoint "${KUBE_ENDPOINT}" >/dev/null
export KUBECONFIG

echo
echo "[2/6] Kubernetes rights checks..."
kubectl get nodes >/dev/null
kubectl get storageclass "${GRAFANA_STORAGE_CLASS}" >/dev/null
kubectl auth can-i create namespaces >/dev/null
kubectl auth can-i create deployments -n "${GRAFANA_NAMESPACE}" >/dev/null
kubectl auth can-i create configmaps -n "${GRAFANA_NAMESPACE}" >/dev/null
kubectl auth can-i create secrets -n "${GRAFANA_NAMESPACE}" >/dev/null
kubectl auth can-i create persistentvolumeclaims -n "${GRAFANA_NAMESPACE}" >/dev/null

if [[ "${MODE}" == "check" ]]; then
    echo
    echo "Check mode complete. No resources were changed."
    exit 0
fi

echo
echo "[3/6] Creating namespace and admin secret..."
kubectl create namespace "${GRAFANA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "${GRAFANA_NAMESPACE}" \
    app.kubernetes.io/part-of=octo-demo-observability \
    app.kubernetes.io/component=dashboards \
    octo.oracle.com/tier=test --overwrite >/dev/null

: "${GRAFANA_ADMIN_USER:=admin}"
: "${GRAFANA_ADMIN_PASSWORD:=$(random_base64 18)}"
# Bearer token the Infinity datasource presents to the GenAI API. Reuse the AI
# Studio internal-service key if available; otherwise generate a placeholder.
: "${GENAI_API_TOKEN:=$(random_base64 24)}"

kubectl -n "${GRAFANA_NAMESPACE}" create secret generic grafana-secrets \
    --from-literal "admin-user=${GRAFANA_ADMIN_USER}" \
    --from-literal "admin-password=${GRAFANA_ADMIN_PASSWORD}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo
echo "[4/6] Building dashboards ConfigMap (datasource UIDs substituted)..."
dash_stage="$(mktemp -d)"
cleanup() { rm -rf "${dash_stage}"; }
trap cleanup EXIT
for f in "${DASHBOARD_DIR}"/*.json; do
    sed \
        -e "s|__CP_API_BASE__|${GENAI_API_BASE}|g" \
        -e "s|__INFINITY_UID__|control-plane-api|g" \
        -e "s|__OCI_UID__|oci-metrics|g" \
        "$f" > "${dash_stage}/$(basename "$f")"
done
kubectl -n "${GRAFANA_NAMESPACE}" create configmap grafana-dashboards \
    --from-file="${dash_stage}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo
echo "[5/6] Rendering and applying Grafana..."
export GRAFANA_NAMESPACE GRAFANA_PUBLIC_URL GRAFANA_HOSTNAME GRAFANA_STORAGE_CLASS \
    GRAFANA_STORAGE OCI_REGION OCI_LB_SUBNET_OCID OCI_LB_SHAPE_FLEX_MIN \
    OCI_LB_SHAPE_FLEX_MAX GENAI_API_BASE GENAI_API_TOKEN

if [[ "${MODE}" == "dry-run" ]]; then
    envsubst < "${MANIFEST}" | kubectl apply --dry-run=server -f -
    echo "Dry run complete. No resources were persisted."
    exit 0
fi

envsubst < "${MANIFEST}" | kubectl apply -f -

echo
echo "[6/6] Waiting for Grafana..."
kubectl rollout status deployment/grafana -n "${GRAFANA_NAMESPACE}" --timeout=300s

echo
echo "LoadBalancer status:"
kubectl get svc grafana-lb -n "${GRAFANA_NAMESPACE}"

echo
echo "================================================================"
echo " Done. Point DNS:"
echo "   ${GRAFANA_HOSTNAME}  A/CNAME  -> grafana-lb external IP/hostname"
echo
echo " Admin user: ${GRAFANA_ADMIN_USER}  (password stored only in grafana-secrets)"
echo " Validate:"
echo "   kubectl -n ${GRAFANA_NAMESPACE} port-forward svc/grafana 33001:3000"
echo "   curl -fsS http://127.0.0.1:33001/api/health"
echo "================================================================"

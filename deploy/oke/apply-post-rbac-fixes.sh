#!/usr/bin/env bash
# Apply the post-RBAC OKE fixes that do not require cluster-admin once the
# octo-drone-shop namespace RoleBinding is in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
Usage: apply-post-rbac-fixes.sh [--help]

Restart the shop Deployment and apply the Langfuse->OCI Monitoring sync CronJob,
once the octo-drone-shop namespace RoleBinding is in place. Read-only preflight
by default (kubectl auth can-i + server dry-run); set APPLY=true to perform it.

Env: APPLY (default false), K8S_NAMESPACE_SHOP (default octo-drone-shop),
     SHOP_DEPLOYMENT (default octo-drone-shop), OCIR_REPO + OCI_REGION (required
     to render the CronJob image/region).
USAGE
    exit 0
    ;;
esac

: "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
: "${SHOP_DEPLOYMENT:=octo-drone-shop}"
: "${APPLY:=false}"
# Required to render the CronJob image/region — fail fast rather than ship an
# empty image path (image: /octo-genai-studio:latest).
: "${OCIR_REPO:?set OCIR_REPO before running (e.g. <region>.ocir.io/<tenancy>)}"
: "${OCI_REGION:?set OCI_REGION before running (e.g. us-phoenix-1)}"

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required tool: $1" >&2
    exit 1
  }
}

require_tool kubectl
require_tool envsubst

can_i() {
  # First line only (the answer is 'yes'/'no'); drops any stdout warning that
  # would otherwise corrupt the exact-match comparison. The caller word-splits
  # $check intentionally so "get pods" arrives as two args ($@).
  kubectl auth can-i "$@" -n "${K8S_NAMESPACE_SHOP}" 2>/dev/null | head -1 | tr -d '[:space:]'
}

echo "Checking Kubernetes authorization in namespace ${K8S_NAMESPACE_SHOP}..."
# Cover every verb the operation exercises: rollout restart/status read+patch the
# Deployment; kubectl apply of an existing CronJob get+patches it (not just create).
for check in \
  "get pods" \
  "get deployments.apps" \
  "patch deployments.apps" \
  "get cronjobs.batch" \
  "create cronjobs.batch" \
  "patch cronjobs.batch"; do
  if [[ "$(can_i ${check})" != "yes" ]]; then
    echo "Missing RBAC permission: ${check} in namespace ${K8S_NAMESPACE_SHOP}" >&2
    echo "Apply deploy/k8s/oke/rbac/octo-drone-shop-deployer-rolebinding.yaml from an admin context first." >&2
    exit 1
  fi
done

if [[ "${APPLY}" != "true" ]]; then
  echo "DRY RUN: set APPLY=true to restart ${SHOP_DEPLOYMENT} and apply the Langfuse sync CronJob."
  envsubst < "${REPO_ROOT}/shop/deploy/k8s/genai-studio-langfuse-sync-cronjob.yaml" \
    | kubectl apply -n "${K8S_NAMESPACE_SHOP}" --dry-run=server -f -
  exit 0
fi

echo "Restarting deployment/${SHOP_DEPLOYMENT} in namespace ${K8S_NAMESPACE_SHOP}..."
kubectl rollout restart "deploy/${SHOP_DEPLOYMENT}" -n "${K8S_NAMESPACE_SHOP}"

echo "Applying Langfuse -> OCI Monitoring sync CronJob..."
envsubst < "${REPO_ROOT}/shop/deploy/k8s/genai-studio-langfuse-sync-cronjob.yaml" | kubectl apply -n "${K8S_NAMESPACE_SHOP}" -f -

echo "Waiting for ${SHOP_DEPLOYMENT} rollout..."
kubectl rollout status "deploy/${SHOP_DEPLOYMENT}" -n "${K8S_NAMESPACE_SHOP}" --timeout=240s

echo "Post-RBAC OKE fixes applied."

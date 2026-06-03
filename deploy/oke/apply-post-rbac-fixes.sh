#!/usr/bin/env bash
# Apply the post-RBAC OKE fixes that do not require cluster-admin once the
# octo-drone-shop namespace RoleBinding is in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

: "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
: "${SHOP_DEPLOYMENT:=octo-drone-shop}"
: "${APPLY:=false}"

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required tool: $1" >&2
    exit 1
  }
}

require_tool kubectl
require_tool envsubst

can_i() {
  kubectl auth can-i "$@" -n "${K8S_NAMESPACE_SHOP}" 2>/dev/null | tr -d '\n'
}

echo "Checking Kubernetes authorization in namespace ${K8S_NAMESPACE_SHOP}..."
for check in \
  "get pods" \
  "patch deployments.apps" \
  "create cronjobs.batch"; do
  if [[ "$(can_i ${check})" != "yes" ]]; then
    echo "Missing RBAC permission: ${check} in namespace ${K8S_NAMESPACE_SHOP}" >&2
    echo "Apply deploy/k8s/oke/rbac/octo-drone-shop-deployer-rolebinding.yaml from an admin context first." >&2
    exit 1
  fi
done

if [[ "${APPLY}" != "true" ]]; then
  echo "DRY RUN: set APPLY=true to restart ${SHOP_DEPLOYMENT} and apply the Langfuse sync CronJob."
  envsubst < "${REPO_ROOT}/shop/deploy/k8s/genai-studio-langfuse-sync-cronjob.yaml" \
    | kubectl apply --dry-run=server -f -
  exit 0
fi

echo "Restarting deployment/${SHOP_DEPLOYMENT} in namespace ${K8S_NAMESPACE_SHOP}..."
kubectl rollout restart "deploy/${SHOP_DEPLOYMENT}" -n "${K8S_NAMESPACE_SHOP}"

echo "Applying Langfuse -> OCI Monitoring sync CronJob..."
envsubst < "${REPO_ROOT}/shop/deploy/k8s/genai-studio-langfuse-sync-cronjob.yaml" | kubectl apply -f -

echo "Waiting for ${SHOP_DEPLOYMENT} rollout..."
kubectl rollout status "deploy/${SHOP_DEPLOYMENT}" -n "${K8S_NAMESPACE_SHOP}" --timeout=240s

echo "Post-RBAC OKE fixes applied."

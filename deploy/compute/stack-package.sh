#!/usr/bin/env bash
# Package the two-instance Compute deployment as an OCI Resource Manager zip.
#
# Usage:
#   ./deploy/compute/stack-package.sh [--output-dir DIR]
#
# Output: deploy/compute/build/octo-compute-stack.zip

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
case "$#" in
    0) BUILD_DIR="${SCRIPT_DIR}/build" ;;
    2) [[ "$1" == "--output-dir" && -n "$2" ]] || exit 2
       BUILD_DIR="$2" ;;
    *) echo "Expected --output-dir DIR" >&2; exit 2 ;;
esac
mkdir -p "${BUILD_DIR}"
BUILD_DIR="$(cd "${BUILD_DIR}" && pwd)"
OUT_ZIP="${BUILD_DIR}/octo-compute-stack.zip"

STAGE_DIR="$(mktemp -d "${BUILD_DIR}/stage.XXXXXX")"
TMP_ZIP="${BUILD_DIR}/octo-compute-stack.$$.zip"
cleanup() {
    rm -rf "${STAGE_DIR}" "${TMP_ZIP}"
}
trap cleanup EXIT

cp -R "${SCRIPT_DIR}/terraform/"*.tf "${STAGE_DIR}/"
cp "${SCRIPT_DIR}/terraform/schema.yaml" "${STAGE_DIR}/schema.yaml"
mkdir -p "${STAGE_DIR}/cloud-init"
cp "${SCRIPT_DIR}/terraform/cloud-init/compute.yaml.tftpl" "${STAGE_DIR}/cloud-init/"
mkdir -p "${STAGE_DIR}/bootstrap/nginx" "${STAGE_DIR}/bootstrap/systemd"
cp "${SCRIPT_DIR}/install.sh" "${STAGE_DIR}/bootstrap/install.sh"
cp "${SCRIPT_DIR}/app-compose.yml" "${STAGE_DIR}/bootstrap/app-compose.yml"
cp "${SCRIPT_DIR}/runtime.env.template" "${STAGE_DIR}/bootstrap/runtime.env.template"
cp "${SCRIPT_DIR}/synthetic-users-job.sh" "${STAGE_DIR}/bootstrap/synthetic-users-job.sh"
cp "${SCRIPT_DIR}/nginx/app.conf.template" "${STAGE_DIR}/bootstrap/nginx/app.conf.template"
cp "${SCRIPT_DIR}/systemd/octo-compute.service" "${STAGE_DIR}/bootstrap/systemd/octo-compute.service"
cp "${SCRIPT_DIR}/systemd/octo-java-apm.service" "${STAGE_DIR}/bootstrap/systemd/octo-java-apm.service"
cp "${SCRIPT_DIR}/systemd/octo-podman.service" "${STAGE_DIR}/bootstrap/systemd/octo-podman.service"
cp "${SCRIPT_DIR}/systemd/octo-synthetic-users.service" "${STAGE_DIR}/bootstrap/systemd/octo-synthetic-users.service"
cp "${SCRIPT_DIR}/systemd/octo-synthetic-users.timer" "${STAGE_DIR}/bootstrap/systemd/octo-synthetic-users.timer"
cp "${SCRIPT_DIR}/systemd/octo-tetragon.service" "${STAGE_DIR}/bootstrap/systemd/octo-tetragon.service"
cp "${SCRIPT_DIR}/systemd/octo-workflow-gateway.service" "${STAGE_DIR}/bootstrap/systemd/octo-workflow-gateway.service"

(
    cd "${REPO_ROOT}/deploy/terraform"
    modules=(modules/atp modules/apm_domain modules/logging modules/security modules/stack_monitoring modules/waf)
    for module in "${modules[@]}"; do
        while IFS= read -r -d '' module_file; do
            mkdir -p "${STAGE_DIR}/modules-shared/$(dirname "$module_file")"
            cp "$module_file" "${STAGE_DIR}/modules-shared/$module_file"
        done < <(find "$module" -type f -name '*.tf' ! -name backend.tf ! -path '*/.*' -print0)
    done
)

python3 - "${STAGE_DIR}" <<'PY'
import pathlib
import re
import sys

stage = pathlib.Path(sys.argv[1])
for tf in stage.glob("*.tf"):
    text = tf.read_text(encoding="utf-8")
    text = re.sub(
        r'source\s*=\s*"\.\./\.\./terraform/modules/',
        'source = "./modules-shared/modules/',
        text,
    )
    tf.write_text(text, encoding="utf-8")
PY

# Resource Manager injects provider auth/region. A local config profile would
# fail in the managed service.
cat >"${STAGE_DIR}/provider.tf" <<'EOF'
provider "oci" {}
EOF

(cd "${STAGE_DIR}" && zip -qr "${TMP_ZIP}" . -x '*/.terraform/*' '*/.terraform.lock.hcl')
mv "${TMP_ZIP}" "${OUT_ZIP}"

echo "Packaged: ${OUT_ZIP}"
echo
echo "Next: upload in OCI Console → Resource Manager → Stacks → Create Stack"
echo "      (source = My Configuration, file = octo-compute-stack.zip)"

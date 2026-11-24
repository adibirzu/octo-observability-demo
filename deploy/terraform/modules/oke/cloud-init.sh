#!/bin/bash
# Future managed nodes only. Do not run manually on an existing worker.
set -euo pipefail
case "${1:-}" in
  -h|--help)
    echo "Usage: cloud-init.sh (OKE future-node bootstrap only)"
    exit 0
    ;;
  "") ;;
  *) echo "Unexpected argument" >&2; exit 2 ;;
esac
curl --fail --retry 3 -H "Authorization: Bearer Oracle" -L0 \
  http://169.254.169.254/opc/v2/instance/metadata/oke_init_script \
  | base64 --decode > /var/run/oke-init.sh
bash /var/run/oke-init.sh --kubelet-extra-args "--image-gc-high-threshold=75 --image-gc-low-threshold=60"

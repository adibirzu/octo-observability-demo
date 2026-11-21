#!/usr/bin/env bash
# Package the shop-only OCI Resource Manager stack.
# Usage: stack-package.sh [--output-dir DIR]
# Output: build/octo-stack.zip next to this script by default.

set -euo pipefail

case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [--output-dir DIR]"
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/../../../tools/package_orm_stack.sh" "${SCRIPT_DIR}" "$@"

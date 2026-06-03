#!/usr/bin/env bash
# Activate payment decline attributes in an OCI APM domain.
#
# Dry-run by default. To apply:
#
#   APM_DOMAIN_ID=<APM_DOMAIN_OCID> ./deploy/oci/apm/activate_payment_attributes.sh --apply
#
# Or discover by display name:
#
#   COMPARTMENT_ID=<COMPARTMENT_OCID> \
#   APM_DOMAIN_DISPLAY_NAME=octo-emdemo-apm \
#   ./deploy/oci/apm/activate_payment_attributes.sh --apply

set -euo pipefail

DRY_RUN=true
case "${1:-}" in
  -h|--help)
    sed -n '1,18p' "$0"
    exit 0
    ;;
  --apply) DRY_RUN=false ;;
  --dry-run|"") DRY_RUN=true ;;
  *)
    echo "Usage: $0 [--dry-run|--apply]" >&2
    exit 2
    ;;
esac

OCI_PROFILE="${OCI_CLI_PROFILE:-${OCI_PROFILE:-DEFAULT}}"
APM_DOMAIN_DISPLAY_NAME="${APM_DOMAIN_DISPLAY_NAME:-octo-emdemo-apm}"
APM_DOMAIN_ID="${APM_DOMAIN_ID:-}"
COMPARTMENT_ID="${COMPARTMENT_ID:-}"
APM_PAYMENT_INCLUDE_NUMERIC="${APM_PAYMENT_INCLUDE_NUMERIC:-true}"

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required tool: $1" >&2
    exit 1
  }
}

string_attribute_details='[
  {
    "attributeName": "payment.antifraud_reasons",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.verification.decision",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.error_code",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.decision_source",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  }
]'

all_attribute_details='[
  {
    "attributeName": "payment.antifraud_reasons",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.verification.decision",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.error_code",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.decision_source",
    "attributeType": "STRING",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  },
  {
    "attributeName": "payment.risk_score",
    "attributeType": "NUMERIC",
    "attributeNamespace": "TRACES",
    "unit": "NONE"
  }
]'

if [[ "${APM_PAYMENT_INCLUDE_NUMERIC}" == "true" ]]; then
  attribute_details="${all_attribute_details}"
else
  attribute_details="${string_attribute_details}"
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "DRY RUN: would activate payment decline attributes in APM domain '${APM_DOMAIN_DISPLAY_NAME}'."
  if [[ "${APM_PAYMENT_INCLUDE_NUMERIC}" != "true" ]]; then
    echo "Numeric attributes are excluded because APM_PAYMENT_INCLUDE_NUMERIC=false."
  fi
  printf '%s\n' "${attribute_details}"
  exit 0
fi

require_tool oci

if [[ -z "${APM_DOMAIN_ID}" ]]; then
  if [[ -z "${COMPARTMENT_ID}" ]]; then
    echo "Set APM_DOMAIN_ID, or set COMPARTMENT_ID plus APM_DOMAIN_DISPLAY_NAME." >&2
    exit 2
  fi
  APM_DOMAIN_ID="$(
    oci apm-control-plane apm-domain list \
      --profile "${OCI_PROFILE}" \
      --compartment-id "${COMPARTMENT_ID}" \
      --display-name "${APM_DOMAIN_DISPLAY_NAME}" \
      --lifecycle-state ACTIVE \
      --query 'data[0].id // `""`' \
      --raw-output
  )"
fi

if [[ -z "${APM_DOMAIN_ID}" || "${APM_DOMAIN_ID}" == "null" ]]; then
  echo "No ACTIVE APM domain found for display name '${APM_DOMAIN_DISPLAY_NAME}'." >&2
  exit 1
fi

echo "Activating payment decline attributes in APM domain '${APM_DOMAIN_DISPLAY_NAME}'..."
oci apm-traces attributes activate \
  --profile "${OCI_PROFILE}" \
  --apm-domain-id "${APM_DOMAIN_ID}" \
  --attribute-details "${attribute_details}" \
  --output json

echo "Activation requested. APM Trace Explorer can take a few minutes to refresh attribute search caches."

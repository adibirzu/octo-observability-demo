#!/usr/bin/env bash
###############################################################################
# security-modules.sh — enable + validate the OCI Data Safe and Cloud Guard
# Terraform submodules against ANY OCI deployment.
#
#   ./security-modules.sh <command> --profile <oci_profile> [options]
#
# Commands:
#   discover   Read-only: probe the tenancy and write vars/<profile>.tfvars.
#   plan       Show the Terraform plan (runs discover if needed).
#   apply      Create/update the security resources (asks unless --auto-approve).
#   verify     Read-only: confirm the live resources are ACTIVE via the OCI CLI.
#   status     Show terraform state + outputs for the profile.
#   destroy    Tear down everything this harness created for the profile.
#
# Options:
#   --profile P            (required) OCI CLI profile / tenancy.
#   --region R             Region + Cloud Guard reporting region (default: from ~/.oci/config).
#   --compartment OCID     Parent compartment for the dedicated sec compartment (default: tenancy root).
#   --watch-compartment O  Compartment Cloud Guard watches (default: the created sec compartment).
#   --db NAME|OCID         Data Safe target ADB (default: auto-pick a free, registerable ADB).
#   --skip-data-safe       Do not register a Data Safe target.
#   --skip-cloud-guard     Do not create Cloud Guard resources.
#   --assessments          Also create Security + User Assessment baselines.
#   --auto-remediate       Phase 3: flip responder rules to ENABLED (default notify-only).
#   --sec-name NAME        Dedicated compartment name (default: octo-sec-validation).
#   --auto-approve         apply/destroy without the interactive prompt.
#
# State + generated tfvars are per-profile and gitignored (state/, vars/).
###############################################################################
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---- defaults / arg parsing ------------------------------------------------
CMD="${1:-}"; shift || true
# --help / -h as the command prints usage and exits preflight-free (a command is
# the first positional, so without this --help is read as an unknown command).
case "${CMD}" in
  -h|--help)
    echo "Usage: ./security-modules.sh <discover|plan|apply|verify|status|destroy> --profile <oci_profile> [options]"
    sed -n '2,40p' "$0"
    exit 0
    ;;
esac
PROFILE=""; REGION=""; PARENT_CMPT=""; WATCH_CMPT=""; DB=""
SKIP_DS=0; SKIP_CG=0; ASSESS=0; AUTOREM=0; AUTO_APPROVE=0
SEC_NAME="octo-sec-validation"

while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2;;
    --region) REGION="$2"; shift 2;;
    --compartment) PARENT_CMPT="$2"; shift 2;;
    --watch-compartment) WATCH_CMPT="$2"; shift 2;;
    --db) DB="$2"; shift 2;;
    --sec-name) SEC_NAME="$2"; shift 2;;
    --skip-data-safe) SKIP_DS=1; shift;;
    --skip-cloud-guard) SKIP_CG=1; shift;;
    --assessments) ASSESS=1; shift;;
    --auto-remediate) AUTOREM=1; shift;;
    --auto-approve) AUTO_APPROVE=1; shift;;
    -h|--help) sed -n '2,40p' "$0"; exit 0;;
    *) echo "Unknown option: $1" >&2; exit 2;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date -u +%H:%M:%S)] $*"; }
mask() { sed -E 's/(ocid1\.[a-z]+\.oc1[._a-z0-9-]*\.)[a-z0-9]{6}[a-z0-9]+([a-z0-9]{4})/\1XXXX…\2/g'; }

# Read terraform outputs straight from a per-profile state file (terraform output
# -state is unreliable in 1.5). $2 = "name" | "name.subkey" | "" (dump all).
state_output() {
  python3 - "$1" "$2" <<'PY'
import json, sys
sf, key = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(sf))
except Exception:
    sys.exit(0)
outs = {k: v.get("value") for k, v in d.get("outputs", {}).items()}
if not key:
    print(json.dumps(outs, indent=2)); sys.exit(0)
parts = key.split(".")
v = outs.get(parts[0])
for p in parts[1:]:
    v = v.get(p) if isinstance(v, dict) else None
print(v if v not in (None, False) else "")
PY
}

[ -n "$CMD" ] || die "missing command. Try: $0 --help"
[ -n "$PROFILE" ] || die "--profile is required"
command -v oci >/dev/null || die "oci CLI not found"
command -v terraform >/dev/null || die "terraform not found"

TFVARS="vars/${PROFILE}.tfvars"
STATE="state/${PROFILE}.tfstate"
mkdir -p vars state

oci_q() { oci "$@" --profile "$PROFILE" 2>/dev/null; }

resolve_region() {
  [ -n "$REGION" ] && return
  REGION="$(awk -v p="[$PROFILE]" '$0==p{f=1;next}/^\[/{f=0}f&&/^region/{print $3}' ~/.oci/config | head -1)"
  [ -n "$REGION" ] || REGION="$(oci_q iam region-subscription list --query 'data[?("is-home-region")].["region-name"]|[0]' --raw-output)"
  [ -n "$REGION" ] || die "could not resolve region; pass --region"
}

tenancy_ocid() {
  awk -v p="[$PROFILE]" '$0==p{f=1;next}/^\[/{f=0}f&&/^tenancy/{print $3}' ~/.oci/config | head -1
}

# ---- discovery -------------------------------------------------------------
discover() {
  resolve_region
  local TEN; TEN="$(tenancy_ocid)"; [ -n "$TEN" ] || die "no tenancy OCID for profile $PROFILE in ~/.oci/config"
  [ -n "$PARENT_CMPT" ] || PARENT_CMPT="$TEN"
  log "tenancy + region: $(echo "$TEN" | mask) / $REGION"

  # Cloud Guard enablement — only enable the service if it is OFF.
  local CG_STATUS CG_ENABLE_SVC=false
  if [ "$SKIP_CG" -eq 0 ]; then
    CG_STATUS="$(oci_q cloud-guard configuration get --compartment-id "$TEN" --query 'data.status' --raw-output || true)"
    if [ "$CG_STATUS" != "ENABLED" ]; then CG_ENABLE_SVC=true; log "Cloud Guard not enabled → will enable (reporting_region=$REGION)"; else log "Cloud Guard already ENABLED → service enablement off"; fi
  fi

  # Managed recipe OCIDs (per tenancy).
  local CFG ACT THR RSP
  if [ "$SKIP_CG" -eq 0 ]; then
    CFG="$(oci_q cloud-guard detector-recipe list --compartment-id "$TEN" --all --query 'data.items[?detector==`IAAS_CONFIGURATION_DETECTOR`&&owner==`ORACLE`]|[0].id' --raw-output)"
    ACT="$(oci_q cloud-guard detector-recipe list --compartment-id "$TEN" --all --query 'data.items[?detector==`IAAS_ACTIVITY_DETECTOR`&&owner==`ORACLE`]|[0].id' --raw-output)"
    THR="$(oci_q cloud-guard detector-recipe list --compartment-id "$TEN" --all --query 'data.items[?detector==`IAAS_THREAT_DETECTOR`&&owner==`ORACLE`]|[0].id' --raw-output)"
    RSP="$(oci_q cloud-guard responder-recipe list --compartment-id "$TEN" --all --query 'data.items[?owner==`ORACLE`]|[0].id' --raw-output)"
    [ -n "$CFG" ] && [ "$CFG" != None ] || die "no Oracle-managed Configuration detector recipe found (is Cloud Guard available in $REGION?)"
  fi

  # Data Safe target ADB — explicit --db, else auto-pick a registerable one.
  local DS_ENABLE=true DB_ID="" DS_PE=false PE_VCN="" PE_SUBNET=""
  if [ "$SKIP_DS" -eq 1 ]; then DS_ENABLE=false; log "Data Safe skipped (--skip-data-safe)"; fi
  if [ "$DS_ENABLE" = true ]; then
    if [ -n "$DB" ]; then
      if [[ "$DB" == ocid1.autonomousdatabase.* ]]; then DB_ID="$DB"
      else DB_ID="$(oci_q search resource structured-search --query-text "query autonomousdatabase resources where displayName = '$DB'" --query 'data.items[?("lifecycle-state")==`AVAILABLE`]|[0].identifier' --raw-output)"; fi
      [ -n "$DB_ID" ] && [ "$DB_ID" != None ] || die "--db '$DB' not found / not AVAILABLE"
    else
      log "auto-picking a registerable ADB (NOT_REGISTERED, public-access preferred)…"
      local ids; ids="$(oci_q search resource structured-search --query-text "query autonomousdatabase resources" --query 'data.items[?("lifecycle-state")==`AVAILABLE`].identifier' --raw-output | tr -d '[],"')"
      local fallback=""
      for id in $ids; do
        local st sub; st="$(oci_q db autonomous-database get --autonomous-database-id "$id" --query 'data."data-safe-status"' --raw-output)"
        [ "$st" = "NOT_REGISTERED" ] || continue
        sub="$(oci_q db autonomous-database get --autonomous-database-id "$id" --query 'data."subnet-id"' --raw-output)"
        if [ -z "$sub" ] || [ "$sub" = None ]; then DB_ID="$id"; break; else [ -z "$fallback" ] && fallback="$id"; fi
      done
      if [ -z "$DB_ID" ] && [ -n "$fallback" ]; then DB_ID="$fallback"; log "only private (VCN-bound) candidates → will create a Data Safe private endpoint"; fi
      if [ -z "$DB_ID" ]; then DS_ENABLE=false; log "no registerable ADB found → Data Safe skipped (pass --db to override)"; fi
    fi
    # Private ADB → auto-enable a private endpoint in its VCN/subnet.
    if [ -n "$DB_ID" ]; then
      local sub; sub="$(oci_q db autonomous-database get --autonomous-database-id "$DB_ID" --query 'data."subnet-id"' --raw-output)"
      if [ -n "$sub" ] && [ "$sub" != None ]; then
        DS_PE=true; PE_SUBNET="$sub"
        PE_VCN="$(oci_q network subnet get --subnet-id "$sub" --query 'data."vcn-id"' --raw-output)"
        log "target ADB is VCN-bound → private endpoint on $(echo "$PE_VCN" | mask)"
      fi
    fi
  fi

  # Write the per-profile tfvars (gitignored).
  cat > "$TFVARS" <<EOF
# GENERATED by security-modules.sh discover for profile '$PROFILE'. Do not commit.
oci_profile                = "$PROFILE"
region                     = "$REGION"
parent_compartment_id      = "$PARENT_CMPT"
sec_compartment_name       = "$SEC_NAME"
watch_compartment_id       = "${WATCH_CMPT}"

enable_data_safe              = $DS_ENABLE
data_safe_atp_id              = "${DB_ID}"
enable_assessments            = $([ "$ASSESS" -eq 1 ] && echo true || echo false)
data_safe_enable_private_endpoint   = $DS_PE
data_safe_private_endpoint_vcn_id   = "${PE_VCN}"
data_safe_private_endpoint_subnet_id = "${PE_SUBNET}"

enable_cloud_guard            = $([ "$SKIP_CG" -eq 1 ] && echo false || echo true)
enable_cloud_guard_service    = $CG_ENABLE_SVC
auto_remediate                = $([ "$AUTOREM" -eq 1 ] && echo true || echo false)
config_source_recipe_id       = "${CFG:-}"
activity_source_recipe_id     = "${ACT:-}"
threat_source_recipe_id       = "${THR:-}"
responder_source_recipe_id    = "${RSP:-}"
EOF
  log "wrote $TFVARS:"
  mask < "$TFVARS" | sed 's/^/    /'
}

tf() { terraform "$@"; }
ensure_init() { [ -d .terraform ] || tf init -input=false >/dev/null; }
ensure_discovered() { [ -f "$TFVARS" ] || { log "no $TFVARS yet → discovering"; discover; }; }

case "$CMD" in
  discover) discover;;
  plan)    ensure_init; ensure_discovered; tf plan -input=false -var-file="$TFVARS" -state="$STATE" | mask;;
  apply)
    ensure_init; ensure_discovered
    if [ "$AUTO_APPROVE" -eq 1 ]; then tf apply -input=false -auto-approve -var-file="$TFVARS" -state="$STATE" | mask
    else tf apply -input=false -var-file="$TFVARS" -state="$STATE"; fi;;
  destroy)
    ensure_init; ensure_discovered
    if [ "$AUTO_APPROVE" -eq 1 ]; then tf destroy -input=false -auto-approve -var-file="$TFVARS" -state="$STATE" | mask
    else tf destroy -input=false -var-file="$TFVARS" -state="$STATE"; fi;;
  status)
    ensure_init
    tf state list -state="$STATE" 2>/dev/null || echo "(no state for $PROFILE)"
    echo "--- outputs ---"
    state_output "$STATE" "" | mask;;
  verify)
    ensure_init
    log "verifying live resources for profile ${PROFILE}"
    SEC="$(state_output "$STATE" sec_compartment_id)"
    [ -n "$SEC" ] || die "no state/outputs for $PROFILE — run apply first"
    DSID="$(state_output "$STATE" data_safe.target_database_id)"
    CGID="$(state_output "$STATE" cloud_guard.target_id)"
    if [ -n "$DSID" ]; then oci_q data-safe target-database get --target-database-id "$DSID" --query 'data.{DataSafe:"display-name",state:"lifecycle-state"}' --output table | grep -v ocid1; else echo "(no Data Safe target)"; fi
    if [ -n "$CGID" ]; then oci_q cloud-guard target get --target-id "$CGID" --query 'data.{CloudGuard:"display-name",state:"lifecycle-state",detectors:length("target-detector-recipes")}' --output table | grep -v ocid1; else echo "(no Cloud Guard target)"; fi;;
  *) die "unknown command '$CMD'. Try: $0 --help";;
esac

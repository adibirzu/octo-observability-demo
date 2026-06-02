###############################################################################
# OCI Data Safe — register OCTOATP as a Data Safe target and (optionally) turn
# on the unified audit trail + Security/User Assessment baselines.
#
# SCAFFOLD: resources are defined but each beyond bare target registration is
# gated behind a toggle (see variables.tf). Defaults keep this submodule a
# registration-only scaffold. Promote to cap (staging) first, then emdemo.
#
# No OCIDs/IPs/datakeys are hardcoded — every coordinate is a variable.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

###############################################################################
# 0. Service enablement (idempotent). Enabling Data Safe is a one-per-region
#    operation; gate it so re-applying in a region that already has it on is a
#    no-op driven by an operator toggle rather than always present.
###############################################################################

resource "oci_data_safe_data_safe_configuration" "this" {
  count          = var.enable_data_safe_service ? 1 : 0
  compartment_id = var.compartment_id
  is_enabled     = var.is_enabled
}

###############################################################################
# 1. Target database registration — OCTOATP by its Autonomous DB OCID.
#    This is the anchor resource; everything else references its id.
###############################################################################

resource "oci_data_safe_target_database" "octoatp" {
  compartment_id = var.compartment_id
  display_name   = var.target_display_name
  description    = "Data Safe target registration for the shared Autonomous Database (OCTOATP)."

  database_details {
    database_type          = var.database_type
    infrastructure_type    = var.infrastructure_type
    autonomous_database_id = var.atp_id
  }

  freeform_tags = var.freeform_tags

  lifecycle {
    precondition {
      condition     = var.atp_id != ""
      error_message = "atp_id (Autonomous Database OCID) is required to register a Data Safe target database."
    }
  }
}

###############################################################################
# 2. Unified audit — audit policy + audit profile + audit trail for the target.
#    Gated behind enable_audit.
###############################################################################

# The audit policy + audit trail resources manage policy/trail OCIDs that Data
# Safe materialises *after* a target is registered (they are not derivable from
# the target resource at plan time). They are therefore gated behind passed-in
# OCIDs so a fresh registration is a valid plan; populate these on a second
# apply once `oci data-safe audit-policy list` / `audit-trail list` return them.
resource "oci_data_safe_audit_policy" "octoatp" {
  count           = var.enable_audit && var.audit_policy_id != "" ? 1 : 0
  audit_policy_id = var.audit_policy_id
  compartment_id  = var.compartment_id
  freeform_tags   = var.freeform_tags
}

resource "oci_data_safe_audit_profile" "octoatp" {
  count                 = var.enable_audit ? 1 : 0
  compartment_id        = var.compartment_id
  target_id             = oci_data_safe_target_database.octoatp.id
  target_type           = var.audit_profile_target_type
  is_paid_usage_enabled = false
  online_months         = var.audit_online_months
  offline_months        = var.audit_offline_months
  description           = "Audit profile for OCTOATP — controls online/offline retention."
  freeform_tags         = var.freeform_tags
}

resource "oci_data_safe_audit_trail" "octoatp" {
  count                 = var.enable_audit && var.audit_trail_id != "" ? 1 : 0
  audit_trail_id        = var.audit_trail_id
  is_auto_purge_enabled = var.audit_trail_is_auto_purge_enabled
  description           = "Audit trail collection for OCTOATP."
  freeform_tags         = var.freeform_tags
}

###############################################################################
# 3. Assessments — Security Assessment + User Assessment baselines.
#    Gated independently so an operator can enable one without the other.
###############################################################################

resource "oci_data_safe_security_assessment" "octoatp" {
  count                   = var.enable_security_assessment ? 1 : 0
  compartment_id          = var.compartment_id
  target_id               = oci_data_safe_target_database.octoatp.id
  display_name            = "${var.name_prefix}-security-assessment"
  description             = "Baseline Security Assessment for OCTOATP."
  is_assessment_scheduled = var.assessment_schedule != ""
  schedule                = var.assessment_schedule != "" ? var.assessment_schedule : null
  freeform_tags           = var.freeform_tags
}

resource "oci_data_safe_user_assessment" "octoatp" {
  count                   = var.enable_user_assessment ? 1 : 0
  compartment_id          = var.compartment_id
  target_id               = oci_data_safe_target_database.octoatp.id
  display_name            = "${var.name_prefix}-user-assessment"
  description             = "Baseline User Assessment for OCTOATP."
  is_assessment_scheduled = var.assessment_schedule != ""
  schedule                = var.assessment_schedule != "" ? var.assessment_schedule : null
  freeform_tags           = var.freeform_tags
}

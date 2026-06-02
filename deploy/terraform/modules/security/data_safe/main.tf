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
# 0b. Data Safe private endpoint — REQUIRED to register an Autonomous DB that
#     is locked to a private VCN (subnet_id set, no secure/public access).
#     Off by default; public-access ADBs register without it (current path).
#     Discovered during the cap validation: registering a VCN-bound ADB fails
#     with "Data Safe private endpoint is not found in the VCN" unless a PE
#     exists in that VCN. Pass an existing PE via datasafe_private_endpoint_id
#     instead, or set enable_private_endpoint=true to create one here.
###############################################################################

resource "oci_data_safe_data_safe_private_endpoint" "this" {
  count          = var.enable_private_endpoint ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = var.private_endpoint_display_name
  vcn_id         = var.private_endpoint_vcn_id
  subnet_id      = var.private_endpoint_subnet_id
  nsg_ids        = length(var.private_endpoint_nsg_ids) > 0 ? var.private_endpoint_nsg_ids : null
  description    = "Data Safe private endpoint for registering a VCN-bound target database."
  freeform_tags  = var.freeform_tags

  lifecycle {
    precondition {
      condition     = !var.enable_private_endpoint || (var.private_endpoint_vcn_id != "" && var.private_endpoint_subnet_id != "")
      error_message = "enable_private_endpoint requires private_endpoint_vcn_id and private_endpoint_subnet_id."
    }
  }
}

locals {
  # The PE to wire into the target connection: a passed-in one wins, else the
  # one created above (null when neither). one() yields null when count = 0, so
  # this is safe whether or not the PE resource exists.
  created_private_endpoint_id = one(oci_data_safe_data_safe_private_endpoint.this[*].id)
  effective_private_endpoint_id = (
    var.datasafe_private_endpoint_id != "" ? var.datasafe_private_endpoint_id :
    (local.created_private_endpoint_id != null ? local.created_private_endpoint_id : "")
  )
}

###############################################################################
# 1. Target database registration — OCTOATP by its Autonomous DB OCID.
#    This is the anchor resource; everything else references its id.
#    For a private/VCN ADB a connection_option referencing the PE is emitted;
#    for a public-access ADB the block is omitted (unchanged behavior).
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

  # Private-endpoint connection — only for VCN-bound ADBs. Omitted entirely for
  # public-access ADBs so the simple registration path stays a no-op change.
  dynamic "connection_option" {
    for_each = local.effective_private_endpoint_id != "" ? [1] : []
    content {
      connection_type              = "PRIVATE_ENDPOINT"
      datasafe_private_endpoint_id = local.effective_private_endpoint_id
    }
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

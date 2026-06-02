###############################################################################
# Portable security-modules harness — enable + validate the Data Safe and
# Cloud Guard submodules against ANY OCI deployment (tenancy/profile).
#
# Driven by security-modules.sh, which auto-discovers the per-tenancy inputs
# (managed recipe OCIDs, a registerable ADB, Cloud Guard enablement state) and
# keeps one isolated state file per profile under state/<profile>.tfstate.
#
# Provider profile, region, compartment, and every OCID are variables — nothing
# is tenancy-specific in this file. Sources the shipped modules unchanged.
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

# Profile-parameterized: config_file_profile = "" falls back to the default OCI
# auth chain (env / instance principal). The orchestrator always passes one.
provider "oci" {
  config_file_profile = var.oci_profile != "" ? var.oci_profile : null
  region              = var.region
}

###############################################################################
# Dedicated child compartment the Cloud Guard target watches. Most tenancies
# already have a target on the root compartment (one target per compartment),
# so a fresh child avoids that collision and keeps teardown trivial.
###############################################################################

resource "oci_identity_compartment" "sec" {
  compartment_id = var.parent_compartment_id
  name           = var.sec_compartment_name
  description    = "octo security-module validation (Data Safe + Cloud Guard). Safe to delete."
  enable_delete  = true
  freeform_tags = {
    # Matches the modules' default project tag; keep stable to avoid retagging
    # live resources on profiles already managed by this harness.
    project = "octo-apm-demo"
    purpose = "security-validation"
  }
}

###############################################################################
# Data Safe — register an Autonomous DB as a target (+ optional assessments).
# Gated by enable_data_safe so a tenancy with no registerable ADB can still
# validate Cloud Guard. Private/VCN-bound ADBs are handled via the module's
# private-endpoint inputs.
###############################################################################

module "data_safe" {
  source              = "../../modules/security/data_safe"
  count               = var.enable_data_safe && var.data_safe_atp_id != "" ? 1 : 0
  compartment_id      = oci_identity_compartment.sec.id
  atp_id              = var.data_safe_atp_id
  target_display_name = var.data_safe_target_display_name

  enable_security_assessment = var.enable_assessments
  enable_user_assessment     = var.enable_assessments

  enable_private_endpoint      = var.data_safe_enable_private_endpoint
  datasafe_private_endpoint_id = var.data_safe_private_endpoint_id
  private_endpoint_vcn_id      = var.data_safe_private_endpoint_vcn_id
  private_endpoint_subnet_id   = var.data_safe_private_endpoint_subnet_id
}

###############################################################################
# Cloud Guard — clone the managed detector/responder recipes + attach a target
# on the dedicated compartment. Gated by enable_cloud_guard. Service enablement
# is auto-set by the orchestrator only when the tenancy is not already enabled.
###############################################################################

module "cloud_guard" {
  source                = "../../modules/security/cloud_guard"
  count                 = var.enable_cloud_guard ? 1 : 0
  compartment_id        = oci_identity_compartment.sec.id
  reporting_region      = var.region
  target_compartment_id = var.watch_compartment_id != "" ? var.watch_compartment_id : oci_identity_compartment.sec.id

  enable_cloud_guard_service = var.enable_cloud_guard_service

  clone_detector_recipes    = true
  config_source_recipe_id   = var.config_source_recipe_id
  activity_source_recipe_id = var.activity_source_recipe_id
  threat_source_recipe_id   = var.threat_source_recipe_id

  clone_responder_recipe     = true
  responder_source_recipe_id = var.responder_source_recipe_id

  create_target  = true
  auto_remediate = var.auto_remediate
}

output "sec_compartment_id" {
  value       = oci_identity_compartment.sec.id
  description = "OCID of the dedicated validation compartment."
}

output "data_safe" {
  value = length(module.data_safe) > 0 ? {
    target_database_id  = module.data_safe[0].target_database_id
    target_name         = module.data_safe[0].target_display_name
    private_endpoint_id = module.data_safe[0].private_endpoint_id
  } : null
  description = "Data Safe target coordinates (null when skipped)."
}

output "cloud_guard" {
  value = length(module.cloud_guard) > 0 ? {
    target_id                   = module.cloud_guard[0].target_id
    config_detector_recipe_id   = module.cloud_guard[0].config_detector_recipe_id
    activity_detector_recipe_id = module.cloud_guard[0].activity_detector_recipe_id
    threat_detector_recipe_id   = module.cloud_guard[0].threat_detector_recipe_id
    responder_recipe_id         = module.cloud_guard[0].responder_recipe_id
    responder_rule_state        = module.cloud_guard[0].responder_rule_state
  } : null
  description = "Cloud Guard coordinates (null when skipped)."
}

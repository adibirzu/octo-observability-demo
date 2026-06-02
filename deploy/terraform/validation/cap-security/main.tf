###############################################################################
# Isolated validation root — Data Safe + Cloud Guard modules against cap.
#
# WHY THIS EXISTS (not the repo root stack):
#   The repo-root deploy/terraform/terraform.tfstate describes oci4cca (DEFAULT)
#   resources. Terraform reconciles ALL of state against the provider's auth on
#   every plan/apply, so running the root stack with cap credentials would treat
#   oci4cca's ATP/logging as missing and plan destructive churn. This root has
#   its OWN local state and a cap-PINNED provider, so it can only ever talk to
#   the pbncapgemini (cap / eu-frankfurt-1) staging tenancy. It sources the two
#   security submodules byte-for-byte unchanged — the point is to validate the
#   modules, not fork them.
#
# Reversible: `terraform destroy` here removes only what this root created
#   (the dedicated compartment + Data Safe target + Cloud Guard recipes/target).
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

# Pinned to the cap profile — this root cannot authenticate against emdemo or
# oci4cca even if a stray env var is set. Region is the cap home region.
provider "oci" {
  config_file_profile = "cap"
  region              = var.region
}

###############################################################################
# Dedicated child compartment for the Cloud Guard target.
#
# cap already has a Cloud Guard COMPARTMENT target on the root compartment, and
# OCI permits only one target per compartment. Watching a fresh child sidesteps
# that collision and keeps the whole validation trivially deletable.
###############################################################################

resource "oci_identity_compartment" "sec" {
  compartment_id = var.parent_compartment_id
  name           = var.sec_compartment_name
  description    = "octo-apm-demo security-module validation (Data Safe + Cloud Guard) — cap staging. Safe to delete."
  enable_delete  = true
  freeform_tags = {
    project = "octo-apm-demo"
    purpose = "security-validation"
  }
}

###############################################################################
# Data Safe — Phase 1 minimal: bare target registration of oci-demo-atp.
# Audit policy/trail + assessments stay OFF (module defaults) for the first
# apply so a provider-schema surprise on those resources cannot block the
# anchor target registration. Flip the toggles below for a second apply once
# registration is verified.
###############################################################################

module "data_safe" {
  source              = "../../modules/security/data_safe"
  compartment_id      = oci_identity_compartment.sec.id
  atp_id              = var.data_safe_atp_id
  target_display_name = "octo-apm-demo-octoatp-capval"

  # Phase-2 surfaces — left at module defaults (off) for apply #1:
  enable_security_assessment = var.enable_assessments
  enable_user_assessment     = var.enable_assessments
}

###############################################################################
# Cloud Guard — Phase 1 enablement: clone the three Oracle-managed detector
# recipes + the managed responder recipe, then attach a target on the dedicated
# compartment. Service enablement stays OFF (cap is already enabled). Responders
# stay notify-only (auto_remediate = false) per the plan's Phase 1/2.
###############################################################################

module "cloud_guard" {
  source                = "../../modules/security/cloud_guard"
  compartment_id        = oci_identity_compartment.sec.id
  reporting_region      = var.region
  target_compartment_id = oci_identity_compartment.sec.id

  enable_cloud_guard_service = false # already ENABLED tenancy-wide in cap

  clone_detector_recipes    = true
  config_source_recipe_id   = var.config_source_recipe_id
  activity_source_recipe_id = var.activity_source_recipe_id
  threat_source_recipe_id   = var.threat_source_recipe_id

  clone_responder_recipe     = true
  responder_source_recipe_id = var.responder_source_recipe_id

  create_target  = true
  auto_remediate = false # Phase 1/2 — notify-only
}

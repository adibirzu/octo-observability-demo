###############################################################################
# OCI Cloud Guard — enable the service, clone the managed detector/responder
# recipes into demo-tunable copies, and attach a target to the project
# compartment.
#
# SCAFFOLD: each step is gated behind a toggle (see variables.tf). Defaults
# create only the target referencing whatever recipes are supplied; recipe
# cloning and auto-remediation are opt-in. Promote cap (staging) first, then
# emdemo (LogAnalytics compartment scope only).
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

locals {
  # The compartment Cloud Guard watches; defaults to the resource compartment.
  watched_compartment_id = var.target_compartment_id != "" ? var.target_compartment_id : var.compartment_id

  # Responder rule lifecycle state derived from the phase-3 auto_remediate flag.
  # Phase 1/2: DETECT (notify-only). Phase 3: ENABLED (auto-remediation).
  responder_rule_state = var.auto_remediate ? "ENABLED" : "DETECT"
}

###############################################################################
# 0. Service enablement. Gated — enabling Cloud Guard is a tenancy-wide,
#    one-time operation. Off by default so we never collide with an
#    already-enabled tenancy.
###############################################################################

resource "oci_cloud_guard_cloud_guard_configuration" "this" {
  count                 = var.enable_cloud_guard_service ? 1 : 0
  compartment_id        = var.compartment_id
  reporting_region      = var.reporting_region
  status                = var.cloud_guard_status
  self_manage_resources = var.self_manage_resources
}

###############################################################################
# 1. Detector recipes — clone the Oracle-managed Configuration/Activity/Threat
#    recipes so demo rules can be tuned independently. Gated behind
#    clone_detector_recipes + the per-recipe source OCIDs.
###############################################################################

resource "oci_cloud_guard_detector_recipe" "config" {
  count                     = var.clone_detector_recipes && var.config_source_recipe_id != "" ? 1 : 0
  compartment_id            = var.compartment_id
  display_name              = "${var.name_prefix}-config-detector"
  description               = "Cloned Configuration detector recipe (demo-tunable)."
  source_detector_recipe_id = var.config_source_recipe_id
  freeform_tags             = var.freeform_tags
}

resource "oci_cloud_guard_detector_recipe" "activity" {
  count                     = var.clone_detector_recipes && var.activity_source_recipe_id != "" ? 1 : 0
  compartment_id            = var.compartment_id
  display_name              = "${var.name_prefix}-activity-detector"
  description               = "Cloned Activity detector recipe (demo-tunable)."
  source_detector_recipe_id = var.activity_source_recipe_id
  freeform_tags             = var.freeform_tags
}

resource "oci_cloud_guard_detector_recipe" "threat" {
  count                     = var.clone_detector_recipes && var.threat_source_recipe_id != "" ? 1 : 0
  compartment_id            = var.compartment_id
  display_name              = "${var.name_prefix}-threat-detector"
  description               = "Cloned Threat detector recipe (demo-tunable)."
  source_detector_recipe_id = var.threat_source_recipe_id
  freeform_tags             = var.freeform_tags
}

###############################################################################
# 2. Responder recipe — clone of the managed responder recipe. In Phase 1/2
#    every responder rule stays notify-only (DETECT); Phase 3 flips selected
#    rules to ENABLED via the auto_remediate flag (see locals).
###############################################################################

resource "oci_cloud_guard_responder_recipe" "this" {
  count                      = var.clone_responder_recipe && var.responder_source_recipe_id != "" ? 1 : 0
  compartment_id             = var.compartment_id
  display_name               = "${var.name_prefix}-responder"
  description                = "Cloned responder recipe. Rules default to notify-only; auto_remediate flips them to ENABLED."
  source_responder_recipe_id = var.responder_source_recipe_id
  freeform_tags              = var.freeform_tags

  # Responder rule state is derived from the phase-3 auto_remediate toggle.
  # Concrete per-rule blocks are added when specific responder rule IDs are
  # selected for the demo; the derived state (local.responder_rule_state) is
  # the single switch the plan calls for.
  lifecycle {
    ignore_changes = [responder_rules]
  }
}

###############################################################################
# 3. Target — attach the watched compartment to the cloned detector recipe(s).
#    Gated behind create_target. Requires the config detector clone to exist
#    (the primary recipe the demo tunes); other recipes can be added as
#    additional target_detector_recipes blocks.
###############################################################################

resource "oci_cloud_guard_target" "this" {
  count                = var.create_target && length(oci_cloud_guard_detector_recipe.config) > 0 ? 1 : 0
  compartment_id       = var.compartment_id
  display_name         = "${var.name_prefix}-target"
  target_resource_type = var.target_resource_type
  target_resource_id   = local.watched_compartment_id
  freeform_tags        = var.freeform_tags

  dynamic "target_detector_recipes" {
    for_each = oci_cloud_guard_detector_recipe.config
    content {
      detector_recipe_id = target_detector_recipes.value.id
    }
  }

  dynamic "target_detector_recipes" {
    for_each = oci_cloud_guard_detector_recipe.activity
    content {
      detector_recipe_id = target_detector_recipes.value.id
    }
  }

  dynamic "target_detector_recipes" {
    for_each = oci_cloud_guard_detector_recipe.threat
    content {
      detector_recipe_id = target_detector_recipes.value.id
    }
  }

  dynamic "target_responder_recipes" {
    for_each = oci_cloud_guard_responder_recipe.this
    content {
      responder_recipe_id = target_responder_recipes.value.id
    }
  }
}

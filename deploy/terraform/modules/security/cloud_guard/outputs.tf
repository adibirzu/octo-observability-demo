###############################################################################
# OCI Cloud Guard submodule — outputs. Surface target + recipe ids so the root
# stack can wire problem export into Log Analytics and reference recipes later.
###############################################################################

output "target_id" {
  value       = length(oci_cloud_guard_target.this) > 0 ? oci_cloud_guard_target.this[0].id : ""
  description = "OCID of the Cloud Guard target (empty when create_target is off or no detector recipe is present)."
}

output "config_detector_recipe_id" {
  value       = length(oci_cloud_guard_detector_recipe.config) > 0 ? oci_cloud_guard_detector_recipe.config[0].id : ""
  description = "OCID of the cloned Configuration detector recipe (empty when not cloned)."
}

output "activity_detector_recipe_id" {
  value       = length(oci_cloud_guard_detector_recipe.activity) > 0 ? oci_cloud_guard_detector_recipe.activity[0].id : ""
  description = "OCID of the cloned Activity detector recipe (empty when not cloned)."
}

output "threat_detector_recipe_id" {
  value       = length(oci_cloud_guard_detector_recipe.threat) > 0 ? oci_cloud_guard_detector_recipe.threat[0].id : ""
  description = "OCID of the cloned Threat detector recipe (empty when not cloned)."
}

output "responder_recipe_id" {
  value       = length(oci_cloud_guard_responder_recipe.this) > 0 ? oci_cloud_guard_responder_recipe.this[0].id : ""
  description = "OCID of the cloned responder recipe (empty when not cloned)."
}

output "responder_rule_state" {
  value       = local.responder_rule_state
  description = "Derived responder lifecycle state: DETECT (notify-only) or ENABLED (auto-remediation)."
}

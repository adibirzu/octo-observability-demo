###############################################################################
# Validation outputs — confirm the modules materialised real coordinates.
###############################################################################

output "sec_compartment_id" {
  value       = oci_identity_compartment.sec.id
  description = "OCID of the dedicated validation compartment."
}

output "data_safe_target" {
  value = {
    target_database_id = module.data_safe.target_database_id
    target_name        = module.data_safe.target_display_name
  }
  description = "Data Safe target registration for oci-demo-atp."
}

output "cloud_guard" {
  value = {
    target_id                   = module.cloud_guard.target_id
    config_detector_recipe_id   = module.cloud_guard.config_detector_recipe_id
    activity_detector_recipe_id = module.cloud_guard.activity_detector_recipe_id
    threat_detector_recipe_id   = module.cloud_guard.threat_detector_recipe_id
    responder_recipe_id         = module.cloud_guard.responder_recipe_id
    responder_rule_state        = module.cloud_guard.responder_rule_state
  }
  description = "Cloud Guard recipe/target coordinates (responder_rule_state should be DETECT in Phase 1)."
}

###############################################################################
# OCI Data Safe submodule — outputs. Surface the target id so the root stack
# can wire the audit/alert feed into Log Analytics later.
###############################################################################

output "target_database_id" {
  value       = oci_data_safe_target_database.octoatp.id
  description = "OCID of the Data Safe target database registration for OCTOATP."
}

output "target_display_name" {
  value       = oci_data_safe_target_database.octoatp.display_name
  description = "Display name of the registered Data Safe target."
}

output "audit_profile_id" {
  value       = var.enable_audit ? oci_data_safe_audit_profile.octoatp[0].id : ""
  description = "OCID of the audit profile (empty when enable_audit = false)."
}

output "audit_trail_id" {
  value       = var.enable_audit ? oci_data_safe_audit_trail.octoatp[0].id : ""
  description = "OCID of the audit trail (empty when enable_audit = false)."
}

output "security_assessment_id" {
  value       = var.enable_security_assessment ? oci_data_safe_security_assessment.octoatp[0].id : ""
  description = "OCID of the Security Assessment baseline (empty when disabled)."
}

output "user_assessment_id" {
  value       = var.enable_user_assessment ? oci_data_safe_user_assessment.octoatp[0].id : ""
  description = "OCID of the User Assessment baseline (empty when disabled)."
}

output "private_endpoint_id" {
  value       = local.effective_private_endpoint_id
  description = "OCID of the Data Safe private endpoint wired into the target (created or reused; empty for public-access ADBs)."
}

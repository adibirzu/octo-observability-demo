###############################################################################
# OCI Data Safe submodule — inputs.
#
# Scaffold + feature-flagged. Everything that needs a live OCID is passed in
# (no hardcoded values), and resources that require live coordinates are gated
# behind toggles so a partial enablement is valid HCL and a safe `plan`.
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID hosting the Data Safe resources and the target database."
}

variable "atp_id" {
  type        = string
  description = "Autonomous Database OCID to register as a Data Safe target (e.g. OCTOATP). Sourced from module.atp[0].atp_id or a passed-in OCID."
}

variable "name_prefix" {
  type        = string
  default     = "octo-apm-demo"
  description = "Prefix for naming Data Safe resources."
}

variable "target_display_name" {
  type        = string
  default     = "octo-apm-demo-octoatp"
  description = "Display name for the Data Safe target database registration."
}

variable "database_type" {
  type        = string
  default     = "AUTONOMOUS_DATABASE"
  description = "Data Safe target database type. AUTONOMOUS_DATABASE for OCTOATP."
}

variable "infrastructure_type" {
  type        = string
  default     = "ORACLE_CLOUD"
  description = "Data Safe target infrastructure type."
}

###############################################################################
# Feature toggles — every resource beyond bare target registration is gated.
# Defaults keep the submodule a registration-only scaffold so a first apply is
# minimal and reversible.
###############################################################################

variable "enable_data_safe_service" {
  type        = bool
  default     = false
  description = "Ensure the Data Safe service is enabled in the region (idempotent; no-op if already enabled). Enable once per tenancy/region."
}

variable "is_enabled" {
  type        = bool
  default     = true
  description = "Whether the Data Safe service configuration should report enabled. Only used when enable_data_safe_service = true."
}

variable "enable_audit" {
  type        = bool
  default     = false
  description = "Provision the unified audit policy + audit profile/trail for the registered target."
}

variable "audit_trail_is_auto_purge_enabled" {
  type        = bool
  default     = true
  description = "Auto-purge the target's audit trail after the retention window (only used when enable_audit = true)."
}

variable "audit_profile_target_type" {
  type        = string
  default     = "TARGET_DATABASE"
  description = "Target type for the audit profile (TARGET_DATABASE for a registered target DB)."
}

variable "audit_policy_id" {
  type        = string
  default     = ""
  description = "OCID of the target's Data Safe audit policy. Materialised by Data Safe after registration; populate on a second apply to manage the policy. Empty = skip."
}

variable "audit_trail_id" {
  type        = string
  default     = ""
  description = "OCID of the target's Data Safe audit trail. Materialised by Data Safe after registration; populate on a second apply to manage collection. Empty = skip."
}

variable "audit_online_months" {
  type        = number
  default     = 6
  description = "Number of months audit records stay online in the audit profile (only used when enable_audit = true)."
}

variable "audit_offline_months" {
  type        = number
  default     = 12
  description = "Number of months audit records are retained offline in the audit profile (only used when enable_audit = true)."
}

variable "enable_security_assessment" {
  type        = bool
  default     = false
  description = "Provision a scheduled Security Assessment baseline for the target."
}

variable "enable_user_assessment" {
  type        = bool
  default     = false
  description = "Provision a scheduled User Assessment baseline for the target."
}

variable "assessment_schedule" {
  type        = string
  default     = ""
  description = "Optional cron-like schedule string for security/user assessments. Empty = on-demand only. Refer to the OCI provider docs for the expected format."
}

variable "freeform_tags" {
  type        = map(string)
  default     = { project = "octo-apm-demo" }
  description = "Freeform tags applied to all Data Safe resources."
}

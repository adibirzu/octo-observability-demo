###############################################################################
# Inputs for the portable security-modules harness. The orchestrator generates
# vars/<profile>.tfvars from live discovery; nothing is hardcoded here.
###############################################################################

variable "oci_profile" {
  type        = string
  default     = ""
  description = "OCI CLI config profile to authenticate with. Empty = default auth chain."
}

variable "region" {
  type        = string
  description = "Region (also the Cloud Guard reporting region), e.g. eu-frankfurt-1 / us-phoenix-1."
}

variable "parent_compartment_id" {
  type        = string
  description = "Parent compartment OCID for the dedicated validation compartment (often the tenancy root)."
}

variable "sec_compartment_name" {
  type        = string
  default     = "octo-sec-validation"
  description = "Name of the dedicated child compartment the Cloud Guard target watches."
}

variable "watch_compartment_id" {
  type        = string
  default     = ""
  description = "Compartment the Cloud Guard target watches. Empty = the dedicated compartment created here."
}

###############################################################################
# Data Safe
###############################################################################

variable "enable_data_safe" {
  type        = bool
  default     = true
  description = "Register a Data Safe target. Auto-skipped by the orchestrator when no registerable ADB is found."
}

variable "data_safe_atp_id" {
  type        = string
  default     = ""
  description = "Autonomous DB OCID to register as the Data Safe target."
}

variable "data_safe_target_display_name" {
  type        = string
  default     = "octo-sec-validation-target"
  description = "Display name for the Data Safe target registration."
}

variable "enable_assessments" {
  type        = bool
  default     = false
  description = "Provision scheduled Security + User Assessment baselines for the target."
}

variable "data_safe_enable_private_endpoint" {
  type        = bool
  default     = false
  description = "Create a Data Safe private endpoint (required for a VCN-bound/private ADB)."
}

variable "data_safe_private_endpoint_id" {
  type        = string
  default     = ""
  description = "Reuse an existing Data Safe private endpoint instead of creating one."
}

variable "data_safe_private_endpoint_vcn_id" {
  type        = string
  default     = ""
  description = "VCN OCID for the Data Safe private endpoint (required when enable_private_endpoint = true)."
}

variable "data_safe_private_endpoint_subnet_id" {
  type        = string
  default     = ""
  description = "Subnet OCID for the Data Safe private endpoint (required when enable_private_endpoint = true)."
}

###############################################################################
# Cloud Guard
###############################################################################

variable "enable_cloud_guard" {
  type        = bool
  default     = true
  description = "Create the Cloud Guard recipes + target."
}

variable "enable_cloud_guard_service" {
  type        = bool
  default     = false
  description = "Enable the Cloud Guard service (tenancy-wide). The orchestrator sets this true only when the tenancy is not already enabled."
}

variable "auto_remediate" {
  type        = bool
  default     = false
  description = "Phase 3 — flip responder rules from notify-only (DETECT) to auto-remediation (ENABLED)."
}

variable "config_source_recipe_id" {
  type        = string
  default     = ""
  description = "OCID of the Oracle-managed Configuration detector recipe to clone."
}

variable "activity_source_recipe_id" {
  type        = string
  default     = ""
  description = "OCID of the Oracle-managed Activity detector recipe to clone."
}

variable "threat_source_recipe_id" {
  type        = string
  default     = ""
  description = "OCID of the Oracle-managed Threat detector recipe to clone."
}

variable "responder_source_recipe_id" {
  type        = string
  default     = ""
  description = "OCID of the Oracle-managed Responder recipe to clone."
}

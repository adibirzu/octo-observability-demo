###############################################################################
# OCI Cloud Guard submodule — inputs.
#
# Scaffold + feature-flagged. Live coordinates (compartment, reporting region,
# remediation topic) are passed in; nothing is hardcoded. Recipe cloning and
# auto-remediation are gated behind toggles.
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID where Cloud Guard recipes/targets are created."
}

variable "reporting_region" {
  type        = string
  description = "Cloud Guard reporting region (where the service aggregates findings, e.g. us-phoenix-1)."
}

variable "target_compartment_id" {
  type        = string
  default     = ""
  description = "Compartment OCID the Cloud Guard target watches. Defaults to compartment_id when empty."
}

variable "name_prefix" {
  type        = string
  default     = "octo-apm-demo"
  description = "Prefix for naming Cloud Guard resources."
}

###############################################################################
# Service enablement.
###############################################################################

variable "enable_cloud_guard_service" {
  type        = bool
  default     = false
  description = "Provision oci_cloud_guard_cloud_guard_configuration to enable Cloud Guard (one-per-tenancy). Off by default to avoid colliding with an already-enabled tenancy."
}

variable "cloud_guard_status" {
  type        = string
  default     = "ENABLED"
  description = "Cloud Guard service status when enable_cloud_guard_service = true (ENABLED | DISABLED)."
}

variable "self_manage_resources" {
  type        = bool
  default     = false
  description = "When true, Cloud Guard does not auto-create Oracle-managed recipes — the demo manages its own cloned recipes."
}

###############################################################################
# Recipe cloning. The plan clones the Oracle-managed Configuration/Activity/
# Threat detector recipes + the managed responder recipe so demo rules can be
# tuned without editing the managed originals. Cloning requires the managed
# recipe OCIDs, which differ per tenancy — pass them in, gated.
###############################################################################

variable "clone_detector_recipes" {
  type        = bool
  default     = false
  description = "Clone the Oracle-managed detector recipes into demo-tunable copies. Requires *_source_recipe_id inputs."
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

variable "clone_responder_recipe" {
  type        = bool
  default     = false
  description = "Clone the Oracle-managed responder recipe into a demo-tunable copy. Requires responder_source_recipe_id."
}

variable "responder_source_recipe_id" {
  type        = string
  default     = ""
  description = "OCID of the Oracle-managed responder recipe to clone."
}

###############################################################################
# Target attachment + auto-remediation.
###############################################################################

variable "create_target" {
  type        = bool
  default     = true
  description = "Create the Cloud Guard target for the watched compartment. Requires at least the detector recipe(s) to attach."
}

variable "target_resource_type" {
  type        = string
  default     = "COMPARTMENT"
  description = "Cloud Guard target resource type (COMPARTMENT for the project compartment)."
}

variable "auto_remediate" {
  type        = bool
  default     = false
  description = "Phase 3 toggle. When true, selected responder rules switch from notify-only (DETECT) to auto-remediation (ENABLED)."
}

variable "remediation_topic_id" {
  type        = string
  default     = ""
  description = "ONS notification topic OCID used as the responder/notify target. Reuse modules/security oci_ons_notification_topic.remediation."
}

variable "freeform_tags" {
  type        = map(string)
  default     = { project = "octo-apm-demo" }
  description = "Freeform tags applied to all Cloud Guard resources."
}

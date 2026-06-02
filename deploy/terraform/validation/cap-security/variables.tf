###############################################################################
# Inputs for the cap security-module validation root. Real OCIDs live in the
# gitignored terraform.cap.tfvars (generated from .cap-recipe-ocids.env). No
# value is hardcoded here.
###############################################################################

variable "region" {
  type        = string
  default     = "eu-frankfurt-1"
  description = "cap home region; also the Cloud Guard reporting region."
}

variable "parent_compartment_id" {
  type        = string
  description = "Parent compartment OCID for the dedicated validation compartment (cap root tenancy compartment)."
}

variable "sec_compartment_name" {
  type        = string
  default     = "octo-apm-demo-sec"
  description = "Name of the dedicated child compartment the Cloud Guard target watches."
}

variable "data_safe_atp_id" {
  type        = string
  description = "Autonomous DB OCID to register as the Data Safe target (cap oci-demo-atp)."
}

variable "config_source_recipe_id" {
  type        = string
  description = "OCID of the Oracle-managed Configuration detector recipe (cap) to clone."
}

variable "activity_source_recipe_id" {
  type        = string
  description = "OCID of the Oracle-managed Activity detector recipe (cap) to clone."
}

variable "threat_source_recipe_id" {
  type        = string
  description = "OCID of the Oracle-managed Threat detector recipe (cap) to clone."
}

variable "responder_source_recipe_id" {
  type        = string
  description = "OCID of the Oracle-managed Responder recipe (cap) to clone."
}

variable "enable_assessments" {
  type        = bool
  default     = false
  description = "Apply #2 toggle — provision scheduled Security + User Assessment baselines for the Data Safe target."
}

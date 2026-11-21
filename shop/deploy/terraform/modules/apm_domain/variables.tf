###############################################################################
# APM Domain + RUM Web Application module inputs.
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID that will own the APM Domain."
}

variable "display_name" {
  type        = string
  default     = "octo-apm"
  description = "Display name for the APM Domain."
}

variable "description" {
  type    = string
  default = "APM Domain for OCTO Drone Shop + Enterprise CRM traces and RUM events."
}

variable "is_free_tier" {
  type        = bool
  default     = false
  description = "Create the domain on the free tier. Not recommended for demos that exceed free limits."
}

variable "web_application_display_name" {
  type        = string
  default     = "octo-drone-shop-web"
  description = "Display name for the RUM web application inside the APM Domain."
}

variable "create_rum_web_app" {
  type        = bool
  default     = true
  description = "Retained compatibility no-op: RUM web applications are registered in the OCI Console, so this module no longer creates one."
}

variable "freeform_tags" {
  type        = map(string)
  default     = {}
  description = "Freeform tags applied to all resources in this module."
}

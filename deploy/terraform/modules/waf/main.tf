###############################################################################
# OCI WAF module — detection-mode policy for a single frontend.
#
# Usage (from root stack):
#
#   module "waf_shop" {
#     source          = "./modules/waf"
#     compartment_id  = var.compartment_id
#     display_name    = "octo-waf-shop"
#     domain          = var.shop_domain
#     mode            = var.waf_mode            # DETECTION | BLOCK
#     log_group_id    = var.waf_log_group_id
#     admin_allow_cidrs = var.admin_allow_cidrs # applied on /api/admin/*
#   }
#
# Terraform 1.6+ / OCI provider 5.x.
###############################################################################

terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

variable "compartment_id" {
  type        = string
  description = "OCI compartment OCID owning the policy."
}

variable "display_name" {
  type        = string
  description = "Human-readable policy name."
}

variable "domain" {
  type        = string
  description = "Public hostname the policy protects (e.g. shop.example.test)."
}

variable "mode" {
  type        = string
  default     = "DETECTION"
  description = "DETECTION or BLOCK. Keep DETECTION until traffic is observed."
  validation {
    condition     = contains(["DETECTION", "BLOCK"], upper(var.mode))
    error_message = "mode must be DETECTION or BLOCK."
  }
}

variable "log_group_id" {
  type        = string
  description = "OCI Logging log group OCID that will receive WAF events."
}

variable "admin_allow_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to hit /api/admin/* — others are flagged (not blocked in DETECTION)."
}

variable "enable_waf_logging" {
  type        = bool
  default     = false
  description = "Create an OCI WAF SERVICE log for this firewall and emit it to log_group_id. Requires web_app_firewall_id."
}

variable "web_app_firewall_id" {
  type        = string
  default     = ""
  description = "OCID of the oci_waf_web_app_firewall the policy is attached to (the LB enforcement point) — the source of the WAF SERVICE log. Operator-supplied because the portable stack uses an external load balancer."
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "Retention (days) for the WAF log."
}

locals {
  effective_action = upper(var.mode) == "BLOCK" ? "block" : "check"
}

resource "oci_waf_web_app_firewall_policy" "this" {
  compartment_id = var.compartment_id
  display_name   = var.display_name

  actions {
    name = "allow"
    type = "ALLOW"
  }

  actions {
    name = "check"
    type = "CHECK"
  }

  actions {
    name = "block"
    type = "RETURN_HTTP_RESPONSE"
    code = 403
    headers {
      name  = "x-waf-action"
      value = "BLOCK"
    }
  }

  # Admin-path allowlist — flags (or blocks) when request hits /api/admin/*
  # from a CIDR outside `admin_allow_cidrs`. In DETECTION we only log.
  request_access_control {
    default_action_name = "allow"
  }

  request_rate_limiting {
    rules {
      name               = "login-burst"
      type               = "REQUEST_RATE_LIMITING"
      action_name        = local.effective_action
      condition_language = "JMESPATH"
      condition          = "http.request.url.path == '/login' || http.request.url.path == '/api/auth/login'"
      configurations {
        period_in_seconds          = 60
        requests_limit             = 10
        action_duration_in_seconds = 300
      }
    }
  }

  freeform_tags = {
    "deployment-profile" = "portable"
    "waf-mode"           = upper(var.mode)
    "waf-domain"         = var.domain
  }
}

# Optional WAF SERVICE log, sourced from the externally-attached firewall and
# emitted to log_group_id. Feed its id into the la_pipeline_waf_* connector so
# WAF detections reach Log Analytics (closes the "WAF dark by default" gap).
resource "oci_logging_log" "waf" {
  count              = var.enable_waf_logging && var.web_app_firewall_id != "" ? 1 : 0
  display_name       = "${var.display_name}-log"
  log_group_id       = var.log_group_id
  log_type           = "SERVICE"
  is_enabled         = true
  retention_duration = var.log_retention_days

  configuration {
    compartment_id = var.compartment_id
    source {
      category    = "all"
      resource    = var.web_app_firewall_id
      service     = "waf"
      source_type = "OCISERVICE"
    }
  }
}

output "policy_ocid" {
  value = oci_waf_web_app_firewall_policy.this.id
}

output "mode" {
  value = upper(var.mode)
}

output "waf_log_id" {
  value       = try(oci_logging_log.waf[0].id, "")
  description = "OCID of the WAF SERVICE log (empty when enable_waf_logging is false). Feed into la_pipeline_waf_*."
}

###############################################################################
# Root-stack inputs — tenancy-portable. Fill via terraform.tfvars or
# environment variables (`TF_VAR_*`). No value is hardcoded.
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID hosting the demo stack."
}

variable "shop_domain" {
  type        = string
  default     = "shop.example.test"
  description = "Public hostname for the drone shop frontend."
}

variable "crm_domain" {
  type        = string
  default     = "crm.example.test"
  description = "Public hostname for the CRM portal."
}

variable "ops_domain" {
  type        = string
  default     = "ops.example.test"
  description = "Public hostname for the internal ops/cp console."
}

variable "coordinator_domain" {
  type        = string
  default     = "coordinator.example.test"
  description = "Public hostname for the OCI Coordinator UI/API."
}

variable "waf_mode" {
  type        = string
  default     = "DETECTION"
  description = "WAF mode applied to every frontend (DETECTION | BLOCK)."
}

variable "waf_log_group_id" {
  type        = string
  description = "OCI Logging log group OCID for WAF events."
}

variable "admin_allow_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs permitted to reach /api/admin/*. Leave empty to skip the admin guard."
}

variable "la_namespace" {
  type        = string
  description = "OCI Log Analytics namespace."
}

variable "la_log_group_id" {
  type        = string
  description = "OCI Log Analytics log group OCID receiving app + WAF logs."
}

###############################################################################
# ATP — application database. Off by default so an existing ATP can be
# reused via its OCID.
###############################################################################

variable "create_atp" {
  type    = bool
  default = false
}

variable "atp_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "atp_wallet_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "atp_whitelisted_ips" {
  type    = list(string)
  default = []
}

###############################################################################
# Vault — secret storage for app + integrations. Off by default so an
# existing Vault can be reused.
###############################################################################

variable "create_vault" {
  type    = bool
  default = false
}

variable "vault_secrets" {
  type      = map(string)
  sensitive = true
  default   = {}
}

###############################################################################
# Object Storage — chaos state, wallet mirror, artifacts.
###############################################################################

variable "create_object_storage" {
  type    = bool
  default = false
}

variable "object_storage_namespace" {
  type    = string
  default = ""
}

###############################################################################
# Logging — log group + custom logs (app, chaos-audit, security).
###############################################################################

variable "create_logging" {
  type    = bool
  default = false
}

variable "logging_retention_days" {
  type    = number
  default = 30
}

###############################################################################
# Stack Monitoring — register the ATP DB as a monitored resource.
###############################################################################

variable "create_stack_monitoring" {
  type    = bool
  default = false
}

variable "stack_monitoring_atp_id" {
  type        = string
  default     = ""
  description = "ATP OCID to register. If create_atp=true this is auto-wired to the new DB."
}

###############################################################################
# OKE — provision when the tenancy has no usable cluster. Reuse an existing
# one by passing create_oke = false + existing_cluster_id (no wiring yet —
# root module currently consumes the output only when create_oke=true).
###############################################################################

variable "create_oke" {
  type    = bool
  default = false
}

variable "oke_cluster_name" {
  type    = string
  default = "octo-apm-demo-oke"
}

variable "oke_kubernetes_version" {
  type    = string
  default = "v1.31.1"
}

variable "oke_vcn_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "oke_node_pool_size" {
  type    = number
  default = 3
}

variable "oke_node_ocpus" {
  type    = number
  default = 2
}

variable "oke_node_memory_gbs" {
  type    = number
  default = 16
}

variable "oke_node_boot_volume_gbs" {
  type    = number
  default = 93
}

variable "oke_node_image_id" {
  type        = string
  default     = ""
  description = "OKE-managed node image OCID. Required when create_oke=true."
}

variable "oke_availability_domain_names" {
  type    = list(string)
  default = []
}

###############################################################################
# Security posture expansion — OCI Data Safe + Cloud Guard.
# Additive + off by default so existing deploys see zero diff until an
# operator opts in. Mirrors the create_atp / create_vault / create_logging
# pattern. See docs/security-expansion-data-safe-cloud-guard.md.
###############################################################################

variable "create_data_safe" {
  type        = bool
  default     = false
  description = "Register OCTOATP as a Data Safe target (+ optional audit/assessment scaffold)."
}

variable "data_safe_atp_id" {
  type        = string
  default     = ""
  description = "Autonomous DB OCID to register in Data Safe. If create_atp=true this auto-wires to the new DB; otherwise pass a reused ATP OCID."
}

# Data Safe private-endpoint registration — only for a VCN-bound (private) ATP.
# All off/empty by default so the public-access path (e.g. cap oci-demo-shared-atp)
# is unchanged. Set these in emdemo only if OCTOATP is locked to a private VCN.
variable "data_safe_enable_private_endpoint" {
  type        = bool
  default     = false
  description = "Create a Data Safe private endpoint in the ATP's VCN. Required to register a private/VCN-bound Autonomous DB."
}

variable "data_safe_private_endpoint_id" {
  type        = string
  default     = ""
  description = "OCID of an existing Data Safe private endpoint to reuse instead of creating one."
}

variable "data_safe_private_endpoint_vcn_id" {
  type        = string
  default     = ""
  description = "VCN OCID for the Data Safe private endpoint (required when data_safe_enable_private_endpoint = true)."
}

variable "data_safe_private_endpoint_subnet_id" {
  type        = string
  default     = ""
  description = "Subnet OCID for the Data Safe private endpoint (required when data_safe_enable_private_endpoint = true)."
}

variable "create_cloud_guard" {
  type        = bool
  default     = false
  description = "Provision the Cloud Guard target + cloned detector/responder recipes for the project compartment."
}

variable "cloud_guard_reporting_region" {
  type        = string
  default     = ""
  description = "Cloud Guard reporting region (e.g. us-phoenix-1 in emdemo, eu-frankfurt-1 in cap). Required when create_cloud_guard=true."
}

variable "cloud_guard_target_compartment_id" {
  type        = string
  default     = ""
  description = "Compartment the Cloud Guard target watches. Empty defaults to compartment_id."
}

variable "cloud_guard_topic_id" {
  type        = string
  default     = ""
  description = "ONS notification topic OCID used as the responder/notify target (reuse modules/security oci_ons_notification_topic.remediation)."
}

variable "cloud_guard_auto_remediate" {
  type        = bool
  default     = false
  description = "Phase 3 toggle. When true, selected responder rules switch from notify-only (DETECT) to auto-remediation (ENABLED)."
}

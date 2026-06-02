# `data_safe` submodule — OCI Data Safe for OCTOATP

Registers the shared Autonomous Database (`OCTOATP`, Oracle 19c) as an **OCI
Data Safe target** and optionally turns on the unified audit trail plus
Security/User Assessment baselines.

> **Status: SCAFFOLD, OFF BY DEFAULT.** The root stack only calls this module
> when `create_data_safe = true`. Within the module, every resource beyond bare
> target registration is gated behind its own toggle, all defaulting to a safe
> registration-only posture. No OCIDs/IPs/datakeys are hardcoded — every
> coordinate is a variable.

## What it provisions

| Resource | Gate | Purpose |
|---|---|---|
| `oci_data_safe_data_safe_configuration` | `enable_data_safe_service` (off) | Enable Data Safe in the region (idempotent; one-per-region). |
| `oci_data_safe_target_database` | always (when module enabled) | Register `OCTOATP` by its Autonomous DB OCID — the anchor resource. |
| `oci_data_safe_audit_profile` | `enable_audit` (off) | Online/offline audit retention for the target. |
| `oci_data_safe_audit_policy` | `enable_audit` + `audit_policy_id` (off) | Manage the target's audit policy (OCID materialised after registration). |
| `oci_data_safe_audit_trail` | `enable_audit` + `audit_trail_id` (off) | Manage audit-trail collection (OCID materialised after registration). |
| `oci_data_safe_security_assessment` | `enable_security_assessment` (off) | Baseline Security Assessment for the target. |
| `oci_data_safe_user_assessment` | `enable_user_assessment` (off) | Baseline User Assessment for the target. |

Sensitive-data discovery + masking (plan Phase 2) are intentionally **not** in
this scaffold: per the plan they run against a `OCTOATP_MASKDEMO` clone, never
production data, and are added in a later iteration.

## Inputs (key)

| Variable | Default | Notes |
|---|---|---|
| `compartment_id` | — (required) | Compartment OCID. |
| `atp_id` | — (required) | Autonomous DB OCID for OCTOATP. Passed from `module.atp[0].atp_id` or a reused OCID. |
| `name_prefix` | `octo-apm-demo` | Resource name prefix. |
| `enable_data_safe_service` | `false` | Turn on per-region Data Safe enablement. |
| `enable_audit` | `false` | Provision audit policy/profile/trail. |
| `enable_security_assessment` | `false` | Provision Security Assessment. |
| `enable_user_assessment` | `false` | Provision User Assessment. |
| `assessment_schedule` | `""` | Optional schedule; empty = on-demand. |

## Outputs

`target_database_id`, `target_display_name`, `audit_profile_id`,
`audit_trail_id`, `security_assessment_id`, `user_assessment_id`.

## Enable steps (cap-first, then emdemo)

This follows the project tenancy rules: **stage in `cap` first, review the
plan, then promote to `emdemo` inside the `LogAnalytics` compartment scope.**

1. In `cap` (staging) tfvars, set:
   ```hcl
   create_data_safe   = true
   data_safe_atp_id   = "<AUTONOMOUS_DB_OCID>"   # only if create_atp = false
   ```
2. `terraform plan` — confirm only the new Data Safe target appears.
3. To turn on auditing/assessments, pass module-level toggles through the root
   wiring (extend `main.tf` to forward `enable_audit` etc.) or apply in a later
   iteration once registration is verified. The audit **policy** and **trail**
   OCIDs are materialised by Data Safe only *after* the target is registered, so
   `oci_data_safe_audit_policy` / `oci_data_safe_audit_trail` stay inert until
   you pass `audit_policy_id` / `audit_trail_id` on a second apply (look them up
   with `oci data-safe audit-policy list` / `oci data-safe audit-trail list`).
4. Review, then repeat in `emdemo` (LogAnalytics compartment only).

> Verify provider attribute names against your installed `oracle/oci` provider
> version before the first real apply — Data Safe resource argument names have
> evolved across provider releases. This scaffold targets `oci >= 5.0.0`.

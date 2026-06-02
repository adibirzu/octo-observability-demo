# `cloud_guard` submodule — OCI Cloud Guard for the project compartment

Enables Cloud Guard, clones the Oracle-managed detector/responder recipes into
demo-tunable copies, and attaches a **target** to the project compartment so
the service watches ATP, OKE, Vault, Object Storage, and the LB in one scope.

> **Status: SCAFFOLD, OFF BY DEFAULT.** The root stack only calls this module
> when `create_cloud_guard = true`. Within the module, service enablement,
> recipe cloning, and auto-remediation are each gated behind their own toggle.
> No OCIDs/IPs/datakeys are hardcoded — every coordinate is a variable.

## What it provisions

| Resource | Gate | Purpose |
|---|---|---|
| `oci_cloud_guard_cloud_guard_configuration` | `enable_cloud_guard_service` (off) | Enable Cloud Guard with the reporting region (tenancy-wide, one-time). |
| `oci_cloud_guard_detector_recipe` ×3 | `clone_detector_recipes` + per-recipe source OCID (off) | Clone managed Configuration/Activity/Threat recipes for tuning. |
| `oci_cloud_guard_responder_recipe` | `clone_responder_recipe` + source OCID (off) | Clone the managed responder recipe; rules notify-only until Phase 3. |
| `oci_cloud_guard_target` | `create_target` (on) + at least the config detector clone present | Attach the watched compartment to the cloned recipe(s). |

## Phase model (matches the plan)

- **Phase 1/2** — `auto_remediate = false` ⇒ responder rules stay `DETECT`
  (notify-only). Findings flow to the notification topic / Log Analytics.
- **Phase 3** — `auto_remediate = true` ⇒ derived `responder_rule_state` flips
  to `ENABLED`, switching selected responder rules to auto-remediation. Reuse
  the existing `modules/security` ONS topic
  (`oci_ons_notification_topic.remediation`) via `remediation_topic_id` so Cloud
  Guard's responder and the demo's quarantine-NSG remediation share one path.

## Inputs (key)

| Variable | Default | Notes |
|---|---|---|
| `compartment_id` | — (required) | Compartment OCID for recipes/target. |
| `reporting_region` | — (required) | Cloud Guard reporting region. |
| `target_compartment_id` | `""` | Compartment to watch; defaults to `compartment_id`. |
| `enable_cloud_guard_service` | `false` | Tenancy-wide enablement (one-time). |
| `clone_detector_recipes` | `false` | Clone managed detector recipes (needs source OCIDs). |
| `clone_responder_recipe` | `false` | Clone managed responder recipe (needs source OCID). |
| `create_target` | `true` | Attach the watched compartment (needs config detector clone). |
| `auto_remediate` | `false` | Phase 3 — flip responders to auto-remediation. |
| `remediation_topic_id` | `""` | Reuse the security module's ONS topic. |

## Outputs

`target_id`, `config_detector_recipe_id`, `activity_detector_recipe_id`,
`threat_detector_recipe_id`, `responder_recipe_id`, `responder_rule_state`.

## Enable steps (cap-first, then emdemo)

Follows the project tenancy rules: **stage in `cap` first, review the plan,
then promote to `emdemo` inside the `LogAnalytics` compartment scope.**

1. In `cap` (staging) tfvars:
   ```hcl
   create_cloud_guard = true
   reporting_region   = "<REPORTING_REGION>"   # e.g. eu-frankfurt-1 in cap
   ```
2. Look up the Oracle-managed source recipe OCIDs in the tenancy
   (`oci cloud-guard detector-recipe list` / `responder-recipe list`) and pass
   them as `*_source_recipe_id` once you opt into cloning.
3. `terraform plan` — confirm only the new Cloud Guard resources appear.
4. Keep `auto_remediate = false` for Phases 1/2. Flip to `true` only in Phase 3
   after the notify-only behaviour is verified.
5. Review, then repeat in `emdemo` with `reporting_region = us-phoenix-1`,
   inside the LogAnalytics compartment scope only.

> Verify provider attribute names (recipe clone arguments, target sub-blocks)
> against your installed `oracle/oci` provider version before the first real
> apply — Cloud Guard resource schemas have evolved across releases. This
> scaffold targets `oci >= 5.0.0`.

## Operational note — one target per compartment

OCI Cloud Guard permits **exactly one target per compartment**. Most tenancies
already have a target on the **root** compartment (created when Cloud Guard is
first enabled), so pointing this module's target at the root would collide.
Set `target_compartment_id` to a **child** compartment instead — a child target
coexists with an ancestor's target and takes precedence for its subtree. Keep
`enable_cloud_guard_service = false` when the tenancy is already enabled.

## Validated in cap (2026-06-02)

Applied live against cap (`pbncapgemini`, eu-frankfurt-1) with `oracle/oci`
**8.16.0**: cloned all three managed detector recipes + the managed responder
recipe, and attached a target on a dedicated child compartment
(`octo-apm-demo-sec`) — `responder_rule_state = DETECT` (notify-only). cap's
Cloud Guard was already enabled with a root target, so `enable_cloud_guard_service`
stayed off and the target watched the child compartment. All resources reached
`ACTIVE`; `terraform plan` is clean. See the portable harness at
`deploy/terraform/validation/security-modules/`.

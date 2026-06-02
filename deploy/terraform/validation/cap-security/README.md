# cap security-module validation root

Isolated Terraform root that validates the `modules/security/data_safe` and
`modules/security/cloud_guard` submodules against the **cap** (pbncapgemini,
eu-frankfurt-1) staging tenancy **before** they are promoted to `emdemo`.

## Why a separate root (not the repo root stack)

`deploy/terraform/terraform.tfstate` tracks **oci4cca** (DEFAULT) resources.
Terraform reconciles all of state against the provider's auth on every
plan/apply, so pointing the root stack at cap would treat oci4cca's ATP/logging
as missing and plan destructive churn. This root has its **own local state** and
a provider **pinned to `config_file_profile = "cap"`**, so it can only ever act
on the cap tenancy. It sources the two submodules unchanged — the goal is to
validate them, not fork them.

## What it creates (Phase 1)

| Resource | Module | Notes |
|---|---|---|
| `oci_identity_compartment.sec` (`octo-apm-demo-sec`) | root | Dedicated child compartment; the Cloud Guard target watches it (cap root already has a target — one target per compartment). `enable_delete = true`. |
| Data Safe target database | `data_safe` | Registers `oci-demo-atp` (19c). Audit + assessments off in apply #1. |
| 3× cloned detector recipes (Config/Activity/Threat) | `cloud_guard` | Clones of the Oracle-managed recipes. |
| 1× cloned responder recipe | `cloud_guard` | Rules notify-only (`DETECT`); `auto_remediate = false`. |
| Cloud Guard target | `cloud_guard` | Watches `octo-apm-demo-sec`, attaches the cloned recipes. |

Cloud Guard service enablement stays **off** — cap is already enabled
tenancy-wide.

## Run

```bash
cd deploy/terraform/validation/cap-security
terraform init
terraform plan  -var-file=terraform.cap.tfvars
terraform apply -var-file=terraform.cap.tfvars
```

Real OCIDs live in the gitignored `terraform.cap.tfvars`, regenerated from
`deploy/terraform/.cap-recipe-ocids.env` (also gitignored).

## Apply #2 (optional, deeper validation)

Flip `enable_assessments = true` in the tfvars and re-apply to validate the
Security/User Assessment resource schemas. Audit policy/trail are two-phase
(their OCIDs are materialised by Data Safe only after registration) — see the
`data_safe` module README.

## Reverse

```bash
terraform destroy -var-file=terraform.cap.tfvars
```

Removes only what this root created (recipes/target/registration + the
dedicated compartment).

## Promote to emdemo

Do **not** reuse this root for emdemo. In emdemo, enable the same flags on the
real root stack inside the **`LogAnalytics` compartment** scope only, with
`reporting_region = us-phoenix-1`, after reviewing this cap plan/apply. See
`docs/security-expansion-data-safe-cloud-guard.md` §6.

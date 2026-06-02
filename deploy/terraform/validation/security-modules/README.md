# Portable security-modules harness — Data Safe + Cloud Guard on any tenancy

Enable and validate the `modules/security/data_safe` and
`modules/security/cloud_guard` submodules against **any OCI deployment**, one
isolated state per profile. Auto-discovers the per-tenancy inputs (managed
recipe OCIDs, a registerable Autonomous DB, Cloud Guard enablement state) so the
same command works in cap, emdemo, or a brand-new tenancy.

## Quick start

```bash
cd deploy/terraform/validation/security-modules

# 1) Read-only probe — writes vars/<profile>.tfvars from live discovery
./security-modules.sh discover --profile cap

# 2) Review the plan, then apply
./security-modules.sh plan    --profile cap
./security-modules.sh apply   --profile cap

# 3) Confirm the live resources are ACTIVE
./security-modules.sh verify  --profile cap

# Tear down everything this harness created for the profile
./security-modules.sh destroy --profile cap
```

## What it creates (Phase 1, notify-only)

A dedicated child compartment, a Data Safe target (+ optional assessments), the
three cloned detector recipes, a cloned responder recipe (`DETECT`), and a Cloud
Guard target watching the dedicated compartment.

## How "any deployment" is handled

| Concern | Behaviour |
|---|---|
| **Auth / region** | `--profile` selects the OCI profile; region is read from `~/.oci/config` (override with `--region`). |
| **State isolation** | One `state/<profile>.tfstate` per profile — no cross-tenancy collisions. |
| **Cloud Guard already enabled** | Detected; service-enablement is set only when the tenancy is OFF. The target always watches a fresh child compartment (one target per compartment). |
| **Managed recipe OCIDs** | Looked up live per tenancy (they differ everywhere). |
| **Registerable DB** | Auto-picks an `AVAILABLE` + `NOT_REGISTERED` ADB, preferring public-access. Override with `--db NAME\|OCID`, or `--skip-data-safe`. |
| **Private / VCN-bound ADB** | Detected; a Data Safe **private endpoint** is created automatically in the ADB's VCN/subnet. |
| **No registerable DB** | Data Safe is skipped; Cloud Guard still validates. |

## Options

`--region`, `--compartment <parent>`, `--watch-compartment <ocid>`,
`--db <name|ocid>`, `--skip-data-safe`, `--skip-cloud-guard`, `--assessments`,
`--auto-remediate` (Phase 3), `--sec-name <name>`, `--auto-approve`.
Run `./security-modules.sh --help` for the full list.

## Safety

- `discover` and `verify` are read-only.
- `state/` and `vars/` (real OCIDs) are gitignored; committed files carry none.
- **Tenancy rules still apply:** stage in `cap` first; in `emdemo` operate only
  inside the `LogAnalytics` compartment (`--compartment <LogAnalytics OCID>`,
  `--region us-phoenix-1`) and review the plan before apply.
- Keep `--auto-remediate` off until notify-only behaviour is verified.

## cap reference run (2026-06-02)

Validated live in cap (`pbncapgemini`, eu-frankfurt-1) against `oracle/oci`
8.16.0 — all resources `ACTIVE`, responders `DETECT`. See
`docs/security-expansion-data-safe-cloud-guard.md` §8.

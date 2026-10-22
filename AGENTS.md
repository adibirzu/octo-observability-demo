# octo-observability-demo agent guide

OCI observability demo with a FastAPI shop and CRM, supporting services, and OCI deployment assets.

## Commands

- Install app/test dependencies: `python -m pip install -r shop/requirements-dev.txt` (from the repository root).
- Install docs dependencies: `python -m pip install -r requirements-docs.txt` (repository root).
- Test: `make test` (contract, docs, and app suites).
- Lint: no root lint target is defined in the Makefile.
- Run local stack: `make local-up`; stop it with `make local-down`.

## Layout

- Shop storefront and Python tests -> `shop/`
- CRM portal and Python tests -> `crm/`
- Supporting services -> `services/`
- Deployment assets and local Compose stack -> `deploy/`
- MkDocs documentation -> `site/`, configured by `mkdocs.yml`
- Cross-service contract tests -> `tests/`
- Operator utilities -> `tools/`

## Boundaries

- Never commit environment files, credentials, keys, wallets, kubeconfig, Terraform state/plans, or local tenancy data; `.gitignore` lists protected paths.
- Keep generated build outputs out of commits (`build/`, `dist/`, and `*.pyc` are ignored).
- OCI deploy targets any configured tenancy; `OCI_PROFILE` defaults to `DEFAULT` and deploys require `OCI_COMPARTMENT_ID`, `OCIR_REGION`, `OCIR_TENANCY`, and `DNS_DOMAIN`.

## On error

Search KB.md (and ~/dev/OCI-DEMO/KB.md for OCI issues) before debugging; add an entry after a new fix. Do not read KB.md at session start.

## Done

Run `make verify` to validate tests, docs, diagrams, and deployment verification.

<!-- BEGIN oci4cca-ecosystem-matrix -->
Shared OCI4CCA ownership/interconnect contract: [docs/OCI4CCA_ECOSYSTEM.md](docs/OCI4CCA_ECOSYSTEM.md), generated from OCI-DEMO `config/oci4cca_ecosystem.json`. Read it only for cross-project work.
<!-- END oci4cca-ecosystem-matrix -->

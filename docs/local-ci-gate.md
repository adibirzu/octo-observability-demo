# Local CI gate

Run the gate on macOS with Python 3.11, `sandbox-exec`, Git, Gitleaks, Node/npm,
Go, Terraform 1.14.3, TFLint, Trivy 0.76.2, and the test and docs dependencies installed
in the workspace's `.gate/venv`. The runner puts `.gate/venv/bin` and
`.gate/bin` first on the path for local checks. Populate the workspace Go module
cache in `.gate/gomodcache`, the Terraform filesystem mirror in
`.gate/terraform-mirror`, and the Trivy advisory database in
`.gate/trivy-cache/db` before running the offline checks that need them.
For the Trivy cache, run the public database download separately with an
empty home and Docker configuration. The gate itself uses the cached database
without network access.
Install the shop requirements from `shop/`. Put the CRM requirements in
`.gate/venv/crm` and the GenAI Studio dependencies from its `pyproject.toml` in
`.gate/venv/genai` (Python 3.12) to satisfy their independent Python pins.

```sh
.gate/venv/bin/python scripts/local_ci_gate.py --mode all --allow-online --keep-going
```

Use `--list` to inspect the commands and `--step NAME` to rerun a specific
check. Stage new files before running the added-line scan so the staged diff
includes them. The secret scan checks commits since `origin/main`, the index,
and unstaged tracked changes. It reports only the count and file/line locations.

Only the pip and npm advisory lookups use the network. Each lookup starts with
an empty temporary home, distinct private package-manager configs, and only
the dependency manifests for that check. Seatbelt blocks reads of host
credentials and workspace environment files. An absolute interpreter path
gets a file-specific read allowance for the launcher and its resolved target.
TFLint and Terraform provider
validation can use Unix sockets inside their own private temporary directory.
All IP networking remains denied for those checks.

## Workflow coverage

| Workflow job | Local check names | Hosted or provisioned inputs |
| --- | --- | --- |
| `tests.yml / tests` | `sbom-generate-check`, `pytest-contract`, `pytest-shop` | Install the shop test dependencies before running the gate. |
| `tests.yml / crm` | `pytest-crm` | Install the CRM test dependencies before running the gate. |
| `orm-and-sbom-release.yml / package` | `pytest-contract`, `sbom-generate-check`, `sbom-public-check`, `release-matrix`, `orm-archives`, `orm-terraform-validate`, `trivy-source-inventory`, `trivy-source-vulnerabilities` | Offline Terraform mirror and Trivy advisory database. `orm-artifact-upload` requires GitHub Actions. |
| `orm-and-sbom-release.yml / images` | `release-matrix` | `orm-native-image-build` and `orm-image-scans` require the exact native Linux amd64 images. `orm-image-publish-attest` and `orm-image-artifacts` require registry and Actions services. |
| `orm-and-sbom-release.yml / attach` | `orm-archives` verifies local package checksums. | `orm-release-artifact-transfer` requires image checksums, Actions artifact download, and GitHub release upload. |
| `ocir-publish.yml / publish` | `ocir-source-selection` checks main ancestry and the four candidate build definitions. | `ocir-native-image-build` and `ocir-image-scans` require native Linux amd64 candidates. `ocir-publish` and `ocir-artifact-upload` require registry and Actions services. |

The gate also runs strict docs, Gitleaks, the pip and npm audits, TFLint,
Go vet and race tests, and the additional Python app, service, and tool suites.
Missing prerequisites and hosted checks appear as `UNAVAILABLE` and cause a
nonzero exit. The private receipt and logs under `.gate/` record local results.

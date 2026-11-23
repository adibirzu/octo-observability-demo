# octo-observability-demo knowledge base

Troubleshooting reference. Read it only when an error occurs, not at session start.
Cross-cutting OCI, OKE, IAM and networking issues live in the shared OCI-DEMO KB: `~/dev/OCI-DEMO/KB.md`
(search it with `python3.11 ~/dev/OCI-DEMO/scripts/knowledge_lookup.py --query '<error>'`).

Add an entry after every error that needed investigation and a fix. Use the next number.

## Entry format

```
## KB-NNN: <component> - <short symptom>
- Error: <exact message>
- Root cause: <what was actually wrong>
- Fix: <what changed, with file/command>
- Prevention: <how to avoid it next time>
```

## KB-008. Startup reset and seed reconciliation can replace existing data

- Component: Shop database initialization and CRM bootstrap.
- Symptom: an empty users table could trigger a full Shop schema reset; restarting populated apps could reconcile accounts, credentials and catalog records.
- Cause: automatic identity repair lacked an opt-in guard, and seed helpers treated existing users as permission to reconcile live data.
- Fix: default `ALLOW_DESTRUCTIVE_DB_BOOTSTRAP` off and never enable it in deployment assets; seed only when every modeled application table is empty.
- Verification: failing-before local SQLite state snapshots now pass for empty-user catalogs, populated accounts, repeated initial seeding, and missing bootstrap credentials on a populated CRM.
- Limitation: schema compatibility checks still run; no live database or deployment was changed.

## Resource Manager validation on macOS

- Symptom. `terraform validate` reports `Unrecognized remote plugin message`. Terraform debug output shows `listen unix ... bind: invalid argument` when the provider socket path exceeds the macOS limit.
- Resolution. Set `PLUGIN_UNIX_SOCKET_DIR=.` while running Terraform in the configuration directory. Keep `TMPDIR` in the approved scratch directory.
- Verification. Run `terraform init -backend=false` and `terraform validate` against the source and extracted archive with a CLI version that satisfies `required_version`.

## KB-001. Deployment verification fails to collect root tests without jsonschema

- Error. Pytest reports `ModuleNotFoundError: No module named 'jsonschema'` during collection.
- Root cause. The deployment test module imported the schema validator before pytest could deselect the only test that needed it.
- Fix. `deploy/verify.sh` warns and deselects the control-plane manifest contract when its `python3` cannot import `jsonschema`. The direct contract test imports it locally and still requires it.
- Verification. Run the root deployment suite with the manifest contract deselected on the workstation. Install `shop/requirements-dev.txt` to run the manifest contract directly, as CI does.

## KB-002. Local test gates reported success after failed suites

- Error. `make test-apps` returned zero after pytest failed; deployment verification emitted only a warning.
- Root cause. The Makefile used `|| echo`, ran app tests outside their owning directories, and omitted tool suites. Deployment verification converted app failures into warnings and inferred success from output text.
- Fix. Both gates use pytest exit status from isolated suite directories. Deployment verification counts suite failures as errors. The private bootstrap source contract reports an explicit pytest skip when its local-only script is absent; dependency collection failures remain fatal.
- Verification. `python3.11 -m pytest -q tests/test_local_test_gates.py` covers success, test failure, collection error, no tests collected, and owning-directory execution.

## KB-003. Verification skips suites under paths containing glob characters

- Error. A workspace path containing brackets can make deployment verification skip every app suite.
- Root cause. The unquoted repository prefix in Bash parameter removal is treated as a glob pattern, so the derived suite path can remain absolute.
- Fix. Quote the repository prefix when removing it from each suite path in `deploy/verify.sh`.
- Verification. `python3.11 -m pytest -q tests/test_local_test_gates.py` exercises every suite with normal and bracketed workspace paths and checks its owning directory.

## KB-004. fakeredis setup fails with Redis 8.2

- Error. FakeRedis construction raises `AttributeError: 'method_descriptor' object has no attribute '__closure__'` before service tests can run.
- Root cause. Redis 8.2's client constructor decorator contains a callable closure value that fakeredis 2.40.0 inspects as a Python function. fakeredis 2.36.1 has the same failure.
- Fix. Pin Redis 8.0.0 with fakeredis 2.40.0 in the async worker, cache client and remediator manifests, and align the Shop/CRM consumer requirements. Redis 7.4.1 also passes the service suites but conflicts with the consumers' Redis 8 constraints.
- Verification. Run the full async-worker, cache, remediator, Shop and CRM suites in separate environments; all pass with the selected pair. Keep dependency setup failures fatal.

## KB-005. App security updates need coupled pins and a JWT backend replacement

- Error. Requirements audits report vulnerable OTel API, multipart, JWT, settings, PDF and cryptography versions; the old OCI SDK excludes the fixed cryptography version.
- Root cause. Older OCI constraints exclude fixed cryptography, exact OTel dependencies must move together, and the previous JWT backend has no fixed release.
- Fix. Align OTel API/SDK/exporters and instrumentation, select OCI 2.184.2 with cryptography 50.0.0, and apply the consolidated app dependency updates. Replace the unfixed python-jose/ecdsa backend with PyJWT 2.15.1.
- Compatibility. Preserve numeric-only issued-at policy; require expiry and reject missing/empty audience under the approved stricter policies. Non-finite issued-at values fail closed. Verify each live identity-provider client separately before deployment.
- Framework regression. FastAPI included-router entries no longer expose the same path attributes. Verify the metrics GET operation through public OpenAPI instead of inspecting the internal route list.
- Verification. Run the offline OIDC regressions, full isolated suites, blocking requirements audits and make verify. The dependency refresh document records the proposal ledger and acceptance limits.

## KB-006. Native amd64 builds must reject ARM before OCI lookup

- Component: `deploy/oke/build-push-images.sh`.
- Symptom: the default amd64 image build starts OCI namespace discovery on an ARM workstation before checking the host architecture.
- Cause: image platform defaults and credential-dependent discovery precede any architecture guard.
- Fix: reject amd64 on a non-x86_64 host before resolving the OCI profile or registry namespace. Use an approved native builder or CI.
- Verification: `tests/test_public_release_sbom.py` runs the helper with a synthetic ARM host and fails if a cloud or build command runs.
- Status: locally verified; no image build, push, or deployment executed.

## KB-007. Release packaging regression needs application collection dependencies

- Component: ORM and SBOM release workflow.
- Symptom: the missing-jsonschema regression fails with a prior FastAPI collection error in the minimal release environment.
- Cause: pytest collects root modules before applying the regression's selection; pytest, PyYAML and jsonschema alone do not provide the app imports.
- Fix: install the Shop development requirements from the Shop directory, plus PyYAML, before package contract tests. Keep the schema-failure regression and its exact-cause assertion.
- Verification: the original minimal environment reproduces the failure; the declared package verification environment runs the same regression successfully.
- Status: local reproduction and repair; no release, image publication or provider action.

## Storage hygiene collection and local validation

- OCI boot attachment listing requires an availability domain even though boot volume listing can span ADs. Enumerate the selected compartment's ADs, list all boot attachments per AD, and join across the scoped inventory before calling a volume unattached.
- Successful OCI CLI empty-list calls can emit no stdout. Treat this separately from a nonzero response and retain exit receipts.
- Node-pool creator tags are service-principal clues. Match the exact current pool ID privately before calling their resources demo-owned.
- Local gates require compatible docs, plotting, and OpenTelemetry packages. Use a disposable workspace venv; install shop requirements from `shop/` because editable dependency paths are relative to that working directory.
- A report timer must see the host's dedicated temporary directory. PrivateTmp hides that directory and produces an incomplete report.
- Verification: storage-hygiene regression tests capture failures before these fixes. No live cleanup or configuration changes are part of local verification.

### Storage hygiene review hardening

- Preserve wallets, dumps, and extensionless data with a file allowlist even if a caller supplies a wildcard. Provision dedicated cleanup directories as root-owned mode 0700.
- A missing Docker/Podman daemon must produce a report-only runtime_unavailable result, not suppress the host's remaining report.
- Future-node image GC user data is opt-in. Review the boot default change from 93 GB to 100 GB in the authoritative saved plan.
- Namespace cleanup apply requires explicit dedicated-namespace confirmation. Registry retention overrides cannot go below versioned policy floors.
- Verification: these findings have failing-before behavioral tests, including apply-mode chart rendering. The image is pinned by a verified official multi-platform manifest digest.

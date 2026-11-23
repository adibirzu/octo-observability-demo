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

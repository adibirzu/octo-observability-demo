# octo-observability-demo

OCI observability demo: a multi-service shop + CRM + GenAI studio with full APM / RUM /
Log Analytics instrumentation, deployed to OKE on the **emdemo** tenancy. Python is the
primary language; the `Makefile` is the canonical entrypoint for every workflow.

## Stack

- **Python / FastAPI** (primary) — `shop/`, `crm/`, `services/*` (most have `pyproject.toml`), root `tests/` (pytest)
- **TypeScript / Playwright** — `shop/` E2E suite (`shop/package.json`), `services/browser-runner`
- **Java / Spring Boot** — `services/apm-java-demo` (payment APM sidecar)
- **Docker** — every service ships a `Dockerfile`; local stack via docker-compose
- **MkDocs** — `mkdocs.yml`, `shop/mkdocs.yml` (strict build, fails on broken links)

## Commands

Run `make help` for the full list. Most-used:

```bash
make doctor        # Verify local tooling + OCI access
make test          # Full local test gate (contract tests + docs)
make test-contract # Source-level observability + deployment contract tests
make verify        # Full validation gate (tests + mkdocs + drawio + deploy/verify.sh)
make local-up      # Start local docker-compose stack (no OCI needed)
make local-down    # Stop local stack
make local-logs    # Tail local stack logs
make docs-serve    # Serve MkDocs locally at http://localhost:8000
make docs-build    # Strict MkDocs build (fails on broken links)
```

E2E (from `shop/`): `npm run test:e2e` (see `shop/package.json` for focused suites:
`test:e2e:payments`, `test:e2e:shopping`, `test:e2e:auth`, …).

## Deploy

```bash
make deploy         # Build + push images + apply manifests for shop + CRM
make deploy-shop    # Shop only
make deploy-crm     # CRM only
make deploy-java-apm# Java payment sidecar
make smoke          # Smoke-check public endpoints (DNS + /ready + APM/RUM/logging)
make info           # Show current cluster + APM/logging configuration
```

Images build on the x86 control-plane VM (the dev Mac is ARM) — never build amd64 images
locally under QEMU. See deploy docs and the global build/deploy guidance.

## OCI tenancy discipline (read before any OCI/kubectl action)

- Tenancy: **emdemo** (profile `emdemo`, region `us-phoenix-1`) — **production**.
- Default **read-only**; only the `LogAnalytics` compartment is writable.
- OKE cluster in scope: **`octo-apm-demo-oke`** only. Confirm context before any
  `kubectl apply|edit|delete|patch`: `kubectl config current-context`.
- Never inline real OCIDs, public IPs, datakeys, or tenancy namespaces in committed files —
  use `<PLACEHOLDER>` tokens.

## Conventions

- Many small, focused files; explicit error handling; validate at boundaries.
- TDD with pytest; contract tests gate observability/deployment invariants (`make test-contract`).
- Docs are tested — keep MkDocs strict-clean (`make docs-build`).

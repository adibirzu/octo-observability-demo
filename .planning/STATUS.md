# Status Snapshot — 2026-06-04

Runtime + repo state at planning time. Not a health guarantee — re-run validation.

## Repo

- Branch: `main` (0 ahead / 0 behind `origin` before WS1; +2 local commits after).
- Working tree: clean.
- Tests: `python3 -m pytest tests/` → **222 passed (4.09s)**.
- Open GitHub issues/PRs: **0 / 0**.

## Known operational items

| Item | Severity | Action |
|------|----------|--------|
| `GITHUB_TOKEN` env var invalid (gh 401) | Med | `gh auth refresh -h github.com` or unset the env var |
| WS1 commits unpushed | Low | `git push origin main` after auth fix |

## Deployment (from site/operations/current-status.md)

- Shop / Admin(CRM) / Java payment gateway / Workflow Gateway deployed on VM + OKE.
- GenAI telemetry → APM (`octo-apm-ai`) + Langfuse/LLMetry + OCI Monitoring (`octo_genai`).
- `octo-genai-langfuse-apm-sync` CronJob hourly in `octo-drone-shop`.
- Custom metrics land in Phoenix Monitoring namespace `octo_apm_demo`; OKE/OCIR in Frankfurt.

## Validation commands

```bash
python3 -m pytest tests/ -q
make test-contract
make docs-build
```

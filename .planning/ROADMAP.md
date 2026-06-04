# Roadmap — octo-observability-demo

Durable planning home. Tasks are tracked in the session task list; this file is
the human-readable index. Last reviewed: **2026-06-04**.

## Workstreams

| WS | Title | Status | Notes |
|----|-------|--------|-------|
| WS1 | Land sanitization WIP + project CLAUDE.md | ✅ done | commits `9598be7`, `a262472` (unpushed) |
| WS2 | Fix GitHub auth + push WS1 | ⏳ blocked | `GITHUB_TOKEN` invalid; operator runs `gh auth refresh` |
| WS3 | Scaffold `.planning/` | 🔄 in progress | this directory |
| WS4 | GUI full redesign | ⏳ pending | direction TBD → see `design/redesign-brief.md` |
| WS5 | Enhancement backlog | ⏳ pending | see `BACKLOG.md` |
| WS6 | Reusable workflows | ⏳ pending | `.claude/workflows/` |

## Baseline (2026-06-04)

- Branch `main`, even with `origin`.
- Root contract suite: **222/222 green** (offline, 4.1s).
- Open GitHub issues: **0**.
- Stack: Python/FastAPI (primary), TS/Playwright, Java/Spring Boot sidecar, Docker, MkDocs.
- Deploy target: OKE on **emdemo** (production — read-only outside `LogAnalytics`).

## Principles

- emdemo is production: all app/GUI work stays local/staging; no OCI mutations from this roadmap.
- Every PR passes the pre-PR quality gate (see `.claude/workflows/`).
- Tests stay green; docs stay strict-clean (`make docs-build`).
- No real OCIDs/IPs/datakeys in commits — `<PLACEHOLDER>` tokens only.

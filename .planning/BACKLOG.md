# Enhancement Backlog (WS5)

Prioritized, **no-code** ideas. Each item is gated separately — promote to a task
only after scoping. Priority: P1 (next) → P3 (someday).

## GUI / UX

| # | Item | Priority | Notes |
|---|------|----------|-------|
| G1 | Full visual redesign of core surfaces | P1 | See `design/redesign-brief.md` (WS4) |
| G2 | Shared design-token sheet (dedupe shop+crm CSS) | P1 | Foundation for G1 |
| G3 | Checkout-evidence panel as polished "receipt" component | P2 | Trace/Order/Gateway IDs + copy buttons |
| G4 | Observability dashboards as data-viz design system | P2 | Sparklines, status chips, MELT-correlation cards |
| G5 | A11y baseline (contrast, focus, reduced-motion, landmarks) | P1 | Ship with G1 |
| G6 | Responsive audit 320/768/1024/1440 | P1 | shop styling is inline-only today |

## Observability / Demo depth

| # | Item | Priority | Notes |
|---|------|----------|-------|
| O1 | Surface GenAI-studio traces/cost in-app (not just APM/Langfuse) | P2 | Token/cost via Langfuse already |
| O2 | New workshop labs (beyond Lab 18 root-cause) | P3 | Follows existing lab format |
| O3 | RUM dashboard surface in CRM/Shop | P2 | `rum-advanced.js` exists |
| O4 | Security-triage UI (Cloud Guard / Data Safe findings) | P3 | Modules validated in cap |
| O5 | OKE autoscaling demo surface | P3 | `configure-cluster-autoscaler.sh` exists |

## Platform / DX

| # | Item | Priority | Notes |
|---|------|----------|-------|
| D1 | Pre-PR quality-gate workflow | P1 | WS6 |
| D2 | GUI-redesign review workflow (a11y + visual-regression) | P1 | WS6 |
| D3 | CI: add visual-regression job | P2 | After WS4c |

# Langfuse vs OCI APM for GenAI — head-to-head + APM gap backlog

This is a capability comparison between **Langfuse** (the LLM-native analytics pane) and
**OCI APM + the surrounding OCI observability stack** (APM Trace Explorer, Log Analytics,
Management Dashboards, OCI Monitoring) for the AI Studio + Drone Shop GenAI surface. It ends
with a concrete **"what to add to OCI APM"** backlog so the two panes reach parity.

Both backends are fed by **one OpenTelemetry `TracerProvider`** in the studio service: APM gets
*every* span via OTLP/`Authorization: dataKey`; Langfuse gets the *GenAI-path subset* via a
span-name prefix filter (`coordinator.` `studio.` `agent.invoke.` `llm.invoke.` `gen_ai.`
`tool.` `retrieval.` `rag.` `vector_db.`). Same `gen_ai.*` attributes flow to both — so the raw
signal is largely identical; the difference is in **what each backend natively does with it**.

## Capability matrix

| Capability | Langfuse | OCI APM stack (today) | Gap |
| --- | --- | --- | --- |
| Distributed trace / span waterfall | ✅ observations tree | ✅ Trace Explorer (and APM sees the *full* shop→studio→agent trace; Langfuse only the GenAI subset) | **APM ahead** |
| Token usage (in/out/total) | ✅ native | ✅ `gen_ai.usage.*` on spans + `genai-token-*` LA searches + Command Center | parity |
| Cost (USD) | ✅ model-priced | ✅ `gen_ai.usage.cost_usd` (CostEnrichment) + `genai-cost-by-model` + Monitoring `genai_cost_usd` + daily-cost alarm | parity |
| Latency p50/p95 | ✅ native percentiles | ⚠️ only via Langfuse→Monitoring sync (`genai_latency_p50/p95_ms`); **not computed from APM spans directly** | **gap** |
| Sessions / threads (multi-turn grouping) | ✅ first-class sessions | ⚠️ `session.id` attribute exists but no session-rollup view/dashboard | **gap** |
| Prompt / completion content | ✅ stored, diffable, replayable | ⚠️ only if `OTEL_GENAI_CAPTURE_CONTENT=true` (≤600 chars on span); no diff/replay UI | **gap (by design — privacy)** |
| Scores / evals / LLM-as-judge | ✅ native scores API, eval runs | ⚠️ scores only land as `genai_judge_score_avg` metric via sync; **no per-trace score on the APM span** | **gap** |
| Dashboards | ✅ built-in usage/cost | ✅ 2 Management Dashboards + 1 Monitoring dashboard | parity |
| Alerting | ⚠️ limited | ✅ OCI Monitoring alarms (token-spike >100k/5m, cost >$25/day) | **APM ahead** |
| Cross-service correlation (RUM→shop→DB→GenAI) | ❌ GenAI-only | ✅ one APM trace end-to-end incl. payment/Java/ATP | **APM ahead** |
| Infra/topology, errors, service map | ❌ | ✅ APM native | **APM ahead** |
| Retention / RBAC / compartments | app-managed | ✅ OCI IAM + LA retention | **APM ahead** |
| Prompt-injection / guardrail visibility | via attributes | ✅ `genai-errors` LA search on `studio.guardrail.allowed=false` | parity |
| Per-agent fan-out analytics | ✅ | ✅ `ai_studio_agent_fanout` saved query + `genai-agent-fanout` | parity |
| Datasource provenance (live ATP vs synthetic) | via attributes | ✅ `genai-data-source-mix` | **APM ahead** |

**Net:** OCI APM already wins on **correlation, alerting, topology, RBAC, and end-to-end trace**.
Langfuse still wins on **LLM-native ergonomics**: per-trace scores, session/thread rollups,
prompt/completion diff+replay, and span-derived latency percentiles. Those four are the gap.

## What OCI APM already has (so we don't rebuild it)

- **APM saved queries** (`deploy/oci/apm/saved-queries/`): `ai_studio_agent_fanout`,
  `ai_studio_token_cost` (with `external_drilldowns` to Langfuse + Grafana),
  `assistant-genai-llmetry`, plus `payment-java-sidecar` + `checkout-end-to-end`.
- **Log Analytics searches** (`deploy/oci/log_analytics/searches/genai-*.sql`): token-trend,
  token-cost, cost-by-model, agent-fanout, data-source-mix, errors, assistant-llmetry.
- **Management Dashboards**: GenAI Command Center (7 widgets), GenAI APM Trace Dashboard (4).
- **OCI Monitoring**: `octo_genai` namespace (`genai_total/input/output_tokens`, `genai_cost_usd`,
  `genai_generations`, `genai_latency_p50/p95_ms`, `genai_judge_score_avg`, `genai_judge_scores`)
  + dashboard + 2 alarms.
- **In-app admin pane** (PR #18): `/admin/genai-observability` rolls these up live + deep-links out.

## The gap backlog — what to add to OCI APM (each gap → the concrete artifact)

### G1. Per-trace judge/eval scores on the APM span (not just an averaged metric)
Today scores only survive as the `genai_judge_score_avg` Monitoring metric. To see *which run*
scored low in APM:
- Emit `gen_ai.evaluation.score` + `gen_ai.evaluation.name` + `gen_ai.evaluation.passed` span
  attributes on `studio.brief|ask|rag` (write back from the judge into the run's span, or stamp
  via a post-run enrichment keyed on `studio.run_id`).
- New LA search `genai-judge-by-run.sql` (score by `studio.run_id`/model/agent) + a Command
  Center widget; alarm on `genai_judge_score_avg < threshold`.

### G2. Span-derived latency percentiles (independent of Langfuse)
Latency p50/p95 currently come *from Langfuse*. Add an APM-native path:
- LA `timestats`/`eventstats` percentile search over `SpanDuration` for `llm.invoke.*` and
  `studio.*` → `genai-latency-percentiles.sql` + Command Center widget. Removes the Langfuse
  dependency for the latency tiles.

### G3. Session / thread rollup view (multi-turn)
`session.id` is on every span but there's no rollup. Add:
- `genai-session-rollup.sql` (group by `session.id`: runs, total tokens, cost, agents, span
  count, first/last time) + a Command Center widget + an APM saved query scoped on `session.id`.
- Pairs with the chat work below (multi-turn makes sessions meaningful).

### G4. Prompt/completion capture policy + a safe preview surface
APM can hold previews (`gen_ai.prompt`/`gen_ai.completion`, ≤600 chars, flag-gated). To make it
useful without leaking PII:
- Document enabling `OTEL_GENAI_CAPTURE_CONTENT=true` in non-prod only; add a redacted
  `llm.prompt.preview_redacted`/`llm.response.preview_redacted` path (mirror the shop LLMetry
  redaction) so APM has *something* to show without raw content.
- LA search `genai-content-preview.sql` gated on the capture flag.

### G5. Cost/token model-coverage parity
`estimate_cost_usd` only knows a fixed model map; the Langfuse sync's `cost_usd` was 0 for models
missing from `MODEL_COSTS`. Add:
- A `gen_ai.usage.cost_source` attribute (`enriched` vs `langfuse_calculated`) and widen
  `MODEL_COSTS` (cohere/meta/google embed + new chat models) so APM cost ≠ Langfuse cost is
  explainable and rare.

### G6. Embedding/RAG retrieval analytics (new in PR #18 — wire the consumers)
The `retrieval.embed` + `vector_db.search` spans now exist but no LA search/widget reads them:
- `genai-rag-retrieval.sql` (by `vector.top_k`, `retrieval.documents.count`,
  `retrieval.top_distance`, embed latency) + a Command Center "RAG retrieval" widget +
  alarm on empty-retrieval rate (grounding-quality signal).

Every item above reuses the existing apply scripts: `deploy/oci/apm/apply_saved_queries.sh`,
`deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py`, `tools/monitoring-alarms/`.

## Bottom line

OCI APM is the **system-of-record** (correlation, alerting, RBAC, end-to-end). Langfuse is the
**LLM workbench** (scores, sessions, prompt diff/replay). Closing **G1–G3** (per-trace scores,
span-native latency, session rollup) gives OCI APM ~90% of Langfuse's day-to-day GenAI value
while keeping Langfuse for deep prompt iteration — and keeps everything in one correlated trace.

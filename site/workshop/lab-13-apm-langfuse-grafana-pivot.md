---
title: "Lab 13 — APM ↔ Langfuse ↔ Grafana Pivot"
description: "Pivot one GenAI run between OCI APM, Langfuse, and Grafana for the full dual-pane view."
---

# Lab 13 — APM ↔ Langfuse ↔ Grafana Pivot

!!! info "Lab Facts"
    - **Time:** 25 minutes
    - **Surface:** OCI APM, Langfuse (`lf.octodemo.cloud`), Grafana (`grafana.octodemo.cloud`)
    - **Prereqs:** Lab 12 complete; observability-stack deployed

## Objective

Take the same AI Studio run and view it in all three panes: the OCI APM trace
(infra + service map), the Langfuse trace (prompts, tokens, cost, judge scores),
and the Grafana FinOps dashboard (cost attribution) — using the trace id as the
join key.

## Steps

### 1. Capture the run

Generate a brief in AI Studio (Lab 12) and copy the trace id.

### 2. OCI APM pane

Open the trace in Trace Explorer. Open the **AI Studio — GenAI Token & Cost**
saved query; note the per-call `gen_ai.usage.cost_usd`. Use the saved query's
**external drilldown** links to jump to Langfuse and Grafana.

### 3. Langfuse pane

Open `https://lf.octodemo.cloud` → the same session/run. Inspect the prompts and
completions per agent, token usage, cost, and any LLM-as-judge scores (Lab 14).

### 4. Grafana pane

Open `https://grafana.octodemo.cloud` → **OCTO GenAI** folder → *LLM FinOps —
Token Cost Attribution*. Confirm the run's tokens/cost appear in the rollups
(published by the Langfuse → OCI Monitoring sync into the `octo_genai` namespace).

### What you should see

- The **same trace id** in APM and Langfuse.
- APM answers *"where did time/errors go across services?"*; Langfuse answers
  *"what did each agent prompt and spend?"*; Grafana shows *cost over time*.

## Verify

```bash
# Trigger the Langfuse -> OCI Monitoring sync once and confirm metrics flow.
python -m app.sync.langfuse_apm_sync --once --hours 1   # from services/genai-studio
echo "Expect genai_total_tokens / genai_cost_usd in OCI Monitoring namespace octo_genai"
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Langfuse trace missing | Span-prefix filter / keys | Confirm `LANGFUSE_*` keys + span names |
| Grafana panels empty | Sync not run / namespace | Run the sync; confirm `octo_genai` namespace |
| Drilldown link 404 | Hostname not provisioned | Point `*.octodemo.cloud` DNS at the LBs |

## Read More

- [GenAI monitoring (APM + Langfuse)](../observability-v2/ai-studio-genai-monitoring.md)
- [Observability stack install](../../services/observability-stack/README.md)

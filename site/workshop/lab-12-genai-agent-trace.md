---
title: "Lab 12 — GenAI Agent Trace Drill-Down"
description: "Trace an AI Studio agentic merchandising brief across six agents in OCI APM."
---

# Lab 12 — GenAI Agent Trace Drill-Down

!!! info "Lab Facts"
    - **Time:** 20 minutes
    - **Surface:** OCI APM, AI Studio (admin)
    - **Prereqs:** Lab 01 complete; admin access; AI Studio enabled (`AI_STUDIO_ENABLED=true`)

## Objective

Run the AI Studio agentic GenAI workflow and follow one request as a single
distributed trace across the supervisor and five agents in OCI APM — the same
trace structure you'll later compare against Langfuse (Lab 13).

## Steps

### 1. Generate a brief (admin only)

Open `${OCTO_LIVE_ADMIN_URL}/ai-studio` and submit, e.g.
`Build a merchandising brief for our thermal-mapping drones`. Note the **trace id**
shown with the result.

### 2. Open the trace in OCI APM

Console path:

```text
OCI Console → Observability & Management → Application Performance Monitoring → Trace Explorer
```

Search by the trace id, or filter:

```text
ServiceName = 'octo-genai-studio'
```

### 3. Walk the agent fan-out

In the span waterfall, confirm the order:

- `ai_studio.brief` (shop proxy) → `studio.brief` (studio root)
- `coordinator.supervisor`
- `agent.invoke.sales_analyst` → `tool.atp_query`
- `retrieval.evidence`
- `tool.code_interpreter`
- `agent.invoke.product_copy`
- `agent.invoke.presenter`
- `llm.invoke.*` children carrying `gen_ai.request.model` and token attributes

### What you should see

- One trace spanning **shop → studio → 6 agents → each LLM call**.
- `gen_ai.usage.input_tokens` / `output_tokens` / `cost_usd` on each `llm.invoke.*` span.
- `studio.data_source` = `oracle_atp` (or `synthetic` with a `fallback_reason`).

## Verify

```bash
# The APM saved query "AI Studio — Agent Fan-out" returns the ordered spans.
echo "Trace shows coordinator.supervisor + 5 agent.invoke.* spans, 0 errors"
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/ai-studio` redirects to login | Not an admin session | Sign in as admin |
| Trace only shows `studio.*` | Inbound traceparent not propagated | Confirm shop proxy injects trace context |
| `data_source = synthetic` | ATP read fell back | Check `fallback_reason` on `tool.atp_query` |

## Read More

- [AI Studio](../drone-shop/ai-studio.md)
- [GenAI monitoring (APM + Langfuse)](../observability-v2/ai-studio-genai-monitoring.md)

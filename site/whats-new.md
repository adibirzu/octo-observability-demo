---
title: What's new
description: Latest components and changes in the OCTO Observability Demo platform (2026-06).
---

# What's new — latest components & changes (2026-06)

A concise digest of the most recent additions to the platform. Each item links to
the page that documents it in full. For the broader signal story see the
[Observability v2 overview](observability-v2/index.md); for deployment see the
[Quickstart](getting-started/quickstart.md) and
[Deployment options](getting-started/deployment-options.md).

## AI Studio — agentic GenAI

<div class="grid cards" markdown>

-   :material-login-variant: **Admin-host sign-in + seamless CRM → AI Studio SSO**

    ---

    AI Studio is **admin-host-only**. A single CRM portal login also mints the
    shop's `octo_session` cookie (shared `octo-auth/token-secret`), so opening
    `/ai-studio` from the CRM nav goes straight in — **no second prompt**. A
    standalone `/ai-studio/login` page still covers operators who land on AI
    Studio first; CRM logout clears both.

    [:octicons-arrow-right-24: AI Studio sign-in](drone-shop/ai-studio.md#admin-sign-in)

-   :material-message-text-outline: **Chat (multi-turn) mode with streaming**

    ---

    A conversational surface alongside the single-shot **Ask**, **RAG**, and
    **Brief** modes. The studio keeps a bounded, session-scoped history and
    **replays prior turns** into each OCI GenAI call; set `stream=true` for an
    SSE token stream (time-to-first-token is recorded on the span). Each
    conversation is one correlatable `session.id` in APM and Langfuse.

    [:octicons-arrow-right-24: Multi-turn chat](drone-shop/ai-studio.md#multi-turn-chat)

-   :material-database-search-outline: **RAG on Oracle Database 19c (app-side cosine)**

    ---

    The **Ask the catalog (RAG)** mode runs an **app-side cosine** similarity
    search over embeddings stored as JSON in a CLOB (`genai_kb`) on Oracle
    Database **19c** — there is **no** 23ai native `VECTOR` type or
    `VECTOR_DISTANCE`. Every retrieval step is a span, so cost and grounding are
    visible, with cosine-distance citations.

    [:octicons-arrow-right-24: RAG span model](observability-v2/ai-studio-genai-monitoring.md#rag-over-the-oracle-19c-knowledge-base)

</div>

## GenAI observability

<div class="grid cards" markdown>

-   :material-chart-areaspline: **Dedicated `octo-ai-apm` APM domain**

    ---

    GenAI telemetry now flows to its **own** APM domain, separate from the shared
    main domain (correlated by `trace_id`). There the GenAI **numeric** attributes
    are activated and queryable: `gen_ai.usage.input_tokens` /
    `output_tokens` / `cost_usd` and `retrieval.documents.count`, plus the string
    dimensions (`gen_ai.agent.name`, `gen_ai.request.model`, `studio.mode`,
    `studio.outcome`, `studio.run_id`, `ai_studio.*`).

    [:octicons-arrow-right-24: Dedicated AI APM domain](observability-v2/ai-studio-genai-monitoring.md#dedicated-ai-apm-domain-octo-ai-apm)

-   :material-sitemap-outline: **Langfuse GenAI tracing**

    ---

    Langfuse (`lf.<DNS_DOMAIN>`) shows the full multi-agent trace tree with
    per-model token and cost detail — the LLM-native pane fed by the **same**
    OpenTelemetry `TracerProvider` as APM.

    [:octicons-arrow-right-24: GenAI monitoring](observability-v2/ai-studio-genai-monitoring.md)
    · [Langfuse vs APM](observability-v2/langfuse-vs-apm-genai.md)

-   :material-tune-variant: **In-product GenAI Observability page**

    ---

    `/admin/genai-observability` rolls up live token / cost / latency / judge
    tiles and a recent-generations table, deep-linking each row into OCI APM
    Trace Explorer, Langfuse, Grafana, and the GenAI Command Center dashboard.

    [:octicons-arrow-right-24: Admin GenAI Observability](observability-v2/ai-studio-genai-monitoring.md#admin-genai-observability-page)

</div>

## Database telemetry

<div class="grid cards" markdown>

-   :material-database-cog-outline: **OPS Insights + Database Management on the project ATP**

    ---

    The shared Autonomous DB **OCTOATP** (Oracle Database 19c) is monitored by
    **OPS Insights** and **Database Management**, with Stack Monitoring bridging
    the ATP node into the same topology. This is the durable ATP investigation
    path for SQL tuning, capacity, and health drilldowns.

    [:octicons-arrow-right-24: Stack Monitoring — Autonomous Database](observability-v2/stack-monitoring.md)

</div>

## Deployment

<div class="grid cards" markdown>

-   :material-rocket-launch-outline: **Resource Manager stack — one-click deploy**

    ---

    A **Deploy to Oracle Cloud** button provisions the platform from a packaged
    Terraform stack published at release **`stack-20260602`**
    (`octo-compute-stack.zip` = full private compute stack;
    `octo-stack.zip` = OKE infra). It is the fastest path to a running tenancy.

    [:octicons-arrow-right-24: Quickstart (one-click)](getting-started/quickstart.md#path-a-one-click-resource-manager-stack)
    · [Deployment options](getting-started/deployment-options.md)

</div>

## See it in a workshop lab

- [Lab 15 — GenAI Data Q&A: full lineage](workshop/lab-15-genai-data-qa-lineage.md)
- [Lab 16 — GenAI RAG retrieval lineage](workshop/lab-16-genai-rag-retrieval-lineage.md)

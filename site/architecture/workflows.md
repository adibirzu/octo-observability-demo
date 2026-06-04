# Workflows

This page walks the four defined workflows end to end — from a customer click in
the storefront through CRM order sync, into the AI Studio agentic GenAI modes,
and finally out to the OCI observability fan-out. For each stage it names **which
signals land where** so a reader knows exactly where to look in observability.

The companion diagram is authored in [Excalidraw](https://excalidraw.com) so
presenters can re-lay it out without a desktop tool.

## Diagram

[Download editable Excalidraw source](diagrams/octo-workflows.excalidraw)

The `.excalidraw` file is editable at
[excalidraw.com](https://excalidraw.com) (*File → Open* and select the
downloaded file) or in VS Code with the
[Excalidraw extension](https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor).
It depicts a left-to-right flow:

```
storefront browse/checkout  ->  CRM order sync  ->  AI Studio (ask/rag/brief/chat)
                                      |
                                      v
        OCI APM (main)  +  octo-ai-apm GenAI domain  +  Langfuse
        +  Logging Analytics  +  OPS Insights  +  Database Management  +  RUM
```

The published source uses `<DNS_DOMAIN>` placeholders only — no OCIDs, public or
private IPs, datakeys, or tenancy namespaces. Keep resolved values in local-only
operator notes, the same as the `.drawio` sources.

## Workflow 1 — Storefront browse and checkout

The customer journey runs on the public storefront host
(`drones.<DNS_DOMAIN>`).

| Step | Service | What happens |
|---|---|---|
| Browse / cart | `octo-drone-shop` (FastAPI) | Customer browses the catalog, builds a cart, and starts checkout. RUM runs in the browser. |
| Payment | `octo-apm-java-demo` | The Java payment APM sidecar verifies/authorizes the (synthetic) payment and enriches the active span with token-safe payment fields. |
| Persist | Autonomous DB `OCTOATP` (Oracle 19c) | Orders, customers, and catalog state are written to the shared database. |

**Where the signals land:**

- **OCI RUM** — browser session, page performance, and the customer-side view of
  the journey.
- **OCI APM (main domain)** — the server request trace across Shop and the Java
  payment sidecar, grouped by `workflow_id` (for example `checkout-v2`).
- **OCI Logging Analytics** — structured JSON logs joined to the trace via
  `oracleApmTraceId` (`trace_id <-> log`).
- **OPS Insights + Database Management** — the SQL and database-health view of
  the writes against `OCTOATP`.

## Workflow 2 — CRM order sync

Orders originate in the Shop and synchronize into the CRM admin console
(`admin.<DNS_DOMAIN>`).

| Step | Service | What happens |
|---|---|---|
| Order sync | `enterprise-crm-portal` (FastAPI) | Receives the order, reconciles customer + order records, and exposes them in the CRM admin console. |
| Workflow checks | `octo-workflow-gateway` (Go) | Select AI and the query lab run ATP workflow checks and component health surfaces. |

The Shop and CRM propagate the W3C `traceparent` plus `X-Request-Id`,
`X-Workflow-Id`, and `X-Run-Id` headers, so the order-sync hop stays on the same
trace as the originating checkout.

**Where the signals land:**

- **OCI APM (main domain)** — the cross-service trace continues from Shop into
  CRM; `service-trace-log-coverage` and `trace-drilldown` saved queries pivot
  here.
- **OCI Logging Analytics** — CRM logs joined on `oracleApmTraceId`,
  `order_id`, and `payment.gateway.request_id`.
- **OPS Insights + Database Management** — the shared `OCTOATP` SQL/db-health
  view for the CRM reads and writes.

## Workflow 3 — AI Studio (ask / rag / brief / chat)

`octo-genai-studio` is a LangGraph multi-agent application on OCI Generative AI
(`cohere.command-r-08-2024` for generation, `cohere.embed-multilingual-v3.0` for
embeddings). It is served **only on the admin host** (`admin.<DNS_DOMAIN>`).

A single CRM login mints the `octo_session` cookie (shared `octo-auth` token
secret), so opening **AI Studio** from the CRM nav is **seamless SSO** — no
second login. AI Studio reads the shared database through the read-only
`studio_ro` user.

| Mode | What it does | Notes |
|---|---|---|
| `ask` | Data Q&A over orders and products | Structured query path against `OCTOATP`. |
| `rag` | Retrieval-augmented answers over `genai_kb` | Oracle Database 19c **app-side cosine** over embeddings stored as JSON in a CLOB (not 23ai native `VECTOR` / `VECTOR_DISTANCE`). |
| `brief` | 6-agent merchandising brief | A multi-agent fan-out; one `studio.run_id` joins the whole run. |
| `chat` | Multi-turn conversation + streaming | Session memory across turns. |

**Where the signals land:**

- **octo-ai-apm domain** — a *dedicated* APM domain just for GenAI, where all
  GenAI numeric attributes are activated and queryable:
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.usage.cost_usd`, and `retrieval.documents.count`, plus the string
  dimensions `gen_ai.agent.name`, `gen_ai.request.model`, `studio.mode`,
  `studio.outcome`, `studio.run_id`, and the `ai_studio.*` family. Keeping GenAI
  on its own domain leaves numeric attribute slots free on the main domain.
- **Langfuse** (`lf.<DNS_DOMAIN>`) — the full multi-agent trace tree with
  per-model token and cost detail. The same tracer exports to APM and Langfuse,
  so the trace id is identical in both panes.
- **OCI Monitoring** — the hourly `octo-genai-langfuse-apm-sync` CronJob reads
  Langfuse aggregates and publishes tokens, cost, latency, and judge-score
  metrics into the `octo_genai` namespace for Management Dashboard and Grafana
  tiles.
- **OCI Logging Analytics** — AI Studio app logs carry `oracleApmTraceId`,
  `studio.run_id`, and the `gen_ai.*` fields for `trace_id <-> log` joins.
- **OPS Insights + Database Management** — `ask` and `rag` reads against
  `OCTOATP` (via `studio_ro`) appear in the same SQL/db-health surfaces.

## Workflow 4 — Observability fan-out

Every stage above emits a trace, a structured log, and a metric. The fan-out
makes a single business journey readable across the OCI observability stack.

| Destination | Carries | Best pivot |
|---|---|---|
| OCI APM (main) | Shop / CRM / Java / workflow traces and topology | `workflow_id`, `oracleApmTraceId`, `payment.gateway.request_id` |
| octo-ai-apm domain | GenAI numerics (tokens, `cost_usd`, retrieved docs) | `studio.run_id`, `studio.mode`, `gen_ai.request.model` |
| Langfuse (`lf.<DNS_DOMAIN>`) | Multi-agent trace tree, per-model token + cost | `studio.run_id` (= APM trace id), `session.id` |
| OCI Monitoring `octo_genai` | Langfuse-derived GenAI token, cost, latency, and judge-score metrics | `service=octo-genai-studio`, model, agent, run dimensions |
| OCI Logging Analytics | App / edge / DB logs with trace ids | `Trace ID`, `Order ID`, `Payment Gateway Request ID` |
| OPS Insights | ATP SQL + database performance | `OCTOATP` SQL id, wait events |
| Database Management | `OCTOATP` health + SQL diagnostics | database / SQL diagnostics |
| OCI RUM | Browser sessions + page performance | RUM session, customer journey |

## How to follow one journey across the panes

1. Start from a **RUM** session (the customer-side complaint).
2. Pivot to the **APM (main)** trace via `oracleApmTraceId` to see the
   server-side checkout and order-sync hops.
3. For an AI Studio run, switch to the **octo-ai-apm** domain and filter by
   `studio.run_id` to read tokens, `cost_usd`, and `studio.mode`; the same
   `run_id` opens the matching **Langfuse** multi-agent trace tree.
4. Use **OCI Monitoring** namespace `octo_genai` to confirm the hourly
   Langfuse-derived aggregate tiles are fresh.
5. Jump to **Logging Analytics** on the same `Trace ID` to read the structured
   log line for any hop.
6. Drop into **OPS Insights / Database Management** for the SQL and database
   health behind the writes against `OCTOATP`.

## Demo levers

These error-injection levers exercise the workflows above so the fan-out shows
real failure signatures:

- `WORKFLOW_FAULTY_QUERY_ENABLED` — the workflow gateway emits a slow/faulty SQL
  (surfaces in APM, Logging Analytics, OPS Insights, and Database Management).
- CRM Chaos admin (`/admin/chaos` presets) — latency and error injection across
  the storefront/CRM path.
- `PAYMENT_SIMULATION_MODE` (`approve` | `decline`) — toggles the checkout
  payment outcome.

## Related pages

- [Platform Overview](platform-overview.md) — full topology and OCI service
  boundaries.
- [System Design](system-design.md) — runtime topology and cross-service flows.
- [Correlation Contract](correlation-contract.md) — the identity fields that make
  every pivot above clickable.
- [Service Inventory](service-inventory.md) — shipped services and the signals
  they emit.
- [Diagrams README](diagrams/README.md) — shape/colour legend and re-render
  commands.

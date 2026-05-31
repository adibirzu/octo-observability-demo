# OCTO AI Studio — GenAI multi-agent service

A standalone **LangGraph** multi-agent service on **OCI Generative AI** that produces a
drone-shop *merchandising brief*, observable end-to-end in **OCI APM** and **Langfuse**.
It is the GenAI component of the [OCTO APM Demo](../../README.md), integrated into the
Drone Shop as a feature-flagged "AI Studio" admin surface — the shop proxies to it; the
heavy LLM/agent dependencies stay out of the shop image.

The design mirrors Dario Mandic's OCI multi-agent e-commerce demo and reuses the proven
OCI GenAI + Langfuse + OTEL patterns from `oci-coordinator-oke`.

## Agents

```
START → supervisor ─►(routes)─► sales_analyst → evidence → code_interpreter → product_copy → presenter → END
            ▲                                                                                      │
            └──────────────────────────── re-enters between each agent ────────────────────────────┘
```

| Agent | Span name | Role |
| --- | --- | --- |
| Supervisor | `coordinator.supervisor` | Plans + routes through the agent sequence (bounded by `STUDIO_MAX_STEPS`). |
| Sales Analyst | `agent.invoke.sales_analyst` | Read-only SELECT over ATP `orders`/`order_items`/`products` (synthetic fallback). |
| Evidence/RAG | `retrieval.evidence` | Grounds the brief in catalog facts (+ optional web search). |
| Code Interpreter | `tool.code_interpreter` | Deterministic pandas/matplotlib trend chart over the sales rows. |
| Product Copy | `agent.invoke.product_copy` | Merchandising copy grounded on sales + evidence. |
| Presenter | `agent.invoke.presenter` | Assembles the final markdown brief + chart. |

Each LLM call is wrapped in an `llm.invoke.*` span carrying OpenTelemetry `gen_ai.*`
attributes (model, tokens, finish reason), which both APM and Langfuse consume.

## Observability

One OTEL `TracerProvider` exports to **OCI APM** (OTLP/HTTP, same endpoint shape as the
shop) **and** to **Langfuse** via a span-prefix filter (`coordinator.`, `studio.`,
`agent.invoke.`, `llm.invoke.`, `gen_ai.`, `tool.`, `retrieval.`, `rag.`). The shop proxy
forwards W3C `traceparent`, so a single APM trace spans **shop → studio → each agent → each
LLM call**.

## Run locally

```bash
cd services/genai-studio
python -m venv .venv && . .venv/bin/activate
pip install -e .            # or: pip install -e '.[dev]'
cp .env.example .env        # fill OCI GenAI + (optional) Langfuse / APM / DB
uvicorn app.main:app --reload --port 8090
```

```bash
curl -s localhost:8090/readyz | jq
curl -s -X POST localhost:8090/api/studio/brief \
  -H 'content-type: application/json' \
  -d '{"request":"merchandising brief for our thermal-mapping drones"}' | jq
```

With no DB and no GenAI configured the graph still runs on synthetic data; the LLM-backed
agents degrade gracefully (the brief is assembled from the deterministic agents).

## Tests

```bash
pip install -e '.[dev]'
pytest -q          # graph compiles & terminates, guardrails, read-only SQL, Langfuse filter
```

## Configuration

See [`.env.example`](.env.example). Key groups: OCI GenAI (`OCI_GENAI_*`, `OCI_AUTH_TYPE`),
observability (`OCI_APM_*`, `LANGFUSE_*`, `OTEL_SERVICE_NAME`), data (`STUDIO_DB_*`), and
the service boundary key (`STUDIO_INTERNAL_SERVICE_KEY`, presented by the shop proxy).

## Deploy

- **Image:** build x86_64 on the control-plane VM, push to
  `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-genai-studio`.
- **OKE:** `shop/deploy/k8s/genai-studio.yaml` (Workload-Identity GenAI auth, Vault secrets).
- **Local:** the `genai-studio` service in `shop/docker-compose.yml` (host port 8091).

> **Tenancy policy:** validate in a staging tenancy first; deploy to production only after
> explicit approval. The ATP user must be **read-only**.

# Runbook — make the LogAnalytics GenAI dashboard tiles render

The "GenAI Command Center" / "GenAI APM Trace" Logging Analytics dashboard tiles
query **Log Source `octo-genai-studio`** for fields like `gen_ai.agent.name`,
`studio.outcome`, `gen_ai.usage.*`. genai-studio now emits those as structured
JSON to stdout, and the OKE Logging Analytics agent already ships container
stdout to LogAn — so the **data is in LogAn** (verified: a `studio.ask` event is
queryable). What's missing is a Log Source + JSON parser that extracts those keys
as fields, plus the pod annotation that routes genai-studio logs to that source.

> GenAI is already fully observable without this: the dedicated **`octo-ai-apm`**
> APM domain has all the numerics (tokens, cost, retrieval count) activated,
> **Langfuse** shows the full multi-agent trace tree, and the **GenAI
> Observability** page rolls up token/cost/latency. This runbook only lights up
> the *fourth* (LogAnalytics dashboard) surface.

## Why this is a Console task (CLI findings, 2026-06-02)

Creating the parser/fields reliably needs the **OCI Console → Logging Analytics
parser builder** (it previews the live JSON and auto-allocates field storage).
The CLI path is blocked at multiple points:

- `oci log-analytics parser upsert-parser` (type JSON) → *"At least one field
  mapping is required"* (no pure auto-discovery).
- A field-map must reference an **existing** field by `fieldName`; you cannot
  define a field inline (*"Invalid property name field"*).
- `oci log-analytics field upsert-field` will **not create** a custom field by a
  chosen name (*"Field not found"* — it is update-only for custom fields).

## Steps (OCI Console, ≈5–10 min)

1. **Sample log.** Grab one genai-studio event line:
   `kubectl logs -n octo-drone-shop -l app=octo-genai-studio --tail=50 | grep '"event": "studio.'`
   (fields: `event, service.name, gen_ai.agent.name, gen_ai.request.model,
   studio.mode, studio.outcome, studio.run_id, gen_ai.usage.input_tokens,
   gen_ai.usage.output_tokens, gen_ai.usage.cost_usd, retrieval.documents.count`).
2. **Create a JSON parser** — LogAn → Administration → Parsers → Create → JSON.
   Paste the sample; the builder auto-detects the keys. Keep the field display
   names **exactly** matching the keys the dashboards query (`gen_ai.agent.name`,
   `studio.outcome`, `gen_ai.usage.input_tokens`, …). Numerics as LONG/DOUBLE.
3. **Create a Log Source** `octo-genai-studio` — type *Application Log (for
   cloud)*, attach the JSON parser, entity type *Kubernetes*.
4. **Route the pods to the source** — annotate the genai-studio Deployment so the
   agent tags its logs with the source (mirrors the shop's `"SOC Application
   Logs"` annotation):
   ```yaml
   spec:
     template:
       metadata:
         annotations:
           oracle.com/oci_la_log_source_name: "octo-genai-studio"
           oracle.com/oci_la_log_set: "octo-apm-demo"
   ```
   `kubectl rollout restart deployment/octo-genai-studio -n octo-drone-shop`.
5. **Verify** — LogAn search:
   `'Log Source' = 'octo-genai-studio' | where 'gen_ai.agent.name' != null | stats count by 'gen_ai.agent.name'`
   should return rows within a few minutes; the dashboard tiles then populate.

## Related follow-up — re-export the platform-overview SVG

`site/architecture/diagrams/platform-overview.drawio` is updated (new GenAI / AI
Studio band) but the embedded **`platform-overview.svg`** is a hand-tuned
high-contrast export. Re-export it from **draw.io desktop** (File → Export →
SVG, overwrite `platform-overview.svg`, bump the `?v=` cache-bust in
`site/architecture/index.md` + `platform-overview.md`) to preserve the curated
styling — an automated headless export degrades the contrast.

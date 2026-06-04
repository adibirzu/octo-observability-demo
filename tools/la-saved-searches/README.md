# APM ↔ Log Analytics round-trip (Phase 1.3)

Closes the observability loop: every APM trace links to its log records,
every LA log record links back to the APM trace. Clickable both
directions.

## Components

| File | Purpose |
|---|---|
| `trace-to-logs.json` | Saved search parameterised by `${trace_id}`. APM widgets deep-link to it. |
| `errors-by-route.json` | Bar-chart widget: HTTP 4xx/5xx by route, last 1h. Populates the operations dashboard. |
| `slow-checkout-spans.json` | Table: checkout calls > 1s, grouped by `oracleApmTraceId` — click the trace id to jump into APM Trace Explorer. |
| `apply.sh` | Idempotent upsert of every `*.json` saved search via `oci log-analytics saved-search create-or-update`. |
| `smoke-test.py` | End-to-end smoke: given a trace id, polls LA until the log record arrives; asserts the round-trip works. |

## Wire it up

```bash
LA_NAMESPACE=<oci-tenancy-la-namespace> \
LA_LOG_GROUP_ID=<OCI_LOG_ANALYTICS_OCID> \
./tools/la-saved-searches/apply.sh
```

Then, in the **OCI APM → Trace Explorer** widget editor, add a drilldown
action on the "Trace ID" column:

```
https://cloud.oracle.com/loganalytics/search?region=${OCI_REGION}&savedSearch=octo-trace-to-logs&param.trace_id=${TRACE_ID}
```

Clicking a trace id in APM now opens LA filtered to that trace's logs.
Click a log record in LA and the `oracleApmTraceId` column links back
to `https://cloud.oracle.com/apm-traces/trace-explorer?traceId=<x>`.

## Validate end-to-end

```bash
# 1. Run the traffic generator briefly
OCTO_TRAFFIC_RUN_DURATION_SECONDS=90 \
OCTO_TRAFFIC_SHOP_BASE_URL=https://shop.example.test \
octo-traffic

# 2. Grab any trace_id from APM Trace Explorer (30 chars hex)
# 3. Run the smoke test
python tools/la-saved-searches/smoke-test.py \
    --la-namespace <namespace> \
    --trace-id <32-hex-chars> \
    --timeout 300
```

A passing run prints:

```
[poll 3] trace_id=abc...def found in LA after 28s
```

The searches query the live ingestion source — `OCI Unified Schema Logs`
filtered by `OCI Resource Name in ('octo-drone-shop', 'enterprise-crm-portal')`
— and `jsonextract` fields (`$.trace_id`, `$.url_path`, `$.http_status_code`,
`$.http_response_time_ms`) from `Message`. This matches the SQL correlation
searches in `deploy/oci/log_analytics/searches/`, so no custom source is
required for them to return rows.

If it times out, check:

- App logs are reaching LA via the Service Connector Hub (they land as
  `OCI Unified Schema Logs`, or `SOC Application Logs` for direct/OKE ingestion).
- The shop's `server/observability/logging_sdk.py` is stamping `trace_id`
  + `oracleApmTraceId` (it should — the correlation shim handles this).
- (Optional) For a dedicated promoted-field source, run
  `tools/create_la_source.py --apply` to register `octo-shop-app-json` and set
  `app_log_id` so the `la_pipeline_app_logs` connector is provisioned.

Typical ingestion latency on OCI: 30–120 s.

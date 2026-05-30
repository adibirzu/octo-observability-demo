# OCTO-DEMO — GenAI Observability Stack (external component)

A self-contained external component that stands up the **GenAI observability backends** for the
OCTO platform on **OKE**:

- **Langfuse** (`langfuse.octodemo.cloud`) — LLM/agent traces, prompts, token usage, cost, and
  LLM-as-a-judge scores for the [AI Studio](../genai-studio/README.md) multi-agent service.
- **Grafana** (`grafana.octodemo.cloud`) — GenAI FinOps / operations dashboards (token cost
  attribution, LLM operations, unified GenAI view) reading OCI Monitoring custom metrics and the
  AI Studio GenAI API via the Infinity datasource.

Together with **OCI APM** (the always-on, native trace surface) these form the complete OCI
observability picture for enterprise GenAI: APM for the distributed trace + service map, Langfuse
for the LLM-centric analytics, Grafana for cost/ops dashboards. APM **drilldowns** link out to both
(see the [GenAI monitoring guide](../../site/observability-v2/ai-studio-genai-monitoring.md)).

This is an **external/optional** component — the shop and existing monitoring run without it. It is
labelled `app.kubernetes.io/part-of: octo-demo-observability` and deployed into its own namespaces
(`octo-langfuse`, `octo-grafana`), separate from the app.

## Contents

| Asset | Path |
| --- | --- |
| Langfuse manifests (Postgres/ClickHouse/Redis/MinIO/web/worker) | `deploy/k8s/oke/langfuse/langfuse.yaml` |
| Langfuse deploy script | `deploy/oke/deploy-langfuse.sh` |
| Grafana manifest (Deployment/Service/LB/PVC/datasources) | `deploy/k8s/oke/grafana/grafana.yaml` |
| Grafana GenAI dashboards (ported from OCI-DEMO C32) | `deploy/k8s/oke/grafana/dashboards/*.json` |
| Grafana deploy script | `deploy/oke/deploy-grafana.sh` |
| Config contract (placeholders only) | `services/observability-stack/.env.example` |

## Preflight

```bash
cp services/observability-stack/.env.example services/observability-stack/.env   # fill in
set -a; . services/observability-stack/.env; set +a

./deploy/oke/deploy-langfuse.sh --check
./deploy/oke/deploy-grafana.sh  --check
```

Both scripts read `COMPARTMENT_ID` / `TARGET_VCN_ID` / `OCI_LB_SUBNET_OCID` from the env or from
`credentials/<profile>/outputs.json`, and **refuse to deploy to an OKE cluster outside the OCTO
project VCN** unless `ALLOW_DIFFERENT_VCN=true`.

## Apply

```bash
# 1) Langfuse
LANGFUSE_HOSTNAME=langfuse.octodemo.cloud ./deploy/oke/deploy-langfuse.sh

# 2) Grafana (after Langfuse, or independently)
GRAFANA_HOSTNAME=grafana.octodemo.cloud ./deploy/oke/deploy-grafana.sh
```

All secrets (Langfuse Postgres/ClickHouse/Redis/MinIO/encryption keys, Grafana admin password, the
GenAI API token) are **generated at deploy time** with `openssl` and stored only in Kubernetes
Secrets. None are committed.

## Wire the apps to it

1. Create a Langfuse project in the UI; copy its `pk-lf-…` / `sk-lf-…` ingestion keys.
2. Inject them into the shop + AI Studio (never commit):
   ```bash
   APP_LANGFUSE_PUBLIC_KEY=pk-lf-... APP_LANGFUSE_SECRET_KEY=sk-lf-... \
   LANGFUSE_PROJECT_NAME=drones.octodemo.cloud ./deploy/oke/deploy-langfuse.sh
   ```
   This updates the `octo-llmetry` secret in the shop namespace; the AI Studio reads the same keys.

## DNS / TLS

`*.octodemo.cloud` wildcard DNS + TLS are provisioned out of band (OCI DNS zone + cert import).
Point `langfuse.octodemo.cloud` / `grafana.octodemo.cloud` at the respective LoadBalancer external
addresses printed by each script.

## Low-usage defaults

Both stacks are sized as **test/visibility** endpoints, not high-throughput production. See the
per-component resource tables in `deploy/oke/langfuse/README.md`. Grafana runs 1 replica at
`100m`/`256Mi` requests with a `5Gi` PVC.

## Security

No tenancy names, OCIDs, IPs, datakeys, admin passwords, or Langfuse keys live in this component —
only `<PLACEHOLDER>` / `${VAR}` tokens and the accepted `*.octodemo.cloud` demo domain. A redaction
guard test (`tests/test_observability_stack_surface.py`) enforces this.

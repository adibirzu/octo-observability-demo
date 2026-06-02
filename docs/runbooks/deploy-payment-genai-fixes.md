# Runbook — Deploy the payment-decline + GenAI-sync fixes

Deploys the two fixes merged in **PR #55** to `octo-apm-demo-oke` (emdemo,
`LogAnalytics` compartment):

1. **Payment decline observability** — a declined/review payment no longer sets
   `otel.status_code=ERROR`. This lives in the **shop image** (`shop/server/modules/payments/*`),
   so it needs a shop image **rebuild + rollout**.
2. **GenAI metrics sync** — an hourly CronJob refreshes the OCI Monitoring
   `octo_genai` namespace. It runs the **existing genai-studio image**
   (`app.sync.langfuse_apm_sync`), so it's a **`kubectl apply`** — no rebuild,
   provided the running studio image was built from current `main`.

> **emdemo is production.** Review the diff, confirm the kubectl context, and
> prefer a low-traffic window. The dev Mac is ARM — build amd64 images on the
> `control-plane-oci` x86 VM (see `~/.claude/CLAUDE.md`). Resolve every
> `<PLACEHOLDER>` / `${VAR}` from `~/.claude/private/octo-apm-redactions.md`;
> never commit real OCIDs/IPs.

---

## Step 0 — Grant kubectl access (one-time, by a cluster-admin)

The emdemo API-key identity can mint an OKE token but isn't bound to Kubernetes
RBAC, so every `kubectl` call returns *"the server has asked for the client to
provide credentials."* Fix it with the RoleBinding in this repo.

**This must be applied by someone who already has cluster-admin on
`octo-apm-demo-oke`** (the cluster creator, a tenancy admin, or the OCI Console
→ *Kubernetes Cluster → Access Cluster → Cloud Shell*, which is admin):

```bash
# user OCID pulled from your local config — stays local, never committed
export OKE_RBAC_USER_OCID=$(awk '/^\[emdemo\]/{f=1;next}/^\[/{f=0}f&&/^user/{print $3}' ~/.oci/config | head -1)
envsubst < deploy/k8s/oke/rbac/octo-deployer-rolebinding.yaml | kubectl apply -f -
```

Then the granted user refreshes their kubeconfig and confirms the **right**
cluster (suffix `…cm67gejykua`, us-phoenix-1):

```bash
oci ce cluster create-kubeconfig --cluster-id <OKE_CLUSTER_OCID> \
  --region us-phoenix-1 --file ~/.kube/config --token-version 2.0.0 --profile emdemo
kubectl config current-context        # MUST map to …cm67gejykua, not another cluster
kubectl get pods -n octo-drone-shop   # should now succeed (RBAC bound)
```

---

## Step 1 — Build + push the shop image (x86 VM)

The decline fix is Python in the shop image. Build on `control-plane-oci`:

```bash
export OCIR_REGION=<OCIR_REGION> OCIR_TENANCY=${OCIR_TENANCY}   # from redactions file
IMG=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop
TS=$(date +%Y%m%d%H%M%S)

rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '.venv' \
  shop/ control-plane-oci:/tmp/octo-drone-shop/
ssh control-plane-oci "cd /tmp/octo-drone-shop && docker build -t $IMG:$TS -t $IMG:latest ."
ssh control-plane-oci "docker push $IMG:$TS && docker push $IMG:latest"
```

---

## Step 2 — Roll the shop Deployment

```bash
export OCIR_REGION=<OCIR_REGION> OCIR_TENANCY=${OCIR_TENANCY}
kubectl set image deployment/octo-drone-shop \
  app=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:$TS -n octo-drone-shop
kubectl rollout status deployment/octo-drone-shop -n octo-drone-shop
```

---

## Step 3 — Apply the CronJob + backfill now

The CronJob reuses the genai-studio image. Confirm that image was built from
current `main` (contains `app/sync/langfuse_apm_sync.py`); if it predates the
sync module, rebuild genai-studio the same way (context `services/genai-studio/`).

```bash
export OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}
export OCI_REGION=us-phoenix-1
envsubst < shop/deploy/k8s/genai-studio-langfuse-sync-cronjob.yaml | kubectl apply -f -

# don't wait for the top of the hour — run one now to un-stale octo_genai:
kubectl create job --from=cronjob/octo-genai-langfuse-apm-sync \
  octo-genai-sync-backfill -n octo-drone-shop
kubectl logs -f job/octo-genai-sync-backfill -n octo-drone-shop
```

---

## Step 4 — Verify

```bash
# shop running the new image
kubectl get deploy octo-drone-shop -n octo-drone-shop \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# octo_genai metrics fresh (datapoint within the last hour)
oci monitoring metric-data summarize-metrics-data --profile emdemo \
  --compartment-id <LOGANALYTICS_COMPARTMENT_OCID> \
  --namespace octo_genai \
  --query-text "genai_total_tokens[1h].max()"

# CronJob registered + last run
kubectl get cronjob octo-genai-langfuse-apm-sync -n octo-drone-shop
```

- **Payment fix:** in OCI APM (`octo-emdemo-apm`), open a *declined* checkout
  trace — `payment_gateway.credit_card.merchant_authorization_result` should now
  have **no** `otel.status_code=ERROR` (the trace stays `is-fault=false`). Follow
  **Lab 18** for the trace-path.
- **GenAI traces** were never missing — they're in the **`octo-ai-apm`** domain,
  not `octo-emdemo-apm`. This runbook only fixes the aggregate `octo_genai`
  Monitoring metrics.

---

## Rollback

```bash
kubectl rollout undo deployment/octo-drone-shop -n octo-drone-shop
kubectl delete cronjob octo-genai-langfuse-apm-sync -n octo-drone-shop
kubectl delete rolebinding octo-deployer -n octo-drone-shop      # revoke access
```

---

## Optional follow-up — make decline reasons visible in APM

Separately from this deploy, the antifraud attributes (`payment.decision_source`,
`payment.risk_score`, `payment.antifraud_reasons`) are not activated in the
`octo-emdemo-apm` domain, so the *reason* for a decline isn't queryable in Trace
Explorer. Activating custom span attributes is an APM-domain config change in the
`LogAnalytics` compartment (often Console-bound, like the Log Analytics
field/parser work) — stage and review before applying to production.

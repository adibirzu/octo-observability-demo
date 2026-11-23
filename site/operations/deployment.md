# Deployment

For the `DEFAULT` profile, use `example.test` as both the bootstrap base
domain (`DNS_BASE_DOMAIN`) and the rollout host domain (`DNS_DOMAIN`).
Check [Current Status](current-status.md) before relying on any shared
tenancy. As of May 4, 2026, the separate `<OCI_PROFILE>` private Compute
deployment is the current production-demo target for
`shop.example.test` and `crm.example.test`; the `DEFAULT` OKE
runtime remains a shared environment that should be validated before
hostname-only E2E.

For the non-Kubernetes production demo, use the
[Compute Deployment](../getting-started/compute-deployment.md) stack
instead of this OKE rollout page. That path creates or selects the VCN,
keeps Shop/CRM/ATP private, places OCI LB/WAF in front, deploys Podman
services on two Compute instances, and wires APM, OCI Logging, Log
Analytics, DB Management, Operations Insights, and Stack Monitoring
Standard.

## First-time tenancy bootstrap

Use `deploy/bootstrap.sh` for a fresh tenancy or a newly selected
compartment:

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=<OCI_COMPARTMENT_OCID> \
DNS_BASE_DOMAIN=example.test \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

This is the canonical end-to-end path: OCIR repos, kubeconfig, ATP,
wallet/secret seeding, shared ingress, TLS loading, DNS, and initial
Shop+CRM rollout.

## Ongoing rollouts

```bash
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
DNS_DOMAIN=example.test \
./deploy/deploy.sh                  # Build + push + rollout

./deploy/deploy.sh --build-only     # Build + push, no rollout
./deploy/deploy.sh --rollout-only   # Roll out the existing latest tag
./deploy/deploy.sh --shop-only      # Only the shop service
./deploy/deploy.sh --crm-only       # Only the CRM service
```

Use `deploy/init-tenancy.sh` only when the cluster, ATP, and ingress are
already managed out-of-band and you want the repo to seed namespaces,
repos, and secrets without running the full lifecycle wrapper.

## Manual Workflow

### 1. Sync to Build VM

```bash
rsync -az --exclude '.git' --exclude '__pycache__' \
  . remote-builder:/tmp/octo-apm-demo-shop/
```

### 2. Build (Native x86_64)

```bash
TAG=$(date +%Y%m%d%H%M%S)
ssh remote-builder "cd /tmp/octo-apm-demo-shop && \
  docker build -f shop/Dockerfile \
    -t <region>.ocir.io/<tenancy-namespace>/octo-drone-shop:${TAG} \
    -t <region>.ocir.io/<tenancy-namespace>/octo-drone-shop:latest ."
```

### 3. Push to OCIR

```bash
ssh remote-builder "docker push <region>.ocir.io/<tenancy-namespace>/octo-drone-shop:${TAG} && \
  docker push <region>.ocir.io/<tenancy-namespace>/octo-drone-shop:latest"
```

### 4. Rollout on OKE

```bash
kubectl set image deployment/octo-drone-shop \
  app=<region>.ocir.io/<tenancy-namespace>/octo-drone-shop:${TAG} -n octo-drone-shop

kubectl rollout status deployment/octo-drone-shop -n octo-drone-shop
```

## Verification

```bash
kubectl -n ingress-nginx get deploy,svc,pods,endpoints -o wide
kubectl get deploy -n octo-drone-shop octo-drone-shop
kubectl get deploy -n enterprise-crm enterprise-crm-portal
```

Both app deployments must show `2/2` before root Playwright E2E is
considered runnable.

## K8s Configuration

- **Replicas**: 2
- **Resources**: 250m CPU / 512Mi (request), 1 CPU / 1Gi (limit)
- **Liveness**: `/health` every 15s (12s initial delay)
- **Readiness**: `/ready` every 12s (18s initial delay)
- **Image pull**: OCIR with `ocir-pull-secret`
- **ATP wallet**: Mounted as read-only volume

## Preserve database data during restarts

Leave `ALLOW_DESTRUCTIVE_DB_BOOTSTRAP` unset. It defaults to false, and no
deployment manifest enables it. Setting it explicitly permits the legacy Shop
identity-repair reset when the users table is empty; that reset drops all modeled
application tables. It is intended only for an isolated database under a
separately reviewed recovery procedure.

Shop seeding and CRM bootstrap seed only when every modeled application table
is empty. If any application record exists, they preserve existing accounts,
password hashes, roles, catalog data and inventory. They also skip partially
populated databases, including a catalog with an empty users table. An existing
database does not receive a new CRM bootstrap account or automatic seed
reconciliation on restart. Manage existing accounts and data through the
application's normal administration flows.

For a new empty CRM database, configure the bootstrap admin password before
the first start. A populated database does not need a bootstrap credential just
to skip seeding.

Schema compatibility checks still run. They can add legacy columns or backfill
missing values, so this change does not make all startup database activity
read-only. Review schema changes and the database recovery plan before a rollout.
The state-preservation regressions use local SQLite fixtures; live Oracle and
PostgreSQL startup behavior requires separate provider validation.

# OKE RBAC Bootstrap

Use this directory when an OCI API-key identity can generate an OKE token but
Kubernetes rejects reads with `Unauthorized` / `the server has asked for the
client to provide credentials`.

OKE authentication and Kubernetes authorization are separate. Creating a
kubeconfig proves the OCI identity can authenticate to OCI, but the Kubernetes
API server still needs a RoleBinding or ClusterRoleBinding for that identity or
its OCI IAM group.

## Least-Privilege Shop Deployer

Prefer the namespace-scoped binding for the post-deploy operations needed by
the OKE shop fix:

```bash
K8S_NAMESPACE_SHOP=octo-drone-shop \
OKE_RBAC_SUBJECT_KIND=User \
OKE_RBAC_SUBJECT_NAME=<OCI_IAM_USER_OR_GROUP_OCID> \
envsubst < deploy/k8s/oke/rbac/octo-drone-shop-deployer-rolebinding.yaml | kubectl apply -f -
```

Use `OKE_RBAC_SUBJECT_KIND=Group` when binding an OCI IAM group instead of one
user. Keep concrete OCIDs local-only and out of committed files.

After the binding is applied from an already-authorized admin context, the
bound identity can run (preflight by default; `OCIR_REPO`/`OCI_REGION` are
required to render the CronJob image):

```bash
OCIR_REPO=<region>.ocir.io/<tenancy> OCI_REGION=us-phoenix-1 \
  ./deploy/oke/apply-post-rbac-fixes.sh             # dry-run preflight
OCIR_REPO=<region>.ocir.io/<tenancy> OCI_REGION=us-phoenix-1 \
  APPLY=true ./deploy/oke/apply-post-rbac-fixes.sh  # perform it
```

## Relationship to the broad `edit` bindings

`octo-deployer-rolebinding.yaml` and `octo-deployer-group-rolebinding.yaml` bind
the built-in ClusterRole **`edit`**, which grants read/write to **secrets** and
most namespaced resources. This `octo-drone-shop-deployer` custom Role is the
**least-privilege replacement** (no secrets; only the rollout/CronJob/read verbs
the deploy needs). **RBAC is additive** — if a subject keeps both, it still
effectively has `edit`. After migrating a subject to this Role, delete the broad
binding:

```bash
kubectl delete rolebinding octo-deployer octo-deployer-group -n octo-drone-shop
```

## Verification

From the newly bound identity:

```bash
kubectl auth can-i get pods -n octo-drone-shop
kubectl auth can-i patch deployments -n octo-drone-shop
kubectl auth can-i create cronjobs.batch -n octo-drone-shop
kubectl auth can-i get secrets -n octo-drone-shop
```

The first three should return `yes`. The secrets check should return `no`; this
binding is intentionally scoped to rollout, CronJob, and read-only workload
inspection.

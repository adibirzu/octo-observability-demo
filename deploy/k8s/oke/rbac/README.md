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
bound identity can run:

```bash
APPLY=true ./deploy/oke/apply-post-rbac-fixes.sh
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

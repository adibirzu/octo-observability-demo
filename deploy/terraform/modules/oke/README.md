# OKE module

Provisions a VCN-native OKE cluster sized for octo-apm-demo when the
tenancy does not already have one. Opt-in via `create_oke = true` in
the root `terraform.tfvars`.

## What it creates

| Resource | Notes |
|---|---|
| VCN `192.0.2.1/16` | Configurable via `vcn_cidr`. |
| Internet Gateway | Public egress for k8s API + LB subnets. |
| NAT Gateway | Outbound egress for private worker subnet. |
| Service Gateway | Private connectivity to OCI services (OCIR, ATP wallet, object storage). |
| Subnets | `k8s-api` (public), `workers` (private), `lb` (public), `pods` (private, /18). |
| OKE cluster | Enhanced, VCN-native pod networking. |
| Node pool | Default 3 × VM.Standard.E5.Flex · 2 OCPU · 16 GiB mem · 100 GB boot volume. |

The future-worker default changes from 93 GB to 100 GB. Existing boot disks are not shrunk.
Review all private input overrides and the authoritative saved plan before changing a live pool.
Image GC bootstrap is opt-in through `node_image_gc_bootstrap_enabled = true` in this module,
or `oke_node_image_gc_bootstrap_enabled = true` at the root. Both default to false.
When enabled, future-node user data passes image GC high/low thresholds of 75/60 percent through the OKE bootstrap.
The saved-plan run against the real stack needs separate operator GO.
See [storage hygiene](../../../../site/operations/storage-hygiene.md) for scope, validation, and approval steps.

## Inputs you must supply

```hcl
compartment_id            = "<OCI_COMPARTMENT_OCID>"
availability_domain_names = ["FHlk:EU-FRANKFURT-1-AD-1", "FHlk:EU-FRANKFURT-1-AD-2", "FHlk:EU-FRANKFURT-1-AD-3"]
node_image_id             = "ocid1.image.oc1.eu-frankfurt-1.xxx"   # OKE-managed image
```

Get the managed node image OCID matching your k8s version:

```bash
oci ce node-pool-options get --node-pool-option-id all --profile DEFAULT \
    | jq '.data.sources[] | select(."source-name" | test("OKE.*Oracle-Linux-8.*")) | {image_id: ."image-id", source_name: ."source-name"}' \
    | head -30
```

## Outputs consumed downstream

| Output | Downstream use |
|---|---|
| `cluster_id` | `oci ce cluster create-kubeconfig --cluster-id ...` |
| `lb_subnet_id` | `OCI_LB_SUBNET_OCID` env var on shop + crm deployments. |
| `vcn_id` | Peering, additional subnets, network policy debugging. |

## Post-apply steps

```bash
# 1. Kubeconfig
oci ce cluster create-kubeconfig \
    --cluster-id $(terraform output -raw cluster_id) \
    --file ~/.kube/config \
    --region $TF_VAR_region \
    --token-version 2.0.0 \
    --kube-endpoint PUBLIC_ENDPOINT \
    --profile DEFAULT

kubectl config rename-context $(kubectl config current-context) <OCI_PROFILE>-oke

# 2. Namespaces + imagePullSecret (if not using instance-principal OCIR pull)
kubectl create namespace octo-drone-shop
kubectl create namespace enterprise-crm
```

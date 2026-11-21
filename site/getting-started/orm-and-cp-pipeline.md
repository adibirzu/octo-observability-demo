# Deploy OCI Resource Manager stacks with the control-plane pipeline

Choose [OKE](oke-deployment.md) for Kubernetes or [private Compute](compute-deployment.md) for a load balancer in front of private Shop and CRM instances. The [repository operator runbook](https://github.com/adibirzu/octo-observability-demo/blob/main/docs/ORM-AND-PIPELINE.md) lists the package scripts, validation commands, and pipeline contract.

## Create a stack

| Package | Purpose |
| --- | --- |
| `octo-stack.zip` | Bootstrap APM, WAF, and optional Log Analytics connectors for an existing OKE deployment. Deploy the Kubernetes workloads and configure ingress separately. |
| `octo-compute-stack.zip` | Provision the private Compute topology with a public HTTPS load balancer. Select network reuse, private ATP, and observability options. |
| Legacy Shop `octo-stack.zip` | Build from `shop/deploy/resource-manager/stack-package.sh`. Store this archive separately. |

Run `make doctor` for tool and OCI profile checks. Confirm the region, compartment, policies, registry namespace, domain, and TLS certificate. Run `make verify` and read the local results.

Download the archive and `SHA256SUMS` from the same [GitHub Release](https://github.com/adibirzu/octo-observability-demo/releases). Verify the checksums. For a local build, run `bash deploy/resource-manager/stack-package.sh` or `bash deploy/compute/stack-package.sh`. Extract the zip to a scratch directory and run `terraform init -backend=false` followed by `terraform validate`.

In the OCI Console, open **Resource Manager → Stacks → Create Stack**, choose **My Configuration**, and upload the zip. Set `dns_domain` to your zone. For OKE, configure the observability inputs and WAF logging. For Compute, check the subnets, TLS certificate, image inputs, and ATP options. Review a Plan job before applying. If you use Helm for OKE workloads, set `global.dnsDomain` to the same zone.

## Render the pipeline matrix

Validate the [v1 manifest](https://github.com/adibirzu/octo-observability-demo/blob/main/deploy/cp-pipeline-manifest.json) against its sibling JSON Schema. The manifest binds this repository to OCI-DEMO component IDs `c2`, `c27`, and `c28`. Use the listed Dockerfiles and contexts for the DevOps build matrix. Record the image digests with the Git ref, archives, and SBOM.

Set `DNS_DOMAIN=lab.example.test` in the pipeline and substitute `<DNS_DOMAIN>`. Point `cp.lab.example.test` at the OCI-DEMO control plane. Route `shop.lab.example.test` and `crm.lab.example.test` to Shop and CRM. Configure `ai.lab.example.test` if you deploy AI Studio. Match the certificate and OIDC redirect URIs to the rendered origins. If you use the legacy OKE `drones` and `admin` aliases, configure the corresponding ingress and public app URLs before switching smoke checks to the canonical names.

Check the manifest's health paths and require `ready=true` for both applications. Inspect `/api/observability/melts` for configured capabilities and `/api/auth/sso/status` for SSO status. Run `make smoke`. Set `SHOP_HOST` and `ADMIN_HOST` if you use other hostnames. Run the [browser E2E tests](../testing/e2e.md) for cross-service behavior and OIDC callback validation.

## Verify telemetry with a synthetic order

1. Place a synthetic browser order. Confirm navigation and fetch timings in [RUM](../observability/rum.md). Capture the trace ID from the request's W3C `traceparent` header.
2. Find the matching APM trace. Check Shop, the downstream CRM or Java payment spans, and the ATP calls for that route. [Distributed trace guide](../observability/distributed-traces.md)
3. Search OCI Logging and then Log Analytics for the same `oracleApmTraceId`. The Service Connector routes OCI Logging records to the selected Log Analytics destination. Match the time window and span ID where present. [Application log guide](../observability/logs.md)
4. Match [OCI Monitoring metrics](../observability/metrics.md) and [Stack Monitoring](../observability-v2/stack-monitoring.md) entities to the environment. Inspect ATP or JVM health by resource and time. Record backend observations separately from configuration flags.

Register a web application in the OCI APM Console if you want RUM web application grouping. Use the APM Domain output and the public data key for browser beacons.

## Verify the CycloneDX inventory

Run `make sbom-check` before publishing. Run `make sbom` after changing a supported manifest or Dockerfile and review the diff. The CycloneDX 1.6 inventory records package URLs, versions where available, and Docker stages. Scan the immutable image digest for a runtime inventory.

## Diagnose a failed check

| Failure | First check |
| --- | --- |
| Archive import or module resolution | Verify the checksums and inspect the archive root with `unzip -l`. Repackage with the matching script. |
| Terraform provider error | Check the Terraform version and registry or cache. On macOS, use a shorter provider socket path. |
| DNS, TLS, or SSO | Match DNS records, certificate names, ingress or load balancer rules, and OIDC redirect URIs to the manifest. |
| Missing trace or log | Confirm exporter configuration, log IDs, and Service Connector source and destination. Query the receiving backend with the trace ID. |
| Missing resource metrics | Check Stack Monitoring discovery and management agent registration for the ATP or Java resource. |

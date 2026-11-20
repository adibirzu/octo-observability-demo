# Deploy the observability lab with Resource Manager

Use OCI Resource Manager (ORM) to prepare an OKE deployment or provision a private Compute deployment. The [MkDocs operator guide](../site/getting-started/orm-and-cp-pipeline.md) links to the signal-specific lab guides.

## Choose the topology and confirm inputs

| Topology | Archive or source | What it provides |
| --- | --- | --- |
| Oracle Kubernetes Engine (OKE) | `octo-stack.zip` from `deploy/resource-manager` | Bootstrap observability for an existing OKE deployment. The stack can create an APM Domain and WAF policies and connect existing OCI logs to Log Analytics. Prepare OKE, network access, ATP, secrets, ingress, and applications separately. |
| Private Compute | `octo-compute-stack.zip` from `deploy/compute` | A public HTTPS load balancer in front of private Shop and CRM instances. Configure subnet reuse and DNS, private Autonomous Transaction Processing (ATP), APM, logging, WAF, and Stack Monitoring as needed. |
| Legacy Shop bootstrap | `shop/deploy/resource-manager/stack-package.sh` | A separate source archive with the same filename as the OKE bootstrap. Use a separate output directory. |

Confirm the OCI profile, region, compartment, policy grants, registry namespace, and DNS zone before planning. Use an approved certificate, secret store, and immutable image tag or digest. Keep the APM endpoint, data keys, logging IDs, and Log Analytics destination from the same environment.

Run `make doctor` to check tooling and the selected OCI profile. Run `make verify` for local deployment, documentation, test, and SBOM checks. Read the warnings for checks that require more tooling or credentials.

## Build and verify an archive

On a published GitHub Release, the packaging workflow attaches both zips, the SBOM, and `SHA256SUMS`. A manually dispatched run produces the same Actions artifact. Download the archive for the intended tag and upload it manually if OCI cannot read a private release URL. [GitHub releases](https://github.com/adibirzu/octo-observability-demo/releases)

```bash
bash deploy/resource-manager/stack-package.sh --output-dir build/orm
bash deploy/compute/stack-package.sh --output-dir build/orm
bash shop/deploy/resource-manager/stack-package.sh --output-dir build/shop-orm
make sbom-check
```

From the asset directory, run `sha256sum -c SHA256SUMS` on Linux or `shasum -a 256 -c SHA256SUMS` on macOS. Inspect the archive with `unzip -l`. Expect `main.tf`, `variables.tf`, and `schema.yaml` at the root along with any local modules and bootstrap files. ORM supplies provider authentication and manages state.

```bash
mkdir -p build/orm-check/oke
unzip -q build/orm/octo-stack.zip -d build/orm-check/oke
terraform -chdir=build/orm-check/oke init -backend=false -input=false
terraform -chdir=build/orm-check/oke validate
```

Repeat for each archive in its own directory. Use Terraform 1.6 or newer for the legacy Shop archive. Terraform validation may need registry access to obtain a provider schema. On macOS, if provider startup reports `listen unix ... bind: invalid argument`, use a shorter scratch path or set `PLUGIN_UNIX_SOCKET_DIR=.` in the extracted configuration. [OCI Resource Manager configuration reference](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager.htm)

## Deploy through the OCI Console

1. Open **Developer Services → Resource Manager → Stacks → Create Stack**.
2. Choose **My Configuration**, select the target compartment and compatible Terraform version, and upload the ZIP.
3. Set `dns_domain` to your zone without a scheme or trailing dot. The OKE bootstrap derives Shop, CRM, Ops, and Coordinator hostnames. Override a hostname when reusing an existing name. Compute uses the Shop and CRM hostnames in load balancer rules.
4. For OKE, set the WAF log group and optional existing app log and Log Analytics destination. For Compute, select the network, DNS, TLS, image, ATP, and observability inputs. If Compute builds the apps from source, use a Git ref reachable from both private instances.
5. Run a Plan job and review additions and replacements. Apply through your approved change process.
6. For OKE, create the Kubernetes secrets, deploy the workloads, and configure ingress. For Helm, set `global.dnsDomain`. For guided OKE bootstrap, set `DNS_BASE_DOMAIN` to the pipeline's `DNS_DOMAIN`, `SHOP_SUBDOMAIN=shop`, and `CRM_SUBDOMAIN=crm`. Set the matching `SHOP_PUBLIC_URL` and `CRM_PUBLIC_URL` when invoking the lower-level workload script directly.
7. For Compute, check instance cloud-init, the application systemd services, and both load balancer backend sets. If you manage DNS externally, submit the Shop and CRM records to the DNS operator. Match the certificate names to the listener's host rules.

For RUM web application grouping, register a web application in the OCI APM Console and set `OCI_APM_WEB_APPLICATION`. The APM Domain supplies the endpoint and public data key for browser beacons. Keep the private key on the server.

## Configure the control-plane pipeline

The [version 1 manifest](../deploy/cp-pipeline-manifest.json) binds the repository to OCI-DEMO IDs `c2`, `c27`, and `c28`. Validate it against the [JSON Schema](../deploy/cp-pipeline-manifest.schema.json) from the same Git ref before building the DevOps matrix.

1. Set `DNS_DOMAIN` once in the pipeline environment. Substitute `<DNS_DOMAIN>` in each HTTPS origin. For `lab.example.test`, the hostnames are `cp.lab.example.test`, `shop.lab.example.test`, `crm.lab.example.test`, and `ai.lab.example.test`.
2. Build each image with the listed Dockerfile and context. The last entry in `stages` is the default. `stage-N` describes an unnamed stage. Pass `--target` only with an explicit Dockerfile stage name. Record the image digests by Git ref.
3. Route `cp` to the OCI-DEMO control plane, `shop` to Shop, and `crm` to CRM. Configure an AI Studio workload and ingress before enabling the `ai` probes. The ORM archives provision resources for this repository. The external control plane and optional AI Studio route require separate setup. Match DNS, certificates, and OIDC redirect URIs to the final origins.
4. Package and validate the selected ORM archive. Run the `health` GET probes and inspect readiness JSON. Shop can return HTTP 200 with `ready=false`. Inspect the `meltS` capability responses and require `configured=true` from `sso` when the identity provider is enabled.
5. Record the ref, archive checksums, image digests, and evidence. Mark a probe skipped when its optional component is disabled.

## Trace one transaction

1. Place a synthetic order in a browser. OCI APM Real User Monitoring (RUM) records navigation and fetch timings. Capture the trace ID from the browser request's W3C `traceparent` header.
2. Find the ID in OCI APM Trace Explorer. Check the Shop span and the downstream CRM, Java payment, or workflow gateway spans for the route used. Compare parent and child span IDs, then inspect the instrumented ATP calls.
3. Find the structured log in OCI Logging. Search Log Analytics for the same `oracleApmTraceId` after the Service Connector routes the record. Compare the timestamp, service, operation, and `oracleApmSpanId` where present.
4. Verify the metric or alarm in OCI Monitoring. Check ATP or JVM health in Stack Monitoring by resource identity and time window.
5. Run the relevant [browser tests](../site/testing/e2e.md) for cross-service requests and the OIDC browser callback. Run `make smoke` against a configured deployment. The make target uses the pipeline's Shop and CRM hostnames. Set `SHOP_HOST` and `ADMIN_HOST` if you use other hostnames. A readiness or capability flag reports application state. Query the receiving OCI backends to confirm ingestion.

## Refresh the CycloneDX inventory

Run `make sbom` after changing a supported manifest or Dockerfile. Review the diff and run `make sbom-check`. CI compares the committed [CycloneDX 1.6 SBOM](../sbom/octo-observability-demo.cdx.json) with a fresh offline generation. It lists Python, Go, npm, Maven, Docker base images, and Docker stages. Lockfile versions and exact pins carry version fields. Unresolved ranges and inherited versions stay in declaration properties. Input hashes detect changes to any supported file.

Use this inventory for pre-build review. Scan each built image digest when you need installed operating system packages or resolved runtime dependencies. [CycloneDX 1.6 JSON reference](https://cyclonedx.org/docs/1.6/json/)

## Troubleshoot

| Symptom | Check |
| --- | --- |
| ORM rejects the archive or reports an unreadable module | Check for the three root files. Repackage with the script to include the rewritten module paths. |
| Terraform init fails | Check the CLI version, provider constraints, registry reachability, and cache. Use `-backend=false` for local validation. |
| DNS or TLS fails | Check delegation, record targets, certificate SANs, listener rules, and all rendered origins. |
| SSO status is false or the callback fails | Check the issuer, client configuration, approved secret mount, and exact HTTPS redirect URI. Exercise the callback in an authorized browser test. |
| APM trace exists and Log Analytics has no match | Find the log in OCI Logging. Check the Service Connector's source, destination, and IAM. Confirm parser fields and time range. |
| Readiness fails | Check the ATP connection, wallet mount, and service logs. Check `/api/shop/app-server/health` for the Java health proxy. |
| SBOM freshness fails | Run `make sbom` at the intended Git ref and review the dependency and build-stage changes. |

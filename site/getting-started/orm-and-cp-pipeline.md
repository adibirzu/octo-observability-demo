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


## Publish public release SBOMs

The **ORM and SBOM release** workflow runs on a published release. It also
supports a manual package-only run. A manual run builds no images and pushes
nothing to a registry.

The release job uses the Dockerfiles and build contexts in
`deploy/cp-pipeline-manifest.json`. Native GitHub-hosted amd64 runners build
each image once. [Trivy](https://github.com/aquasecurity/trivy-action) generates a CycloneDX 1.6 package inventory and a JSON
vulnerability report for that local image before publication. The workflow
publishes that same image to the repository's GHCR package path with a
`sha-<COMMIT>` tag, records its registry digest, and attaches a [GitHub SBOM attestation](https://github.com/actions/attest-sbom)
to the digest. It does not use production registry credentials.

Release assets include:

- The validated Resource Manager archives and their checksums.
- `octo-observability-demo.cdx.json`, generated by scanning source dependency
  manifests and lockfiles at the release commit.
- `source-vulnerabilities.json`, containing the source scan's severity counts
  and package findings.
- One `<IMAGE>.cdx.json`, `<IMAGE>-vulnerabilities.json`, digest receipt, and
  checksum file for every image in the manifest.

`tools/generate_sbom.py` remains the offline declaration inventory and freshness
gate. Its committed output records declared versions and Docker stages. The CI
source scan adds discovered lockfile dependencies; neither source inventory
proves the full runtime dependency set. Use the image SBOM for installed OS and
application packages. Scanner coverage and the vulnerability database affect the
findings. A successful report is not a claim that an image has no vulnerabilities.

`tools/public_sbom.py` constructs the published artifacts from package identity
fields and selected vulnerability fields. It drops scanner filesystem locations,
root image coordinates, environment metadata, arbitrary properties, and raw
scanner output. A final guard rejects OCIDs, network addresses, private registry
coordinates, private service names, and unapproved hostname patterns. The same
guard checks the offline declaration inventory. New public dependency hosts
require an explicit allowlist review and regression test. Raw scanner files are
not uploaded as workflow artifacts or release assets. Private local receipts
under `.gate/` are excluded from Git and the Docker build context.

The vulnerability summary is informational and includes all scanner severities.
A scanner error, malformed report, privacy failure, image publication failure,
or attestation failure fails the release job. The workflow attaches release
assets only after every image job succeeds. Some images may already have been
published if a later job fails; inspect the run and its digests before a retry.

The workflow needs GitHub Packages write access and GitHub attestation/OIDC
permissions. Confirm the packages are associated with this repository and
configure their intended visibility before the first release. Public GitHub
release assets do not prove GHCR package visibility. A release is a separate
publication action; reviewing or merging this workflow does not deploy a demo,
copy production secrets, or promote an image into a production registry.

To inspect a release, verify its checksum files, resolve each image by the
recorded digest, and verify the GitHub attestation against this repository.
Production promotion must bind the approved digest to the selected deployment
and requires its own authorization. ARM workstations must use an approved native
amd64 builder or CI; the OKE build helper rejects a local amd64 build on ARM.

## Diagnose a failed check

| Failure | First check |
| --- | --- |
| Archive import or module resolution | Verify the checksums and inspect the archive root with `unzip -l`. Repackage with the matching script. |
| Terraform provider error | Check the Terraform version and registry or cache. On macOS, use a shorter provider socket path. |
| DNS, TLS, or SSO | Match DNS records, certificate names, ingress or load balancer rules, and OIDC redirect URIs to the manifest. |
| Missing trace or log | Confirm exporter configuration, log IDs, and Service Connector source and destination. Query the receiving backend with the trace ID. |
| Missing resource metrics | Check Stack Monitoring discovery and management agent registration for the ATP or Java resource. |

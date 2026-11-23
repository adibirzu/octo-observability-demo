# Publish demo images to a private registry

The manual `ocir-publish.yml` workflow builds four reviewed application images on
GitHub-hosted amd64 runners. It scans them before publishing to precreated private
repositories. It does not deploy applications.

Before dispatch, create the `demo-registry-publish` GitHub environment. Configure
required reviewers, prevent self-review, restrict deployments to main, and disable
protection-rule bypass where your GitHub plan supports it. Verify these settings
before every approved dispatch. A workflow environment name alone does not prove
that protection rules exist.

Store two environment secrets. Do not use repository-wide fallback credentials.

- `OCIR_PUSH_TOKEN` is a dedicated service user's auth token.
- `OCIR_PUBLISH_CONFIG` is a JSON object with `registry`, `namespace`,
  `username`, and `repositories`. The repository object has exactly the
  `shop`, `crm`, `java-apm`, and `workflow-gateway` keys.

The IAM owner must restrict that service user to read and update permissions on
the four precreated repositories. An OCI auth token inherits all permissions of
its user. It is not independently scoped. Repository update permission also
permits image deletion, so keep this principal separate from pull-only credentials.
Repository creation, IAM changes and credential delivery need separate approval.

After the workflow PR merges, request approval before dispatching it. Supply the
full 40-character reviewed source commit. The workflow runs only from main and
requires the source commit to be an ancestor of main. A commit from before the
publisher PR can be built after that PR merges.

Each matrix job builds a local candidate, produces an inventory, rejects HIGH and
CRITICAL vulnerabilities, and exports the sanitized SBOM with the existing public
exporter. The publisher requires linux/amd64, runtime UID 10001 and the selected
source revision label before it tags or pushes anything. Credentials are supplied
only to the final publishing step, through mode-0600 files. Docker uses an isolated
temporary credential directory. Subprocess output that could contain registry
coordinates stays out of the workflow log.

Each successful job uploads only the sanitized inventory, vulnerability summary
and a receipt containing the role, source SHA and independently read registry
digest. Failed publication produces no verified receipt. Image signatures,
end-to-end application acceptance and deployment approval remain separate gates.
No release, public-registry copy or automatic rollout is configured.

Rotate by issuing a replacement dedicated token, updating the protected environment
secret, approving a verification build, and confirming all consumers switched.
Revocation and cleanup require separate approval. Keep staging image references
and credentials available until the operator accepts the rollout rollback window.

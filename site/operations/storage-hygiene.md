# Storage hygiene

Use this procedure to report storage candidates, review ownership, and approve each cleanup separately.

## Approval boundaries

This change prepares code only. Do not install host timers, enable cluster CronJobs, change node configuration,
delete resources, run a Helm upgrade, or apply Terraform until the operator approves that exact step.
Destructive live steps also require the designated independent approver.
A retention candidate is not deletion authority.

Guest cleanup frees filesystem space. It does not shrink a provisioned boot or block volume and does not release
the shared block-and-boot capacity quota. Container Registry images and volume backups have separate storage
accounting. Do not subtract them from the provisioned-volume quota.

## Report host storage

1. Copy the reviewed script through the existing Compute provisioning package after installation approval.
   The package includes `deploy/compute/storage_hygiene.py` and the `octo-storage-hygiene` service and timer.
2. Run the report on each approved application VM:

    ```sh
    sudo python3 /usr/local/libexec/octo/storage_hygiene.py
    ```

3. Review filesystem totals, directory sizes, eligible file bytes, and the printed command plan.
   Journal vacuum and package-cache cleaning are host-wide actions, identified as such in the plan.
   An unavailable container runtime is reported as `runtime_unavailable`; report mode continues without its cleanup plan.
   The script reads rootful Docker and Podman stores. Run a separate report as the service user for any rootless store.
4. Keep app data, databases, wallets, bind mounts, and persistent container volumes outside the dedicated cleanup directories.
   Only explicitly disposable scratch volumes can use the name prefix `hygiene-scratch-` and the label
   `octo.hygiene.disposable=true`. Do not add that label to a data volume.
5. After per-host cleanup approval, run the same reviewed command with
   `--apply --approval cleanup-disposable-host-storage`.
6. Compare the before and after byte reports and verify application readiness.

The default age is 14 days and the minimum is seven. Cleanup vacuums archived journal files,
clears package download caches, prunes only dangling images carrying the disposable label,
and removes only unused explicitly disposable scratch volumes. It preserves stopped containers and their referenced volumes.
It deletes only aged `*.tmp` and `*.part` regular files directly in `/var/tmp/octo-hygiene` and rotated
`*.log.*` files directly in `/var/log/octo/hygiene`.
It does not recurse or follow symlinks. These directories must contain only expendable content.
The installer creates both dedicated directories owned by root with mode 0700.
Wallets, dumps, extensionless files, known database filename extensions, and hard-linked files remain excluded.
Even a caller-supplied wildcard cannot broaden the built-in file allowlist.

The provisioning installer installs a daily **report-only** timer. Existing VMs do not receive the change
automatically because their Terraform user-data is ignored after creation.
An approved operator can copy these files and install the units on an existing VM, or use a separately approved
OCI Run Command. This change does not invoke Run Command.
The timer never gains apply mode through an environment variable. Schedule destructive cleanup only after a separate
review of the unit's exact `ExecStart`, writable paths, retention, and approval scope.
Journal and package-cache cleanup are irreversible. Repull images and rebuild package caches if needed.

## Report Kubernetes candidates

1. Render the chart locally with synthetic inputs and `storageHygiene.enabled=true`.
2. Confirm each rendered Role and RoleBinding names an approved demo namespace.
3. Keep `storageHygiene.suspend=true` and `storageHygiene.apply=false` for the first reviewed installation.
4. After installation approval, obtain separate approval to unsuspend the report CronJobs.
5. Review their logs before requesting cleanup approval.
6. To activate cleanup later, confirm `storageHygiene.namespacesDedicated=true` and obtain approval for
   `storageHygiene.apply=true` and the corresponding namespaced delete RBAC. The chart rejects apply mode without that confirmation.

Each namespace has a separate service account. There is no ClusterRole or cross-namespace binding.
Report mode grants only reads. Apply mode adds single-object delete on Jobs, pods, and ReplicaSets.
The code selects objects labeled with the exact Helm release instance.
Kubernetes RBAC cannot restrict delete by label, so each enabled namespace must be dedicated to the demo.
System namespaces and the default namespace are rejected.
The default Python cleanup image is pinned to a verified multi-platform manifest digest. No image was pulled or run for this change.

The CronJobs run daily, forbid overlap, limit execution to ten minutes, and retain their own finished Job for one day.
The default candidate age is seven days. Completed and failed Jobs must have an aged terminal condition and no active work.
Only Failed pods are candidates. Pod age uses available status timestamps or, when absent, object creation time.
Review recent incident diagnostics before enabling this policy.
ReplicaSet cleanup requires a fully available, observed Deployment, a zero-replica historical ReplicaSet,
and a revision older than the Deployment's retained history.
All demo Deployments declare `revisionHistoryLimit: 5`.
Deletes include UID and resourceVersion preconditions, so a stale report cannot delete a replacement object.
A conflict or API error stops the run. No force deletion or finalizer removal exists.

Unbound PVCs are reported by name without delete permission. PVs remain operator reports because the CronJob
has no cluster-wide PV access. With read-only access to the verified cluster context, inspect:

```sh
kubectl --context <VERIFIED_CONTEXT> get pv -o json
kubectl --context <VERIFIED_CONTEXT> -n <DEMO_NAMESPACE> get pvc -o json
```

Unbound and Released volumes can hold recoverable data. Do not delete them through this workflow.

## Report OCI resources

1. Select the reviewed profile and region through `OCI_CLI_PROFILE` and `OCI_REGION`.
2. Bind the demo-owned compartment and exact allowed repository IDs privately.
   Do not pass a parent compartment that contains other owners' resources.
3. Use the installed OCI administrator pack:

    ```sh
    python3 tools/storage_janitor.py \
      --pack-root <OCI_SKILLS_PACK_ROOT> \
      --compartment-id <DEMO_COMPARTMENT_ID> \
      --project-tag <DEMO_PROJECT_TAG> \
      --repository-id <DEMO_OWNED_REPOSITORY_ID> \
      --days 30 --keep-images 10 \
      --output <NEW_PRIVATE_REPORT_PATH>
    ```

4. Review the private mode-0600 JSON report. Never commit or publish it.
5. Verify immutable ownership, attachment state, age, backups, restore needs, and running deployment image digests
   before proposing a deletion.

The collector uses `oci_cli` from the installed skill pack and checks installed CLI help before each read.
It reads all pages and all attachment states in the exact compartment.
It reports unattached AVAILABLE boot and block volumes, old AVAILABLE backups, and old images beyond the retained count.
Image reporting requires both the explicit repository allowlist and a matching repository project tag.
The versioned policy in `deploy/storage-hygiene-policy.json` sets report mode, a disabled provider policy,
a minimum of 30 days, at least ten newest images per repository, and explicit ownership requirements.
CLI overrides can increase retention but cannot reduce these versioned floors. Unknown volume ownership is shown as unknown.
Creator classes are tag-derived clues. They do not establish a person's identity or deletion authority.

**No OCI delete path is implemented.** Every row has `deletion_authorized=false`.
For any later implementation, re-read the exact object and require
`run_action --risk destructive --compartment <DEMO_COMPARTMENT_ID> --description <EXACT_ACTION> -- <VERIFIED_COMMAND>`.
First use `OCI_SKILLS_DRY_RUN=true`, then require the exact preview's
`OCI_SKILLS_APPROVAL`, an unexpired matching preflight receipt, operator approval, and independent destructive approval.
Do not run a direct delete or reuse an approval for another object.

The repo creates registry repositories through its tenancy initializer; it does not own a Terraform registry policy.
The installed OCI CLI exposes no retention-policy field in container-configuration update.
The reviewed [registry policy model](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrymanagingimageretention.htm)
has a global policy and custom policies scoped to selected repositories. Do not modify the tenancy-wide global policy.
Use this tool's versioned count-and-age report settings until an exact repository override API or provider schema is verified.
Automatic provider-policy activation remains unavailable in this change.

## Review future-node storage

The HCL changes the repository default from 93 GB to 100 GB for future workers and validates a 50 GB minimum.
Review the default change even when the deployment's private inputs retain a different explicit value.
This is a template change; an existing disk cannot be shrunk through this procedure.
The 100 GB proposal leaves room for an approximately 40 GiB working footprint, image churn,
logs, and free space. Confirm current root and image filesystem readings privately before accepting that budget.
An unreachable worker remains an unknown measurement.

The OKE-managed node bootstrap is opt-in. `oke_node_image_gc_bootstrap_enabled` defaults to false,
so this change does not supply node user data until you explicitly enable it in a reviewed plan.
When enabled, it passes image garbage collection thresholds of 75 percent high and 60 percent low
through the supported `--kubelet-extra-args` mechanism.
Those flags are deprecated upstream in favor of a kubelet configuration file but are supported by the reviewed OKE bootstrap.
They apply only to future workers. Do not run the bootstrap manually on existing workers.
The provider's `node_metadata.user_data` holds the bootstrap script.
See [OKE custom initialization](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingcustomcloudinitscripts.htm)
and the [kubelet flags](https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/).

1. Resolve the authoritative Terraform state owner and current live variable overrides.
2. Set `oke_node_boot_volume_gbs=100` in the private deployment inputs.
3. After Adi's separate GO for the real stack's saved-plan run, generate that plan with its authoritative backend and private input files.
   Enable `oke_node_image_gc_bootstrap_enabled=true` only if the same review explicitly includes the bootstrap change.
4. Review the complete plan, including size, Kubernetes version, image, desired node count, and unrelated drift.
5. Reject any plan that destroys a resource, cycles workers, or changes the desired node count without separate approval.
6. Obtain approval for the precise future-node template change before applying that saved plan.
7. Separately approve any node launch, with verified quota headroom, cost cap, and stop conditions.

No live saved plan was generated for this PR. Local HCL formatting and validation are the available checks.
The authoritative state owner is unavailable in this checkout. Do not infer it from a packaging script.
No Terraform plan from an unowned or empty state is a live review.
This change does not import resources, refresh another worktree's state, apply a plan, cycle nodes, or change quota policy.
A smaller new boot disk still needs enough provisioned-storage headroom.

## Validate locally

Run `python3 -m pytest -q tests/test_storage_hygiene.py`, `make test`, and `make verify`.
The behavioral tests exercise report-only execution, age filtering, ownership boundaries, active-resource preservation,
ReplicaSet retention, delete preconditions, rendered RBAC, disabled schedules, packaging inputs, and node defaults.
Local validation does not establish live cleanup acceptance.

For live acceptance, keep private before and after byte reports, exact approved previews,
fresh attachment and workload checks, successful readback, and any unreconciled quota gap.

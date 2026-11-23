"""Behavioral storage-hygiene safety contracts. No live clients."""

import importlib.util
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import os
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)


def load(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vm_report_never_executes_mutations():
    vm = load("deploy/compute/storage_hygiene.py")
    calls = []
    vm.run_commands(
        [["journalctl", "--vacuum-time=14d"], ["docker", "image", "prune", "-f"]],
        False,
        calls.append,
    )
    assert calls == []
    vm.run_commands([["dnf", "clean", "all"]], True, calls.append)
    assert calls == [["dnf", "clean", "all"]]


def test_vm_age_cleanup_preserves_new_files_directories_and_symlinks(tmp_path):
    vm = load("deploy/compute/storage_hygiene.py")
    old = tmp_path / "old.log.1"
    old.write_text("old")
    os.utime(old, (1, 1))
    new = tmp_path / "current.log"
    new.write_text("keep")
    data = tmp_path / "database.db"
    data.write_text("data")
    os.utime(data, (1, 1))
    link = tmp_path / "link.log.1"
    link.symlink_to(data)
    assert vm.clean_files(tmp_path, 100, "*.log.*", False) == 3
    assert old.exists()
    vm.clean_files(tmp_path, 100, "*.log.*", True)
    assert not old.exists() and new.exists() and data.exists() and link.is_symlink()


def test_vm_refuses_symlink_cleanup_root(tmp_path):
    vm = load("deploy/compute/storage_hygiene.py")
    real = tmp_path / "real"
    real.mkdir()
    (real / "old.log.1").write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        vm.clean_files(link, 100, "*", True)


def test_vm_volume_removal_is_opt_in_disposable_and_unused():
    vm = load("deploy/compute/storage_hygiene.py")
    volumes = [
        {"Name": "database", "Labels": {"octo.hygiene.disposable": "true"}},
        {"Name": "hygiene-scratch-a", "Labels": {"octo.hygiene.disposable": "true"}},
        {"Name": "hygiene-scratch-b", "Labels": {}},
    ]
    assert vm.disposable_volumes(volumes, {"hygiene-scratch-a"}) == []
    assert vm.disposable_volumes(volumes, set()) == ["hygiene-scratch-a"]


def obj(name, status=None, owner=None, **extra):
    return {
        "metadata": {
            "name": name,
            "namespace": "demo",
            "uid": name + "-uid",
            "resourceVersion": "1",
            "creationTimestamp": "2020-01-01T00:00:00Z",
            "ownerReferences": owner or [],
        },
        "status": status or {},
        **extra,
    }


def test_cluster_deletes_only_aged_terminal_resources():
    k = load("deploy/helm/octo-apm-demo/files/storage_cleanup.py")
    jobs = [
        obj(
            "success",
            {
                "conditions": [
                    {
                        "type": "Complete",
                        "status": "True",
                        "lastTransitionTime": "2020-01-01T00:00:00Z",
                    }
                ]
            },
        ),
        obj(
            "failure",
            {
                "conditions": [
                    {
                        "type": "Failed",
                        "status": "True",
                        "lastTransitionTime": "2020-01-01T00:00:00Z",
                    }
                ]
            },
        ),
        obj("active", {"active": 1}),
        obj(
            "recent",
            {
                "conditions": [
                    {
                        "type": "Complete",
                        "status": "True",
                        "lastTransitionTime": "2026-11-22T23:59:59Z",
                    }
                ]
            },
        ),
    ]
    pods = [obj("evicted", {"phase": "Failed"}), obj("running", {"phase": "Running"})]
    candidates = k.candidates(
        {"jobs": jobs, "pods": pods, "replicasets": [], "deployments": []},
        NOW,
        7 * 86400,
    )
    assert {(kind, o["metadata"]["name"]) for kind, o in candidates} == {
        ("jobs", "success"),
        ("jobs", "failure"),
        ("pods", "evicted"),
    }


def test_cluster_retains_revision_limit_and_active_or_orphan_replicasets():
    k = load("deploy/helm/octo-apm-demo/files/storage_cleanup.py")
    deployment = obj(
        "app",
        {"observedGeneration": 2, "updatedReplicas": 1, "availableReplicas": 1},
        spec={"replicas": 1, "revisionHistoryLimit": 1},
    )
    deployment["metadata"].update(
        generation=2, annotations={"deployment.kubernetes.io/revision": "4"}
    )
    rs = []
    for rev in range(1, 5):
        item = obj(
            "rs" + str(rev),
            {"replicas": 0},
            [{"kind": "Deployment", "uid": "app-uid", "controller": True}],
            spec={"replicas": 0},
        )
        item["metadata"]["annotations"] = {
            "deployment.kubernetes.io/revision": str(rev)
        }
        rs.append(item)
    orphan = obj("orphan", {"replicas": 0}, spec={"replicas": 0})
    result = k.candidates(
        {
            "jobs": [],
            "pods": [],
            "deployments": [deployment],
            "replicasets": rs + [orphan],
        },
        NOW,
        86400,
    )
    assert {o["metadata"]["name"] for _, o in result} == {"rs1", "rs2"}
    deployment["status"]["updatedReplicas"] = 0
    assert (
        k.candidates(
            {"jobs": [], "pods": [], "deployments": [deployment], "replicasets": rs},
            NOW,
            86400,
        )
        == []
    )


def test_cluster_report_does_not_delete_and_apply_uses_preconditions():
    k = load("deploy/helm/octo-apm-demo/files/storage_cleanup.py")
    calls = []
    target = obj("stale", {"phase": "Failed"})
    k.process([("pods", target)], False, lambda *a: calls.append(a))
    assert not calls
    k.process([("pods", target)], True, lambda *a: calls.append(a))
    assert calls[0][0] == "DELETE"
    assert calls[0][2]["preconditions"] == {"uid": "stale-uid", "resourceVersion": "1"}


def test_oci_report_excludes_attached_young_wrong_scope_and_kept_images():
    j = load("tools/storage_janitor.py")

    def volume(name, scope="demo", created="2020-01-01T00:00:00Z"):
        return {
            "id": name,
            "compartment-id": scope,
            "time-created": created,
            "lifecycle-state": "AVAILABLE",
            "size-in-gbs": 50,
            "freeform-tags": {"project": "demo"},
        }

    rows = j.report(
        {
            "boot": [
                volume("old"),
                volume("attached"),
                volume("other", "parent"),
                volume("young", created="2026-11-22T00:00:00Z"),
            ],
            "block": [],
            "boot-backups": [],
            "block-backups": [],
            "boot-attachments": [
                {"boot-volume-id": "attached", "lifecycle-state": "ATTACHED"}
            ],
            "block-attachments": [],
            "repositories": [
                {
                    "id": "repo",
                    "compartment-id": "demo",
                    "freeform-tags": {"project": "demo"},
                }
            ],
            "images": [
                dict(
                    volume(
                        "image" + str(i),
                        created="2020-01-0" + str(3 - i) + "T00:00:00Z",
                    ),
                    **{"repository-id": "repo"},
                )
                for i in range(3)
            ],
        },
        "demo",
        {"repo"},
        "demo",
        30,
        2,
        NOW,
    )
    assert {r["id"] for r in rows} == {"old", "image2"}
    assert all("creator" in r and "age_days" in r for r in rows)
    assert all(r["deletion_authorized"] is False for r in rows)


def test_oci_unknown_ownership_is_reported_not_authorized():
    j = load("tools/storage_janitor.py")
    v = {
        "id": "unknown",
        "compartment-id": "demo",
        "time-created": "2020-01-01T00:00:00Z",
        "lifecycle-state": "AVAILABLE",
    }
    rows = j.report({"boot": [v]}, "demo", set(), "demo", 30, 3, NOW)
    assert rows[0]["ownership"] == "unknown" and not rows[0]["deletion_authorized"]


def test_chart_cleanup_rbac_and_jobs_are_namespaced_and_report_only():
    r = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(ROOT / "deploy/helm/octo-apm-demo"),
            "--set",
            "storageHygiene.enabled=true",
            "--set",
            "global.image.tenancy=example",
            "--set",
            "global.image.region=example",
            "--set",
            "global.dnsDomain=example.invalid",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    docs = [x for x in yaml.safe_load_all(r.stdout) if x]
    jobs = [
        x
        for x in docs
        if x["kind"] == "CronJob" and "storage-hygiene" in x["metadata"]["name"]
    ]
    assert jobs
    for job in jobs:
        assert job["spec"]["suspend"] is True
        spec = job["spec"]["jobTemplate"]["spec"]
        assert spec["ttlSecondsAfterFinished"] == 86400
        container = spec["template"]["spec"]["containers"][0]
        assert "--apply" not in container["args"]
    roles = [
        x
        for x in docs
        if x["kind"] == "Role" and "storage-hygiene" in x["metadata"]["name"]
    ]
    assert len(roles) == len(jobs)
    for role in roles:
        assert not any(
            "*" in rule["verbs"] or "*" in rule["resources"] for rule in role["rules"]
        )
        assert not any(
            "persistentvolumes" in rule["resources"] for rule in role["rules"]
        )
        assert all(
            "delete" not in rule["verbs"]
            for rule in role["rules"]
            if "persistentvolumeclaims" in rule["resources"]
        )
    for d in docs:
        if d["kind"] == "Deployment":
            assert d["spec"]["revisionHistoryLimit"] == 5


def test_future_nodes_have_100gb_and_image_gc_bootstrap():
    root = (ROOT / "deploy/terraform/variables.tf").read_text()
    module = (ROOT / "deploy/terraform/modules/oke/main.tf").read_text()
    import re

    for text, key in [
        (root, "oke_node_boot_volume_gbs"),
        (module, "node_boot_volume_gbs"),
    ]:
        assert re.search(r'variable "' + key + r'"\s*\{[^}]*default\s*=\s*100', text)
    assert "node_metadata" in module and "user_data" in module
    init = (ROOT / "deploy/terraform/modules/oke/cloud-init.sh").read_text()
    assert (
        "--image-gc-high-threshold=75" in init and "--image-gc-low-threshold=60" in init
    )


def test_vm_timer_is_report_only_and_packaged():
    unit = (ROOT / "deploy/compute/systemd/octo-storage-hygiene.service").read_text()
    assert "storage_hygiene.py" in unit and "--apply" not in unit
    for path in [
        "deploy/compute/install.sh",
        "deploy/compute/terraform/main.tf",
        "deploy/compute/stack-package.sh",
    ]:
        source = (ROOT / path).read_text()
        assert "storage_hygiene.py" in source
        assert "octo-storage-hygiene.timer" in source


def test_retention_policy_is_disabled_and_limits_report_to_owned_repositories():
    policy = json.loads((ROOT / "deploy/storage-hygiene-policy.json").read_text())
    assert policy["mode"] == "report"
    assert policy["registry"]["provider_policy_enabled"] is False
    assert policy["registry"]["keep_images"] == 10
    assert policy["registry"]["minimum_age_days"] == 30
    assert policy["registry"]["require_repository_allowlist"] is True
    assert policy["registry"]["require_project_tag"] is True


def test_oci_collector_inventories_boot_attachments_in_every_ad():
    j = load("tools/storage_janitor.py")
    calls = []

    class Reader:
        def read(self, command):
            calls.append(command)
            if command[:3] == ["iam", "availability-domain", "list"]:
                return [{"name": "AD-A"}, {"name": "AD-B"}]
            if command[:3] == ["compute", "boot-volume-attachment", "list"]:
                assert "--availability-domain" in command
                return [
                    {
                        "boot-volume-id": command[
                            command.index("--availability-domain") + 1
                        ]
                    }
                ]
            return []

    result = j.collect(Reader(), "demo", set())
    assert {a["boot-volume-id"] for a in result["boot-attachments"]} == {"AD-A", "AD-B"}
    assert all(
        "--compartment-id" in cmd and cmd[cmd.index("--compartment-id") + 1] == "demo"
        for cmd in calls
    )


def test_oci_nodepool_creator_is_not_misclassified_as_human():
    j = load("tools/storage_janitor.py")
    assert (
        j.creator(
            {"defined-tags": {"Oracle-Tags": {"CreatedBy": "ocid1.nodepool.example"}}}
        )
        == "node-pool-principal-tag"
    )


def test_host_report_timer_sees_the_real_dedicated_temporary_directory():
    unit = (ROOT / "deploy/compute/systemd/octo-storage-hygiene.service").read_text()
    assert "PrivateTmp=true" not in unit
    assert "ProtectSystem=strict" in unit

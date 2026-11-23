#!/usr/bin/env python3
"""Private OCI storage report. No deletion path exists."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


def age_days(item, now):
    value = item.get("time-created")
    if not value:
        return None
    return (now - datetime.fromisoformat(value.replace("Z", "+00:00"))).days


def creator(item):
    created = (
        (item.get("defined-tags") or {}).get("Oracle-Tags", {}).get("CreatedBy", "")
    )
    if created.startswith("ocid1.nodepool."):
        return "node-pool-principal-tag"
    if created == "oke":
        return "service-tag:oke"
    if "instance" in created:
        return "instance-principal-tag"
    return "user-tag" if created else "unknown"


def report(data, compartment, repositories, project, days, keep, now):
    rows = []

    def append(kind, item):
        age = age_days(item, now)
        if item.get("compartment-id") != compartment or age is None or age < days:
            return
        rows.append(
            {
                "kind": kind,
                "id": item["id"],
                "age_days": age,
                "creator": creator(item),
                "size_gb": item.get("size-in-gbs"),
                "ownership": "project-tag"
                if (item.get("freeform-tags") or {}).get("project") == project
                else "unknown",
                "deletion_authorized": False,
            }
        )

    for kind, attachment, key in [
        ("boot", "boot-attachments", "boot-volume-id"),
        ("block", "block-attachments", "volume-id"),
    ]:
        attached = {
            a[key]
            for a in data.get(attachment, [])
            if a.get("lifecycle-state") != "DETACHED"
        }
        for item in data.get(kind, []):
            if (
                item["id"] not in attached
                and item.get("lifecycle-state") == "AVAILABLE"
            ):
                append(kind, item)
    for kind in ("boot-backups", "block-backups"):
        for item in data.get(kind, []):
            if item.get("lifecycle-state") == "AVAILABLE":
                append(kind, item)
    owned = {
        r["id"]
        for r in data.get("repositories", [])
        if r["id"] in repositories
        and r.get("compartment-id") == compartment
        and (r.get("freeform-tags") or {}).get("project") == project
    }
    for repo in owned:
        images = sorted(
            [
                i
                for i in data.get("images", [])
                if i.get("repository-id") == repo
                and i.get("lifecycle-state") == "AVAILABLE"
            ],
            key=lambda i: (i.get("time-created", ""), i["id"]),
            reverse=True,
        )
        for image in images[keep:]:
            append("image", image)
    return rows


class Reader:
    def __init__(self, pack):
        self.common = str(Path(pack).resolve() / "scripts/common.sh")
        if not Path(self.common).is_file():
            raise ValueError("OCI skills common.sh not found")

    def read(self, command):
        prefix = [
            "bash",
            "-c",
            'source "$1"; shift; oci_cli "$@"',
            "janitor",
            self.common,
        ]
        # Installed help validates each exact command/flag shape before reading.
        subprocess.run(prefix + command + ["--help"], check=True, capture_output=True)
        result = subprocess.run(
            prefix + command, check=True, capture_output=True, text=True
        )
        if not result.stdout.strip():
            return []
        value = json.loads(result.stdout)["data"]
        return value.get("items", []) if isinstance(value, dict) else value


def collect(reader, compartment, repositories):
    # No subtree traversal. All attachments across ADs are read before eligibility.
    commands = {
        "boot": ["bv", "boot-volume", "list"],
        "block": ["bv", "volume", "list"],
        "block-attachments": ["compute", "volume-attachment", "list"],
        "boot-backups": ["bv", "boot-volume-backup", "list"],
        "block-backups": ["bv", "backup", "list"],
        "repositories": ["artifacts", "container", "repository", "list"],
    }
    data = {
        key: reader.read(cmd + ["--compartment-id", compartment, "--all"])
        for key, cmd in commands.items()
    }
    domains = reader.read(
        ["iam", "availability-domain", "list", "--compartment-id", compartment, "--all"]
    )
    data["boot-attachments"] = []
    for domain in domains:
        data["boot-attachments"].extend(
            reader.read(
                [
                    "compute",
                    "boot-volume-attachment",
                    "list",
                    "--compartment-id",
                    compartment,
                    "--availability-domain",
                    domain["name"],
                    "--all",
                ]
            )
        )
    data["images"] = []
    for repo in data["repositories"]:
        if repo["id"] in repositories and repo.get("compartment-id") == compartment:
            data["images"].extend(
                reader.read(
                    [
                        "artifacts",
                        "container",
                        "image",
                        "list",
                        "--compartment-id",
                        compartment,
                        "--repository-id",
                        repo["id"],
                        "--all",
                    ]
                )
            )
    return data


def main():
    policy = json.loads(
        (
            Path(__file__).resolve().parents[1] / "deploy/storage-hygiene-policy.json"
        ).read_text()
    )
    if policy["mode"] != "report" or policy["registry"]["provider_policy_enabled"]:
        raise ValueError("only disabled provider policy and report mode are supported")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compartment-id", required=True)
    parser.add_argument("--repository-id", action="append", default=[])
    parser.add_argument("--project-tag", required=True)
    parser.add_argument("--pack-root", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="private JSON file, created mode 0600",
    )
    parser.add_argument(
        "--days", type=int, default=policy["registry"]["minimum_age_days"]
    )
    parser.add_argument(
        "--keep-images", type=int, default=policy["registry"]["keep_images"]
    )
    args = parser.parse_args()
    if args.days < 1 or args.keep_images < 1:
        parser.error("retention must be positive")
    if not os.environ.get("OCI_CLI_PROFILE") or not os.environ.get("OCI_REGION"):
        parser.error("set the reviewed OCI_CLI_PROFILE and OCI_REGION explicitly")
    os.umask(0o077)
    reader = Reader(args.pack_root)
    data = collect(reader, args.compartment_id, set(args.repository_id))
    rows = report(
        data,
        args.compartment_id,
        set(args.repository_id),
        args.project_tag,
        args.days,
        args.keep_images,
        datetime.now(timezone.utc),
    )
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump({"report_only": True, "candidates": rows}, output, indent=2)
    print("Private report written; no deletion was attempted.")


if __name__ == "__main__":
    main()

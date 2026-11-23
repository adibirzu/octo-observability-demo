#!/usr/bin/env python3
"""Namespaced terminal-object cleanup; report-only unless explicitly enabled."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import urllib.parse
import urllib.request


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def old(value, now, age):
    when = timestamp(value)
    return when is not None and (now - when).total_seconds() >= age


def candidates(snapshot, now, age):
    result = []
    for job in snapshot["jobs"]:
        if job["status"].get("active", 0):
            continue
        terminal = [
            c
            for c in job["status"].get("conditions", [])
            if c.get("type") in {"Complete", "Failed"} and c.get("status") == "True"
        ]
        if terminal and old(terminal[-1].get("lastTransitionTime"), now, age):
            result.append(("jobs", job))
    for pod in snapshot["pods"]:
        status = pod["status"]
        if status.get("phase") != "Failed":
            continue
        # Age is terminal timestamp where present, otherwise object creation age.
        times = [
            c.get("lastTransitionTime")
            for c in status.get("conditions", [])
            if c.get("lastTransitionTime")
        ]
        times += [
            c["state"]["terminated"]["finishedAt"]
            for c in status.get("containerStatuses", [])
            if c.get("state", {}).get("terminated", {}).get("finishedAt")
        ]
        if old(
            max(times) if times else pod["metadata"].get("creationTimestamp"), now, age
        ):
            result.append(("pods", pod))
    for deployment in snapshot["deployments"]:
        meta, spec, status = (
            deployment["metadata"],
            deployment.get("spec", {}),
            deployment.get("status", {}),
        )
        desired = spec.get("replicas", 1)
        current = meta.get("annotations", {}).get("deployment.kubernetes.io/revision")
        if (
            not current
            or status.get("observedGeneration", 0) < meta.get("generation", 1)
            or status.get("updatedReplicas", 0) != desired
            or status.get("availableReplicas", 0) != desired
        ):
            continue
        historical = []
        for rs in snapshot["replicasets"]:
            owners = rs["metadata"].get("ownerReferences", [])
            if not any(
                o.get("kind") == "Deployment"
                and o.get("uid") == meta["uid"]
                and o.get("controller")
                for o in owners
            ):
                continue
            revision = (
                rs["metadata"]
                .get("annotations", {})
                .get("deployment.kubernetes.io/revision", "")
            )
            if not revision.isdigit() or int(revision) >= int(current):
                continue
            historical.append(rs)
        historical.sort(
            key=lambda r: int(
                r["metadata"]["annotations"]["deployment.kubernetes.io/revision"]
            ),
            reverse=True,
        )
        for rs in historical[max(0, spec.get("revisionHistoryLimit", 10)) :]:
            if (
                rs.get("spec", {}).get("replicas", 0) == 0
                and all(
                    rs.get("status", {}).get(k, 0) == 0
                    for k in ("replicas", "readyReplicas", "availableReplicas")
                )
                and old(rs["metadata"].get("creationTimestamp"), now, age)
            ):
                result.append(("replicasets", rs))
    return result


def process(items, apply, request):
    for kind, item in items:
        meta = item["metadata"]
        print(json.dumps({"kind": kind, "name": meta["name"], "apply": apply}))
        if apply:
            request(
                "DELETE",
                kind + "/" + urllib.parse.quote(meta["name"], safe=""),
                {
                    "apiVersion": "v1",
                    "kind": "DeleteOptions",
                    "propagationPolicy": "Background",
                    "preconditions": {
                        "uid": meta["uid"],
                        "resourceVersion": meta["resourceVersion"],
                    },
                },
            )


class Client:
    def __init__(self, namespace):
        self.namespace = namespace
        service = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.token = (service / "token").read_text().strip()
        self.context = ssl.create_default_context(cafile=str(service / "ca.crt"))
        self.url = "https://kubernetes.default.svc"

    def request(self, method, resource, body=None):
        kind = resource.split("/")[0].split("?")[0]
        prefix = (
            "/apis/batch/v1"
            if kind == "jobs"
            else "/apis/apps/v1"
            if kind in {"deployments", "replicasets"}
            else "/api/v1"
        )
        url = (
            self.url
            + prefix
            + "/namespaces/"
            + urllib.parse.quote(self.namespace, safe="")
            + "/"
            + resource
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(
            request, context=self.context, timeout=30
        ) as response:
            return json.load(response)

    def listing(self, kind, selector):
        items, token = [], ""
        while True:
            query = urllib.parse.urlencode(
                {"labelSelector": selector, "limit": 200, "continue": token}
            )
            data = self.request("GET", kind + "?" + query)
            items.extend(data.get("items", []))
            token = data.get("metadata", {}).get("continue", "")
            if not token:
                return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--age-days", type=int, default=7)
    args = parser.parse_args()
    if args.age_days < 1:
        parser.error("age must be at least one day")
    namespace = os.environ["POD_NAMESPACE"]
    selector = os.environ["DEMO_SELECTOR"]
    if (
        not selector.startswith("app.kubernetes.io/instance=")
        or not selector.split("=", 1)[1]
    ):
        parser.error("a specific release selector is required")
    client = Client(namespace)
    snapshot = {
        kind: client.listing(kind, selector)
        for kind in ("jobs", "pods", "replicasets", "deployments")
    }
    # PVCs are a report only. No PV permission is granted to this service account.
    for pvc in client.listing("persistentvolumeclaims", selector):
        if pvc.get("status", {}).get("phase") != "Bound":
            print(
                json.dumps(
                    {
                        "kind": "persistentvolumeclaims",
                        "name": pvc["metadata"]["name"],
                        "report_only": True,
                    }
                )
            )
    process(
        candidates(snapshot, datetime.now(timezone.utc), args.age_days * 86400),
        args.apply,
        client.request,
    )


if __name__ == "__main__":
    main()

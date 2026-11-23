#!/usr/bin/env python3
"""Publish one scanned native-amd64 candidate without logging private coordinates."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

ROLES = ("shop", "crm", "java-apm", "workflow-gateway")


def read_private(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("A private regular file is required")
        if info.st_uid != os.getuid() or info.st_size > 65536:
            raise ValueError("Invalid private file owner or size")
        return stream.read()


def destination(config):
    if not isinstance(config, dict):
        raise ValueError("A destination object is required")
    registry, namespace, username = (config.get(k, "") for k in ("registry", "namespace", "username"))
    repositories = config.get("repositories", {})
    if not re.fullmatch(r"[a-z0-9-]+\.ocir\.io", registry):
        raise ValueError("Invalid registry")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", namespace):
        raise ValueError("Invalid namespace")
    if not username or any(c.isspace() or ord(c) < 32 for c in username):
        raise ValueError("Invalid registry login")
    if not isinstance(repositories, dict):
        raise ValueError("A repository object is required")
    if set(repositories) != set(ROLES) or len(set(repositories.values())) != len(ROLES):
        raise ValueError("Exactly four distinct approved repositories are required")
    for repository in repositories.values():
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", repository):
            raise ValueError("Invalid repository")
        if any(part in {"", ".", ".."} for part in repository.split("/")):
            raise ValueError("Invalid repository path")
    return registry, namespace, username, repositories


def publish(args):
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_sha):
        raise ValueError("An immutable source SHA is required")
    if not re.fullmatch(r"[0-9]+-[0-9]+", args.run_tag):
        raise ValueError("A unique workflow run and attempt are required")
    receipt = Path(args.receipt)
    if receipt.exists() or receipt.is_symlink():
        raise ValueError("Receipt output must be new")
    registry, namespace, username, repositories = destination(json.loads(read_private(args.config_file)))
    token = read_private(args.token_file).strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError("Invalid registry token")
    local_image = f"candidate-{args.role}:{args.source_sha}"
    image = f"{registry}/{namespace}/{repositories[args.role]}"
    target = f"{image}:sha-{args.source_sha}-{args.run_tag}"
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("OCIR_") and k not in {
               "GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "DOCKER_HOST", "DOCKER_CONTEXT",
           }}
    with tempfile.TemporaryDirectory(prefix="ocir-publish-") as directory:
        env["DOCKER_CONFIG"] = directory

        def docker(*command):
            return subprocess.run(
                ["docker", *command], env=env, capture_output=True, text=True,
                check=True, timeout=1800,
            ).stdout

        candidate = json.loads(docker("image", "inspect", local_image))[0]
        config = candidate.get("Config") or {}
        if (candidate.get("Os"), candidate.get("Architecture")) != ("linux", "amd64"):
            raise ValueError("Candidate architecture does not match")
        if (config.get("Labels") or {}).get("org.opencontainers.image.revision") != args.source_sha:
            raise ValueError("Candidate source does not match")
        if str(config.get("User", "")).split(":")[0] != "10001":
            raise ValueError("Candidate runtime user does not match")
        credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
        auth = Path(directory) / "config.json"
        descriptor = os.open(auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"auths": {registry: {"auth": credentials}}}, stream)
        docker("tag", local_image, target)
        docker("push", target)
        pushed = json.loads(docker("image", "inspect", target))[0]
        if pushed.get("Id") != candidate.get("Id"):
            raise ValueError("Candidate changed during publication")
        references = [x for x in pushed.get("RepoDigests", []) if x.startswith(image + "@")]
        if len(references) != 1:
            raise ValueError("An unambiguous pushed digest is required")
        digest = references[0].split("@", 1)[1]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError("Invalid pushed digest")
        remote = json.loads(docker(
            "buildx", "imagetools", "inspect", target,
            "--format", "{{json .Manifest}}",
        ))
        if remote.get("digest") != digest:
            raise ValueError("Remote digest does not match")
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"role": args.role, "source_sha": args.source_sha, "digest": digest}, stream)
    print("Published a verified image for " + args.role)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    try:
        publish(args)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError):
        parser.exit(1, "Publication failed; no verified receipt was written.\n")


if __name__ == "__main__":
    main()

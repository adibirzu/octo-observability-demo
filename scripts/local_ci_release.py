"""Run the release workflow checks that can use local inputs."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
STACKS = ("resource-manager", "compute")
REQUIRED_STACK_FILES = {"main.tf", "variables.tf", "schema.yaml"}
TRIVY_VERSION = "0.76.2"
TERRAFORM_VERSION = "1.14.3"


class Unavailable(RuntimeError):
    pass


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, timeout=240, **kwargs)


def matrix():
    builds = json.loads((ROOT / "deploy/cp-pipeline-manifest.json").read_text())["containerBuilds"]
    ids = set()
    for item in builds:
        role = item["id"]
        if not role or role in ids:
            raise ValueError("Missing or duplicate image role")
        ids.add(role)
        for key, expect_file in (("context", False), ("dockerfile", True)):
            value = item[key]
            if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Invalid build path")
            path = (ROOT / value).resolve()
            exists = path.is_file() if expect_file else path.is_dir()
            if not path.is_relative_to(ROOT) or not exists:
                raise ValueError("Build path must exist within the repository")
    if not ids:
        raise ValueError("Release image matrix is empty")
    return ids


def source_selection():
    source = run("git", "rev-parse", "--verify", "origin/main^{commit}", capture_output=True).stdout.strip()
    if len(source) != 40 or any(byte not in b"0123456789abcdef" for byte in source):
        raise ValueError("Invalid source commit")
    run("git", "merge-base", "--is-ancestor", source.decode(), "HEAD")
    if not {"shop", "crm", "java-apm", "workflow-gateway"} <= matrix():
        raise ValueError("An approved OCIR workflow role has no build")
    print("Main ancestry and candidate build paths verified")


def verify_checksums(directory, paths):
    checksums = directory / "SHA256SUMS"
    with checksums.open("w") as output:
        for path in paths:
            with path.open("rb") as artifact:
                digest = hashlib.file_digest(artifact, "sha256").hexdigest()
            output.write(f"{digest}  {path.name}\n")
    subprocess.run(
        ["shasum", "-a", "256", "--check", checksums.name], cwd=directory, check=True, timeout=60,
    )


def stack_checks(directory, *, validate):
    if validate:
        terraform = json.loads(run("terraform", "version", "-json", capture_output=True).stdout)
        if terraform.get("terraform_version") != TERRAFORM_VERSION:
            raise Unavailable(f"Workflow requires Terraform {TERRAFORM_VERSION}")
    for stack in STACKS:
        run("bash", f"deploy/{stack}/stack-package.sh", "--output-dir", str(directory))
    archives = sorted(directory.glob("*.zip"))
    if len(archives) != len(STACKS):
        raise ValueError("Expected two Resource Manager archives")
    for archive in archives:
        with ZipFile(archive) as package:
            files = set(package.namelist())
            if package.testzip() is not None or not REQUIRED_STACK_FILES <= files:
                raise ValueError("Invalid Resource Manager archive")
            if any(Path(name).name == "backend.tf" for name in files):
                raise ValueError("Resource Manager archive contains a backend")
            if validate:
                mirror = ROOT / ".gate/terraform-mirror"
                if not mirror.is_dir():
                    raise Unavailable("Offline provider mirror is missing (.gate/terraform-mirror)")
                stack = directory / archive.stem
                package.extractall(stack)
                config = directory / "terraform.rc"
                config.write_text(f'provider_installation {{\n filesystem_mirror {{\n path = {json.dumps(str(mirror))}\n }}\n}}\n')
                env = {**os.environ, "TF_CLI_CONFIG_FILE": str(config),
                       "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
                run("terraform", f"-chdir={stack}", "init", "-backend=false", "-input=false", "-no-color", env=env)
                run("terraform", f"-chdir={stack}", "validate", "-no-color", env=env)
    verify_checksums(directory, archives)


def tracked_snapshot(destination):
    tracked = run("git", "ls-files", "--cached", "-z", capture_output=True).stdout
    for entry in dict.fromkeys(tracked.split(b"\0")):
        if not entry:
            continue
        relative = Path(os.fsdecode(entry))
        source = ROOT / relative
        if not source.exists():
            continue
        if not source.is_file() or source.resolve() != source:
            raise ValueError("Source inventory requires regular tracked files")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def trivy_source(directory, *, vulnerabilities):
    trivy = shutil.which("trivy")
    if trivy is None:
        raise Unavailable(f"Trivy {TRIVY_VERSION} is missing")
    version = run(trivy, "--version", capture_output=True, text=True).stdout.splitlines()
    if f"Version: {TRIVY_VERSION}" not in version:
        raise Unavailable(f"Workflow requires Trivy {TRIVY_VERSION}")
    cache = ROOT / ".gate/trivy-cache"
    if vulnerabilities and not (cache / "db/trivy.db").is_file():
        raise Unavailable("Offline Trivy vulnerability database is missing (.gate/trivy-cache/db)")
    source = directory / "source"
    source.mkdir()
    tracked_snapshot(source)
    raw = directory / "source-raw.cdx.json"
    public = directory / "octo-observability-demo.cdx.json"
    source_sha = run("git", "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    flags = ("--offline-scan", "--skip-db-update", "--skip-java-db-update", "--skip-version-check")
    run(trivy, "fs", "--cache-dir", str(cache) if vulnerabilities else str(directory / "cache"),
        *flags, "--format", "cyclonedx", "--output", str(raw), str(source))
    extra = ()
    outputs = [public]
    if vulnerabilities:
        raw_vulns = directory / "source-vulns-raw.json"
        summary = directory / "source-vulnerabilities.json"
        run(trivy, "fs", "--cache-dir", str(cache), *flags, "--scanners", "vuln",
            "--format", "json", "--output", str(raw_vulns), str(source))
        print("Offline Trivy vulnerability scan completed", flush=True)
        extra = ("--vulnerabilities", str(raw_vulns), "--summary", str(summary))
        outputs.append(summary)
    run(sys.executable, "tools/public_sbom.py", "--input", str(raw),
        "--output", str(public), "--name", "octo-observability-demo", "--version", source_sha, *extra)
    run(sys.executable, "tools/public_sbom.py", "--check", str(public))
    verify_checksums(directory, outputs)


def main(command):
    try:
        if command == "matrix":
            print(f"Validated {len(matrix())} release build entries")
        elif command == "source":
            source_selection()
        else:
            with tempfile.TemporaryDirectory(prefix="release-") as temp:
                directory = Path(temp)
                if command in {"archives", "terraform"}:
                    stack_checks(directory, validate=command == "terraform")
                elif command in {"source-inventory", "source-vulnerabilities"}:
                    trivy_source(directory, vulnerabilities=command == "source-vulnerabilities")
                else:
                    raise ValueError("Unknown release check")
    except (Unavailable, FileNotFoundError) as error:
        print(f"Check unavailable: {error}")
        return 69
    except ValueError as error:
        print(f"Check failed: {error}")
        return 1
    except subprocess.SubprocessError as error:
        print(f"Check failed: {type(error).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

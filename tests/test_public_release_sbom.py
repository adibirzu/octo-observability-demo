import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_export(tmp_path, bom, vulnerabilities=None):
    source = tmp_path / "input.json"
    output = tmp_path / "public.json"
    source.write_text(json.dumps(bom))
    command = [sys.executable, str(ROOT / "tools/public_sbom.py"),
               "--input", str(source), "--output", str(output),
               "--name", "demo-shop", "--version", "v1.2.3"]
    if vulnerabilities is not None:
        raw = tmp_path / "scan.json"
        raw.write_text(json.dumps(vulnerabilities))
        command += ["--vulnerabilities", str(raw), "--summary", str(tmp_path / "summary.json")]
    return subprocess.run(command, capture_output=True, text=True), output


def bom(component=None):
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"component": {"name": "registry.private.example/team/shop"}},
            "components": [component or {"type": "library", "name": "requests",
                "version": "2.32.4", "purl": "pkg:pypi/requests@2.32.4",
                "properties": [{"name": "location", "value": "/private/build/work"}]}]}


def test_export_contains_only_public_package_inventory(tmp_path):
    result, output = run_export(tmp_path, bom(), {"Results": [
        {"Target": "registry.private.example/team/shop", "Vulnerabilities": [
            {"VulnerabilityID": "CVE-2026-12345", "Severity": "HIGH",
             "PkgName": "requests", "InstalledVersion": "2.32.4", "FixedVersion": "2.32.5"}]}]})
    assert result.returncode == 0, result.stderr
    public = json.loads(output.read_text())
    assert public["metadata"]["component"]["name"] == "demo-shop"
    assert public["components"][0]["purl"] == "pkg:pypi/requests@2.32.4"
    assert "private" not in output.read_text()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["counts"]["HIGH"] == 1
    assert summary["findings"][0]["id"] == "CVE-2026-12345"
    assert "Target" not in (tmp_path / "summary.json").read_text()


@pytest.mark.parametrize("private", [
    "ocid1.compartment.oc1..syntheticprivate",
    "phx.ocir.io/private-tenant/shop",
    "registry.private.example/team/shop",
    "payments.svc.cluster.local",
    "10.42.0.7", "https://secret.corp.invalid/token",
])
def test_export_rejects_private_package_identifiers_without_leaking_them(tmp_path, private):
    result, output = run_export(tmp_path, bom({"type": "library", "name": private}))
    assert result.returncode != 0
    assert not output.exists()
    assert "public SBOM rejected" in result.stderr
    assert private not in result.stdout + result.stderr


def test_failed_scan_is_not_reported_as_zero_vulnerabilities(tmp_path):
    result, output = run_export(tmp_path, bom(), {})
    assert result.returncode != 0
    assert not output.exists()
    assert "public SBOM rejected" in result.stderr


def test_source_inventory_is_public_safe():
    subprocess.run([sys.executable, str(ROOT / "tools/public_sbom.py"),
                    "--check", str(ROOT / "sbom/octo-observability-demo.cdx.json")],
                   check=True, capture_output=True)


def test_arm_workstation_refuses_amd64_before_cloud_or_build_calls(tmp_path):
    marker = tmp_path / "called"
    for name, content in {
        "uname": "#!/bin/sh\nprintf 'arm64\\n'\n",
        "oci": f"#!/bin/sh\ntouch '{marker}'\nexit 88\n",
        "docker": f"#!/bin/sh\ntouch '{marker}'\nexit 88\n",
    }.items():
        path = tmp_path / name
        path.write_text(content)
        path.chmod(0o700)
    import os
    result = subprocess.run(["bash", str(ROOT / "deploy/oke/build-push-images.sh")],
                            env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
                                 "PLATFORM": "linux/amd64"},
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "native" in result.stderr.lower()
    assert not marker.exists()


def test_private_gate_files_are_excluded_from_build_and_git():
    assert ".gate/" in (ROOT / ".dockerignore").read_text().splitlines()
    assert ".gate/" in (ROOT / ".gitignore").read_text().splitlines()


def test_release_requires_public_sboms_for_every_manifest_image():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/orm-and-sbom-release.yml").read_text())
    jobs = workflow["jobs"]
    assert {"package", "images", "attach"} <= jobs.keys()
    assert "images" in jobs["attach"]["needs"]
    steps = jobs["images"]["steps"]
    assert any("public_sbom.py" in step.get("run", "") for step in steps)
    assert any(step.get("uses", "").startswith("actions/attest-sbom@") for step in steps)
    uploads = [step["with"]["path"] for step in steps
               if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert uploads == ["release/"]


@pytest.mark.parametrize("component", [
    {"type": "library", "name": "shop", "purl": "pkg:docker/private-tenant/shop@v1"},
    {"type": "library", "name": "registry.secret.biz/team/shop"},
    {"type": "library", "name": "backend.corp"},
    {"type": "library", "name": "ocid%2531.compartment.oc1..synthetic"},
])
def test_export_rejects_private_registry_namespaces_and_encoded_identifiers(tmp_path, component):
    result, output = run_export(tmp_path, bom(component))
    assert result.returncode != 0
    assert "public SBOM rejected" in result.stderr
    assert not output.exists()

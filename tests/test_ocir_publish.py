import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/publish_ocir_image.py"
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def publisher(tmp_path):
    config = tmp_path / "destination.json"
    token = tmp_path / "token"
    config.write_text(json.dumps({
        "registry": "region.ocir.io", "namespace": "synthetic",
        "username": "synthetic/service",
        "repositories": {"shop": "demo-shop", "crm": "demo-crm",
                         "java-apm": "demo-java-payment", "workflow-gateway": "demo-workflow"},
    }))
    token.write_text("synthetic-test-token")
    config.chmod(0o600)
    token.chmod(0o600)
    docker = tmp_path / "docker"
    docker.write_text(
        "#!" + sys.executable + "\n"
        "import json,os,sys,pathlib\n"
        "args=sys.argv[1:]\n"
        "with open(os.environ['CALL_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')\n"
        "fault=os.environ.get('FAULT','')\n"
        "if args[:2]==['image','inspect']:\n"
        " image=args[2]; remote='region.ocir.io/synthetic/demo-shop'\n"
        " changed = fault=='image-id' and image.startswith('region.')\n"
        " print(json.dumps([{'Id':'sha256:changed' if changed else 'sha256:local','Os':'linux',"
        "'Architecture':'arm64' if fault=='architecture' else 'amd64',"
        "'Config':{'User':'0' if fault=='user' else '10001','Labels':{'org.opencontainers.image.revision':"
        "'c'*40 if fault=='source' else 'a'*40}},"
        "'RepoDigests':[] if fault=='zero-digests' else [remote+'@sha256:'+'b'*64,remote+'@sha256:'+'c'*64] if fault=='multiple-digests' else [remote+'@sha256:'+'b'*64]}]))\n"
        "elif args[:2]==['buildx','imagetools']:\n"
        " mismatch = fault=='digest' or (fault=='tag-retargeted' and ':sha-' in args[3])\n"
        " print(json.dumps({'digest':'sha256:'+('c' if mismatch else 'b')*64}))\n"
        "elif args[0]=='push' and fault=='push':\n"
        " print('synthetic-test-token region.ocir.io/synthetic',file=sys.stderr);sys.exit(1)\n"
        "elif args[0]=='push':\n"
        " auth=pathlib.Path(os.environ['DOCKER_CONFIG'])/'config.json'\n"
        " assert auth.stat().st_mode & 0o777 == 0o600\n"
        " pathlib.Path(os.environ['AUTH_LOCATION']).write_text(str(auth))\n"
    )
    docker.chmod(0o700)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               CALL_LOG=str(tmp_path / "calls.jsonl"), AUTH_LOCATION=str(tmp_path / "auth-location"),
               DOCKER_CONFIG="/must/not/be/used", OCIR_PUSH_TOKEN="must-not-reach-child")
    return tmp_path, config, token, env


def run(publisher, run_tag="123-1", **changes):
    tmp, config, token, env = publisher
    env.update(changes)
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--role", "shop", "--source-sha", SHA,
        "--run-tag", run_tag, "--config-file", str(config),
        "--token-file", str(token), "--receipt", str(tmp / "receipt.json"),
    ], env=env, capture_output=True, text=True)
    log = tmp / "calls.jsonl"
    calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return result, calls


def test_publish_pins_source_and_remote_digest_without_disclosing_destination(publisher):
    result, calls = run(publisher)
    assert result.returncode == 0, result.stderr
    tmp = publisher[0]
    assert json.loads((tmp / "receipt.json").read_text()) == {
        "role": "shop", "source_sha": SHA, "digest": DIGEST,
    }
    assert any(c[0] == "push" for c in calls)
    assert (tmp / "receipt.json").stat().st_mode & 0o777 == 0o600
    assert not Path((tmp / "auth-location").read_text()).exists()
    assert "region.ocir.io" not in result.stdout + result.stderr
    assert "synthetic-test-token" not in result.stdout + result.stderr


@pytest.mark.parametrize("fault", ["architecture", "source", "user"])
def test_mismatched_candidate_never_reaches_registry(publisher, fault):
    result, calls = run(publisher, FAULT=fault)
    assert result.returncode != 0
    assert not any(c[0] in {"tag", "push"} for c in calls)


@pytest.mark.parametrize("fault", ["push", "digest"])
def test_registry_failure_has_no_receipt_or_private_output(publisher, fault):
    result, _ = run(publisher, FAULT=fault)
    assert result.returncode != 0
    assert not (publisher[0] / "receipt.json").exists()
    assert "region.ocir.io" not in result.stdout + result.stderr
    assert "synthetic-test-token" not in result.stdout + result.stderr


def test_world_readable_token_is_rejected_before_docker(publisher):
    publisher[2].chmod(0o644)
    result, calls = run(publisher)
    assert result.returncode != 0
    assert not calls


@pytest.mark.parametrize("field,value", [
    ("registry", "https://region.ocir.io"), ("namespace", "../other"),
    ("repositories", {"shop": "../outside", "crm": "demo-crm", "java-apm": "demo-java-payment", "workflow-gateway": "demo-workflow"}), ("username", "injected\nvalue"),
])
def test_invalid_destination_never_invokes_docker(publisher, field, value):
    config = publisher[1]
    data = json.loads(config.read_text())
    data[field] = value
    config.write_text(json.dumps(data))
    result, calls = run(publisher)
    assert result.returncode != 0
    assert not calls


def test_workflow_requires_manual_main_and_a_protected_environment():
    raw = (ROOT / ".github/workflows/ocir-publish.yml").read_text()
    workflow = yaml.safe_load(raw)
    trigger = workflow.get("on", workflow.get(True))
    assert set(trigger) == {"workflow_dispatch"}
    job = workflow["jobs"]["publish"]
    assert job["environment"] == "demo-registry-publish"
    assert job["runs-on"] == "ubuntu-latest"
    assert "refs/heads/main" in job["if"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["strategy"]["max-parallel"] == 1
    assert set(job["strategy"]["matrix"]["role"]) == {
        "shop", "crm", "java-apm", "workflow-gateway",
    }
    assert "kubectl" not in raw and "workflow_run" not in raw
    assert "setup-qemu" not in raw and "ghcr.io" not in raw
    steps = job["steps"]
    scan = next(i for i, x in enumerate(steps) if "Scan vulnerabilities" == x.get("name"))
    publish = next(i for i, x in enumerate(steps) if "Publish the scanned image" == x.get("name"))
    assert scan < publish
    for name in ("OCIR_PUSH_TOKEN", "OCIR_PUBLISH_CONFIG"):
        assert "secrets." + name not in json.dumps(job.get("env", {}))
        assert all("secrets." + name not in json.dumps(step)
                   for index, step in enumerate(steps) if index != publish)
    for step in steps:
        if "uses" in step:
            assert len(step["uses"].rsplit("@", 1)[-1]) == 40


def test_malformed_config_has_a_generic_failure_before_docker(publisher):
    publisher[1].write_text("[]")
    result, calls = run(publisher)
    assert result.returncode != 0
    assert "Publication failed;" in result.stderr
    assert "Traceback" not in result.stderr
    assert not calls


def test_symlink_token_is_rejected_before_docker(publisher):
    token = publisher[2]
    target = token.with_name("actual-token")
    token.rename(target)
    token.symlink_to(target)
    result, calls = run(publisher)
    assert result.returncode != 0
    assert not calls


def test_workflow_blocks_fixable_high_findings_and_keeps_unfixed_in_the_inventory():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ocir-publish.yml").read_text())
    steps = workflow["jobs"]["publish"]["steps"]
    gate = next(x for x in steps if x.get("name") == "Scan vulnerabilities")["with"]
    assert gate["severity"] == "HIGH,CRITICAL"
    assert gate["exit-code"] == "1"
    assert gate["ignore-unfixed"] == "true"
    inventory = next(x for x in steps if x.get("name") == "Inventory vulnerabilities")["with"]
    assert inventory["exit-code"] == "0"
    assert inventory.get("ignore-unfixed", "false") == "false"
    assert inventory["output"] == "image-vulns-raw.json"


def test_each_publisher_role_has_one_build_in_the_reviewed_manifest():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ocir-publish.yml").read_text())
    roles = workflow["jobs"]["publish"]["strategy"]["matrix"]["role"]
    builds = json.loads((ROOT / "deploy/cp-pipeline-manifest.json").read_text())["containerBuilds"]
    for role in roles:
        matches = [item for item in builds if item["id"] == role]
        assert len(matches) == 1, role
        for key in ("dockerfile", "context"):
            path = (ROOT / matches[0][key]).resolve()
            assert path.is_relative_to(ROOT) and path.exists()


def test_repositories_array_is_rejected_without_a_traceback(publisher):
    config = publisher[1]
    data = json.loads(config.read_text())
    data["repositories"] = ["shop", "crm", "java-apm", "workflow-gateway"]
    config.write_text(json.dumps(data))
    result, calls = run(publisher)
    assert result.returncode != 0
    assert "Publication failed;" in result.stderr
    assert "Traceback" not in result.stderr
    assert not calls


def test_remote_tag_must_resolve_to_the_pushed_digest(publisher):
    result, _ = run(publisher, FAULT="tag-retargeted")
    assert result.returncode != 0
    assert not (publisher[0] / "receipt.json").exists()


def test_manifest_newline_cannot_inject_environment_into_publish_step(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ocir-publish.yml").read_text())
    select = next(x for x in workflow["jobs"]["publish"]["steps"]
                  if x.get("name") == "Select one approved application build")["run"]
    code = select.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    source = tmp_path / "source"
    (source / "deploy").mkdir(parents=True)
    malicious = ".\nOCIR_PUSH_TOKEN=overridden"
    (source / malicious).mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n")
    (source / "deploy/cp-pipeline-manifest.json").write_text(json.dumps({
        "containerBuilds": [{"id": "shop", "context": malicious, "dockerfile": "Dockerfile"}],
    }))
    output = tmp_path / "github-env"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                            env=dict(os.environ, ROLE="shop", SOURCE_SHA=SHA, GITHUB_ENV=str(output)),
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("fault", ["zero-digests", "multiple-digests", "image-id"])
def test_ambiguous_or_changed_pushed_image_has_no_receipt(publisher, fault):
    result, _ = run(publisher, FAULT=fault)
    assert result.returncode != 0
    assert not (publisher[0] / "receipt.json").exists()


def test_invalid_run_tag_never_invokes_docker(publisher):
    result, calls = run(publisher, run_tag="123/1")
    assert result.returncode != 0
    assert not calls

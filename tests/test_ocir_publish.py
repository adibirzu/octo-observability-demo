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
        " print(json.dumps([{'Id':'sha256:local','Os':'linux',"
        "'Architecture':'arm64' if fault=='architecture' else 'amd64',"
        "'Config':{'User':'10001','Labels':{'org.opencontainers.image.revision':"
        "'c'*40 if fault=='source' else 'a'*40}},"
        "'RepoDigests':[remote+'@sha256:'+'b'*64]}]))\n"
        "elif args[:2]==['buildx','imagetools']:\n"
        " print(json.dumps({'digest':'sha256:'+('c' if fault=='digest' else 'b')*64}))\n"
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


def run(publisher, **changes):
    tmp, config, token, env = publisher
    env.update(changes)
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--role", "shop", "--source-sha", SHA,
        "--run-tag", "123-1", "--config-file", str(config),
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


@pytest.mark.parametrize("fault", ["architecture", "source"])
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
    ("repositories", {"shop": "../outside"}), ("username", "injected\nvalue"),
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
    assert all("secrets.OCIR_PUSH_TOKEN" not in json.dumps(x) for x in steps[:publish])
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

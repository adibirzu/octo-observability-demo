"""Unit and contract tests for scripts/local_ci_gate.py and .no-mistakes.yaml."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml


def test_active_workflow_jobs_are_mapped_and_only_audits_have_network():
    gate = load_gate_module()
    steps = {step.name: step for step in gate.build_steps(sys.executable)}
    actual = {
        f"{file.name}:{job}"
        for file in (ROOT / ".github/workflows").glob("*.yml")
        for job in yaml.safe_load(file.read_text())["jobs"]
    }
    assert set(gate.WORKFLOW_CHECKS) == actual
    assert all(set(checks) <= steps.keys() for checks in gate.WORKFLOW_CHECKS.values())
    assert {name for name, step in steps.items() if step.online} == {
        "pip-audit-shop", "pip-audit-crm", "npm-audit-shop", "npm-audit-browser-runner"
    }
    assert steps["playwright-visual-receipt"].skipped
    assert steps["orm-native-image-build"].skipped
    assert steps["ocir-publish"].skipped


def test_tests_workflow_visual_regression_job_contract():
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    assert workflow.get("permissions") == {"contents": "read"}
    visual = workflow["jobs"]["visual"]
    runs_on = str(visual["runs-on"])
    assert runs_on == "macos-15"
    assert visual.get("permissions") == {"contents": "read"}
    assert visual.get("defaults", {}).get("run", {}).get("working-directory") == "shop"

    steps = visual["steps"]
    runs = [step.get("run", "") for step in steps if "run" in step]
    if runs_on.startswith("macos-"):
        assert any("playwright install chromium" in cmd for cmd in runs)
        assert not any("--with-deps" in cmd for cmd in runs)
        platform_suffix = "darwin"
    elif runs_on.startswith("ubuntu-"):
        assert any("playwright install --with-deps chromium" in cmd for cmd in runs)
        platform_suffix = "linux"
    else:
        raise AssertionError(f"Unsupported visual job runner: {runs_on}")

    assert any(
        "playwright test -c playwright.visual.config.ts --update-snapshots=none" in cmd
        for cmd in runs
    )

    uploads = [
        step for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    assert uploads[0].get("if") == "failure()"
    assert uploads[0]["with"]["path"] == "shop/test-results/visual/**/*-diff.png"

    visual_cfg = (ROOT / "shop/playwright.visual.config.ts").read_text()
    assert "testDir: './tests/visual'" in visual_cfg
    assert "workers: 1" in visual_cfg
    assert "retries: 0" in visual_cfg
    assert "checkout-receipt.visual.spec.ts" in visual_cfg

    assert not (ROOT / "shop/tests/e2e/checkout-receipt.visual.spec.ts").exists()
    assert (ROOT / "shop/tests/visual/checkout-receipt.visual.spec.ts").is_file()

    snapshot_dir = (
        ROOT / "shop/tests/visual/checkout-receipt.visual.spec.ts-snapshots"
    )
    assert snapshot_dir.is_dir()
    for viewport in ("wide", "narrow"):
        snap = snapshot_dir / f"checkout-receipt-{viewport}-chromium-{platform_suffix}.png"
        assert snap.is_file() and snap.stat().st_size > 0, f"Missing baseline {snap}"


def test_audit_environment_uses_distinct_private_empty_configs(tmp_path):
    gate = load_gate_module()
    env = gate.build_audit_env(tmp_path)
    paths = {Path(env[key]) for key in (
        "PIP_CONFIG_FILE", "NPM_CONFIG_USERCONFIG", "NPM_CONFIG_GLOBALCONFIG"
    )}
    assert len(paths) == 3
    for path in paths:
        assert path.parent == tmp_path
        assert path.read_bytes() == b""
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "PYTHONPATH" not in env
    assert env["REQUESTS_CA_BUNDLE"] == "/private/etc/ssl/cert.pem"


def test_secret_scan_reports_locations_only_and_fails_closed(monkeypatch):
    gate = load_gate_module()
    response = subprocess.CompletedProcess(
        [], 42, '[{"File":"example.txt","StartLine":2,"Secret":"do-not-print"}]', ""
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: response)
    assert gate.added_line_findings() == {("example.txt", 2)}
    response.stdout = "malformed"
    with pytest.raises(ValueError):
        gate.added_line_findings()


@pytest.mark.usefixtures("seatbelt")
def test_advisory_sandbox_denies_credential_reads(tmp_path, monkeypatch):
    gate = load_gate_module()
    account = tmp_path / "account"
    workspace = account / "workspace"
    paths = [account / ".oci/config", workspace / ".env", workspace / "shop/.env.local",
             workspace / "shop/.npmrc", workspace / ".gate/venv/pip.conf"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    monkeypatch.setattr(gate.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(account)))
    profile = gate.sandbox_profile_for_step(
        gate.GateStep("probe", "lint", [], online=True), allow_online=True, repo_root=workspace
    )
    sandbox = gate.verify_sandbox_available()
    if subprocess.run([sandbox, "-p", profile, "/usr/bin/true"], capture_output=True).returncode == 71:
        pytest.skip("Parent sandbox prevents the HTTPS advisory policy")
    for path in paths:
        result = subprocess.run([sandbox, "-p", profile, "/bin/cat", path], capture_output=True)
        assert result.returncode != 0 and not result.stdout


@pytest.mark.usefixtures("seatbelt")
def test_unix_socket_allowance_is_private_and_keeps_ip_denied(tmp_path):
    gate = load_gate_module()
    with gate.tempfile.TemporaryDirectory(prefix="ci-ipc-", dir="/private/tmp") as directory:
        private = Path(directory)
        profile = gate.sandbox_profile_for_step(
            gate.GateStep("tflint", "lint", []), socket_dir=private
        )
        sandbox = gate.verify_sandbox_available()
        if subprocess.run([sandbox, "-p", profile, "/usr/bin/true"], capture_output=True).returncode == 71:
            pytest.skip("Parent sandbox prevents the private socket policy")
        probe = r"""
import os, socket, sys
private, outside = sys.argv[1:]
assert os.stat(private).st_mode & 0o777 == 0o700
with socket.socket(socket.AF_UNIX) as server, socket.socket(socket.AF_UNIX) as client:
    allowed = private + '/test.sock'
    server.bind(allowed)
    server.listen(1)
    client.connect(allowed)
for family, address in ((socket.AF_UNIX, outside), (socket.AF_INET, ('localhost', 0))):
    with socket.socket(family) as blocked:
        try:
            blocked.bind(address)
        except PermissionError:
            pass
        else:
            raise AssertionError('Socket escaped the permitted scope')
"""
        result = subprocess.run(
            [sandbox, "-p", profile, sys.executable, "-c", probe, private,
             f"/private/tmp/ci-outside-{os.getpid()}.sock"], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".no-mistakes.yaml"
SCRIPT_PATH = ROOT / "scripts/local_ci_gate.py"

FORBIDDEN_SHELL_TOKENS = ("|| true", "|| echo", "set +e", "; true", "&& true")
ALLOWED_TOP_LEVEL_KEYS = {"commands", "auto_fix"}
ALLOWED_COMMAND_KEYS = {"prepare", "test", "lint", "format"}
ALLOWED_AUTO_FIX_KEYS = {"review", "test", "lint", "ci"}
FORBIDDEN_CONFIG_KEYS = {
    "ci",
    "no_ci",
    "allow_repo_commands",
    "skip",
    "local_only",
}


def load_gate_module():
    assert SCRIPT_PATH.is_file(), f"Missing gate script: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location("local_ci_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["local_ci_gate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seatbelt():
    gate = load_gate_module()
    if sys.platform != "darwin":
        pytest.skip("Live Seatbelt tests require macOS")
    probe = subprocess.run(
        [gate.verify_sandbox_available(), "-p", gate.SANDBOX_OFFLINE_PROFILE, "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    if probe.returncode == 71:
        pytest.skip("The parent sandbox prevents Seatbelt subprocesses")
    assert probe.returncode == 0, probe.stderr


def invoke_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def init_temp_git_repo(repo: Path) -> dict[str, str]:
    repo.mkdir(parents=True, exist_ok=True)
    git_env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(
        ["git", "init", "--template="],
        cwd=repo,
        env=git_env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repo,
        env=git_env,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        env=git_env,
        check=True,
    )
    (repo / ".gitignore").write_text(".gate/\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "tracked.txt"],
        cwd=repo,
        env=git_env,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", "init"],
        cwd=repo,
        env=git_env,
        check=True,
        capture_output=True,
    )
    return git_env


def test_no_mistakes_yaml_schema_and_command_wiring():
    assert CONFIG_PATH.is_file(), f"Missing {CONFIG_PATH}"
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(config, dict)

    assert set(config.keys()) <= ALLOWED_TOP_LEVEL_KEYS
    assert set(config.keys()).isdisjoint(FORBIDDEN_CONFIG_KEYS)

    commands = config.get("commands")
    assert isinstance(commands, dict)
    assert set(commands.keys()) == {"test", "lint"}
    assert set(commands.keys()) <= ALLOWED_COMMAND_KEYS
    assert "ci" not in commands

    assert commands["test"] == (
        "python3.11 scripts/local_ci_gate.py --mode all --allow-online --keep-going"
    )
    assert commands["lint"] == (
        "python3.11 scripts/local_ci_gate.py --mode lint --allow-online --keep-going"
    )

    for cmd_str in commands.values():
        assert "--skip-online" not in cmd_str
        for token in FORBIDDEN_SHELL_TOKENS:
            assert token not in cmd_str

    auto_fix = config.get("auto_fix")
    assert auto_fix == {"review": 0, "test": 0, "lint": 0}
    assert set(auto_fix.keys()) <= ALLOWED_AUTO_FIX_KEYS


def test_command_assembly_covers_all_required_gates_without_shell_swallowing():
    custom_py = "/custom/venv/bin/python3.11"
    result = invoke_gate("--list", "--mode", "all", "--python", custom_py)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    steps = payload["steps"]
    assert isinstance(steps, list)
    assert len({step["name"] for step in steps}) == len(steps)

    step_names = [step["name"] for step in steps]
    for required_step in (
        "sbom-generate-check",
        "sbom-public-check",
        "gitleaks",
        "mkdocs-strict",
        "pip-audit-shop",
        "pip-audit-crm",
        "go-vet-workflow-gateway",
        "pytest-contract",
        "pytest-docs-surface",
        "pytest-shop",
        "pytest-crm",
        "pytest-service-async-worker",
        "pytest-service-cache",
        "pytest-service-edge-fuzz",
        "pytest-service-genai-studio",
        "pytest-service-load-control",
        "pytest-service-object-pipeline",
        "pytest-service-remediator",
        "pytest-tool-traffic-generator",
        "pytest-deploy-wizard",
        "go-test-workflow-gateway",
    ):
        assert required_step in step_names, f"Missing required step {required_step}"

    by_name = {step["name"]: step for step in steps}

    assert by_name["sbom-generate-check"]["command"] == [
        custom_py,
        "tools/generate_sbom.py",
        "--check",
    ]
    assert by_name["sbom-public-check"]["command"] == [
        custom_py,
        "tools/public_sbom.py",
        "--check",
        "sbom/octo-observability-demo.cdx.json",
    ]
    assert by_name["gitleaks"]["commands"] == [
        [custom_py, str(SCRIPT_PATH), "--scan-added-lines"],
    ]
    assert by_name["mkdocs-strict"]["command"][:5] == [
        custom_py,
        "-m",
        "mkdocs",
        "build",
        "--strict",
    ]
    assert by_name["mkdocs-strict"]["online"] is False
    assert by_name["pip-audit-shop"]["online"] is True
    assert by_name["pip-audit-crm"]["online"] is True
    assert "requirements.txt" in by_name["pip-audit-shop"]["command"]
    assert "--strict" in by_name["pip-audit-shop"]["command"]
    assert "requirements.txt" in by_name["pip-audit-crm"]["command"]
    assert "--strict" in by_name["pip-audit-crm"]["command"]

    assert by_name["go-vet-workflow-gateway"]["command"] == ["go", "vet", "./..."]
    assert by_name["go-vet-workflow-gateway"]["cwd"].endswith(
        "shop/services/workflow-gateway"
    )
    assert by_name["go-test-workflow-gateway"]["command"] == [
        "go",
        "test",
        "-race",
        "./...",
    ]
    assert by_name["go-test-workflow-gateway"]["cwd"].endswith(
        "shop/services/workflow-gateway"
    )

    for step in steps:
        if step["skipped"]:
            assert step["skip_reason"]
            continue
        cmds = step["commands"]
        for cmd in cmds:
            assert isinstance(cmd, list) and all(isinstance(part, str) for part in cmd)
            joined = " ".join(cmd)
            for token in FORBIDDEN_SHELL_TOKENS:
                assert token not in joined, f"Forbidden token {token!r} in {step['name']}"
            assert cmd[0] not in {"sh", "bash", "zsh"}, (
                f"Step {step['name']} must execute argv directly without a shell wrapper"
            )


def test_cross_mode_step_selection_and_empty_selection_rejected():
    module = load_gate_module()

    mismatched = invoke_gate("--mode", "test", "--step", "gitleaks")
    assert mismatched.returncode == 2
    assert "gitleaks" in mismatched.stderr

    mixed = invoke_gate(
        "--mode", "test", "--step", "pytest-contract", "--step", "gitleaks"
    )
    assert mixed.returncode == 2
    assert "gitleaks" in mixed.stderr

    with pytest.raises(ValueError, match="Empty step selection"):
        module.select_steps([], mode="test")


@pytest.mark.usefixtures("seatbelt")
def test_offline_and_skip_online_advisory_steps_fail_closed_as_unavailable(tmp_path):
    receipt_default = tmp_path / "receipt-default.json"
    res_default = invoke_gate(
        "--mode",
        "lint",
        "--step",
        "pip-audit-shop",
        "--receipt",
        str(receipt_default),
    )
    assert res_default.returncode == 1
    data_default = json.loads(receipt_default.read_text(encoding="utf-8"))
    assert data_default["status"] == "failed"
    assert data_default["steps"][0]["name"] == "pip-audit-shop"
    assert data_default["steps"][0]["status"] == "unavailable"
    assert data_default["steps"][0]["exit_code"] == 1
    assert "online" in data_default["steps"][0]["reason"].lower()

    receipt_skip = tmp_path / "receipt-skip.json"
    res_skip = invoke_gate(
        "--mode",
        "lint",
        "--step",
        "pip-audit-shop",
        "--skip-online",
        "--receipt",
        str(receipt_skip),
    )
    assert res_skip.returncode == 1
    data_skip = json.loads(receipt_skip.read_text(encoding="utf-8"))
    assert data_skip["status"] == "failed"
    assert data_skip["steps"][0]["status"] == "unavailable"
    assert data_skip["steps"][0]["exit_code"] == 1
    assert "--skip-online" in data_skip["steps"][0]["reason"]


@pytest.mark.usefixtures("seatbelt")
def test_online_profile_allows_only_selected_home_interpreter(tmp_path, monkeypatch):
    gate = load_gate_module()
    account = tmp_path / "account"
    interpreter = account / "venv/bin/python3.11"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(Path(sys.executable).resolve())
    private_file = interpreter.with_name("private.txt")
    private_file.write_text("synthetic")
    monkeypatch.setattr(gate.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(account)))
    probe = (
        "import pathlib, sys\n"
        "try:\n"
        "    pathlib.Path(sys.argv[1]).read_text()\n"
        "except PermissionError:\n"
        "    sys.exit(0)\n"
        "sys.exit(9)\n"
    )
    step = gate.GateStep(
        "python-probe", "lint", [str(interpreter), "-I", "-c", probe, str(private_file)],
        online=True,
    )
    profile = gate.sandbox_profile_for_step(step, allow_online=True)
    sandbox = gate.verify_sandbox_available()
    nesting = subprocess.run([sandbox, "-p", profile, "/usr/bin/true"], capture_output=True)
    if nesting.returncode == 71:
        pytest.skip("Parent sandbox prevents the HTTPS advisory policy")
    assert nesting.returncode == 0, nesting.stderr
    result = subprocess.run([sandbox, "-p", profile, *step.command], capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.usefixtures("seatbelt")
def test_seatbelt_network_denial_isolated_home_and_allow_online_scoping(tmp_path):
    module = load_gate_module()
    host_home = os.environ.get("HOME", "")
    probe_out = tmp_path / "probe.json"

    offline_probe = module.GateStep(
        name="offline-probe",
        mode="test",
        command=[
            sys.executable,
            "-c",
            (
                "import json, os, socket\n"
                "net_blocked = False\n"
                "try:\n"
                "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "    s.bind(('127.0.0.1', 0))\n"
                "except OSError:\n"
                "    net_blocked = True\n"
                f"open({str(probe_out)!r}, 'w').write(json.dumps({{\n"
                "    'home': os.environ.get('HOME'),\n"
                "    'oci_config': os.environ.get('OCI_CONFIG_FILE'),\n"
                "    'oci_auth': os.environ.get('OCI_AUTH_MODE'),\n"
                "    'goproxy': os.environ.get('GOPROXY'),\n"
                "    'gosumdb': os.environ.get('GOSUMDB'),\n"
                "    'net_blocked': net_blocked,\n"
                "}))\n"
                "raise SystemExit(0 if net_blocked else 9)\n"
            ),
        ],
        cwd=ROOT,
        online=False,
    )
    online_bind_probe = module.GateStep(
        name="online-bind-probe",
        mode="lint",
        command=[
            sys.executable,
            "-c",
            (
                "import socket\n"
                "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "try:\n"
                "    s.bind(('127.0.0.1', 0))\n"
                "except OSError:\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(8)\n"
            ),
        ],
        cwd=ROOT,
        online=True,
    )

    assert "deny network*" in module.sandbox_profile_for_step(
        offline_probe, allow_online=True
    )
    online_profile = module.sandbox_profile_for_step(
        online_bind_probe, allow_online=True
    )
    assert "deny network*" in online_profile
    assert 'remote tcp "*:443"' in online_profile

    exit_code, results = module.execute_steps(
        [offline_probe],
        output_dir=tmp_path / "logs",
        allow_online=True,
    )
    assert exit_code == 0, results
    observed = json.loads(probe_out.read_text(encoding="utf-8"))
    assert observed["net_blocked"] is True
    assert observed["home"] and observed["home"] != host_home
    assert not Path(observed["home"]).exists(), "Temporary HOME must be cleaned up"
    assert observed["oci_config"] == "/dev/null"
    assert observed["oci_auth"] == "config"
    assert observed["goproxy"] == "off"
    assert observed["gosumdb"] == "off"

    # If this pytest process is not already inside an outer '(deny network*)' sandbox,
    # execute the outbound-permitted profile directly; if already inside '(deny network*)'
    # (e.g. during pytest-contract), Seatbelt rejects relaxing '(deny network*)' with rc=71.
    nest_check = subprocess.run(
        [
            "sandbox-exec",
            "-p",
            online_profile,
            "/usr/bin/true",
        ],
        capture_output=True,
        check=False,
    )
    exit_online, results_online = module.execute_steps(
        [online_bind_probe],
        output_dir=tmp_path / "logs-online",
        allow_online=True,
    )
    if nest_check.returncode == 0:
        assert exit_online == 0, results_online
        assert results_online[0]["sandbox_policy"] == (
            "credential-isolated advisory HTTPS"
        )
    else:
        assert nest_check.returncode == 71
        assert results_online[0]["exit_code"] == 71


def test_fail_closed_when_sandbox_exec_or_darwin_unavailable(tmp_path, monkeypatch):
    module = load_gate_module()
    marker = tmp_path / "unisolated_ran"
    step = module.GateStep(
        name="should-not-run-unisolated",
        mode="test",
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        cwd=ROOT,
    )

    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    exit_code, results = module.execute_steps([step], output_dir=tmp_path / "logs-linux")
    assert exit_code == 1
    assert results[0]["status"] == "unavailable"
    assert not marker.exists()

    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.shutil, "which", lambda binary: None)
    exit_code2, results2 = module.execute_steps([step], output_dir=tmp_path / "logs-nosb")
    assert exit_code2 == 1
    assert results2[0]["status"] == "unavailable"
    assert not marker.exists()


def test_minimal_env_allowlist_strips_project_and_cloud_secrets(tmp_path, monkeypatch):
    module = load_gate_module()
    secret_vars = {
        "OCIR_PUSH_TOKEN": "synthetic-ocir-token",
        "ORACLE_PASSWORD": "synthetic-oracle-password",
        "TF_VAR_password": "synthetic-tf-password",
        "GH_TOKEN": "synthetic-gh-token",
        "GITHUB_TOKEN": "synthetic-github-token",
        "ARM_CLIENT_SECRET": "synthetic-arm-secret",
        "PGPASSWORD": "synthetic-pg-password",
        "DB_PASSWORD": "synthetic-db-password",
        "PIP_INDEX_URL": "https://secret:token@example.invalid/simple",
        "OCI_CLI_PROFILE": "synthetic-profile",
        "OCI_TOKEN": "synthetic-oci-token",
        "AWS_SECRET_ACCESS_KEY": "synthetic-aws-secret",
        "AZURE_CLIENT_SECRET": "synthetic-azure-secret",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/synthetic-gcp.json",
        "ARBITRARY_AMBIENT_SECRET": "synthetic-ambient",
    }
    for key, val in secret_vars.items():
        monkeypatch.setenv(key, val)

    fake_home = tmp_path / "isolated-home"
    fake_home.mkdir()
    env = module.build_isolated_env(
        ROOT, {"PYTHONPATH": str(ROOT / "shop")}, home_dir=fake_home
    )
    for forbidden_key in secret_vars:
        assert forbidden_key not in env, f"Secret env var {forbidden_key} leaked!"

    assert env["HOME"] == str(fake_home)
    assert env["OCI_AUTH_MODE"] == "config"
    assert env["OCI_CONFIG_FILE"] == "/dev/null"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["GOPROXY"] == "off"
    assert env["GOSUMDB"] == "off"
    assert env["GOPATH"] == str(ROOT / ".gate/gopath")
    assert env["GOMODCACHE"] == str(ROOT / ".gate/gomodcache")
    assert env["GOCACHE"] == str(ROOT / ".gate/gocache")
    assert env["PIP_CACHE_DIR"] == str(ROOT / ".gate/pip-cache")
    assert str(ROOT / "shop") in env["PYTHONPATH"].split(os.pathsep)


@pytest.mark.usefixtures("seatbelt")
def test_git_status_failure_before_and_after_step_fails_cleanliness_guard(
    tmp_path, monkeypatch
):
    module = load_gate_module()
    non_git_dir = tmp_path / "not-a-git-repo"
    non_git_dir.mkdir()

    step = module.GateStep(
        name="noop-step",
        mode="lint",
        command=[sys.executable, "-c", "raise SystemExit(0)"],
        cwd=non_git_dir,
    )

    # Failure BEFORE step runs (non-git repo returns git status rc=128)
    exit_code_before, results_before = module.execute_steps(
        [step],
        output_dir=tmp_path / "logs-before",
        repo_root=non_git_dir,
        enforce_clean_git=True,
    )
    assert exit_code_before == 1
    assert results_before[0]["status"] in {"failed", "unavailable"}
    assert results_before[0]["exit_code"] != 0

    # Failure AFTER step runs
    calls = {"count": 0}

    def fake_git_status(repo_root: Path = ROOT) -> list[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return []
        raise RuntimeError("git status exited 128: fatal: index file corrupt")

    monkeypatch.setattr(module, "git_status_lines", fake_git_status)
    exit_code_after, results_after = module.execute_steps(
        [step],
        output_dir=tmp_path / "logs-after",
        repo_root=non_git_dir,
        enforce_clean_git=True,
    )
    assert exit_code_after == 1
    assert results_after[0]["status"] == "failed"
    assert results_after[0]["exit_code"] != 0
    assert "128" in results_after[0].get("error", "")


@pytest.mark.usefixtures("seatbelt")
def test_clean_git_working_tree_guard_and_mkdocs_temp_cleanup(tmp_path):
    module = load_gate_module()
    repo = tmp_path / "repo"
    init_temp_git_repo(repo)

    gate_dir = repo / ".gate"
    gate_dir.mkdir()
    (gate_dir / "receipt.json").write_text("{}\n", encoding="utf-8")
    assert module.git_status_lines(repo) == []

    # Verify mkdocs cleanup_paths removes temporary site dir even on step failure.
    mkdocs_tmp_site = tmp_path / "mkdocs-temp-site"
    mkdocs_step = module.GateStep(
        name="mkdocs-strict",
        mode="lint",
        command=[
            sys.executable,
            "-c",
            (
                f"from pathlib import Path; p = Path({str(mkdocs_tmp_site)!r}); "
                "p.mkdir(parents=True, exist_ok=True); "
                "(p / 'index.html').write_text('built'); "
                "raise SystemExit(1)"
            ),
        ],
        cwd=repo,
        cleanup_paths=(mkdocs_tmp_site,),
    )
    rc_mk, _ = module.execute_steps(
        [mkdocs_step],
        output_dir=gate_dir / "logs-mk",
        repo_root=repo,
        enforce_clean_git=True,
    )
    assert rc_mk == 1
    assert not mkdocs_tmp_site.exists(), "cleanup_paths must remove temp site dir"
    assert module.git_status_lines(repo) == []

    # Leaving untracked build dirt outside .gate/ must be caught by the worktree guard.
    dirty_step = module.GateStep(
        name="dirty-step",
        mode="lint",
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(repo / 'untracked.out')!r}).write_text('dirt')",
        ],
        cwd=repo,
    )
    exit_code, results = module.execute_steps(
        [dirty_step],
        output_dir=gate_dir / "logs",
        repo_root=repo,
        enforce_clean_git=True,
    )
    assert exit_code != 0
    assert results[0]["status"] == "failed"
    assert "dirty" in results[0].get("error", "").lower()


def test_gate_venv_precedence_and_atomic_private_receipt_permissions(
    tmp_path, monkeypatch
):
    module = load_gate_module()
    fake_repo = tmp_path / "repo"
    fake_venv_py = fake_repo / ".gate/venv/bin/python"
    fake_venv_py.parent.mkdir(parents=True)
    fake_venv_py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_venv_py.chmod(0o755)

    monkeypatch.setattr(module.sys, "executable", "/ambient/venv/bin/python3")
    assert module.default_python(fake_repo) == str(fake_venv_py)

    fake_venv_py.unlink()
    assert module.default_python(fake_repo) == "/ambient/venv/bin/python3"

    receipt_path = tmp_path / "private-receipt.json"
    module.write_private_text(receipt_path, '{"ok": true}\n')
    assert receipt_path.is_file()
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600


@pytest.mark.usefixtures("seatbelt")
def test_gitleaks_step_detects_staged_synthetic_secret_in_temp_repo(tmp_path):
    module = load_gate_module()
    repo = tmp_path / "secret-repo"
    git_env = init_temp_git_repo(repo)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
        cwd=repo, env=git_env, check=True,
    )

    # Dynamically construct a synthetic GitHub PAT token so no literal appears in source.
    synthetic_token = "ghp_" + ("A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8")
    (repo / "tracked.txt").write_text(
        f"token = {synthetic_token}\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, env=git_env, check=True)

    steps = module.build_steps(sys.executable, repo_root=repo)
    gitleaks_step = next(s for s in steps if s.name == "gitleaks")
    gitleaks_step = replace(gitleaks_step, command=[sys.executable, str(SCRIPT_PATH), "--scan-added-lines"])
    exit_code, results = module.execute_steps(
        [gitleaks_step],
        output_dir=repo / ".gate/logs",
        repo_root=repo,
        enforce_clean_git=False,
    )
    assert exit_code == 1
    assert results[0]["status"] == "failed"
    assert results[0]["exit_code"] != 0
    log = (repo / ".gate/logs" / results[0]["log"]).read_text()
    assert log == "tracked.txt:1\nAdded-line findings: 1\n"
    assert synthetic_token not in log


@pytest.mark.usefixtures("seatbelt")
def test_nonzero_exit_propagation_fail_fast_and_keep_going(tmp_path):
    module = load_gate_module()
    marker = tmp_path / "should_not_run"
    steps = [
        module.GateStep(
            name="pass-first",
            mode="test",
            command=[sys.executable, "-c", "raise SystemExit(0)"],
            cwd=ROOT,
        ),
        module.GateStep(
            name="fail-second",
            mode="test",
            command=[sys.executable, "-c", "raise SystemExit(7)"],
            cwd=ROOT,
        ),
        module.GateStep(
            name="after-fail",
            mode="test",
            command=[
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).touch()",
            ],
            cwd=ROOT,
        ),
    ]
    exit_code, results = module.execute_steps(
        steps, output_dir=tmp_path / "logs", fail_fast=True
    )
    assert exit_code == 1
    assert [r["name"] for r in results] == ["pass-first", "fail-second"]
    assert results[0]["exit_code"] == 0
    assert results[1]["exit_code"] == 7
    assert not marker.exists()

    exit_code_kg, results_kg = module.execute_steps(
        steps, output_dir=tmp_path / "logs-kg", fail_fast=False
    )
    assert exit_code_kg == 1
    assert [r["exit_code"] for r in results_kg] == [0, 7, 0]
    assert marker.exists()


def test_private_output_helpers_reject_symlinks_without_truncating_target(tmp_path, monkeypatch):
    module = load_gate_module()
    monkeypatch.setattr(module, "verify_sandbox_available", lambda: "/usr/bin/false")
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("ORIGINAL_SENTINEL\n", encoding="utf-8")
    sentinel.chmod(0o644)

    log_dir = tmp_path / "logs"
    log_dir.mkdir(mode=0o700)
    log_symlink = log_dir / "00-pass-step.log"
    log_symlink.symlink_to(sentinel)

    with pytest.raises(OSError):
        module.open_private_write(log_symlink)
    assert sentinel.read_text(encoding="utf-8") == "ORIGINAL_SENTINEL\n"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o644

    receipt_symlink = tmp_path / "receipt-link.json"
    receipt_symlink.symlink_to(sentinel)
    with pytest.raises(OSError):
        module.write_private_text(receipt_symlink, '{"overwritten": true}\n')
    assert sentinel.read_text(encoding="utf-8") == "ORIGINAL_SENTINEL\n"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o644

    real_dir = tmp_path / "real-parent"
    real_dir.mkdir()
    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(real_dir)
    with pytest.raises(OSError):
        module.open_private_write(symlink_parent / "child.log")
    with pytest.raises(OSError):
        module.write_private_text(symlink_parent / "child.json", "{}\n")

    step = module.GateStep(
        name="pass-step",
        mode="lint",
        command=[sys.executable, "-c", "print('hello')"],
        cwd=ROOT,
    )
    rc_exec, results_exec = module.execute_steps([step], output_dir=log_dir)
    assert rc_exec == 1
    assert results_exec[0]["status"] == "failed"
    assert sentinel.read_text(encoding="utf-8") == "ORIGINAL_SENTINEL\n"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o644

    rc_main = module.main(
        [
            "--mode",
            "lint",
            "--step",
            "sbom-generate-check",
            "--receipt",
            str(receipt_symlink),
        ]
    )
    assert rc_main == 1
    assert sentinel.read_text(encoding="utf-8") == "ORIGINAL_SENTINEL\n"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o644


def test_private_output_helpers_fail_closed_on_fchmod_error_and_close_fd(
    tmp_path, monkeypatch
):
    module = load_gate_module()
    closed_fds: list[int] = []
    real_close = os.close

    def tracking_close(fd: int) -> None:
        closed_fds.append(fd)
        real_close(fd)

    def failing_fchmod(fd: int, mode: int) -> None:
        raise PermissionError("simulated fchmod failure")

    monkeypatch.setattr(module.os, "close", tracking_close)
    monkeypatch.setattr(module.os, "fchmod", failing_fchmod)

    log_target = tmp_path / "step.log"
    with pytest.raises(PermissionError, match="simulated fchmod failure"):
        module.open_private_write(log_target)
    assert closed_fds, "open_private_write must close fd when fchmod fails"
    assert not log_target.exists()

    closed_fds.clear()
    existing_receipt = tmp_path / "receipt.json"
    existing_receipt.write_text('{"preserved": true}\n', encoding="utf-8")
    existing_receipt.chmod(0o600)

    with pytest.raises(PermissionError, match="simulated fchmod failure"):
        module.write_private_text(existing_receipt, '{"corrupted": true}\n')
    assert closed_fds, "write_private_text must close temp fd when fchmod fails"
    assert existing_receipt.read_text(encoding="utf-8") == '{"preserved": true}\n'
    assert list(tmp_path.glob("*.tmp*")) == []


def test_private_output_helpers_reject_intermediate_symlink_with_existing_subdir(
    tmp_path, monkeypatch,
):
    module = load_gate_module()
    monkeypatch.setattr(module, "verify_sandbox_available", lambda: "/usr/bin/false")
    external_dir = tmp_path / "external-target"
    existing_subdir = external_dir / "lint"
    existing_subdir.mkdir(parents=True)

    sentinel_log = existing_subdir / "00-pass-step.log"
    sentinel_log.write_text("EXTERNAL_LOG_SENTINEL\n", encoding="utf-8")
    sentinel_log.chmod(0o644)

    sentinel_receipt = existing_subdir / "receipt.json"
    sentinel_receipt.write_text("EXTERNAL_RECEIPT_SENTINEL\n", encoding="utf-8")
    sentinel_receipt.chmod(0o644)

    fake_repo = tmp_path / "repo"
    (fake_repo / ".gate").mkdir(parents=True)
    # Intermediate symlink: .gate/logs -> external_dir, where external_dir/lint already exists!
    (fake_repo / ".gate/logs").symlink_to(external_dir)

    nested_log = fake_repo / ".gate/logs/lint/00-pass-step.log"
    nested_receipt = fake_repo / ".gate/logs/lint/receipt.json"

    with pytest.raises(OSError):
        module.open_private_write(nested_log)
    assert sentinel_log.read_text(encoding="utf-8") == "EXTERNAL_LOG_SENTINEL\n"
    assert stat.S_IMODE(sentinel_log.stat().st_mode) == 0o644

    with pytest.raises(OSError):
        module.write_private_text(nested_receipt, '{"overwritten": true}\n')
    assert (
        sentinel_receipt.read_text(encoding="utf-8") == "EXTERNAL_RECEIPT_SENTINEL\n"
    )
    assert stat.S_IMODE(sentinel_receipt.stat().st_mode) == 0o644

    step = module.GateStep(
        name="pass-step",
        mode="lint",
        command=[sys.executable, "-c", "print('hello')"],
        cwd=ROOT,
    )
    rc_exec, results_exec = module.execute_steps(
        [step],
        output_dir=fake_repo / ".gate/logs/lint",
        repo_root=fake_repo,
    )
    assert rc_exec == 1
    assert results_exec[0]["status"] == "failed"
    assert sentinel_log.read_text(encoding="utf-8") == "EXTERNAL_LOG_SENTINEL\n"
    assert stat.S_IMODE(sentinel_log.stat().st_mode) == 0o644

    rc_main = module.main(
        [
            "--mode",
            "lint",
            "--step",
            "sbom-generate-check",
            "--receipt",
            str(nested_receipt),
        ]
    )
    assert rc_main == 1
    assert (
        sentinel_receipt.read_text(encoding="utf-8") == "EXTERNAL_RECEIPT_SENTINEL\n"
    )
    assert stat.S_IMODE(sentinel_receipt.stat().st_mode) == 0o644


def test_private_output_helpers_support_macos_var_alias_and_reject_dotdot(tmp_path):
    module = load_gate_module()
    raw_tmp = str(tmp_path)
    if raw_tmp.startswith("/private/var/"):
        var_alias_root = Path("/var/" + raw_tmp[len("/private/var/") :])
    else:
        var_alias_root = tmp_path

    alias_receipt = var_alias_root / "nested/dir/receipt.json"
    module.write_private_text(alias_receipt, '{"alias_ok": true}\n')
    assert alias_receipt.read_text(encoding="utf-8") == '{"alias_ok": true}\n'
    assert stat.S_IMODE(alias_receipt.stat().st_mode) == 0o600

    traversal_path = Path(f"{tmp_path}/nested/../traversal.json")
    with pytest.raises(OSError):
        module.write_private_text(traversal_path, '{"bad": true}\n')

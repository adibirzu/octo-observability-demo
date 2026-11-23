"""Exercise local gate exit status without application or provider dependencies."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("shop", "crm", "services/load-control", "tools/traffic-generator")


def stub_python(tmp_path, failing_suite, status):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "python3"
    script.write_text(
        "#!/bin/sh\n"
        'echo "$PWD" >> "$CALLS"\n'
        'echo "1 passed, 1 error"\n'
        'case "$PWD" in *"$FAIL_SUITE") exit "$FAIL_STATUS";; esac\n'
        "exit 0\n"
    )
    script.chmod(0o700)
    (bindir / "python").symlink_to(script)
    return {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "CALLS": str(tmp_path / "calls"),
        "FAIL_SUITE": failing_suite,
        "FAIL_STATUS": str(status),
    }


@pytest.mark.parametrize("suite", SUITES)
@pytest.mark.parametrize("status", [0, 1, 2, 5])
def test_make_test_apps_propagates_suite_exit(tmp_path, suite, status):
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text())
    for directory in SUITES:
        tests = tmp_path / directory / "tests"
        tests.mkdir(parents=True)
        (tests / "test_example.py").touch()
    result = subprocess.run(
        ["make", "test-apps"], cwd=tmp_path,
        env=stub_python(tmp_path, suite, status), capture_output=True, text=True,
    )
    assert (result.returncode == 0) == (status == 0), result.stdout + result.stderr
    assert str(tmp_path / suite) in (tmp_path / "calls").read_text().splitlines()


@pytest.mark.parametrize("root_name", ["plain", "root[brackets]"])
@pytest.mark.parametrize("suite", SUITES)
@pytest.mark.parametrize("status", [0, 1, 2, 5])
def test_verify_counts_suite_failures(tmp_path, status, suite, root_name):
    test_root = tmp_path / root_name
    test_root.mkdir()
    # Run the actual test-suite section in isolation from infrastructure validators.
    source = (ROOT / "deploy/verify.sh").read_text()
    section = source.split('section "Python test suites"', 1)[1].split(
        '# ── Template import smoke', 1
    )[0]
    for directory in SUITES:
        tests = test_root / directory / "tests"
        tests.mkdir(parents=True)
        (tests / "test_example.py").touch()
    env = stub_python(test_root, suite, status)
    env["REPO_ROOT"] = str(test_root)
    result = subprocess.run(
        ["bash", "-c", 'set -uo pipefail; errors=0; ok() { :; }; '
         'warn() { :; }; fail() { errors=$((errors + 1)); }; '
         + section + '\nexit "$errors"'],
        env=env, capture_output=True, text=True,
    )
    assert (result.returncode == 0) == (status == 0), result.stdout + result.stderr

    assert str(test_root / suite) in (test_root / "calls").read_text().splitlines()

def test_make_empty_python_suite_is_fatal(tmp_path):
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text())
    (tmp_path / "shop/tests").mkdir(parents=True)
    result = subprocess.run(
        ["make", "test-apps"], cwd=tmp_path,
        env=stub_python(tmp_path, "shop", 5), capture_output=True, text=True,
    )
    assert result.returncode != 0, result.stdout + result.stderr


def test_verify_empty_python_suite_is_fatal(tmp_path):
    source = (ROOT / "deploy/verify.sh").read_text()
    section = source.split('section "Python test suites"', 1)[1].split(
        '# ── Template import smoke', 1
    )[0]
    (tmp_path / "shop/tests").mkdir(parents=True)
    env = stub_python(tmp_path, "shop", 5)
    env["REPO_ROOT"] = str(tmp_path)
    result = subprocess.run(
        ["bash", "-c", 'set -uo pipefail; errors=0; ok() { :; }; '
         'warn() { :; }; fail() { errors=$((errors + 1)); }; '
         + section + '\nexit "$errors"'],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0, result.stdout + result.stderr

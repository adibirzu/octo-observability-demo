"""Behavioral tests for the OKE RBAC + APM payment-attribute ops artifacts.

Complements the content-grep assertions in test_oke_rbac_and_apm_ops.py by
actually EXECUTING the scripts (dry-run / --help / unknown-arg) and PARSING the
RBAC manifest — catching control-flow and contract bugs that string greps miss
(found in adversarial review): missing --help/Usage, wrong APM attribute JSON
key casing, an unsafe NUMERIC-by-default on the shared prod APM domain, and an
auth-check set that doesn't cover the verbs the operation exercises.

Stdlib-only with graceful skips when bash/envsubst are unavailable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTIVATE = ROOT / "deploy/oci/apm/activate_payment_attributes.sh"
POST_RBAC = ROOT / "deploy/oke/apply-post-rbac-fixes.sh"
ROLEBINDING = ROOT / "deploy/k8s/oke/rbac/octo-drone-shop-deployer-rolebinding.yaml"

bash = shutil.which("bash")
requires_bash = pytest.mark.skipif(bash is None, reason="bash not available")

STRING_ATTRS = (
    "payment.antifraud_reasons",
    "payment.verification.decision",
    "payment.error_code",
    "payment.decision_source",
)


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [bash, *args], capture_output=True, text=True, env=full_env, timeout=30, cwd=str(ROOT)
    )


def _dry_run_json(env: dict[str, str] | None = None) -> list[dict]:
    res = _run([str(ACTIVATE), "--dry-run"], env=env)
    assert res.returncode == 0, res.stderr
    block = res.stdout[res.stdout.index("[") : res.stdout.rindex("]") + 1]
    return json.loads(block)


# ── deploy-script --help / Usage contract (matches test_unified_deploy_surface) ──
@requires_bash
@pytest.mark.parametrize("script", [ACTIVATE, POST_RBAC], ids=["activate", "post-rbac"])
def test_help_is_preflight_safe_and_prints_usage(script: Path) -> None:
    res = _run([str(script), "--help"])
    assert res.returncode == 0, f"{script.name} --help exit {res.returncode}: {res.stderr}"
    assert "Usage:" in res.stdout, f"{script.name} --help must print a Usage: line"
    assert "Missing RBAC permission" not in res.stdout, "--help must not run the preflight"


# ── activate_payment_attributes.sh behavior ──
@requires_bash
def test_activate_no_arg_is_dry_run() -> None:
    res = _run([str(ACTIVATE)])
    assert res.returncode == 0
    assert "DRY RUN" in res.stdout


@requires_bash
def test_activate_unknown_arg_exits_2() -> None:
    res = _run([str(ACTIVATE), "--bogus"])
    assert res.returncode == 2


@requires_bash
def test_activate_dry_run_emits_valid_json_with_string_attrs() -> None:
    attrs = _dry_run_json()
    names = {a["attributeName"] for a in attrs}
    for a in STRING_ATTRS:
        assert a in names


@requires_bash
def test_activate_attribute_json_uses_sdk_key_casing() -> None:
    # The OCI CLI model field is attributeNameSpace (capital S) — lowercase
    # 'attributeNamespace' is silently wrong and would break --apply.
    for obj in _dry_run_json():
        assert "attributeNameSpace" in obj, f"wrong key casing in {obj}"
        assert "attributeNamespace" not in obj


@requires_bash
def test_activate_default_is_string_only_safe_on_shared_domain() -> None:
    # Default must NOT activate the NUMERIC payment.risk_score on the shared prod
    # domain (numeric slots are exhausted; bulk activation is atomic).
    names = {a["attributeName"] for a in _dry_run_json()}
    assert "payment.risk_score" not in names


@requires_bash
def test_activate_numeric_is_opt_in() -> None:
    attrs = _dry_run_json(env={"APM_PAYMENT_INCLUDE_NUMERIC": "true"})
    risk = [a for a in attrs if a["attributeName"] == "payment.risk_score"]
    assert risk and risk[0]["attributeType"] == "NUMERIC"


# ── apply-post-rbac-fixes.sh: auth checks must cover the verbs it exercises ──
@requires_bash
def test_post_rbac_auth_checks_cover_cronjob_apply_update_path() -> None:
    # kubectl apply of an existing CronJob patches it, so the pre-flight must
    # verify patch/get on cronjobs, not only create.
    script = POST_RBAC.read_text(encoding="utf-8")
    for check in ("create cronjobs.batch", "patch cronjobs.batch", "get cronjobs.batch"):
        assert check in script, f"missing auth pre-check: {check!r}"


@requires_bash
def test_post_rbac_guards_required_envsubst_vars() -> None:
    # OCIR_REPO / OCI_REGION are referenced by the CronJob manifest; the script
    # must fail fast if they are unset rather than render image: /…:latest.
    script = POST_RBAC.read_text(encoding="utf-8")
    assert re.search(r"OCIR_REPO:\?", script), "OCIR_REPO must be a required (:?) var"
    assert re.search(r"OCI_REGION:\?", script), "OCI_REGION must be a required (:?) var"


# ── RBAC manifest: parse + least-privilege structure ──
def _render_rolebinding() -> list[dict]:
    yaml = pytest.importorskip("yaml")
    text = ROLEBINDING.read_text(encoding="utf-8")
    rendered = (
        text.replace("${K8S_NAMESPACE_SHOP}", "octo-drone-shop")
        .replace("${OKE_RBAC_SUBJECT_KIND}", "User")
        .replace("${OKE_RBAC_SUBJECT_NAME}", "ocid1.user.oc1..aaaa")
    )
    return [d for d in yaml.safe_load_all(rendered) if d]


def test_rolebinding_is_namespaced_role_plus_binding() -> None:
    docs = _render_rolebinding()
    kinds = [d["kind"] for d in docs]
    assert kinds == ["Role", "RoleBinding"]
    assert "ClusterRole" not in kinds and "ClusterRoleBinding" not in kinds


def test_rolebinding_grants_no_secrets_and_no_wildcards() -> None:
    role = next(d for d in _render_rolebinding() if d["kind"] == "Role")
    for rule in role["rules"]:
        assert "secrets" not in rule.get("resources", []), "least-privilege: no secrets access"
        assert "*" not in rule.get("resources", []), "no wildcard resources"
        assert "*" not in rule.get("verbs", []), "no wildcard verbs"


def test_rolebinding_roleref_points_at_in_file_role() -> None:
    docs = _render_rolebinding()
    role = next(d for d in docs if d["kind"] == "Role")
    binding = next(d for d in docs if d["kind"] == "RoleBinding")
    assert binding["roleRef"]["kind"] == "Role"
    assert binding["roleRef"]["name"] == role["metadata"]["name"]

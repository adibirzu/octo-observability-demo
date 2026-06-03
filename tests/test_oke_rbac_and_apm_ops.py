from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_oke_shop_deployer_rbac_is_namespace_scoped_and_least_privilege() -> None:
    manifest = _read("deploy/k8s/oke/rbac/octo-drone-shop-deployer-rolebinding.yaml")

    assert "kind: Role\n" in manifest
    assert "kind: RoleBinding\n" in manifest
    assert "kind: ClusterRoleBinding" not in manifest
    assert "namespace: ${K8S_NAMESPACE_SHOP}" in manifest
    assert "name: ${OKE_RBAC_SUBJECT_NAME}" in manifest
    assert 'resources: ["deployments", "replicasets"]' in manifest
    assert 'resources: ["cronjobs", "jobs"]' in manifest
    assert 'resources: ["secrets"]' not in manifest


def test_apm_payment_attribute_activation_script_targets_decline_contract() -> None:
    script = _read("deploy/oci/apm/activate_payment_attributes.sh")

    for attribute in (
        "payment.antifraud_reasons",
        "payment.verification.decision",
        "payment.error_code",
        "payment.decision_source",
        "payment.risk_score",
    ):
        assert attribute in script

    assert "DRY_RUN=true" in script
    assert "oci apm-traces attributes activate" in script
    assert "APM_DOMAIN_DISPLAY_NAME:-octo-emdemo-apm" in script
    assert '"attributeType": "NUMERIC"' in script


def test_post_rbac_fix_script_checks_auth_before_apply() -> None:
    script = _read("deploy/oke/apply-post-rbac-fixes.sh")

    assert "APPLY:=false" in script
    assert "kubectl auth can-i" in script
    assert "kubectl rollout restart" in script
    assert "genai-studio-langfuse-sync-cronjob.yaml" in script
    assert "kubectl apply --dry-run=server" in script

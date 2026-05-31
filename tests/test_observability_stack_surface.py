"""Surface + redaction guards for the GenAI observability-stack component.

Mirrors tests/test_oke_langfuse_surface.py. Ensures the Grafana OKE assets exist,
the deploy script keeps the project-VCN guardrails, and NO sensitive data
(tenancy names, OCIDs, IPs, datakeys, Langfuse keys, admin passwords) is
committed in the new external component.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Files introduced by the observability-stack component that must stay clean.
COMPONENT_FILES = [
    "services/observability-stack/README.md",
    "services/observability-stack/.env.example",
    "deploy/oke/deploy-grafana.sh",
    "deploy/k8s/oke/grafana/grafana.yaml",
]
DASHBOARD_GLOB = "deploy/k8s/oke/grafana/dashboards/*.json"

# Structural patterns for sensitive data. These describe the *shape* of secrets
# so the guard never has to hardcode (and thus commit) the very tenancy names /
# namespaces it is meant to keep out of git.
FORBIDDEN_PATTERNS = [
    # Any tenancy OCID family.
    re.compile(r"ocid1\.(tenancy|compartment|apmdomain|loadbalancer|subnet|vcn)\.oc1"),
    # OCIR object-storage namespace embedded in an image path (e.g. <region>.ocir.io/<ns>/...).
    re.compile(r"ocir\.io/[a-z0-9]{8,}/"),
    # Internal-infra public IP ranges.
    re.compile(r"\b(129\.153|130\.61|161\.153|144\.24|141\.147|82\.76|82\.77|109\.166)\.\d+\.\d+\b"),
    # Langfuse ingestion keys.
    re.compile(r"\bpk-lf-[A-Za-z0-9]"),
    re.compile(r"\bsk-lf-[A-Za-z0-9]"),
    # APM datakeys + the apm-agt upload host.
    re.compile(r"dataKey\s+[A-Za-z0-9+/]{20}"),
    re.compile(r"\.apm-agt\."),
]


def _denylist_terms() -> list[str]:
    """Exact tenancy/namespace literals to forbid, loaded WITHOUT committing them.

    Sourced from the env var ``REDACTION_DENYLIST`` (comma-separated) or a
    gitignored ``tests/redaction_denylist.local`` (one term per line). This keeps
    the literal tenancy names (e.g. production/staging profile names, OCIR
    namespaces) out of the repository while still enforcing them locally / in CI
    where the secret list is provided.
    """
    terms: list[str] = []
    env_terms = os.getenv("REDACTION_DENYLIST", "")
    terms += [t.strip() for t in env_terms.split(",") if t.strip()]
    local = ROOT / "tests" / "redaction_denylist.local"
    if local.exists():
        terms += [ln.strip() for ln in local.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    return terms


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_grafana_assets_exist() -> None:
    assert (ROOT / "deploy/oke/deploy-grafana.sh").exists()
    assert (ROOT / "deploy/k8s/oke/grafana/grafana.yaml").exists()
    assert (ROOT / "services/observability-stack/README.md").exists()
    assert (ROOT / "services/observability-stack/.env.example").exists()
    dashboards = list(ROOT.glob(DASHBOARD_GLOB))
    assert dashboards, "expected at least one ported GenAI Grafana dashboard"


def test_grafana_script_enforces_project_vcn_and_checks_rights() -> None:
    script = _read("deploy/oke/deploy-grafana.sh")
    assert "TARGET_VCN_ID" in script
    assert "ALLOW_DIFFERENT_VCN" in script
    assert '."vcn-id"==$vcn' in script
    assert "kubectl auth can-i create deployments" in script
    assert "kubectl auth can-i create configmaps" in script
    assert "oci_cmd ce cluster create-kubeconfig" in script
    # Secrets must be generated, not committed.
    assert "random_base64" in script
    assert "grafana-secrets" in script


def test_grafana_manifest_is_observability_labelled_and_templated() -> None:
    manifest = _read("deploy/k8s/oke/grafana/grafana.yaml")
    assert "app.kubernetes.io/part-of: octo-demo-observability" in manifest
    assert "${GRAFANA_NAMESPACE}" in manifest
    # Admin password comes from a Secret, never inline.
    assert "secretKeyRef" in manifest
    assert "GF_SECURITY_ADMIN_PASSWORD" in manifest
    assert "admin-password" not in manifest.split("secretKeyRef")[0]


def _assert_clean(label: str, text: str) -> None:
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        assert match is None, f"{label} contains forbidden pattern: {match.group(0)!r}"
    lowered = text.lower()
    for term in _denylist_terms():
        assert term.lower() not in lowered, f"{label} contains denylisted literal"


@pytest.mark.parametrize("rel", COMPONENT_FILES)
def test_component_files_have_no_sensitive_data(rel: str) -> None:
    _assert_clean(rel, _read(rel))


def test_dashboards_have_no_sensitive_data() -> None:
    for dash in ROOT.glob(DASHBOARD_GLOB):
        _assert_clean(dash.name, dash.read_text(encoding="utf-8"))

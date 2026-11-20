import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SBOM = "sbom/octo-observability-demo.cdx.json"
DOCKERFILES = {
    path.relative_to(ROOT).as_posix()
    for directory in ("shop", "crm", "services", "tools")
    for path in (ROOT / directory).rglob("Dockerfile")
}
MANIFESTS = {
    "requirements-docs.txt", "shop/requirements.txt", "crm/requirements.txt",
    "services/auto-remediator/requirements.txt", "shop/services/workflow-gateway/go.mod",
    "shop/package.json", "services/browser-runner/package.json",
    "services/apm-java-demo/pom.xml", "deploy/wizard/pyproject.toml",
} | {
    path.relative_to(ROOT).as_posix()
    for directory in ("services", "tools")
    for path in (ROOT / directory).glob("*/pyproject.toml")
}
STACKS = (
    ("deploy/resource-manager", "deploy/resource-manager", "octo-stack.zip"),
    ("deploy/compute/terraform", "deploy/compute", "octo-compute-stack.zip"),
    ("shop/deploy/resource-manager", "shop/deploy/resource-manager", "octo-stack.zip"),
)


def test_sbom_covers_dependency_inputs_and_is_fresh():
    bom = json.loads((ROOT / SBOM).read_text())
    assert (bom["bomFormat"], bom["specVersion"]) == ("CycloneDX", "1.6")
    components = bom["components"]
    purls = {component["purl"] for component in components}
    assert len(purls) == len(components)
    assert {"pypi", "golang", "npm", "maven", "generic", "docker"} <= {
        purl.split(":", 1)[1].split("/", 1)[0] for purl in purls
    }
    inputs = {
        prop["value"] for component in components for prop in component["properties"]
        if prop["name"] == "octo:source"
    }
    assert MANIFESTS | DOCKERFILES <= inputs
    for dockerfile in DOCKERFILES:
        assert any(
            component["type"] == "container"
            and {"name": "octo:source", "value": dockerfile} in component["properties"]
            for component in components
        )
    subprocess.run([sys.executable, "tools/generate_sbom.py", "--check"], cwd=ROOT, check=True)


@pytest.mark.parametrize(("root", "packager", "archive"), STACKS)
def test_orm_schema_parity_and_flat_self_contained_package(root, packager, archive, tmp_path):
    tf_vars = set(re.findall(r'^variable\s+"([^"]+)"', (ROOT / root / "variables.tf").read_text(), re.M))
    schema = yaml.safe_load((ROOT / root / "schema.yaml").read_text())
    grouped = [
        variable for group in schema["variableGroups"] for variable in group["variables"]
    ]
    assert set(schema["variables"]) == tf_vars
    assert set(grouped) == tf_vars
    assert len(grouped) == len(tf_vars)

    subprocess.run(
        ["bash", str(ROOT / packager / "stack-package.sh"), "--output-dir", str(tmp_path)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    with ZipFile(tmp_path / archive) as package:
        names = set(package.namelist())
        assert {"main.tf", "variables.tf", "schema.yaml"} <= names
        assert all(PurePosixPath(name).name != "backend.tf" for name in names)
        package.extractall(tmp_path / "stack")
    stack = tmp_path / "stack"
    root_tf = "\n".join(path.read_text() for path in stack.glob("*.tf"))
    assert re.search(r'provider\s+"oci"\s*\{\s*\}', root_tf)
    for tf in stack.rglob("*.tf"):
        for source in re.findall(r'^\s*source\s*=\s*"(\.{1,2}/[^"]+)"', tf.read_text(), re.M):
            target = (tf.parent / source).resolve()
            assert target.is_relative_to(stack) and target.is_dir(), (tf, source)


def test_active_deployment_surfaces_use_portable_domains_and_repository():
    forbidden = re.compile(
        r"octodemo\.cloud|\bemdemo\b|(?:<|&lt;)github-username(?:>|&gt;)"
        r"|https://[^\s)>\"]*github[^\s)>\"]*/octo-apm-demo(?:[/.\s)>\"]|$)",
        re.I,
    )
    surfaces = [ROOT / "README.md", ROOT / "env.template"]
    for directory in ("deploy", "shop/deploy", "crm/deploy", ".github/workflows"):
        surfaces.extend(
            path for path in (ROOT / directory).rglob("*")
            if path.is_file() and not any(part.startswith(".") or part == "build"
                for part in path.relative_to(ROOT / directory).parts[:-1])
            and (path.suffix in {".tf", ".tftpl", ".sh", ".yaml", ".yml", ".md", ".conf", ".template"}
                 or path.name == "env.template")
        )
    assert not [str(path.relative_to(ROOT)) for path in surfaces if forbidden.search(path.read_text())]


def test_control_plane_manifest_contract():
    manifest = json.loads((ROOT / "deploy/cp-pipeline-manifest.json").read_text())
    schema = json.loads((ROOT / "deploy/cp-pipeline-manifest.schema.json").read_text())
    jsonschema.validate(manifest, schema)
    assert manifest["schemaVersion"] == 1
    assert manifest["repository"] == "adibirzu/octo-observability-demo"
    assert set(manifest["componentIds"]) == {"c2", "c27", "c28"}
    assert manifest["routes"] == {
        role: f"https://{role}.<DNS_DOMAIN>" for role in ("cp", "shop", "crm", "ai")
    }
    assert {target["dockerfile"] for target in manifest["containerBuilds"]} == DOCKERFILES
    for target in manifest["containerBuilds"]:
        assert (ROOT / target["context"]).is_dir()
    assert set(manifest["smoke"]) == {"health", "meltS", "sso"}
    for checks in manifest["smoke"].values():
        assert checks and all(
            check["route"] in manifest["routes"] and check["path"].startswith("/")
            for check in checks
        )
    assert set(manifest["ormPackageScripts"]) == {
        f"{packager}/stack-package.sh" for _, packager, _ in STACKS
    }
    assert manifest["sbom"] == SBOM


def test_terraform_description_uses_literal_dns_placeholder():
    variables = (ROOT / "deploy/terraform/modules/api_gateway/variables.tf").read_text()
    assert "https://shop.<DNS_DOMAIN>" in variables


def test_make_helm_overrides_the_values_consumed_by_templates():
    result = subprocess.run(
        ["make", "-n", "deploy-helm", "DNS_DOMAIN=lab.example.test",
         "OCIR_REGION=region", "OCIR_TENANCY=namespace", "OCI_COMPARTMENT_ID=compartment"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    for setting in ("global.dnsDomain=lab.example.test", "global.image.region=region",
                    "global.image.tenancy=namespace", "secrets.data.ociConfig.compartmentId=compartment"):
        assert setting in shlex.split(result.stdout)


@pytest.mark.parametrize("root", ("deploy/resource-manager", "shop/deploy/resource-manager"))
def test_orm_bootstrap_derives_hosts_from_dns_domain(root):
    schema = yaml.safe_load((ROOT / root / "schema.yaml").read_text())
    assert schema["variables"]["dns_domain"]["required"] is True
    main = (ROOT / root / "main.tf").read_text()
    for service in ("shop", "crm", "ops", "coordinator"):
        assert f'coalesce(var.{service}_domain, "{service}.${{var.dns_domain}}")' in main


def test_smoke_fails_on_http_errors_even_without_a_body_match(tmp_path):
    curl = tmp_path / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
for argument in "$@"; do
    if [[ "$argument" == "-fsS" ]]; then fail_http=true; fi
done
url="${@: -1}"
case "$url" in
    */login) [[ "${fail_http:-false}" == "false" ]] ;;
    */api/shop/app-server/health) printf '%s\\n' '{"java_app_server":{"status":"ok"}}' ;;
    */ready) printf '%s\\n' '{"ready":true,"db_type":"oracle_atp","apm_configured":true,"rum_configured":true,"logging_configured":true,"java_apm_enabled":true,"workflow_gateway_configured":true,"selectai_configured":true,"genai_configured":true}' ;;
    *) printf '%s\\n' '<!doctype html><html>' ;;
esac
""",
    )
    curl.chmod(0o700)
    result = subprocess.run(
        ["bash", str(ROOT / "deploy/validate-deployment.sh")], cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "DNS_DOMAIN": "lab.example.test"},
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Shop /login: request failed" in result.stdout
    assert "Java app server reachable" in result.stdout
    assert "1 of 15 checks failed" in result.stdout


def test_oke_manifests_consume_configured_public_urls():
    cases = {
        "shop/deployment.yaml": 'value: "${CRM_PUBLIC_URL}"',
        "crm/deployment.yaml": 'value: "${CRM_PUBLIC_URL}"',
        "workflow-gateway/deployment.yaml": 'value: "${SHOP_PUBLIC_URL},${CRM_PUBLIC_URL}"',
    }
    for relative, expected in cases.items():
        assert expected in (ROOT / "deploy/k8s/oke" / relative).read_text()


def test_orm_packager_excludes_local_module_input_values(tmp_path):
    wrapper = tmp_path / "resource-manager"
    upstream = tmp_path / "terraform"
    module = upstream / "modules/demo"
    wrapper.mkdir()
    module.mkdir(parents=True)
    (wrapper / "main.tf").write_text('module "demo" { source = "../terraform" }\n')
    (wrapper / "variables.tf").touch()
    (wrapper / "schema.yaml").touch()
    (upstream / "main.tf").write_text('module "demo" { source = "./modules/demo" }\n')
    (module / "main.tf").touch()
    (module / "local.auto.tfvars").write_text('example = "synthetic"\n')

    subprocess.run(
        ["bash", str(ROOT / "tools/package_orm_stack.sh"), str(wrapper)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    with ZipFile(wrapper / "build/octo-stack.zip") as package:
        assert "modules-shared/modules/demo/main.tf" in package.namelist()
        assert not any(name.endswith(".tfvars") for name in package.namelist())


def test_make_smoke_defaults_to_the_pipeline_routes():
    result = subprocess.run(
        ["make", "-n", "smoke", "DNS_DOMAIN=lab.example.test", "OCIR_REGION=region",
         "OCIR_TENANCY=namespace", "OCI_COMPARTMENT_ID=compartment"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert 'SHOP_HOST="${SHOP_HOST:-shop.${DNS_DOMAIN}}"' in result.stdout
    assert 'ADMIN_HOST="${ADMIN_HOST:-crm.${DNS_DOMAIN}}"' in result.stdout

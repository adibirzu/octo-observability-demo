import json
import os
import re
import shlex
import shutil
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
def test_orm_schema_requires_dns_domain(root):
    schema = yaml.safe_load((ROOT / root / "schema.yaml").read_text())
    assert schema["variables"]["dns_domain"]["required"] is True
    assert schema["variables"]["dns_domain"]["type"] == "string"


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


def render_manifest(relative, env):
    rendered = subprocess.run(
        ["envsubst"], input=(ROOT / "deploy/k8s/oke" / relative).read_text(),
        env={"PATH": os.environ["PATH"], **env}, capture_output=True, text=True, check=True,
    ).stdout
    return [doc for doc in yaml.safe_load_all(rendered) if doc]


def container_env(documents):
    values = {}
    for document in documents:
        template = document.get("spec", {}).get("template", {}).get("spec", {})
        for container in template.get("containers", []):
            for item in container.get("env", []):
                values[item["name"]] = item.get("value")
    return values


@pytest.mark.skipif(shutil.which("envsubst") is None, reason="envsubst is required")
def test_oke_manifests_render_configured_public_urls():
    env = {
        "SHOP_PUBLIC_URL": "https://shop.lab.example.test",
        "CRM_PUBLIC_URL": "https://crm.lab.example.test",
        "DNS_DOMAIN": "lab.example.test", "K8S_NAMESPACE_SHOP": "shop-ns",
        "K8S_NAMESPACE_CRM": "crm-ns", "OCIR_REGION": "region",
        "OCIR_TENANCY": "namespace", "IMAGE_TAG": "tag",
    }
    shop = container_env(render_manifest("shop/deployment.yaml", env))
    crm = container_env(render_manifest("crm/deployment.yaml", env))
    gateway = container_env(render_manifest("workflow-gateway/deployment.yaml", env))
    assert shop["CRM_PUBLIC_URL"] == "https://crm.lab.example.test"
    assert crm["CRM_BASE_URL"] == "https://crm.lab.example.test"
    assert "https://shop.lab.example.test,https://crm.lab.example.test" in gateway.values()


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


@pytest.mark.parametrize("overrides, shop, crm", (
    ({}, "shop.lab.example.test", "crm.lab.example.test"),
    ({"SHOP_HOST": "s.custom.test", "ADMIN_HOST": "a.custom.test"}, "s.custom.test", "a.custom.test"),
))
def test_make_smoke_probes_the_pipeline_routes(tmp_path, overrides, shop, crm):
    log = tmp_path / "urls.log"
    curl = tmp_path / "curl"
    curl.write_text(f"""#!/usr/bin/env bash
printf '%s\\n' "${{@: -1}}" >> {log}
printf '%s\\n' '<!doctype html><html>'
""")
    curl.chmod(0o700)
    result = subprocess.run(
        ["make", "smoke", "DNS_DOMAIN=lab.example.test", "OCIR_REGION=region",
         "OCIR_TENANCY=namespace", "OCI_COMPARTMENT_ID=compartment"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", **overrides},
    )
    assert log.exists(), result.stdout + result.stderr
    hosts = {url.split("/")[2] for url in log.read_text().split()}
    assert hosts == {shop, crm}


def strip_hcl_comments(text):
    out, i, quote = [], 0, False
    while i < len(text):
        two = text[i:i + 2]
        if quote:
            out.append(text[i])
            if text[i] == "\\":
                out.append(text[i + 1])
                i += 1
            elif text[i] == '"':
                quote = False
        elif text[i] == '"':
            quote = True
            out.append('"')
        elif text[i] == "#" or two == "//":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif two == "/*":
            i = text.index("*/", i) + 1
        else:
            out.append(text[i])
        i += 1
    return "".join(out)


def hcl_block_body(text, header):
    start = strip_hcl_comments(text)
    match = re.search(re.escape(header) + r"\s*\{", start)
    assert match, header
    depth, quote, i = 1, False, match.end()
    begin = i
    while depth:
        char = start[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return start[begin:i - 1]


def hcl_attributes(body):
    return {name: value.strip() for name, value in re.findall(r"^\s*(\w+)\s*=\s*(.+)$", body, re.M)}


def derived_host(expression, variables):
    match = re.fullmatch(r'coalesce\(var\.(\w+),\s*"([^"]*)"\)', expression)
    assert match, expression
    override, template = match.groups()
    return variables[override] or template.replace("${var.dns_domain}", variables["dns_domain"])


@pytest.mark.parametrize("root", ("deploy/resource-manager", "shop/deploy/resource-manager"))
def test_orm_bootstrap_derives_hosts_from_dns_domain(root):
    main = (ROOT / root / "main.tf").read_text()
    variables = (ROOT / root / "variables.tf").read_text()
    attributes = hcl_attributes(hcl_block_body(main, 'module "stack"'))
    services = ("shop", "crm", "ops", "coordinator")
    for service in services:
        assert hcl_attributes(hcl_block_body(variables, f'variable "{service}_domain"'))["default"] == '""'
        inputs = {f"{name}_domain": "" for name in services} | {"dns_domain": "lab.example.test"}
        assert derived_host(attributes[f"{service}_domain"], inputs) == f"{service}.lab.example.test"
        assert derived_host(attributes[f"{service}_domain"], inputs | {f"{service}_domain": "x.test"}) == "x.test"
    assert "default" not in hcl_attributes(hcl_block_body(variables, 'variable "dns_domain"'))


def test_root_terraform_keeps_example_host_defaults():
    variables = (ROOT / "deploy/terraform/variables.tf").read_text()
    for service in ("shop", "crm"):
        defaults = hcl_attributes(hcl_block_body(variables, f'variable "{service}_domain"'))
        assert defaults["default"] == f'"{service}.example.test"'

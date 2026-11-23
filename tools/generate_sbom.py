#!/usr/bin/env python3
"""Generate an offline inventory of declared dependencies and Docker build stages."""

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from public_sbom import validate_public_bom


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sbom/octo-observability-demo.cdx.json"
SCHEMA = "http://cyclonedx.org/schema/bom-1.6.schema.json"
IGNORED = {"build", "dist", "node_modules", "venv", "site-packages"}
MANIFESTS = {"go.mod", "package.json", "package-lock.json", "pom.xml", "pyproject.toml"}


def inventory_inputs():
    paths = {ROOT / "requirements-docs.txt"}
    for parent in ("shop", "crm", "services", "tools", "deploy/wizard"):
        for directory, children, files in os.walk(ROOT / parent):
            children[:] = [
                name for name in children if name not in IGNORED and not name.startswith(".")
            ]
            for name in files:
                if (name in MANIFESTS or name == "Dockerfile"
                        or name.startswith("Dockerfile.")
                        or re.fullmatch(r"requirements(?:-[\w-]+)?\.txt", name)):
                    paths.add(Path(directory) / name)
    return sorted(paths)


class Inventory:
    def __init__(self):
        self.components = {}
        self.properties = defaultdict(set)

    def add(self, ecosystem, name, source, *, version="", kind="library",
            namespace="", qualifier="", requirement=""):
        namespace_path = "".join(quote(part, safe="") + "/" for part in namespace.split("/") if part)
        purl = f"pkg:{ecosystem}/{namespace_path}{quote(name, safe='')}"
        if version:
            purl += "@" + quote(version, safe="")
        if qualifier:
            purl += "?" + qualifier

        component = {"type": kind, "name": name, "purl": purl, "bom-ref": purl}
        if namespace:
            component["group"] = namespace
        if version:
            component["version"] = version
        self.components[purl] = component
        self.properties[purl].add(("octo:source", source))
        if requirement:
            self.properties[purl].add(("octo:declaration", f"{source}: {requirement}"))

    def sorted_components(self):
        return [
            {
                **self.components[purl],
                "properties": [
                    {"name": name, "value": value}
                    for name, value in sorted(self.properties[purl])
                ],
            }
            for purl in sorted(self.components)
        ]


def add_python(inventory, value, source):
    match = re.fullmatch(r"([\w.-]+)(?:\[[^]]+\])?(.*)", value)
    if not match:
        raise ValueError(f"{source}: unsupported Python dependency declaration")
    name = re.sub(r"[-_.]+", "-", match[1]).lower()
    pin = re.fullmatch(r"\s*==\s*([\w.!+-]+)\s*", match[2].split(";", 1)[0])
    inventory.add("pypi", name, source, version=pin[1] if pin else "", requirement=value)


def requirements(inventory, path, source):
    for line in path.read_text(encoding="utf-8").splitlines():
        value = re.split(r"(?:^|\s+)#", line, maxsplit=1)[0].strip()
        if not value:
            continue
        if value.startswith(("-r ", "--requirement ")):
            included = (path.parent / value.split(maxsplit=1)[1]).resolve()
            if not included.is_relative_to(ROOT) or not included.is_file():
                raise ValueError(f"{source}: missing repository requirements include")
        elif value.startswith(("-e ", "--editable ")):
            manifest = (path.parent / value.split(maxsplit=1)[1] / "pyproject.toml").resolve()
            if not manifest.is_relative_to(ROOT):
                raise ValueError(f"{source}: editable dependency is outside the repository")
            project = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]
            add_python(inventory, f'{project["name"]}=={project["version"]}', source)
        else:
            add_python(inventory, value, source)


def pyproject(inventory, path, source):
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data["project"]
    add_python(inventory, f'{project["name"]}=={project["version"]}', source)
    groups = [
        project.get("dependencies", []),
        data.get("build-system", {}).get("requires", []),
        *project.get("optional-dependencies", {}).values(),
    ]
    for group in groups:
        for value in group:
            add_python(inventory, value, source)


def go_modules(inventory, path, source):
    in_require = False
    for line in path.read_text(encoding="utf-8").splitlines():
        words = line.split("//", 1)[0].split()
        if not words:
            continue
        if words == ["require", "("]:
            in_require = True
        elif words == [")"]:
            in_require = False
        elif in_require or words[0] == "require":
            module, version = words if in_require else words[1:]
            namespace, _, name = module.rpartition("/")
            inventory.add("golang", name, source, namespace=namespace, version=version)
        elif words[0] == "replace":
            raise ValueError(f"{source}: Go replacement declarations need inventory support")


def add_npm(inventory, name, version, source, declaration=""):
    namespace, _, name = name.rpartition("/")
    inventory.add("npm", name, source, namespace=namespace, version=version, requirement=declaration)


def npm(inventory, path, source):
    data = json.loads(path.read_text(encoding="utf-8"))
    add_npm(inventory, data["name"], data["version"], source)
    if path.name == "package-lock.json":
        for key, item in data["packages"].items():
            if key and "version" in item:
                name = item.get("name", key.split("node_modules/")[-1])
                add_npm(inventory, name, item["version"], source)
    else:
        for group in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            for name, declaration in data.get(group, {}).items():
                pin = re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.+-]+)?", declaration)
                add_npm(inventory, name, pin[0] if pin else "", source, declaration)


def maven(inventory, path, source):
    pom = ET.parse(path).getroot()
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    properties = {
        child.tag.rsplit("}", 1)[-1]: child.text for child in pom.findall("m:properties/*", ns)
    }
    entries = [pom, *pom.findall("m:parent", ns), *pom.findall(".//m:dependency", ns),
               *pom.findall(".//m:plugin", ns)]
    for entry in entries:
        group = entry.findtext("m:groupId", namespaces=ns) or "org.apache.maven.plugins"
        name = entry.findtext("m:artifactId", namespaces=ns)
        version = entry.findtext("m:version", namespaces=ns)
        if version:
            version = re.sub(r"\$\{([^}]+)\}", lambda match: properties[match[1]], version)
        qualifier = "type=pom" if entry.tag.endswith("}parent") else ""
        inventory.add("maven", name, source, namespace=group, version=version or "",
                      qualifier=qualifier, requirement="" if version else "managed by parent")


def docker(inventory, path, source):
    args = {}
    stages = set()
    lines = path.read_text(encoding="utf-8").replace("\\\n", "").splitlines()
    for line in lines:
        arg = re.fullmatch(r"\s*ARG\s+(\w+)=(\S+)\s*", line, re.I)
        if arg and not stages:
            args[arg[1]] = arg[2]
        stage = re.match(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line, re.I)
        if not stage:
            continue
        base = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda match: args[match[1] or match[2]], stage[1])
        name = stage[2] or f"stage-{len(stages) + 1}"
        inventory.add("generic", name, source, kind="container",
                      qualifier="dockerfile=" + quote(source, safe=""), requirement=base)
        if base.lower() not in stages and base != "scratch":
            repository, _, digest = base.partition("@")
            namespace, _, image = repository.rpartition("/")
            image, _, tag = image.partition(":")
            inventory.add("docker", image, source, kind="container",
                          namespace=namespace.lower(), version=digest or tag or "latest",
                          requirement=base)
        stages.add(name.lower())
    if not stages:
        raise ValueError(f"{source}: no Docker build stages")


def generate():
    readers = {
        "go.mod": go_modules,
        "package.json": npm,
        "package-lock.json": npm,
        "pom.xml": maven,
        "pyproject.toml": pyproject,
    }
    inventory = Inventory()
    fingerprints = []
    for path in inventory_inputs():
        source = path.relative_to(ROOT).as_posix()
        reader = readers.get(path.name)
        if reader is None:
            reader = docker if path.name.startswith("Dockerfile") else requirements
        reader(inventory, path, source)
        fingerprints.append({
            "name": "octo:input-sha256",
            "value": f"{source} {hashlib.sha256(path.read_bytes()).hexdigest()}",
        })

    return {
        "$schema": SCHEMA,
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "octo-observability-demo",
                "purl": "pkg:github/adibirzu/octo-observability-demo",
            },
            "properties": fingerprints,
        },
        "components": inventory.sorted_components(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the canonical CycloneDX 1.6 BOM")
    mode.add_argument("--check", action="store_true", help="reject a missing or stale BOM")
    args = parser.parse_args()
    try:
        bom = generate()
        validate_public_bom(bom)
        expected = json.dumps(bom, indent=2, ensure_ascii=True) + "\n"
        if args.write:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(expected, encoding="utf-8")
        elif not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print(f"{OUTPUT.relative_to(ROOT)} is missing, invalid, or stale. Run make sbom.",
                  file=sys.stderr)
            return 1
    except (KeyError, OSError, ValueError, ET.ParseError) as error:
        print(f"SBOM generation failed: {error}", file=sys.stderr)
        return 1
    print(f"{OUTPUT.relative_to(ROOT)}: {len(bom['components'])} components, "
          f"{len(bom['metadata']['properties'])} inputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())

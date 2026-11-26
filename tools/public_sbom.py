#!/usr/bin/env python3
"""Export package-only CycloneDX and vulnerability summaries for public releases."""
import argparse
import ipaddress
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

PUBLIC_HOSTS = {
    "cyclonedx.org", "docker.io", "gcr.io", "github.com", "go.opentelemetry.io",
    "golang.org", "google.golang.org", "mcr.microsoft.com", "k8s.io",
    "sigs.k8s.io", "go.uber.org", "cloud.google.com", "go.opencensus.io",
    "gopkg.in", "gotest.tools", "honnef.co", "gorm.io", "modernc.org",
    "go.yaml.in", "filippo.io", "rsc.io", "howett.net", "mvdan.cc",
    "go.etcd.io", "go.mongodb.org", "go4.org",
}
ECOSYSTEMS = {"pypi", "npm", "golang", "maven", "deb", "rpm", "apk", "generic",
              "cargo", "gem", "nuget", "composer", "pub", "swift", "cocoapods",
              "hex", "hackage", "cran", "conan", "github", "docker"}
PUBLIC_IMAGES = ("docker.io/library/", "gcr.io/distroless/",
                 "mcr.microsoft.com/playwright@", "grafana/k6@",
                 "otel/opentelemetry-collector-contrib@", "golang@", "python@")
IP = re.compile(r"(?<!\w)(?:\d{1,3}\.){3}\d{1,3}(?!\w)")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def decoded(text):
    while unquote(text) != text:
        text = unquote(text)
    return text


def package_identity(purl):
    if not isinstance(purl, str) or not purl.startswith("pkg:"):
        raise ValueError("missing package URL")
    clean = purl.split("?", 1)[0].split("#", 1)[0]
    body = clean[4:]
    coordinate, separator, version = body.rpartition("@")
    if not separator:
        coordinate, version = body, ""
    ecosystem, _, path = coordinate.partition("/")
    parts = decoded(path).split("/")
    if ecosystem not in ECOSYSTEMS or not parts or not all(parts):
        raise ValueError("unsupported package identity")
    if not all(re.fullmatch(r"@?[\w.+%-]+", part) for part in parts):
        raise ValueError("invalid package identity")
    if ecosystem in {"pypi", "cargo", "gem", "nuget"} and len(parts) != 1:
        raise ValueError("unexpected package namespace")
    if ecosystem == "golang" and parts[0] not in PUBLIC_HOSTS and path not in {
        "stdlib", "octo-drone-shop/services/workflow-gateway",
    }:
        raise ValueError("unapproved Go module host")
    if ecosystem == "docker" and not decoded(body.partition("/")[2]).startswith(PUBLIC_IMAGES):
        raise ValueError("unapproved container namespace")
    if ecosystem == "generic" and (len(parts) != 1 or "." in parts[0]):
        raise ValueError("unapproved generic identity")
    for part in parts:
        try:
            ipaddress.ip_address(part)
        except ValueError:
            continue
        raise ValueError("network address in package identity")
    result = {"name": parts[-1], "purl": clean}
    if len(parts) > 1:
        result["group"] = "/".join(parts[:-1])
    if version:
        result["version"] = decoded(version)
    return result


def validate_public_bom(value):
    """Reject private coordinates without echoing the offending content."""
    def visit(item, key=""):
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, child_key)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str):
            text = decoded(item).lower()
            if any(marker in text for marker in (
                "ocid1.", ".ocir.", "ocir.io", ".svc.", "cluster.local",
                "-----begin ", "private_key", "auth_token",
            )):
                raise ValueError("private identifier")
            if key == "purl" or (key == "bom-ref" and item.startswith("pkg:")):
                package_identity(item)
                return
            if key == "version":
                return
            if any(host not in PUBLIC_HOSTS for host in
                   re.findall(r"https?://([^/\s\"?]+)", text)):
                raise ValueError("unapproved URL host")
            for candidate in IP.findall(text):
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                raise ValueError("network address")
    visit(value)


def public_bom(raw, name, version, digest=None):
    if raw.get("bomFormat") != "CycloneDX" or raw.get("specVersion") not in {"1.4", "1.5", "1.6", "1.7"}:
        raise ValueError("unsupported SBOM")
    components = []
    pending = list(raw.get("components", []))
    seen = set()
    while pending:
        component = pending.pop()
        pending.extend(component.get("components", []))
        if component.get("type") not in {"library", "framework"}:
            continue
        item = {"type": component["type"], **package_identity(component.get("purl"))}
        if item["purl"] not in seen:
            components.append(item)
            seen.add(item["purl"])
    if not components or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("invalid package inventory or artifact name")
    metadata = {"component": {"type": "application", "name": name, "version": version}}
    if digest:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError("invalid image digest")
        metadata["component"]["hashes"] = [{"alg": "SHA-256", "content": digest[7:]}]
        metadata["properties"] = [{"name": "octo:image-digest", "value": digest}]
    return {"$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
            "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": metadata, "components": sorted(components, key=lambda item: item["purl"])}


def vulnerability_summary(raw, name, version, digest=None):
    results = raw.get("Results")
    if results is None and raw.get("SchemaVersion") == 2 and raw.get("ArtifactType") and raw.get("ArtifactName"):
        results = []
    if not isinstance(results, list) or any(not isinstance(result, dict) for result in results):
        raise ValueError("missing or malformed scanner results")
    findings = []
    for result in results:
        for finding in result.get("Vulnerabilities") or []:
            severity = finding.get("Severity", "UNKNOWN").upper()
            if severity not in SEVERITIES:
                severity = "UNKNOWN"
            identifier = finding["VulnerabilityID"]
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+", identifier):
                raise ValueError("invalid vulnerability identifier")
            public_finding = {"id": identifier, "severity": severity}
            purl = finding.get("PkgIdentifier", {}).get("PURL")
            if purl:
                public_finding["purl"] = package_identity(purl)["purl"]
            findings.append(public_finding)
    counts = Counter(item["severity"] for item in findings)
    summary = {"name": name, "version": version, "scanner": "Trivy",
               "counts": {severity: counts[severity] for severity in SEVERITIES},
               "findings": findings}
    if digest:
        summary["imageDigest"] = digest
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--version")
    parser.add_argument("--digest")
    parser.add_argument("--vulnerabilities", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    try:
        if args.check:
            validate_public_bom(json.loads(args.check.read_text()))
            return 0
        if not all((args.input, args.output, args.name, args.version)):
            parser.error("--input, --output, --name and --version are required")
        if bool(args.vulnerabilities) != bool(args.summary):
            parser.error("--vulnerabilities and --summary must be paired")
        bom = public_bom(json.loads(args.input.read_text()), args.name, args.version, args.digest)
        validate_public_bom(bom)
        summary = None
        if args.vulnerabilities:
            summary = vulnerability_summary(json.loads(args.vulnerabilities.read_text()),
                                            args.name, args.version, args.digest)
            validate_public_bom(summary)
        args.output.write_text(json.dumps(bom, indent=2) + "\n")
        if summary is not None:
            args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print("public SBOM rejected: invalid input or private identifier", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

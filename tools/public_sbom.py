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
    "golang.org", "google.golang.org", "mcr.microsoft.com",
}
HOST = re.compile(r"(?:[a-z0-9-]+\.)+(?:com|org|io|net|dev|cloud|ai|internal|local|example|invalid|test|biz|corp|lan|private)\b", re.I)
IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def validate_public_bom(value):
    """Reject private identifiers without echoing the offending content."""
    text = json.dumps(value, ensure_ascii=True).lower()
    while unquote(text) != text:
        text = unquote(text)
    public_images = ("docker.io/library/", "gcr.io/distroless/",
                     "mcr.microsoft.com/playwright@", "grafana/k6@",
                     "otel/opentelemetry-collector-contrib@", "golang@", "python@")
    if "pkg:oci/" in text:
        raise ValueError("unapproved container coordinate")
    for coordinate in re.findall(r'pkg:docker/([^"\s]+)', text):
        if not coordinate.startswith(public_images):
            raise ValueError("unapproved container namespace")
    if any(marker in text for marker in (
        "ocid1.", ".ocir.", "ocir.io", ".svc.", "cluster.local",
        "-----begin ", "private_key", "auth_token", "password",
    )):
        raise ValueError("private identifier")
    if any(host.lower() not in PUBLIC_HOSTS for host in HOST.findall(text)):
        raise ValueError("unapproved hostname")
    for candidate in IP.findall(text):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        raise ValueError("network address")


def public_bom(raw, name, version):
    if raw.get("bomFormat") != "CycloneDX" or raw.get("specVersion") not in {"1.4", "1.5", "1.6"}:
        raise ValueError("unsupported SBOM")
    components = []
    for component in raw.get("components", []):
        item = {key: component[key] for key in
                ("type", "name", "group", "version", "purl", "cpe")
                if key in component}
        if not item.get("name") or not item.get("type"):
            raise ValueError("missing package identity")
        components.append(item)
    if not components:
        raise ValueError("empty package inventory")
    return {"$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
            "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"component": {"type": "application", "name": name, "version": version}},
            "components": components}


def vulnerability_summary(raw, name, version):
    if not isinstance(raw.get("Results"), list):
        raise ValueError("missing scanner results")
    findings = []
    for result in raw["Results"]:
        for finding in result.get("Vulnerabilities") or []:
            severity = finding.get("Severity", "UNKNOWN").upper()
            if severity not in SEVERITIES:
                severity = "UNKNOWN"
            findings.append({"id": finding["VulnerabilityID"], "severity": severity,
                             "package": finding["PkgName"],
                             "installed": finding.get("InstalledVersion", ""),
                             "fixed": finding.get("FixedVersion", "")})
    counts = Counter(item["severity"] for item in findings)
    return {"name": name, "version": version, "scanner": "Trivy",
            "counts": {severity: counts[severity] for severity in SEVERITIES},
            "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--version")
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
        bom = public_bom(json.loads(args.input.read_text()), args.name, args.version)
        validate_public_bom(bom)
        summary = None
        if args.vulnerabilities:
            summary = vulnerability_summary(json.loads(args.vulnerabilities.read_text()),
                                            args.name, args.version)
            validate_public_bom(summary)
        args.output.write_text(json.dumps(bom, indent=2) + "\n")
        if summary is not None:
            args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    except (OSError, ValueError, KeyError, TypeError):
        print("public SBOM rejected: invalid input or private identifier", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

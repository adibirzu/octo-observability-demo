#!/usr/bin/env python3.11
"""Run the local CI checks and report any unavailable workflow checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import errno
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
GATE_DIR = ROOT / ".gate"
DEFAULT_RECEIPT = GATE_DIR / "local-ci-receipt.json"

SANDBOX_OFFLINE_PROFILE = "(version 1) (allow default) (deny network*)"
SANDBOX_OUTBOUND_PROFILE = SANDBOX_OFFLINE_PROFILE + (
    ' (allow network-outbound (remote tcp "*:443") '
    '(remote unix-socket (path-literal "/private/var/run/mDNSResponder")))'
)

ALLOWED_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
)

WORKFLOW_CHECKS = {
    "tests.yml:tests": ("sbom-generate-check", "pytest-contract", "pytest-shop"),
    "tests.yml:crm": ("pytest-crm",),
    "tests.yml:visual": ("playwright-visual-receipt",),
    "orm-and-sbom-release.yml:package": (
        "pytest-contract", "sbom-generate-check", "sbom-public-check",
        "release-matrix", "orm-archives", "orm-terraform-validate",
        "trivy-source-inventory", "trivy-source-vulnerabilities", "orm-artifact-upload",
    ),
    "orm-and-sbom-release.yml:images": (
        "release-matrix", "orm-native-image-build", "orm-image-scans",
        "orm-image-publish-attest", "orm-image-artifacts",
    ),
    "orm-and-sbom-release.yml:attach": (
        "orm-archives", "orm-release-artifact-transfer",
    ),
    "ocir-publish.yml:publish": (
        "ocir-source-selection", "ocir-native-image-build", "ocir-image-scans",
        "ocir-publish", "ocir-artifact-upload",
    ),
}

HOSTED_ONLY = {
    "playwright-visual-receipt": "Requires Chromium MachPortRendezvousServer outside Seatbelt or a Linux CI runner",
    "orm-artifact-upload": "GitHub artifact upload requires an Actions run",
    "orm-native-image-build": "Requires a native Linux amd64 builder and approved inputs",
    "orm-image-scans": "Requires the exact native Linux amd64 images from the build",
    "orm-image-publish-attest": "Requires registry writes and GitHub Actions OIDC",
    "orm-image-artifacts": "Requires the verified image digests and GitHub artifact upload",
    "orm-release-artifact-transfer": "Requires Actions artifact download and GitHub release upload",
    "ocir-native-image-build": "Requires a native Linux amd64 builder and approved inputs",
    "ocir-image-scans": "Requires the exact candidate images from the native build",
    "ocir-publish": "Requires approved registry credentials and a registry write",
    "ocir-artifact-upload": "Requires a verified registry digest and GitHub artifact upload",
}

AUDIT_MANIFESTS = {
    "pip-audit-shop": ("requirements.txt",),
    "pip-audit-crm": ("requirements.txt",),
    "npm-audit-shop": ("package.json", "package-lock.json"),
    "npm-audit-browser-runner": ("package.json", "package-lock.json"),
}

APP_TEST_DIRS: tuple[tuple[str, str], ...] = (
    ("pytest-service-async-worker", "services/async-worker"),
    ("pytest-service-cache", "services/cache"),
    ("pytest-service-edge-fuzz", "services/edge-fuzz"),
    ("pytest-service-genai-studio", "services/genai-studio"),
    ("pytest-service-load-control", "services/load-control"),
    ("pytest-service-object-pipeline", "services/object-pipeline"),
    ("pytest-service-remediator", "services/remediator"),
    ("pytest-tool-traffic-generator", "tools/traffic-generator"),
    ("pytest-deploy-wizard", "deploy/wizard"),
)


@dataclass(frozen=True)
class GateStep:
    name: str
    mode: str  # "lint" or "test"
    command: list[str]
    cwd: Path = ROOT
    env: dict[str, str] = field(default_factory=dict)
    online: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    cleanup_paths: tuple[Path, ...] = ()
    extra_commands: tuple[list[str], ...] = ()

    def all_commands(self) -> list[list[str]]:
        return [list(self.command), *(list(cmd) for cmd in self.extra_commands)] if self.command else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "command": list(self.command),
            "commands": self.all_commands(),
            "cwd": str(self.cwd),
            "online": self.online,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


def default_python(repo_root: Path = ROOT) -> str:
    gate_python = repo_root / ".gate/venv/bin/python"
    if gate_python.is_file() and os.access(gate_python, os.X_OK):
        return str(gate_python)
    return sys.executable


def _normalize_platform_root_alias(path: Path) -> Path:
    raw = Path(path)
    if ".." in raw.parts:
        raise OSError(
            errno.EINVAL, "Refusing '..' path traversal component", str(path)
        )
    if not raw.is_absolute():
        raw = Path(os.getcwd()) / raw
        if ".." in raw.parts:
            raise OSError(
                errno.EINVAL, "Refusing '..' path traversal component", str(path)
            )
    if (
        platform.system() == "Darwin"
        and len(raw.parts) >= 2
        and raw.parts[0] == "/"
        and raw.parts[1] in {"var", "tmp", "etc"}
    ):
        alias_target = Path("/private") / raw.parts[1]
        if alias_target.exists():
            raw = alias_target.joinpath(*raw.parts[2:])
    return raw


def _open_private_parent_fd(
    path: Path, trusted_root: Path | None = None
) -> tuple[int, str]:
    norm_path = _normalize_platform_root_alias(path)
    leaf_name = norm_path.name
    if not leaf_name or leaf_name in {".", ".."}:
        raise OSError(errno.EINVAL, "Invalid private output filename", str(path))

    if trusted_root is not None:
        norm_root = _normalize_platform_root_alias(Path(trusted_root))
        if not norm_path.parent.is_relative_to(norm_root):
            raise OSError(
                errno.EXDEV,
                "Private output path is outside trusted root",
                str(path),
            )
    else:
        candidates = (
            _normalize_platform_root_alias(ROOT),
            _normalize_platform_root_alias(Path(tempfile.gettempdir())),
        )
        norm_root = next(
            (c for c in candidates if norm_path.parent.is_relative_to(c)),
            Path("/"),
        )

    dir_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    cur_fd = os.open("/", dir_flags)
    try:
        for part in norm_root.parts[1:]:
            next_fd = os.open(part, dir_flags, dir_fd=cur_fd)
            os.close(cur_fd)
            cur_fd = next_fd

        rel_parent = norm_path.parent.relative_to(norm_root)
        for part in rel_parent.parts:
            if not part or part in {".", ".."}:
                raise OSError(
                    errno.EINVAL, "Invalid directory component", str(path)
                )
            try:
                next_fd = os.open(part, dir_flags, dir_fd=cur_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=cur_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, dir_flags, dir_fd=cur_fd)
            os.close(cur_fd)
            cur_fd = next_fd
    except Exception:
        try:
            os.close(cur_fd)
        except OSError:
            pass
        raise

    return cur_fd, leaf_name


def open_private_write(path: Path, *, trusted_root: Path | None = None):
    parent_fd, leaf_name = _open_private_parent_fd(
        path, trusted_root=trusted_root
    )
    try:
        try:
            existing_st = os.lstat(leaf_name, dir_fd=parent_fd)
        except FileNotFoundError:
            created_new = True
        else:
            if stat.S_ISLNK(existing_st.st_mode) or not stat.S_ISREG(
                existing_st.st_mode
            ):
                raise OSError(
                    errno.ELOOP,
                    "Refusing symlink or non-regular target",
                    str(path),
                )
            created_new = False

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_TRUNC
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(leaf_name, flags, 0o600, dir_fd=parent_fd)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise OSError(
                    errno.EINVAL,
                    "Private output target must be a regular file",
                    str(path),
                )
            os.fchmod(fd, 0o600)
            return os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if created_new:
                try:
                    os.unlink(leaf_name, dir_fd=parent_fd)
                except OSError:
                    pass
            raise
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


def write_private_text(
    path: Path, content: str, *, trusted_root: Path | None = None
) -> None:
    parent_fd, leaf_name = _open_private_parent_fd(
        path, trusted_root=trusted_root
    )
    try:
        try:
            existing_st = os.lstat(leaf_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(existing_st.st_mode) or not stat.S_ISREG(
                existing_st.st_mode
            ):
                raise OSError(
                    errno.ELOOP,
                    "Refusing symlink or non-regular target",
                    str(path),
                )

        tmp_name = f".{leaf_name}.tmp-{os.getpid()}-{time.time_ns()}"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(tmp_name, flags, 0o600, dir_fd=parent_fd)
        fd_owned = False
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise OSError(
                    errno.EINVAL,
                    "Private temporary file must be a regular file",
                    str(path),
                )
            os.fchmod(fd, 0o600)
            handle = os.fdopen(fd, "w", encoding="utf-8")
            fd_owned = True
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                dest_st = os.lstat(leaf_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISLNK(dest_st.st_mode) or not stat.S_ISREG(
                    dest_st.st_mode
                ):
                    raise OSError(
                        errno.ELOOP,
                        "Refusing symlink destination",
                        str(path),
                    )
            os.replace(
                tmp_name,
                leaf_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except Exception:
            if not fd_owned:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


def verify_sandbox_available() -> str:
    if platform.system() != "Darwin":
        raise RuntimeError(
            "macOS Darwin platform required for sandbox-exec isolation; refusing unisolated execution"
        )
    sandbox_bin = shutil.which("sandbox-exec")
    if not sandbox_bin:
        raise RuntimeError(
            "macOS sandbox-exec binary required; refusing unisolated execution"
        )
    return sandbox_bin


def sandbox_profile_for_step(
    step: GateStep,
    allow_online: bool = False,
    repo_root: Path = ROOT,
    socket_dir: Path | None = None,
) -> str:
    if step.online and allow_online:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
        root = repo_root.resolve()
        workspace = json.dumps(str(root))
        credential_dirs = (
            ".ssh", ".oci", ".aws", ".kube", ".azure", ".docker", ".gnupg",
            ".config", ".local/share/keyrings", ".npm", ".pip", "Library/Keychains",
            "Library/Application Support/pip",
        )
        credential_files = (
            home / ".netrc", home / ".npmrc", home / ".pypirc",
            home / ".git-credentials", home / ".gitconfig",
            Path("/private/etc/pip.conf"), Path("/Library/Application Support/pip/pip.conf"),
            Path("/opt/homebrew/etc/npmrc"), Path("/usr/local/etc/npmrc"),
        )
        directories = [home / name for name in credential_dirs]
        read_filters = " ".join(
            [f"(subpath {json.dumps(str(path))})" for path in directories]
            + [f"(literal {json.dumps(str(path))})" for path in credential_files]
        )
        executables: set[Path] = set()
        for command in step.all_commands():
            executable = Path(command[0])
            if executable.is_absolute() and executable.is_file() and os.access(executable, os.X_OK):
                executables.update((executable, executable.resolve()))
        metadata_paths = {root, *root.parents, root / ".gate"}
        for executable in executables:
            metadata_paths.update(executable.parents)
        ancestors = " ".join(
            f"(literal {json.dumps(str(path))})"
            for path in sorted(metadata_paths)
        )
        executable_reads = "".join(
            f" (allow file-read* (literal {json.dumps(str(path))}))"
            for path in sorted(executables)
        )
        return (
            SANDBOX_OUTBOUND_PROFILE
            + f" (deny file-write* (subpath {json.dumps(str(home))}) (subpath {workspace}))"
            + f" (deny file-read* (subpath {json.dumps(str(home))}))"
            + f" (allow file-read-metadata {ancestors})"
            + f" (allow file-read* (subpath {json.dumps(str(root / '.gate/venv'))}))"
            + executable_reads
            + f" (deny file-read* {read_filters})"
            + f" (deny file-read* (require-all (subpath {workspace}) "
              '(regex #".*/([.]env([.]|/|$)|[^/]+[.]env([.]|/|$)|[.]npmrc$|pip[.]conf$|'
              '[.]git(/|$)|(secrets|credentials|wallet)(/|$)|[^/]+[.](pem|key|p12|wallet)$)")))'
        )
    if socket_dir is not None:
        socket_path = re.escape(str(socket_dir.resolve()))
        socket_filter = f'unix-socket (regex #"^{socket_path}/")'
        return (
            SANDBOX_OFFLINE_PROFILE
            + f" (allow network-bind network-inbound (local {socket_filter}))"
            + f" (allow network-outbound (remote {socket_filter}))"
        )
    return SANDBOX_OFFLINE_PROFILE


def build_audit_env(home: Path) -> dict[str, str]:
    configs = {
        "PIP_CONFIG_FILE": "pip.conf",
        "NPM_CONFIG_USERCONFIG": "npm-user.conf",
        "NPM_CONFIG_GLOBALCONFIG": "npm-global.conf",
    }
    for filename in configs.values():
        write_private_text(home / filename, "", trusted_root=home)
    return {
        **{key: str(home / filename) for key, filename in configs.items()},
        "PYTHONSAFEPATH": "1",
        "PYTHONNOUSERSITE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_ONLY_BINARY": ":all:",
        "REQUESTS_CA_BUNDLE": "/private/etc/ssl/cert.pem",
        "PIP_CACHE_DIR": str(home / "pip-cache"),
        "NPM_CONFIG_CACHE": str(home / "npm-cache"),
        "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_DIRS": str(home / "config"),
    }


def prepare_audit(step: GateStep, home: Path) -> None:
    for filename in AUDIT_MANIFESTS.get(step.name, ()):
        source = step.cwd / filename
        if source.resolve() != source:
            raise ValueError("Audit manifests must be regular repository files")
        contents = source.read_text()
        if filename == "requirements.txt":
            for line in contents.splitlines():
                requirement = line.partition("#")[0].strip()
                if requirement and not re.fullmatch(
                    r"[a-zA-Z0-9][a-zA-Z0-9_.\-\[\],<>=!~*+ ]*", requirement
                ):
                    raise ValueError("Audit requires public package specifications")
        elif filename == "package-lock.json":
            for package in json.loads(contents)["packages"].values():
                if "resolved" in package:
                    url = urlsplit(package["resolved"])
                    if url.scheme != "https" or url.netloc != "registry.npmjs.org":
                        raise ValueError("Audit requires public registry lock entries")
        write_private_text(home / filename, contents, trusted_root=home)


def added_line_findings() -> set[tuple[str, int]]:
    locations: set[tuple[str, int]] = set()
    for option in (
        "--log-opts=origin/main..HEAD --diff-merges=first-parent --no-ext-diff",
        "--staged", "--pre-commit",
    ):
        result = subprocess.run(
            ["gitleaks", "git", "--redact=100", "--no-banner", "--exit-code", "42",
             "--report-format", "json", "--report-path", "-", option, "."],
            capture_output=True, check=False, timeout=90,
        )
        findings = json.loads(result.stdout)
        if (
            result.returncode not in (0, 42)
            or not isinstance(findings, list)
            or bool(findings) != (result.returncode == 42)
        ):
            raise ValueError("Invalid secret scanner response")
        for finding in findings:
            path, line = finding["File"], finding["StartLine"]
            if not isinstance(path, str) or not path or type(line) is not int or line < 1:
                raise ValueError("Invalid secret scanner location")
            locations.add((path, line))
    return locations


def scan_added_lines() -> int:
    try:
        locations = added_line_findings()
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("Added-line scan unavailable")
        return 1
    for path, line in sorted(locations):
        print(f"{json.dumps(path, ensure_ascii=True)[1:-1]}:{line}")
    print(f"Added-line findings: {len(locations)}")
    return int(bool(locations))


def build_steps(
    python_bin: str,
    repo_root: Path = ROOT,
    skip_online: bool = False,
    mkdocs_site_dir: Path | None = None,
) -> list[GateStep]:
    site_out = mkdocs_site_dir or (repo_root / ".gate/tmp-mkdocs-site")
    release_helper = [python_bin, str(repo_root / "scripts/local_ci_release.py")]
    crm_python = app_python(python_bin, repo_root, "crm")
    skip_reason = (
        "Online check skipped via --skip-online; unavailable evidence cannot pass the gate"
        if skip_online
        else None
    )

    lint_steps = [
        GateStep(
            name="sbom-generate-check",
            mode="lint",
            command=[python_bin, "tools/generate_sbom.py", "--check"],
            cwd=repo_root,
        ),
        GateStep(
            name="sbom-public-check",
            mode="lint",
            command=[
                python_bin,
                "tools/public_sbom.py",
                "--check",
                "sbom/octo-observability-demo.cdx.json",
            ],
            cwd=repo_root,
        ),
        GateStep(
            name="gitleaks",
            mode="lint",
            command=[python_bin, str(repo_root / "scripts/local_ci_gate.py"), "--scan-added-lines"],
            cwd=repo_root,
        ),
        GateStep(
            name="mkdocs-strict",
            mode="lint",
            command=[
                python_bin,
                "-m",
                "mkdocs",
                "build",
                "--strict",
                "--site-dir",
                str(site_out),
            ],
            cwd=repo_root,
            cleanup_paths=(site_out,),
        ),
        GateStep(
            name="pip-audit-shop",
            mode="lint",
            command=[
                python_bin,
                "-I",
                "-m",
                "pip_audit",
                "--strict",
                "-r",
                "requirements.txt",
            ],
            cwd=repo_root / "shop",
            online=True,
            skipped=skip_online,
            skip_reason=skip_reason,
        ),
        GateStep(
            name="pip-audit-crm",
            mode="lint",
            command=[
                python_bin,
                "-I",
                "-m",
                "pip_audit",
                "--strict",
                "-r",
                "requirements.txt",
            ],
            cwd=repo_root / "crm",
            online=True,
            skipped=skip_online,
            skip_reason=skip_reason,
        ),
        GateStep(
            name="go-vet-workflow-gateway",
            mode="lint",
            command=["go", "vet", "./..."],
            cwd=repo_root / "shop/services/workflow-gateway",
        ),
        *(
            GateStep(
                name=f"npm-audit-{name}", mode="lint",
                command=["npm", "audit", "--ignore-scripts", "--package-lock-only"],
                cwd=repo_root / directory, online=True,
                skipped=skip_online, skip_reason=skip_reason,
            )
            for name, directory in (("shop", "shop"), ("browser-runner", "services/browser-runner"))
        ),
        *(
            GateStep(name=name, mode="lint", command=[*release_helper, subcommand], cwd=repo_root)
            for name, subcommand in (
                ("release-matrix", "matrix"),
                ("ocir-source-selection", "source"),
                ("orm-archives", "archives"),
                ("orm-terraform-validate", "terraform"),
                ("trivy-source-inventory", "source-inventory"),
                ("trivy-source-vulnerabilities", "source-vulnerabilities"),
            )
        ),
        GateStep(
            name="tflint", mode="lint", command=["tflint", "--chdir=deploy/terraform", "--recursive"],
            cwd=repo_root,
        ),
        *(
            GateStep(name=name, mode="lint", command=[], cwd=repo_root, skipped=True, skip_reason=reason)
            for name, reason in HOSTED_ONLY.items()
        ),
    ]

    test_steps = [
        GateStep(
            name="pytest-contract",
            mode="test",
            command=[
                python_bin,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/",
                "--ignore=tests/e2e",
            ],
            cwd=repo_root,
            env={"PYTHONPATH": str(repo_root / "shop")},
        ),
        GateStep(
            name="pytest-docs-surface",
            mode="test",
            command=[
                python_bin,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "crm/tests/test_observability_guidance_surfaces.py",
            ],
            cwd=repo_root,
        ),
        GateStep(
            name="pytest-shop",
            mode="test",
            command=[
                python_bin,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests",
                "-m",
                "not integration and not e2e",
            ],
            cwd=repo_root / "shop",
        ),
        GateStep(
            name="pytest-crm",
            mode="test",
            command=[
                crm_python,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests",
            ],
            cwd=repo_root / "crm",
            env={"OCI_AUTH_MODE": "instance_principal"},
        ),
    ]

    for step_name, rel_dir in APP_TEST_DIRS:
        app_dir = repo_root / rel_dir
        if (app_dir / "tests").is_dir():
            app_bin = app_python(python_bin, repo_root, "genai") if rel_dir == "services/genai-studio" else python_bin
            test_steps.append(
                GateStep(
                    name=step_name,
                    mode="test",
                    command=[
                        app_bin,
                        "-m",
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        "tests",
                    ],
                    cwd=app_dir,
                )
            )

    test_steps.append(
        GateStep(
            name="go-test-workflow-gateway",
            mode="test",
            command=["go", "test", "-race", "./..."],
            cwd=repo_root / "shop/services/workflow-gateway",
        )
    )

    return [*lint_steps, *test_steps]


def app_python(fallback: str, repo_root: Path, app: str) -> str:
    primary = repo_root / ".gate/venv/bin/python"
    isolated = repo_root / ".gate/venv" / app / "bin/python"
    if fallback == str(primary) and os.access(isolated, os.X_OK):
        return str(isolated)
    return fallback


def select_steps(
    steps: list[GateStep], mode: str, selected_names: list[str] | None = None
) -> list[GateStep]:
    if mode in {"lint", "test"}:
        filtered = [step for step in steps if step.mode == mode]
    elif mode == "all":
        filtered = list(steps)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    if selected_names:
        mode_names = {step.name for step in filtered}
        invalid = [name for name in selected_names if name not in mode_names]
        if invalid:
            raise ValueError(
                f"Unknown or mode-incompatible step(s) for --mode {mode}: {', '.join(invalid)}"
            )
        wanted = set(selected_names)
        filtered = [step for step in filtered if step.name in wanted]

    if not filtered:
        raise ValueError(f"Empty step selection for --mode {mode}")
    return filtered


def git_status_lines(repo_root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = " ".join(result.stderr.strip().splitlines())[:240] or "unknown git error"
        raise RuntimeError(f"git status exited {result.returncode}: {stderr}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def build_isolated_env(
    repo_root: Path,
    extra_env: dict[str, str],
    home_dir: Path | None = None,
) -> dict[str, str]:
    gate_root = repo_root / ".gate"
    env: dict[str, str] = {
        key: os.environ[key] for key in ALLOWED_ENV_KEYS if key in os.environ
    }
    gate_venv_bin = gate_root / "venv/bin"
    env["PATH"] = os.pathsep.join(
        [str(gate_venv_bin), str(gate_root / "bin"), env.get("PATH", os.defpath)]
    )

    shared_paths = [
        str(repo_root / "services/cache/client"),
        str(repo_root / "services/async-worker/src"),
        str(repo_root / "tools/traffic-generator"),
    ]
    extra_copy = dict(extra_env)
    custom_py_path = extra_copy.pop("PYTHONPATH", "")
    py_path_entries = ([custom_py_path] if custom_py_path else []) + shared_paths

    resolved_home = str(home_dir) if home_dir is not None else str(gate_root / "home")
    env.update(
        HOME=resolved_home,
        OCI_AUTH_MODE="config",
        OCI_CONFIG_FILE="/dev/null",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        GOTOOLCHAIN="local",
        GOPROXY="off",
        GOSUMDB="off",
        PYTHONPATH=os.pathsep.join(py_path_entries),
        PIP_CACHE_DIR=str(gate_root / "pip-cache"),
        GOPATH=str(gate_root / "gopath"),
        GOMODCACHE=str(gate_root / "gomodcache"),
        GOCACHE=str(gate_root / "gocache"),
        npm_config_cache=str(gate_root / "npm-cache"),
    )
    env.update(extra_copy)
    return env


def execute_steps(
    steps: list[GateStep],
    output_dir: Path,
    repo_root: Path = ROOT,
    fail_fast: bool = True,
    enforce_clean_git: bool = False,
    allow_online: bool = False,
    timeout_seconds: int = 600,
) -> tuple[int, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    try:
        norm_out = _normalize_platform_root_alias(output_dir)
        norm_repo = _normalize_platform_root_alias(repo_root)
        log_trusted_root: Path | None = (
            repo_root if norm_out.is_relative_to(norm_repo) else None
        )
    except OSError:
        log_trusted_root = repo_root

    try:
        sandbox_bin = verify_sandbox_available()
    except RuntimeError as exc:
        reason = str(exc)
        for step in steps:
            results.append(
                {
                    "name": step.name,
                    "mode": step.mode,
                    "command": list(step.command),
                    "commands": step.all_commands(),
                    "cwd": str(step.cwd),
                    "status": "unavailable",
                    "exit_code": 1,
                    "duration_seconds": 0.0,
                    "reason": reason,
                }
            )
            print(f"[{step.name}] UNAVAILABLE ({reason})", flush=True)
            if fail_fast:
                break
        return 1, results

    baseline_git: list[str] = []
    if enforce_clean_git:
        try:
            baseline_git = git_status_lines(repo_root)
        except (RuntimeError, OSError) as exc:
            err_msg = f"Pre-step git cleanliness check failed: {exc}"
            for step in steps[:1]:
                results.append(
                    {
                        "name": step.name,
                        "mode": step.mode,
                        "command": list(step.command),
                        "commands": step.all_commands(),
                        "cwd": str(step.cwd),
                        "status": "failed",
                        "exit_code": 1,
                        "duration_seconds": 0.0,
                        "error": err_msg,
                    }
                )
                print(f"[{step.name}] FAILED ({err_msg})", flush=True)
            return 1, results

    overall_exit = 0

    for index, step in enumerate(steps):
        if step.skipped or (step.online and not allow_online):
            reason = step.skip_reason or (
                "Online step requires outbound network access; unavailable in default offline "
                "'(deny network*)' mode (pass --allow-online to run under outbound-permitted "
                "(inbound/bind denied) sandbox)"
            )
            record: dict[str, Any] = {
                "name": step.name,
                "mode": step.mode,
                "command": list(step.command),
                "commands": step.all_commands(),
                "cwd": str(step.cwd),
                "status": "unavailable",
                "exit_code": 1,
                "duration_seconds": 0.0,
                "reason": reason,
            }
            results.append(record)
            overall_exit = 1
            print(f"[{step.name}] UNAVAILABLE ({reason})", flush=True)
            if fail_fast:
                break
            continue

        log_path = output_dir / f"{index:02d}-{step.name}.log"
        sandbox_policy = (
            "credential-isolated advisory HTTPS"
            if (step.online and allow_online)
            else "network-denied (private Unix sockets only)"
            if step.name in {"tflint", "orm-terraform-validate"}
            else "network-denied"
        )
        started = time.monotonic()
        error_detail: str | None = None
        code = 0

        try:
            with tempfile.TemporaryDirectory(prefix="local-ci-", dir="/private/tmp") as temp_home:
                home = Path(temp_home)
                temp_dir = home / "tmp"
                temp_dir.mkdir(mode=0o700)
                env = build_isolated_env(
                    repo_root, step.env, home_dir=home
                )
                env["TMPDIR"] = str(temp_dir)
                command_cwd = step.cwd
                if step.online:
                    env.pop("PYTHONPATH", None)
                    env.update(build_audit_env(home))
                    command_cwd = home
                    env["PATH"] = os.pathsep.join(
                        [str(repo_root / ".gate/venv/bin"), "/opt/homebrew/bin",
                         "/usr/local/bin", "/usr/bin", "/bin"]
                    )
                    prepare_audit(step, home)
                profile = sandbox_profile_for_step(
                    step, allow_online=allow_online, repo_root=repo_root,
                    socket_dir=temp_dir if step.name in {"tflint", "orm-terraform-validate"} else None,
                )
                try:
                    stream_ctx = open_private_write(
                        log_path, trusted_root=log_trusted_root
                    )
                except OSError as exc:
                    code = 1
                    error_detail = (
                        f"Private log open failed: {type(exc).__name__}: {exc}"
                    )
                    stream_ctx = None
                if stream_ctx is not None:
                    with stream_ctx as stream:
                        for cmd in step.all_commands():
                            try:
                                proc = subprocess.run(
                                    [sandbox_bin, "-p", profile, *cmd],
                                    cwd=command_cwd,
                                    env=env,
                                    stdout=subprocess.PIPE if step.online else stream,
                                    stderr=subprocess.STDOUT,
                                    timeout=timeout_seconds,
                                    check=False,
                                    umask=0o077,
                                )
                                if step.online:
                                    stream.write(proc.stdout.decode("utf-8", errors="replace"))
                                code = proc.returncode
                            except subprocess.TimeoutExpired:
                                stream.write(
                                    f"\nStep timed out after {timeout_seconds}s\n"
                                )
                                code = 124
                                error_detail = (
                                    f"timed out after {timeout_seconds}s"
                                )
                            except OSError as exc:
                                stream.write(
                                    f"\nStep failed to start: {type(exc).__name__}: {exc}\n"
                                )
                                code = 127
                                error_detail = f"{type(exc).__name__}: {exc}"
                            if code != 0:
                                break
        except (OSError, ValueError, KeyError, TypeError) as exc:
            code = 1
            error_detail = f"Step preparation failed: {type(exc).__name__}"
        finally:
            for cleanup_target in step.cleanup_paths:
                if cleanup_target.is_dir():
                    shutil.rmtree(cleanup_target, ignore_errors=True)
                elif cleanup_target.exists():
                    cleanup_target.unlink(missing_ok=True)

        duration = round(time.monotonic() - started, 3)

        if enforce_clean_git:
            try:
                after_git = git_status_lines(repo_root)
                if after_git != baseline_git:
                    new_dirt = sorted(set(after_git) ^ set(baseline_git))
                    code = code or 1
                    error_detail = (
                        f"Git working tree dirty after {step.name}: {new_dirt}"
                    )
            except (RuntimeError, OSError) as exc:
                code = code or 1
                error_detail = (
                    f"Post-step git cleanliness check failed after {step.name}: {exc}"
                )

        status = "passed" if code == 0 else "unavailable" if code in (69, 127) else "failed"
        record = {
            "name": step.name,
            "mode": step.mode,
            "command": list(step.command),
            "commands": step.all_commands(),
            "cwd": str(step.cwd),
            "sandbox_policy": sandbox_policy,
            "status": status,
            "exit_code": code,
            "duration_seconds": duration,
            "log": log_path.name,
        }
        if error_detail:
            record["error"] = error_detail
        results.append(record)
        print(
            f"[{step.name}] {status.upper()} (rc={code}, {duration:.2f}s)",
            flush=True,
        )

        if code != 0:
            overall_exit = 1
            if fail_fast:
                break

    return overall_exit, results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("all", "test", "lint"),
        default="all",
        help="Gate subset to execute (default: all)",
    )
    parser.add_argument(
        "--step",
        action="append",
        dest="steps",
        help="Run only the named step(s) within the selected mode",
    )
    parser.add_argument(
        "--python",
        default=default_python(ROOT),
        help="Python interpreter for subprocess invocations (defaults to .gate/venv/bin/python or sys.executable)",
    )
    parser.add_argument(
        "--allow-online",
        action="store_true",
        help="Permit outbound network access (inbound/bind still denied) for online steps (mkdocs-strict, pip-audit-*)",
    )
    parser.add_argument(
        "--skip-online",
        action="store_true",
        help="Explicitly mark online checks unavailable (never produces a passed gate when online steps are selected)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running remaining steps after a failure instead of failing fast",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print selected steps and commands as JSON without executing",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=DEFAULT_RECEIPT,
        help="Path to write JSON execution receipt",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    all_steps = build_steps(
        python_bin=args.python,
        repo_root=ROOT,
        skip_online=args.skip_online,
    )
    try:
        selected = select_steps(all_steps, mode=args.mode, selected_names=args.steps)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.list:
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "python": args.python,
                    "allow_online": args.allow_online,
                    "skip_online": args.skip_online,
                    "steps": [step.to_dict() for step in selected],
                },
                indent=2,
            )
        )
        return 0

    with tempfile.TemporaryDirectory(prefix="mkdocs-site-") as tmp_mkdocs_root:
        runtime_steps = build_steps(
            python_bin=args.python,
            repo_root=ROOT,
            skip_online=args.skip_online,
            mkdocs_site_dir=Path(tmp_mkdocs_root) / "site",
        )
        selected_runtime = select_steps(
            runtime_steps, mode=args.mode, selected_names=args.steps
        )
        log_dir = args.receipt.parent / "logs" / args.mode
        exit_code, results = execute_steps(
            selected_runtime,
            output_dir=log_dir,
            repo_root=ROOT,
            fail_fast=not args.keep_going,
            enforce_clean_git=True,
            allow_online=args.allow_online and not args.skip_online,
        )

    all_passed = bool(results) and all(r["status"] == "passed" for r in results)
    if not all_passed:
        exit_code = exit_code or 1

    receipt = {
        "schema": "octo-observability-demo.local-ci/v1",
        "mode": args.mode,
        "python": args.python,
        "allow_online": args.allow_online,
        "skip_online": args.skip_online,
        "status": "passed" if (exit_code == 0 and all_passed) else "failed",
        "provider_verified": False,
        "release_accepted": False,
        "steps": results,
    }
    try:
        write_private_text(args.receipt, json.dumps(receipt, indent=2) + "\n")
    except OSError as exc:
        print(f"Receipt write failed: {exc}", file=sys.stderr)
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(scan_added_lines() if sys.argv[1:] == ["--scan-added-lines"] else main())

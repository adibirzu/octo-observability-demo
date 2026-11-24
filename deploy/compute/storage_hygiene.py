#!/usr/bin/env python3
"""Report host storage; clean only reviewed disposable storage with --apply."""

import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

DISPOSABLE = "octo.hygiene.disposable=true"
ALLOWED_FILES = ("*.tmp", "*.part", "*.log.*")


def run_commands(commands, apply, run):
    for command in commands:
        scope = (
            "host-wide"
            if command[0] in {"journalctl", "dnf", "apt-get"}
            else "disposable-container-storage"
        )
        print(json.dumps({"command": command, "scope": scope, "apply": apply}))
        if apply:
            run(command)


def clean_files(root, cutoff, pattern, apply):
    """One dedicated directory, no recursion, symlinks, mounts or DB extensions."""
    root = Path(root)
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError("cleanup root must not traverse symlinks")
    if not root.exists():
        return 0
    patterns = (pattern,) if isinstance(pattern, str) else pattern
    total = 0
    # dir_fd and O_NOFOLLOW keep a replaced directory/symlink outside this boundary.
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        device = os.fstat(fd).st_dev
        for name in os.listdir(fd):
            if (
                not any(fnmatch.fnmatch(name, allowed) for allowed in ALLOWED_FILES)
                or not any(fnmatch.fnmatch(name, selected) for selected in patterns)
                or name.endswith(
                    (
                        ".db",
                        ".sqlite",
                        ".sqlite3",
                        ".dbf",
                        ".sso",
                        ".p12",
                        ".pfx",
                        ".jks",
                        ".dmp",
                        ".dump",
                    )
                )
            ):
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_dev != device
                or info.st_mtime >= cutoff
                or info.st_nlink != 1
            ):
                continue
            total += info.st_size
            if apply:
                fresh = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if (
                    fresh.st_ino == info.st_ino
                    and fresh.st_nlink == 1
                    and fresh.st_mtime < cutoff
                    and stat.S_ISREG(fresh.st_mode)
                ):
                    os.unlink(name, dir_fd=fd)
    finally:
        os.close(fd)
    return total


def disposable_volumes(volumes, used):
    return sorted(
        v["Name"]
        for v in volumes
        if v["Name"].startswith("hygiene-scratch-")
        and (v.get("Labels") or {}).get("octo.hygiene.disposable") == "true"
        and v["Name"] not in used
    )


def checked(command):
    subprocess.run(command, check=True)


def read(command):
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def size_report():
    usage = shutil.disk_usage("/")
    print(
        json.dumps(
            {
                "filesystem_bytes": {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                }
            }
        )
    )
    for directory in [
        "/var/log/journal",
        "/var/cache/dnf",
        "/var/cache/apt",
        "/var/log/octo/hygiene",
        "/var/tmp/octo-hygiene",
    ]:
        if Path(directory).exists():
            print(read(["du", "-sk", directory]).strip())


def runtime_commands(runtime, days):
    commands = []
    # Dangling only; no system prune, container prune, --all or app-volume sweep.
    commands.append(
        [
            runtime,
            "image",
            "prune",
            "--force",
            "--filter",
            "label=" + DISPOSABLE,
            "--filter",
            "until=" + str(days * 24) + "h",
        ]
    )
    names = read(
        [
            runtime,
            "volume",
            "ls",
            "--filter",
            "label=" + DISPOSABLE,
            "--format",
            "{{.Name}}",
        ]
    ).splitlines()
    for name in names:
        if not name.startswith("hygiene-scratch-"):
            continue
        volume = json.loads(read([runtime, "volume", "inspect", name]))
        used = read(
            [
                runtime,
                "ps",
                "--all",
                "--filter",
                "volume=" + name,
                "--format",
                "{{.ID}}",
            ]
        ).strip()
        if disposable_volumes(volume, {name} if used else set()):
            commands.append([runtime, "volume", "rm", name])
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval", default="")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--runtime", choices=["docker", "podman"])
    args = parser.parse_args()
    if args.days < 7:
        parser.error("--days must be at least 7")
    if args.apply and args.approval != "cleanup-disposable-host-storage":
        parser.error(
            "--apply requires --approval cleanup-disposable-host-storage after operator GO"
        )
    if args.apply and os.geteuid() != 0:
        parser.error("apply requires root")
    size_report()
    commands = []
    if shutil.which("journalctl"):
        commands.append(["journalctl", "--vacuum-time=" + str(args.days) + "d"])
    if shutil.which("dnf"):
        commands.append(["dnf", "clean", "all"])
    elif shutil.which("apt-get"):
        commands.append(["apt-get", "clean"])
    runtimes = (
        [args.runtime]
        if args.runtime
        else [r for r in ("docker", "podman") if shutil.which(r)]
    )
    for runtime in runtimes:
        try:
            commands.extend(runtime_commands(runtime, args.days))
        except (subprocess.CalledProcessError, FileNotFoundError):
            if args.apply:
                raise
            print(json.dumps({"runtime_unavailable": runtime, "apply": False}))
    run_commands(commands, args.apply, checked)
    cutoff = time.time() - args.days * 86400
    for root, pattern in [
        ("/var/log/octo/hygiene", "*.log.*"),
        ("/var/tmp/octo-hygiene", ("*.tmp", "*.part")),
    ]:
        count = clean_files(root, cutoff, pattern, args.apply)
        print(
            json.dumps(
                {"directory": root, "eligible_bytes": count, "apply": args.apply}
            )
        )
    size_report()


if __name__ == "__main__":
    main()

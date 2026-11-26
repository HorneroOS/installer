#!/usr/bin/env python3
"""Fail before any disk change when the installer payload is unavailable.

Calamares' unpackfs stage reads the squashfs payload from the archiso
boot mount (``/run/archiso/bootmnt/...``). With ``copytoram`` active on
high-RAM machines, archiso copies the live system to RAM and unmounts
that mount, so unpackfs only fails *after* partitioning has already
destroyed the target disk. This preflight runs as the first exec step
and aborts the installation while it is still harmless.

Every ``source:`` entry of the unpackfs configuration must exist and,
for regular files, be non-empty. Exit code 0 means the payload is
usable; 1 aborts with an actionable message.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_CONF = Path("/etc/calamares/modules/unpackfs.conf")
SOURCE_RE = re.compile(r"^\s*-\s*source:\s*(\S+)\s*$", re.MULTILINE)


def unpack_sources(conf_text: str) -> list[str]:
    return SOURCE_RE.findall(conf_text)


def missing_sources(conf: Path, root: Path) -> list[str]:
    if not conf.is_file():
        return [f"unpackfs configuration not found: {conf}"]
    missing: list[str] = []
    for source in unpack_sources(conf.read_text(encoding="utf-8")):
        candidate = Path(root, source.lstrip("/"))
        if candidate.is_dir():
            continue
        if not candidate.is_file() or candidate.stat().st_size == 0:
            missing.append(source)
    return missing


OFFLINE_MARKER = Path("/run/hornero-installer/offline-mode")
OFFLINE_REPO = Path("/run/archiso/bootmnt/hornero/x86_64/offline-repo")


def offline_repo_errors(root: Path) -> list[str]:
    """Fail before partitioning when offline mode lacks its repo."""
    marker = root / OFFLINE_MARKER.relative_to("/")
    if not marker.is_file():
        return []
    repo = root / OFFLINE_REPO.relative_to("/")
    errors: list[str] = []
    import json as _json

    if not (repo / "hornero-offline.db.tar.gz").is_file():
        errors.append("offline pacman database is missing")
    manifest_path = repo / "offline-manifest.json"
    if not manifest_path.is_file():
        errors.append("offline repository manifest is missing")
        return errors
    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        return [f"offline repository manifest is unreadable: {error}"]
    for entry in manifest.get("packages") or []:
        artifact = repo / entry["file"]
        if not artifact.is_file() or artifact.stat().st_size != entry["size"]:
            errors.append(f"offline package missing or truncated: {entry['file']}")
    return errors


def preflight_environment(root: Path, *, min_ram_mib: int = 2048) -> dict:
    """Inspect firmware mode (UEFI/BIOS), RAM, and AC/battery power status."""
    firmware = "uefi" if (root / "sys/firmware/efi").is_dir() else "bios"
    ram_mib: int | None = None
    warnings: list[str] = []
    errors: list[str] = []

    meminfo = root / "proc/meminfo"
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    ram_mib = int(parts[1]) // 1024
                break
    if ram_mib is not None:
        if ram_mib < min_ram_mib:
            errors.append(
                f"available RAM ({ram_mib} MiB) is below minimum ({min_ram_mib} MiB)"
            )
        elif ram_mib < 4096:
            warnings.append(
                f"available RAM ({ram_mib} MiB) is below recommended 4096 MiB"
            )

    on_battery = False
    power_dir = root / "sys/class/power_supply"
    if power_dir.is_dir():
        for entry in sorted(power_dir.iterdir()):
            status_file = entry / "status"
            if status_file.is_file():
                status = status_file.read_text(encoding="utf-8", errors="replace").strip()
                if status.lower() == "discharging":
                    on_battery = True
                    warnings.append(
                        "system is running on battery power; connect AC adapter to avoid power loss during installation"
                    )
                    break

    return {
        "firmware": firmware,
        "ramMiB": ram_mib,
        "onBattery": on_battery,
        "warnings": warnings,
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    conf = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONF
    root = Path(argv[2]) if len(argv) > 2 else Path("/")
    env = preflight_environment(root)
    for warning in env["warnings"]:
        print(f"HorneroOS installer preflight warning: {warning}", file=sys.stderr)
    offline_errors = offline_repo_errors(root)
    for error in offline_errors:
        print(
            "HorneroOS installer preflight: offline installation was "
            f"requested but {error}. Installation was aborted before "
            "any disk change. Reconnect to the internet or re-create "
            "the USB medium from an ISO built with offline support.",
            file=sys.stderr,
        )
    if offline_errors:
        return 1
    missing = missing_sources(conf, root)
    if missing:
        for source in missing:
            print(
                "HorneroOS installer preflight: installation payload is "
                f"unavailable: {source}. The USB payload could not be "
                "read (this happens when the live system was copied to "
                "RAM and the boot device was unmounted). Installation "
                "was aborted before any disk change. Reboot and try "
                "again; if it persists, re-create the USB medium.",
                file=sys.stderr,
            )
        return 1
    print("HorneroOS installer preflight: installation payload available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

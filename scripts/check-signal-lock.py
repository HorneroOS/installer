#!/usr/bin/env python3
"""Check that installer.lock.yaml pins a Signal-era product before an ISO build.

The preview32 ISO shipped a pre-Signal live session because the lock still
pinned pre-Signal AUR packages (installer#101). This gate fails when any
Hornero package is below its Signal floor or a retired Material-era package
is still pinned. build-iso.sh runs it; set HORNEROS_ALLOW_PRE_SIGNAL_LOCK=1 to
build a deliberately old image (never for a release).

Usage: scripts/check-signal-lock.py [--lock installer.lock.yaml]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# First release of each package built on Hornero Signal (RELEASE-PLAN:
# config 0.4.0, shell 1.3.0, greeter 1.1.0, horneroctl 0.2.0_preview46).
SIGNAL_FLOOR = {
    "hornero-config": "0.4.0",
    "hornero-shell": "1.3.0",
    "hornero-greeter": "1.1.0",
    "horneroctl-bin": "0.2.0_preview46",
}
# Material-era packages the Signal shell no longer needs.
RETIRED = ("python-materialyoucolor", "ttf-rubik-vf", "ttf-material-symbols-variable")


def version_key(version: str) -> tuple[int, ...]:
    """Compare pkgver[-pkgrel] numerically; '0.2.0_preview46' sorts as 0.2.0.46."""
    pkgver = version.rsplit("-", 1)[0]
    return tuple(int(part) for part in re.findall(r"\d+", pkgver))


def problems(lock: dict) -> list[str]:
    packages = lock.get("aur", {}).get("packages", {})
    found = []
    for name, floor in SIGNAL_FLOOR.items():
        entry = packages.get(name)
        if entry is None:
            found.append(f"{name} is not pinned (Signal floor {floor})")
        elif version_key(entry["version"]) < version_key(floor):
            found.append(f"{name} {entry['version']} is below the Signal floor {floor}")
    for name in RETIRED:
        if name in packages:
            found.append(f"{name} is a retired Material-era package and must not be pinned")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "installer.lock.yaml")
    args = parser.parse_args()
    lock = yaml.safe_load(args.lock.read_text(encoding="utf-8"))
    found = problems(lock)
    for line in found:
        print(f"signal-lock: {line}", file=sys.stderr)
    if found:
        print("signal-lock: refresh installer.lock.yaml per docs/release-iso.md", file=sys.stderr)
        return 1
    print("signal-lock: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

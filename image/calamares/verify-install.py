#!/usr/bin/env python3
"""Verify the installed target before Calamares may report success.

"All done" must mean the target can actually boot: a generated GRUB
configuration, a kernel image, and its initramfs must exist in the
target, a real user must have been created, the target must identify
itself, and no installer-only package repository may remain enabled.
This runs after the bootloader step and before umount; any problem
fails the installation instead of presenting a false success.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def verify_install(root: Path) -> list[str]:
    problems: list[str] = []

    def require_file(rel: str, what: str) -> None:
        path = root / rel
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f"missing or empty {what}: {rel}")

    require_file("boot/grub/grub.cfg", "GRUB configuration")
    require_file("boot/vmlinuz-linux", "kernel image")
    require_file("boot/initramfs-linux.img", "initramfs")

    os_release = root / "etc/os-release"
    if not os_release.is_file() or "ID=" not in os_release.read_text(
        encoding="utf-8", errors="replace"
    ):
        problems.append("missing distribution identity: etc/os-release")

    passwd = root / "etc/passwd"
    has_user = False
    if passwd.is_file():
        for line in passwd.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) >= 1000:
                has_user = True
                break
    if not has_user:
        problems.append("no regular user (uid >= 1000) in etc/passwd")

    pacman_conf = root / "etc/pacman.conf"
    if pacman_conf.is_file() and "hornero-installer" in pacman_conf.read_text(
        encoding="utf-8", errors="replace"
    ):
        problems.append("installer-only repository still enabled in etc/pacman.conf")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Installed target root")
    args = parser.parse_args()
    problems = verify_install(Path(args.root))
    for problem in problems:
        print(f"verify-install: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("verify-install: target has GRUB config, kernel, initramfs, user, identity; no installer repo left enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

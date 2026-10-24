#!/usr/bin/env python3
"""Remove the temporary install repository and restore normal Arch mirrors."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


LOCAL_INCLUDES = {
    "Include = /etc/pacman.d/hornero-installer.conf",
    "Include = /etc/pacman.d/hornero-installer-mirrorlist.conf",
}
REPOSITORIES = {"[core]", "[extra]"}
NORMAL_MIRROR = "Include = /etc/pacman.d/mirrorlist"


def cleanup(root: Path) -> None:
    root = root.resolve(strict=True)
    pacman_conf = root / "etc/pacman.conf"
    if pacman_conf.is_symlink() or not pacman_conf.is_file():
        raise ValueError("target pacman.conf is missing or is not a regular file")

    original = pacman_conf.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    section = ""
    for line in original:
        if line in LOCAL_INCLUDES:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            output.append(line)
            if section in REPOSITORIES:
                output.append(NORMAL_MIRROR)
            continue
        if section in REPOSITORIES and line == NORMAL_MIRROR:
            continue
        output.append(line)

    temporary = pacman_conf.with_name(".pacman.conf.hornero-tmp")
    if temporary.is_symlink():
        raise ValueError("temporary pacman.conf path must not be a symlink")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary, pacman_conf)
    (root / "etc/pacman.d/hornero-installer.conf").unlink(missing_ok=True)
    (root / "etc/pacman.d/hornero-installer-mirrorlist.conf").unlink(missing_ok=True)
    (root / "usr/lib/hornero-installer/cleanup-package-source.py").unlink(missing_ok=True)
    try:
        (root / "usr/lib/hornero-installer").rmdir()
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="target root (used by tests)")
    args = parser.parse_args()
    cleanup(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

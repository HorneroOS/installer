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
    pacman_conf = root / "etc/pacman.conf"
    original = pacman_conf.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    section = ""
    restored: set[str] = set()
    removed_includes: set[str] = set()
    for line in original:
        if line in LOCAL_INCLUDES:
            removed_includes.add(line)
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            output.append(line)
            if section in REPOSITORIES:
                output.append(NORMAL_MIRROR)
                restored.add(section)
            continue
        output.append(line)
    if restored != REPOSITORIES or removed_includes != LOCAL_INCLUDES:
        raise ValueError(
            "pacman.conf did not contain the expected temporary repository configuration "
            f"(repositories={sorted(restored)}, includes={sorted(removed_includes)})"
        )
    temporary = pacman_conf.with_name(".pacman.conf.hornero-tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary, pacman_conf)
    (root / "etc/pacman.d/hornero-installer.conf").unlink(missing_ok=True)
    (root / "etc/pacman.d/hornero-installer-mirrorlist.conf").unlink(missing_ok=True)
    (root / "usr/lib/hornero-installer/cleanup-package-source.py").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="target root (used by tests)")
    args = parser.parse_args()
    cleanup(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Seed the factory snapper config when the snapshots capability landed.

Runs dontChroot against the installed target. The opt-in `snapshots`
capability (HorneroOS/hornero editions catalogue, hornero#179) is the
only path that installs snapper; this step writes
/etc/snapper/configs/root only when the target proves every piece
the recovery contract needs:

- snapper is installed in the target (capability selected),
- the target root is Btrfs (per its own fstab), and
- the top-level /.snapshots store exists (fresh-install layout).

Anything else is an explicit no-op: a default install must never
gain a snapper config that pretends an OS rollback backend exists.
An existing admin config is never overwritten. Writing this file
does not flip HorneroOS's reported snapshot backend: that stays
"none" until the disposable-VM restore acceptance in
docs/SNAPSHOT_BACKEND_CONTRACT.md passes.
"""

from __future__ import annotations

import argparse
import stat
from pathlib import Path

FACTORY_CONFIG = """\
# HorneroOS factory snapper configuration for the root subvolume.
# Written at install time because the opt-in snapshots capability
# was selected. This file configures snapper's timeline/retention;
# its presence is not proof that an OS restore has been validated
# (see docs/SNAPSHOT_BACKEND_CONTRACT.md in HorneroOS/hornero).
# Home is never part of this config: restores cover root only.

SUBVOLUME="/"
FSTYPE="btrfs"

# snap-pac creates pre/post pairs around pacman transactions.
# Keep recent pairs, bound everything: an unbounded snapshot store
# eventually fills the disk it was meant to protect.
NUMBER_CLEANUP="yes"
NUMBER_MIN_AGE="1800"
NUMBER_LIMIT="10"
NUMBER_LIMIT_IMPORTANT="5"

TIMELINE_CREATE="yes"
TIMELINE_CLEANUP="yes"
TIMELINE_MIN_AGE="1800"
TIMELINE_LIMIT_HOURLY="5"
TIMELINE_LIMIT_DAILY="7"
TIMELINE_LIMIT_WEEKLY="0"
TIMELINE_LIMIT_MONTHLY="0"
TIMELINE_LIMIT_YEARLY="0"

EMPTY_PRE_POST_CLEANUP="yes"
EMPTY_PRE_POST_MIN_AGE="1800"

ALLOW_USERS=""
ALLOW_GROUPS=""
SYNC_ACL="no"
BACKGROUND_COMPARISON="yes"
SPACE_LIMIT="0.5"
FREE_LIMIT="0.2"
"""


def _fstab_facts(fstab: Path) -> tuple[str, bool]:
    """(root fstype, has /.snapshots mount) from the target fstab."""
    fstype = ""
    store = False
    try:
        lines = fstab.read_text(encoding="utf-8").splitlines()
    except OSError:
        return fstype, store
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 3:
            continue
        if fields[1] == "/":
            fstype = fields[2]
        if fields[1] == "/.snapshots":
            store = True
    return fstype, store


def _reject_symlink_components(root: Path, relative_parts: tuple[str, ...]) -> None:
    current = root
    for component in relative_parts:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in target snapper config path: {current}")


def configure_recovery(root: Path) -> bool:
    """Write the factory config when the target is recovery-ready.

    Returns True when the file was written, False for every no-op
    (backend pieces absent, or an admin config already exists).
    """
    root = root.resolve()
    if not (root / "usr/bin/snapper").is_file():
        return False
    fstype, store = _fstab_facts(root / "etc/fstab")
    if fstype != "btrfs" or not store:
        return False

    destination = root / "etc/snapper/configs/root"
    try:
        info = destination.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Target snapper config is not a regular file: {destination}")
        return False  # admin-owned config: never overwrite

    _reject_symlink_components(root, ("etc", "snapper", "configs", "root"))
    for directory in (root / "etc/snapper", destination.parent):
        try:
            directory.mkdir(mode=0o755)
        except FileExistsError:
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError(f"Target snapper config parent is not a directory: {directory}")
    destination.write_text(FACTORY_CONFIG, encoding="utf-8")
    destination.chmod(0o644)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    args = parser.parse_args()
    if configure_recovery(args.root.resolve()):
        print("Seeded factory snapper config for the snapshots capability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

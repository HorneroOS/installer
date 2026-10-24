#!/usr/bin/env python3
"""Seed the selected user's Exo helper from the installed Hornero defaults."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
from pathlib import Path


def configure_user_defaults(root: Path) -> None:
    root = root.resolve()
    source = root / "etc/xdg/xfce4/helpers.rc"
    if not source.is_file():
        raise FileNotFoundError(f"Hornero Exo helper defaults are missing: {source}")

    passwd = root / "etc/passwd"
    if not passwd.is_file():
        raise FileNotFoundError(f"Target passwd database is missing: {passwd}")

    users: list[tuple[Path, int, int]] = []
    for line in passwd.read_text(encoding="utf-8").splitlines():
        fields = line.split(":")
        if len(fields) < 7:
            continue
        try:
            uid, gid = int(fields[2]), int(fields[3])
        except ValueError:
            continue
        home = fields[5]
        if uid < 1000 or not home.startswith("/home/"):
            continue
        home_parts = home.split("/")[1:]
        if any(part in {"", ".", ".."} for part in home_parts):
            raise ValueError(f"User home has unsafe path components: {home}")
        target_home = root.joinpath(*home_parts)
        try:
            target_home.relative_to(root)
        except ValueError as error:
            raise ValueError(f"User home escapes target root: {home}") from error
        users.append((target_home, uid, gid))

    if not users:
        raise ValueError("Calamares did not create a regular user under /home")

    for home, uid, gid in users:
        config_home = home / ".config"
        destination = config_home / "xfce4/helpers.rc"
        # dontChroot runs this script as root against the installed target.
        # Reject symlinks in every existing component so a reused target
        # cannot redirect the write outside its own filesystem tree.
        current = root
        for component in home.relative_to(root).parts + (".config", "xfce4", "helpers.rc"):
            current = current / component
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"Refusing symlink in target user config path: {current}")
        for directory in (home, config_home, destination.parent):
            try:
                directory.mkdir(mode=0o755)
            except FileExistsError:
                if not directory.is_dir() or directory.is_symlink():
                    raise ValueError(f"Target user config parent is not a directory: {directory}")
            else:
                if os.geteuid() == 0:
                    os.chown(directory, uid, gid)
            if directory in (config_home, destination.parent) and os.geteuid() == 0:
                os.chown(directory, uid, gid)
        try:
            destination_info = destination.lstat()
        except FileNotFoundError:
            destination_info = None
        if destination_info is not None:
            if not stat.S_ISREG(destination_info.st_mode):
                raise ValueError(f"Target user helper config is not a regular file: {destination}")
            if os.geteuid() == 0:
                os.chown(destination, uid, gid)
            continue
        shutil.copyfile(source, destination)
        destination.chmod(0o644)
        if os.geteuid() == 0:
            os.chown(destination, uid, gid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    args = parser.parse_args()
    configure_user_defaults(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

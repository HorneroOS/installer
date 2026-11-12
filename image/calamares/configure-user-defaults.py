#!/usr/bin/env python3
"""Seed the selected user's Exo helper from the installed Hornero defaults.

Also seeds the recorded Studio selection (HorneroOS/installer#36): when the
installed system profile carries a `studioSelection`, it is translated to
`~/.config/hornero/studio-selection.json`, the exact file `horneroctl studio
selection show` reads. This is a record-only handoff: nothing is downloaded
or installed here, and manual opt-in applications (for example the
experimental ArtCraft Launcher) stay uninstalled until the user acts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
from pathlib import Path


def _studio_selection_from_profile(root: Path) -> dict | None:
    profile_path = root / "usr/lib/hornero/system-profile.json"
    if not profile_path.is_file():
        return None
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    edition = profile.get("edition") if isinstance(profile, dict) else None
    selection = edition.get("studioSelection") if isinstance(edition, dict) else None
    if not isinstance(selection, dict):
        return None

    def _ids(key: str) -> list[str]:
        value = selection.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"Installed Studio selection has invalid {key}: {value!r}")
        return list(value)

    return {
        "schemaVersion": 1,
        "specializations": _ids("specializations"),
        "applications": _ids("applications"),
    }


def _seed_studio_selection(root: Path, home: Path, uid: int, gid: int, selection: dict) -> None:
    hornero_dir = home / ".config" / "hornero"
    destination = hornero_dir / "studio-selection.json"
    current = root
    for component in home.relative_to(root).parts + (".config", "hornero", "studio-selection.json"):
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in target Studio selection path: {current}")
    for directory in (hornero_dir,):
        try:
            directory.mkdir(mode=0o755)
        except FileExistsError:
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError(f"Target Studio selection parent is not a directory: {directory}")
        if os.geteuid() == 0:
            os.chown(directory, uid, gid)
    try:
        info = destination.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Target Studio selection is not a regular file: {destination}")
        return  # Never overwrite a selection the user already recorded.
    destination.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.chmod(0o644)
    if os.geteuid() == 0:
        os.chown(destination, uid, gid)


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
        else:
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
            if os.geteuid() == 0:
                os.chown(destination, uid, gid)
        selection = _studio_selection_from_profile(root)
        if selection is not None:
            _seed_studio_selection(root, home, uid, gid, selection)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    args = parser.parse_args()
    configure_user_defaults(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

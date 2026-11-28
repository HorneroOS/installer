#!/usr/bin/env python3
"""Seed the selected user's Exo helper from the installed Hornero defaults.

Also seeds:
- Studio selection (HorneroOS/installer#36): `~/.config/hornero/studio-selection.json`
- Appearance (HorneroOS/installer PR-B): `~/.config/hornero/appearance.json`
- First-boot Hornero Apps onboarding queue (HorneroOS/installer#134):
  when `installation-plan.json` or `system-profile.json` records selected
  `workstationProfiles` or `deferredApps`, seeds
  `~/.config/hornero/store-onboarding-queue.json` matching the exact
  `horneroctl store queue` JSON schema (`{"items": [{"id": ..., "backend": ...}]}`).

All handoffs are record-only and symlink-safe: nothing is downloaded or
installed here, existing user files are never overwritten, and proprietary
software is never silently queued or installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
from pathlib import Path

APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _load_json_dict(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _seed_user_json(
    root: Path,
    home: Path,
    uid: int,
    gid: int,
    filename: str,
    payload: dict,
    label: str,
) -> None:
    hornero_dir = home / ".config" / "hornero"
    destination = hornero_dir / filename
    current = root
    for component in home.relative_to(root).parts + (".config", "hornero", filename):
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in target {label} path: {current}")
    try:
        hornero_dir.mkdir(mode=0o755)
    except FileExistsError:
        if not hornero_dir.is_dir() or hornero_dir.is_symlink():
            raise ValueError(f"Target {label} parent is not a directory: {hornero_dir}")
    if os.geteuid() == 0:
        os.chown(hornero_dir, uid, gid)
    try:
        info = destination.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Target {label} file is not a regular file: {destination}")
        return  # Never overwrite a file the user already recorded.
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.chmod(0o644)
    if os.geteuid() == 0:
        os.chown(destination, uid, gid)


def _studio_selection_from_profile(root: Path) -> dict | None:
    profile = _load_json_dict(root / "usr/lib/hornero/system-profile.json")
    if profile is None:
        return None
    edition = profile.get("edition")
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
    _seed_user_json(root, home, uid, gid, "studio-selection.json", selection, "Studio selection")


def _appearance_from_plan(root: Path) -> dict | None:
    """Appearance recorded in the installation plan, if any.

    Record-only handoff (same contract as the Studio selection):
    ~/.config/hornero/appearance.json is seeded once and never
    overwritten. Only the theme the pinned catalogue ships today
    (hornero-signal-night) can reach a plan; other themes are
    rejected by apply-system-plan.py, never silently seeded.
    """
    plan = _load_json_dict(root / "usr/lib/hornero/installation-plan.json")
    if plan is None:
        return None
    appearance = (plan.get("selection") or {}).get("appearance")
    if not isinstance(appearance, dict) or not appearance.get("theme"):
        return None
    return {
        "schemaVersion": 1,
        "theme": appearance["theme"],
        "shellPreset": appearance.get("shellPreset", "cockpit"),
    }


def _seed_appearance(root: Path, home: Path, uid: int, gid: int, appearance: dict) -> None:
    _seed_user_json(root, home, uid, gid, "appearance.json", appearance, "appearance")


def _load_workstation_profiles(root: Path, profiles_path: Path | None = None) -> dict[str, dict]:
    candidates: list[Path] = []
    if profiles_path is not None:
        candidates.append(profiles_path)
    else:
        here = Path(__file__).resolve().parent
        candidates.extend([
            here / "hornero-workstation-profiles.json",
            here / "modules" / "hornero-workstation-profiles.json",
            root / "usr/lib/hornero/workstation-profiles.json",
            root / "usr/share/hornero/workstation-profiles.json",
        ])
    for candidate in candidates:
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            profiles = data.get("profiles") if isinstance(data, dict) else None
            if not isinstance(profiles, list):
                raise ValueError(f"Invalid workstation profiles metadata: {candidate}")
            return {
                str(entry["id"]): entry
                for entry in profiles
                if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
            }
    raise FileNotFoundError("Workstation profiles metadata (hornero-workstation-profiles.json) not found")


def _validate_app_id(value: object, context: str) -> str:
    if not isinstance(value, str) or not APP_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid app id in {context}: {value!r}")
    return value


def _normalize_deferred_entries(raw: object, context: str) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{context} must be a list: {raw!r}")
    entries: list[dict[str, str]] = []
    for entry in raw:
        if isinstance(entry, str):
            entries.append({"id": _validate_app_id(entry, context), "backend": ""})
        elif isinstance(entry, dict):
            app_id = _validate_app_id(entry.get("id"), context)
            backend = entry.get("backend", "")
            if backend is None:
                backend = ""
            if not isinstance(backend, str):
                raise ValueError(f"Invalid backend in {context} for {app_id!r}: {backend!r}")
            entries.append({"id": app_id, "backend": backend})
        else:
            raise ValueError(f"Invalid deferred app entry in {context}: {entry!r}")
    return entries


def _store_queue_from_target(root: Path, profiles_path: Path | None = None) -> dict | None:
    """Build horneroctl store queue document from installation plan / system profile."""
    plan = _load_json_dict(root / "usr/lib/hornero/installation-plan.json")
    profile = _load_json_dict(root / "usr/lib/hornero/system-profile.json")

    selected_profiles: list[str] = []
    deferred_entries: list[dict[str, str]] = []

    sources: list[tuple[str, dict]] = []
    if plan is not None:
        sources.append(("installation-plan", plan))
        if isinstance(plan.get("selection"), dict):
            sources.append(("installation-plan.selection", plan["selection"]))
    if profile is not None:
        sources.append(("system-profile", profile))
        if isinstance(profile.get("edition"), dict):
            sources.append(("system-profile.edition", profile["edition"]))

    for label, obj in sources:
        raw_profiles = obj.get("workstationProfiles")
        if raw_profiles is not None:
            if not isinstance(raw_profiles, list):
                raise ValueError(f"{label}.workstationProfiles must be a list: {raw_profiles!r}")
            for pid in raw_profiles:
                valid_pid = _validate_app_id(pid, f"{label}.workstationProfiles")
                if valid_pid not in selected_profiles:
                    selected_profiles.append(valid_pid)
        deferred_entries.extend(
            _normalize_deferred_entries(obj.get("deferredApps"), f"{label}.deferredApps")
        )

    queue_items: list[dict[str, str]] = []
    by_id: dict[str, dict[str, str]] = {}

    def _add_item(app_id: str, backend: str) -> None:
        existing = by_id.get(app_id)
        if existing is None:
            item = {"id": app_id, "backend": backend}
            by_id[app_id] = item
            queue_items.append(item)
        elif not existing["backend"] and backend:
            existing["backend"] = backend

    if selected_profiles:
        profiles_by_id = _load_workstation_profiles(root, profiles_path=profiles_path)
        for pid in selected_profiles:
            entry = profiles_by_id.get(pid)
            if entry is None:
                raise ValueError(f"Unknown workstation profile in installation metadata: {pid!r}")
            # Expand strictly open-source deferred apps; proprietaryOptIn is never auto-queued.
            for app_entry in _normalize_deferred_entries(
                entry.get("deferredApps"), f"workstationProfile[{pid}].deferredApps"
            ):
                _add_item(app_entry["id"], app_entry["backend"])

    for entry in deferred_entries:
        _add_item(entry["id"], entry["backend"])

    if not queue_items:
        return None
    return {"items": queue_items}


def _seed_store_queue(root: Path, home: Path, uid: int, gid: int, queue_doc: dict) -> None:
    _seed_user_json(
        root,
        home,
        uid,
        gid,
        "store-onboarding-queue.json",
        queue_doc,
        "store onboarding queue",
    )


def configure_user_defaults(root: Path, profiles_path: Path | None = None) -> None:
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

    selection = _studio_selection_from_profile(root)
    appearance = _appearance_from_plan(root)
    store_queue = _store_queue_from_target(root, profiles_path=profiles_path)

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
        if selection is not None:
            _seed_studio_selection(root, home, uid, gid, selection)
        if appearance is not None:
            _seed_appearance(root, home, uid, gid, appearance)
        if store_queue is not None:
            _seed_store_queue(root, home, uid, gid, store_queue)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    args = parser.parse_args()
    configure_user_defaults(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

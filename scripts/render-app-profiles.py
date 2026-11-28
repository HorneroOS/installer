#!/usr/bin/env python3
"""Render declarative optional workstation profiles from the Hornero app catalog.

Reads the canonical ApplicationCatalog JSON (``catalog/apps.v1.json`` via
``--catalog`` for offline-safe deterministic builds) and generates
``image/calamares/modules/hornero-workstation-profiles.json``.

Safety invariants enforced fail-closed:
- All 9 canonical workstation profiles must be present.
- Every app in a profile's ``apps[]`` list must have ``is_open_source: true``
  and must never appear in ``proprietaryOptIn[]``.
- ``proprietaryOptIn[]`` applications are strictly separated and never
  auto-selected or included in ``archOfficialPackages[]`` / ``deferredApps[]``.
- Every rendered profile and optional group carries ``selected: false`` and
  ``critical: false`` so optional package failures never abort OS installation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "image" / "calamares" / "modules" / "hornero-workstation-profiles.json"

REQUIRED_PROFILE_IDS = (
    "minimal",
    "everyday-desktop",
    "work-productivity",
    "software-development",
    "ai-native-workstation",
    "creative-studio",
    "music-audio-production",
    "gaming",
    "education-research",
)

# Packages owned by the mandatory base/kernel/bootloader layer; optional
# workstation profiles must never duplicate them.
DEFAULT_BASE_PACKAGES = frozenset({
    "base",
    "linux",
    "linux-lts",
    "linux-zen",
    "linux-hardened",
    "linux-headers",
    "linux-lts-headers",
    "linux-zen-headers",
    "linux-hardened-headers",
    "linux-firmware",
    "grub",
    "systemd-boot",
    "efibootmgr",
})

# AUR-only packages cannot be installed by Calamares netinstall (pacman).
DEFAULT_EXCLUDED_PACKAGES = frozenset({"bottles", "vkbasalt", "lib32-vkbasalt"})


def load_catalog(path: Path) -> dict:
    """Load and validate the canonical ApplicationCatalog JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"App catalog must be a JSON object: {path}")
    if data.get("apiVersion") != "hornero.os/v1" or data.get("kind") != "ApplicationCatalog":
        raise ValueError(f"Unsupported app catalog header in {path}")
    if data.get("schemaVersion") != 1:
        raise ValueError(f"Unsupported app catalog schemaVersion: {data.get('schemaVersion')!r}")
    if not isinstance(data.get("profiles"), list) or not isinstance(data.get("apps"), list):
        raise ValueError(f"App catalog missing profiles or apps arrays: {path}")
    return data


def _arch_official_package(app: dict) -> str | None:
    """Return the official Arch package name when ``arch_native`` is recommended."""
    if app.get("recommended_source") != "arch_native":
        return None
    for source in app.get("sources") or []:
        if (
            source.get("backend") == "arch_native"
            and source.get("provenance") == "arch_official"
            and source.get("package_id")
        ):
            return str(source["package_id"])
    return None


def build_profiles_document(
    catalog: dict,
    *,
    base_packages: frozenset[str] | set[str] = DEFAULT_BASE_PACKAGES,
    excluded_packages: frozenset[str] | set[str] = DEFAULT_EXCLUDED_PACKAGES,
) -> dict:
    """Build deterministic workstation profile metadata from *catalog*."""
    apps_by_id: dict[str, dict] = {}
    for app in catalog["apps"]:
        app_id = app.get("id")
        if not isinstance(app_id, str) or not app_id:
            raise ValueError(f"Catalog app missing valid id: {app!r}")
        if app_id in apps_by_id:
            raise ValueError(f"Duplicate catalog app id: {app_id!r}")
        apps_by_id[app_id] = app

    profiles_by_id: dict[str, dict] = {}
    for profile in catalog["profiles"]:
        pid = profile.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"Catalog profile missing valid id: {profile!r}")
        if pid in profiles_by_id:
            raise ValueError(f"Duplicate catalog profile id: {pid!r}")
        profiles_by_id[pid] = profile

    missing_profiles = [pid for pid in REQUIRED_PROFILE_IDS if pid not in profiles_by_id]
    if missing_profiles:
        raise ValueError(f"App catalog missing required workstation profiles: {missing_profiles}")

    rendered_profiles: list[dict] = []
    for profile in catalog["profiles"]:
        pid = profile["id"]
        open_app_ids = list(profile.get("apps") or [])
        proprietary_ids = list(profile.get("proprietaryOptIn") or [])
        proprietary_set = set(proprietary_ids)

        arch_packages: list[str] = []
        seen_arch: set[str] = set()
        deferred_apps: list[dict[str, str]] = []
        verified_open_ids: list[str] = []

        for app_id in open_app_ids:
            if app_id in proprietary_set:
                raise ValueError(
                    f"Profile {pid!r} lists {app_id!r} in both apps[] and proprietaryOptIn[]"
                )
            app = apps_by_id.get(app_id)
            if app is None:
                raise ValueError(f"Profile {pid!r} references unknown app {app_id!r}")
            if app.get("is_open_source") is not True:
                raise ValueError(
                    f"Profile {pid!r} app {app_id!r} is not open-source; "
                    "non-free apps must live strictly in proprietaryOptIn[]"
                )
            if app.get("deprecated"):
                continue
            verified_open_ids.append(app_id)

            arch_pkg = _arch_official_package(app)
            if arch_pkg is not None:
                if (
                    arch_pkg not in base_packages
                    and arch_pkg not in excluded_packages
                    and arch_pkg not in seen_arch
                ):
                    seen_arch.add(arch_pkg)
                    arch_packages.append(arch_pkg)
            else:
                deferred_apps.append({
                    "id": app_id,
                    "backend": str(app.get("recommended_source") or ""),
                })

        verified_proprietary: list[str] = []
        for app_id in proprietary_ids:
            if app_id not in apps_by_id:
                raise ValueError(
                    f"Profile {pid!r} proprietaryOptIn references unknown app {app_id!r}"
                )
            verified_proprietary.append(app_id)

        rendered_profiles.append({
            "id": pid,
            "name": profile["name"],
            "name_es": profile.get("name_es", profile["name"]),
            "description": profile["description"],
            "description_es": profile.get("description_es", profile["description"]),
            "selected": False,
            "critical": False,
            "apps": verified_open_ids,
            "proprietaryOptIn": verified_proprietary,
            "archOfficialPackages": arch_packages,
            "deferredApps": deferred_apps,
        })

    return {
        "apiVersion": "hornero.os/v1",
        "kind": "WorkstationProfiles",
        "schemaVersion": 1,
        "catalogSchemaVersion": catalog["schemaVersion"],
        "catalogVerifiedAt": catalog.get("verifiedAt", ""),
        "defaultSelected": False,
        "critical": False,
        "profiles": rendered_profiles,
    }


def build_workstation_netinstall_group(
    catalog: dict,
    *,
    base_packages: frozenset[str] | set[str] = DEFAULT_BASE_PACKAGES,
    excluded_packages: frozenset[str] | set[str] = DEFAULT_EXCLUDED_PACKAGES,
) -> dict:
    """Build an optional, unticked Calamares netinstall group from *catalog*."""
    doc = build_profiles_document(
        catalog,
        base_packages=base_packages,
        excluded_packages=excluded_packages,
    )
    subgroups: list[dict] = []
    for profile in doc["profiles"]:
        packages = list(profile["archOfficialPackages"])
        if not packages:
            continue
        description = (
            f"{profile['description']} Installs open-source Arch official packages only "
            "(optional, non-critical). Flatpak, AppImage, WebApp, and guided tools "
            "are queued for first-boot review; proprietary apps are never included here."
        )
        subgroups.append({
            "name": f"Profile — {profile['name']}",
            "description": description,
            "selected": False,
            "critical": False,
            "packages": packages,
        })
    return {
        "name": "Workstation profiles (optional)",
        "description": (
            "Optional open-source workstation profiles from the Hornero application "
            "catalog. Unticked by default; proprietary software is never included."
        ),
        "selected": False,
        "expanded": False,
        "subgroups": subgroups,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(os.environ["HORNEROS_APP_CATALOG"])
        if os.environ.get("HORNEROS_APP_CATALOG")
        else None,
        help="path to canonical catalog/apps.v1.json (or set HORNEROS_APP_CATALOG)",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    if args.catalog is None:
        parser.error("--catalog (or HORNEROS_APP_CATALOG) is required")
    catalog = load_catalog(args.catalog.expanduser().resolve())
    document = build_profiles_document(catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"rendered {len(document['profiles'])} optional workstation profiles "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

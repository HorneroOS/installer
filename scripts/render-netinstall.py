#!/usr/bin/env python3
"""Render the Calamares netinstall groups from the pinned Hornero catalogue.

Every package below comes from HorneroOS/hornero editions/catalogue.yaml
at the revision pinned in installer.lock.yaml, resolved through the
canonical scripts/resolve-edition.py. Nothing is hand-listed here:

- Studio and Gaming groups are the resolver selections per
  specialization. The resolver already excludes proprietary payloads
  from group selections, so no group installs them.
- Proprietary applications appear only as individual, explicitly
  ticked items carrying a licence note (never inside a group).
- Reference-only applications (no Arch package) and manual-only
  applications (vendor-installed, e.g. ArtCraft Launcher) never appear.
- Capabilities are the catalogue capability package lists.
- Individual applications are the curated open-source catalogue
  applications, one tickable item each.
- GPU drivers are NOT rendered: the pinned catalogue ships no GPU
  package provenance (no nvidia/mesa/vulkan driver entries), so any
  GPU group today would be a UI that installs nothing honest. Tracked
  as a gap until HorneroOS/hornero models GPU provenance.

All groups default to unticked: an untouched netinstall page installs
exactly the edition chosen in packagechooser, nothing more.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "installer.lock.yaml"
OUTPUT = ROOT / "image" / "calamares" / "modules" / "netinstall.conf"
# Packages that belong to the mandatory edition/kernel/bootloader base:
# netinstall must never offer to add or duplicate them.
BASE_PACKAGES = {
    "base", "linux", "linux-lts", "linux-zen", "linux-hardened",
    "linux-headers", "linux-lts-headers", "linux-zen-headers",
    "linux-hardened-headers", "linux-firmware", "grub",
    "systemd-boot", "efibootmgr",
}


def _catalogue_renderer():
    spec = importlib.util.spec_from_file_location(
        "render_installer_catalogue", Path(__file__).with_name("render-installer-catalogue.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve(root: Path, edition: str, specialization: str) -> dict:
    command = [
        "python3", str(root / "scripts" / "resolve-edition.py"), edition,
        "--specialization", specialization,
    ]
    return json.loads(subprocess.check_output(command, text=True))


def _leaf(name: str, description: str, packages: list[str]) -> dict:
    packages = [p for p in dict.fromkeys(packages) if p not in BASE_PACKAGES]
    if not packages:
        raise ValueError(f"netinstall group {name!r} would install nothing")
    return {
        "name": name,
        "description": description,
        "selected": False,
        "critical": False,
        "packages": packages,
    }


def build_groups(root: Path, catalogue: dict) -> list[dict]:
    groups: list[dict] = []

    studio_specs = catalogue.get("studioSpecializations") or {}
    if studio_specs:
        subgroups = []
        for spec_id, spec in studio_specs.items():
            selection = _resolve(root, "studio", spec_id)
            subgroups.append(_leaf(
                f"Studio — {spec['title']}",
                f"Open-source applications for {spec['title']} from the pinned catalogue. "
                "Proprietary applications are never installed by this group.",
                selection["packages"],
            ))
        groups.append({
            "name": "Studio specializations",
            "description": "Creative specializations from the pinned Hornero catalogue. Unticked by default.",
            "selected": False,
            "expanded": False,
            "subgroups": subgroups,
        })

    gaming_specs = catalogue.get("gamingSpecializations") or {}
    if gaming_specs:
        subgroups = []
        for spec_id, spec in gaming_specs.items():
            selection = _resolve(root, "gaming", spec_id)
            subgroups.append(_leaf(
                f"Gaming — {spec['title']}",
                f"Open-source gaming platform and applications for {spec['title']} from the pinned catalogue. "
                "Steam is never installed by this group.",
                selection["packages"],
            ))
        groups.append({
            "name": "Gaming",
            "description": "Gaming profiles from the pinned Hornero catalogue. Unticked by default.",
            "selected": False,
            "expanded": False,
            "subgroups": subgroups,
        })

    capabilities = catalogue.get("capabilities") or {}
    if capabilities:
        subgroups = [
            _leaf(
                f"Capability — {entry.get('title', cap_id)}",
                f"Catalogue capability {cap_id}. Packages already in the chosen edition are skipped by pacman.",
                entry.get("packages", []),
            )
            for cap_id, entry in capabilities.items()
            if entry.get("packages")
        ]
        if subgroups:
            groups.append({
                "name": "Capabilities",
                "description": "Optional system capabilities from the pinned catalogue. Unticked by default.",
                "selected": False,
                "expanded": False,
                "subgroups": subgroups,
            })

    # Individual curated applications: open-source, packaged, not
    # reference-only, not manual-only, not experimental launcher payloads.
    manual_ids: set[str] = set()
    proprietary_ids: set[str] = set()
    for edition, specs in (("studio", studio_specs), ("gaming", gaming_specs)):
        for spec_id in specs:
            selection = _resolve(root, edition, spec_id)
            manual_ids.update(selection.get("manualOptInRequired", []))
            proprietary_ids.update(selection.get("proprietaryOptInRequired", []))
    individual: dict[str, dict] = {}
    for apps_key in ("studioApplications", "gamingApplications"):
        for app_id, app in (catalogue.get(apps_key) or {}).items():
            if app_id in individual or app_id in manual_ids or app_id in proprietary_ids:
                continue
            if app.get("availability") == "reference-only" or app.get("experimental"):
                continue
            if not app.get("packages"):
                continue
            individual[app_id] = app
    if individual:
        subgroups = [
            _leaf(
                app.get("title", app_id),
                f"Individual catalogue application {app_id}. Unticked by default.",
                app["packages"],
            )
            for app_id, app in individual.items()
        ]
        groups.append({
            "name": "Individual applications",
            "description": "Curated open-source applications from the pinned catalogue, ticked one by one. Unticked by default.",
            "selected": False,
            "expanded": False,
            "subgroups": subgroups,
        })

    if proprietary_ids:
        subgroups = []
        for app_id in sorted(proprietary_ids):
            app = (catalogue.get("studioApplications") or {}).get(app_id) or \
                  (catalogue.get("gamingApplications") or {}).get(app_id)
            if app is None or not app.get("packages"):
                continue
            subgroups.append(_leaf(
                f"{app.get('title', app_id)} (proprietary)",
                f"Proprietary application {app.get('title', app_id)}: installed ONLY because you "
                "ticked this individual item. It is never installed by any group selection and is "
                "subject to its vendor licence/EULA, which HorneroOS does not grant.",
                app["packages"],
            ))
        if subgroups:
            groups.append({
                "name": "Proprietary applications (explicit opt-in only)",
                "description": "Each item installs only when ticked individually, with its licence note. Unticked by default.",
                "selected": False,
                "expanded": False,
                "subgroups": subgroups,
            })
    return groups


def render(root: Path, catalogue: dict) -> dict:
    return {
        "groupsUrl": "local",
        "required": False,
        "label": {"sidebar": "Additional software", "title": "Additional software"},
        "groups": build_groups(root, catalogue),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-source", type=Path, help="use a local Hornero checkout instead of the pinned source")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "hornero-installer")
    args = parser.parse_args()
    renderer = _catalogue_renderer()
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    root = renderer.load_product_root(lock, args.product_source, args.cache_dir.expanduser().absolute())
    catalogue = yaml.safe_load((root / "editions" / "catalogue.yaml").read_text(encoding="utf-8"))
    rendered = render(root, catalogue)
    header = (
        "# Generated by scripts/render-netinstall.py from the pinned\n"
        f"# HorneroOS/hornero catalogue ({lock['product']['revision']}); do not edit.\n"
        "# All groups are unticked by default. GPU driver groups are absent on\n"
        "# purpose: the pinned catalogue has no GPU package provenance yet.\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        header + yaml.safe_dump(rendered, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    leaves = []

    def collect(items):
        for item in items:
            if item.get("subgroups"):
                collect(item["subgroups"])
            else:
                leaves.append(item["name"])

    collect(rendered["groups"])
    print(f"rendered {len(rendered['groups'])} netinstall groups ({len(leaves)} tickable leaves) from Hornero {lock['product']['revision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

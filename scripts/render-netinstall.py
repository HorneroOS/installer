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
- AUR-only packages are NOT rendered: bottles, vkbasalt and
  lib32-vkbasalt exist only in the AUR (verified against Arch
  core/extra/multilib), and the target has no AUR helper, so
  offering them would tick a box that cannot install anything.
- GPU drivers are rendered only when the pinned catalogue ships
  both `gpuVendors` and complete `gpuProvenance` for every rendered
  package (HorneroOS/hornero#466, installer#115). A catalogue without
  them renders no GPU group from it; a catalogue with vendors but
  missing/incomplete provenance fails closed (ValueError) instead of
  rendering a group that installs something unprovenanced. AMD/Intel
  open-source groups may be pre-selected from a PCI probe (probe-gpu.py
  JSON); the NVIDIA proprietary item is never pre-selected.

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
# AUR-only: not in Arch core/extra/multilib and not in the local
# Hornero repository; the target pacman.conf has no AUR helper.
AUR_ONLY_PACKAGES = {"bottles", "vkbasalt", "lib32-vkbasalt"}

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


def _leaf(name: str, description: str, packages: list[str]) -> dict | None:
    packages = [
        p for p in dict.fromkeys(packages)
        if p not in BASE_PACKAGES and p not in AUR_ONLY_PACKAGES
    ]
    if not packages:
        return None
    return {
        "name": name,
        "description": description,
        "selected": False,
        "critical": False,
        "packages": packages,
    }


def build_gpu_groups(catalogue: dict, probe_vendors: list[str] | tuple = ()) -> list[dict]:
    """GPU groups from catalogue gpuVendors+gpuProvenance (fail-closed).

    No gpuVendors in the pinned catalogue -> no groups (dependency on
    the Hornero catalogue GPU provenance, hornero#466, plus a pin
    bump). Vendors present but any rendered package without complete
    provenance -> ValueError. AMD/Intel leaves are pre-selected only
    when the PCI probe reported that vendor; NVIDIA is an explicit
    top-level proprietary item, never pre-selected.
    """
    vendors = catalogue.get("gpuVendors")
    if not vendors:
        return []
    provenance = catalogue.get("gpuProvenance") or {}
    if not provenance:
        raise ValueError(
            "catalogue ships gpuVendors without gpuProvenance; refusing "
            "to render GPU groups without provenance (fail-closed)"
        )

    def require_provenance(packages: list[str], *, allow_proprietary: bool) -> None:
        for package in packages:
            entry = provenance.get(package)
            if not isinstance(entry, dict) or not entry.get("source") \
                    or not str(entry.get("sourceUrl", "")).startswith("https://") \
                    or not entry.get("licenses") \
                    or not entry.get("licenseClass"):
                raise ValueError(
                    f"GPU package {package!r} lacks complete gpuProvenance "
                    "(source/sourceUrl/licenses/licenseClass); refusing to render it"
                )
            if not allow_proprietary and entry.get("licenseClass") == "proprietary":
                raise ValueError(
                    f"GPU package {package!r} is proprietary inside an open-source GPU group"
                )

    groups: list[dict] = []
    subgroups: list[dict] = []
    for vendor_id in ("amd", "intel"):
        entry = vendors.get(vendor_id)
        if not entry:
            continue
        if entry.get("proprietary") or entry.get("explicitOptIn"):
            raise ValueError(
                f"gpuVendors.{vendor_id} must remain open-source and non-proprietary"
            )
        packages = list(entry.get("packages") or [])
        if not packages:
            raise ValueError(f"gpuVendors.{vendor_id} has no packages")
        require_provenance(packages, allow_proprietary=False)
        licences = sorted({lic for pkg in packages for lic in provenance[pkg]["licenses"]})
        subgroups.append({
            "name": f"GPU — {entry.get('title', vendor_id)}",
            "description": (
                f"Open-source GPU drivers for {vendor_id} from the pinned catalogue "
                f"(licences: {', '.join(licences)}). "
                + ("Pre-selected because the PCI probe detected this vendor; untick freely."
                   if vendor_id in probe_vendors else "Unticked by default.")
            ),
            "selected": vendor_id in probe_vendors,
            "critical": False,
            "packages": packages,
        })
    if subgroups:
        groups.append({
            "name": "GPU drivers (open-source)",
            "description": "Open-source GPU drivers by vendor from the pinned catalogue. Only a probe-detected vendor is pre-selected, and it stays editable.",
            "selected": False,
            "expanded": False,
            "subgroups": subgroups,
        })
    nvidia = vendors.get("nvidia")
    if nvidia:
        if not nvidia.get("proprietary") or not nvidia.get("explicitOptIn"):
            raise ValueError(
                "gpuVendors.nvidia must declare proprietary: true and explicitOptIn: true"
            )
        userspace = list(nvidia.get("packages") or [])
        dkms = nvidia.get("dkmsModule")
        packages = ([dkms] if dkms else []) + userspace
        if not packages:
            raise ValueError("gpuVendors.nvidia has no packages")
        require_provenance(packages, allow_proprietary=True)
        groups.append({
            "name": "NVIDIA GPU driver (proprietary)",
            "description": (
                "Proprietary NVIDIA userspace (nvidia-utils) with the nvidia-open-dkms "
                "kernel module, which builds against the installed kernel headers. "
                "Installed ONLY because you ticked this individual item: it is never "
                "pre-selected, never installed by any group, and is subject to the "
                "NVIDIA licence/EULA, which HorneroOS does not grant."
            ),
            "selected": False,
            "critical": False,
            "packages": packages,
        })
    return groups


def build_groups(root: Path, catalogue: dict, probe_vendors: list[str] | tuple = ()) -> list[dict]:
    groups: list[dict] = []

    studio_specs = catalogue.get("studioSpecializations") or {}
    if studio_specs:
        subgroups = []
        for spec_id, spec in studio_specs.items():
            selection = _resolve(root, "studio", spec_id)
            leaf = _leaf(
                f"Studio — {spec['title']}",
                f"Open-source applications for {spec['title']} from the pinned catalogue. "
                "Proprietary applications are never installed by this group.",
                selection["packages"],
            )
            if leaf:
                subgroups.append(leaf)
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
            leaf = _leaf(
                f"Gaming — {spec['title']}",
                f"Open-source gaming platform and applications for {spec['title']} from the pinned catalogue. "
                "Steam is never installed by this group.",
                selection["packages"],
            )
            if leaf:
                subgroups.append(leaf)
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
            leaf for cap_id, entry in capabilities.items()
            if entry.get("packages")
            if (leaf := _leaf(
                f"Capability — {entry.get('title', cap_id)}",
                f"Catalogue capability {cap_id}. Packages already in the chosen edition are skipped by pacman.",
                entry.get("packages", []),
            ))
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
            leaf for app_id, app in individual.items()
            if (leaf := _leaf(
                app.get("title", app_id),
                f"Individual catalogue application {app_id}. Unticked by default.",
                app["packages"],
            ))
        ]
        groups.append({
            "name": "Individual applications",
            "description": "Curated open-source applications from the pinned catalogue, ticked one by one. Unticked by default.",
            "selected": False,
            "expanded": False,
            "subgroups": subgroups,
        })

    # Proprietary apps are top-level items, not subgroups of a
    # checkable parent: ticking a parent must never install them.
    for app_id in sorted(proprietary_ids):
        app = (catalogue.get("studioApplications") or {}).get(app_id) or \
              (catalogue.get("gamingApplications") or {}).get(app_id)
        if app is None or not app.get("packages"):
            continue
        leaf = _leaf(
            f"{app.get('title', app_id)} (proprietary)",
            f"Proprietary application {app.get('title', app_id)}: installed ONLY because you "
            "ticked this individual item. It is never installed by any group selection and is "
            "subject to its vendor licence/EULA, which HorneroOS does not grant.",
            app["packages"],
        )
        if leaf:
            groups.append(leaf)
    groups.extend(build_gpu_groups(catalogue, probe_vendors))
    return groups


def render(root: Path, catalogue: dict, probe_vendors: list[str] | tuple = ()) -> dict:
    return {
        "groupsUrl": "local",
        "required": False,
        "label": {"sidebar": "Additional software", "title": "Additional software"},
        "groups": build_groups(root, catalogue, probe_vendors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-source", type=Path, help="use a local Hornero checkout instead of the pinned source")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "hornero-installer")
    parser.add_argument("--gpu-probe", type=Path, help="probe-gpu.py JSON; pre-selects detected AMD/Intel GPU groups (NVIDIA never)")
    args = parser.parse_args()
    probe_vendors: list[str] = []
    if args.gpu_probe:
        probe_vendors = list(json.loads(args.gpu_probe.read_text(encoding="utf-8")).get("vendors") or [])
    renderer = _catalogue_renderer()
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    root = renderer.load_product_root(lock, args.product_source, args.cache_dir.expanduser().absolute())
    catalogue = yaml.safe_load((root / "editions" / "catalogue.yaml").read_text(encoding="utf-8"))
    rendered = render(root, catalogue, probe_vendors)
    header = (
        "# Generated by scripts/render-netinstall.py from the pinned\n"
        f"# HorneroOS/hornero catalogue ({lock['product']['revision']}); do not edit.\n"
        "# All groups are unticked by default, except open-source GPU groups\n"
        "# pre-selected from a PCI probe at render time. GPU groups are absent\n"
        "# when the pinned catalogue ships no gpuVendors/gpuProvenance\n"
        "# (dependency: HorneroOS/hornero#466 + a catalogue pin bump).\n"
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

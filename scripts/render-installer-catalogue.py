#!/usr/bin/env python3
"""Render Calamares edition choices from the pinned Hornero product model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "installer.lock.yaml"
OUTPUT = ROOT / "image" / "calamares" / "modules" / "packagechooser.conf"
ALLOWED_MATURITIES = {"preview", "supported", "experimental"}
CHOICE_SCREENSHOTS = {
    "desktop-hyprland": "screenshots/desktop-hyprland.jpg",
    "desktop-niri": "screenshots/niri-experimental.svg",
}


def verify_product_source(root: Path, lock: dict) -> None:
    expected = lock["product"]
    for field, relative in (
        ("catalogueSha256", "editions/catalogue.yaml"),
        ("resolverSha256", "scripts/resolve-edition.py"),
    ):
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if digest != expected[field]:
            raise ValueError(
                f"product source {relative} does not match the locked Hornero revision "
                f"{expected['revision']}"
            )


def prepare_private_cache(path: Path) -> Path:
    """Create or validate a user-owned, private product-source cache."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise ValueError(f"cache directory must be a user-owned directory: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError(f"cache directory must not be accessible by other users: {path}")
    parent = path.parent.stat()
    if stat.S_IMODE(parent.st_mode) & 0o022 and not stat.S_IMODE(parent.st_mode) & stat.S_ISVTX:
        raise ValueError(f"cache parent must not be writable by other users: {path.parent}")
    return path


def load_product_root(lock: dict, source: Path | None, cache_dir: Path) -> Path:
    if source:
        root = source.resolve()
        verify_product_source(root, lock)
        return root
    url = lock["product"]["repository"].removesuffix(".git")
    revision = lock["product"]["revision"]
    archive_url = f"{url}/archive/{revision}.tar.gz"
    private_cache = prepare_private_cache(cache_dir)
    cache = private_cache / "product" / revision
    if cache.is_symlink():
        raise ValueError(f"cached product source must not be a symlink: {cache}")
    if cache.exists():
        verify_product_source(cache, lock)
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="hornero-installer-product-") as temp:
        archive = Path(temp) / "hornero.tar.gz"
        urllib.request.urlretrieve(archive_url, archive)
        unpacked = Path(temp) / "source"
        unpacked.mkdir()
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(unpacked), "--strip-components=1"], check=True)
        verify_product_source(unpacked, lock)
        shutil.copytree(unpacked, cache)
        return cache


def resolve(root: Path, edition: str, compositor: str | None) -> dict:
    command = ["python3", str(root / "scripts" / "resolve-edition.py"), edition, "--json"]
    if compositor:
        command += ["--compositor", compositor]
    return json.loads(subprocess.check_output(command, text=True))


def resolve_studio_selection(root: Path, specialization: str) -> dict:
    command = ["python3", str(root / "scripts" / "resolve-edition.py"), "studio",
               "--specialization", specialization]
    return json.loads(subprocess.check_output(command, text=True))


def resolve_gaming_selection(root: Path, specialization: str) -> dict:
    command = ["python3", str(root / "scripts" / "resolve-edition.py"), "gaming",
               "--specialization", specialization]
    return json.loads(subprocess.check_output(command, text=True))


def gaming_candidate_choices(root: Path, catalogue: dict, desktop_packages: list[str]) -> list[dict]:
    """Gaming choices for a candidate/testing ISO build.

    Gaming stays `planned` in the canonical catalogue; these items only
    exist when the builder explicitly opts into a candidate build. Each
    specialization resolves through the canonical resolver: Steam is
    proprietary and never installed by group selection (recorded as a
    post-install opt-in), reference-only applications cannot appear, and
    no GPU driver is chosen here (hardware decision at install/first
    boot, never from a PCI ID). Packages = Desktop (Hyprland) + Gaming
    platform + the specialization's own applications.
    """
    resolved_gaming = resolve(root, "gaming", "hyprland")
    result = []
    for spec_id, spec in catalogue["gamingSpecializations"].items():
        selection = resolve_gaming_selection(root, spec_id)
        packages = list(desktop_packages)
        for package in selection["packages"]:
            if package not in packages:
                packages.append(package)
        profile_package = f"hornero-profile-gaming-hyprland-{spec_id}"
        profile = dict(resolved_gaming)
        profile["gamingSelection"] = selection
        opt_ins = selection["proprietaryOptInRequired"]
        description = (
            f"Gaming desktop based on HorneroOS Desktop. Profile: {spec['title']}. "
            "Planned edition — candidate testing only, not a supported release. "
            "No hardware is qualified by choosing this profile."
        )
        if opt_ins:
            titles = [catalogue["gamingApplications"][app]["title"] for app in opt_ins]
            description += (
                " Not installed by this selection (explicit post-install opt-in required): "
                + ", ".join(titles) + "."
            )
        result.append({
            "id": f"gaming-hyprland-{spec_id}",
            "name": f"HorneroOS Gaming — {spec['title']} (Planned candidate)",
            "description": description,
            "packages": [*packages, profile_package],
            "profilePackage": profile_package,
            "profile": profile,
            "edition": "gaming",
            "compositor": "hyprland",
            "maturity": "planned",
            "compositorMaturity": catalogue["compositors"]["hyprland"]["maturity"],
            "isDefault": False,
            "candidate": True,
            "specializations": [spec_id],
        })
    return result


def studio_candidate_choices(root: Path, catalogue: dict, desktop_packages: list[str]) -> list[dict]:
    """Studio choices for a candidate/testing ISO build.

    Studio stays `planned` in the canonical catalogue; these items only
    exist when the builder explicitly opts into a candidate build. Each
    specialization resolves through the canonical resolver: proprietary
    applications are never installed by group selection (they are
    recorded as post-install opt-ins), and reference-only applications
    cannot appear. Packages = Desktop (Hyprland) + Studio platform +
    the specialization's own applications.
    """
    resolved_studio = resolve(root, "studio", "hyprland")
    result = []
    for spec_id, spec in catalogue["studioSpecializations"].items():
        selection = resolve_studio_selection(root, spec_id)
        packages = list(desktop_packages)
        for package in selection["packages"]:
            if package not in packages:
                packages.append(package)
        profile_package = f"hornero-profile-studio-hyprland-{spec_id}"
        profile = dict(resolved_studio)
        profile["studioSelection"] = selection
        opt_ins = selection["proprietaryOptInRequired"]
        description = (
            f"Creative workstation based on HorneroOS Desktop. Specialization: {spec['title']}. "
            "Planned edition — candidate testing only, not a supported release."
        )
        if opt_ins:
            titles = [catalogue["studioApplications"][app]["title"] for app in opt_ins]
            description += (
                " Not installed by this selection (explicit post-install opt-in required): "
                + ", ".join(titles) + "."
            )
        result.append({
            "id": f"studio-hyprland-{spec_id}",
            "name": f"HorneroOS Studio — {spec['title']} (Planned candidate)",
            "description": description,
            "packages": [*packages, profile_package],
            "profilePackage": profile_package,
            "profile": profile,
            "edition": "studio",
            "compositor": "hyprland",
            "maturity": "planned",
            "compositorMaturity": catalogue["compositors"]["hyprland"]["maturity"],
            "isDefault": False,
            "candidate": True,
            "specializations": [spec_id],
        })
    return result


def choices(root: Path, candidate_studio: bool = False, candidate_gaming: bool = False) -> list[dict]:
    catalogue = yaml.safe_load((root / "editions" / "catalogue.yaml").read_text(encoding="utf-8"))
    result = []
    for edition_id, edition in catalogue["editions"].items():
        maturity = edition["maturity"]
        if maturity not in ALLOWED_MATURITIES:
            continue
        compositor = edition.get("compositor")
        while isinstance(compositor, dict) and "inherit" in compositor:
            compositor = catalogue["editions"][compositor["inherit"]].get("compositor")
        backends = compositor["supported"] if compositor else [None]
        for backend in backends:
            backend_maturity = catalogue["compositors"][backend]["maturity"] if backend else None
            if backend_maturity == "planned":
                continue
            resolved = resolve(root, edition_id, backend)
            if resolved["maturity"] not in ALLOWED_MATURITIES:
                continue
            if backend and backend_maturity == "experimental":
                label = f"{edition['title']} — {backend.title()} (Experimental)"
            elif backend:
                label = f"{edition['title']} — {backend.title()}"
            else:
                label = edition["title"]
            profile_package = f"hornero-profile-{edition_id}-{backend}" if backend else f"hornero-profile-{edition_id}"
            result.append({
                "id": f"{edition_id}-{backend}" if backend else edition_id,
                "name": label,
                "description": description(edition_id, backend, maturity, backend_maturity),
                "packages": [*resolved["packages"], profile_package],
                "profilePackage": profile_package,
                "profile": resolved,
                "edition": edition_id,
                "compositor": backend,
                "maturity": maturity,
                "compositorMaturity": backend_maturity,
                "isDefault": bool(edition_id == "desktop" and compositor and backend == compositor.get("default")),
            })
    if candidate_studio or candidate_gaming:
        desktop = next((c for c in result if c["id"] == "desktop-hyprland"), None)
        if desktop is None:
            raise ValueError("candidate choices require the desktop-hyprland composition")
        desktop_packages = [pkg for pkg in desktop["packages"] if pkg != desktop["profilePackage"]]
    if candidate_studio:
        result.extend(studio_candidate_choices(root, catalogue, desktop_packages))
    if candidate_gaming:
        result.extend(gaming_candidate_choices(root, catalogue, desktop_packages))
    if not result:
        raise ValueError("the pinned product catalogue exposes no installable compositions")
    return result


def render_profile_package(output: Path, choice: dict, revision: str) -> None:
    """Create a small local package that records the selected installation profile."""
    if output.is_symlink():
        raise ValueError(f"profile package output cannot be a symlink: {output}")
    if output.exists() and not output.is_dir():
        raise ValueError(f"profile package output must be a directory: {output}")
    package_name = choice["profilePackage"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", package_name):
        raise ValueError(f"invalid generated profile package name: {package_name!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("profile source revision must be a full lowercase Git SHA")
    package_version = f"0.0.0.{revision}"
    directory = output / package_name
    directory.mkdir(parents=True, exist_ok=True)
    profile = {
        "apiVersion": "hornero.os/v1",
        "kind": "InstalledProfile",
        "sourceRevision": revision,
        "profilePackage": package_name,
        "edition": choice["profile"],
    }
    (directory / "system-profile.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directory / "PKGBUILD").write_text(
        "\n".join(
            [
                "# Generated from HorneroOS/hornero editions/catalogue.yaml; do not edit.",
                f"pkgname={package_name}",
                f"pkgver={package_version}",
                "pkgrel=1",
                f"pkgdesc='Installed HorneroOS profile metadata for {package_name}'",
                "arch=('any')",
                "license=('CC0-1.0')",
                "source=('system-profile.json')",
                "sha256sums=('SKIP')",
                "package() {",
                "  install -Dm644 \"$srcdir/system-profile.json\" \\",
                "    \"$pkgdir/usr/lib/hornero/system-profile.json\"",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def description(edition: str, compositor: str | None, maturity: str, backend_maturity: str | None) -> str:
    if edition == "server":
        summary = "Headless system for homelabs and services. It starts without a graphical session."
    elif edition == "desktop":
        summary = "Wayland-first desktop with Hornero Shell, themes, layouts and Control Center."
    elif edition == "studio":
        summary = "Creative workstation based on HorneroOS Desktop."
    else:
        summary = "Server-derived host for isolated autonomous-agent workloads."
    if compositor:
        summary += f" Compositor: {compositor.title()}."
    marks = []
    if maturity == "preview":
        marks.append("Preview");
    if backend_maturity == "experimental":
        marks.append("Experimental compositor")
    if marks:
        summary += " " + ", ".join(marks) + " support."
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-source", type=Path, help="use a local Hornero checkout instead of the pinned source")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "hornero-installer")
    parser.add_argument("--profile-packages-dir", type=Path, help="also render one profile metadata package per install choice")
    parser.add_argument("--candidate-studio", action="store_true", help="also render planned Studio specialization choices for a candidate/testing ISO (never for a release build)")
    parser.add_argument("--candidate-gaming", action="store_true", help="also render planned Gaming specialization choices for a candidate/testing ISO (never for a release build)")
    args = parser.parse_args()
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    root = load_product_root(lock, args.product_source, args.cache_dir.expanduser().absolute())
    options = choices(root, candidate_studio=args.candidate_studio, candidate_gaming=args.candidate_gaming)
    if args.profile_packages_dir:
        output_dir = args.profile_packages_dir.expanduser().absolute()
        if output_dir.is_symlink():
            raise ValueError(f"profile package output cannot be a symlink: {output_dir}")
        if output_dir.exists() and not output_dir.is_dir():
            raise ValueError(f"profile package output must be a directory: {output_dir}")
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(f"profile package output must be empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        for option in options:
            render_profile_package(output_dir, option, lock["product"]["revision"])
    defaults = [option["id"] for option in options if option["isDefault"]]
    if len(defaults) != 1:
        raise ValueError(f"the catalogue must resolve to one default compositor choice; found {defaults}")
    rendered = {
        "mode": "required",
        "method": "packages",
        "default": defaults[0],
        "labels": {"step": "Edition and compositor"},
        "items": [],
    }
    for choice in options:
        rendered["items"].append({
            "id": choice["id"],
            "name": choice["name"],
            "description": choice["description"],
            "packages": choice["packages"],
            "screenshot": CHOICE_SCREENSHOTS.get(choice["id"], ":/images/no-selection.png"),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(rendered, sort_keys=False, allow_unicode=True), encoding="utf-8")
    provenance = args.output.with_name("compositions.json")
    provenance.write_text(json.dumps({"productRevision": lock["product"]["revision"], "options": options}, indent=2) + "\n", encoding="utf-8")
    print(f"rendered {len(options)} install compositions from Hornero {lock['product']['revision']}")
    for option in options:
        print(f"  {option['id']}: {option['maturity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

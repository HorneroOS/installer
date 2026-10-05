#!/usr/bin/env python3
"""Render Calamares edition choices from the pinned Hornero product model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def choices(root: Path) -> list[dict]:
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
            result.append({
                "id": f"{edition_id}-{backend}" if backend else edition_id,
                "name": label,
                "description": description(edition_id, backend, maturity, backend_maturity),
                "packages": resolved["packages"],
                "edition": edition_id,
                "compositor": backend,
                "maturity": maturity,
                "compositorMaturity": backend_maturity,
                "isDefault": bool(compositor and backend == compositor.get("default")),
            })
    if not result:
        raise ValueError("the pinned product catalogue exposes no installable compositions")
    return result


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
    args = parser.parse_args()
    lock = yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))
    root = load_product_root(lock, args.product_source, args.cache_dir.expanduser().absolute())
    options = choices(root)
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

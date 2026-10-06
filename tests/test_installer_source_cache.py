"""Security regression tests for the pinned product-source cache."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "render_installer_catalogue", ROOT / "scripts/render-installer-catalogue.py"
)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def _product_source(root: Path) -> dict:
    catalogue = root / "editions/catalogue.yaml"
    resolver = root / "scripts/resolve-edition.py"
    catalogue.parent.mkdir(parents=True)
    resolver.parent.mkdir(parents=True)
    catalogue.write_text("editions: {}\n", encoding="utf-8")
    resolver.write_text("print('safe resolver')\n", encoding="utf-8")
    return {
        "repository": "https://example.invalid/hornero.git",
        "revision": "0123456789abcdef",
        "catalogueSha256": hashlib.sha256(catalogue.read_bytes()).hexdigest(),
        "resolverSha256": hashlib.sha256(resolver.read_bytes()).hexdigest(),
    }


def _mock_archive_download(monkeypatch, source_root: Path) -> None:
    def write_archive(_url: str, destination: str) -> None:
        with tarfile.open(destination, "w:gz") as archive:
            for relative in ("editions/catalogue.yaml", "scripts/resolve-edition.py"):
                archive.add(source_root / relative, arcname=f"hornero/{relative}")

    monkeypatch.setattr(renderer.urllib.request, "urlretrieve", write_archive)


def test_cache_is_created_private_and_reused_only_after_lock_verification(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    lock = {"product": _product_source(source)}
    _mock_archive_download(monkeypatch, source)
    cache_root = tmp_path / "cache"

    cached = renderer.load_product_root(lock, None, cache_root)
    assert cached == cache_root / "product" / lock["product"]["revision"]
    assert stat.S_IMODE(cache_root.stat().st_mode) == 0o700
    assert cached.is_dir()

    # The cache-hit path must recheck locked content before it is returned.
    (cached / "scripts/resolve-edition.py").write_text(
        "raise RuntimeError('untrusted cached code')\n", encoding="utf-8"
    )
    try:
        renderer.load_product_root(lock, None, cache_root)
    except ValueError as error:
        assert "does not match the locked Hornero revision" in str(error)
    else:
        raise AssertionError("tampered cache was accepted")


def test_cache_refuses_a_symlink_as_its_private_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    cache_link = tmp_path / "cache-link"
    cache_link.symlink_to(outside, target_is_directory=True)

    try:
        renderer.prepare_private_cache(cache_link)
    except ValueError as error:
        assert "user-owned directory" in str(error)
    else:
        raise AssertionError("cache symlink was accepted")


def test_cache_refuses_shared_directory_without_changing_its_permissions(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    original_mode = stat.S_IMODE(shared.stat().st_mode)

    try:
        renderer.prepare_private_cache(shared)
    except ValueError as error:
        assert "not be accessible by other users" in str(error)
    else:
        raise AssertionError("shared cache directory was accepted")

    assert stat.S_IMODE(shared.stat().st_mode) == original_mode


def test_profile_package_records_resolved_product_without_duplicating_packages(
    tmp_path: Path,
) -> None:
    output = tmp_path / "profiles"
    choice = {
        "id": "desktop-niri",
        "profilePackage": "hornero-profile-desktop-niri",
        "profile": {
            "edition": "desktop",
            "title": "HorneroOS Desktop",
            "maturity": "preview",
            "role": "desktop",
            "compositor": "niri",
            "compositorMaturity": "experimental",
            "packageSets": ["base", "desktop", "compositor:niri"],
            "packages": ["base", "hornero-shell", "niri"],
        },
    }

    revision = "0123456789abcdef0123456789abcdef01234567"
    renderer.render_profile_package(output, choice, revision)

    package = output / "hornero-profile-desktop-niri"
    metadata = json.loads((package / "system-profile.json").read_text())
    assert metadata["apiVersion"] == "hornero.os/v1"
    assert metadata["kind"] == "InstalledProfile"
    assert metadata["sourceRevision"] == revision
    assert metadata["edition"]["compositor"] == "niri"
    assert metadata["edition"]["packages"] == ["base", "hornero-shell", "niri"]

    build_recipe = (package / "PKGBUILD").read_text()
    assert "pkgname=hornero-profile-desktop-niri" in build_recipe
    assert '"$pkgdir/usr/lib/hornero/system-profile.json"' in build_recipe


def test_profile_package_rejects_symlink_output_and_non_sha_revision(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "profiles-link"
    output.symlink_to(outside, target_is_directory=True)
    choice = {
        "id": "desktop-niri",
        "profilePackage": "hornero-profile-desktop-niri",
        "profile": {"edition": "desktop"},
    }
    try:
        renderer.render_profile_package(output, choice, "0" * 40)
    except ValueError as error:
        assert "cannot be a symlink" in str(error)
    else:
        raise AssertionError("profile package output symlink was accepted")
    try:
        renderer.render_profile_package(tmp_path / "profiles", choice, "bad-revision")
    except ValueError as error:
        assert "full lowercase Git SHA" in str(error)
    else:
        raise AssertionError("non-SHA profile revision was accepted")

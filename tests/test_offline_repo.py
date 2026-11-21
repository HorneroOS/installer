"""Offline repository: closure list, manifest verify, target switch."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_mod = _load("offline_repo_build", ROOT / "scripts/offline-repo.py")
runtime_mod = _load("offline_repo_runtime", CALAMARES / "offline-repo.py")
cleanup_mod = _load("cleanup_package_source", CALAMARES / "cleanup-package-source.py")
preflight_mod = _load(
    "preflight_payload_offline", CALAMARES / "preflight-payload.py"
)


def test_package_union_covers_every_selectable_package():
    packages = build_mod.package_union(
        CALAMARES / "modules/compositions.json",
        CALAMARES / "modules/netinstall.conf",
    )
    compositions = json.loads(
        (CALAMARES / "modules/compositions.json").read_text()
    )
    expected = set()
    for option in compositions["options"]:
        expected.update(option["packages"])

    def _leaves(items):
        for item in items:
            if item.get("subgroups"):
                yield from _leaves(item["subgroups"])
            else:
                yield item

    import yaml

    netinstall = yaml.safe_load(
        (CALAMARES / "modules/netinstall.conf").read_text()
    )
    for leaf in _leaves(netinstall["groups"]):
        expected.update(leaf.get("packages") or [])
    assert set(packages) == {p for p in expected if not p.startswith("hornero")}
    # Netinstall-only leaves are covered too, Hornero-local ones excluded.
    assert "ardour" in packages and "blender" in packages
    assert not any(p.startswith("hornero") for p in packages)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact = repo / "nano-1.0-1-x86_64.pkg.tar.zst"
    artifact.write_bytes(b"fake-package")
    (repo / "hornero-offline.db.tar.gz").write_bytes(b"db")
    build_mod.write_manifest(repo, "2026/10/10")
    return repo


def test_manifest_verify_roundtrip_and_tamper(tmp_path):
    repo = _repo(tmp_path)
    manifest = json.loads((repo / "offline-manifest.json").read_text())
    assert manifest["packageCount"] == 1
    assert manifest["totalBytes"] == len(b"fake-package")
    assert build_mod.verify_repo(repo) == []
    assert runtime_mod.verify_repo(repo) == []
    (repo / "nano-1.0-1-x86_64.pkg.tar.zst").write_bytes(b"tampered-longer")
    assert build_mod.verify_repo(repo)
    assert runtime_mod.verify_repo(repo)


ONLINE_CONF = """[options]
HoldPkg = pacman glibc
Include = /etc/pacman.d/hornero-installer.conf

[core]
Include = /etc/pacman.d/hornero-installer-mirrorlist.conf

[extra]
Include = /etc/pacman.d/hornero-installer-mirrorlist.conf

[multilib]
Include = /etc/pacman.d/hornero-installer-mirrorlist.conf
"""


def _target(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "etc/pacman.d").mkdir(parents=True)
    (root / "etc/pacman.conf").write_text(ONLINE_CONF)
    return root


def test_apply_offline_no_marker_is_noop(tmp_path):
    root = _target(tmp_path)
    assert runtime_mod.apply_offline(root, _repo(tmp_path), tmp_path / "nope") is False
    assert (root / "etc/pacman.conf").read_text() == ONLINE_CONF


def test_apply_offline_rewrites_and_cleanup_restores(tmp_path):
    root = _target(tmp_path)
    repo = _repo(tmp_path)
    marker = tmp_path / "offline-mode"
    marker.write_text("offline\n")
    assert runtime_mod.apply_offline(root, repo, marker) is True
    conf = (root / "etc/pacman.conf").read_text()
    assert "[hornero-offline]" in conf
    assert f"Server = file://{repo}" in conf
    assert "archive.archlinux.org" not in conf
    assert "[core]" not in conf
    assert "Include = /etc/pacman.d/hornero-installer.conf" in conf
    cleanup_mod.cleanup(root)
    restored = (root / "etc/pacman.conf").read_text()
    assert "hornero-offline" not in restored
    assert "file://" not in restored
    for section in ("[core]", "[extra]", "[multilib]"):
        assert section in restored
    assert restored.count("Include = /etc/pacman.d/mirrorlist") == 3


def test_cleanup_online_target_unchanged_shape(tmp_path):
    root = _target(tmp_path)
    cleanup_mod.cleanup(root)
    conf = (root / "etc/pacman.conf").read_text()
    assert conf.count("Include = /etc/pacman.d/mirrorlist") == 3
    assert "hornero-installer.conf" not in conf


def test_preflight_blocks_incomplete_offline_repo_before_partition(tmp_path):
    root = tmp_path / "live"
    (root / "run/hornero-installer").mkdir(parents=True)
    (root / "run/hornero-installer/offline-mode").write_text("offline\n")
    (root / "usr/share/hornero-installer/offline-repo").mkdir(parents=True)
    errors = preflight_mod.offline_repo_errors(root)
    assert errors, "preflight must reject offline mode without its repo"
    # No marker: online installs never consult the offline repo.
    (root / "run/hornero-installer/offline-mode").unlink()
    assert preflight_mod.offline_repo_errors(root) == []


def test_apply_system_plan_still_rejects_extra_kernel_offline():
    plan_mod = _load("apply_system_plan_offline", CALAMARES / "apply-system-plan.py")
    allowlist = plan_mod.load_allowlist()
    selection = dict(plan_mod.DEFAULT_SELECTION)
    selection.update({"offline": True, "primaryKernel": "linux-lts"})
    errors = plan_mod.validate_selection(selection, allowlist)
    assert any("Offline installation" in e for e in errors)


def test_launcher_offers_offline_before_sudo_and_runner_marks_root_owned():
    start = (
        ROOT / "image/archiso/airootfs/usr/local/bin/hornero-installer-start"
    ).read_text()
    run = (
        ROOT / "image/archiso/airootfs/usr/local/bin/hornero-installer-run"
    ).read_text()
    assert "Continue offline" in start
    assert "--verify-only" in start
    assert start.index("offer_offline") < start.index("exec /usr/bin/sudo")
    assert "No disk changes have been made" in start
    assert "/run/hornero-installer/offline-mode" in run
    assert "install -m 0600" in run
    assert run.index("offline-mode") < run.index("/usr/bin/calamares -D6")


def test_build_iso_offline_is_opt_in():
    build = (ROOT / "scripts/build-iso.sh").read_text()
    assert "--offline" in build
    assert "build-offline-repo.sh" in build
    assert "offline-manifest.json" in build

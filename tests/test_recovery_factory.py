"""Factory snapper config for the opt-in snapshots capability (hornero#179).

The installer writes /etc/snapper/configs/root ONLY when the target
actually carries the pieces the recovery doctor probes: snapper
installed (the capability was selected), a Btrfs root, and the
top-level /.snapshots store. Anything else must stay a silent no-op
so default installs never gain a config that pretends a backend
exists. An existing config is never overwritten.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "image/calamares/configure-recovery.py"

spec = importlib.util.spec_from_file_location("configure_recovery", MODULE_PATH)
assert spec is not None and spec.loader is not None
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def _target(tmp_path: Path, *, snapper: bool, fstab: str) -> Path:
    root = tmp_path / "target"
    (root / "etc").mkdir(parents=True)
    (root / "etc/fstab").write_text(fstab, encoding="utf-8")
    if snapper:
        (root / "usr/bin").mkdir(parents=True)
        (root / "usr/bin/snapper").write_text("#!/bin/true\n", encoding="utf-8")
    return root


BTRFS_FSTAB = (
    "UUID=root / btrfs rw,subvol=/@ 0 1\n"
    "UUID=root /home btrfs rw,subvol=/@home 0 2\n"
    "UUID=root /.snapshots btrfs rw,subvol=/@snapshots 0 2\n"
)
EXT4_FSTAB = "UUID=root / ext4 rw 0 1\n"
NO_STORE_FSTAB = "UUID=root / btrfs rw,subvol=/@ 0 1\n"


def test_no_snapper_is_noop(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=False, fstab=BTRFS_FSTAB)
    assert recovery.configure_recovery(root) is False
    assert not (root / "etc/snapper").exists()


def test_non_btrfs_root_is_noop(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=True, fstab=EXT4_FSTAB)
    assert recovery.configure_recovery(root) is False
    assert not (root / "etc/snapper").exists()


def test_missing_snapshots_store_is_noop(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=True, fstab=NO_STORE_FSTAB)
    assert recovery.configure_recovery(root) is False
    assert not (root / "etc/snapper").exists()


def test_ready_target_gets_bounded_factory_config(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=True, fstab=BTRFS_FSTAB)
    assert recovery.configure_recovery(root) is True
    config = (root / "etc/snapper/configs/root").read_text(encoding="utf-8")
    assert 'SUBVOLUME="/"' in config
    assert 'FSTYPE="btrfs"' in config
    # Bounded retention is a contract requirement, not a preference.
    assert "TIMELINE_LIMIT_HOURLY=" in config
    assert "NUMBER_LIMIT=" in config
    # The file itself must carry the honesty boundary.
    assert "not proof" in config


def test_existing_config_is_never_overwritten(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=True, fstab=BTRFS_FSTAB)
    existing = root / "etc/snapper/configs/root"
    existing.parent.mkdir(parents=True)
    existing.write_text("# admin-owned\n", encoding="utf-8")
    assert recovery.configure_recovery(root) is False
    assert existing.read_text(encoding="utf-8") == "# admin-owned\n"


def test_symlinked_snapper_dir_is_refused(tmp_path: Path) -> None:
    root = _target(tmp_path, snapper=True, fstab=BTRFS_FSTAB)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "etc/snapper").symlink_to(outside, target_is_directory=True)
    try:
        recovery.configure_recovery(root)
    except ValueError:
        pass
    else:
        raise AssertionError("symlinked /etc/snapper must be refused")
    assert not (outside / "configs/root").exists()

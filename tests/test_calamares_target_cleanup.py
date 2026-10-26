"""Post-exit Calamares target cleanup (installer#31 cancel mount leak)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "image/archiso/airootfs/usr/local/lib/hornero-installer/cleanup-calamares-targets.py"
)

spec = importlib.util.spec_from_file_location("cleanup_calamares_targets", MODULE_PATH)
assert spec is not None and spec.loader is not None
cleanup_targets_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup_targets_mod)


class _CleanupModule:
    def __init__(self) -> None:
        self.cleaned: list[Path] = []

    def cleanup(self, target: Path) -> None:
        self.cleaned.append(target)


def _make_target(tmp_path: Path) -> Path:
    target = tmp_path / "calamares-root-test1"
    (target / "etc").mkdir(parents=True)
    (target / "etc/pacman.conf").write_text(
        "[core]\nInclude = /etc/pacman.d/hornero-installer.conf\n",
        encoding="utf-8",
    )
    return target


def test_recursive_fallback_clears_nested_mount_failures(tmp_path: Path) -> None:
    target = _make_target(tmp_path)
    cleanup_module = _CleanupModule()
    recursive_calls: list[Path] = []

    def failing_unmount(mountpoint: Path) -> None:
        raise RuntimeError(f"unmount {mountpoint}: target is busy")

    def recursive_unmount(mountpoint: Path) -> None:
        recursive_calls.append(mountpoint)

    failures, cleaned = cleanup_targets_mod.cleanup_targets(
        [target / "etc/pacman.conf"],
        cleanup_module,
        failing_unmount,
        unmount_recursive=recursive_unmount,
        temp_root=tmp_path,
        owner_uid=target.lstat().st_uid,
    )

    assert failures == []
    assert cleaned == [target]
    assert recursive_calls == [target]
    assert cleanup_module.cleaned == [target]


def test_recursive_failure_keeps_failures_visible(tmp_path: Path) -> None:
    target = _make_target(tmp_path)

    def failing_unmount(mountpoint: Path) -> None:
        raise RuntimeError(f"unmount {mountpoint}: target is busy")

    def failing_recursive(mountpoint: Path) -> None:
        raise RuntimeError(f"unmount -R {mountpoint}: target is busy")

    failures, cleaned = cleanup_targets_mod.cleanup_targets(
        [target / "etc/pacman.conf"],
        _CleanupModule(),
        failing_unmount,
        unmount_recursive=failing_recursive,
        temp_root=tmp_path,
        owner_uid=target.lstat().st_uid,
    )

    assert cleaned == []
    assert failures
    assert any("unmount -R" in failure for failure in failures)


def test_unmarked_target_is_ignored(tmp_path: Path) -> None:
    target = _make_target(tmp_path)
    (target / "etc/pacman.conf").write_text("[core]\n", encoding="utf-8")

    failures, cleaned = cleanup_targets_mod.cleanup_targets(
        [target / "etc/pacman.conf"],
        _CleanupModule(),
        lambda mountpoint: None,
        unmount_recursive=lambda mountpoint: None,
        temp_root=tmp_path,
        owner_uid=target.lstat().st_uid,
    )

    assert failures == []
    assert cleaned == []

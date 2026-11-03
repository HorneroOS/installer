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


def test_unmarked_target_unmounts_without_pacman_restore(tmp_path: Path) -> None:
    """A cancel before the packages step leaves no include marker, but the
    target can still hold mounts/swap: unmounts must run; only the
    pacman.conf restore stays gated on the marker."""
    target = _make_target(tmp_path)
    (target / "etc/pacman.conf").write_text("[core]\n", encoding="utf-8")
    cleanup_module = _CleanupModule()
    unmounted: list[Path] = []

    failures, cleaned = cleanup_targets_mod.cleanup_targets(
        [target / "etc/pacman.conf"],
        cleanup_module,
        unmounted.append,
        unmount_recursive=lambda mountpoint: None,
        temp_root=tmp_path,
        owner_uid=target.lstat().st_uid,
    )

    assert failures == []
    assert cleaned == [target]
    assert unmounted  # resolver + target mounts were attempted
    assert cleanup_module.cleaned == []  # restore stayed gated


def test_deactivate_devices_scoped_to_target(tmp_path: Path) -> None:
    target = tmp_path / "calamares-root-x"
    commands: list[list[str]] = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def runner(argv):
        commands.append(argv)
        if argv[0].endswith("swapon"):
            return Result(stdout=f"{target}/swapfile\n/swap_live\n")
        if argv[0].endswith("findmnt"):
            return Result(stdout="/dev/mapper/cryptroot\n/dev/sda2\n")
        return Result()

    failures = cleanup_targets_mod.deactivate_target_devices(target, runner)

    assert failures == []
    assert ["/usr/bin/swapoff", f"{target}/swapfile"] in commands
    assert not any("/swap_live" in str(argv) for argv in commands if argv[0].endswith("swapoff"))
    assert ["/usr/bin/cryptsetup", "close", "cryptroot"] in commands


def test_deactivate_devices_reports_busy_mapper(tmp_path: Path) -> None:
    target = tmp_path / "calamares-root-x"

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def runner(argv):
        if argv[0].endswith("findmnt"):
            return Result(stdout="/dev/mapper/cryptroot\n")
        if argv[0].endswith("cryptsetup"):
            return Result(returncode=1, stderr="Device cryptroot is still in use.")
        return Result()

    failures = cleanup_targets_mod.deactivate_target_devices(target, runner)

    assert len(failures) == 1
    assert "cryptsetup close cryptroot" in failures[0]

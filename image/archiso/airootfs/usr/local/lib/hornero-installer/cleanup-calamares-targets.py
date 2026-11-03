#!/usr/bin/env python3
"""Remove temporary Calamares mounts and restore the target pacman config."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import glob
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path


CLEANUP_MODULE = Path("/usr/local/lib/hornero-installer/cleanup-package-source.py")
TARGET_GLOB = "/tmp/calamares-root-*/etc/pacman.conf"
TEMP_INCLUDES = (
    "Include = /etc/pacman.d/hornero-installer.conf",
    "Include = /etc/pacman.d/hornero-installer-mirrorlist.conf",
)
RESOLVER_MOUNTS = ("etc/hosts", "etc/resolv.conf")
TARGET_MOUNTS = (
    "sys/firmware/efi/efivars",
    "run/udev",
    "usr/share/hornero-installer/repo",
    "dev",
    "proc",
    "sys",
    "run",
    "var/cache",
    "var/log",
    "home",
    "boot",
    ".",
)


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("cleanup_package_source", CLEANUP_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load cleanup module: {CLEANUP_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unmount_bind(mountpoint: Path) -> None:
    result = subprocess.run(
        ["/usr/bin/umount", str(mountpoint)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "not mounted" not in result.stderr.lower():
        raise RuntimeError(f"unmount {mountpoint}: {result.stderr.strip()}")


def unmount_recursive(mountpoint: Path) -> None:
    """Detach a target and every submount below it, deepest first.

    Plain per-directory umounts fail when Calamares left nested mounts such
    as ``dev/pts`` or ``run/udev`` behind (cancel path, installer#31), which
    leaked the target root mount. ``umount -R`` handles the whole tree; the
    lazy variant is the last resort so the live session never keeps a
    cancelled target attached.
    """
    for flags in (["-R"], ["-R", "-l"]):
        result = subprocess.run(
            ["/usr/bin/umount", *flags, str(mountpoint)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 or "not mounted" in result.stderr.lower():
            return
    raise RuntimeError(f"unmount -R {mountpoint}: {result.stderr.strip()}")


def _run_quiet(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def deactivate_target_devices(target: Path, runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run_quiet) -> list[str]:
    """Turn off swap and close LUKS mappings that belong to this target.

    Calamares can leave the target swap active and its LUKS mapping open
    on the cancel/failure path; unmounting alone then leaks both and the
    partition stays busy for a retry. Discovery is read-only and scoped
    to this target: swap entries must live under the target, and mapper
    devices must be mounted under it. Failures are reported, never
    forced: a mapping still in use stays open and visible in the error.
    """
    failures: list[str] = []
    swaps = runner(["/usr/bin/swapon", "--show=NAME", "--noheadings"])
    if swaps.returncode == 0:
        for name in swaps.stdout.split():
            if name.startswith(f"{target}/"):
                result = runner(["/usr/bin/swapoff", name])
                if result.returncode != 0:
                    failures.append(f"swapoff {name}: {result.stderr.strip()}")
    mounts = runner(["/usr/bin/findmnt", "-R", "-r", "-n", "-o", "SOURCE", str(target)])
    if mounts.returncode == 0:
        mappers = sorted({s.strip() for s in mounts.stdout.splitlines() if s.strip().startswith("/dev/mapper/")})
        for source in mappers:
            name = source.removeprefix("/dev/mapper/")
            result = runner(["/usr/bin/cryptsetup", "close", name])
            err = result.stderr.lower()
            if result.returncode != 0 and "not active" not in err and "no such device" not in err:
                failures.append(f"cryptsetup close {name}: {result.stderr.strip()}")
    return failures


def safe_target(pacman_conf: Path, temp_root: Path, owner_uid: int) -> Path | None:
    """Accept only root-owned Calamares targets directly below the temp root."""
    if pacman_conf.is_symlink() or pacman_conf.name != "pacman.conf":
        return None
    target = pacman_conf.parent.parent
    try:
        if target.parent != temp_root or not target.name.startswith("calamares-root-"):
            return None
        target_info = target.lstat()
        etc_info = pacman_conf.parent.lstat()
        conf_info = pacman_conf.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(target_info.st_mode) or target_info.st_uid != owner_uid:
        return None
    if target_info.st_mode & 0o022:
        return None
    if not stat.S_ISDIR(etc_info.st_mode) or etc_info.st_uid != owner_uid:
        return None
    if not stat.S_ISREG(conf_info.st_mode) or conf_info.st_uid != owner_uid:
        return None
    return target


def cleanup_targets(
    pacman_configs: Iterable[Path],
    cleanup_module,
    unmount: Callable[[Path], None],
    *,
    unmount_recursive: Callable[[Path], None] | None = None,
    deactivate_devices: Callable[[Path], list[str]] | None = None,
    temp_root: Path = Path("/tmp"),
    owner_uid: int = 0,
) -> tuple[list[str], list[Path]]:
    failures: list[str] = []
    cleaned: list[Path] = []
    for pacman_conf in pacman_configs:
        target = safe_target(pacman_conf, temp_root, owner_uid)
        if target is None:
            continue
        try:
            content = pacman_conf.read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            failures.append(f"{pacman_conf}: {error}")
            continue
        marked = any(include in content.splitlines() for include in TEMP_INCLUDES)

        # Unmounting is unconditional for a verified Calamares target: a
        # cancel before the packages step (or after its cleanup) leaves no
        # include marker yet can still leak mounts, swap and LUKS mappings
        # (installer#31 class). Only the pacman.conf restore stays gated
        # on the marker, because it rewrites a user-visible file.
        target_failures: list[str] = []
        for relative in RESOLVER_MOUNTS:
            try:
                unmount(target / relative)
            except RuntimeError as error:
                target_failures.append(str(error))
        if marked:
            try:
                cleanup_module.cleanup(target)
            except (OSError, ValueError, RuntimeError) as error:
                target_failures.append(f"restore pacman config: {error}")
        for relative in TARGET_MOUNTS:
            try:
                unmount(target / relative)
            except RuntimeError as error:
                target_failures.append(str(error))
        if target_failures and unmount_recursive is not None:
            # Nested submounts (dev/pts, run/udev, ...) can make the plain
            # per-directory umounts above fail and leak the target root on
            # the cancel path (installer#31). One recursive detach of the
            # whole target tree resolves that; only keep the failures if
            # even the recursive detach fails.
            try:
                unmount_recursive(target)
                target_failures = [
                    failure
                    for failure in target_failures
                    if failure.startswith(("restore pacman config:", "swapoff ", "cryptsetup close "))
                ]
            except RuntimeError as error:
                target_failures.append(str(error))
        if deactivate_devices is not None:
            # After the unmounts: swap files and LUKS mappings under the
            # target would otherwise keep the install disk busy.
            target_failures.extend(deactivate_devices(target))
        if target_failures:
            failures.extend(f"{pacman_conf}: {error}" for error in target_failures)
        else:
            cleaned.append(target)
    return failures, cleaned


def main() -> int:
    try:
        cleanup_module = load_cleanup_module()
        failures, cleaned = cleanup_targets(
            map(Path, glob.glob(TARGET_GLOB)),
            cleanup_module,
            unmount_bind,
            unmount_recursive=unmount_recursive,
            deactivate_devices=deactivate_target_devices,
            temp_root=Path("/tmp"),
            owner_uid=os.geteuid(),
        )
        for target in cleaned:
            print(f"Cleaned temporary Calamares target {target}")
        if failures:
            print("Calamares post-exit cleanup failed: " + "; ".join(failures), file=sys.stderr)
            return 1
        return 0
    except Exception as error:  # Keep failures visible in the installer log.
        print(f"Calamares post-exit cleanup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

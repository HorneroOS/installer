#!/usr/bin/env python3
"""Unmount temporary Calamares resolver binds and restore target pacman config."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import glob
import importlib.util
import subprocess
import sys
from pathlib import Path


CLEANUP_MODULE = Path("/usr/local/lib/hornero-installer/cleanup-package-source.py")
TARGET_GLOB = "/tmp/calamares-root-*/etc/pacman.conf"
TEMP_INCLUDES = (
    "Include = /etc/pacman.d/hornero-installer.conf",
    "Include = /etc/pacman.d/hornero-installer-mirrorlist.conf",
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


def cleanup_targets(
    pacman_configs: Iterable[Path], cleanup_module, unmount: Callable[[Path], None]
) -> tuple[list[str], list[Path]]:
    failures: list[str] = []
    cleaned: list[Path] = []
    for pacman_conf in pacman_configs:
        try:
            if pacman_conf.is_symlink() or not pacman_conf.is_file():
                continue
            content = pacman_conf.read_text(encoding="utf-8")
            if not any(include in content.splitlines() for include in TEMP_INCLUDES):
                continue
            target = pacman_conf.parents[1]
            for relative in ("etc/hosts", "etc/resolv.conf"):
                unmount(target / relative)
            cleanup_module.cleanup(target)
            cleaned.append(target)
        except (OSError, ValueError, RuntimeError) as error:
            failures.append(f"{pacman_conf}: {error}")
    return failures, cleaned


def main() -> int:
    try:
        cleanup_module = load_cleanup_module()
        failures, cleaned = cleanup_targets(
            map(Path, glob.glob(TARGET_GLOB)), cleanup_module, unmount_bind
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

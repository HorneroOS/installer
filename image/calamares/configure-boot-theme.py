#!/usr/bin/env python3
"""Apply the Hornero Signal GRUB theme to the installed target (installer#107).

Runs before Calamares `grubcfg` / `bootloader` with `--root ${ROOT}` so the
installed GRUB config picks up `GRUB_THEME="/boot/grub/themes/hornero-signal/theme.txt"`
when `hornero-boot-theme` and the packaged theme exist in the target.

Skips cleanly when `systemd-boot` is selected, `/etc/default/grub` is absent, or
`hornero-boot-theme` / `hornero-signal` theme assets are not packaged in the target.
Refuses symlinks on any touched path.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import stat
import subprocess
import sys
from pathlib import Path

BOOT_THEME_TOOL_REL = Path("usr/share/hornero/bin/hornero-boot-theme")
GRUB_THEME_FILE_REL = Path("usr/share/grub/themes/hornero-signal/theme.txt")
GRUB_DEFAULT_REL = Path("etc/default/grub")
PLAN_REL = Path("usr/lib/hornero/installation-plan.json")
GRUB_DEST_REL = Path("boot/grub/themes/hornero-signal")


def _run(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


def _reject_symlink_components(root: Path, rel: Path) -> None:
    current = root
    for component in rel.parts:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in boot-theme path: {current}")


def _selected_bootloader(root: Path) -> str:
    plan_path = root / PLAN_REL
    if not plan_path.is_file():
        return "grub"
    if plan_path.is_symlink():
        raise ValueError(f"Refusing symlink in installation plan path: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("installation plan must be a JSON object")
    selection = plan.get("selection") or {}
    return str(selection.get("bootloader") or "grub")


def apply_grub_theme(
    root: Path,
    *,
    runner: Callable[[list[str]], int] = _run,
) -> str:
    """Apply Signal GRUB theme to *root* if GRUB is selected and assets exist."""
    root = root.resolve()
    bootloader = _selected_bootloader(root)
    if bootloader != "grub":
        return f"skipped (bootloader={bootloader})"

    for rel in (
        GRUB_DEFAULT_REL,
        BOOT_THEME_TOOL_REL,
        GRUB_THEME_FILE_REL,
        GRUB_DEST_REL,
    ):
        _reject_symlink_components(root, rel)

    grub_default = root / GRUB_DEFAULT_REL
    tool = root / BOOT_THEME_TOOL_REL
    theme_file = root / GRUB_THEME_FILE_REL

    if not grub_default.is_file():
        return "skipped (missing /etc/default/grub)"
    if not tool.is_file():
        return "skipped (hornero-boot-theme not packaged)"
    if not theme_file.is_file():
        return "skipped (hornero-signal GRUB theme not packaged)"

    argv = [
        "/usr/bin/bash",
        str(tool),
        "apply",
        "--grub",
        "--no-rebuild",
        "--root",
        str(root),
    ]
    rc = runner(argv)
    if rc != 0:
        raise RuntimeError(f"hornero-boot-theme exited with status {rc}")
    return "applied"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="installed target root")
    args = parser.parse_args()
    try:
        status = apply_grub_theme(args.root)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"configure-boot-theme: {error}", file=sys.stderr)
        return 1
    print(f"configure-boot-theme: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

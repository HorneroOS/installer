#!/usr/bin/env python3
"""Give the installed target its HorneroOS os-release identity.

The target rootfs unpacks Arch's os-release (``ID=arch``). HorneroOS is
the installed distribution, so the target must identify itself as such:
tooling such as chezmoi reads ``.chezmoi.osRelease.id`` from
``/etc/os-release`` to decide whether the native HorneroOS configuration
owns the desktop, instead of guessing from the hostname.

Per the os-release spec, ``/etc/os-release`` takes precedence over
``/usr/lib/os-release``. On Arch it is a symlink into ``/usr/lib``; this
module replaces that symlink with a regular file owned by the
installation, without modifying the packaged ``/usr/lib/os-release``.
Existing user/admin edits are not expected at install time, but a target
that already carries a non-Arch identity is left untouched.
"""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

OS_RELEASE = """\
NAME="HorneroOS"
PRETTY_NAME="HorneroOS"
ID=horneroos
ID_LIKE=arch
BUILD_ID=preview
HOME_URL="https://horneroos.com/"
DOCUMENTATION_URL="https://horneroos.com/docs/"
SUPPORT_URL="https://github.com/HorneroOS/hornero/issues"
BUG_REPORT_URL="https://github.com/HorneroOS/hornero/issues"
LOGO=horneroos
"""


def _identity_of(path: Path) -> str | None:
    """Return the ID= value of an os-release file, resolving symlinks."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    for line in text.splitlines():
        if line.startswith("ID="):
            return line[3:].strip().strip('"')
    return None


def configure_os_identity(root: Path) -> None:
    root = root.resolve()
    etc = root / "etc"
    if not etc.is_dir() or etc.is_symlink():
        raise ValueError(f"Target etc directory is missing or a symlink: {etc}")
    destination = etc / "os-release"

    existing = _identity_of(destination)
    if existing is not None and existing != "arch":
        # The target already declares a real identity; never clobber it.
        return

    try:
        info = destination.lstat()
    except FileNotFoundError:
        info = None
    if info is not None and not (stat.S_ISLNK(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise ValueError(f"Target os-release is not a file or symlink: {destination}")

    # Write beside the destination and rename, so a crash cannot leave a
    # truncated identity file behind. rename replaces the Arch symlink.
    tmp = etc / ".os-release.hornero-tmp"
    tmp.write_text(OS_RELEASE, encoding="utf-8")
    tmp.chmod(0o644)
    os.rename(tmp, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed target root")
    args = parser.parse_args()
    configure_os_identity(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Drop the encrypt initramfs hook on targets that are not encrypted.

`initcpiocfg` appends the busybox `encrypt` hook unconditionally. On an
unencrypted install that hook falls back to opening the root device as
if it were a LUKS volume and prints

    ERROR: Failed to open encryption mapping: The device UUID=... is
    not a LUKS volume and the crypto= parameter was not specified.

on every boot before continuing normally (installer#65).

This step runs after `initcpiocfg` and before `initcpio`. It removes
`encrypt`/`sd-encrypt` from the target's HOOKS only when the target is
positively unencrypted: no `/dev/mapper/` device in `/etc/fstab` and no
mapping entry in `/etc/crypttab`. Any doubt (missing fstab, unreadable
files) keeps the hook — never break a LUKS unlock to silence a message.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ENCRYPT_HOOKS = ("encrypt", "sd-encrypt")


def _has_crypttab_entry(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return False
    return any(
        line.strip() and not line.strip().startswith("#")
        for line in text.splitlines()
    )


def _uses_mapper_device(path: Path) -> bool | None:
    """True/False from fstab, or None when fstab cannot be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if line.split()[0].startswith("/dev/mapper/"):
                return True
    return False


def configure_initcpio_encrypt(root: Path) -> None:
    root = root.resolve()
    etc = root / "etc"
    if not etc.is_dir() or etc.is_symlink():
        raise ValueError(f"Target etc directory is missing or a symlink: {etc}")

    if _uses_mapper_device(etc / "fstab") is not False:
        return  # Encrypted, or unknown: keep the hook (fail safe).
    if _has_crypttab_entry(etc / "crypttab"):
        return

    conf_path = etc / "mkinitcpio.conf"
    text = conf_path.read_text(encoding="utf-8")

    def _drop(match: re.Match[str]) -> str:
        hooks = [h for h in match.group(1).split() if h not in ENCRYPT_HOOKS]
        return "HOOKS=(" + " ".join(hooks) + ")"

    new_text, count = re.subn(r"HOOKS=\(([^)]*)\)", _drop, text, count=1)
    if count and new_text != text:
        conf_path.write_text(new_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    configure_initcpio_encrypt(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())

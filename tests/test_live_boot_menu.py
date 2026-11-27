"""Static checks for the Hornero Signal live-ISO BIOS boot menu (syslinux)."""

from __future__ import annotations

import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSLINUX = ROOT / "image/archiso/syslinux"

# hornero-signal-night roles used by the menu (HorneroOS/config theme.json).
ALLOWED = {"0C1016", "E6EBF1", "A9B7C6", "24303D", "F2AC52", "8999AB", "000000"}


def cfg() -> str:
    return (SYSLINUX / "syslinux.cfg").read_text(encoding="utf-8")


def test_menu_is_graphical_and_uses_the_splash() -> None:
    text = cfg()
    assert re.search(r"^UI vesamenu\.c32$", text, re.M)
    assert re.search(r"^MENU BACKGROUND splash\.png$", text, re.M)
    assert re.search(r"^MENU RESOLUTION 800 600$", text, re.M)


def test_splash_is_800x600_png() -> None:
    data = (SYSLINUX / "splash.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (800, 600)


def test_colours_are_signal_night_roles() -> None:
    colours = re.findall(r"#[0-9a-fA-F]{2}([0-9a-fA-F]{6})\b", cfg())
    assert colours
    assert {c.upper() for c in colours} <= ALLOWED
    # The screen element must stay transparent or it hides the splash artwork.
    screen = re.search(r"^MENU COLOR screen\s+\S+\s+(\S+)\s+(\S+)", cfg(), re.M)
    assert screen and screen.group(2).startswith("#00")


def test_boot_entry_and_archiso_placeholders_are_unchanged() -> None:
    text = cfg()
    assert "DEFAULT hornero" in text
    assert "LINUX /%INSTALL_DIR%/boot/%ARCH%/vmlinuz-linux" in text
    assert "INITRD /%INSTALL_DIR%/boot/%ARCH%/initramfs-linux.img" in text
    assert (
        "APPEND archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% "
        "copytoram=n %KERNEL_PARAMS%"
    ) in text


def test_bootmodes_keep_systemd_boot_for_uefi() -> None:
    profile = (ROOT / "image/archiso/profiledef.sh").read_text(encoding="utf-8")
    assert "bootmodes=('bios.syslinux' 'uefi.systemd-boot')" in profile

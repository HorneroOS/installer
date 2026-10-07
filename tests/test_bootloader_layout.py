"""Regression tests for firmware-compatible automated disk layouts."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_erase_layout_supports_uefi_and_legacy_bios_grub() -> None:
    partition = yaml.safe_load(
        (ROOT / "image/calamares/modules/partition.conf").read_text(encoding="utf-8")
    )
    bootloader = yaml.safe_load(
        (ROOT / "image/calamares/modules/bootloader.conf").read_text(encoding="utf-8")
    )

    # The erase layout has a GPT BIOS boot partition and an ESP. Mounting the
    # ESP at /boot keeps kernels and initramfs readable by GRUB outside the
    # compressed, encrypted Btrfs root. Install both GRUB targets into the
    # matching ESP and BIOS boot partition.
    assert partition["createHybridBootloaderLayout"] is True
    assert partition["efi"]["mountPoint"] == "/boot"
    assert bootloader["efiBootLoader"] == "grub"
    assert bootloader["installHybridGRUB"] is True


def test_encrypted_root_unlocks_before_mount_without_embedded_keyfile() -> None:
    settings = yaml.safe_load((ROOT / "image/calamares/settings.conf").read_text(encoding="utf-8"))
    modules = settings["sequence"][1]["exec"]
    initcpio = yaml.safe_load(
        (ROOT / "image/calamares/modules/initcpiocfg.conf").read_text(encoding="utf-8")
    )
    grub = yaml.safe_load(
        (ROOT / "image/calamares/modules/grubcfg.conf").read_text(encoding="utf-8")
    )

    assert modules.index("initcpiocfg") < modules.index("initcpio") < modules.index("grubcfg")
    assert modules.index("grubcfg") < modules.index("bootloader")
    assert initcpio["hooks"]["remove"] == ["filesystems", "fsck"]
    assert initcpio["hooks"]["append"] == ["encrypt", "filesystems", "fsck"]
    assert "luksbootkeyfile" not in modules
    assert "cryptdevice=UUID=" not in grub.get("kernel_params", [])

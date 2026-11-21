"""Initramfs generation contracts learned from a real failed install.

On the maintainer's ASUS (UEFI, Btrfs, LUKS root, encrypted swap),
Calamares generated an mkinitcpio.conf with a duplicate `encrypt` hook
and an `openswap` hook that exists neither in stock mkinitcpio nor in
the target, so `mkinitcpio` exited 1 after partitioning. These tests
pin the configuration side of that failure.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "image/calamares/modules"


def test_initcpiocfg_keeps_single_encrypt_hook_source():
    conf = yaml.safe_load((MODULES / "initcpiocfg.conf").read_text(encoding="utf-8"))
    append = conf["hooks"]["append"]
    # Exactly one configured `encrypt` (the bootloader-layout contract);
    # the duplicate seen on hardware came from generation, not config.
    assert append.count("encrypt") == 1
    assert append == ["encrypt", "filesystems", "fsck"]


def test_swap_choices_never_generate_openswap():
    # `file` is safe (Btrfs swapfile on /@swap via fstab, no openswap
    # hook). A swap *partition* (`small`, installer#113) is offered
    # only without LUKS: apply-system-plan.py aborts partition+LUKS
    # before packages, since only that combination generates the
    # missing openswap hook. Hibernation (`suspend`) is never offered
    # (openswap is not pinned). Default remains `none` (preview32).
    conf = yaml.safe_load((MODULES / "partition.conf").read_text(encoding="utf-8"))
    assert conf["userSwapChoices"] == ["none", "file", "small"]
    assert "suspend" not in conf["userSwapChoices"]
    assert "partition" not in conf["userSwapChoices"]
    assert conf["initialSwapChoice"] == "none"

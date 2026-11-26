"""Wave 2 remediation regression tests (#121, #122, #123, #124)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"
ARCHISO = ROOT / "image/archiso"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_mod = _load("apply_system_plan_w2", CALAMARES / "apply-system-plan.py")
choices_mod = _load("apply_system_choices_w2", CALAMARES / "apply-system-choices.py")


def test_dkms_headers_added_on_single_kernel_install(tmp_path):
    allowlist = plan_mod.load_allowlist()
    selection = dict(plan_mod.DEFAULT_SELECTION)
    assert plan_mod.kernel_packages(selection, allowlist, dkms=True) == [
        "linux",
        "linux-headers",
    ]

    # Target with nvidia-open-dkms installed in pacman local DB, no plan file.
    (tmp_path / "var/lib/pacman/local/nvidia-open-dkms-560.35.03-1").mkdir(parents=True)
    ran: list[list[str]] = []
    choices_mod.apply_system_choices(
        tmp_path,
        allowlist,
        runner=lambda argv: (ran.append(argv), 0)[1],
    )
    assert any("linux-headers" in cmd for cmd in ran)


def test_pciutils_and_safe_graphics_live_boot_entries():
    pkgs = {
        line.strip()
        for line in (ARCHISO / "packages.x86_64").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "pciutils" in pkgs

    uefi_safe = (
        ARCHISO / "efiboot/loader/entries/02-horneroos-safe-graphics.conf"
    ).read_text()
    assert "Safe Graphics" in uefi_safe
    assert "nomodeset" in uefi_safe
    assert "WLR_RENDERER=pixman" in uefi_safe

    bios_cfg = (ARCHISO / "syslinux/syslinux.cfg").read_text()
    assert "LABEL hornero-safe" in bios_cfg
    assert "nomodeset" in bios_cfg
    assert "WLR_RENDERER=pixman" in bios_cfg


def test_luks2_sd_encrypt_esp_zram_and_ucode(tmp_path):
    partition = yaml.safe_load((CALAMARES / "modules/partition.conf").read_text())
    assert partition["luksGeneration"] == "luks2"
    assert partition["efi"]["recommendedSize"] == "1024MiB"

    initcpio = yaml.safe_load((CALAMARES / "modules/initcpiocfg.conf").read_text())
    assert initcpio["useSystemdHook"] is True
    assert "sd-encrypt" in initcpio["hooks"]["append"]

    zram_conf = choices_mod.configure_zram(tmp_path)
    assert "[zram0]" in zram_conf.read_text()

    amd_cpu = tmp_path / "cpuinfo-amd"
    amd_cpu.write_text("vendor_id\t: AuthenticAMD\n")
    assert choices_mod.detect_cpu_ucode(amd_cpu) == "amd-ucode"

    intel_cpu = tmp_path / "cpuinfo-intel"
    intel_cpu.write_text("vendor_id\t: GenuineIntel\n")
    assert choices_mod.detect_cpu_ucode(intel_cpu) == "intel-ucode"


def test_issue_124_fixes():
    launcher = (ARCHISO / "airootfs/usr/local/bin/hornero-installer-start").read_text()
    assert "getent ahosts archive.archlinux.org" in launcher
    assert "ahostsv4" not in launcher

    netinstall = (CALAMARES / "modules/netinstall.conf").read_text()
    assert "\n    - graphite\n" not in netinstall

    grubcfg = yaml.safe_load((CALAMARES / "modules/grubcfg.conf").read_text())
    assert "nvidia_drm.modeset=1" in grubcfg["kernel_params"]
    assert grubcfg["defaults"]["GRUB_DISABLE_OS_PROBER"] is False

    sys_cpp = (CALAMARES / "viewmodules/hornerosystem/HorneroSystemConfig.cpp").read_text()
    assert "/run/hornero-installer/offline-mode" in sys_cpp
    assert "QFile::remove( m_selectionPath )" in sys_cpp

    users_cpp = (CALAMARES / "viewmodules/hornerousers/HorneroUsersConfig.cpp").read_text()
    assert "QFile::remove( m_selectionPath )" in users_cpp

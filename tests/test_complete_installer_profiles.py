"""Tests for complete installer profiles, hardware detection, preflight, and post-install verification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


choices_mod = _load("apply_system_choices_complete", CALAMARES / "apply-system-choices.py")
probe_mod = _load("probe_gpu_complete", CALAMARES / "probe-gpu.py")
preflight_mod = _load("preflight_payload_complete", CALAMARES / "preflight-payload.py")
verify_mod = _load("verify_install_complete", CALAMARES / "verify-install.py")
plan_mod = _load("apply_system_plan_complete", CALAMARES / "apply-system-plan.py")


def test_default_install_configures_zram_and_planned_installs_cpu_ucode(tmp_path):
    allowlist = plan_mod.load_allowlist()
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("vendor_id\t: AuthenticAMD\n", encoding="utf-8")
    ran: list[list[str]] = []

    # Default install (no plan): writes zram-generator.conf without running pacman
    result = choices_mod.apply_system_choices(
        tmp_path,
        allowlist,
        runner=lambda argv: (ran.append(argv), 0)[1],
        offline=False,
        cpuinfo_path=cpuinfo,
    )
    assert result is None
    assert ran == []
    zram = tmp_path / "etc/systemd/zram-generator.conf"
    assert zram.is_file()
    assert "[zram0]" in zram.read_text(encoding="utf-8")

    # Planned install (online): installs matching CPU microcode
    plan_path = tmp_path / "usr/lib/hornero/installation-plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps({"selection": {"kernels": ["linux"], "bootloader": "grub", "services": {}}}),
        encoding="utf-8",
    )
    planned = choices_mod.apply_system_choices(
        tmp_path,
        allowlist,
        runner=lambda argv: (ran.append(argv), 0)[1],
        offline=False,
        cpuinfo_path=cpuinfo,
    )
    assert planned is not None
    assert planned["ucode"] == "amd-ucode"
    assert any("amd-ucode" in cmd for cmd in ran)


def test_planned_install_skips_ucode_when_offline(tmp_path):
    allowlist = plan_mod.load_allowlist()
    plan_path = tmp_path / "usr/lib/hornero/installation-plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps({"selection": {"kernels": ["linux"], "bootloader": "grub", "services": {}}}),
        encoding="utf-8",
    )
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("vendor_id\t: GenuineIntel\n", encoding="utf-8")
    ran: list[list[str]] = []

    result = choices_mod.apply_system_choices(
        tmp_path,
        allowlist,
        runner=lambda argv: (ran.append(argv), 0)[1],
        offline=True,
        cpuinfo_path=cpuinfo,
    )
    assert result is not None
    assert result["ucode"] is None
    assert not any("intel-ucode" in cmd for cmd in ran)
    assert (tmp_path / "etc/systemd/zram-generator.conf").is_file()


def test_probe_hardware_detects_gpu_vm_and_cpu():
    lspci = "\n".join([
        "00:02.0 VGA compatible controller [0300]: Red Hat, Inc. Virtio GPU [1af4:1050] (rev 01)",
        "01:00.0 VGA compatible controller [0300]: Advanced Micro Devices [AMD] [1002:67df]",
        "02:00.0 System peripheral [0880]: VMware Virtual Machine Communication Interface [15ad:0740]",
    ])
    cpuinfo = "processor\t: 0\nvendor_id\t: AuthenticAMD\n"

    hw = probe_mod.probe_hardware(lspci_text=lspci, cpuinfo_text=cpuinfo)
    assert hw["schemaVersion"] == 2
    assert hw["vendors"] == ["amd"]
    assert hw["vmHypervisors"] == ["qemu", "vmware"]
    assert "qemu-guest-agent" in hw["guestPackages"]
    assert "open-vm-tools" in hw["guestPackages"]
    assert hw["cpuVendor"] == "amd"
    assert hw["microcodePackage"] == "amd-ucode"


def test_preflight_environment_checks_uefi_ram_and_battery(tmp_path):
    (tmp_path / "sys/firmware/efi").mkdir(parents=True)
    (tmp_path / "proc").mkdir(parents=True)
    (tmp_path / "proc/meminfo").write_text("MemTotal:        3072000 kB\n", encoding="utf-8")
    bat = tmp_path / "sys/class/power_supply/BAT0"
    bat.mkdir(parents=True)
    (bat / "status").write_text("Discharging\n", encoding="utf-8")

    env = preflight_mod.preflight_environment(tmp_path)
    assert env["firmware"] == "uefi"
    assert env["ramMiB"] == 3000
    assert env["onBattery"] is True
    assert env["errors"] == []
    assert len(env["warnings"]) == 2


def test_verify_install_checks_zram_and_sd_encrypt_hooks(tmp_path):
    (tmp_path / "boot/grub").mkdir(parents=True)
    (tmp_path / "boot/grub/grub.cfg").write_text("menuentry 'Hornero' {}", encoding="utf-8")
    (tmp_path / "boot/vmlinuz-linux").write_bytes(b"kernel")
    (tmp_path / "boot/initramfs-linux.img").write_bytes(b"initramfs")
    (tmp_path / "etc/systemd").mkdir(parents=True)
    (tmp_path / "etc/os-release").write_text("ID=hornero\n", encoding="utf-8")
    (tmp_path / "etc/passwd").write_text("alice:x:1000:1000::/home/alice:/bin/bash\n", encoding="utf-8")

    # Broken zram config and broken sd-encrypt without systemd hook
    (tmp_path / "etc/systemd/zram-generator.conf").write_text("# empty\n", encoding="utf-8")
    (tmp_path / "etc/mkinitcpio.conf").write_text("HOOKS=(base udev sd-encrypt filesystems)\n", encoding="utf-8")

    problems = verify_mod.verify_install(tmp_path)
    assert any("zram-generator" in p for p in problems)
    assert any("sd-encrypt without systemd" in p for p in problems)

    # Fix both -> zero problems
    (tmp_path / "etc/systemd/zram-generator.conf").write_text("[zram0]\n", encoding="utf-8")
    (tmp_path / "etc/mkinitcpio.conf").write_text("HOOKS=(base systemd sd-encrypt filesystems)\n", encoding="utf-8")
    assert verify_mod.verify_install(tmp_path) == []

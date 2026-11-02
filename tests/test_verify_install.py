"""The target must be verifiably bootable before Calamares says done."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "verify_install", ROOT / "image/calamares/verify-install.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _complete_target(tmp_path: Path) -> Path:
    boot = tmp_path / "boot/grub"
    boot.mkdir(parents=True)
    (boot / "grub.cfg").write_text("menuentry 'HorneroOS' {}\n", encoding="utf-8")
    (tmp_path / "boot/vmlinuz-linux").write_bytes(b"kernel")
    (tmp_path / "boot/initramfs-linux.img").write_bytes(b"initramfs")
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "os-release").write_text("ID=horneroos\n", encoding="utf-8")
    (etc / "passwd").write_text(
        "root:x:0:0::/root:/usr/bin/bash\nhornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n",
        encoding="utf-8",
    )
    (etc / "pacman.conf").write_text("[core]\nInclude = /etc/pacman.d/mirrorlist\n", encoding="utf-8")
    return tmp_path


def test_complete_target_passes(tmp_path):
    assert mod.verify_install(_complete_target(tmp_path)) == []


def test_missing_grub_cfg_fails(tmp_path):
    root = _complete_target(tmp_path)
    (root / "boot/grub/grub.cfg").unlink()
    problems = mod.verify_install(root)
    assert any("GRUB" in p for p in problems)


def test_missing_initramfs_fails(tmp_path):
    root = _complete_target(tmp_path)
    (root / "boot/initramfs-linux.img").unlink()
    problems = mod.verify_install(root)
    assert any("initramfs" in p for p in problems)


def test_installer_repo_left_enabled_fails(tmp_path):
    root = _complete_target(tmp_path)
    (root / "etc/pacman.conf").write_text(
        "[hornero-installer]\nServer = file:///x\n", encoding="utf-8"
    )
    problems = mod.verify_install(root)
    assert any("installer-only" in p for p in problems)


def test_wiring():
    settings = (ROOT / "image/calamares/settings.conf").read_text(encoding="utf-8")
    assert "shellprocess@verify" in settings
    seq = settings.split("exec:")[1]
    assert seq.index("bootloader") < seq.index("shellprocess@verify") < seq.index("umount")
    conf = ROOT / "image/calamares/modules/shellprocess-verify.conf"
    assert "verify-install.py" in conf.read_text(encoding="utf-8")
    builder = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert "verify-install.py" in builder


PLAN = {
    "schemaVersion": 2,
    "selection": {
        "edition": "desktop", "kernels": ["linux", "linux-lts"],
        "primaryKernel": "linux", "bootloader": "systemd-boot",
        "firmware": "uefi", "capabilities": ["bluetooth"],
    },
    "packages": [], "services": ["bluetooth.service"],
    "espRecommendedMiB": 1280, "planWarnings": [],
}


def _plan_target(tmp_path: Path) -> Path:
    root = _complete_target(tmp_path)
    (root / "boot/vmlinuz-linux-lts").write_bytes(b"kernel")
    (root / "boot/initramfs-linux-lts.img").write_bytes(b"initramfs")
    entries = root / "boot/loader/entries"
    entries.mkdir(parents=True)
    (root / "boot/loader/loader.conf").write_text("default linux\n", encoding="utf-8")
    (entries / "linux.conf").write_text("linux /vmlinuz-linux\n", encoding="utf-8")
    (entries / "linux-lts.conf").write_text("linux /vmlinuz-linux-lts\n", encoding="utf-8")
    return root


def test_plan_systemd_boot_dual_kernel_passes(tmp_path):
    assert mod.verify_install(_plan_target(tmp_path), plan=PLAN) == []


def test_plan_missing_second_kernel_fails(tmp_path):
    root = _plan_target(tmp_path)
    (root / "boot/vmlinuz-linux-lts").unlink()
    problems = mod.verify_install(root, plan=PLAN)
    assert any("linux-lts" in p for p in problems)


def test_plan_missing_systemd_boot_entry_fails(tmp_path):
    root = _plan_target(tmp_path)
    (root / "boot/loader/entries/linux-lts.conf").unlink()
    problems = mod.verify_install(root, plan=PLAN)
    assert any("systemd-boot entry" in p for p in problems)


def test_plan_capability_service_not_enabled_fails(tmp_path):
    root = _plan_target(tmp_path)
    unit = root / "usr/lib/systemd/system/bluetooth.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]\n", encoding="utf-8")
    problems = mod.verify_install(root, plan=PLAN)
    assert any("bluetooth.service installed but not enabled" in p for p in problems)

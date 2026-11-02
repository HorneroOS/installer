"""Bluetooth reachability on installed targets and in the live session.

Installed packages come from the pinned HorneroOS/hornero catalogue;
this repository owns service enablement, the live session, target
verification, and the documented catalogue hand-off.
"""
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHISO = ROOT / "image/archiso"
MODULES = ROOT / "image/calamares/modules"

_spec = importlib.util.spec_from_file_location(
    "verify_install", ROOT / "image/calamares/verify-install.py"
)
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)


def _live_packages():
    return {
        line.strip()
        for line in (ARCHISO / "packages.x86_64").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _complete_target(tmp_path: Path) -> Path:
    (tmp_path / "boot/grub").mkdir(parents=True)
    (tmp_path / "boot/grub/grub.cfg").write_text("menuentry {}\n", encoding="utf-8")
    (tmp_path / "boot/vmlinuz-linux").write_bytes(b"k")
    (tmp_path / "boot/initramfs-linux.img").write_bytes(b"i")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text("ID=horneroos\n", encoding="utf-8")
    (tmp_path / "etc/passwd").write_text(
        "hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n", encoding="utf-8"
    )
    (tmp_path / "etc/pacman.conf").write_text("[core]\n", encoding="utf-8")
    return tmp_path


def test_bluetooth_service_enabled_not_mandatory():
    conf = yaml.safe_load((MODULES / "services-systemd.conf").read_text(encoding="utf-8"))
    units = [u for u in conf["units"] if u.get("name") == "bluetooth.service"]
    # mandatory: false — a Bluetooth-less VM/server install must not fail.
    assert units == [
        {"name": "bluetooth.service", "action": "enable", "mandatory": False}
    ]


def test_live_session_has_bluetooth_stack_and_firmware():
    pkgs = _live_packages()
    assert {"bluez", "bluez-utils", "linux-firmware"} <= pkgs
    link = ARCHISO / "airootfs/etc/systemd/system/multi-user.target.wants/bluetooth.service"
    assert link.is_symlink()
    assert link.readlink().as_posix() == "/usr/lib/systemd/system/bluetooth.service"


def test_every_composition_carries_firmware_and_consistent_bluez():
    compositions = json.loads((MODULES / "compositions.json").read_text(encoding="utf-8"))
    assert compositions["options"]
    assert all("linux-firmware" in o["packages"] for o in compositions["options"])
    # bluez/bluez-utils arrive via the catalogue desktop set (Studio and
    # Gaming extend Desktop): either every option has them or the
    # hand-off has not been rendered yet — never a partial rollout.
    flags = [{"bluez", "bluez-utils"} <= set(o["packages"]) for o in compositions["options"]]
    assert all(flags) or not any(flags)


def test_verify_passes_without_bluez(tmp_path):
    assert verify.verify_install(_complete_target(tmp_path)) == []


def test_verify_fails_when_bluez_installed_but_not_enabled(tmp_path):
    root = _complete_target(tmp_path)
    unit = root / "usr/lib/systemd/system/bluetooth.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]\n", encoding="utf-8")
    problems = verify.verify_install(root)
    assert any("bluetooth.service installed but not enabled" in p for p in problems)
    # `systemctl enable bluetooth` files the link under
    # bluetooth.target.wants (the unit's [Install] WantedBy), not
    # multi-user.target.wants — the gate must accept what enable
    # actually creates or every bluez install fails (preview30 VM).
    wants = root / "etc/systemd/system/bluetooth.target.wants"
    wants.mkdir(parents=True)
    (wants / "bluetooth.service").symlink_to("/usr/lib/systemd/system/bluetooth.service")
    assert verify.verify_install(root) == []


def test_catalogue_and_migration_handoff_documented():
    doc = (ROOT / "docs/calamares-provisional.md").read_text(encoding="utf-8")
    assert "render-installer-catalogue.py" in doc
    assert "bluez-utils" in doc
    assert "Preview24/29" in doc
    assert "installer.lock.yaml" in doc

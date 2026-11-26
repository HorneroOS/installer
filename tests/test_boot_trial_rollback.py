"""Tests for Btrfs snapshot boot-trial ALPM hook and boot-confirm service."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


choices_mod = _load("apply_system_choices_boot_trial", CALAMARES / "apply-system-choices.py")
verify_mod = _load("verify_install_boot_trial", CALAMARES / "verify-install.py")
plan_mod = _load("apply_system_plan_boot_trial", CALAMARES / "apply-system-plan.py")


def _minimal_bootable_target(root: Path) -> Path:
    (root / "boot/grub").mkdir(parents=True, exist_ok=True)
    (root / "boot/grub/grub.cfg").write_text("menuentry 'HorneroOS' { linux /vmlinuz-linux }\n", encoding="utf-8")
    (root / "boot/vmlinuz-linux").write_bytes(b"kernel")
    (root / "boot/initramfs-linux.img").write_bytes(b"initramfs")
    (root / "boot/initramfs-linux-fallback.img").write_bytes(b"initramfs-fallback")
    (root / "etc").mkdir(parents=True, exist_ok=True)
    (root / "etc/os-release").write_text("ID=horneroos\n", encoding="utf-8")
    (root / "etc/passwd").write_text("hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n", encoding="utf-8")
    (root / "etc/pacman.conf").write_text("[core]\n", encoding="utf-8")
    return root


def test_configure_boot_trial_rollback_contents_and_idempotency(tmp_path):
    first = choices_mod.configure_boot_trial_rollback(tmp_path)
    assert first == {
        "unit": "usr/lib/systemd/system/hornero-boot-confirm.service",
        "wants": "etc/systemd/system/graphical.target.wants/hornero-boot-confirm.service",
        "hook": "etc/pacman.d/hooks/95-hornero-boot-trial.hook",
    }

    unit = tmp_path / first["unit"]
    wants = tmp_path / first["wants"]
    hook = tmp_path / first["hook"]

    assert unit.is_file()
    unit_text = unit.read_text(encoding="utf-8")
    assert "[Unit]" in unit_text
    assert "After=graphical.target" in unit_text
    assert "ConditionPathExists=/var/lib/hornero/boot-trial.pending" in unit_text
    assert "[Service]" in unit_text
    assert "boot-confirmed" in unit_text
    assert "[Install]" in unit_text
    assert "WantedBy=graphical.target" in unit_text

    assert wants.is_symlink()
    assert str(wants.readlink()) == "/usr/lib/systemd/system/hornero-boot-confirm.service"

    assert hook.is_file()
    hook_text = hook.read_text(encoding="utf-8")
    assert "[Trigger]" in hook_text
    assert "Operation = Install" in hook_text
    assert "Operation = Upgrade" in hook_text
    assert "Type = Path" in hook_text
    assert "Target = usr/lib/modules/*/vmlinuz" in hook_text
    assert "Target = boot/initramfs-*.img" in hook_text
    assert "[Action]" in hook_text
    assert "When = PostTransaction" in hook_text
    assert "boot-trial.tries" in hook_text
    assert "boot-trial.pending" in hook_text

    # Idempotent second run
    second = choices_mod.configure_boot_trial_rollback(tmp_path)
    assert second == first
    assert unit.read_text(encoding="utf-8") == unit_text
    assert hook.read_text(encoding="utf-8") == hook_text


def test_configure_boot_trial_rollback_disabled_and_symlink_guard(tmp_path):
    assert choices_mod.configure_boot_trial_rollback(tmp_path, enabled=False) is None
    assert not (tmp_path / "usr/lib/systemd/system/hornero-boot-confirm.service").exists()

    hook_path = tmp_path / "etc/pacman.d/hooks/95-hornero-boot-trial.hook"
    hook_path.parent.mkdir(parents=True)
    hook_path.symlink_to("/tmp/outside")
    with pytest.raises(ValueError, match="Refusing symlink"):
        choices_mod.configure_boot_trial_rollback(tmp_path, enabled=True)


def test_apply_system_choices_wires_boot_trial_for_planned_and_snapper_installs(tmp_path):
    allowlist = plan_mod.load_allowlist()
    ran: list[list[str]] = []

    # Planned install with snapshots enabled (default)
    planned_root = tmp_path / "planned"
    plan_path = planned_root / "usr/lib/hornero/installation-plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps({"selection": {"kernels": ["linux"], "bootloader": "grub", "services": {}, "snapshots": True}}),
        encoding="utf-8",
    )
    res = choices_mod.apply_system_choices(
        planned_root, allowlist, runner=lambda argv: (ran.append(argv), 0)[1], offline=True
    )
    assert res is not None
    assert res["bootTrial"] is not None
    assert (planned_root / "usr/lib/systemd/system/hornero-boot-confirm.service").is_file()
    assert (planned_root / "etc/pacman.d/hooks/95-hornero-boot-trial.hook").is_file()

    # Planned install with snapshots explicitly disabled
    optout_root = tmp_path / "optout"
    optout_plan = optout_root / "usr/lib/hornero/installation-plan.json"
    optout_plan.parent.mkdir(parents=True)
    optout_plan.write_text(
        json.dumps({"selection": {"kernels": ["linux"], "bootloader": "grub", "services": {}, "snapshots": False}}),
        encoding="utf-8",
    )
    res_optout = choices_mod.apply_system_choices(
        optout_root, allowlist, runner=lambda argv: (ran.append(argv), 0)[1], offline=True
    )
    assert res_optout is not None
    assert res_optout["bootTrial"] is None
    assert not (optout_root / "usr/lib/systemd/system/hornero-boot-confirm.service").exists()

    # No-plan install with Snapper root config present
    snapper_root = tmp_path / "snapper"
    snapper_cfg = snapper_root / "etc/snapper/configs/root"
    snapper_cfg.parent.mkdir(parents=True)
    snapper_cfg.write_text('SUBVOLUME="/"\n', encoding="utf-8")
    assert choices_mod.apply_system_choices(
        snapper_root, allowlist, runner=lambda argv: (ran.append(argv), 0)[1], offline=True
    ) is None
    assert (snapper_root / "usr/lib/systemd/system/hornero-boot-confirm.service").is_file()
    assert (snapper_root / "etc/pacman.d/hooks/95-hornero-boot-trial.hook").is_file()


def test_verify_install_checks_boot_trial_unit_symlink_and_hook(tmp_path):
    root = _minimal_bootable_target(tmp_path)
    plan = {"selection": {"kernels": ["linux"], "bootloader": "grub", "snapshots": True}}

    # Missing unit & hook when snapshots=True -> fails
    problems = verify_mod.verify_install(root, plan=plan)
    assert any("boot-confirm systemd service" in p for p in problems)
    assert any("boot-trial pacman ALPM hook" in p for p in problems)

    # Provision -> passes cleanly
    choices_mod.configure_boot_trial_rollback(root)
    assert verify_mod.verify_install(root, plan=plan) == []

    # Remove enablement symlink -> fails
    (root / "etc/systemd/system/graphical.target.wants/hornero-boot-confirm.service").unlink()
    problems = verify_mod.verify_install(root, plan=plan)
    assert any("hornero-boot-confirm.service installed but not enabled" in p for p in problems)

    # Restore symlink, corrupt hook -> fails
    (root / "etc/systemd/system/graphical.target.wants/hornero-boot-confirm.service").symlink_to(
        "/usr/lib/systemd/system/hornero-boot-confirm.service"
    )
    (root / "etc/pacman.d/hooks/95-hornero-boot-trial.hook").write_text("# broken\n", encoding="utf-8")
    problems = verify_mod.verify_install(root, plan=plan)
    assert any("invalid boot-trial ALPM hook" in p for p in problems)

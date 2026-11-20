"""PR-B system choices: plan validation, defaults, and target effects."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_mod = _load("apply_system_plan", CALAMARES / "apply-system-plan.py")
choices_mod = _load("apply_system_choices", CALAMARES / "apply-system-choices.py")
defaults_mod = _load("configure_user_defaults", CALAMARES / "configure-user-defaults.py")
ALLOWLIST = plan_mod.load_allowlist()


def _selection(**overrides):
    selection = dict(plan_mod.DEFAULT_SELECTION)
    selection.update(overrides)
    return selection


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "etc/systemd/system").mkdir(parents=True)
    (root / "usr/lib/systemd/system").mkdir(parents=True)
    (root / "usr/lib/hornero").mkdir(parents=True)
    (root / "etc/default").mkdir(parents=True)
    return root


def test_default_selection_packages_match_current_compositions():
    compositions = json.loads((CALAMARES / "modules/compositions.json").read_text())
    desktop = next(o for o in compositions["options"] if o["id"] == "desktop-hyprland")
    transformed = plan_mod.transform_packages(desktop["packages"], _selection(), ALLOWLIST)
    assert transformed == desktop["packages"]
    assert plan_mod.kernel_packages(_selection(), ALLOWLIST) == ["linux"]


def test_dual_kernel_headers_and_primary_first():
    selection = _selection(primaryKernel="linux-lts", fallbackKernel="linux")
    assert plan_mod.kernel_packages(selection, ALLOWLIST) == [
        "linux-lts", "linux", "linux-lts-headers", "linux-headers",
    ]
    plan = plan_mod.build_plan(selection, ALLOWLIST)
    assert plan["selection"]["kernels"] == ["linux-lts", "linux"]
    assert plan["espRecommendedMiB"] == 768


def test_lts_substitution_replaces_kernel_exactly_once():
    packages = ["base", "linux", "linux-firmware", "grub"]
    output = plan_mod.transform_packages(packages, _selection(primaryKernel="linux-lts"), ALLOWLIST)
    assert output == ["base", "linux-lts", "linux-firmware", "grub"]
    assert output.count("linux-lts") == 1 and "linux" not in output


@pytest.mark.parametrize("selection,fragment", [
    (_selection(primaryKernel="linux-rt"), "Unknown primary kernel"),
    (_selection(fallbackKernel="linux"), "must differ"),
    (_selection(bootloader="systemd-boot"), "only GRUB is proven"),
    (_selection(swap="partition"), "not offered"),
    (_selection(services={"NetworkManager": False}), "cannot be toggled"),
    (_selection(appearance={"theme": "hornero-signal-day", "shellPreset": "cockpit"}), "not available"),
    (_selection(offline=True, primaryKernel="linux-lts"), "Offline installation"),
])
def test_invalid_selections_rejected(selection, fragment):
    errors = plan_mod.validate_selection(selection, ALLOWLIST)
    assert any(fragment in error for error in errors)


def test_absent_selection_is_noop_and_writes_no_plan(tmp_path):
    root = _root(tmp_path)
    assert plan_mod.apply_system_plan(root, tmp_path / "missing.json", ALLOWLIST) is None
    assert not (root / "usr/lib/hornero/installation-plan.json").exists()
    calls = []
    assert choices_mod.apply_system_choices(root, ALLOWLIST, runner=lambda argv: calls.append(argv) or 0) is None
    assert calls == []


def test_selection_writes_plan_and_is_consumed(tmp_path):
    root = _root(tmp_path)
    selection_file = tmp_path / "system-selection.json"
    selection_file.write_text(json.dumps({"primaryKernel": "linux-lts", "fallbackKernel": "linux"}))
    plan = plan_mod.apply_system_plan(root, selection_file, ALLOWLIST)
    assert plan["selection"]["primaryKernel"] == "linux-lts"
    assert not selection_file.exists()
    saved = json.loads((root / "usr/lib/hornero/installation-plan.json").read_text())
    assert saved["services"] == ["bluetooth.service", "systemd-timesyncd.service"]


def test_kernel_transaction_and_grub_default(tmp_path):
    root = _root(tmp_path)
    (root / "etc/default/grub").write_text('GRUB_DEFAULT=0\nGRUB_TIMEOUT=5\n')
    plan = plan_mod.build_plan(_selection(primaryKernel="linux-lts", fallbackKernel="linux"), ALLOWLIST)
    calls = []
    commands = choices_mod.kernel_transaction(root, plan, ALLOWLIST, runner=lambda argv: calls.append(argv) or 0)
    assert commands[0][:4] == ["arch-chroot", str(root.resolve()), "pacman", "-S"]
    assert "linux-lts" in commands[0] and "linux-lts-headers" in commands[0]
    assert choices_mod.apply_grub_default(root, plan) is True
    text = (root / "etc/default/grub").read_text()
    assert "GRUB_DEFAULT=saved" in text and "GRUB_SAVEDEFAULT=true" in text


def test_services_disable_and_enable_via_wants_symlinks(tmp_path):
    root = _root(tmp_path)
    unit = root / "usr/lib/systemd/system/bluetooth.service"
    unit.write_text("[Unit]\n")
    wants = root / "etc/systemd/system/bluetooth.target.wants"
    wants.mkdir(parents=True)
    (wants / "bluetooth.service").symlink_to("/usr/lib/systemd/system/bluetooth.service")
    plan = plan_mod.build_plan(_selection(services={"bluetooth": False, "timesyncd": True}), ALLOWLIST)
    changed = choices_mod.apply_services(root, plan, ALLOWLIST)
    assert changed == ["disabled bluetooth.service"]
    assert not (wants / "bluetooth.service").exists()


def test_appearance_seeded_from_plan_and_never_overwritten(tmp_path):
    root = _root(tmp_path)
    (root / "etc").mkdir(exist_ok=True)
    (root / "etc/xdg/xfce4").mkdir(parents=True)
    (root / "etc/xdg/xfce4/helpers.rc").write_text("TerminalEmulator=kitty\n")
    (root / "home/ana").mkdir(parents=True)
    (root / "etc/passwd").write_text("ana:x:1000:1000::/home/ana:/usr/bin/zsh\n")
    plan = plan_mod.build_plan(_selection(), ALLOWLIST)
    (root / "usr/lib/hornero/installation-plan.json").write_text(json.dumps(plan))
    defaults_mod.configure_user_defaults(root)
    appearance = json.loads((root / "home/ana/.config/hornero/appearance.json").read_text())
    assert appearance == {"schemaVersion": 1, "shellPreset": "cockpit", "theme": "hornero-signal-night"}


def test_swap_choices_offer_file_but_not_partition():
    partition = yaml.safe_load((CALAMARES / "modules/partition.conf").read_text())
    assert partition["userSwapChoices"] == ["none", "file"]
    assert partition["initialSwapChoice"] == "none"
    mount = yaml.safe_load((CALAMARES / "modules/mount.conf").read_text())
    assert mount["btrfsSwapSubvol"] == "/@swap"

"""Contract tests for the composable installation plan + renderer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_mod = _load("installation_plan", ROOT / "scripts/installation_plan.py")
renderer = _load("render_installer_catalogue", ROOT / "scripts/render-installer-catalogue.py")

CATALOGUE = {
    "editions": {
        "desktop": {"title": "HorneroOS Desktop", "role": "desktop"},
        "server": {"title": "HorneroOS Server", "role": "server"},
    },
    "packageSets": {
        "bootloader:grub": {"packages": ["grub", "efibootmgr"]},
        "bootloader:systemd-boot": {"packages": ["systemd-boot"]},
        "capability:bluetooth": {"packages": ["bluez", "bluez-utils"]},
        "capability:printing": {"packages": ["cups"]},
    },
    "kernels": {
        "linux": {"packages": ["linux"], "headers": "linux-headers", "default": True},
        "linux-lts": {"packages": ["linux-lts"], "headers": "linux-lts-headers"},
    },
    "bootloaders": {
        "grub": {"packageSet": "bootloader:grub", "firmwares": ["uefi", "bios"], "espBaseMiB": 512, "perKernelMiB": 256, "default": True},
        "systemd-boot": {"packageSet": "bootloader:systemd-boot", "firmwares": ["uefi"], "espBaseMiB": 1024, "perKernelMiB": 256},
    },
    "capabilities": {
        "bluetooth": {"packageSet": "capability:bluetooth", "services": ["bluetooth.service"], "appliesTo": ["desktop"]},
        "printing": {"packageSet": "capability:printing", "services": ["cups.service"], "appliesTo": ["desktop"]},
    },
}


def _selection(**overrides):
    base = {
        "edition": "desktop",
        "kernels": ["linux"],
        "primaryKernel": "linux",
        "bootloader": "grub",
        "firmware": "uefi",
        "capabilities": [],
    }
    base.update(overrides)
    return base


def test_default_plan_packages_and_esp():
    plan = plan_mod.build_plan(CATALOGUE, _selection())
    assert plan["schemaVersion"] == 2
    assert plan["packages"] == ["linux", "linux-headers", "grub", "efibootmgr"]
    assert plan["espRecommendedMiB"] == 512


def test_esp_formula_dual_kernel():
    assert plan_mod.esp_recommended_mib(CATALOGUE["bootloaders"]["systemd-boot"], 1) == 1024
    assert plan_mod.esp_recommended_mib(CATALOGUE["bootloaders"]["systemd-boot"], 2) == 1280
    assert plan_mod.esp_recommended_mib(CATALOGUE["bootloaders"]["grub"], 2) == 768


def test_systemd_boot_on_bios_rejected_with_actionable_message():
    errors = plan_mod.validate_selection(
        CATALOGUE, _selection(bootloader="systemd-boot", firmware="bios")
    )
    assert any("systemd-boot needs UEFI" in e for e in errors)


def test_empty_kernels_and_primary_outside_rejected():
    assert "Select at least one kernel." in plan_mod.validate_selection(
        CATALOGUE, _selection(kernels=[], primaryKernel=None)
    )
    errors = plan_mod.validate_selection(CATALOGUE, _selection(primaryKernel="linux-lts"))
    assert "The primary kernel must be one of the installed kernels." in errors


def test_bluetooth_capability_reuses_bluetooth_service_name():
    plan = plan_mod.build_plan(CATALOGUE, _selection(capabilities=["bluetooth"]))
    assert {"bluez", "bluez-utils"} <= set(plan["packages"])
    assert plan["services"] == ["bluetooth.service"]


def test_capability_on_wrong_role_rejected():
    errors = plan_mod.validate_selection(
        CATALOGUE, _selection(edition="server", capabilities=["printing"])
    )
    assert any("not available for" in e for e in errors)


def test_nvidia_multi_kernel_uses_dkms_with_warning():
    plan = plan_mod.build_plan(
        CATALOGUE,
        _selection(kernels=["linux", "linux-lts"], nvidiaModule=True),
    )
    assert "nvidia-open-dkms" in plan["packages"]
    assert "nvidia-open" not in plan["packages"]
    assert plan["planWarnings"]


def test_plan_is_deterministic():
    first = json.dumps(plan_mod.build_plan(CATALOGUE, _selection(capabilities=["bluetooth"])), sort_keys=True)
    second = json.dumps(plan_mod.build_plan(CATALOGUE, _selection(capabilities=["bluetooth"])), sort_keys=True)
    assert first == second


def test_unknown_kernel_raises_with_valid_values():
    with pytest.raises(ValueError, match="Unknown kernel"):
        plan_mod.build_plan(CATALOGUE, _selection(kernels=["linux-zen"], primaryKernel="linux-zen"))


def test_renderer_without_maps_renders_nothing(tmp_path):
    assert renderer.composable_catalogue({"editions": {}}) is None
    assert renderer.render_composable_choosers(tmp_path, {"editions": {}}) == []


def test_renderer_with_maps_renders_choosers_from_catalogue_only(tmp_path):
    written = renderer.render_composable_choosers(tmp_path, CATALOGUE)
    assert "packagechooser-kernel.conf" in written
    kernel = yaml.safe_load((tmp_path / "packagechooser-kernel.conf").read_text(encoding="utf-8"))
    assert [i["id"] for i in kernel["items"]] == ["linux", "linux-lts"]
    assert kernel["items"][0]["packages"] == ["linux", "linux-headers"]
    bootloader = yaml.safe_load((tmp_path / "packagechooser-bootloader.conf").read_text(encoding="utf-8"))
    assert {i["id"] for i in bootloader["items"]} == {"grub", "systemd-boot"}
    caps = yaml.safe_load((tmp_path / "packagechooser-capabilities.conf").read_text(encoding="utf-8"))
    bt = next(i for i in caps["items"] if i["id"] == "bluetooth")
    assert bt["packages"] == ["bluez", "bluez-utils"]


# --- Canonical-catalogue shape contract ---------------------------------
# The REAL HorneroOS catalogue declares direct `packages:` lists on
# kernels/bootloaders/capabilities (no packageSet anywhere). The
# synthetic fixture above must not mask a schema drift: this fixture
# mirrors editions/catalogue.yaml in HorneroOS/hornero exactly.
CANONICAL_SHAPE = {
    "kernels": {
        "linux": {"packages": ["linux"], "headers": "linux-headers", "default": True},
        "linux-lts": {"packages": ["linux-lts"], "headers": "linux-lts-headers"},
    },
    "bootloaders": {
        "grub": {"packages": ["grub", "efibootmgr"], "firmwares": ["uefi", "bios"],
                 "espBaseMiB": 512, "perKernelMiB": 256, "default": True},
        "systemd-boot": {"packages": [], "firmwares": ["uefi"],
                         "espBaseMiB": 1024, "perKernelMiB": 256},
    },
    "capabilities": {
        "bluetooth": {"packages": ["bluez", "bluez-utils"],
                      "services": ["bluetooth.service"],
                      "appliesTo": ["desktop", "studio", "gaming"]},
    },
}


def test_canonical_direct_packages_shape_emits_capability_and_bootloader():
    plan = plan_mod.build_plan(
        CANONICAL_SHAPE,
        _selection(kernels=["linux", "linux-lts"], primaryKernel="linux",
                   capabilities=["bluetooth"]),
    )
    for expected in ("bluez", "bluez-utils", "grub", "efibootmgr",
                     "linux", "linux-headers", "linux-lts", "linux-lts-headers"):
        assert expected in plan["packages"], plan["packages"]
    assert plan["services"] == ["bluetooth.service"]


def test_renderer_canonical_shape_capability_packages_not_empty(tmp_path):
    renderer.render_composable_choosers(tmp_path, CANONICAL_SHAPE)
    conf = yaml.safe_load((tmp_path / "packagechooser-capabilities.conf").read_text())
    items = {item["id"]: item for item in conf["items"]}
    assert items["bluetooth"]["packages"] == ["bluez", "bluez-utils"]

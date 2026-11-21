"""HorneroSystem viewmodule contract (installer#113): page -> selection JSON.

The C++ page cannot run here (no local Calamares build, lightweight
gate), so these tests pin the contract statically and by feeding the
exact JSON shape the page emits to the real backend validator
(apply-system-plan.py). The VM gate is declared in the PR; nothing
here claims it ran.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image/calamares"
VIEWMODULE = CALAMARES / "viewmodules/hornerosystem"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_mod = _load("apply_system_plan_hs", CALAMARES / "apply-system-plan.py")
ALLOWLIST = plan_mod.load_allowlist()


def _text(name: str) -> str:
    return (VIEWMODULE / name).read_text(encoding="utf-8")


def test_viewmodule_registered_and_injected_before_cmake():
    cmake = _text("CMakeLists.txt")
    assert "calamares_add_plugin(hornerosystem" in cmake
    assert "TYPE viewmodule" in cmake
    pkgbuild = (ROOT / "packaging/calamares/PKGBUILD").read_text(encoding="utf-8")
    injection = 'cp -a "$startdir/../../image/calamares/viewmodules/hornerosystem" "$srcdir/calamares/src/modules/hornerosystem"'
    assert injection in pkgbuild
    assert pkgbuild.index(injection) < pkgbuild.index("cmake -S")
    assert re.search(r"^pkgrel=3$", pkgbuild, re.MULTILINE)


def test_page_not_in_show_sequence_until_vm_gate():
    settings = yaml.safe_load((CALAMARES / "settings.conf").read_text(encoding="utf-8"))
    show = settings["sequence"][0]["show"]
    assert "hornerosystem" not in show


def test_config_matches_backend_contract():
    conf = yaml.safe_load((CALAMARES / "modules/hornerosystem.conf").read_text(encoding="utf-8"))
    assert conf["selectionPath"] == "/run/hornero-installer/system-selection.json"
    assert conf["kernels"] == list(ALLOWLIST["kernels"])
    shellprocess = (CALAMARES / "modules/shellprocess-system-plan.conf").read_text(encoding="utf-8")
    assert "apply-system-plan.py" in shellprocess


def test_cpp_gates_present_and_no_theme_selector():
    config = _text("HorneroSystemConfig.cpp")
    page = _text("HorneroSystemPage.cpp")
    assert "systemd-boot needs UEFI" in config
    assert "/sys/firmware/efi" in config
    assert "0600" in config and "O_CLOEXEC" in config
    assert "hornero_bootloader" in config
    assert "isDefaultSelection" in config  # untouched page writes nothing
    # (c) no theme selector: no consumer reads other themes yet.
    assert "theme" not in page.lower()
    assert "hornero-signal-night" in config  # record-only single theme
    assert "suspend" not in page and "hibernat" in page.lower()


def test_page_json_shape_validates_in_backend(tmp_path):
    # Exact shape HorneroSystemConfig::writeSelection emits.
    payload = {
        "primaryKernel": "linux-lts", "fallbackKernel": "linux",
        "bootloader": "systemd-boot", "firmware": "uefi",
        "encryption": "none", "swap": "partition",
        "services": {"bluetooth": False, "timesyncd": True},
        "appearance": {"theme": "hornero-signal-night", "shellPreset": "cockpit"},
        "offline": False,
    }
    selection = dict(plan_mod.DEFAULT_SELECTION)
    selection.update(payload)
    assert plan_mod.validate_selection(selection, ALLOWLIST) == []
    plan = plan_mod.build_plan(selection, ALLOWLIST)
    assert plan["selection"]["bootloader"] == "systemd-boot"
    assert plan["espRecommendedMiB"] == 1280


def test_page_default_shape_is_backend_default():
    selection = dict(plan_mod.DEFAULT_SELECTION)
    assert plan_mod.validate_selection(selection, ALLOWLIST) == []
    assert plan_mod.kernel_packages(selection, ALLOWLIST) == ["linux"]

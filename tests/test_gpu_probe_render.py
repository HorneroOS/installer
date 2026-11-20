"""GPU probe + netinstall GPU groups (installer#115, hornero#466).

Fail-closed: the pinned catalogue (0618004) has no gpuVendors, so no
GPU group renders from it. With a catalogue that ships gpuVendors,
every rendered package needs complete gpuProvenance or rendering
raises. AMD/Intel pre-select only from a PCI probe; NVIDIA never.
"""

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


probe_mod = _load("probe_gpu", ROOT / "image/calamares/probe-gpu.py")
preselect_mod = _load("preselect_gpu", ROOT / "image/calamares/preselect-gpu.py")
render_mod = _load("render_netinstall_gpu", ROOT / "scripts/render-netinstall.py")

LSPCI = """\
00:02.0 VGA compatible controller [0300]: Intel Corporation HD Graphics [8086:1912] (rev 06)
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GP107 [10de:1c82] (rev a1)
02:00.0 3D controller [0302]: Advanced Micro Devices [AMD] [1002:67df] (rev ef)
03:00.0 Ethernet controller [0200]: Intel Corporation I211 [8086:1539]
"""


def _catalogue(with_provenance: bool = True) -> dict:
    catalogue = {
        "gpuVendors": {
            "amd": {"title": "AMD GPU (open Mesa/RADV)", "packages": ["mesa", "vulkan-radeon"],
                    "proprietary": False, "explicitOptIn": False},
            "intel": {"title": "Intel GPU (open Mesa/ANV)", "packages": ["mesa", "vulkan-intel"],
                      "proprietary": False, "explicitOptIn": False},
            "nvidia": {"title": "NVIDIA GPU", "packages": ["nvidia-utils"],
                       "kernelModules": {"linux": "nvidia-open", "linux-lts": "nvidia-open-lts"},
                       "dkmsModule": "nvidia-open-dkms", "dkmsRequiresHeaders": True,
                       "proprietary": True, "explicitOptIn": True},
        },
    }
    if with_provenance:
        def prov(cls="open-source"):
            return {"source": "arch-extra", "sourceUrl": "https://archlinux.org/packages/extra/x86_64/x/",
                    "licenses": ["MIT"], "licenseClass": cls}
        catalogue["gpuProvenance"] = {
            pkg: prov("proprietary" if pkg == "nvidia-utils" else "open-source")
            for pkg in ["mesa", "vulkan-radeon", "vulkan-intel", "nvidia-utils", "nvidia-open-dkms"]
        }
    return catalogue


def test_probe_parses_display_vendors_only():
    assert probe_mod.parse_lspci(LSPCI) == ["intel", "nvidia", "amd"]
    assert probe_mod.probe("") == {"schemaVersion": 1, "vendors": []}
    assert probe_mod.probe("garbage\n")["vendors"] == []


def test_no_gpu_vendors_no_groups_pinned_catalogue():
    assert render_mod.build_gpu_groups({}) == []
    assert render_mod.build_gpu_groups({"capabilities": {}}) == []


def test_gpu_vendors_without_provenance_fails_closed():
    with pytest.raises(ValueError, match="fail-closed"):
        render_mod.build_gpu_groups(_catalogue(with_provenance=False))
    broken = _catalogue()
    del broken["gpuProvenance"]["mesa"]
    with pytest.raises(ValueError, match="lacks complete gpuProvenance"):
        render_mod.build_gpu_groups(broken)


def test_gpu_groups_preselect_open_only_and_nvidia_never():
    groups = render_mod.build_gpu_groups(_catalogue(), probe_vendors=["amd", "nvidia"])
    by_name = {}
    def walk(items):
        for item in items:
            by_name[item["name"]] = item
            walk(item.get("subgroups") or [])
    walk(groups)
    amd = next(v for k, v in by_name.items() if k.startswith("GPU — AMD"))
    intel = next(v for k, v in by_name.items() if k.startswith("GPU — Intel"))
    nvidia = by_name["NVIDIA GPU driver (proprietary)"]
    assert amd["selected"] is True and amd["packages"] == ["mesa", "vulkan-radeon"]
    assert intel["selected"] is False
    assert nvidia["selected"] is False
    assert "licence" in nvidia["description"] or "license" in nvidia["description"].lower()
    assert "nvidia-open-dkms" in nvidia["packages"] and "nvidia-utils" in nvidia["packages"]


def test_preselect_only_touches_detected_open_leaf():
    doc = {"groups": [
        {"name": "GPU drivers (open-source)", "selected": False, "subgroups": [
            {"name": "GPU — AMD GPU (open Mesa/RADV)", "selected": False, "packages": ["mesa"]},
            {"name": "GPU — Intel GPU (open Mesa/ANV)", "selected": False, "packages": ["mesa"]},
        ]},
        {"name": "NVIDIA GPU driver (proprietary)", "selected": False, "packages": ["nvidia-utils"]},
    ]}
    changed = preselect_mod.preselect(doc, ["intel", "nvidia"])
    assert changed == ["GPU — Intel GPU (open Mesa/ANV)"]
    assert doc["groups"][0]["subgroups"][1]["selected"] is True
    assert doc["groups"][1]["selected"] is False


def test_committed_netinstall_has_no_gpu_until_pin_bump():
    conf = yaml.safe_load((ROOT / "image/calamares/modules/netinstall.conf").read_text(encoding="utf-8"))
    names = [g["name"] for g in conf["groups"]]
    assert not any("GPU" in name for name in names), (
        "pinned catalogue 0618004 has no GPU provenance; GPU groups "
        "appear only after hornero#466 merges and the pin bumps"
    )

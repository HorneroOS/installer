"""GPU probe + netinstall GPU groups (installer#115, hornero#466).

Fail-closed: a pinned catalogue without gpuVendors, so no
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


def test_probe_ignores_trailing_subsystem_pci_ids_and_handles_display_classes():
    lspci_subsys = """\
00:02.0 Display controller [0380]: Intel Corporation AlderLake-S GT1 [8086:4680] [1028:0b10] (rev 0c)
01:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23 [1002:73ff] [1458:2400] (rev c7)
02:00.0 VGA compatible controller [0300]: Red Hat, Inc. Virtio GPU [1af4:1050] (rev 01)
03:00.0 3D controller [0302]: NVIDIA Corporation GA107M [10de:25a0] [1028:0b10] (rev a1)
"""
    assert probe_mod.parse_lspci(lspci_subsys) == ["intel", "amd", "nvidia"]


def test_gpu_vendors_rejects_proprietary_in_open_group_and_unmarked_nvidia():
    bad_open = _catalogue()
    bad_open["gpuProvenance"]["mesa"]["licenseClass"] = "proprietary"
    with pytest.raises(ValueError, match="proprietary inside an open-source GPU group"):
        render_mod.build_gpu_groups(bad_open)

    bad_nvidia = _catalogue()
    bad_nvidia["gpuVendors"]["nvidia"]["explicitOptIn"] = False
    with pytest.raises(ValueError, match="explicitOptIn: true"):
        render_mod.build_gpu_groups(bad_nvidia)


def test_preselect_re_run_clears_stale_and_fails_closed_on_bad_input(tmp_path):
    doc = {"groups": [
        {"name": "GPU drivers (open-source)", "selected": False, "subgroups": [
            {"name": "GPU — AMD GPU (open Mesa/RADV)", "selected": True, "packages": ["mesa"]},
            {"name": "GPU — Intel GPU (open Mesa/ANV)", "selected": False, "packages": ["mesa"]},
        ]},
        {"name": "NVIDIA GPU driver (proprietary)", "selected": False, "packages": ["nvidia-utils"]},
    ]}
    changed = preselect_mod.preselect(doc, ["intel", "nvidia"])
    assert set(changed) == {"GPU — AMD GPU (open Mesa/RADV)", "GPU — Intel GPU (open Mesa/ANV)"}
    assert doc["groups"][0]["subgroups"][0]["selected"] is False
    assert doc["groups"][0]["subgroups"][1]["selected"] is True
    assert doc["groups"][1]["selected"] is False

    import subprocess
    probe_file = tmp_path / "probe.json"
    net_file = tmp_path / "netinstall.conf"
    probe_file.write_text('["not-an-object"]\n', encoding="utf-8")
    original = yaml.safe_dump(doc, sort_keys=False)
    net_file.write_text(original, encoding="utf-8")
    res = subprocess.run(
        ["python3", str(ROOT / "image/calamares/preselect-gpu.py"),
         "--probe", str(probe_file), "--netinstall", str(net_file)],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 1
    assert net_file.read_text(encoding="utf-8") == original

    probe_file.write_text('{"vendors": "amd"}\n', encoding="utf-8")
    res2 = subprocess.run(
        ["python3", str(ROOT / "image/calamares/preselect-gpu.py"),
         "--probe", str(probe_file), "--netinstall", str(net_file)],
        capture_output=True, text=True, check=False,
    )
    assert res2.returncode == 1
    assert net_file.read_text(encoding="utf-8") == original


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


def test_committed_netinstall_has_gpu_after_pin_bump():
    conf = yaml.safe_load((ROOT / "image/calamares/modules/netinstall.conf").read_text(encoding="utf-8"))
    names = [g["name"] for g in conf["groups"]]
    assert any("GPU" in name for name in names), (
        "pinned catalogue 8c0d13c ships GPU provenance (hornero#466 merged); "
        "GPU groups must be rendered"
    )

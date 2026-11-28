"""Tests for the HorneroOS VM QCOW2 builder, virtual-GPU detector, and live demo prep."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUILD_VM_SCRIPT = ROOT / "scripts" / "build-vm-image.sh"
GPU_DETECT_SCRIPT = ROOT / "image" / "vm" / "hornero-vm-gpu-detect.sh"
DEMO_PREP_SCRIPT = ROOT / "image" / "archiso" / "airootfs" / "usr" / "local" / "bin" / "hornero-live-demo-prep"
LIVE_SETUP_SCRIPT = ROOT / "image" / "archiso" / "airootfs" / "usr" / "local" / "bin" / "hornero-live-session-setup"
LOCK_FILE = ROOT / "installer.lock.yaml"

CATALOGUE_FIXTURE = {
    "apiVersion": "hornero.os/v1",
    "kind": "EditionCatalogue",
    "version": 1,
    "base": {
        "packages": [
            "base",
            "linux",
            "linux-firmware",
            "sudo",
            "dosfstools",
            "efibootmgr",
            "e2fsprogs",
        ]
    },
    "packageSets": {
        "desktop": {
            "packages": [
                "hornero-shell",
                "hornero-config",
                "horneroctl-bin",
                "quickshell",
                "kitty",
                "sddm",
                "hornero-greeter",
            ]
        },
        "compositor:hyprland": {
            "packages": ["hyprland", "xdg-desktop-portal-hyprland"]
        },
        "compositor:niri": {
            "packages": ["niri", "xwayland-satellite", "xdg-desktop-portal-gnome"]
        },
        "studio": {
            "packages": ["pipewire-jack", "qpwgraph", "ardour", "obs-studio"]
        },
        "gaming": {
            "packages": ["vulkan-icd-loader", "gamemode", "gamescope", "mangohud"]
        },
    },
    "compositors": {
        "hyprland": {"maturity": "supported", "packageSet": "compositor:hyprland"},
        "niri": {"maturity": "experimental", "packageSet": "compositor:niri"},
    },
    "capabilities": {
        "bluetooth": {
            "packages": ["bluez", "bluez-utils"],
            "services": ["bluetooth.service"],
            "appliesTo": ["desktop", "studio", "gaming"],
            "defaultByEdition": {"desktop": True, "studio": True, "gaming": True},
        }
    },
    "editions": {
        "desktop": {
            "title": "HorneroOS Desktop",
            "maturity": "preview",
            "role": "desktop",
            "packageSets": ["desktop"],
            "compositor": {"default": "hyprland", "supported": ["hyprland", "niri"]},
        },
        "studio": {
            "title": "HorneroOS Studio",
            "maturity": "preview",
            "role": "creative-workstation",
            "extends": "desktop",
            "packageSets": ["studio"],
            "compositor": {"inherit": "desktop"},
        },
        "gaming": {
            "title": "HorneroOS Gaming",
            "maturity": "preview",
            "role": "gaming-workstation",
            "extends": "desktop",
            "packageSets": ["gaming"],
            "compositor": {"inherit": "desktop"},
        },
    },
}


def _make_hornero_fixture(tmp_path: Path) -> Path:
    hornero_dir = tmp_path / "hornero"
    editions_dir = hornero_dir / "editions"
    editions_dir.mkdir(parents=True)
    (editions_dir / "catalogue.yaml").write_text(
        yaml.safe_dump(CATALOGUE_FIXTURE, sort_keys=False),
        encoding="utf-8",
    )
    return hornero_dir


def _find_real_hornero_dir() -> Path | None:
    candidates = [
        ROOT.parent / "hornero",
        ROOT.parent / "github.com" / "HorneroOS" / "hornero",
    ]
    for candidate in candidates:
        if (candidate / "editions" / "catalogue.yaml").is_file():
            return candidate
    return None


def _parse_kv(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        parsed[key] = value
    return parsed


def test_build_vm_image_help() -> None:
    res = subprocess.run(
        [str(BUILD_VM_SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "--edition" in res.stdout
    assert "--dry-run" in res.stdout
    assert "--demo" in res.stdout


@pytest.mark.parametrize(
    ("edition", "expected_pkgs"),
    [
        ("desktop", {"base", "linux", "hornero-shell", "hyprland", "bluez"}),
        ("studio", {"base", "hornero-shell", "hyprland", "ardour", "obs-studio"}),
        ("gaming", {"base", "hornero-shell", "hyprland", "gamescope", "mangohud"}),
    ],
)
def test_build_vm_image_dry_run_editions(
    tmp_path: Path, edition: str, expected_pkgs: set[str]
) -> None:
    hornero_dir = _make_hornero_fixture(tmp_path)
    out_dir = tmp_path / "out"
    res = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--edition",
            edition,
            "--hornero-dir",
            str(hornero_dir),
            "--output-dir",
            str(out_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert not out_dir.exists(), "--dry-run must not create output directory or write disks"

    plan = json.loads(res.stdout)
    assert plan["schema"] == "hornero.vm.image/1"
    assert plan["dry_run"] is True
    assert plan["edition"] == edition
    assert plan["compositor"] == "hyprland"
    assert plan["demo_mode"] is False
    assert plan["lock_sha256"] == hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest()
    assert plan["virtual_gpu_profile"]
    assert plan["packages_count"] == len(plan["packages"])
    assert expected_pkgs <= set(plan["packages"])
    assert plan["artifact"] == f"horneroos-2026.10-{edition}-qemu-x86_64.qcow2.zst"
    assert plan["checksum_file"] == f"{plan['artifact']}.sha256"
    assert plan["manifest_file"] == f"{plan['artifact']}.manifest.json"
    assert plan["disk_layout"]["bootloader"] == "systemd-boot"
    assert plan["disk_layout"]["esp"]["size"] == "512M"
    assert "--edition" in plan["build_args"]
    assert edition in plan["build_args"]


def test_build_vm_image_dry_run_demo_niri_and_no_compress(tmp_path: Path) -> None:
    hornero_dir = _make_hornero_fixture(tmp_path)
    res = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--edition",
            "desktop",
            "--compositor",
            "niri",
            "--demo",
            "--no-compress",
            "--disk-size",
            "32G",
            "--version",
            "0.2.0-test",
            "--hornero-dir",
            str(hornero_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    plan = json.loads(res.stdout)
    assert plan["schema"] == "hornero.vm.image/1"
    assert plan["compositor"] == "niri"
    assert plan["demo_mode"] is True
    assert plan["compress"] is False
    assert plan["disk_size"] == "32G"
    assert plan["artifact"] == "horneroos-0.2.0-test-desktop-qemu-x86_64.qcow2"
    assert "niri" in plan["packages"]
    assert "hyprland" not in plan["packages"]
    assert "--demo" in plan["build_args"]
    assert "--no-compress" in plan["build_args"]
    assert "hornero-playground-demo" in plan["hooks"]
    assert "hornero-vm-gpu-detect" in plan["hooks"]


def test_build_vm_image_rejects_invalid_options_and_pre_signal_lock(tmp_path: Path) -> None:
    hornero_dir = _make_hornero_fixture(tmp_path)

    bad_edition = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--edition",
            "server",
            "--hornero-dir",
            str(hornero_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_edition.returncode == 2
    assert "invalid edition" in bad_edition.stderr

    bad_comp = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--compositor",
            "xorg",
            "--hornero-dir",
            str(hornero_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_comp.returncode == 2

    stale_lock = tmp_path / "stale.lock.yaml"
    lock_data = yaml.safe_load(LOCK_FILE.read_text(encoding="utf-8"))
    lock_data["aur"]["packages"]["hornero-shell"]["version"] = "1.2.60-1"
    stale_lock.write_text(yaml.safe_dump(lock_data), encoding="utf-8")

    blocked = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--lock",
            str(stale_lock),
            "--hornero-dir",
            str(hornero_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 1
    assert "pre-Signal lock" in blocked.stderr

    allowed = subprocess.run(
        [
            str(BUILD_VM_SCRIPT),
            "--lock",
            str(stale_lock),
            "--hornero-dir",
            str(hornero_dir),
            "--dry-run",
        ],
        env={**os.environ, "HORNEROS_ALLOW_PRE_SIGNAL_LOCK": "1"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0, allowed.stderr


def test_build_vm_image_dry_run_matches_sibling_catalogue_when_present(tmp_path: Path) -> None:
    real_hornero = _find_real_hornero_dir()
    if real_hornero is None:
        pytest.skip("sibling HorneroOS/hornero checkout not present")
    catalogue = yaml.safe_load((real_hornero / "editions" / "catalogue.yaml").read_text(encoding="utf-8"))

    for edition in ("desktop", "studio", "gaming"):
        res = subprocess.run(
            [
                str(BUILD_VM_SCRIPT),
                "--edition",
                edition,
                "--hornero-dir",
                str(real_hornero),
                "--output-dir",
                str(tmp_path / "out"),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        plan = json.loads(res.stdout)
        expected_base = set(catalogue["base"]["packages"])
        expected_role = set(catalogue["packageSets"][edition]["packages"])
        assert expected_base <= set(plan["packages"])
        assert expected_role <= set(plan["packages"])


def test_gpu_detect_bare_metal_emits_nothing(tmp_path: Path) -> None:
    empty_dri = tmp_path / "dri"
    empty_dri.mkdir()
    res = subprocess.run(
        [str(GPU_DETECT_SCRIPT), "--detect", "none", "--dri-dir", str(empty_dri)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert res.stdout == ""


def test_gpu_detect_kvm_with_and_without_3d_render_node(tmp_path: Path) -> None:
    dri_3d = tmp_path / "dri-3d"
    dri_3d.mkdir()
    (dri_3d / "renderD128").touch()

    res_3d = subprocess.run(
        [str(GPU_DETECT_SCRIPT), "--detect", "kvm", "--dri-dir", str(dri_3d)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_3d.returncode == 0
    env_3d = _parse_kv(res_3d.stdout)
    assert env_3d == {
        "AQ_NO_MODIFIERS": "1",
        "QSG_RHI_BACKEND": "opengl",
        "LIBVA_DRIVER_NAME": "virtio_gpu",
    }

    dri_sw = tmp_path / "dri-sw"
    dri_sw.mkdir()
    res_sw = subprocess.run(
        [str(GPU_DETECT_SCRIPT), "--detect", "kvm", "--dri-dir", str(dri_sw)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_sw.returncode == 0
    env_sw = _parse_kv(res_sw.stdout)
    assert env_sw == {
        "AQ_NO_MODIFIERS": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GALLIUM_DRIVER": "llvmpipe",
        "QT_QUICK_BACKEND": "software",
    }


def test_gpu_detect_vmware_oracle_and_sourcing(tmp_path: Path) -> None:
    empty_dri = tmp_path / "dri"
    empty_dri.mkdir()

    res_vmware = subprocess.run(
        [str(GPU_DETECT_SCRIPT), "--detect", "vmware", "--dri-dir", str(empty_dri)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_vmware.returncode == 0
    assert _parse_kv(res_vmware.stdout) == {"QSG_RHI_BACKEND": "opengl"}
    assert "QSG_RHI_BACKEND=software" in GPU_DETECT_SCRIPT.read_text(encoding="utf-8")

    res_oracle = subprocess.run(
        [str(GPU_DETECT_SCRIPT), "--detect", "oracle", "--dri-dir", str(empty_dri)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_oracle.returncode == 0
    assert _parse_kv(res_oracle.stdout) == {
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GALLIUM_DRIVER": "llvmpipe",
        "QT_QUICK_BACKEND": "software",
        "WLR_NO_HARDWARE_CURSORS": "1",
    }

    res_sourced = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{GPU_DETECT_SCRIPT}" --detect oracle --dri-dir "{empty_dri}" && '
            'printf "%s:%s:%s:%s\\n" "$LIBGL_ALWAYS_SOFTWARE" "$GALLIUM_DRIVER" "$QT_QUICK_BACKEND" "$WLR_NO_HARDWARE_CURSORS"',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_sourced.returncode == 0, res_sourced.stderr
    assert res_sourced.stdout.strip() == "1:llvmpipe:software:1"


def test_live_demo_prep_seeds_idempotently_and_rejects_symlinks(tmp_path: Path) -> None:
    home = tmp_path / "hornero-live"
    home.mkdir()

    res = subprocess.run(
        [str(DEMO_PREP_SCRIPT), "--home", str(home)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    workspace = home / "Workspace"
    assert workspace.is_dir()
    readme = workspace / "README.md"
    notes = workspace / "sample-notes.md"
    cheat = workspace / "quick-reference.md"
    assert readme.is_file() and notes.is_file() and cheat.is_file()
    cheat_text = cheat.read_text(encoding="utf-8")
    assert "Hornero Welcome" in cheat_text
    assert "Hornero Apps" in cheat_text
    assert "Calamares" in cheat_text

    # Idempotency: user edits to README.md are preserved, missing files are re-seeded.
    readme.write_text("custom user note\n", encoding="utf-8")
    notes.unlink()
    res2 = subprocess.run(
        [str(DEMO_PREP_SCRIPT), "--home", str(home)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 0, res2.stderr
    assert readme.read_text(encoding="utf-8") == "custom user note\n"
    assert notes.is_file()

    # Symlink attack on target file must fail and never overwrite the symlink target.
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched\n", encoding="utf-8")
    notes.unlink()
    notes.symlink_to(victim)
    attack_file = subprocess.run(
        [str(DEMO_PREP_SCRIPT), "--home", str(home)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert attack_file.returncode != 0
    assert victim.read_text(encoding="utf-8") == "untouched\n"

    # Symlinked Workspace directory must also fail.
    shutil.rmtree(workspace)
    evil_dir = tmp_path / "evil-dir"
    evil_dir.mkdir()
    workspace.symlink_to(evil_dir)
    attack_dir = subprocess.run(
        [str(DEMO_PREP_SCRIPT), "--home", str(home)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert attack_dir.returncode != 0
    assert not (evil_dir / "README.md").exists()


def test_live_demo_prep_hooked_in_live_session_and_profiledef() -> None:
    setup_text = LIVE_SETUP_SCRIPT.read_text(encoding="utf-8")
    assert "/usr/local/bin/hornero-live-demo-prep" in setup_text
    profiledef = (ROOT / "image" / "archiso" / "profiledef.sh").read_text(encoding="utf-8")
    assert '["/usr/local/bin/hornero-live-demo-prep"]="0:0:755"' in profiledef


def test_shell_scripts_syntax_and_shellcheck() -> None:
    shell_scripts = [BUILD_VM_SCRIPT, GPU_DETECT_SCRIPT, LIVE_SETUP_SCRIPT]
    for script in shell_scripts:
        assert os.access(script, os.X_OK), f"{script} must be executable"
        syntax = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert syntax.returncode == 0, f"bash -n failed on {script}: {syntax.stderr}"

    shellcheck = shutil.which("shellcheck")
    if shellcheck:
        for script in shell_scripts:
            lint = subprocess.run(
                [shellcheck, str(script)],
                check=False,
                capture_output=True,
                text=True,
            )
            assert lint.returncode == 0, f"shellcheck failed on {script}:\n{lint.stdout}\n{lint.stderr}"

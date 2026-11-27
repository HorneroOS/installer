"""Signal GRUB theme installation wiring and target verification (installer#107)."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
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


boot_theme_mod = _load("configure_boot_theme", CALAMARES / "configure-boot-theme.py")
verify_mod = _load("verify_install_boot_theme", CALAMARES / "verify-install.py")


def _write_fake_tool(root: Path) -> Path:
    tool = root / "usr/share/hornero/bin/hornero-boot-theme"
    tool.parent.mkdir(parents=True, exist_ok=True)
    tool.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'root=""\n'
        'while [[ $# -gt 0 ]]; do\n'
        '  case "$1" in\n'
        '    --root) root="${2:?}"; shift 2 ;;\n'
        '    *) shift ;;\n'
        '  esac\n'
        'done\n'
        'mkdir -p "$root/boot/grub/themes/hornero-signal"\n'
        'cp "$root/usr/share/grub/themes/hornero-signal/theme.txt" '
        '"$root/boot/grub/themes/hornero-signal/theme.txt"\n'
        'printf \'GRUB_THEME="/boot/grub/themes/hornero-signal/theme.txt"\\n\' '
        '>> "$root/etc/default/grub"\n',
        encoding="utf-8",
    )
    os.chmod(tool, 0o755)
    theme_src = root / "usr/share/grub/themes/hornero-signal/theme.txt"
    theme_src.parent.mkdir(parents=True, exist_ok=True)
    theme_src.write_text('desktop-color: "#0C0F13"\n', encoding="utf-8")
    grub_default = root / "etc/default/grub"
    grub_default.parent.mkdir(parents=True, exist_ok=True)
    grub_default.write_text('GRUB_TIMEOUT=5\nGRUB_DEFAULT="0"\n', encoding="utf-8")
    return tool


def test_calamares_sequences_boot_theme_before_grubcfg():
    settings = yaml.safe_load((CALAMARES / "settings.conf").read_text(encoding="utf-8"))
    instances = {
        (entry["module"], entry["id"]): entry["config"]
        for entry in settings["instances"]
    }
    assert instances[("shellprocess", "boot-theme")] == "shellprocess-boot-theme.conf"
    exec_seq = settings["sequence"][1]["exec"]
    assert exec_seq.index("initcpio") < exec_seq.index("shellprocess@boot-theme")
    assert exec_seq.index("shellprocess@boot-theme") < exec_seq.index("grubcfg")
    assert exec_seq.index("grubcfg") < exec_seq.index("bootloader")

    conf = yaml.safe_load((CALAMARES / "modules/shellprocess-boot-theme.conf").read_text(encoding="utf-8"))
    assert conf["dontChroot"] is True
    assert conf["script"] == [
        "/usr/bin/python3 /usr/lib/hornero-installer/configure-boot-theme.py --root ${ROOT}"
    ]

    iso_builder = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert "configure-boot-theme.py" in iso_builder


def test_apply_grub_theme_runs_tool_and_copies_theme(tmp_path):
    _write_fake_tool(tmp_path)
    status = boot_theme_mod.apply_grub_theme(tmp_path)
    assert status == "applied"
    assert (tmp_path / "boot/grub/themes/hornero-signal/theme.txt").is_file()
    grub_text = (tmp_path / "etc/default/grub").read_text(encoding="utf-8")
    assert 'GRUB_THEME="/boot/grub/themes/hornero-signal/theme.txt"' in grub_text


def test_apply_grub_theme_skips_for_systemd_boot_and_missing_assets(tmp_path):
    _write_fake_tool(tmp_path)
    plan_path = tmp_path / "usr/lib/hornero/installation-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps({"selection": {"bootloader": "systemd-boot", "kernels": ["linux"]}}),
        encoding="utf-8",
    )
    assert boot_theme_mod.apply_grub_theme(tmp_path) == "skipped (bootloader=systemd-boot)"
    assert not (tmp_path / "boot/grub/themes/hornero-signal").exists()

    # Missing tool -> safe no-op skip
    plan_path.unlink()
    (tmp_path / "usr/share/hornero/bin/hornero-boot-theme").unlink()
    assert boot_theme_mod.apply_grub_theme(tmp_path) == "skipped (hornero-boot-theme not packaged)"


def test_apply_grub_theme_rejects_symlinks(tmp_path):
    _write_fake_tool(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("x", encoding="utf-8")
    (tmp_path / "etc/default/grub").unlink()
    (tmp_path / "etc/default/grub").symlink_to(outside)
    with pytest.raises(ValueError, match="Refusing symlink"):
        boot_theme_mod.apply_grub_theme(tmp_path)


def test_verify_install_validates_referenced_grub_theme(tmp_path):
    (tmp_path / "boot/grub").mkdir(parents=True)
    (tmp_path / "boot/grub/grub.cfg").write_text("menuentry 'HorneroOS' {}\n", encoding="utf-8")
    (tmp_path / "boot/vmlinuz-linux").write_bytes(b"kernel")
    (tmp_path / "boot/initramfs-linux.img").write_bytes(b"initramfs")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text("ID=horneroos\n", encoding="utf-8")
    (tmp_path / "etc/passwd").write_text("hornero:x:1000:1000::/home/hornero:/bin/zsh\n", encoding="utf-8")
    (tmp_path / "etc/default").mkdir()
    (tmp_path / "etc/default/grub").write_text(
        'GRUB_THEME="/boot/grub/themes/hornero-signal/theme.txt"\n', encoding="utf-8"
    )

    problems = verify_mod.verify_install(tmp_path)
    assert any("GRUB theme" in p for p in problems)

    theme = tmp_path / "boot/grub/themes/hornero-signal/theme.txt"
    theme.parent.mkdir(parents=True)
    theme.write_text('desktop-color: "#0C0F13"\n', encoding="utf-8")
    assert verify_mod.verify_install(tmp_path) == []

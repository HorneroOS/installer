"""Studio selection handoff seeded by configure-user-defaults (#36)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "configure_user_defaults", ROOT / "image" / "calamares" / "configure-user-defaults.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _target(tmp_path: Path, profile: dict | None) -> Path:
    root = tmp_path / "target"
    (root / "etc/xdg/xfce4").mkdir(parents=True)
    (root / "etc/xdg/xfce4/helpers.rc").write_text("TerminalEmulator=kitty\n", encoding="utf-8")
    (root / "etc").mkdir(exist_ok=True)
    (root / "etc/passwd").write_text(
        "ana:x:1000:1000:Ana:/home/ana:/bin/bash\n", encoding="utf-8"
    )
    (root / "home/ana").mkdir(parents=True)
    if profile is not None:
        profile_dir = root / "usr/lib/hornero"
        profile_dir.mkdir(parents=True)
        (profile_dir / "system-profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )
    return root


def test_seeds_studio_selection_from_installed_profile(tmp_path: Path):
    module = _module()
    root = _target(
        tmp_path,
        {
            "edition": {
                "studioSelection": {
                    "specializations": ["custom-selection"],
                    "applications": ["artcraft-launcher"],
                    "packages": ["pipewire"],
                }
            }
        },
    )
    module.configure_user_defaults(root)
    seeded = root / "home/ana/.config/hornero/studio-selection.json"
    data = json.loads(seeded.read_text(encoding="utf-8"))
    assert data == {
        "schemaVersion": 1,
        "specializations": ["custom-selection"],
        "applications": ["artcraft-launcher"],
    }
    # Seeding again never overwrites an existing user selection.
    seeded.write_text('{"schemaVersion": 1, "specializations": [], "applications": []}\n')
    module.configure_user_defaults(root)
    assert json.loads(seeded.read_text(encoding="utf-8"))["applications"] == []


def test_no_profile_no_selection_file(tmp_path: Path):
    module = _module()
    root = _target(tmp_path, None)
    module.configure_user_defaults(root)
    assert not (root / "home/ana/.config/hornero/studio-selection.json").exists()
    assert (root / "home/ana/.config/xfce4/helpers.rc").is_file()

"""The greeter must preselect the installed desktop session.

SDDM's session model falls back to its first entry on a fresh
system. Because `hornero-gaming-session.desktop` sorts first, a
Desktop install's first login opened the experimental Gamescope
session (black screen) instead of Hyprland (preview30 VM matrix).
The installer seeds `/var/lib/sddm/state.conf` from the installed
composition's compositor so the greeter opens on the desktop the
user actually chose.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_greeter_session",
    ROOT / "image/calamares/configure-greeter-session.py",
)
greeter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(greeter)


def _target(tmp_path: Path, profile_package: str | None,
            sessions: tuple[str, ...] = ("hyprland.desktop",)) -> Path:
    root = tmp_path / "root"
    (root / "usr/lib/hornero").mkdir(parents=True)
    if profile_package is not None:
        (root / "usr/lib/hornero/system-profile.json").write_text(
            json.dumps({"profilePackage": profile_package}), encoding="utf-8")
    sessions_dir = root / "usr/share/wayland-sessions"
    sessions_dir.mkdir(parents=True)
    for name in ("hornero-gaming-session.desktop", *sessions):
        (sessions_dir / name).write_text("[Desktop Entry]\n", encoding="utf-8")
    (root / "etc").mkdir(parents=True)
    (root / "etc/passwd").write_text(
        "root:x:0:0::/root:/usr/bin/zsh\n"
        "hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n",
        encoding="utf-8")
    return root


def _state(root: Path) -> str:
    return (root / "var/lib/sddm/state.conf").read_text(encoding="utf-8")


def test_desktop_hyprland_is_preseeded(tmp_path):
    root = _target(tmp_path, "hornero-profile-desktop-hyprland")
    assert greeter.configure_greeter_session(root) == "hyprland.desktop"
    state = _state(root)
    assert "Session=/usr/share/wayland-sessions/hyprland.desktop" in state
    assert "User=hornero" in state


def test_gaming_still_preseeds_desktop_session(tmp_path):
    # The Gaming session stays opt-in from the greeter list; a
    # Gaming install also lands on its desktop first.
    root = _target(tmp_path, "hornero-profile-gaming-hyprland")
    assert greeter.configure_greeter_session(root) == "hyprland.desktop"
    assert "hornero-gaming-session" not in _state(root)


def test_niri_is_preseeded_when_chosen(tmp_path):
    root = _target(tmp_path, "hornero-profile-desktop-niri",
                   sessions=("niri.desktop",))
    assert greeter.configure_greeter_session(root) == "niri.desktop"
    assert "Session=/usr/share/wayland-sessions/niri.desktop" in _state(root)


def test_missing_profile_is_a_noop(tmp_path):
    root = _target(tmp_path, None)
    assert greeter.configure_greeter_session(root) is None
    assert not (root / "var/lib/sddm/state.conf").exists()


def test_missing_session_file_is_a_noop(tmp_path):
    root = _target(tmp_path, "hornero-profile-desktop-hyprland", sessions=())
    assert greeter.configure_greeter_session(root) is None
    assert not (root / "var/lib/sddm/state.conf").exists()


def test_installer_wires_the_step_after_users():
    settings = (ROOT / "image/calamares/settings.conf").read_text(encoding="utf-8")
    assert "shellprocess@greeter-session" in settings
    conf = (ROOT / "image/calamares/modules/"
            "shellprocess-greeter-session.conf").read_text(encoding="utf-8")
    assert "dontChroot: true" in conf
    assert "configure-greeter-session.py --root ${ROOT}" in conf
    builder = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert "configure-greeter-session.py" in builder

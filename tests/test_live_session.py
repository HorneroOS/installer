"""The live session is HorneroOS Desktop, not XFCE."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHISO = ROOT / "image/archiso"


def _packages():
    return {
        line.strip()
        for line in (ARCHISO / "packages.x86_64").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_live_packages_are_hornero_desktop():
    pkgs = _packages()
    assert {"hyprland", "quickshell", "hornero-shell", "hornero-config",
            "horneroctl-bin", "kitty"} <= pkgs
    assert not any(p.startswith("xfce") or p == "xfconf" for p in pkgs)


def test_live_session_is_hyprland():
    conf = (ARCHISO / "airootfs/etc/sddm.conf.d/10-hornero-live.conf").read_text(encoding="utf-8")
    assert "Session=hyprland.desktop" in conf


def test_installer_wrapper_keeps_wayland_env():
    sudoers = (ARCHISO / "airootfs/etc/sudoers.d/hornero-live").read_text(encoding="utf-8")
    assert "WAYLAND_DISPLAY" in sudoers and "XDG_RUNTIME_DIR" in sudoers

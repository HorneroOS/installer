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


def test_live_session_never_locks_blanks_or_suspends():
    """The live user has no password: an idle lock would trap the install."""
    setup = ARCHISO / "airootfs/usr/local/bin/hornero-live-session-setup"
    text = setup.read_text(encoding="utf-8")
    assert "shell.json" in text and "hypridle.conf" in text
    assert text.count('"enabled": false') == 3
    assert '"lockBeforeSleep": false' in text
    desktop = ARCHISO / "airootfs/etc/xdg/autostart/hornero-live-session.desktop"
    assert "Exec=/usr/local/bin/hornero-live-session-setup" in desktop.read_text(encoding="utf-8")
    profile = (ARCHISO / "profiledef.sh").read_text(encoding="utf-8")
    assert '["/usr/local/bin/hornero-live-session-setup"]="0:0:755"' in profile


def test_live_session_seeds_terminal_helper():
    """SUPER+Return uses exo; the live home must define TerminalEmulator."""
    setup = ARCHISO / "airootfs/usr/local/bin/hornero-live-session-setup"
    text = setup.read_text(encoding="utf-8")
    assert "xfce4/helpers.rc" in text
    assert "TerminalEmulator=kitty" in text
    # Seeding must not clobber an existing session choice.
    assert "grep -q '^TerminalEmulator='" in text
    assert "kitty" in _packages()


def test_live_sleep_targets_masked_and_logind_idle_ignored():
    system_dir = ARCHISO / "airootfs/etc/systemd/system"
    for target in ("sleep.target", "suspend.target", "hibernate.target",
                   "hybrid-sleep.target", "suspend-then-hibernate.target"):
        link = system_dir / target
        assert link.is_symlink() and link.readlink().as_posix() == "/dev/null", target
    logind = (ARCHISO / "airootfs/etc/systemd/logind.conf.d/10-hornero-live.conf").read_text(encoding="utf-8")
    assert "IdleAction=ignore" in logind and "HandleLidSwitch=ignore" in logind

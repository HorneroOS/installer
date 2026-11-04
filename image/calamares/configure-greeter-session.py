#!/usr/bin/env python3
"""Seed SDDM's last-session state from the installed composition.

On a fresh system SDDM's session model falls back to its first
entry. `hornero-gaming-session.desktop` sorts first, so a Desktop
install's first login opened the experimental Gamescope session
(a black screen) instead of the chosen desktop. Seed
`/var/lib/sddm/state.conf` with the compositor the user picked in
Calamares (recorded in `usr/lib/hornero/system-profile.json`) and
the created user, so the greeter opens on that desktop. The
Gaming session remains selectable from the greeter's list.

Missing profile or session data is a no-op: the greeter keeps its
upstream behaviour rather than failing the installation.
"""

from __future__ import annotations

import argparse
import json
import stat
from pathlib import Path

SESSION_CANDIDATES: dict[str, tuple[str, ...]] = {
    "hyprland": ("hyprland.desktop", "hyprland-uwsm.desktop"),
    "niri": ("niri.desktop", "niri-session.desktop"),
}


def _installed_compositor(root: Path) -> str | None:
    profile_path = root / "usr/lib/hornero/system-profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(profile, dict):
        return None
    # The installed profile records the chosen compositor explicitly;
    # it is authoritative over any package-name parsing.
    edition = profile.get("edition")
    if isinstance(edition, dict):
        compositor = edition.get("compositor")
        if isinstance(compositor, str) and compositor in SESSION_CANDIDATES:
            return compositor
    package = profile.get("profilePackage")
    if not isinstance(package, str):
        return None
    # Fallback: exactly one known compositor token in the package
    # name. Candidate choices append suffixes after the compositor
    # (e.g. hornero-profile-desktop-hyprland-recovery), so the last
    # token alone does not identify the compositor.
    tokens = {token for token in package.split("-")
              if token in SESSION_CANDIDATES}
    return tokens.pop() if len(tokens) == 1 else None


def _first_regular_user(root: Path) -> str | None:
    passwd = root / "etc/passwd"
    try:
        lines = passwd.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split(":")
        if len(fields) < 7:
            continue
        try:
            uid = int(fields[2])
        except ValueError:
            continue
        if uid >= 1000 and fields[5].startswith("/home/"):
            return fields[0]
    return None


def configure_greeter_session(root: Path) -> str | None:
    """Write the SDDM state seed; return the session file or None."""
    root = root.resolve()
    compositor = _installed_compositor(root)
    if compositor is None:
        return None
    sessions_dir = root / "usr/share/wayland-sessions"
    session_file = next(
        (name for name in SESSION_CANDIDATES[compositor]
         if (sessions_dir / name).is_file()),
        None,
    )
    if session_file is None:
        return None
    user = _first_regular_user(root)
    if user is None:
        return None

    state_dir = root / "var/lib/sddm"
    state_file = state_dir / "state.conf"
    # dontChroot runs this script as root against the installed
    # target; refuse symlink redirection outside the target tree.
    for path in (state_dir, state_file):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in SDDM state path: {path}")
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        "[Last]\n"
        f"Session=/usr/share/wayland-sessions/{session_file}\n"
        f"User={user}\n",
        encoding="utf-8",
    )
    state_file.chmod(0o644)
    return session_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"),
                        help="installed target root")
    args = parser.parse_args()
    session = configure_greeter_session(args.root.resolve())
    if session is None:
        print("greeter-session: no composition session to preseed; skipping")
    else:
        print(f"greeter-session: preseeded SDDM session {session}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

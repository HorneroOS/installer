#!/usr/bin/env python3
"""Runtime side of the HorneroOS offline installation mode.

No-op unless the root-owned marker
``/run/hornero-installer/offline-mode`` exists (written by
``hornero-installer-run`` after the live user explicitly accepted
offline mode in the launcher, before Calamares and therefore before
any partitioning). When the marker exists, the offline repository on
the live medium is fully verified first; only then is the target
``pacman.conf`` pointed at ``file://`` repositories. A missing or
incomplete repository fails here, and the exec-phase preflight has
already failed on the same condition before partitioning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_MARKER = Path("/run/hornero-installer/offline-mode")
DEFAULT_REPO = Path("/usr/share/hornero-installer/offline-repo")
DB_NAME = "hornero-offline.db.tar.gz"
MANIFEST_NAME = "offline-manifest.json"
OFFLINE_SECTION = "[hornero-offline]"
ARCH_SECTIONS = {"[core]", "[extra]", "[multilib]"}


def verify_repo(repo_dir: Path) -> list[str]:
    errors: list[str] = []
    if not (repo_dir / DB_NAME).is_file():
        errors.append(f"offline pacman database missing: {repo_dir / DB_NAME}")
    manifest_path = repo_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        errors.append(f"offline manifest missing: {manifest_path}")
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        return [f"offline manifest unreadable: {error}"]
    if manifest.get("repo") != "hornero-offline":
        errors.append("offline manifest does not describe hornero-offline")
    for entry in manifest.get("packages") or []:
        artifact = repo_dir / entry["file"]
        if not artifact.is_file():
            errors.append(f"offline package missing: {entry['file']}")
            continue
        if artifact.stat().st_size != entry["size"]:
            errors.append(f"offline package size mismatch: {entry['file']}")
            continue
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(f"offline package checksum mismatch: {entry['file']}")
    return errors


def offline_pacman_conf(text: str, repo_dir: Path) -> str:
    """Target pacman.conf restricted to local file:// repositories.

    Arch sections are dropped (their snapshot servers need network);
    the single hornero-offline repo replaces them. The local
    hornero-installer include stays: Hornero packages already ship
    as a file:// repository on the ISO.
    """
    lines: list[str] = []
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            if section in ARCH_SECTIONS:
                continue
        if section in ARCH_SECTIONS:
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    lines += ["", OFFLINE_SECTION, "SigLevel = Optional TrustAll",
              f"Server = file://{repo_dir}"]
    return "\n".join(lines) + "\n"


def apply_offline(root: Path, repo_dir: Path, marker: Path) -> bool:
    if not marker.is_file():
        return False
    errors = verify_repo(repo_dir)
    if errors:
        raise ValueError("; ".join(errors))
    pacman_conf = root / "etc/pacman.conf"
    if pacman_conf.is_symlink() or not pacman_conf.is_file():
        raise ValueError("target pacman.conf is missing or is not a regular file")
    pacman_conf.write_text(
        offline_pacman_conf(pacman_conf.read_text(encoding="utf-8"), repo_dir),
        encoding="utf-8",
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="installed target root")
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--marker", type=Path, default=DEFAULT_MARKER)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            errors = verify_repo(args.repo_dir)
            if errors:
                raise ValueError("; ".join(errors))
            print("offline-repo: repository complete")
            return 0
        if args.root is None:
            parser.error("--root is required unless --verify-only is given")
        if apply_offline(args.root, args.repo_dir, args.marker):
            print("offline-repo: target now uses the on-media offline repository")
        else:
            print("offline-repo: no offline marker; keeping online repositories")
    except ValueError as error:
        print(f"offline-repo: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

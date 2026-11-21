#!/usr/bin/env python3
"""Build-time helpers for the HorneroOS offline pacman repository.

The offline repository is a single pacman repo (``hornero-offline``)
holding the full dependency closure of every package an installer
user can select: all edition compositions plus every netinstall leaf.
Hornero's own packages are excluded on purpose: they already ship in
the local ``hornero-installer`` repository on the ISO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

DB_NAME = "hornero-offline.db.tar.gz"
MANIFEST_NAME = "offline-manifest.json"
LOCAL_PREFIX = "hornero"


def _netinstall_leaves(items):
    for item in items:
        if item.get("subgroups"):
            yield from _netinstall_leaves(item["subgroups"])
        else:
            yield item


def package_union(compositions_path: Path, netinstall_path: Path) -> list[str]:
    compositions = json.loads(compositions_path.read_text(encoding="utf-8"))
    packages: set[str] = set()
    for option in compositions["options"]:
        packages.update(option["packages"])
    netinstall = yaml.safe_load(netinstall_path.read_text(encoding="utf-8"))
    for leaf in _netinstall_leaves(netinstall["groups"]):
        packages.update(leaf.get("packages") or [])
    return sorted(p for p in packages if not p.startswith(LOCAL_PREFIX))


def write_manifest(repo_dir: Path, snapshot: str) -> dict:
    packages = []
    total = 0
    for artifact in sorted(repo_dir.glob("*.pkg.tar.*")):
        if artifact.name.endswith(".sig"):
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        size = artifact.stat().st_size
        total += size
        packages.append(
            {"file": artifact.name, "size": size, "sha256": digest}
        )
    if not packages:
        raise ValueError(f"no packages found in offline repository: {repo_dir}")
    if not (repo_dir / DB_NAME).is_file():
        raise ValueError(f"pacman database missing: {repo_dir / DB_NAME}")
    manifest = {
        "schemaVersion": 1,
        "repo": "hornero-offline",
        "archSnapshot": snapshot,
        "packageCount": len(packages),
        "totalBytes": total,
        "packages": packages,
    }
    (repo_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def verify_repo(repo_dir: Path, check_hashes: bool = True) -> list[str]:
    errors: list[str] = []
    manifest_path = repo_dir / MANIFEST_NAME
    if not (repo_dir / DB_NAME).is_file():
        errors.append(f"offline pacman database missing: {repo_dir / DB_NAME}")
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
        if check_hashes and (
            hashlib.sha256(artifact.read_bytes()).hexdigest() != entry["sha256"]
        ):
            errors.append(f"offline package checksum mismatch: {entry['file']}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pkg = sub.add_parser("packages")
    pkg.add_argument("--compositions", type=Path, required=True)
    pkg.add_argument("--netinstall", type=Path, required=True)
    man = sub.add_parser("manifest")
    man.add_argument("--repo-dir", type=Path, required=True)
    man.add_argument("--snapshot", required=True)
    ver = sub.add_parser("verify")
    ver.add_argument("--repo-dir", type=Path, required=True)
    ver.add_argument("--no-hashes", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "packages":
            print("\n".join(package_union(args.compositions, args.netinstall)))
        elif args.command == "manifest":
            manifest = write_manifest(args.repo_dir, args.snapshot)
            print(
                f"offline-repo: {manifest['packageCount']} packages, "
                f"{manifest['totalBytes']} bytes"
            )
        else:
            errors = verify_repo(args.repo_dir, check_hashes=not args.no_hashes)
            for error in errors:
                print(f"offline-repo: {error}", file=sys.stderr)
            if errors:
                return 1
            print("offline-repo: repository complete")
    except (ValueError, OSError, KeyError) as error:
        print(f"offline-repo: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check an installed Hornero profile against its pinned package composition."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = Path("usr/lib/hornero/system-profile.json")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


def audit(
    profile: dict[str, Any], compositions: dict[str, Any], installed: set[str]
) -> dict[str, Any]:
    """Compare installed profile provenance and selected resolver packages."""
    errors: list[str] = []
    options = compositions.get("options")
    if not isinstance(options, list):
        options = []
        errors.append("composition manifest has no options list")

    revision = profile.get("sourceRevision")
    if not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        errors.append("installed profile sourceRevision is not a full lowercase Git SHA")
    if revision != compositions.get("productRevision"):
        errors.append("installed profile sourceRevision does not match the composition manifest")

    profile_package = profile.get("profilePackage")
    matches = [
        option
        for option in options
        if isinstance(option, dict) and option.get("profilePackage") == profile_package
    ]
    if not isinstance(profile_package, str) or len(matches) != 1:
        errors.append("installed profilePackage does not identify exactly one manifest option")
        option: dict[str, Any] = {}
    else:
        option = matches[0]

    expected_profile = option.get("profile")
    installed_profile = profile.get("edition")
    if not isinstance(expected_profile, dict) or not isinstance(installed_profile, dict):
        errors.append("installed profile or manifest option has no profile object")
        expected_profile = expected_profile if isinstance(expected_profile, dict) else {}
        installed_profile = installed_profile if isinstance(installed_profile, dict) else {}
    elif installed_profile != expected_profile:
        errors.append("installed profile metadata differs from the selected manifest profile")

    resolved_packages = expected_profile.get("packages")
    option_packages = option.get("packages")
    if not isinstance(resolved_packages, list) or not all(
        isinstance(package, str) and package for package in resolved_packages
    ):
        errors.append("manifest profile has no valid resolved package list")
        resolved_packages = []
    if not isinstance(option_packages, list) or not all(
        isinstance(package, str) and package for package in option_packages
    ):
        errors.append("manifest option has no valid installer package list")
        option_packages = []
    elif option_packages != [*resolved_packages, profile_package]:
        errors.append(
            "installer package list differs from resolver packages plus profile metadata package"
        )

    expected_packages = set(option_packages)
    missing_packages = sorted(expected_packages - installed)
    if missing_packages:
        errors.append("installed system is missing resolver-selected packages")

    return {
        "schema": "hornero-installed-composition-audit/1",
        "result": "PASS" if not errors else "FAIL",
        "profilePackage": profile_package,
        "sourceRevision": revision,
        "expectedPackages": sorted(expected_packages),
        "installedExpectedPackages": sorted(expected_packages & installed),
        "missingPackages": missing_packages,
        "errors": errors,
        "scope": (
            "Checks profile metadata and resolver-selected package coverage. "
            "Base-image packages and transitive dependencies are allowed; this is not full installed-package equality."
        ),
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def installed_packages(root: Path) -> set[str]:
    root = root.resolve()
    command = ["pacman", "-Qq"]
    if root != Path("/"):
        command.extend(["--root", str(root)])
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"pacman exited with status {result.returncode}"
        raise RuntimeError(detail)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="installed system root")
    parser.add_argument(
        "--compositions",
        type=Path,
        default=ROOT / "image/calamares/modules/compositions.json",
        help="composition manifest generated for the same installer ISO",
    )
    args = parser.parse_args()

    try:
        root = args.root.resolve()
        profile = load_json(root / PROFILE_PATH)
        compositions = load_json(args.compositions)
        report = audit(profile, compositions, installed_packages(root))
    except (OSError, ValueError, RuntimeError) as error:
        report = {
            "schema": "hornero-installed-composition-audit/1",
            "result": "FAIL",
            "errors": [str(error)],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

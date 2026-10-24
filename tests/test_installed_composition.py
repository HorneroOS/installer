from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_installed_composition", ROOT / "scripts/check-installed-composition.py"
)
assert SPEC and SPEC.loader
AUDIT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT_MODULE)


def sample_data():
    profile = {
        "apiVersion": "hornero.os/v1",
        "kind": "InstalledProfile",
        "sourceRevision": "a" * 40,
        "profilePackage": "hornero-profile-desktop-hyprland",
        "edition": {
            "edition": "desktop",
            "compositor": "hyprland",
            "packages": ["base", "hornero-shell", "hyprland"],
        },
    }
    compositions = {
        "productRevision": "a" * 40,
        "options": [
            {
                "profilePackage": "hornero-profile-desktop-hyprland",
                "profile": copy.deepcopy(profile["edition"]),
                "packages": [
                    "base",
                    "hornero-shell",
                    "hyprland",
                    "hornero-profile-desktop-hyprland",
                ],
            }
        ],
    }
    return profile, compositions


def test_installed_profile_and_resolver_packages_pass():
    profile, compositions = sample_data()

    report = AUDIT_MODULE.audit(
        profile,
        compositions,
        {"base", "hornero-shell", "hyprland", "hornero-profile-desktop-hyprland", "glibc"},
    )

    assert report["result"] == "PASS"
    assert report["missingPackages"] == []
    assert "full installed-package equality" in report["scope"]


def test_missing_resolver_package_fails_and_names_the_package():
    profile, compositions = sample_data()

    report = AUDIT_MODULE.audit(profile, compositions, {"base", "hyprland"})

    assert report["result"] == "FAIL"
    assert report["missingPackages"] == [
        "hornero-profile-desktop-hyprland",
        "hornero-shell",
    ]


def test_profile_from_another_product_revision_fails():
    profile, compositions = sample_data()
    profile["sourceRevision"] = "b" * 40

    report = AUDIT_MODULE.audit(
        profile,
        compositions,
        {"base", "hornero-shell", "hyprland", "hornero-profile-desktop-hyprland"},
    )

    assert report["result"] == "FAIL"
    assert (
        "installed profile sourceRevision does not match the composition manifest"
        in report["errors"]
    )


def test_profile_metadata_drift_fails():
    profile, compositions = sample_data()
    profile["edition"]["compositor"] = "niri"

    report = AUDIT_MODULE.audit(
        profile,
        compositions,
        {"base", "hornero-shell", "hyprland", "hornero-profile-desktop-hyprland"},
    )

    assert report["result"] == "FAIL"
    assert (
        "installed profile metadata differs from the selected manifest profile"
        in report["errors"]
    )


def test_installer_package_list_drift_fails():
    profile, compositions = sample_data()
    compositions["options"][0]["packages"].remove("hornero-shell")

    report = AUDIT_MODULE.audit(
        profile,
        compositions,
        {"base", "hornero-shell", "hyprland", "hornero-profile-desktop-hyprland"},
    )

    assert report["result"] == "FAIL"
    assert (
        "installer package list differs from resolver packages plus profile metadata package"
        in report["errors"]
    )


def test_committed_composition_options_match_the_audit_contract():
    compositions = json.loads(
        (ROOT / "image/calamares/modules/compositions.json").read_text(encoding="utf-8")
    )

    for option in compositions["options"]:
        profile = {
            "sourceRevision": compositions["productRevision"],
            "profilePackage": option["profilePackage"],
            "edition": option["profile"],
        }
        report = AUDIT_MODULE.audit(profile, compositions, set(option["packages"]))

        assert report["result"] == "PASS", report["errors"]

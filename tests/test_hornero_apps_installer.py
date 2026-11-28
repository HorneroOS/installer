"""Tests for Hornero Apps runtime, workstation profiles renderer, and queue handoff."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image" / "calamares"
PROFILES_JSON = CALAMARES / "modules" / "hornero-workstation-profiles.json"
DEFAULT_APP_CATALOG = (
    ROOT.parent / "horneroos-wt-hornero-apps" / "catalog" / "apps.v1.json"
)
APP_CATALOG = Path(os.environ.get("HORNEROS_APP_CATALOG", str(DEFAULT_APP_CATALOG)))

EXPECTED_PROFILES = (
    "minimal",
    "everyday-desktop",
    "work-productivity",
    "software-development",
    "ai-native-workstation",
    "creative-studio",
    "music-audio-production",
    "gaming",
    "education-research",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_profiles_mod = _load("render_app_profiles", ROOT / "scripts/render-app-profiles.py")
render_netinstall_mod = _load("render_netinstall", ROOT / "scripts/render-netinstall.py")
defaults_mod = _load("configure_user_defaults", CALAMARES / "configure-user-defaults.py")
verify_mod = _load("verify_install", CALAMARES / "verify-install.py")


def _synthetic_catalog() -> dict:
    """Offline-safe synthetic catalog covering all 9 profile IDs and edge cases."""
    apps = [
        {
            "id": "firefox",
            "name": "Firefox",
            "is_open_source": True,
            "recommended_source": "arch_native",
            "deprecated": False,
            "sources": [
                {"backend": "arch_native", "provenance": "arch_official", "package_id": "firefox"},
                {"backend": "flatpak", "provenance": "flathub_verified", "package_id": "org.mozilla.firefox"},
            ],
        },
        {
            "id": "gear-lever",
            "name": "Gear Lever",
            "is_open_source": True,
            "recommended_source": "flatpak",
            "deprecated": False,
            "sources": [
                {"backend": "flatpak", "provenance": "flathub_verified", "package_id": "it.mijorus.gearlever"},
            ],
        },
        {
            "id": "claude-web",
            "name": "Claude Web",
            "is_open_source": False,
            "recommended_source": "webapp",
            "deprecated": False,
            "sources": [
                {"backend": "webapp", "provenance": "official_web_app", "package_id": "https://claude.ai"},
            ],
        },
        {
            "id": "steam",
            "name": "Steam",
            "is_open_source": False,
            "recommended_source": "arch_native",
            "deprecated": False,
            "sources": [
                {"backend": "arch_native", "provenance": "arch_official", "package_id": "steam"},
            ],
        },
    ]
    profiles = []
    for pid in EXPECTED_PROFILES:
        profiles.append({
            "id": pid,
            "name": pid.replace("-", " ").title(),
            "name_es": pid,
            "description": f"Profile {pid}",
            "description_es": f"Perfil {pid}",
            "apps": ["firefox", "gear-lever"],
            "proprietaryOptIn": ["steam"] if pid == "gaming" else ["claude-web"],
        })
    return {
        "apiVersion": "hornero.os/v1",
        "kind": "ApplicationCatalog",
        "schemaVersion": 1,
        "verifiedAt": "2026-11-28",
        "categories": [],
        "collections": [],
        "profiles": profiles,
        "apps": apps,
    }


def _fake_target(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "etc/xdg/xfce4").mkdir(parents=True)
    (root / "etc/xdg/xfce4/helpers.rc").write_text("TerminalEmulator=kitty\n", encoding="utf-8")
    (root / "etc/passwd").write_text("ana:x:1000:1000:Ana:/home/ana:/bin/zsh\n", encoding="utf-8")
    (root / "home/ana").mkdir(parents=True)
    (root / "usr/lib/hornero").mkdir(parents=True)
    return root


def test_committed_workstation_profiles_contract():
    doc = json.loads(PROFILES_JSON.read_text(encoding="utf-8"))
    assert doc["apiVersion"] == "hornero.os/v1"
    assert doc["kind"] == "WorkstationProfiles"
    assert doc["schemaVersion"] == 1
    assert doc["defaultSelected"] is False
    assert doc["critical"] is False

    profiles = doc["profiles"]
    assert tuple(p["id"] for p in profiles) == EXPECTED_PROFILES

    for profile in profiles:
        assert profile["selected"] is False
        assert profile["critical"] is False
        assert profile["apps"], f"{profile['id']} has empty open-source apps[]"
        assert profile["archOfficialPackages"], f"{profile['id']} has no archOfficialPackages"
        assert not (set(profile["apps"]) & set(profile["proprietaryOptIn"]))
        for entry in profile["deferredApps"]:
            assert isinstance(entry["id"], str) and entry["id"]
            assert entry["id"] not in profile["proprietaryOptIn"]


@pytest.mark.skipif(
    not APP_CATALOG.is_file(),
    reason="canonical catalog/apps.v1.json not available locally",
)
def test_render_app_profiles_against_real_catalog_matches_committed(tmp_path):
    out = tmp_path / "hornero-workstation-profiles.json"
    rc = render_profiles_mod.main(["--catalog", str(APP_CATALOG), "--output", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == PROFILES_JSON.read_text(encoding="utf-8")

    catalog = render_profiles_mod.load_catalog(APP_CATALOG)
    apps_by_id = {app["id"]: app for app in catalog["apps"]}
    doc = json.loads(out.read_text(encoding="utf-8"))

    for profile in doc["profiles"]:
        assert profile["selected"] is False
        assert profile["critical"] is False
        for app_id in profile["apps"]:
            assert apps_by_id[app_id]["is_open_source"] is True
        for prop_id in profile["proprietaryOptIn"]:
            assert apps_by_id[prop_id]["is_open_source"] is False
            assert prop_id not in profile["apps"]
            assert prop_id not in {d["id"] for d in profile["deferredApps"]}
            for source in apps_by_id[prop_id]["sources"]:
                if source["backend"] == "arch_native":
                    assert source["package_id"] not in profile["archOfficialPackages"]

    group = render_profiles_mod.build_workstation_netinstall_group(catalog)
    assert group["selected"] is False
    assert group["expanded"] is False
    assert len(group["subgroups"]) == 9
    for sub in group["subgroups"]:
        assert sub["selected"] is False
        assert sub["critical"] is False
        assert sub["packages"]
        assert not (set(sub["packages"]) & {"steam", "reaper", "obsidian", "discord", "bitwarden"})


def test_render_app_profiles_rejects_proprietary_in_open_apps():
    bad = _synthetic_catalog()
    bad["profiles"][0]["apps"].append("steam")
    with pytest.raises(ValueError, match="not open-source"):
        render_profiles_mod.build_profiles_document(bad)

    overlap = _synthetic_catalog()
    overlap["profiles"][0]["proprietaryOptIn"].append("firefox")
    with pytest.raises(ValueError, match="both apps\\[\\] and proprietaryOptIn\\[\\]"):
        render_profiles_mod.build_profiles_document(overlap)


def test_netinstall_app_catalog_integration_preserves_existing_groups():
    synthetic_app_catalog = _synthetic_catalog()
    if APP_CATALOG.is_file():
        synthetic_app_catalog = render_profiles_mod.load_catalog(APP_CATALOG)

    minimal_catalogue = {
        "studioSpecializations": {"audio": {"title": "Audio"}},
        "gamingSpecializations": {},
        "capabilities": {},
        "studioApplications": {},
        "gamingApplications": {},
        "gpuVendors": {
            "amd": {"title": "AMD GPU", "packages": ["mesa"]},
            "nvidia": {
                "proprietary": True,
                "explicitOptIn": True,
                "dkmsModule": "nvidia-open-dkms",
                "packages": ["nvidia-utils"],
            },
        },
        "gpuProvenance": {
            "mesa": {
                "source": "arch",
                "sourceUrl": "https://archlinux.org/packages/extra/x86_64/mesa/",
                "licenses": ["MIT"],
                "licenseClass": "open-source",
            },
            "nvidia-open-dkms": {
                "source": "arch",
                "sourceUrl": "https://archlinux.org/packages/extra/x86_64/nvidia-open-dkms/",
                "licenses": ["MIT"],
                "licenseClass": "open-source",
            },
            "nvidia-utils": {
                "source": "arch",
                "sourceUrl": "https://archlinux.org/packages/extra/x86_64/nvidia-utils/",
                "licenses": ["LicenseRef-NVIDIA"],
                "licenseClass": "proprietary",
            },
        },
    }

    orig_resolve = render_netinstall_mod._resolve
    try:
        render_netinstall_mod._resolve = lambda _root, _ed, _spec: {
            "packages": ["ardour"],
            "manualOptInRequired": [],
            "proprietaryOptInRequired": [],
        }
        base_render = render_netinstall_mod.render(
            ROOT, minimal_catalogue, probe_vendors=["amd"]
        )
        extended_render = render_netinstall_mod.render(
            ROOT, minimal_catalogue, probe_vendors=["amd"], app_catalog=synthetic_app_catalog
        )
    finally:
        render_netinstall_mod._resolve = orig_resolve

    assert extended_render["groups"][:-1] == base_render["groups"]
    ws_group = extended_render["groups"][-1]
    assert ws_group["name"] == "Workstation profiles (optional)"
    assert ws_group["selected"] is False
    assert len(ws_group["subgroups"]) == 9
    for sub in ws_group["subgroups"]:
        assert sub["selected"] is False
        assert sub["critical"] is False
        assert "steam" not in sub["packages"]

    # AMD GPU probe pre-selection must remain intact.
    gpu_group = next(g for g in extended_render["groups"] if g["name"] == "GPU drivers (open-source)")
    assert gpu_group["subgroups"][0]["selected"] is True
    nvidia_group = next(g for g in extended_render["groups"] if g["name"] == "NVIDIA GPU driver (proprietary)")
    assert nvidia_group["selected"] is False


def test_store_onboarding_queue_seeded_from_plan_and_profile(tmp_path):
    root = _fake_target(tmp_path)
    (root / "usr/lib/hornero/installation-plan.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "selection": {
                "offline": True,
                "workstationProfiles": ["minimal", "gaming"],
                "deferredApps": [{"id": "obsidian", "backend": "flatpak"}],
            },
        }),
        encoding="utf-8",
    )
    (root / "usr/lib/hornero/system-profile.json").write_text(
        json.dumps({
            "edition": {
                "deferredApps": ["claude-web", {"id": "gear-lever", "backend": "flatpak"}],
            }
        }),
        encoding="utf-8",
    )

    defaults_mod.configure_user_defaults(root, profiles_path=PROFILES_JSON)

    queue_path = root / "home/ana/.config/hornero/store-onboarding-queue.json"
    assert queue_path.is_file()
    assert queue_path.stat().st_mode & 0o777 == 0o644

    queue_doc = json.loads(queue_path.read_text(encoding="utf-8"))
    # Exact horneroctl StoreQueueDoc schema: {"items": [{"id": str, "backend": str}]}
    assert list(queue_doc.keys()) == ["items"]
    ids = [item["id"] for item in queue_doc["items"]]
    assert ids == [
        "gear-lever",
        "localsend",
        "heroic-games-launcher",
        "bottles",
        "protonup-qt",
        "obsidian",
        "claude-web",
    ]
    # Proprietary app "steam" from gaming.proprietaryOptIn must NEVER be auto-queued.
    assert "steam" not in ids
    for item in queue_doc["items"]:
        assert set(item.keys()) == {"id", "backend"}
        assert isinstance(item["id"], str) and item["id"]
        assert isinstance(item["backend"], str)

    # Never overwrite an existing user queue.
    user_custom = {"items": [{"id": "firefox", "backend": "arch_native"}]}
    queue_path.write_text(json.dumps(user_custom), encoding="utf-8")
    defaults_mod.configure_user_defaults(root, profiles_path=PROFILES_JSON)
    assert json.loads(queue_path.read_text(encoding="utf-8")) == user_custom


def test_store_onboarding_queue_rejects_symlinks_and_handles_empty(tmp_path):
    root = _fake_target(tmp_path)
    defaults_mod.configure_user_defaults(root, profiles_path=PROFILES_JSON)
    assert not (root / "home/ana/.config/hornero/store-onboarding-queue.json").exists()

    # Empty deferred lists also create no queue file.
    (root / "usr/lib/hornero/installation-plan.json").write_text(
        json.dumps({"selection": {"workstationProfiles": [], "deferredApps": []}}),
        encoding="utf-8",
    )
    defaults_mod.configure_user_defaults(root, profiles_path=PROFILES_JSON)
    assert not (root / "home/ana/.config/hornero/store-onboarding-queue.json").exists()

    # Symlink attack on store-onboarding-queue.json must be rejected.
    outside = tmp_path / "outside.json"
    outside.write_text("do-not-overwrite", encoding="utf-8")
    hornero_dir = root / "home/ana/.config/hornero"
    hornero_dir.mkdir(parents=True, exist_ok=True)
    (hornero_dir / "store-onboarding-queue.json").symlink_to(outside)
    (root / "usr/lib/hornero/installation-plan.json").write_text(
        json.dumps({"selection": {"deferredApps": ["gear-lever"]}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="symlink"):
        defaults_mod.configure_user_defaults(root, profiles_path=PROFILES_JSON)
    assert outside.read_text(encoding="utf-8") == "do-not-overwrite"


def test_live_runtime_packages_and_flathub_setup_verification(tmp_path):
    live_pkgs = {
        line.strip()
        for line in (ROOT / "image/archiso/packages.x86_64").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {
        "flatpak",
        "appstream",
        "fuse2",
        "xdg-desktop-portal",
        "xdg-desktop-portal-gtk",
        "xdg-desktop-portal-hyprland",
    } <= live_pkgs

    # Build minimal bootable target root and verify hornero-flathub-setup.service checks.
    boot = tmp_path / "boot/grub"
    boot.mkdir(parents=True)
    (boot / "grub.cfg").write_text("menuentry 'HorneroOS' {}\n", encoding="utf-8")
    (tmp_path / "boot/vmlinuz-linux").write_bytes(b"kernel")
    (tmp_path / "boot/initramfs-linux.img").write_bytes(b"initramfs")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/os-release").write_text("ID=horneroos\n", encoding="utf-8")
    (tmp_path / "etc/passwd").write_text(
        "hornero:x:1000:1000::/home/hornero:/usr/bin/zsh\n", encoding="utf-8"
    )
    (tmp_path / "etc/pacman.conf").write_text("[core]\n", encoding="utf-8")

    # Absent unit: passes cleanly.
    assert verify_mod.verify_install(tmp_path) == []

    # Installed without enablement symlink: fails clearly.
    unit = tmp_path / "etc/systemd/user/hornero-flathub-setup.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]\nDescription=Flathub\n[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    problems = verify_mod.verify_install(tmp_path)
    assert any("hornero-flathub-setup.service installed but not enabled" in p for p in problems)

    # Enabled under default.target.wants: passes cleanly.
    wants = tmp_path / "etc/systemd/user/default.target.wants"
    wants.mkdir(parents=True)
    (wants / "hornero-flathub-setup.service").symlink_to("../hornero-flathub-setup.service")
    assert verify_mod.verify_install(tmp_path) == []

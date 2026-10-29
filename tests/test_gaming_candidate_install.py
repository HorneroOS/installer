"""Regression tests for the Gaming candidate install failure found in VM QA.

The first candidate ISO install failed with "target not found" for
lib32-vulkan-icd-loader, steam-devices, lib32-gamemode, lib32-mangohud and
hornero-profile-gaming-hyprland-desktop-gaming: the profile-package builder
never received --candidate-gaming, and no pacman configuration enabled the
multilib repository that ships the 32-bit gaming packages.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_profile_package_builder_forwards_candidate_gaming() -> None:
    script = (ROOT / "scripts" / "build-package-repository.sh").read_text()
    assert "HORNEROS_INSTALLER_CANDIDATE_GAMING" in script
    assert "candidate_args+=(--candidate-gaming)" in script


def test_multilib_enabled_where_packages_are_resolved() -> None:
    confs = [
        ROOT / "image" / "archiso" / "pacman.conf",
        ROOT / "image" / "archiso" / "airootfs" / "etc" / "pacman.conf",
    ]
    for conf in confs:
        assert "[multilib]" in conf.read_text(), conf
    build_iso = (ROOT / "scripts" / "build-iso.sh").read_text()
    # Both generated configs (build pacman.conf and target-pacman.conf).
    assert build_iso.count("[multilib]") >= 2

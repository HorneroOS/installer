"""Candidate Recovery choice resolves from the canonical catalogue only."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = Path(os.environ.get("HORNEROS_PRODUCT_SOURCE", "/tmp/hornero-main"))


def _renderer():
    spec = importlib.util.spec_from_file_location(
        "render_installer_catalogue", ROOT / "scripts" / "render-installer-catalogue.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    not (PRODUCT / "editions" / "catalogue.yaml").exists()
    or "snapshots" not in (PRODUCT / "editions" / "catalogue.yaml").read_text(encoding="utf-8"),
    reason="canonical Hornero product source with snapshots capability not available",
)


def test_default_choices_never_include_recovery_candidate():
    renderer = _renderer()
    options = renderer.choices(PRODUCT)
    assert not any(c["id"] == "desktop-hyprland-recovery" for c in options)
    # The capability defaults off: snapper must not leak into any
    # default composition.
    for choice in options:
        assert "snapper" not in choice["packages"]


def test_candidate_recovery_choice_is_honest_and_complete():
    renderer = _renderer()
    options = renderer.choices(PRODUCT, candidate_recovery=True)
    recovery = [c for c in options if c["id"] == "desktop-hyprland-recovery"]
    assert len(recovery) == 1
    choice = recovery[0]
    assert choice["candidate"] is True
    assert choice["isDefault"] is False
    assert choice["capabilities"] == ["snapshots"]
    for package in ("snapper", "snap-pac", "grub-btrfs"):
        assert package in choice["packages"]
    # Candidate copy must never claim proven rollback.
    assert "candidate" in choice["description"].lower()
    assert "not" in choice["description"].lower()
    assert "rollback is proven" not in choice["description"].lower()
    selection = choice["profile"]["recoverySelection"]
    assert selection["capabilities"] == ["snapshots"]
    assert "snapper-cleanup.timer" in selection["services"]

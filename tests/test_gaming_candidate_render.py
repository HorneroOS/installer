"""Candidate Gaming choices resolve from the canonical catalogue only."""
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
    or "gamingSpecializations"
    not in (PRODUCT / "editions" / "catalogue.yaml").read_text(encoding="utf-8"),
    reason="canonical Hornero product source with Gaming not available",
)


def test_default_choices_include_preview_gaming_edition():
    renderer = _renderer()
    options = renderer.choices(PRODUCT)
    ids = [choice["id"] for choice in options]
    assert "desktop-hyprland" in ids
    # The promoted Gaming edition is offered by the default render...
    gaming = [c for c in options if c["edition"] == "gaming"]
    assert gaming and all(c["maturity"] == "preview" for c in gaming)
    # ...but specialization choices stay candidate-only.
    assert not any(item_id.startswith("gaming-hyprland-") for item_id in ids)


def test_gaming_choices_describe_gaming_not_agents():
    renderer = _renderer()
    options = renderer.choices(PRODUCT)
    gaming = [c for c in options if c["edition"] == "gaming"]
    assert gaming
    for choice in gaming:
        assert choice["description"].startswith("Gaming desktop based on HorneroOS Desktop")
        assert "autonomous-agent" not in choice["description"]


def test_candidate_choices_cover_all_profiles_without_steam():
    renderer = _renderer()
    options = renderer.choices(PRODUCT, candidate_gaming=True)
    gaming = [choice for choice in options if choice["id"].startswith("gaming-hyprland-")]
    assert len(gaming) == 6
    for choice in gaming:
        assert choice["maturity"] == "preview"
        assert choice["candidate"] is True
        assert choice["isDefault"] is False
        assert "Preview edition" in choice["description"]
        # Steam is proprietary: never installed by group selection.
        assert "steam" not in choice["packages"]
        selection = choice["profile"]["gamingSelection"]
        assert selection["specializations"] == choice["specializations"]
    desktop = next(c for c in gaming if c["id"] == "gaming-hyprland-desktop-gaming")
    assert desktop["profile"]["gamingSelection"]["proprietaryOptInRequired"] == ["steam"]

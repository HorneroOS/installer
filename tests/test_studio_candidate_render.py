"""Candidate Studio choices resolve from the canonical catalogue only."""
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
    not (PRODUCT / "editions" / "catalogue.yaml").exists(),
    reason="canonical Hornero product source not available",
)


def test_default_choices_include_preview_studio_edition():
    renderer = _renderer()
    options = renderer.choices(PRODUCT)
    ids = [choice["id"] for choice in options]
    assert "desktop-hyprland" in ids
    studio = [c for c in options if c["edition"] == "studio"]
    assert studio and all(c["maturity"] == "preview" for c in studio)
    assert not any(item_id.startswith("studio-hyprland-") for item_id in ids)


def test_candidate_choices_cover_all_specializations_without_proprietary_packages():
    renderer = _renderer()
    options = renderer.choices(PRODUCT, candidate_studio=True)
    studio = [choice for choice in options if choice["id"].startswith("studio-hyprland-")]
    assert len(studio) == 10
    for choice in studio:
        assert choice["maturity"] == "planned"
        assert choice["candidate"] is True
        assert "Planned edition" in choice["description"]
        # Proprietary payloads are never installed by group selection
        # (canonical opt-in list: reaper, penpot — horneroctl studio).
        assert "reaper" not in choice["packages"]
        # Canonical installed metadata records the selection.
        selection = choice["profile"]["studioSelection"]
        assert selection["specializations"] == choice["specializations"]


def test_candidate_audio_selection_records_proprietary_opt_ins():
    renderer = _renderer()
    options = renderer.choices(PRODUCT, candidate_studio=True)
    audio = next(c for c in options if c["id"] == "studio-hyprland-audio-music-production")
    selection = audio["profile"]["studioSelection"]
    assert set(selection["proprietaryOptInRequired"]) == {"reaper"}
    assert "ardour" in audio["packages"]


def test_candidate_custom_selection_installs_platform_only_apps():
    renderer = _renderer()
    options = renderer.choices(PRODUCT, candidate_studio=True)
    custom = next(c for c in options if c["id"] == "studio-hyprland-custom-selection")
    assert "pipewire-jack" in custom["packages"]
    assert "ardour" not in custom["packages"]
    assert "blender" not in custom["packages"]

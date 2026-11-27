"""Calamares branding and the live medium on Hornero Signal (RFC 0001).

Pins the Signal Night palette in branding.desc, stylesheet.qss, the
slideshow and the banner; keeps the old brand palette, Rubik and Material
out of the installer UI; checks that the slideshow only lists packages the
installer choices really add; and that the live medium ships IBM Plex.
"""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BRANDING = ROOT / "image/calamares/branding/hornero"
SHOW = (BRANDING / "show.qml").read_text(encoding="utf-8")
QSS = (BRANDING / "stylesheet.qss").read_text(encoding="utf-8")
BANNER = (BRANDING / "installer-banner.svg").read_text(encoding="utf-8")
NIRI = (BRANDING / "screenshots/niri-experimental.svg").read_text(encoding="utf-8")
LIVE_PACKAGES = (ROOT / "image/archiso/packages.x86_64").read_text(encoding="utf-8")
LIVE_SETUP = (ROOT / "image/archiso/airootfs/usr/local/bin/hornero-live-session-setup").read_text(encoding="utf-8")
COMPOSITIONS = json.loads((ROOT / "image/calamares/modules/compositions.json").read_text(encoding="utf-8"))

# RFC 0001 §3.2 Signal Night with amendment 2 (ruleStrong #707A85).
NIGHT = {
    "ground": "#0C0F13", "sunken": "#101419", "base": "#13171D",
    "panel": "#181D24", "raised": "#1F252E", "lifted": "#283039",
    "ink": "#ECE6DA", "inkMuted": "#A8ABAD", "inkFaint": "#737980",
    "rule": "#2C333C", "ruleStrong": "#707A85", "signal": "#F2A33A",
    "onSignal": "#1A1205", "signalWell": "#3A2A12", "onSignalWell": "#FFD9A3",
    "focus": "#7EC1EA", "cueWell": "#16303F", "onCueWell": "#CDE8F8",
    "alert": "#F0705A",
}
OLD_BRAND = ("#1D1410", "#F6E9DB", "#F2B749", "#E07856", "#241610", "#D9C6B2", "#B24827")
UI_SURFACES = {"show.qml": SHOW, "stylesheet.qss": QSS, "installer-banner.svg": BANNER,
               "niri-experimental.svg": NIRI}


def _hexes(text):
    return {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", text)}


def test_branding_desc_uses_signal_sidebar_and_qml_slideshow():
    desc = yaml.safe_load((BRANDING / "branding.desc").read_text(encoding="utf-8"))
    assert desc["slideshow"] == "show.qml"
    assert desc["slideshowAPI"] == 2
    assert desc["style"] == {
        "SidebarBackground": NIGHT["ground"],
        "SidebarText": NIGHT["ink"],
        "SidebarTextCurrent": NIGHT["onSignalWell"],
        "SidebarBackgroundCurrent": NIGHT["signalWell"],
    }


def test_ui_surfaces_use_only_signal_night_roles():
    allowed = set(NIGHT.values())
    for name, text in UI_SURFACES.items():
        extra = _hexes(text) - allowed
        assert not extra, (name, sorted(extra))


def test_no_old_brand_palette_rubik_or_material():
    for name, text in UI_SURFACES.items():
        for colour in OLD_BRAND:
            assert colour.lower() not in text.lower(), (name, colour)
        assert "Rubik" not in text, name
        assert "Material" not in text, name
        assert "Gradient" not in text and "qlineargradient" not in text, name


def test_plex_type_everywhere():
    assert '"IBM Plex Sans"' in QSS and '"IBM Plex Mono"' in QSS
    for family in ("IBM Plex Sans", "IBM Plex Mono", "IBM Plex Sans Condensed"):
        assert f'"{family}"' in SHOW
    assert "IBM Plex Sans Condensed" in BANNER and "IBM Plex Mono" in BANNER


def test_separate_windows_get_a_dark_surface():
    block = QSS.split("QDialog,", 1)[1].split("}", 1)[0]
    assert "QMessageBox" in block and "background-color: #181D24" in block
    assert "color: #ECE6DA" in block


def test_focus_and_primary_action_follow_signal():
    assert "QPushButton:focus" in QSS and "2px solid #7EC1EA" in QSS
    default = QSS.split("QPushButton:default {", 1)[1].split("}", 1)[0]
    assert "#F2A33A" in default and "#1A1205" in default
    assert "border-radius: 3px" in QSS


def test_slideshow_is_calamares_api2_and_honest():
    assert "import calamares.slideshow 1.0" in SHOW
    assert "function onActivate()" in SHOW and "function onLeave()" in SHOW
    for channel in ("01 · DESKTOP", "02 · STUDIO", "03 · GAMING"):
        assert channel in SHOW
    # Every edition is labelled with its real maturity, never more.
    assert SHOW.count('chip: "SUPPORTED"') == 3
    for claim in ("stable", "Stable", "certified", "production-ready"):
        assert claim not in SHOW
    # Typographic cards only: no screenshot can misrepresent the release.
    assert "Image {" not in SHOW


def _options():
    return {option["id"]: set(option["packages"]) for option in COMPOSITIONS["options"]}


def _listed(channel):
    block = SHOW.split(f'channel: "{channel}"', 1)[1].split("Slide {", 1)[0]
    match = re.search(r"contents: \[(.*?)\]", block, re.DOTALL)
    assert match, channel
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_slideshow_package_lists_match_installer_choices():
    options = _options()
    desktop = options["desktop-hyprland"]
    assert _listed("01 · DESKTOP") <= desktop
    for channel, option in (("02 · STUDIO", "studio-hyprland"), ("03 · GAMING", "gaming-hyprland")):
        listed = _listed(channel)
        adds = options[option] - desktop
        assert listed <= adds, (channel, sorted(listed - adds))


def test_banner_keeps_registration_tick_and_diagonal():
    assert '<rect x="0" y="0" width="2" height="10" fill="#F2A33A"/>' in BANNER
    assert "La Plata 45° diagonal" in BANNER
    assert "PREVIEW" in BANNER


def test_niri_card_stays_honestly_labelled():
    assert "not a desktop screenshot" in NIRI
    assert "EXPERIMENTAL" in NIRI


def test_legacy_wallpaper_slides_removed():
    for name in ("wallpaper-hornero-dark.jpg", "wallpaper-hornero-199x.jpg"):
        assert not (BRANDING / "screenshots" / name).exists()


def test_live_medium_ships_plex_and_no_material_fonts():
    packages = {line.strip() for line in LIVE_PACKAGES.splitlines() if line.strip() and not line.startswith("#")}
    assert {"fontconfig", "ttf-ibm-plex", "ttf-cascadia-code-nerd", "noto-fonts", "noto-fonts-emoji", "noto-fonts-cjk"} <= packages
    for legacy in ("ttf-material-symbols-variable", "python-materialyoucolor", "ttf-rubik-vf"):
        assert legacy not in packages


def test_live_fontconfig_exposes_hornero_glyphs_and_signal_aliases():
    import xml.etree.ElementTree as ET

    dropin = ROOT / "image/archiso/airootfs/etc/fonts/conf.d/60-hornero-signal.conf"
    assert dropin.is_file()
    tree = ET.parse(dropin)
    dirs = [el.text for el in tree.findall(".//dir") if el.text]
    assert "/etc/xdg/quickshell/hornero/assets/fonts" in dirs
    text = dropin.read_text(encoding="utf-8")
    for family in ("IBM Plex Sans", "IBM Plex Mono", "Noto Sans CJK", "Noto Color Emoji"):
        assert family in text, family


def test_live_session_keeps_factory_theme_and_layout():
    # The live user gets the shipped factory defaults (theme
    # hornero-signal-night, layout preset cockpit, owned by HorneroOS/config
    # and HorneroOS/shell). The live setup only disarms idle actions; it
    # must never pin a theme, wallpaper scheme or layout of its own.
    for key in ('"theme"', '"appearance"', '"bar"', "preset apply", "theme apply", "hornero-dark", "hornero-199x"):
        assert key not in LIVE_SETUP, key


def test_stylesheet_covers_every_calamares_page_family():
    # installer#102: no page may fall back to Qt's stock grey. Every widget
    # family a Calamares page uses needs a Signal rule (partition, users,
    # summary, install progress, finished, dialogs, scroll areas).
    for selector in (
        "#mainApp", "QMainWindow", "#sidebarApp", "#view-button-next", "#view-button-cancel",
        "#exec-progress", "#exec-message", "#scrollAreaWidgetContents",
        "#partitionBarView", "#licenseItem", "QHeaderView::section",
        "QTableView", "QTabBar::tab:selected", "QGroupBox", "QCheckBox::indicator",
        "QRadioButton::indicator", "QSlider::handle:horizontal", "QToolButton",
        "QScrollBar:horizontal", "QScrollBar:vertical", "QToolTip", "QDialog",
        "QMessageBox", "QMenu", "QComboBox", "QLineEdit", "QTextBrowser",
        "QProgressBar::chunk", "#CheckerContainer", "#errorLabel", "#warningLabel",
    ):
        assert selector in QSS, selector


def test_error_and_warning_blocks_use_signal_night_roles():
    error_block = QSS.split("#errorLabel,", 1)[1].split("}", 1)[0]
    assert "#F0705A" in error_block and "#181D24" in error_block and "#ECE6DA" in error_block
    warning_block = QSS.split("#warningLabel,", 1)[1].split("}", 1)[0]
    assert "#3A2A12" in warning_block and "#F2A33A" in warning_block and "#FFD9A3" in warning_block


def test_stylesheet_never_encodes_state_by_colour_alone():
    # Checked controls change fill and boundary, the active tab gets an
    # underline, the selected row an on-air bar.
    assert "border-bottom: 2px solid #F2A33A" in QSS
    assert "border-left: 2px solid #F2A33A" in QSS
    assert "QCheckBox::indicator:checked" in QSS


def test_banner_fits_the_welcome_area_without_clipping():
    # installer#101: the 760 px banner clipped the PREVIEW chip to "PRE".
    root = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', BANNER)
    assert root and root.group(1) == root.group(3) and root.group(2) == root.group(4)
    assert int(root.group(1)) <= 640
    chip = re.search(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" rx="3" fill="#F2A33A"/>', BANNER)
    assert chip and int(chip.group(1)) + int(chip.group(3)) + 16 <= int(root.group(1))
    assert int(chip.group(2)) + int(chip.group(4)) + 16 <= int(root.group(2))

def test_brand_marks_carry_signal_colours_only():
    """hornero.svg / hornero-installer.svg are copies of config assets/brand."""
    for name in ("hornero.svg", "hornero-installer.svg", "installer-banner.svg"):
        text = (BRANDING / name).read_text(encoding="utf-8").lower()
        for colour in OLD_BRAND + ("#2b1a11", "#7c4a2c", "#fffdf7", "#e89a55"):
            assert colour.lower() not in text, (name, colour)

# Hornero Signal installer branding (2026-11-16)

Renders produced on the maintainer's Arch Linux host. No ISO was built and
no VM was booted for this evidence.

- `slideshow-00.jpg` … `slideshow-04.jpg` — `image/calamares/branding/hornero/show.qml`
  loaded with the `calamares.slideshow` QML module from the pinned Calamares
  3.4.3 source (`src/qml/calamares-qt6/slideshow`, archive SHA256 from
  `installer.lock.yaml`) in Qt 6.12 `qml` on the offscreen platform at
  960x540, IBM Plex from `ttf-ibm-plex` 6.4.0, one frame per slide.
- `installer-banner.png` — `installer-banner.svg` rasterized with
  ImageMagick at 96 dpi.
- `niri-card.png` — `screenshots/niri-experimental.svg` rasterized with
  ImageMagick and scaled to 640 px wide.

Not covered: `stylesheet.qss` and the sidebar colours inside a running
Calamares window. They need a disposable-VM run of a rebuilt ISO.

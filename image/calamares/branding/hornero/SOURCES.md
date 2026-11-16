# Calamares branding sources

The artwork in this directory comes from the canonical HorneroOS brand
assets in HorneroOS/config (`assets/brand/`, see `docs/BRAND.md` there).
Files are either used unmodified, resized, or — for `installer-banner.svg`
— an original composition in this repo built from the canonical art.
Nothing here is third-party:

- `hornero.svg` — `assets/brand/logo.svg` (canonical full-color mark).
- `hornero-installer.svg` — `assets/brand/icons/hornero-app.svg`.
- `installer-banner.svg` — original Hornero Signal composition in this repo
  (RFC 0001 + amendment 2, Signal Bezel) that inlines the bird and branch
  geometry from `assets/brand/logo-dark.svg`, recoloured to Signal Night
  roles (ground `#0C0F13`, ink `#ECE6DA`, signal `#F2A33A`), with IBM Plex
  type and the La Plata diagonal.
- `show.qml` and `stylesheet.qss` — original Hornero Signal slideshow and
  Calamares stylesheet in this repo. The slideshow is typographic (no
  screenshots); its package lists mirror `modules/compositions.json`.
- `screenshots/desktop-hyprland.jpg` — certified desktop preview pinned in
  `installer.lock.yaml` (`profileMedia.desktopPreview`, source in
  HorneroOS/website).
- `screenshots/niri-experimental.svg` — information card (not a screenshot);
  text and honesty labelling are intentional and checked by
  `scripts/check-installer.py`.

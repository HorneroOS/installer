# Signal Calamares chrome (installer#102, installer#101)

Offscreen renders of `image/calamares/branding/hornero/stylesheet.qss` applied
to stand-in Qt widgets that use the Calamares 3.4.3 object names
(`scripts/render-branding-preview.py`, PySide6, `QT_QPA_PLATFORM=offscreen`).

They are NOT screenshots of the running installer. Calamares paints some
parts itself from the application palette (partition bars, the welcome
requirement rows, the sidebar step list), which this harness cannot show.
Only a real Calamares run in the QA VM (4 GiB guest, see qa VM-HOWTO section 9)
proves those, plus the error block and every real page. That capture set is
still owed.

- `pages-welcome-partition-users-summary-1280x800.png`: welcome (with the
  600 px banner, `PREVIEW` chip fully visible), partition, users, summary.
- `pages-install-finish-dialog-1.5x.png`: install progress, finished,
  confirmation dialog, and the summary page at 1024x768 logical, 1.5x scale.

# HorneroOS installer

Installer and installation workflows for Hornero OS.

## Scope

This repository owns the **program and workflow that installs Hornero OS**:
disk partitioning, filesystems, bootloader configuration, user creation,
locale/timezone, hardware detection and package/profile selection.

It is deliberately separate from the final image-build service. There is no
`HorneroOS/iso` repository yet, so a provisional Archiso profile lives here
until that ownership boundary is established:

- `installer` = the program/workflow that installs Hornero.
- `image/archiso` = the provisional bootable delivery medium / image generation.

## Implementation status

The first graphical implementation in this repository uses **Calamares**. It
is explicitly provisional: [Panda Foss](https://github.com/PandaFoss) is
developing and will own the custom HorneroOS installer intended to become the
official path. This repository's Calamares implementation bridges current
product testing and remains provisional until Panda's version is ready to
publish and passes acceptance. Its intended path is a booted live image, a
human-reviewed disk layout and a Calamares net-install into the selected target.
No ISO has completed installation acceptance yet. Never run preview media
against a system that contains data you have not backed up.

The canonical edition and package composition model lives in
[`HorneroOS/hornero`'s `editions/catalogue.yaml`](https://github.com/HorneroOS/hornero/blob/main/editions/catalogue.yaml).
The installer pins that source revision and asks its resolver for package
composition. It does not maintain an independent edition catalogue. Only
installable product compositions are shown; experimental backends are labeled
and planned editions remain hidden.

## Development checks

```sh
python3 -m pip install --user PyYAML jsonschema
python3 scripts/render-installer-catalogue.py \
  --cache-dir "$HOME/.cache/hornero-installer" \
  --output /tmp/hornero-installer/packagechooser.conf \
  --profile-packages-dir /tmp/hornero-installer/profile-packages
python3 scripts/check-installer.py
```

The render command verifies the pinned catalogue/resolver hashes and writes
the package chooser, a provenance record, and one metadata-package recipe per
installable composition outside the repository. Those recipes are built into
the local install repository by the disposable image builder.
`scripts/build-iso.sh` requires a disposable Arch VM with 40 GiB free for work
and 12 GiB for output (52 GiB if both share a filesystem), and limits
compilation/compression to two workers. Building
packages or images never runs against the host installation.

See [the provisional Calamares guide](docs/calamares-provisional.md) for
installation limits, recovery notes, image composition and acceptance gates.

## Contribution intake and planning

Installer issues use the shared HorneroOS organization forms for bugs,
features, documentation, and engineering tasks. This repository intentionally
does not define a local `ISSUE_TEMPLATE` directory, so GitHub can inherit the
organization defaults. The `label-sync` workflow keeps the shared labels
available here without deleting installer-specific labels. The installer
team retains ownership of installation behavior and release decisions.

## License

[MIT](LICENSE).

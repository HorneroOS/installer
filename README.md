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
The published v0.2.0-preview22 ISO passed the VM installation matrix
(Desktop and Studio, UEFI and legacy BIOS, encrypted and unencrypted;
composition carried from preview21, cancel-cleanup retested end to end).
That is virtual-machine evidence only: no physical-hardware validation
has been performed, the installer's own R11 record still lists UEFI
first login as pending and installed package parity as unverified, and
the acceptance matrix for physical hardware remains open. Never run preview media against a system that
contains data you have not backed up. See the
[R11 validation record](docs/r11-validation.md).

The canonical edition and package composition model lives in
[`HorneroOS/hornero`'s `editions/catalogue.yaml`](https://github.com/HorneroOS/hornero/blob/main/editions/catalogue.yaml).
The installer pins that source revision and asks its resolver for package
composition. It does not maintain an independent edition catalogue. Only
installable product compositions are shown; experimental backends are labeled
and planned editions remain hidden.

## Try the Preview ISO

Download and verify the signed v0.2.0-preview22 ISO from the
[HorneroOS website install page](https://www.horneroos.com/install) or
the [v0.2.0-preview22 release](https://github.com/HorneroOS/hornero/releases/tag/v0.2.0-preview22).
It installs Desktop or Studio Preview and was validated in virtual
machines only; no physical-hardware validation has been performed.
Report installation problems in this repository's issue chooser.

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
compilation/compression to two workers. The `python-yaml` and
`python-jsonschema` Arch packages are required alongside the build tools; the
builder checks these Python dependencies before doing package or image work.
Building packages or images never runs against the host installation.

See [the provisional Calamares guide](docs/calamares-provisional.md) for
installation limits, recovery notes, image composition and acceptance gates.

## Contribution intake and planning

Installer issues use the shared HorneroOS organization forms for bugs,
features, documentation, and engineering tasks. This repository intentionally
does not define a local `ISSUE_TEMPLATE` directory, so GitHub can inherit the
organization defaults. The `label-sync` workflow keeps the shared labels
available here without deleting installer-specific labels. The installer
team retains ownership of installation behavior and release decisions.

The public [HorneroOS Installer project](https://github.com/orgs/HorneroOS/projects/1)
tracks installation outcomes, acceptance evidence, and the transition from
the provisional Calamares path to Panda Foss's custom official installer. Its
roadmap is an ordering aid rather than a release-date promise; this repository
and the canonical edition catalogue remain the sources for implementation
and package composition.

## License

[MIT](LICENSE).

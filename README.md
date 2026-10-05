# installer

Installer and installation workflows for Hornero OS.

## Scope

This repository owns the **program and workflow that installs Hornero OS**:
disk partitioning, filesystems, bootloader configuration, user creation,
locale/timezone, hardware detection and package/profile selection.

It is deliberately separate from bootable image generation (a future `iso`
repository, not created yet):

- `installer` = the program/workflow that installs Hornero.
- `iso` = the bootable delivery medium / image generation.

## Implementation status

The installer implementation is **not decided yet**. Candidates include
integrating with archinstall or Calamares, or building a custom installer —
no choice has been made, and this repository must not be read as locking in
any of them.

The canonical edition and package composition model lives in
[`HorneroOS/hornero`'s `editions/catalogue.yaml`](https://github.com/HorneroOS/hornero/blob/main/editions/catalogue.yaml).
It describes Desktop, Server, Agents and Studio, with maturity and compositor
choices. The installer must consume that product model; it must not define
editions or maintain parallel package lists. Planned editions are not
installation options, and experimental compositors must remain clearly marked.

Edition composition exists independently of the installer. The catalogue
resolver in `HorneroOS/hornero` produces machine-readable JSON for consumers.
Future installer work should pin a catalogue revision and consume that output
rather than reimplement its inheritance or package selection.

## Status

Early scaffolding. No installer code lives here yet.

## License

[MIT](LICENSE).

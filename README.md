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

Possible future installation profiles include Minimal, Desktop, Developer and
Agentic, but these are directions, not committed editions.

## Status

Early scaffolding. No installer code lives here yet.

## License

[MIT](LICENSE).

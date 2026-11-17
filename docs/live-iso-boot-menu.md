# Live ISO boot menu

The live ISO has two boot paths (`image/archiso/profiledef.sh`):

| Firmware | Loader | Themed |
|---|---|---|
| BIOS | syslinux `vesamenu.c32` | **Yes** - Hornero Signal (this document) |
| UEFI | systemd-boot | No - text menu only |

## BIOS (syslinux)

`image/archiso/syslinux/syslinux.cfg` selects the graphical menu and Signal
Night colours; `splash.png` (800 x 600) carries the bird mark, the
`HORNEROOS · INSTALLER` eyebrow with the registration tick, the La Plata
diagonal and the key hint. archiso copies `splash.png` from this directory into
the ISO's `syslinux/`. Syslinux cannot draw the on-air accent bar, so the
selected row is a raised block and the amber lives in the artwork.

`splash.png` is generated, not hand-edited. Source of truth:
`HorneroOS/config` `desktop/boot/art/iso-splash.svg`, rendered with
`scripts/render-boot-assets.sh --out DIR` (`DIR/iso/splash.png`). To refresh,
render from the config revision pinned in `installer.lock.yaml` and replace the
file.

Verified with real syslinux 6.04 + SeaBIOS in QEMU (menu drawn from a FAT disk
carrying the exact `syslinux.cfg` and `splash.png`, archiso placeholders
substituted). Not verified: a full `mkarchiso` build and a boot of the resulting
ISO (maintainer-only, see `docs/release-iso.md`).

## UEFI (systemd-boot) - follow-up

systemd-boot has no graphical theme support. Theming the UEFI live menu means
switching `bootmodes` to `uefi.grub` and adding archiso's `grub/` files with the
Hornero GRUB theme from `HorneroOS/config` (`desktop/boot/grub`). That changes
the only UEFI path that is known to work and needs a real ISO build plus a UEFI
VM boot to validate, so it is intentionally not part of this change.

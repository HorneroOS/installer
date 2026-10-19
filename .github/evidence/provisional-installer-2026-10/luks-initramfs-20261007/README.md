# Encrypted UEFI install failure — 2026-10-07

This evidence comes from the PR source at `1c63ce920616c7c413bfc08526df27a66159a06d`
and its ISO, built in the disposable Arch builder VM. The ISO manifest records
product revision `7471351cbe26e2a8754fd1bd9c5f4a2b984115ad`; its SHA-256 is
`67e68368bac5d1ab43aab340d0df6d588619c9da8780bb45bcf8a6d212433586`.

The UEFI guest used a fresh 40 GiB QCOW2 target, 4 GiB RAM and two virtual
CPUs. Calamares completed an encrypted Btrfs installation and installed GRUB
on the target's ESP. GRUB loaded the kernel and initramfs. First boot then
entered the initramfs emergency shell because the container had not been
unlocked.

The guest's `/proc/cmdline` contained `root=UUID=75c90de4-2cee-4ffc-a5ba-711c0c664dcd`
but no `cryptdevice`. `blkid` showed `/dev/vda3` as LUKS UUID
`86c73f5f-07a7-4536-8809-28860da82c6`, while its unlocked Btrfs filesystem UUID
matched the kernel's `root=UUID`. This isolates the fault to missing early
LUKS unlock configuration, rather than GRUB failing to load the kernel or the
root filesystem UUID being wrong.

The corrected source adds mkinitcpio's `encrypt` hook before `filesystems`,
and Calamares' `grubcfg` module generates the `cryptdevice` and mapper-root
parameters. The EFI System Partition remains unencrypted at `/boot`; the
initramfs contains no embedded LUKS key. The correction still needs a rebuilt
ISO and repeated UEFI and legacy-BIOS installation plus first-boot tests.

## Captures

- `uefi-layout-summary.png` — reviewed hybrid GPT layout on the blank virtual
  disk: 512 MiB ESP, 8 MiB BIOS boot partition and encrypted Btrfs root.
- `uefi-grub-kernel-load.png` — GRUB loads the installed kernel and initramfs.
- `uefi-initramfs-root-failure.png` — the original first-boot root mount
  failure that triggered this diagnosis.

This is diagnostic evidence, not a passing acceptance result.

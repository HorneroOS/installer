# R11 provisional ISO validation

Date: 2026-10-24  
Installer source: `cfc0ca2d7cdbd63806f9c8f1825e6d25fc44f839`  
Hornero product revision: `03476d8bc71626648434587470064e2b82b88463`  
Calamares: `3.4.3`  
Artifact: `horneroos-2026.10-provisional-x86_64.iso`  
Size: `2,721,251,328` bytes  
SHA-256: `93d70f47327d019dadd546eadf6169b93b7627589665190e2f7981b25a04427f`

The ISO and test disks are local, disposable artifacts. The ISO is unsigned and
has not been published as a release.

## UEFI cancellation

- Booted the live ISO in a disposable OVMF VM with a blank qcow2 target disk.
- Resolved the Arch mirror through the VM network after setting a temporary
  DNS server in NetworkManager; the launcher then opened Calamares.
- Started an encrypted erase-disk install and cancelled during package
  installation (64%). Calamares returned to the live desktop.
- The runner logged `Cleaned temporary Calamares target ...`. `findmnt` showed
  no temporary Calamares target, `/etc/hosts`, or `/etc/resolv.conf` bind mount.

## UEFI successful installation and reboot

- Completed Calamares' encrypted erase-disk flow. The summary showed GPT,
  a 512 MiB FAT32 EFI System Partition at `/boot`, an 8 MiB BIOS boot
  partition, and a LUKS-encrypted Btrfs root partition.
- Calamares displayed “All done.” Its log reported successful completion and
  unmounted the target's `/run`, `/proc`, `/home`, `/dev`, `/boot`, and root.
  After the runner exited, `findmnt` showed no temporary target or resolver
  mounts. The post-exit cleanup log was empty because Calamares had already
  removed its mounts on the success path.
- Rebooted from the installed disk with the ISO detached. OVMF selected the
  `HorneroOS` GRUB entry. The initramfs accepted the LUKS unlock request and
  reached the installed Hyprland session lock screen.
- The captured first-login attempts display `Login failed`. They do not
  establish which account name Calamares created or prove an authenticated
  UEFI desktop. Keep this acceptance gate pending until a successful login is
  verified against the installed account. Test credentials are not recorded
  here.

## Legacy BIOS installation and reboot

- Booted the same ISO in a disposable SeaBIOS VM. After resolving the Arch
  mirror, Calamares showed `BIOS` firmware and a blank 32 GiB `/dev/vda`.
- Completed the encrypted erase-disk flow. The summary showed GPT, a 512 MiB
  FAT32 EFI System Partition, an 8 MiB BIOS boot partition, a LUKS-encrypted
  Btrfs root, and GRUB installed to the MBR of `/dev/vda`.
- Calamares displayed “All done.” The session log reported
  `completion: succeeded` and unmounted the target's `/run`, `/proc`, `/home`,
  `/dev`, `/boot`, and root.
- Rebooted from the installed disk with the ISO detached. The BIOS GRUB path
  loaded the encrypted root, the test LUKS passphrase was accepted, and the
  installed Hyprland session lock screen appeared.
- The login automation had appended the supplied username to the value
  Calamares prefilled from the full name. The installed session opened
  successfully with that account name. Test credentials are not recorded
  here.

## Acceptance status

| Gate | Result |
| --- | --- |
| R11 ISO build and checksum manifest | Pass |
| UEFI live boot and Calamares launch | Pass |
| UEFI cancellation cleanup during package stage | Pass |
| Encrypted UEFI installation completes | Pass |
| Installed UEFI system unlocks and reaches session lock screen | Pass |
| UEFI first login and usable desktop | Pending (login attempts failed) |
| BIOS installation completes and Calamares cleans target mounts | Pass |
| Installed BIOS system unlocks and reaches session lock screen | Pass |
| BIOS first login and usable desktop | Pass |
| Installed composition/profile package parity | Not verified |
| Package-failure cleanup path | Not verified on R11 |
| Complete UEFI and BIOS acceptance through usable desktop | Incomplete |

## Installed composition audit command

After booting an installed VM, run the read-only audit from an installer
checkout that contains `scripts/check-installed-composition.py`, and pass the
`image/calamares/modules/compositions.json` generated for the exact ISO under
test:

```sh
python3 scripts/check-installed-composition.py \
  --root / \
  --compositions /path/to/exact-iso-source/image/calamares/modules/compositions.json
```

The report passes only when the installed profile package and source revision
match one manifest option, its metadata matches that resolver result, and all
resolver-selected packages are present in the installed pacman database. Base
image packages and transitive dependencies are expected extras, so this check
does not claim equality of the entire installed package database. Record the
JSON report alongside the VM firmware and boot evidence; a passing command
still does not complete UEFI or BIOS acceptance on its own.

This preview remains provisional and should only be exercised in disposable
VMs. Do not treat a successful ISO build or partition installation as
install-to-first-login acceptance. Signing and release publication remain
separate gates.

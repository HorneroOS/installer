# Provisional Calamares installer

This repository uses Calamares as a provisional graphical installer
implementation for current product testing. [Panda Foss](https://github.com/PandaFoss)
is developing and will own the custom HorneroOS installer intended to become
the official path. This separate Calamares implementation is a bridge; it
remains provisional until Panda's version is ready to publish and passes
acceptance. The Calamares framework and its configuration are packaged
separately, following Calamares deployment guidance.

Installer contributors should follow the shared
[HorneroOS design language](https://github.com/HorneroOS/docs/blob/main/development/design-language.md)
for product identity, accessible interaction, honest maturity labels and
high-consequence confirmation flows. The installer-specific controls and
acceptance gates remain documented in this guide.

The current image profile produced the published, signed
v0.2.0-preview22 Desktop+Studio Preview ISO (one x86_64 image). It
passed the VM installation matrix; it is not certified for physical
legacy BIOS, offer a graphical network tray and launch Calamares. Its
edition
legacy BIOS, offer a graphical network tray and launch Calamares. Its edition
choices come from the pinned
[`HorneroOS/hornero` edition catalogue](https://github.com/HorneroOS/hornero/blob/main/editions/catalogue.yaml)
and are rendered by `scripts/render-installer-catalogue.py`. The installer does
not maintain its own package lists. Each choice also installs a generated
`hornero-profile-*` metadata package containing the resolved edition,
compositor, maturity, package-set identifiers and pinned Hornero source
revision at `/usr/lib/hornero/system-profile.json`. The metadata package is
rendered from the same resolver result as the package chooser; it carries no
independent package list. `horneroctl system info` reads this record and
separates the installed compositor choice from the compositor active in the
current session. Installations made outside this installer can report their
active compositor without claiming an edition that was never recorded.
Only compositions whose product maturity
allows installation appear in the choice page; experimental compositor choices
are labelled as such. Planned editions stay hidden until their system and
installer path have been validated.
The Hyprland option includes an approved Hornero desktop capture. Niri uses an
explicit experimental-status card instead of a fabricated compositor
screenshot; the media lock records the capture's website commit and hashes.

## Before installing

- Back up anything on the selected disk. Choosing an erase layout destroys its
  existing partitions and data.
- Connect to the Internet before starting installation. The launcher checks
  both NetworkManager connectivity and DNS resolution of the Arch package
  server before opening Calamares. If either check fails, it explains what to
  repair and confirms that no disk changes have been made. Package installation
  runs inside the target chroot, so a pre-install step bind-mounts the live
  `/etc/resolv.conf` and `/etc/hosts` there. A cleanup step removes both mounts
  immediately after package installation and before user configuration,
  including after a failed package transaction. The pinned composition comes
  from Arch repositories and the temporary local installer package repository.
- The partition screen starts without a selected operation. Review the disk,
  partition map, encryption setting and final summary before confirming.
- Automated encryption uses the Calamares LUKS support and mkinitcpio's
  matching unlock hook. Keep the unlock phrase safe; HorneroOS cannot recover
  it. The unencrypted EFI system partition remains visible to the machine.
- The installer creates a named user with a password and `wheel`-based sudo.
  It does not create a shared default password, enable automatic login, or set
  a root password.
- Calamares runs with detailed local logging. After its window closes, the live
  session copies the log to `/var/log/hornero-installer/session.log`, readable
  by the live account; the live user receives no general root shell or access
  to other root-owned files.
- Desktop/Hyprland is the default install choice. Niri is explicitly marked
  Experimental while its product maturity remains experimental.
- Server, Agents and Studio do not appear while their catalogue entries remain
  Planned. A graphical live installer can eventually install a headless Server
  target without putting the live desktop on that target.
- The image build assembles a temporary local package repository from
  commit-pinned AUR recipes. The installer bind-mounts that repository into the
  target only during package installation. An emergency-capable cleanup step
  removes repository configuration after package installation succeeds or
  fails; VM acceptance still has to verify both paths.

## Current limits

R11 supersedes the 2026-10-23 build described below. Its exact artifact
identity, UEFI cancellation cleanup, encrypted install, and first-reboot
evidence are recorded in [the R11 validation record](r11-validation.md).
UEFI and legacy-BIOS installs both completed and unlocked the encrypted root.
The BIOS system reached the desktop, and login was verified using the
username Calamares created from its prefilled value. UEFI reached the login
screen; its login, installed
package/profile parity, and package-failure cleanup have not been verified.
Therefore the complete acceptance matrix remains open; the detailed
2026-10-23 report below is historical evidence, not the current test boundary.

Earlier disposable UEFI and legacy-BIOS runs reached Calamares and exposed
partitioning, package-chroot DNS, GRUB, and encrypted-root boot issues. Those
historical results and captures remain in
[provisional installer VM evidence](../.github/evidence/provisional-installer-2026-10/README.md).

On 2026-10-23, a fresh image built from installer revision
`78a292ec00c7eee989c68b40054580dff805270f` and product revision
`7471351cbe26e2a8754fd1bd9c5f4a2b984115ad` booted to the live desktop in
separate disposable UEFI and legacy-BIOS VMs. The exact artifact,
`horneroos-2026.10-provisional-x86_64.iso`, is 2,703,360,000 bytes with
SHA-256 `fde2e6f54f33c341afa6fa87a26cff86740f58e48d8b3ea949cafff35281a2a1`.
In both modes the new launcher DNS preflight displayed its warning before
Calamares opened and reported that no disk changes had been made. The test
VMs had no outbound access to the Arch package server, so neither run reached
partitioning or attempted an installation. A follow-up UEFI run used a
temporary rootless QEMU `passt` backend. DNS resolved the Arch mirror to
`49.12.124.107`, and an HTTP request reached the mirror. Calamares then failed
to start: the package requires Qt symbol `Qt_6.12`, but the live image has
`qt6-base 6.11.2-3`. The fresh image therefore still cannot install. The
evidence points to the disposable builder's installed packages not matching
the locked Arch snapshot; the build now needs to sync the builder to that
snapshot before compiling local packages. No partitioning or installation was
attempted. This validates live boot and DNS behavior only, not package
installation, temporary mount cleanup, installed package parity, encryption,
or first boot. The image is unsigned and provisional. Build and VM details
are tracked in installer
[issue #11](https://github.com/HorneroOS/installer/issues/11).

A previous image also reached the encrypted-root first boot and fell into the
initramfs emergency shell because it lacked the `encrypt` hook and GRUB's
kernel command line lacked `cryptdevice`. The current source orders
mkinitcpio's `encrypt` hook before `filesystems` and uses Calamares' `grubcfg`
module to generate mapper-aware kernel parameters. It keeps the EFI System
Partition at `/boot` and does not embed a LUKS key in the unencrypted
initramfs; this boot fix has not yet been retested in the latest image.

The initial installation attempt exposed a nested loop-device failure:
Calamares mounts its SquashFS source with `loop`, and Linux cannot create that
loop device when the source itself is inside Archiso's loop-mounted live
SquashFS. The build now places `base.sqfs` as a separate file on the ISO
filesystem and points `unpackfs` at that path. A prior corrected image had a
checksum matching its generated manifest and verified contents. The source
gates both the automatic launcher and menu entry on DNS resolution so a live
network failure is reported before disk partitioning. The 2026-10-23 image
includes and exercised this guard in both firmware modes. Its Calamares binary
does not start with the live image's Qt version, so a compatible rebuild is
required before install testing. A successful full install and installed-system
boot remain outstanding. The host
development machine is deliberately not used for ISO builds or disk tests.
Do not use this preview as the sole copy of important data or as an unattended
production deployment. Release signing and artifact publication remain an
explicit release gate. The live-image profile is owned here until a dedicated
image repository exists. See the [image build guide](../image/README.md).

Follow the [installation stages](install-stages.md),
[known installer issues](https://github.com/HorneroOS/installer/issues), and
[Calamares deployment documentation](https://calamares.codeberg.page/docs/deploy-configuration/).

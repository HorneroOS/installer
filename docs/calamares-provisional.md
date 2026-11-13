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
v0.2.0-preview32 Desktop+Studio+Gaming Preview ISO (one x86_64 image). It
passed disposable-VM installation validation (Desktop, Studio and
Gaming, UEFI, unencrypted; LUKS-encrypted installs, legacy BIOS, Niri
sessions and copytoram were not run on this artifact);
it is not certified for physical
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

## Bluetooth

Installed targets enable `bluetooth.service` through the existing
Calamares `services-systemd` module
(`image/calamares/modules/services-systemd.conf`). It is
`mandatory: false`: a Bluetooth-less VM or server install logs the
failure and continues, unlike the mandatory NetworkManager and SDDM
units. Enabling the service does not make the adapter discoverable or
pairable; pairing policy, the pairing agent and power persistence are
owned by the HorneroOS shell and config workstreams, not the installer.
`verify-install.py` fails the install only when bluez actually
installed its unit but the enablement symlink is missing.

The live session is the real HorneroOS Desktop, so it carries the same
stack: `bluez` and `bluez-utils` in `image/archiso/packages.x86_64`
and `bluetooth.service` enabled through
`airootfs/etc/systemd/system/multi-user.target.wants/`. The live
session gains no pairing privileges beyond the installed system.

Packages and firmware for installed targets are not installer-owned.
`linux-firmware`, which carries the Bluetooth adapter firmware, is
already in every rendered composition and in the live package list;
no per-vendor firmware package is needed on Arch. The installed
`bluez`/`bluez-utils` packages must arrive through the existing
catalogue mechanism, in this order:

1. `HorneroOS/hornero` adds `bluez` and `bluez-utils` (with Arch
   provenance entries) to the `desktop` package set in
   `editions/catalogue.yaml`. Studio and Gaming extend Desktop, so all
   three editions inherit them.
2. This repository bumps the product revision in
   `installer.lock.yaml` to that catalogue commit and re-renders with
   `scripts/render-installer-catalogue.py`, committing the resulting
   `image/calamares/modules/compositions.json` and
   `packagechooser.conf` diff. Never hand-edit those generated files.
3. `scripts/check-installer.py` then requires either every
   composition or none to carry `bluez`/`bluez-utils`, and
   `scripts/check-installed-composition.py` fails an installed system
   that is missing resolver-selected packages.

Existing Preview24/29 installations are not migrated by this
repository: the installer owns fresh installs only and has no updater,
preset or migration mechanism. The hand-off is exact: the
`HorneroOS/hornero` profile packages
(`hornero-profile-desktop-*`, `hornero-profile-studio-*`,
`hornero-profile-gaming-*`) gain `bluez`/`bluez-utils` dependencies so
`horneroctl package upgrade` pulls them, and `HorneroOS/config` ships
the BlueZ configuration and systemd preset that enables
`bluetooth.service` on upgrade. Paired devices and user preferences
live under `/var/lib/bluetooth` and user configuration; neither this
installer nor that migration may delete or reset them. Until those two
changes ship, Preview24/29 systems receive Bluetooth only by
reinstalling or by manually installing `bluez`/`bluez-utils` and
running `systemctl enable --now bluetooth.service`.

## Live network contract

The live user must be able to join a network before installing,
without any password prompt (HorneroOS/hornero#373). `hornero-live`
is passwordless and belongs to no administrative group, while
NetworkManager's stock policy requires `auth_admin_keep` for
`org.freedesktop.NetworkManager.settings.modify.system` — creating
the Wi-Fi connection profile therefore asked for a root/live
password that does not exist. The live image ships a polkit rule,
`airootfs/etc/polkit-1/rules.d/10-hornero-live-network.rules`
(pinned `0:0:644` in `profiledef.sh` so polkitd can read it), that
returns `polkit.Result.YES` only when the subject is `hornero-live`
in an active local session and only for the NetworkManager actions
needed to join Wi-Fi: `enable-disable-network`,
`enable-disable-wifi`, `wifi.scan`, `settings.modify.own`,
`settings.modify.system` and `network-control`. Hostname,
global-DNS, reload and checkpoint actions keep their stock
`auth_admin` policy, and the live sudoers grant stays limited to
`/usr/local/bin/hornero-installer-run ""` — joining a network grants
no general administration rights. The rule lives only in the archiso
airootfs; installed targets are built from `base.sqfs`, never
receive it, and keep NetworkManager's default authorization for the
named user Calamares creates. `tests/test_live_network_contract.py`
pins this contract. Joining a real password-protected Wi-Fi network
on a booted ISO is VM/physical proof and remains queued for the
Preview candidate validation pass; this change is source- and
test-verified only.

## Cancellation contract

Cancelling is available during the view steps (welcome through
summary), before any disk write happens. During the Install (exec)
step the Cancel button is disabled
(`disable-cancel-during-exec: true`, installer#93): the packages job
runs a single pacman transaction that does not stop when the UI
quits, so offering cancel there would promise an abort the installer
cannot honour — a preview32 QA run that "cancelled" at 56% ended
with the transaction completing and the target booting as an
installed system. If a deterministic mid-exec abort (transaction
termination, cleanup, incomplete-install invalidation) is ever
implemented and validated, this setting and the
`install-pairwise-negative/cancel-during-install` QA scenario must
be revisited together.

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

## Composable selection model (contract, not yet wired)

The Recommended path is unchanged: accept the defaults on every page
(Desktop/Hyprland, `linux`, GRUB, default capabilities). An Advanced
selection is the same pages with non-default picks — edition preset,
Studio specializations, capabilities, kernels (multi-select with one
primary), and a bootloader constrained by the firmware the installer
booted with. There is no separate wizard.

The canonical `HorneroOS/hornero` catalogue is the only source of
package lists. `scripts/installation_plan.py` validates a selection
against catalogue `kernels:` / `bootloaders:` / `capabilities:` maps
and emits a deterministic plan (`schemaVersion: 2`): packages in
primary-kernel-first order, services, ESP size, and warnings.
`scripts/render-installer-catalogue.py` renders
`packagechooser-kernel.conf`, `packagechooser-bootloader.conf`, and
`packagechooser-capabilities.conf` only when the pinned catalogue
ships those maps; otherwise the current single chooser is rendered
byte-identically and no list is invented in this repository.
Capability `bluetooth` reuses the existing `bluetooth.service` name;
its packages still come from the catalogue, never from here.

Never offer an unbootable combination:

| Bootloader | UEFI | BIOS |
| --- | --- | --- |
| GRUB | yes | yes |
| systemd-boot | yes | no — choose GRUB or reboot in UEFI mode |

ESP size is computed, not guessed:
`espRecommendedMiB = espBaseMiB + perKernelMiB * (kernels - 1)`
from the catalogue bootloader entry (GRUB single-kernel 512 MiB,
systemd-boot single 1024 MiB, dual-kernel systemd-boot 1280 MiB with
the catalogue values). LUKS stays `luks1` with the ESP unencrypted at
`/boot`, no `luksbootkeyfile`, and swap stays `none` (no `openswap`
hook) regardless of the selection.

`image/calamares/verify-install.py` already verifies a plan when one
is present at `/usr/lib/hornero/installation-plan.json` in the target
(or via `--plan`): every installed kernel has `vmlinuz-<kernel>` and
`initramfs-<kernel>.img`, GRUB has an entry per kernel or
systemd-boot has `loader.conf` plus an entry per kernel, and every
plan service whose unit was installed is enabled. Without a plan the
legacy GRUB/`linux` checks are unchanged.

Unresolved runtime pieces, with reasons: instanced packagechooser
pages, the `resolve-installation.py` Calamares job, `efiBootLoaderVar`
wiring, summary rendering of the plan, and systemd-boot/dual-kernel
boots are not wired until (1) the pinned catalogue ships the maps
above, (2) Calamares 3.4.3 GlobalStorage keys for instanced choosers
are verified, and (3) VM rows pass. Limine is not offered: no audited
maintained Calamares support exists. Checkbox multi-select needs a
QML/C++ viewmodule and is deferred to the Panda Foss installer, which
will consume the same catalogue, resolver, and plan JSON.

# Installation stages

The provisional installer uses Calamares. This map describes the modules in
`image/calamares/settings.conf` and the data each stage is expected to own. It
is not a claim that every recovery and preflight behavior is complete. The
published v0.2.0-preview22 ISO completed its VM installation matrix in
disposable UEFI and legacy-BIOS VMs (Desktop and Studio, encrypted and
unencrypted), and the installed systems unlocked their encrypted roots.
The R11 record behind it reached an authenticated desktop on BIOS; on
UEFI it reached the installed login screen, but authentication remains
unverified there. Installed package/profile parity and cleanup after a
simulated package-install failure
also remain unverified. See the [R11 evidence and exact artifact identity](r11-validation.md)
and [acceptance issue #11](https://github.com/HorneroOS/installer/issues/11).

## Calamares flow

1. **Disk and filesystems** — `partition`, `mount` review the disk layout,
   filesystems and encryption, then mount the target. No operation is
   preselected. Confirming a partition operation can erase data; the installer
   cannot roll back a disk operation.
2. **Base system** — `unpackfs` mounts the base SquashFS stored at the root of
   the ISO filesystem and unpacks it into the target root. Keeping this source
   outside Archiso's live SquashFS avoids an unsupported nested loop mount. If
   it fails, stop and retain Calamares logs; the target may be incomplete.
3. **Machine and locale** — `machineid`, `locale`, `keyboard`, `localecfg` and
   `fstab` write the machine identity, locale, input and mount configuration.
   A module failure means the system is not installed.
4. **Network and packages** — `shellprocess@resolver` binds the live session's
   working `/etc/resolv.conf` into the unpacked target immediately before
   `packages`, which runs pacman inside that target's chroot. The resolver file
   is not copied into the installed system. After the package attempt,
   emergency-capable `shellprocess@resolver-cleanup` unmounts the bind, then
   `shellprocess@cleanup` removes the temporary package repository configuration
   and restores Arch mirrors. Both cleanup jobs also run after package failure;
   VM acceptance verifies their behavior on success and failure.
5. **User and services** — `users` creates the named account, then
   `shellprocess@user-defaults` seeds Exo's package-provided terminal helper
   into each new home without replacing an existing user override.
   `services-systemd` enables edition services. Do not claim completion if
   any of these stages fails.
6. **Boot files** — `initcpiocfg` and `initcpio` configure filesystem/encryption
   hooks and build Arch initramfs images with `mkinitcpio`. The `encrypt` hook
   is placed after `block` and before `filesystems`, so an encrypted root is
   unlocked before the initramfs mounts it. `grubcfg` writes LUKS device and
   mapper-root parameters into GRUB's kernel command line before `bootloader`
   installs the firmware-specific GRUB targets. The EFI System Partition
   mounted at `/boot` stays unencrypted; no LUKS key is embedded in its
   initramfs. The Debian-only `initramfs` module is deliberately excluded.
   Firmware or mount failures can leave a target that does not boot.
7. **Unmount and finish** — `umount`, `finished` unmount the target and show
   completion. Report unmount errors accurately; reboot remains the user's
   choice and is never automatic.

The Welcome, Locale, Keyboard, Partition, Users, Edition and Summary pages are
shown before execution. The Welcome page checks RAM, power, root access and
screen size. It omits Calamares' built-in storage check because that check only
measures whole-device capacity; it does not measure free space or the selected
install layout. The profile still lacks an automated minimum-space check for
the selected target, so review the partition summary before confirming.

Calamares runs through a fixed root-owned launcher with detailed local logging.
When the installer exits, the launcher copies the session log to
`/var/log/hornero-installer/session.log`, readable by the live account. This
makes failed pre-installation stages diagnosable without widening the live
user's sudo permissions. The log stays local and is not uploaded automatically.

## Edition source of truth

Edition identity, package composition, compositor selection and maturity are
owned by [`HorneroOS/hornero`](https://github.com/HorneroOS/hornero), not by
this repository. `installer.lock.yaml` pins the catalogue revision plus the
catalogue and resolver hashes; `scripts/render-installer-catalogue.py` derives
the Calamares options from that resolver. The installer does not copy edition
inheritance, maturity or package lists into a second hand-maintained catalogue.

Only compositions whose catalogue maturity permits installation appear.
Experimental backends are clearly labeled and cannot become the default;
planned editions remain hidden until their product and install paths have
passed acceptance.

## State ownership

Target files and package state should be traceable to a Calamares stage and the
repository that owns the content (`config`, `hornero`, `shell`, or `greeter`).
The image artifact records the exact installer commit, product composition,
package-source provenance and checksum. The build refuses an installer
checkout with uncommitted files so the recorded revision identifies the actual
source. The selected edition also installs its generated
`hornero-profile-*` package, which owns `/usr/lib/hornero/system-profile.json`;
`horneroctl system info` reads that immutable composition record and reports
the active session compositor separately. The installer does not yet emit a
complete written-path manifest.
That manifest remains a release gate before the official installer claims
configuration-drift reconciliation.

## Installation acceptance

A built image is not accepted from a successful render or ISO build alone.
The R11 evidence records completed encrypted installations and successful
first boots through the login surface in both disposable firmware modes. BIOS
login reached the desktop; UEFI authentication remains unverified. Calamares
cleaned target mounts after successful installs, and a cancelled UEFI package
transaction returned to the live desktop with no temporary target or resolver
mounts. The following gates remain open:

- Verify the installed profile revision and package set against the pinned
  Hornero composition resolver in both installed VMs.
- Run a disposable simulated package-install failure and verify repository
  configuration, mirrors, and temporary mounts are cleaned up.
- Complete and validate the installer written-path manifest before claiming
  configuration-drift reconciliation.

The exact source revisions, ISO checksum, firmware evidence, and acceptance
status are maintained in the [R11 validation record](r11-validation.md).
Until the remaining gates pass—and Panda Foss completes the official
installer acceptance—the Calamares image remains provisional and is not
validated. Do not treat it as a supported or safe installer for a
personal computer or homelab server.
validated. Do not treat it as a supported or safe installer for a personal computer or homelab server.

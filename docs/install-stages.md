# Installation stages

The provisional installer uses Calamares. This map describes the modules in
`image/calamares/settings.conf` and the data each stage is expected to own. It
is not a claim that every recovery and preflight behavior is complete. The
live ISO has booted in disposable UEFI and legacy-BIOS VMs and Calamares
has been navigated through its partitioning page. Full installation and
installed-system acceptance remain in progress; see the
[VM evidence](../.github/evidence/provisional-installer-2026-10/README.md).

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
5. **User and services** — `users` creates the named account and
   `services-systemd` enables edition services. Do not claim completion if
   either stage fails.
6. **Boot files** — `initcpiocfg` and `initcpio` configure filesystem/encryption
   hooks and build Arch initramfs images with `mkinitcpio`.
   `shellprocess@grub-cryptodisk` sets `GRUB_ENABLE_CRYPTODISK=y` in the
   target's GRUB defaults before `bootloader` installs GRUB, so GRUB can read a
   LUKS root. The Debian-only `initramfs` module is deliberately excluded.
   Firmware or mount failures can leave a target that does not boot.
7. **Unmount and finish** — `umount`, `finished` unmount the target and show
   completion. Report unmount errors accurately; reboot remains the user's
   choice and is never automatic.

The Welcome, Locale, Keyboard, Partition, Users, Edition and Summary pages are
shown before execution. The Welcome page warns about network availability, but
the profile does not yet have a separate automated hardware, power or storage
preflight stage.

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
The image artifact records composition and package-source provenance. The
selected edition also installs its generated `hornero-profile-*` package, which
owns `/usr/lib/hornero/system-profile.json`; `horneroctl system info` reads that
immutable composition record and reports the active session compositor
separately. The installer does not yet emit a complete written-path manifest.
That manifest remains a release gate before the official installer claims
configuration-drift reconciliation.

## Installation acceptance

A built image is not accepted from a successful render or ISO build alone.
Acceptance requires completed installations in disposable UEFI and legacy-BIOS
VMs, successful boots of both installed systems, a package set matching the
pinned resolver, correct cleanup after success and failure, and a complete
written-path manifest. The current UEFI run reaches package installation but
fails at GRUB because the tested ISO predates the cryptodisk fix; BIOS
validation covers live boot and wizard navigation only. Until the full gates
pass, the image profile remains provisional and must not be treated as a safe
way to install a personal computer or homelab server.

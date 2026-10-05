# Installation stages

The provisional installer uses Calamares. This map describes the modules in
`image/calamares/settings.conf` and the data each stage is expected to own. It
is not a claim that every recovery and preflight behavior is complete: this
profile has not yet passed a full ISO and VM installation run.

## Calamares flow

1. **Disk and filesystems** — `partition`, `mount` review the disk layout,
   filesystems and encryption, then mount the target. No operation is
   preselected. Confirming a partition operation can erase data; the installer
   cannot roll back a disk operation.
2. **Base system** — `unpackfs` unpacks the small Arch base into the target
   root. If it fails, stop and retain Calamares logs; the target may be
   incomplete.
3. **Machine and locale** — `machineid`, `locale`, `keyboard`, `localecfg` and
   `fstab` write the machine identity, locale, input and mount configuration.
   A module failure means the system is not installed.
4. **Packages and repository cleanup** — `packages` installs the selected
   resolver composition, then `shellprocess@cleanup` removes the temporary
   package repository configuration and restores Arch mirrors. A package
   failure can leave a partial target; VM acceptance must verify cleanup and
   recovery behavior on both success and failure.
5. **User and services** — `users` creates the named account and
   `services-systemd` enables edition services. Do not claim completion if
   either stage fails.
6. **Boot files** — `initcpiocfg`, `initcpio`, `initramfs` and `bootloader`
   configure filesystem/encryption hooks, build initramfs and install GRUB.
   Firmware or mount failures can leave a target that does not boot.
7. **Unmount and finish** — `umount`, `finished` unmount the target and show
   completion. Report unmount errors accurately; reboot remains the user's
   choice and is never automatic.

The Welcome, Locale, Keyboard, Partition, Users, Edition and Summary pages are
shown before execution. The Welcome page warns about network availability, but
the profile does not yet have a separate automated hardware, power or storage
preflight stage.

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
The profile records composition and package-source provenance, but does not yet
emit a complete written-path manifest. That manifest remains a release gate
before the official installer claims configuration-drift reconciliation.

## Installation acceptance

A built image is not accepted from a successful render or ISO build alone.
Acceptance requires clean runs in disposable UEFI and legacy-BIOS VMs, a
successful boot of the installed system, a package set matching the pinned
resolver, correct cleanup after success and failure, and a complete written-
path manifest. Until then, the image profile remains provisional and must not
be treated as a safe way to install a personal computer or homelab server.

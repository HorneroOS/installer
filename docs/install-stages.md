# Installation stages

The provisional installer uses Calamares. This map describes the modules in
`image/calamares/settings.conf` and the data each stage is expected to own. It
is not a claim that every recovery and preflight behavior is complete: this
profile has not yet passed a full ISO and VM installation run.

## Calamares flow

| # | Calamares modules | Purpose | Target state written | Failure boundary |
| --- | --- | --- | --- | --- |
| 1 | `partition`, `mount` | Review a disk layout, filesystems and encryption; mount the target. No operation is preselected. | Partition table, filesystems and temporary mounts. | Partitioning can erase data once confirmed; the installer cannot roll back a disk operation. |
| 2 | `unpackfs` | Unpack the small Arch base system. | Target root filesystem. | Stop and retain Calamares logs; the target may be incomplete. |
| 3 | `machineid`, `locale`, `keyboard`, `localecfg`, `fstab` | Create machine identity and write locale, input and mount configuration. | Target `/etc`, machine-id and fstab. | Stop and report the failed module; do not call the system installed. |
| 4 | `packages`, `shellprocess@cleanup` | Install the selected resolver composition, then remove the temporary package-repository configuration. | Target packages and restored Arch mirror configuration. | A package failure can leave a partial target; installation acceptance must verify cleanup and recovery behavior. |
| 5 | `users`, `services-systemd` | Create the named account and enable edition services. | Target home and account databases; systemd enablement links. | Do not claim completion if account or service setup fails. |
| 6 | `initcpiocfg`, `initcpio`, `initramfs`, `bootloader` | Add filesystem/encryption hooks, build initramfs and install GRUB. | Target initramfs, boot files and EFI variables where applicable. | Keep logs and explain firmware or mount requirements; the target may not boot. |
| 7 | `umount`, `finished` | Unmount the target and show completion. Reboot remains the user's choice. | No new product configuration. | Report unmount errors accurately; never reboot automatically. |

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

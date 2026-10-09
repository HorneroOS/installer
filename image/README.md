# Provisional installation image

This directory defines HorneroOS's provisional Calamares installation medium.
It is a development build profile, not the future official installer. The
current source has completed an encrypted UEFI installation but first-boot
testing exposed a missing initramfs LUKS-unlock configuration. The fix is under
VM validation. A complete install-and-first-boot path has not passed
acceptance. The profile offers only compositions that the HorneroOS edition
catalogue marks installable. It targets x86_64 Desktop with Hyprland (default)
and Niri (Experimental).

## Source of truth

- Installed target packages and maturity come from the pinned
  `HorneroOS/hornero` resolver.
- Arch package availability uses the dated snapshot in `installer.lock.yaml`.
- Hornero packages come from AUR PKGBUILDs pinned by commit in that lock.
- The temporary local package repository is mounted only during installation
  and removed from the installed `pacman.conf` before the target is unmounted.
- `packages.x86_64` describes the live installer environment only. It is not a
  second target edition manifest.

## Build safety

Build only in a disposable Arch VM with at least 40 GiB free on the work
filesystem and 12 GiB free on the output filesystem. If both paths share one
filesystem, reserve at least 52 GiB total. The script
refuses bare metal, refuses reused output paths, caps build parallelism at two,
limits SquashFS compression to two workers, and does not clean or overwrite
previous work. ISO hashing uses bounded memory. Use a new empty work directory
and output directory for every run:

```sh
VJOBS=2 scripts/build-iso.sh \
  --work /mnt/build/hornero-work-2026-10-05 \
  --output /mnt/build/hornero-output-2026-10-05
```

The VM needs Archiso, `arch-install-scripts`, `squashfs-tools`, `pacman-contrib`,
base-devel, Git, Python with PyYAML, and the Calamares build dependencies. The
builder uses Arch Linux Archive repositories at the snapshot date in the lock.
It refuses a dirty installer checkout and writes the image checksum plus a JSON
manifest with the exact installer commit, product revision, package recipes and
composition provenance next to the ISO. The artifact is unsigned; release
signing is a separate gate.

Do not test erase, replacement, encryption or bootloader flows on a personal
disk. All graphical acceptance must use disposable UEFI and legacy-BIOS VMs
with blank virtual disks. See [the installation test matrix](../docs/calamares-provisional.md).

## Intended live environment

The profile configures Xfce for a familiar, low-complexity network setup
surface and launches Calamares automatically after login. SDDM autologin is
limited to the intended live session. Its sudo rule permits only the fixed
`/usr/local/bin/hornero-installer-run` wrapper, which launches
`/usr/bin/calamares` and copies the installer log; it does not grant the live
user a general root shell. The
installed target gets its own SDDM login and Hornero greeter from the Desktop
composition. Live boot and wizard navigation are evidenced; installation and
first-boot behavior still need acceptance.

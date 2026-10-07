# Provisional Calamares ISO VM evidence

The provisional ISO was built from the pinned inputs in `installer.lock.yaml`
inside an isolated Arch Linux QEMU build VM. The build completed and generated
an ISO checksum and provenance manifest. The ISO SHA-256 was independently
checked on the host:

```text
fac3b6f0ec03eee02b57850263f5c38702888e661caec930066cde0ac3bf765c
```

The same ISO was booted in separate disposable BIOS and UEFI QEMU VMs with
blank 32 GiB QCOW2 target disks. Calamares launched in both sessions and was
navigated through Welcome, Location, Keyboard and Partitioning. The partition
page reported BIOS or EFI respectively and showed the expected empty `/dev/vda`
target. The BIOS run stopped there. A later UEFI run selected the disposable
target, created the planned layout, and reached package installation, which
failed because the guest could not resolve `archive.archlinux.org`.

- `uefi-live.png`: Calamares Welcome page in the UEFI live session.
- `uefi-partition.png`: UEFI partition page, firmware label and blank target.
- `bios-partition.png`: BIOS partition page, firmware label and blank target.

These captures establish live-media boot and early wizard behavior only. They
do not show the later UEFI package-manager failure and do not establish a
successful installation, first boot, installed-package parity, cleanup after
the failed transaction, or suitability for personal hardware. The target was a
disposable virtual disk. The image remains unsigned and provisional; do not use
it as the sole installation path for a personal computer or homelab server.

## Follow-up network diagnosis

On 2026-10-06, the same live ISO was booted again in a disposable UEFI VM. The
guest received an IPv4 address and default route. DNS lookups timed out with
QEMU user networking (including an explicit guest resolver), while the host
resolved the same Arch mirror. Switching only this disposable VM to QEMU's
unprivileged `passt` network backend allowed the guest to resolve
`archive.archlinux.org` to `49.12.124.107`. A subsequent UEFI install with
4 GiB RAM and 2 vCPUs completed package installation on a disposable 40 GiB
encrypted target, then failed in the GRUB stage. The recorded error says GRUB
refuses to install to the encrypted root without
`GRUB_ENABLE_CRYPTODISK=y` in `/etc/default/grub`. The exact failure is captured
in
[`grub-cryptodisk-20261006/uefi-grub-cryptodisk-failure.png`](grub-cryptodisk-20261006/uefi-grub-cryptodisk-failure.png).

The installer source now adds an idempotent Calamares step before the
bootloader to enable GRUB cryptodisk in the target configuration. That change
and the `horneroctl-bin` preview15 source pin are not present in the tested
ISO. A rebuilt ISO, successful UEFI first boot, a legacy-BIOS install, package
parity, and cleanup checks remain acceptance gates. The installer source also
checks DNS before either launcher path opens Calamares, but the existing ISO
predates that guard.

## GPT firmware-layout diagnosis

On 2026-10-06, a disposable UEFI install using the current preview completed
package installation on an encrypted Btrfs target. Its session log records
`GRUB_ENABLE_CRYPTODISK=y` and a successful `x86_64-efi` GRUB install. The
subsequent `i386-pc` install failed because the GPT erase layout had no BIOS
boot partition. The source correction requests Calamares' GPT layout containing
both an EFI System Partition and a BIOS boot partition, and sets
`installHybridGRUB: false` so GRUB installs only for the firmware that booted
the live ISO. Static checks pass for the correction; a rebuilt image and both
firmware-mode installations remain required before this is considered fixed.
The failed target disk and the local installer session log are disposable test
artifacts; no host disk or host bootloader was touched.

The first installed-disk boot after the firmware-layout correction exposed a
second failure: GRUB enumerated the kernel under the encrypted Btrfs root, then
reported a premature end of file when asked to load it. The Btrfs mount options
enable Zstandard compression, while GRUB's documented Btrfs compression support
does not include Zstandard. The source now mounts the already-present EFI
System Partition at `/boot`, so both the kernel and initramfs live on FAT and
GRUB can read them without entering the compressed encrypted root. This change
has not yet been exercised by a rebuilt ISO.

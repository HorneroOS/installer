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

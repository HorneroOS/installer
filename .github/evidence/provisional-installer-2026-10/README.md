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
target. No partition operation was selected and no installation was started.

- `uefi-live.png`: Calamares Welcome page in the UEFI live session.
- `uefi-partition.png`: UEFI partition page, firmware label and blank target.
- `bios-partition.png`: BIOS partition page, firmware label and blank target.

These captures establish live-media boot and early wizard behavior only. They
do not establish successful partitioning, installation, first boot, installed
package parity, post-failure repository cleanup or suitability for personal
hardware. The image remains unsigned and provisional; do not use it as the sole
installation path for a personal computer or homelab server.

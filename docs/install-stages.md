# Staged install contract

No installer implementation is chosen yet (archinstall, Calamares,
or custom — see `README.md`). This page constrains **any** of them:
whatever installs HorneroOS must decompose into the stages below,
and every stage must declare its contract row before it ships.

## The stages

| # | Stage | Job | Writes | Failure means |
|---|-------|-----|--------|---------------|
| 0 | Preflight | hardware detect, disk map, network check | nothing (reads only) | abort before any write, report unmet need |
| 1 | Partition | layout agree, format | partition table, filesystems | abort, disk untouched or re-runnable |
| 2 | Base | pacstrap profiles (`hornero/profiles`) | mounted root | re-run stage 2 only |
| 3 | Boot | bootloader, kernel hooks | ESP, boot entries | system unbootable: must be retried, never skipped |
| 4 | Identity | user, locale, timezone, hostname | `/etc`, home skeleton | re-run stage 4 only |
| 5 | Desktop | `[hornero]`/AUR sets, `hornero-desktop` | packages, `/usr/share/hornero`, `/etc/xdg` | re-run stage 5 only |
| 6 | Seal | snapshots, `doctor`, first-boot welcome | snapshot, state files | report only: system is complete, verification pending |

## Per-file rule

Every file the installer writes must be traceable to one stage and
one owner repo (`config`, `hornero`, `shell`, `greeter`). The
installer keeps a manifest of written paths; `horneroctl doctor`
reconciles drift afterwards. A file with no owning stage is a bug in
the installer, not the user's problem.

## Delivery gate (issue #2)

An installer build passes only when a clean run in a VM reaches
stage 6 with `doctor` green and the manifest complete. No partial
success: stages 0–5 either all complete or the run is a failure
with the disk left re-runnable.

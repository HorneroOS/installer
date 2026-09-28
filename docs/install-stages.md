# Staged install contract

No installer implementation is chosen yet (archinstall, Calamares,
or custom — see `README.md`). This page constrains **any** of them:
whatever installs HorneroOS must decompose into the stages below,
and every stage must declare its contract row before it ships.

## The stages

| # | Stage | Job | Writes | On failure |
|---|---|---|---|---|
| 0 | Preflight | detect hw, map disks | nothing (reads) | abort, report need |
| 1 | Partition | agree layout, format | parttable, fs | abort, re-runnable |
| 2 | Base | pacstrap profiles | mounted root | re-run stage 2 |
| 3 | Boot | bootloader, hooks | ESP, entries | retry, never skip |
| 4 | Identity | user, locale, time | `/etc`, skeleton | re-run stage 4 |
| 5 | Desktop | package sets | `/usr`, `/etc/xdg` | re-run stage 5 |
| 6 | Seal | snapshot, doctor | snapshot, state | report only |

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

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
| 2 | Base | install base packages | mounted root | re-run stage 2 |
| 3 | Boot | bootloader, hooks | ESP, entries | retry, never skip |
| 4 | Identity | user, locale, time | `/etc`, skeleton | re-run stage 4 |
| 5 | Edition | install edition packages | `/usr`, `/etc/xdg` | re-run stage 5 |
| 6 | Seal | snapshot, doctor | snapshot, state | report only |

## Edition source of truth

Edition identity, package composition, compositor selection and maturity are
owned by [`HorneroOS/hornero`](https://github.com/HorneroOS/hornero), not by
this repository. The installer must pin a catalogue revision and consume the
resolver's machine-readable output. It must not copy package names, inheritance
rules or maturity labels into installer-specific manifests.

The installer may only offer a composition whose maturity permits installation.
`planned` is not selectable; `experimental` must be clearly marked and require
an intentional choice; `preview` and `supported` must retain their published
status. These rules keep product truth and install UX aligned while editions
are being validated.

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

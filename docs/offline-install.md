# Offline installation

Offline installation is opt-in at ISO build time and is never
silently enabled at install time.

## Building an offline-capable ISO

```sh
VJOBS=2 scripts/build-iso.sh --offline \
  --work /mnt/build/hornero-work-YYYY-MM-DD \
  --output /mnt/build/hornero-output-YYYY-MM-DD
```

Without `--offline` the image is exactly the online-only preview
build. With it, `scripts/build-offline-repo.sh` downloads the full
dependency closure of every package a user can select — all edition
compositions in `compositions.json` plus every netinstall leaf —
from the Arch snapshot pinned in `installer.lock.yaml`, builds a
single `hornero-offline` pacman repository with `repo-add`, and
writes `offline-manifest.json` (per-package size + sha256). The
repository lands in
`airootfs/usr/share/hornero-installer/offline-repo/` and its package
count and byte total are recorded in the ISO `.manifest.json`.
Hornero's own packages are not duplicated: they already ship in the
local `hornero-installer` file:// repository.

Measured on the pinned snapshot `2026/10/10` with
`pacman -Sp --print-format '%s %n'` over the 88 root packages
(compositions + netinstall, minus Hornero-local): **1080 packages in
the closure, 2,09 GB download (1,94 GiB)**. Package files are already
zstd-compressed, so ISO growth is expected to be close to that figure
plus the pacman database; the exact ISO delta is only known after a
real `--offline` ISO build (not run in light mode).

## Install-time flow

1. `hornero-installer-start` probes the network as before. Only when
   there is no usable network **and** the on-media repository
   verifies complete (database + manifest + every package's sha256)
   does it offer, before any partitioning: *Continue offline*. The
   user must accept explicitly; declining keeps today's honest
   "connect to the internet" block.
2. On acceptance the launcher drops a consent flag and
   `hornero-installer-run` (root) re-verifies the repository before
   writing the root-owned 0600 marker
   `/run/hornero-installer/offline-mode` and the system selection
   `{"offline": true}`. A failed verification refuses to start.
3. Calamares' first exec step (`shellprocess@preflight`) re-checks
   the repository against the manifest and aborts **before
   partitioning** if anything is missing or truncated.
4. After `system-plan` and before `packages`,
   `shellprocess@offline-repo` rewrites the target `pacman.conf`:
   the Arch sections are dropped and a single
   `[hornero-offline] Server = file:///usr/share/hornero-installer/offline-repo`
   remains, next to the existing local `hornero-installer` include.
   Offline selections keep the existing restriction to the default
   `linux` kernel (`apply-system-plan.py`).
5. `cleanup-package-source.py` (including its emergency path) removes
   the offline section again and restores `[core]`/`[extra]`/
   `[multilib]` with the normal mirrorlist, so the installed system
   never points at the live medium after reboot.

With no marker, every step above is a no-op and the online install
is byte-identical to the preview build.

## Gate not yet proven

No offline ISO has been built or installed in a VM in light mode.
Merging this mechanism does **not** claim offline installs work end
to end; the VM gate is: build with `--offline`, boot with no network,
accept offline mode, complete an install (default composition and
one netinstall leaf), reboot into the installed system, and confirm
its `pacman.conf` uses normal mirrors. See installer#113.

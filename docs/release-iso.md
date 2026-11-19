# Building and releasing a Signal ISO

Audience: the maintainer who holds the signing key and the download storage
token. Nothing here can run in CI: the installer repository has no signing or
upload secret, the ISO build needs a disposable Arch VM, and Calamares needs a
guest with at least 4 GiB of RAM for its install gate (`welcome.conf`
`requiredRam`).

## Why the shipped preview32 ISO is pre-Signal (installer#101)

The ISO content is whatever `installer.lock.yaml` pins, not what is on `main`
of the other repositories. The shipped preview32 ISO was built while the lock
still pinned `hornero-shell 1.2.60`, `hornero-config 0.3.18`,
`hornero-greeter 1.0.4`, and `horneroctl-bin 0.2.0_preview40`.
`scripts/build-iso.sh` therefore runs `scripts/check-signal-lock.py` and refuses
to build from a pre-Signal lock. The lock now pins the published Signal
releases (`hornero-shell 1.3.3-1`, `hornero-config 0.4.3-1`,
`hornero-greeter 1.1.0-1`, `horneroctl-bin 0.2.0_preview49-1`) and the gate
passes; what remains is the maintainer build, VM verification, signing and
upload below. Set `HORNEROS_ALLOW_PRE_SIGNAL_LOCK=1` only for a throwaway
test image, never for a release.

What is already on `main` and needs no further change for a Signal live
session: Calamares branding (`image/calamares/branding/hornero`, Signal Night
`stylesheet.qss`, the 600 px banner), `ttf-ibm-plex` in
`image/archiso/packages.x86_64`, and a live-session setup that never pins a
theme, wallpaper or layout (the live user gets the packaged factory defaults,
`tests/test_signal_branding.py`).

## 1. Prerequisites (outside this repository)

1. The AUR packages are published from their tags (see the release plan in the
   mission notes): `hornero-config`, `hornero-shell`, `hornero-greeter` by
   `pkg/<name>-vX.Y.Z` tags, `horneroctl-bin` by `horneroctl-v0.2.0-previewN`.
2. The floors in `scripts/check-signal-lock.py` (`SIGNAL_FLOOR`) match the
   versions you actually published. Edit the floors first if you chose other
   numbers.

## 2. Refresh `installer.lock.yaml`

For each pinned AUR package set `version` to the published `pkgver-pkgrel`
and `revision` to the commit of the AUR git repository that published it
(`git ls-remote https://aur.archlinux.org/<pkg>.git HEAD`). Then:

- Keep `python-materialyoucolor` and `ttf-rubik-vf` out of the lock (already
  removed; the check script fails if either returns).
- Set `product.revision` to the HorneroOS/hornero commit of the release record
  and refresh `product.catalogueSha256` and `product.resolverSha256` from that
  commit (`sha256sum editions/catalogue.yaml` and the resolver file named in
  the lock history; `scripts/check-installer.py` verifies them).
- Move `arch.snapshot` forward only if you also want newer Arch packages;
  keep `profileMedia` pointing at a website revision whose screenshot is a
  Signal capture, or replace the packaged `desktop-hyprland.jpg` and its two
  hashes.
- Re-render the package lists: `python3 scripts/render-installer-catalogue.py
  --cache-dir "$HOME/.cache/hornero-installer" --output <dir>/packagechooser.conf
  --profile-packages-dir <dir>/profile-packages`, then
  `python3 scripts/check-installer.py` and `python3 -m pytest tests`.
  Commit `installer.lock.yaml` and any regenerated checked-in module config in
  one PR and merge it with CI green.

`python3 scripts/check-signal-lock.py` must print `signal-lock: ok`.

## 3. Build (disposable Arch VM, never the host)

```sh
VJOBS=2 scripts/build-iso.sh \
  --work /mnt/build/hornero-work-YYYY-MM-DD \
  --output /mnt/build/hornero-output-YYYY-MM-DD
```

Requirements are enforced by the script: root inside a VM, a clean installer
checkout, 40 GiB free for work and 12 GiB for output (52 GiB if shared), new
empty paths, and the tools listed in `image/README.md`. The output directory
receives `horneroos-<snapshot>-provisional-x86_64.iso`, its `.sha256` and a
`.manifest.json` with the exact installer, product and AUR revisions.

## 4. Verify before signing

Do not sign an image that has not been booted. In a disposable VM with a
4 GiB guest and blank virtual disks (UEFI and legacy BIOS):

1. Boot menu appears (BIOS syslinux menu; UEFI uses systemd-boot).
2. The live session shows the Signal shell (Cockpit, amber on graphite): no
   literal icon words such as `waving_hand`, no clipped workspace indicator.
3. The Welcome app renders Hornero Glyphs. Check `fc-list | grep -i plex`.
4. Calamares uses the Signal chrome on every page and the `PREVIEW` chip is not
   clipped; error blocks (for example the RAM gate) are readable.
5. Run an install on each firmware path and reach the installed greeter and
   desktop (installer#11 acceptance).

Keep the captures: commit the curated ones under `HorneroOS/qa`
`docs/evidence/` and link them from the release record.

## 5. Sign and publish (maintainer only)

1. Verify `sha256sum -c <iso>.sha256`.
2. Sign with the HorneroOS release GPG key held by the maintainer
   (detached signature, for example `gpg --armor --detach-sign <iso>`), and
   verify it with `gpg --verify` against the published key fingerprint.
3. Upload the ISO, `.sha256`, signature and manifest to the download storage
   the website links to, using the maintainer's existing out-of-band procedure
   (the preview ISOs used Vercel Blob). This repository documents no commands
   for it because none are automated here.
4. In HorneroOS/hornero add the release record (new manifest, release yaml and
   checklist, ledger row; never edit an old one).
5. In HorneroOS/website update the current-ISO constant used by
   `scripts/check-release-truth.mjs`, the install page and `llms.txt`, then run
   the website data bump after the AUR packages are public.

Only after step 5 is the Signal ISO available. Until then the README must keep
saying that the published ISO predates Signal.

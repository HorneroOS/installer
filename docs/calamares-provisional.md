# Provisional Calamares installer

HorneroOS uses Calamares as its first graphical installer implementation.
This is a provisional installer: the official installer experience may replace
it after the editions, storage policies and recovery workflows mature. The
Calamares framework and its configuration are packaged separately, following
Calamares deployment guidance.

The current image profile is a development preview; no certified ISO is
available yet. It is configured to boot a small Xfce live session on UEFI or
legacy BIOS, offer a graphical network tray and launch Calamares. Its edition
choices come from the pinned
[`HorneroOS/hornero` edition catalogue](https://github.com/HorneroOS/hornero/blob/main/editions/catalogue.yaml)
and are rendered by `scripts/render-installer-catalogue.py`. The installer does
not maintain its own package lists. Each choice also installs a generated
`hornero-profile-*` metadata package containing the resolved edition,
compositor, maturity, package-set identifiers and pinned Hornero source
revision at `/usr/lib/hornero/system-profile.json`. The metadata package is
rendered from the same resolver result as the package chooser; it carries no
independent package list. `horneroctl system info` reads this record and
separates the installed compositor choice from the compositor active in the
current session. Installations made outside this installer can report their
active compositor without claiming an edition that was never recorded.
Only compositions whose product maturity
allows installation appear in the choice page; experimental compositor choices
are labelled as such. Planned editions stay hidden until their system and
installer path have been validated.
The Hyprland option includes a certified Hornero desktop capture. Niri uses an
explicit experimental-status card instead of a fabricated compositor
screenshot; the media lock records the capture's website commit and hashes.

## Before installing

- Back up anything on the selected disk. Choosing an erase layout destroys its
  existing partitions and data.
- Connect to the Internet before starting installation. The provisional image
  is designed to install the pinned composition from Arch repositories and
  the local installer package repository.
- The partition screen starts without a selected operation. Review the disk,
  partition map, encryption setting and final summary before confirming.
- Automated encryption uses the Calamares LUKS support and mkinitcpio's
  matching unlock hook. Keep the unlock phrase safe; HorneroOS cannot recover
  it. The unencrypted EFI system partition remains visible to the machine.
- The installer creates a named user with a password and `wheel`-based sudo.
  It does not create a shared default password, enable automatic login, or set
  a root password.
- Desktop/Hyprland is the default install choice. Niri is explicitly marked
  Experimental while its product maturity remains experimental.
- Server, Agents and Studio do not appear while their catalogue entries remain
  Planned. A graphical live installer can eventually install a headless Server
  target without putting the live desktop on that target.
- The image build assembles a temporary local package repository from
  commit-pinned AUR recipes. The installer bind-mounts that repository into the
  target only during package installation. An emergency-capable cleanup step
  removes repository configuration after package installation succeeds or
  fails; VM acceptance still has to verify both paths.

## Current limits

The config and build scripts have not yet completed a full image build or
destructive-disk acceptance in disposable UEFI and legacy-BIOS VMs. The host
development machine is deliberately not used for ISO builds or disk tests.
Do not use this preview as the sole copy of important data or as an unattended
production deployment. Release signing and artifact publication remain an
explicit release gate. The live-image profile is owned here until a dedicated
image repository exists. See the [image build guide](../image/README.md).

Follow the [installation stages](install-stages.md),
[known installer issues](https://github.com/HorneroOS/installer/issues), and
[Calamares deployment documentation](https://calamares.codeberg.page/docs/deploy-configuration/).

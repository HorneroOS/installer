#!/usr/bin/env python3
"""Check the provisional Calamares flow without touching a block device."""

from __future__ import annotations

import json
import argparse
import hashlib
import re
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CALAMARES = ROOT / "image" / "calamares"


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    output = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in output:
            raise ValueError(f"duplicate YAML key: {key}")
        output[key] = loader.construct_object(value_node, deep=deep)
    return output


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path: Path) -> dict:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return value


def main() -> int:
    """Validate installer module ordering, config schemas, and safe target edits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=CALAMARES, help="Calamares config directory")
    parser.add_argument("--schema-root", type=Path, help="Calamares source src/modules directory")
    args = parser.parse_args()
    config_root = args.config_root.resolve()
    settings = load_yaml(config_root / "settings.conf")
    phases = settings.get("sequence", [])
    assert [next(iter(phase)) for phase in phases] == ["show", "exec", "show"]
    assert phases[0]["show"][-2:] == ["packagechooser", "summary"]
    exec_modules = phases[1]["exec"]
    assert exec_modules.index("unpackfs") < exec_modules.index("shellprocess@resolver")
    assert exec_modules.index("shellprocess@resolver") < exec_modules.index("packages")
    assert exec_modules.index("packages") < exec_modules.index("shellprocess@resolver-cleanup")
    assert exec_modules.index("shellprocess@resolver-cleanup") < exec_modules.index("shellprocess@cleanup")
    assert exec_modules.index("users") < exec_modules.index("shellprocess@user-defaults")
    # Recovery factory config needs fstab + packages done, and must
    # precede services-systemd so snapper timers enable against a
    # written config (hornero#179).
    assert exec_modules.index("packages") < exec_modules.index("shellprocess@recovery")
    assert exec_modules.index("shellprocess@recovery") < exec_modules.index("services-systemd")
    assert exec_modules.index("initcpiocfg") < exec_modules.index("initcpio")
    assert exec_modules.index("initcpio") < exec_modules.index("grubcfg")
    assert exec_modules.index("grubcfg") < exec_modules.index("bootloader")
    assert "initcpio" in exec_modules
    assert "initramfs" not in exec_modules, (
        "initramfs is Debian-specific; Arch targets regenerate images with initcpio"
    )
    assert phases[1]["exec"][-1] == "umount"
    assert settings["prompt-install"] is True
    assert settings["dont-chroot"] is False

    # Every `module@instance` used in the sequence must be declared in
    # `instances:` with an existing config file. Without a declaration
    # Calamares silently falls back to its bundled example config (the
    # `/usr/local/bin/slowloris` placeholder), which fails the install
    # mid-exec; this is how the recovery step broke the candidate ISO.
    instances = {
        (entry["module"], entry["id"]): entry["config"]
        for entry in settings.get("instances", [])
    }
    sequenced = [
        step
        for phase in phases
        for step in next(iter(phase.values()))
    ]
    for step in sequenced:
        if "@" not in step:
            continue
        module, instance = step.split("@", 1)
        assert (module, instance) in instances, (
            f"sequence step {step!r} has no matching instances: entry"
        )
        config_name = instances[(module, instance)]
        assert (config_root / "modules" / config_name).is_file(), (
            f"instances: config {config_name!r} for {step!r} does not exist"
        )

    modules = config_root / "modules"
    configs = sorted(modules.glob("*.conf"))
    assert len(configs) >= 10, "expected the core target-system modules to be configured"
    parsed = {path.stem: load_yaml(path) for path in configs}
    assert parsed["shellprocess-resolver"]["dontChroot"] is True
    assert parsed["shellprocess-user-defaults"]["dontChroot"] is True
    assert "/usr/bin/mount --bind /etc/resolv.conf ${ROOT}/etc/resolv.conf" in parsed[
        "shellprocess-resolver"
    ]["script"]
    assert "/usr/bin/mount --bind /etc/hosts ${ROOT}/etc/hosts" in parsed[
        "shellprocess-resolver"
    ]["script"]
    assert parsed["shellprocess-resolver-cleanup"]["dontChroot"] is True
    assert parsed["shellprocess-resolver-cleanup"]["emergency"] is True
    assert "-/usr/bin/umount ${ROOT}/etc/hosts" in parsed[
        "shellprocess-resolver-cleanup"
    ]["script"]
    assert "-/usr/bin/umount ${ROOT}/etc/resolv.conf" in parsed[
        "shellprocess-resolver-cleanup"
    ]["script"]
    initcpiocfg = parsed["initcpiocfg"]
    assert initcpiocfg["hooks"]["remove"] == ["filesystems", "fsck"]
    assert initcpiocfg["hooks"]["append"] == ["encrypt", "filesystems", "fsck"]
    assert "luksbootkeyfile" not in exec_modules, (
        "the EFI System Partition mounted at /boot is unencrypted; do not put a LUKS keyfile in initramfs"
    )
    assert parsed["grubcfg"]["kernel_params"] == ["quiet"]
    if args.schema_root:
        import jsonschema

        module_root = args.schema_root.resolve()
        for name, configuration in parsed.items():
            module_name = "shellprocess" if name.startswith("shellprocess-") else name
            schema_path = module_root / module_name / f"{module_name}.schema.yaml"
            if not schema_path.is_file():
                if module_name != "packagechooser":
                    raise FileNotFoundError(f"Calamares schema missing for {module_name}: {schema_path}")
                continue
            schema = load_yaml(schema_path)
            schema_configuration = configuration
            if (
                module_name == "partition"
                and "createHybridBootloaderLayout" in configuration
                and "createHybridBootloaderLayout" not in schema.get("properties", {})
            ):
                # Calamares 3.4.3 implements and documents this setting but
                # omits it from partition.schema.yaml. Validate its value here
                # and validate the remaining settings against the pinned schema.
                assert isinstance(configuration["createHybridBootloaderLayout"], bool)
                schema_configuration = dict(configuration)
                del schema_configuration["createHybridBootloaderLayout"]
            jsonschema.Draft7Validator(schema).validate(schema_configuration)
    assert parsed["welcome"]["geoip"]["style"] == "none"
    assert "storage" not in parsed["welcome"]["requirements"]["check"], (
        "Calamares Welcome storage checks whole-device capacity, not target free space"
    )
    assert parsed["locale"]["geoip"]["style"] == "none"
    assert parsed["locale"]["region"] == "America"
    assert parsed["locale"]["zone"] == "Argentina/Buenos_Aires"
    assert "url" not in parsed["welcome"] or not str(parsed["welcome"].get("url", "")).startswith("http://")
    assert parsed["users"]["setRootPassword"] is False
    assert parsed["users"]["displayAutologin"] is False
    assert parsed["users"]["autologinGroup"] == ""
    assert parsed["users"]["user"]["home_permissions"] == "750"
    assert parsed["users"]["passwordRequirements"]["minLength"] >= 12
    assert parsed["partition"]["initialPartitioningChoice"] == "none"
    assert parsed["partition"]["createHybridBootloaderLayout"] is True
    assert parsed["partition"]["enableLuksAutomatedPartitioning"] is True
    # Composable flow: without rendered kernel/bootloader choosers the
    # pinned catalogue has no such maps and the current GRUB default is
    # the only offered bootloader. Once the renderer emits a bootloader
    # chooser, bootloader.conf must delegate via efiBootLoaderVar.
    if (modules / "packagechooser-bootloader.conf").is_file():
        assert parsed["bootloader"].get("efiBootLoaderVar") == "packagechooser_bootloader", (
            "bootloader chooser rendered but bootloader.conf does not delegate to it"
        )
        bootloader_chooser = load_yaml(modules / "packagechooser-bootloader.conf")
        assert bootloader_chooser["default"] in {
            item["id"] for item in bootloader_chooser["items"]
        }
        kernel_chooser = load_yaml(modules / "packagechooser-kernel.conf")
        assert kernel_chooser["items"], "kernel chooser must offer catalogue kernels"
        assert all(item.get("packages") for item in kernel_chooser["items"])
    else:
        assert parsed["bootloader"]["efiBootLoader"] == "grub"
    assert parsed["bootloader"]["installHybridGRUB"] is False
    # LUKS/openswap invariants must survive any composable selection.
    assert parsed["partition"]["luksGeneration"] == "luks1"
    assert parsed["partition"]["userSwapChoices"] == ["none"]
    assert (ROOT / "scripts/installation_plan.py").is_file(), (
        "composable installation-plan contract module missing"
    )
    assert (CALAMARES / "resolve-installation.py").is_file(), (
        "composable resolve-installation contract missing"
    )
    assert parsed["packages"]["backend"] == "pacman"
    assert parsed["packages"]["update_system"] is False
    assert parsed["packages"]["pacman"]["num_retries"] >= 8
    assert parsed["packages"]["pacman"]["disable_download_timeout"] is True
    assert parsed["shellprocess-cleanup"]["emergency"] is True

    chooser = parsed["packagechooser"]
    compositions = json.loads((modules / "compositions.json").read_text(encoding="utf-8"))
    lock = load_yaml(ROOT / "installer.lock.yaml")
    assert compositions["productRevision"] == lock["product"]["revision"]
    item_ids = [item["id"] for item in chooser["items"]]
    option_ids = [item["id"] for item in compositions["options"]]
    assert item_ids == option_ids and item_ids
    assert chooser["default"] in item_ids
    assert len(item_ids) == len(set(item_ids))
    candidate_studio = any(item_id.startswith("studio-hyprland-") for item_id in item_ids)
    candidate_gaming = any(item_id.startswith("gaming-hyprland-") for item_id in item_ids)
    candidate_recovery = "desktop-hyprland-recovery" in item_ids
    if candidate_gaming:
        gaming_ids = {item_id for item_id in item_ids if item_id.startswith("gaming-hyprland-")}
        assert len(gaming_ids) == 6, "candidate render must expose the six canonical Gaming profiles"
        assert {"desktop-hyprland", "desktop-niri"} <= set(item_ids)
        for item in chooser["items"]:
            if item["id"].startswith("gaming-hyprland-"):
                assert "steam" not in item["packages"], "Steam is proprietary and needs explicit opt-in"
                assert "Planned" in item["description"]
        for option in compositions["options"]:
            if option["id"].startswith("gaming-hyprland-"):
                assert option["edition"] == "gaming"
                assert option["profile"]["gamingSelection"]["specializations"]
    if candidate_studio:
        # Candidate/testing render: Studio specialization candidate choices
        # may appear only with explicit candidate invariants. The default
        # (release) render must never contain them.
        studio_ids = {item_id for item_id in item_ids if item_id.startswith("studio-hyprland-")}
        assert len(studio_ids) == 10, "candidate render must expose the ten canonical specializations"
        assert {"desktop-hyprland", "desktop-niri"} <= set(item_ids)
        for item in chooser["items"]:
            if item["id"].startswith("studio-hyprland-"):
                assert "reaper" not in item["packages"], "proprietary payloads need explicit opt-in"
                assert "Preview" in item["description"]
        for option in compositions["options"]:
            if option["id"].startswith("studio-hyprland-"):
                assert option["edition"] == "studio"
                assert option["profile"]["studioSelection"]["specializations"]
    if candidate_recovery:
        # Candidate/testing render: the recovery choice may appear only
        # with the full canonical snapper stack and honest copy. The
        # default (release) render must never contain it.
        recovery_items = [item for item in chooser["items"] if item["id"] == "desktop-hyprland-recovery"]
        assert len(recovery_items) == 1
        assert {"snapper", "snap-pac", "grub-btrfs"} <= set(recovery_items[0]["packages"])
        assert "not proven" in recovery_items[0]["description"]
        assert "candidate" in recovery_items[0]["description"]
        for option in compositions["options"]:
            if option["id"] == "desktop-hyprland-recovery":
                assert option["candidate"] is True
                assert option["capabilities"] == ["snapshots"]
                assert option["profile"]["recoverySelection"]["capabilities"] == ["snapshots"]
    elif not candidate_gaming and not candidate_studio:
        # Release render: Desktop plus Studio and Gaming Preview
        # choices. Specialization choices stay candidate-only (above).
        assert set(item_ids) == {
            "desktop-hyprland", "desktop-niri", "studio-hyprland", "studio-niri",
            "gaming-hyprland", "gaming-niri",
        }
    assert all(item.get("packages") for item in chooser["items"])
    screenshots = {item["id"]: item.get("screenshot") for item in chooser["items"]}
    assert screenshots["desktop-hyprland"] == "screenshots/desktop-hyprland.jpg"
    assert screenshots["desktop-niri"] == "screenshots/niri-experimental.svg"
    assert all(
        path.startswith(":/") or (config_root / "branding/hornero" / path).is_file()
        for path in screenshots.values()
    )
    assert all(item["edition"] not in {"agents", "server"} for item in compositions["options"])
    # Studio is a published Preview edition: its base choices belong to
    # the release render. Only specialization choices stay candidate-only,
    # and those keep their candidate flag with the catalogue maturity.
    assert all(
        item["maturity"] == "preview"
        for item in compositions["options"]
        if item["edition"] == "studio" and not item.get("candidate")
    )
    # Gaming is a published Preview edition: its base choices belong
    # to the release render with preview maturity.
    assert all(
        item["maturity"] == "preview"
        for item in compositions["options"]
        if item["edition"] == "gaming"
    )
    branding_root = config_root / "branding/hornero"
    branding = load_yaml(branding_root / "branding.desc")
    slideshow = branding.get("slideshow")
    assert isinstance(slideshow, list) and slideshow, (
        "Calamares branding requires at least one slideshow image or QML file"
    )
    assert all(
        isinstance(path, str) and (branding_root / path).is_file()
        for path in slideshow
    ), "every Calamares slideshow entry must resolve inside the branding directory"
    assert lock["arch"]["architecture"] == "x86_64"
    assert re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", lock["arch"]["snapshot"])
    assert re.fullmatch(r"[0-9a-f]{64}", lock["calamares"]["sha256"])
    calamares_pkgbuild = (ROOT / "packaging/calamares/PKGBUILD").read_text(encoding="utf-8")
    assert re.search(r"^depends=\([^\n]*'rsync'", calamares_pkgbuild, re.MULTILINE), (
        "the unpackfs module copies the base image through rsync, so Calamares must declare it"
    )
    assert 'shellprocess_descriptor="$pkgdir/usr/lib/calamares/modules/shellprocess/module.desc"' in calamares_pkgbuild
    assert "emergency: true" in calamares_pkgbuild
    package_builder = (ROOT / "scripts/build-package-repository.sh").read_text(encoding="utf-8")
    assert "makepkg --nodeps --noconfirm --force --cleanbuild --dir" in package_builder
    assert "--packagelist" not in package_builder, "package builder must compile packages before collecting artifacts"
    assert "makepkg produced no packages" in package_builder
    assert 'artifact_info=$(pacman -Qp "$artifact")' in package_builder
    assert "HORNEROS_PRODUCT_SOURCE" in package_builder
    assert "HORNEROS_CALAMARES_CONFIG" in package_builder
    assert '"$config_source/modules" "$calamares_tree/image/calamares/modules"' in package_builder
    assert "profile-packages" in package_builder
    assert "--profile-packages-dir" in package_builder
    profile_renderer = (ROOT / "scripts/render-installer-catalogue.py").read_text(encoding="utf-8")
    assert "system-profile.json" in profile_renderer and "/usr/lib/hornero/system-profile.json" in profile_renderer
    iso_builder = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert 'install -Dm755 "$ROOT/image/calamares/configure-user-defaults.py"' in iso_builder
    assert '"$profile/airootfs/usr/lib/hornero-installer/configure-user-defaults.py"' in iso_builder
    assert 'install -Dm755 "$ROOT/image/calamares/configure-recovery.py"' in iso_builder
    assert '"$profile/airootfs/usr/lib/hornero-installer/configure-recovery.py"' in iso_builder
    assert 'python3 "$product/scripts/resolve-edition.py"' not in iso_builder, (
        "the product resolver must only run after the catalogue renderer verifies its locked hash"
    )
    assert '"$ROOT/image/calamares/settings.conf" "$profile/calamares/settings.conf"' in iso_builder
    assert 'export HORNEROS_CALAMARES_CONFIG="$profile/calamares"' in iso_builder
    assert iso_builder.index('render-installer-catalogue.py') < iso_builder.index('pacstrap -C ')
    assert "base_packages+=(python)" in iso_builder, (
        "the target needs Python before package selection for emergency cleanup"
    )
    assert iso_builder.index('work="$work_path"') < iso_builder.index('profile="$work/profile"')
    assert iso_builder.index('output="$output_path"') < iso_builder.index('profile="$work/profile"')
    assert iso_builder.index('product="$work/product"') < iso_builder.index('export HORNEROS_PRODUCT_SOURCE="$product"')
    assert 's|@ARCH_SNAPSHOT@|$snapshot|g' in iso_builder
    assert 'mksquashfs "$target"' in iso_builder and '-processors "$jobs"' in iso_builder
    assert "54525952" in iso_builder, "shared build/output filesystems must reserve 52 GiB"
    assert 'image_file.read(4 * 1024 * 1024)' in iso_builder, "ISO hashing must stream bounded chunks"
    profile_definition = (ROOT / "image/archiso/profiledef.sh").read_text(encoding="utf-8")
    assert "'-processors' '2'" in profile_definition
    assert re.search(rf"^pkgver={re.escape(lock['calamares']['version'])}$", calamares_pkgbuild, re.MULTILINE)
    assert lock["calamares"]["archive"].endswith(f"/v{lock['calamares']['version']}.tar.gz")
    assert lock["calamares"]["sha256"] in calamares_pkgbuild
    media = lock["profileMedia"]
    assert re.fullmatch(r"[0-9a-f]{40}", media["revision"])
    assert re.fullmatch(r"[0-9a-f]{64}", media["desktopPreview"]["sourceSha256"])
    desktop_preview = ROOT / media["desktopPreview"]["packaged"]
    assert desktop_preview.is_file()
    assert hashlib.sha256(desktop_preview.read_bytes()).hexdigest() == media["desktopPreview"]["sha256"]
    niri_preview = ROOT / "image/calamares/branding/hornero/screenshots/niri-experimental.svg"
    assert niri_preview.is_file() and "not a desktop screenshot" in niri_preview.read_text(encoding="utf-8")
    aur = lock["aur"]["packages"]
    assert aur and all(re.fullmatch(r"[0-9a-f]{40}", item["revision"]) for item in aur.values())
    required_hornero = {
        "hornero-shell",
        "hornero-config",
        "horneroctl-bin",
        "hornero-greeter",
        "hornero-greeter-media-base",
        "python-materialyoucolor",
        "ttf-rubik-vf",
    }
    assert required_hornero <= set(aur)
    assert "libcava" in aur, "the locked shell package requires the pinned libcava AUR runtime"
    assert all(item.get("packages") for item in compositions["options"])
    assert all(
        item["profilePackage"] in item["packages"]
        and item["profilePackage"].startswith("hornero-profile-")
        for item in compositions["options"]
    ), "each installer choice must install its generated profile identity package"
    aur_names = set(aur)
    selected_names = {name for option in compositions["options"] for name in option["packages"]}
    assert selected_names & required_hornero >= {
        "hornero-shell",
        "hornero-config",
        "horneroctl-bin",
        "hornero-greeter",
        "hornero-greeter-media-base",
    }

    archiso = ROOT / "image" / "archiso"
    live_entries = [
        line.strip()
        for line in (archiso / "packages.x86_64").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(live_entries) == len(set(live_entries)), "duplicate Archiso live packages"
    live_packages = set(live_entries)
    assert {
        "calamares",
        "linux",
        "linux-firmware",
        "mkinitcpio",
        "mkinitcpio-archiso",
        "networkmanager",
        "rsync",
        "sddm",
        "syslinux",
        "hyprland",
        "quickshell",
        "hornero-shell",
        "hornero-config",
        "horneroctl-bin",
        "kitty",
        "xdg-desktop-portal-hyprland",
    } <= live_packages
    assert not any(name.startswith("xfce") or name == "xfconf" for name in live_packages), (
        "the live session is HorneroOS Desktop (Hyprland), not XFCE"
    )
    # Bluetooth: enabled on installed targets, never mandatory (a
    # Bluetooth-less VM or server install must not fail), and present
    # in the live session, which is the real HorneroOS Desktop.
    bt_units = [
        unit
        for unit in parsed["services-systemd"]["units"]
        if unit.get("name") == "bluetooth.service"
    ]
    assert bt_units == [
        {"name": "bluetooth.service", "action": "enable", "mandatory": False}
    ], "bluetooth.service must be enabled with mandatory: false"
    # Snapshots capability units exist only when the opt-in capability
    # installed them; enabling must never fail a default install.
    for unit_name in ("snapper-timeline.timer", "snapper-cleanup.timer", "grub-btrfsd.service"):
        units = [
            unit
            for unit in parsed["services-systemd"]["units"]
            if unit.get("name") == unit_name
        ]
        assert units == [
            {"name": unit_name, "action": "enable", "mandatory": False}
        ], f"{unit_name} must be enabled with mandatory: false"
    assert parsed["shellprocess-recovery"]["dontChroot"] is True
    assert {"bluez", "bluez-utils"} <= live_packages, (
        "the live Desktop needs bluez/bluez-utils for its Bluetooth pane"
    )
    live_bt_link = (
        archiso
        / "airootfs/etc/systemd/system/multi-user.target.wants/bluetooth.service"
    )
    assert live_bt_link.is_symlink() and live_bt_link.readlink().as_posix() == (
        "/usr/lib/systemd/system/bluetooth.service"
    ), "the live session must enable bluetooth.service"
    # Firmware: linux-firmware (which carries Bluetooth adapter
    # firmware) is already in every composition and in the live image.
    assert all(
        "linux-firmware" in option["packages"]
        for option in compositions["options"]
    ), "every composition must carry linux-firmware"
    # Installed bluez/bluez-utils come from the pinned HorneroOS/hornero
    # catalogue (desktop set), not an installer-owned list. Until the
    # catalogue hand-off in docs/calamares-provisional.md lands and the
    # lock is re-rendered, compositions legitimately lack them; once
    # any option carries them, every option must (Desktop is the base
    # of Studio and Gaming).
    bt_options = [
        {"bluez", "bluez-utils"} <= set(option["packages"])
        for option in compositions["options"]
    ]
    assert all(bt_options) or not any(bt_options), (
        "bluez/bluez-utils must reach every composition or none yet"
    )
    live_session = (archiso / "airootfs/etc/sddm.conf.d/10-hornero-live.conf").read_text(encoding="utf-8")
    assert "Session=hyprland.desktop" in live_session
    unpackfs = load_yaml(config_root / "modules/unpackfs.conf")
    assert unpackfs["unpack"] and unpackfs["unpack"][0]["sourcefs"] == "squashfs"
    assert "/run/archiso/bootmnt/hornero/x86_64/base.sqfs" == unpackfs["unpack"][0]["source"]
    assert not {"xfce4", "xfce4-goodies"} & live_packages, (
        "live image packages must name XFCE components explicitly to avoid prompts"
    )
    assert "uefi.systemd-boot" in profile_definition and "bios.syslinux" in profile_definition
    assert profile_definition.index("bios.syslinux") < profile_definition.index("uefi.systemd-boot"), (
        "Archiso requires the BIOS El Torito entry before the UEFI entry"
    )
    assert (archiso / "efiboot/loader/loader.conf").is_file()
    assert (archiso / "efiboot/loader/entries/01-horneroos.conf").is_file()
    assert (archiso / "syslinux/syslinux.cfg").is_file()
    initcpio_config = (
        archiso / "airootfs/etc/mkinitcpio.conf.d/archiso.conf"
    ).read_text(encoding="utf-8")
    assert "archiso_loop_mnt" in initcpio_config and " archiso " in initcpio_config, (
        "the live initramfs must include the Archiso mount hooks"
    )
    assert not any(
        hook in initcpio_config
        for hook in ("archiso_pxe_common", "archiso_pxe_nbd", "archiso_pxe_http", "archiso_pxe_nfs")
    ), "PXE hooks require extra clients that are not part of the local installer media"
    build_script = (ROOT / "scripts/build-iso.sh").read_text(encoding="utf-8")
    assert 'mksquashfs "$target" "$work/base.sqfs"' in build_script
    assert 'arch=$(sed -n' in build_script and 'profiledef.sh' in build_script
    assert '"/hornero/$arch/base.sqfs"' in build_script
    assert "-boot_image any replay" in build_script
    assert (archiso / "airootfs/etc/sudoers.d/hornero-live").is_file()
    sudoers = (archiso / "airootfs/etc/sudoers.d/hornero-live").read_text(encoding="utf-8")
    assert 'Defaults:hornero-live env_keep += "WAYLAND_DISPLAY XDG_RUNTIME_DIR DISPLAY XAUTHORITY"' in sudoers
    assert 'NOPASSWD: /usr/local/bin/hornero-installer-run ""' in sudoers
    launcher = (archiso / "airootfs/usr/local/bin/hornero-installer-start").read_text(encoding="utf-8")
    desktop_entry = (CALAMARES / "hornero-installer.desktop").read_text(encoding="utf-8")
    runner = (archiso / "airootfs/usr/local/bin/hornero-installer-run").read_text(encoding="utf-8")
    live_cleanup = archiso / "airootfs/usr/local/lib/hornero-installer/cleanup-package-source.py"
    assert live_cleanup.read_bytes() == (CALAMARES / "cleanup-package-source.py").read_bytes()
    post_exit_cleanup = (
        archiso / "airootfs/usr/local/lib/hornero-installer/cleanup-calamares-targets.py"
    ).read_text(encoding="utf-8")
    assert "sudo -E" not in launcher + desktop_entry
    assert "sudo /usr/local/bin/hornero-installer-run" in launcher
    assert "/usr/bin/nm-online --quiet --timeout=45" in launcher
    assert "/usr/bin/timeout 10 /usr/bin/getent ahostsv4 archive.archlinux.org" in launcher
    assert launcher.index("nm-online") < launcher.index("getent") < launcher.index("sudo")
    assert "Exec=/usr/local/bin/hornero-installer-start" in desktop_entry
    assert "sudo /usr/local/bin/hornero-installer-run" not in desktop_entry
    assert "/usr/bin/calamares -D6" in runner
    assert "/usr/local/lib/hornero-installer/cleanup-calamares-targets.py" in runner
    assert "TEMP_INCLUDES" in post_exit_cleanup and "/usr/bin/umount" in post_exit_cleanup
    assert "def safe_target" in post_exit_cleanup
    assert 'target.name.startswith("calamares-root-")' in post_exit_cleanup
    assert "target_info.st_uid != owner_uid" in post_exit_cleanup
    assert "/root/.cache/calamares/session.log" in runner
    assert "/var/log/hornero-installer/session.log" in runner
    assert "install -d -m 0750 -o root -g hornero-live" in runner
    assert '["/usr/local/bin/hornero-installer-run"]="0:0:755"' in profile_definition
    assert "exit \"$installer_status\"" in runner
    live_user = (archiso / "airootfs/etc/sysusers.d/hornero-live.conf").read_text(encoding="utf-8")
    assert live_user.startswith("u hornero-live ") and "\nd " not in live_user
    live_home = (archiso / "airootfs/etc/tmpfiles.d/hornero-live.conf").read_text(encoding="utf-8")
    assert "d /home/hornero-live 0750 hornero-live hornero-live -" in live_home
    assert "d /var/log/hornero-installer 0750 root hornero-live -" in live_home
    assert (archiso / "airootfs/etc/sddm.conf.d/10-hornero-live.conf").is_file()
    target_repo = (ROOT / "image/calamares/hornero-installer-repo.conf").read_text(encoding="utf-8")
    assert "file:///usr/share/hornero-installer/repo" in target_repo
    assert "hornero-installer-repo.conf" in (archiso / "airootfs/etc/pacman.d/hornero-installer.conf").read_text(encoding="utf-8")
    assert "@ARCH_SNAPSHOT@" in (archiso / "pacman.conf").read_text(encoding="utf-8")
    assert "@ARCH_SNAPSHOT@" in (archiso / "airootfs/etc/pacman.d/hornero-installer-mirrorlist.conf").read_text(encoding="utf-8")
    assert len("HORNER" + lock["arch"]["snapshot"][2:4] + lock["arch"]["snapshot"][5:7]) <= 11
    mount_config = parsed["mount"]["extraMounts"]
    assert any(mount.get("mountPoint") == "/usr/share/hornero-installer/repo" for mount in mount_config)

    with tempfile.TemporaryDirectory(prefix="hornero-installer-cleanup-") as directory:
        fake_root = Path(directory)
        (fake_root / "etc/pacman.d").mkdir(parents=True)
        (fake_root / "usr/lib/hornero-installer").mkdir(parents=True)
        (fake_root / "etc/pacman.conf").write_text(
            "[options]\nInclude = /etc/pacman.d/hornero-installer.conf\n"
            "[core]\nInclude = /etc/pacman.d/hornero-installer-mirrorlist.conf\n"
            "[extra]\nInclude = /etc/pacman.d/hornero-installer-mirrorlist.conf\n",
            encoding="utf-8",
        )
        for path in ("etc/pacman.d/hornero-installer.conf", "etc/pacman.d/hornero-installer-mirrorlist.conf", "usr/lib/hornero-installer/cleanup-package-source.py"):
            (fake_root / path).write_text("temporary", encoding="utf-8")
        import importlib.util
        spec = importlib.util.spec_from_file_location("cleanup_package_source", ROOT / "image/calamares/cleanup-package-source.py")
        cleanup_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cleanup_module)
        cleanup_module.cleanup(fake_root)
        clean_conf = (fake_root / "etc/pacman.conf").read_text(encoding="utf-8")
        assert "hornero-installer" not in clean_conf
        assert clean_conf.count("Include = /etc/pacman.d/mirrorlist") == 2
        assert all(not (fake_root / path).exists() for path in ("etc/pacman.d/hornero-installer.conf", "etc/pacman.d/hornero-installer-mirrorlist.conf", "usr/lib/hornero-installer/cleanup-package-source.py"))

    with tempfile.TemporaryDirectory(prefix="hornero-calamares-post-exit-") as directory:
        fake_target = Path(directory) / "calamares-root-test"
        (fake_target / "etc/pacman.d").mkdir(parents=True)
        (fake_target / "etc").mkdir(exist_ok=True)
        (fake_target / "usr/lib/hornero-installer").mkdir(parents=True)
        (fake_target / "etc/pacman.conf").write_text(
            "[core]\nInclude = /etc/pacman.d/hornero-installer.conf\n"
            "[extra]\nInclude = /etc/pacman.d/hornero-installer-mirrorlist.conf\n",
            encoding="utf-8",
        )
        (fake_target / "etc/pacman.d/hornero-installer.conf").write_text("temp\n", encoding="utf-8")
        (fake_target / "etc/pacman.d/hornero-installer-mirrorlist.conf").write_text("temp\n", encoding="utf-8")
        post_exit_spec = importlib.util.spec_from_file_location(
            "cleanup_calamares_targets",
            archiso / "airootfs/usr/local/lib/hornero-installer/cleanup-calamares-targets.py",
        )
        post_exit_module = importlib.util.module_from_spec(post_exit_spec)
        post_exit_spec.loader.exec_module(post_exit_module)
        configured_mounts = {
            Path(item["mountPoint"].lstrip("/"))
            for item in parsed["mount"]["extraMounts"] + parsed["mount"]["btrfsSubvolumes"]
        }
        configured_mounts.add(Path(parsed["partition"]["efi"]["mountPoint"].lstrip("/")))
        assert set(map(Path, post_exit_module.TARGET_MOUNTS)) == configured_mounts
        unmounted: list[Path] = []
        failures, cleaned = post_exit_module.cleanup_targets(
            [fake_target / "etc/pacman.conf"],
            cleanup_module,
            lambda mountpoint: unmounted.append(mountpoint),
            temp_root=Path(directory),
            owner_uid=fake_target.stat().st_uid,
        )
        assert failures == [] and cleaned == [fake_target]
        assert unmounted == [
            fake_target / "etc/hosts",
            fake_target / "etc/resolv.conf",
            fake_target / "sys/firmware/efi/efivars",
            fake_target / "run/udev",
            fake_target / "usr/share/hornero-installer/repo",
            fake_target / "dev",
            fake_target / "proc",
            fake_target / "sys",
            fake_target / "run",
            fake_target / "var/cache",
            fake_target / "var/log",
            fake_target / "home",
            fake_target / "boot",
            fake_target / ".snapshots",
            fake_target,
        ]
        assert "hornero-installer" not in (fake_target / "etc/pacman.conf").read_text(encoding="utf-8")
        rejected, ignored = post_exit_module.cleanup_targets(
            [fake_target / "etc/pacman.conf"],
            cleanup_module,
            lambda _mountpoint: (_ for _ in ()).throw(AssertionError("unsafe target was unmounted")),
            temp_root=Path(directory),
            owner_uid=fake_target.stat().st_uid + 1,
        )
        assert rejected == [] and ignored == []

    with tempfile.TemporaryDirectory(prefix="hornero-installer-user-defaults-") as directory:
        fake_root = Path(directory)
        defaults = fake_root / "etc/xdg/xfce4/helpers.rc"
        defaults.parent.mkdir(parents=True)
        defaults.write_text("TerminalEmulator=kitty\n", encoding="utf-8")
        (fake_root / "etc/passwd").write_text(
            "root:x:0:0:root:/root:/bin/bash\n"
            "qauser:x:1000:1000:QA User:/home/qauser:/bin/bash\n",
            encoding="utf-8",
        )
        (fake_root / "home/qauser").mkdir(parents=True)
        user_defaults_spec = importlib.util.spec_from_file_location(
            "configure_user_defaults", ROOT / "image/calamares/configure-user-defaults.py"
        )
        user_defaults_module = importlib.util.module_from_spec(user_defaults_spec)
        user_defaults_spec.loader.exec_module(user_defaults_module)
        user_defaults_module.configure_user_defaults(fake_root)
        user_config = fake_root / "home/qauser/.config/xfce4/helpers.rc"
        assert user_config.read_text(encoding="utf-8") == "TerminalEmulator=kitty\n"
        assert user_config.stat().st_mode & 0o777 == 0o644
        user_config.write_text("TerminalEmulator=custom\n", encoding="utf-8")
        user_defaults_module.configure_user_defaults(fake_root)
        assert user_config.read_text(encoding="utf-8") == "TerminalEmulator=custom\n"

    with tempfile.TemporaryDirectory(prefix="hornero-installer-user-defaults-link-") as directory:
        fixture = Path(directory)
        fake_root = fixture / "target"
        outside = fixture / "outside"
        (fake_root / "etc/xdg/xfce4").mkdir(parents=True)
        (fake_root / "etc/xdg/xfce4/helpers.rc").write_text(
            "TerminalEmulator=kitty\n", encoding="utf-8"
        )
        (fake_root / "etc").joinpath("passwd").write_text(
            "qauser:x:1000:1000:QA User:/home/qauser:/bin/bash\n", encoding="utf-8"
        )
        user_home = fake_root / "home/qauser"
        user_home.mkdir(parents=True)
        (user_home / ".config").symlink_to(outside, target_is_directory=True)
        user_defaults_spec = importlib.util.spec_from_file_location(
            "configure_user_defaults_link", ROOT / "image/calamares/configure-user-defaults.py"
        )
        user_defaults_module = importlib.util.module_from_spec(user_defaults_spec)
        user_defaults_spec.loader.exec_module(user_defaults_module)
        try:
            user_defaults_module.configure_user_defaults(fake_root)
        except ValueError as error:
            assert "symlink" in str(error)
        else:
            raise AssertionError("user defaults followed a symlink outside the target root")
        assert not (outside / "xfce4").exists()
        (fake_root / "etc/passwd").write_text(
            "qauser:x:1000:1000:QA User:/home/../../tmp/outside:/bin/bash\n",
            encoding="utf-8",
        )
        try:
            user_defaults_module.configure_user_defaults(fake_root)
        except ValueError as error:
            assert "unsafe path components" in str(error)
        else:
            raise AssertionError("user defaults accepted a passwd home with traversal components")

    print(f"installer config checks passed ({len(configs)} module configs; {len(item_ids)} catalogue choices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

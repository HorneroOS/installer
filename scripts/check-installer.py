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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=CALAMARES, help="Calamares config directory")
    parser.add_argument("--schema-root", type=Path, help="Calamares source src/modules directory")
    args = parser.parse_args()
    config_root = args.config_root.resolve()
    settings = load_yaml(config_root / "settings.conf")
    phases = settings.get("sequence", [])
    assert [next(iter(phase)) for phase in phases] == ["show", "exec", "show"]
    assert phases[0]["show"][-2:] == ["packagechooser", "summary"]
    assert phases[1]["exec"].index("shellprocess@cleanup") == phases[1]["exec"].index("packages") + 1
    assert phases[1]["exec"][-1] == "umount"
    assert settings["prompt-install"] is True
    assert settings["dont-chroot"] is False

    modules = config_root / "modules"
    configs = sorted(modules.glob("*.conf"))
    assert len(configs) >= 10, "expected the core target-system modules to be configured"
    parsed = {path.stem: load_yaml(path) for path in configs}
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
            jsonschema.Draft7Validator(load_yaml(schema_path)).validate(configuration)
    assert parsed["welcome"]["geoip"]["style"] == "none"
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
    assert parsed["partition"]["enableLuksAutomatedPartitioning"] is True
    assert parsed["bootloader"]["efiBootLoader"] == "grub"
    assert parsed["packages"]["backend"] == "pacman"
    assert parsed["packages"]["update_system"] is False
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
    assert set(item_ids) == {"desktop-hyprland", "desktop-niri"}
    assert all(item.get("packages") for item in chooser["items"])
    screenshots = {item["id"]: item.get("screenshot") for item in chooser["items"]}
    assert screenshots["desktop-hyprland"] == "screenshots/desktop-hyprland.jpg"
    assert screenshots["desktop-niri"] == "screenshots/niri-experimental.svg"
    assert all(
        path.startswith(":/") or (config_root / "branding/hornero" / path).is_file()
        for path in screenshots.values()
    )
    assert all(item["edition"] not in {"agents", "studio", "server"} for item in compositions["options"])
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
        "xfce4-panel",
        "xfce4-session",
        "xfce4-settings",
        "xfce4-terminal",
        "xfconf",
        "xfdesktop",
        "xfwm4",
    } <= live_packages
    unpackfs = load_yaml(config_root / "modules/unpackfs.conf")
    assert unpackfs["unpack"] and unpackfs["unpack"][0]["sourcefs"] == "squashfs"
    assert "/usr/share/hornero-installer/base.sqfs" == unpackfs["unpack"][0]["source"]
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
    assert (archiso / "airootfs/etc/sudoers.d/hornero-live").is_file()
    sudoers = (archiso / "airootfs/etc/sudoers.d/hornero-live").read_text(encoding="utf-8")
    assert 'Defaults:hornero-live env_keep += "DISPLAY XAUTHORITY"' in sudoers
    assert 'NOPASSWD: /usr/bin/calamares ""' in sudoers
    launcher = (archiso / "airootfs/usr/local/bin/hornero-installer-start").read_text(encoding="utf-8")
    desktop_entry = (CALAMARES / "hornero-installer.desktop").read_text(encoding="utf-8")
    assert "sudo -E" not in launcher + desktop_entry
    live_user = (archiso / "airootfs/etc/sysusers.d/hornero-live.conf").read_text(encoding="utf-8")
    assert live_user.startswith("u hornero-live ") and "\nd " not in live_user
    live_home = (archiso / "airootfs/etc/tmpfiles.d/hornero-live.conf").read_text(encoding="utf-8")
    assert "d /home/hornero-live 0750 hornero-live hornero-live -" in live_home
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

    print(f"installer config checks passed ({len(configs)} module configs; {len(item_ids)} catalogue choices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

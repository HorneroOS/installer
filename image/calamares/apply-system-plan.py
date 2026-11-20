#!/usr/bin/env python3
"""Validate a system selection and write the installation plan.

The selection arrives as a JSON file owned by the invoking user (root in the installer; mode 0600 enforced) written by the
installer launcher (or a future Calamares page) at
/run/hornero-installer/system-selection.json. When the file is
absent or empty this job is a no-op, so an untouched install
produces exactly the current preview32 result.

A present selection is validated against system-allowlist.yaml:
unknown kernels, a fallback equal to the primary kernel, a
non-GRUB bootloader, a swap partition, disabling a mandatory
service, an unknown theme, or extra kernels while offline all
fail before any package transaction with an actionable message.
The validated plan is written to
<root>/usr/lib/hornero/installation-plan.json (the file
verify-install.py already consumes) and the one-shot selection
file is removed. Applying the plan (kernels, services, GRUB
default) is apply-system-choices.py, later in the exec sequence.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import yaml

DEFAULT_SELECTION_PATH = Path("/run/hornero-installer/system-selection.json")
ALLOWLIST_PATH = Path(__file__).with_name("system-allowlist.yaml")
PLAN_REL = Path("usr/lib/hornero/installation-plan.json")

DEFAULT_SELECTION = {
    "primaryKernel": "linux",
    "fallbackKernel": None,
    "bootloader": "grub",
    "firmware": None,
    "encryption": "none",
    "swap": "none",
    "services": {"bluetooth": True, "timesyncd": True},
    "appearance": {"theme": "hornero-signal-night", "shellPreset": "cockpit"},
    "offline": False,
}


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"system allowlist must be a mapping: {path}")
    return data


def validate_selection(selection: dict, allowlist: dict) -> list[str]:
    errors: list[str] = []
    kernels = allowlist.get("kernels") or {}
    primary = selection.get("primaryKernel")
    fallback = selection.get("fallbackKernel")
    if primary not in kernels:
        errors.append(
            f"Unknown primary kernel: {primary!r}. Valid kernels: {sorted(kernels)}"
        )
    if fallback is not None:
        if fallback not in kernels:
            errors.append(
                f"Unknown fallback kernel: {fallback!r}. Valid kernels: {sorted(kernels)}"
            )
        elif fallback == primary:
            errors.append("The fallback kernel must differ from the primary kernel.")
    bootloader = selection.get("bootloader")
    if bootloader not in (allowlist.get("bootloaders") or []):
        errors.append(
            f"Bootloader {bootloader!r} is not offered. "
            f"Offered bootloaders: {allowlist.get('bootloaders')}"
        )
    if bootloader == "systemd-boot" and selection.get("firmware") != "uefi":
        errors.append(
            "systemd-boot needs UEFI: this machine did not boot in UEFI "
            "mode (firmware is not 'uefi'). Choose GRUB or reboot the "
            "installer in UEFI mode. Nothing has been written yet."
        )
    swap = selection.get("swap")
    if swap not in (allowlist.get("swapChoices") or []):
        errors.append(
            f"Swap choice {swap!r} is not offered: use 'none', 'file' or "
            "'partition' (hibernation-sized swap is not offered: the "
            "mkinitcpio openswap hook is not pinned in the catalogue)."
        )
    if selection.get("encryption") not in (None, "none", "luks"):
        errors.append(f"Unknown encryption mode: {selection.get('encryption')!r}")
    if swap == "partition" and selection.get("encryption") == "luks":
        errors.append(
            "A swap partition is only offered without LUKS: with LUKS it "
            "needs the mkinitcpio openswap hook, which is not pinned in "
            "the Hornero catalogue. Choose swap 'file' or 'none', or "
            "disable LUKS encryption."
        )
    services = selection.get("services") or {}
    optional = allowlist.get("optionalServices") or {}
    for name, enabled in services.items():
        if name not in optional:
            errors.append(
                f"Service {name!r} cannot be toggled. Optional services: "
                f"{sorted(optional)}; NetworkManager and SDDM are always enabled."
            )
        elif not isinstance(enabled, bool):
            errors.append(f"Service {name!r} selection must be true or false.")
    appearance = selection.get("appearance") or {}
    if appearance.get("theme") not in (allowlist.get("themes") or []):
        errors.append(
            f"Theme {appearance.get('theme')!r} is not available. "
            f"Available themes: {allowlist.get('themes')}"
        )
    if appearance.get("shellPreset") not in (allowlist.get("shellPresets") or []):
        errors.append(
            f"Shell preset {appearance.get('shellPreset')!r} is not available. "
            f"Available presets: {allowlist.get('shellPresets')}"
        )
    if selection.get("offline"):
        if primary != "linux" or fallback is not None:
            errors.append(
                "Offline installation only carries the default 'linux' kernel "
                "from the local repository; reconnect or keep the default kernel."
            )
    return errors


def selected_kernels(selection: dict) -> list[str]:
    kernels = [selection["primaryKernel"]]
    if selection.get("fallbackKernel"):
        kernels.append(selection["fallbackKernel"])
    return kernels


def kernel_packages(selection: dict, allowlist: dict) -> list[str]:
    """Kernel packages in primary-first order.

    Headers are added only when more than one kernel is installed
    (DKMS/multi-kernel rule), so the single-kernel default stays
    byte-identical to the current compositions (linux, no headers).
    """
    kernels = selected_kernels(selection)
    entries = allowlist["kernels"]
    packages: list[str] = []
    for kernel in kernels:
        packages.append(entries[kernel]["package"])
    if len(kernels) > 1:
        for kernel in kernels:
            headers = entries[kernel].get("headers")
            if headers:
                packages.append(headers)
    return packages


def transform_packages(edition_packages: list[str], selection: dict, allowlist: dict) -> list[str]:
    """Edition packages with the kernel set replaced exactly once."""
    kernel_ids = set(allowlist["kernels"])
    kernel_pkgs = {
        entry["package"] for entry in allowlist["kernels"].values()
    } | {entry["headers"] for entry in allowlist["kernels"].values() if entry.get("headers")}
    replacement = kernel_packages(selection, allowlist)
    output: list[str] = []
    inserted = False
    for package in edition_packages:
        if package in kernel_pkgs:
            if not inserted:
                output.extend(replacement)
                inserted = True
            continue
        if package not in output:
            output.append(package)
    if not inserted:
        output = replacement + output
    assert kernel_ids  # allowlist sanity, ids mirror package names today
    return output


def build_plan(selection: dict, allowlist: dict) -> dict:
    errors = validate_selection(selection, allowlist)
    if errors:
        raise ValueError("; ".join(errors))
    kernels = selected_kernels(selection)
    services_cfg = selection.get("services") or {}
    enabled_units = [
        allowlist["optionalServices"][name]["unit"]
        for name, enabled in services_cfg.items()
        if enabled
    ]
    return {
        "schemaVersion": 1,
        "selection": {
            "kernels": kernels,
            "primaryKernel": selection["primaryKernel"],
            "fallbackKernel": selection.get("fallbackKernel"),
            "bootloader": selection.get("bootloader", "grub"),
            "firmware": selection.get("firmware"),
            "encryption": selection.get("encryption", "none"),
            "swap": selection.get("swap", "none"),
            "services": dict(services_cfg),
            "appearance": dict(selection.get("appearance") or {}),
            "offline": bool(selection.get("offline", False)),
        },
        "packages": kernel_packages(selection, allowlist),
        "services": enabled_units,
        "espRecommendedMiB": esp_recommended_mib(selection, allowlist),
    }


def esp_recommended_mib(selection: dict, allowlist: dict) -> int:
    """ESP size for the selected bootloader: catalogue base + per-kernel."""
    kernels = selected_kernels(selection)
    if selection.get("bootloader") == "systemd-boot":
        base = int(allowlist.get("systemdBootEspMiB", 1024))
        per_kernel = int(allowlist.get("systemdBootPerKernelMiB", 256))
    else:
        base = int(allowlist.get("grubEspMiB", 512))
        per_kernel = int(allowlist.get("grubPerKernelMiB", 256))
    return base + per_kernel * (len(kernels) - 1)


def target_encryption(root: Path) -> str:
    """'luks' when the mounted target carries a crypttab, else 'none'."""
    crypttab = root / "etc/crypttab"
    if crypttab.is_file() and not crypttab.is_symlink():
        for line in crypttab.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return "luks"
    return "none"


def _reject_symlink_components(root: Path, rel: Path) -> None:
    current = root
    for component in rel.parts:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in installation plan path: {current}")


def write_plan(root: Path, plan: dict) -> Path:
    root = root.resolve()
    _reject_symlink_components(root, PLAN_REL)
    destination = root / PLAN_REL
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink():
        raise ValueError(f"Refusing symlink in installation plan path: {destination.parent}")
    destination.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def apply_system_plan(root: Path, selection_path: Path, allowlist: dict) -> dict | None:
    """Write the plan for a present selection; None when absent (no-op)."""
    if not selection_path.is_file():
        return None
    stat_result = selection_path.stat()
    if stat_result.st_uid != os.geteuid():
        raise ValueError("system selection must be owned by the invoking user")
    if stat_result.st_mode & 0o077:
        raise ValueError("system selection must have mode 0600")
    raw = selection_path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    selection = dict(DEFAULT_SELECTION)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("system selection must be a JSON object")
    selection.update(parsed)
    # LUKS is chosen on the partition page, after any system page: the
    # mounted target is the ground truth for the swap-partition gate.
    if selection.get("encryption") in (None, "none"):
        selection["encryption"] = target_encryption(root)
    plan = build_plan(selection, allowlist)
    # Fail before the package transaction (not at verify-install,
    # after the bootloader) when the plan cannot fit the ESP the
    # partition step already created (multi-kernel GRUB, or any
    # systemd-boot selection, which needs a larger ESP).
    if len(plan["selection"]["kernels"]) > 1 or plan["selection"]["bootloader"] == "systemd-boot":
        boot_dir = root / "boot"
        if boot_dir.is_dir():
            boot_mib = shutil.disk_usage(boot_dir).total // (1024 * 1024)
            if boot_mib < int(plan["espRecommendedMiB"]):
                raise ValueError(
                    f"boot filesystem is {boot_mib} MiB but this selection "
                    f"needs {plan['espRecommendedMiB']} MiB; choose GRUB/a "
                    "single kernel or partition manually with a larger ESP"
                )
    write_plan(root, plan)
    selection_path.unlink(missing_ok=True)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="installed target root")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION_PATH)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_PATH)
    args = parser.parse_args()
    try:
        plan = apply_system_plan(args.root, args.selection, load_allowlist(args.allowlist))
    except (ValueError, json.JSONDecodeError) as error:
        print(f"apply-system-plan: {error}", file=sys.stderr)
        return 1
    if plan is None:
        print("apply-system-plan: no system selection; keeping the default installation")
    else:
        print(f"apply-system-plan: wrote plan for kernels {plan['selection']['kernels']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

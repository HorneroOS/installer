#!/usr/bin/env python3
"""Deterministic installation-plan contract for the composable flow.

The canonical HorneroOS/hornero catalogue and its resolver own every
package list. This module never hard-codes a package list: it only
validates a selection against catalogue maps (`kernels:`,
`bootloaders:`, `capabilities:`) when the pinned catalogue provides
them, computes the ESP size from the catalogue bootloader entry, and
emits the deterministic plan (schemaVersion 2) consumed by the
renderer, the summary, and verify-install.

Until the pinned catalogue ships those maps, the runtime Calamares
wiring stays on the current single-chooser flow; this contract and
its tests are the implementable surface (see
docs/calamares-provisional.md).
"""

from __future__ import annotations

PLAN_SCHEMA_VERSION = 2


def esp_recommended_mib(bootloader_entry: dict, kernel_count: int) -> int:
    """ESP size: catalogue base plus per-extra-kernel allowance."""
    if kernel_count < 1:
        raise ValueError("Select at least one kernel.")
    base = int(bootloader_entry["espBaseMiB"])
    per_kernel = int(bootloader_entry.get("perKernelMiB", 0))
    return base + per_kernel * (kernel_count - 1)


def entry_packages(catalogue: dict, entry: dict) -> list[str]:
    """Packages for a kernel/bootloader/capability catalogue entry.

    The canonical catalogue declares direct ``packages:`` lists on these
    entries. A legacy ``packageSet:`` reference is also honoured so both
    shapes resolve to the same list — one schema, never silently empty.
    """
    packages = list(entry.get("packages", []))
    if entry.get("packageSet"):
        for package in _package_set_packages(catalogue, entry["packageSet"]):
            if package not in packages:
                packages.append(package)
    return packages


def _package_set_packages(catalogue: dict, set_id: str) -> list[str]:
    sets = catalogue.get("packageSets", {})
    # Bootloader/capability entries name a set as "bootloader:grub" or
    # "capability:bluetooth"; the catalogue key may carry that prefix.
    entry = sets.get(set_id)
    if entry is None and ":" in set_id:
        entry = sets.get(set_id.split(":", 1)[1])
    if entry is None:
        raise ValueError(f"unknown package set: {set_id}")
    return list(entry.get("packages", []))


def validate_selection(catalogue: dict, selection: dict) -> list[str]:
    """Return actionable incompatibility messages (empty = valid)."""
    errors: list[str] = []
    kernels_map = catalogue.get("kernels") or {}
    bootloaders_map = catalogue.get("bootloaders") or {}
    capabilities_map = catalogue.get("capabilities") or {}

    kernels = list(selection.get("kernels") or [])
    if not kernels:
        errors.append("Select at least one kernel.")
    if len(kernels) != len(set(kernels)):
        errors.append("Kernels must be unique.")
    for kernel in kernels:
        if kernel not in kernels_map:
            errors.append(
                f"Unknown kernel: {kernel}. Valid kernels: {sorted(kernels_map)}"
            )
    primary = selection.get("primaryKernel")
    if kernels and primary not in kernels:
        errors.append("The primary kernel must be one of the installed kernels.")
    fallback = selection.get("fallbackKernel")
    if fallback is not None:
        if fallback not in kernels:
            errors.append("The fallback kernel must be one of the installed kernels.")
        if fallback == primary:
            errors.append("The fallback kernel must differ from the primary kernel.")

    bootloader = selection.get("bootloader")
    firmware = selection.get("firmware")
    if bootloader not in bootloaders_map:
        errors.append(
            f"Unknown bootloader: {bootloader}. "
            f"Valid bootloaders: {sorted(bootloaders_map)}"
        )
    elif firmware and firmware not in bootloaders_map[bootloader].get("firmwares", []):
        if bootloader == "systemd-boot" and firmware == "bios":
            errors.append(
                "systemd-boot needs UEFI — this machine booted in legacy "
                "BIOS mode. Choose GRUB or reboot the installer in UEFI mode."
            )
        else:
            errors.append(
                f"{bootloader} does not support firmware: {firmware}."
            )

    edition = selection.get("edition")
    editions = catalogue.get("editions") or {}
    role = (editions.get(edition) or {}).get("role", edition)
    for capability in selection.get("capabilities") or []:
        if capability not in capabilities_map:
            errors.append(
                f"Unknown capability: {capability}. "
                f"Valid capabilities: {sorted(capabilities_map)}"
            )
            continue
        applies_to = capabilities_map[capability].get("appliesTo")
        if applies_to and role not in applies_to and edition not in applies_to:
            title = capability[:1].upper() + capability[1:]
            edition_title = (editions.get(edition) or {}).get("title", edition)
            errors.append(
                f"{title} is not available for {edition_title} — "
                f"deselect it or choose a different edition."
            )
    return errors


def nvidia_module_for(kernels: list[str], warnings: list[str]) -> str | None:
    """Per-kernel NVIDIA module rule (mirrors hornero gaming module)."""
    if len(kernels) == 1 and kernels[0] == "linux":
        return "nvidia-open"
    if len(kernels) == 1 and kernels[0] == "linux-lts":
        return "nvidia-open-lts"
    warnings.append(
        "Multiple or non-standard kernels: using nvidia-open-dkms so one "
        "module builds for every installed kernel."
    )
    return "nvidia-open-dkms"


def build_plan(catalogue: dict, selection: dict) -> dict:
    """Build the deterministic plan; raise ValueError on any conflict."""
    errors = validate_selection(catalogue, selection)
    if errors:
        raise ValueError("; ".join(errors))
    kernels_map = catalogue["kernels"]
    bootloaders_map = catalogue["bootloaders"]
    capabilities_map = catalogue.get("capabilities") or {}

    kernels = list(selection["kernels"])
    primary = selection["primaryKernel"]
    # Primary first, remaining kernels keep selection order.
    ordered_kernels = [primary] + [k for k in kernels if k != primary]

    packages: list[str] = []
    warnings: list[str] = []

    def add(package: str) -> None:
        if package not in packages:
            packages.append(package)

    for kernel in ordered_kernels:
        for package in kernels_map[kernel].get("packages", []):
            add(package)
        headers = kernels_map[kernel].get("headers")
        if headers:
            add(headers)

    bootloader = selection["bootloader"]
    bootloader_entry = bootloaders_map[bootloader]
    for package in entry_packages(catalogue, bootloader_entry):
        add(package)

    services: list[str] = []
    for capability in selection.get("capabilities") or []:
        entry = capabilities_map[capability]
        for package in entry_packages(catalogue, entry):
            add(package)
        for service in entry.get("services", []):
            if service not in services:
                services.append(service)

    if selection.get("nvidiaModule"):
        module = nvidia_module_for(ordered_kernels, warnings)
        if module:
            add(module)

    plan = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "selection": {
            "edition": selection.get("edition"),
            "compositor": selection.get("compositor"),
            "specializations": list(selection.get("specializations") or []),
            "capabilities": list(selection.get("capabilities") or []),
            "kernels": ordered_kernels,
            "primaryKernel": primary,
            "fallbackKernel": selection.get("fallbackKernel"),
            "bootloader": bootloader,
            "firmware": selection.get("firmware"),
            "encryption": selection.get("encryption", "none"),
        },
        "packages": packages,
        "services": services,
        "espRecommendedMiB": esp_recommended_mib(bootloader_entry, len(ordered_kernels)),
        "planWarnings": warnings,
    }
    return plan


def summary_text(plan: dict) -> str:
    """Human-readable deterministic summary of a plan."""
    sel = plan["selection"]
    lines = [
        f"Edition: {sel.get('edition')}",
        f"Kernels: {', '.join(sel['kernels'])} (primary: {sel['primaryKernel']}"
        + (f", fallback: {sel['fallbackKernel']}" if sel.get("fallbackKernel") else "")
        + ")",
        f"Bootloader: {sel['bootloader']} ({sel.get('firmware')})",
        f"ESP recommended: {plan['espRecommendedMiB']} MiB",
        f"Capabilities: {', '.join(sel['capabilities']) or 'none'}",
        f"Specializations: {', '.join(sel['specializations']) or 'none'}",
        f"Encryption: {sel.get('encryption', 'none')}",
    ]
    for warning in plan.get("planWarnings", []):
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)

#!/usr/bin/env python3
"""Probe PCI display devices and record GPU vendors for netinstall.

Writes /run/hornero-installer/gpu-probe.json (no secrets, so 0644 is
safe) with the vendors found among PCI display-class devices
(03xx). scripts/render-netinstall.py consumes that file at ISO build
or candidate-render time to pre-select the open-source AMD/Intel GPU
groups; NVIDIA is never pre-selected (explicit proprietary opt-in).

Fail-closed: no lspci, no display device, or an unparsable line means
an empty vendor list, never a guessed pre-selection.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_OUTPUT = Path("/run/hornero-installer/gpu-probe.json")
VENDOR_BY_ID = {"1002": "amd", "8086": "intel", "10de": "nvidia"}
VM_VENDOR_BY_ID = {
    "1af4": "qemu",
    "1b36": "qemu",
    "1234": "qemu",
    "15ad": "vmware",
    "80ee": "virtualbox",
    "1414": "hyperv",
}
VM_GUEST_PACKAGES = {
    "qemu": ["qemu-guest-agent"],
    "vmware": ["open-vm-tools"],
    "virtualbox": ["virtualbox-guest-utils"],
    "hyperv": ["hyperv"],
}
# lspci -nn line: "01:00.0 VGA compatible controller [0300]: Vendor [1002:67df] ..."
_LINE = re.compile(r"\[03[0-9a-fA-F]{2}\]:.*\[([0-9a-fA-F]{4}):[0-9a-fA-F]{4}\]")
_ANY_PCI_VENDOR = re.compile(r"\[([0-9a-fA-F]{4}):[0-9a-fA-F]{4}\]")


def parse_lspci(text: str) -> list[str]:
    vendors: list[str] = []
    for line in text.splitlines():
        match = _LINE.search(line)
        if not match:
            continue
        vendor = VENDOR_BY_ID.get(match.group(1).lower())
        if vendor and vendor not in vendors:
            vendors.append(vendor)
    return vendors


def parse_vm_hypervisors(text: str) -> list[str]:
    """Detect virtual machine hypervisors from lspci -nn output."""
    hypervisors: list[str] = []
    for line in text.splitlines():
        for match in _ANY_PCI_VENDOR.finditer(line):
            vm = VM_VENDOR_BY_ID.get(match.group(1).lower())
            if vm and vm not in hypervisors:
                hypervisors.append(vm)
    return hypervisors


def detect_cpu_vendor(cpuinfo_text: str) -> tuple[str | None, str | None]:
    """Return (cpu_vendor, microcode_package) from /proc/cpuinfo text."""
    if "AuthenticAMD" in cpuinfo_text:
        return ("amd", "amd-ucode")
    if "GenuineIntel" in cpuinfo_text:
        return ("intel", "intel-ucode")
    return (None, None)


def probe(lspci_text: str | None = None) -> dict:
    if lspci_text is None:
        try:
            lspci_text = subprocess.check_output(
                ["lspci", "-nn"], text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            lspci_text = ""
    return {"schemaVersion": 1, "vendors": parse_lspci(lspci_text)}


def probe_hardware(
    lspci_text: str | None = None,
    cpuinfo_text: str | None = None,
) -> dict:
    """Comprehensive hardware probe: GPU vendors, VM hypervisors, guest agents, CPU microcode."""
    if lspci_text is None:
        try:
            lspci_text = subprocess.check_output(
                ["lspci", "-nn"], text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            lspci_text = ""
    if cpuinfo_text is None:
        try:
            cpuinfo_text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        except OSError:
            cpuinfo_text = ""
    vendors = parse_lspci(lspci_text)
    hypervisors = parse_vm_hypervisors(lspci_text)
    guest_packages: list[str] = []
    for vm in hypervisors:
        for pkg in VM_GUEST_PACKAGES.get(vm, []):
            if pkg not in guest_packages:
                guest_packages.append(pkg)
    cpu_vendor, ucode_pkg = detect_cpu_vendor(cpuinfo_text)
    return {
        "schemaVersion": 2,
        "vendors": vendors,
        "vmHypervisors": hypervisors,
        "guestPackages": guest_packages,
        "cpuVendor": cpu_vendor,
        "microcodePackage": ucode_pkg,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--lspci-output", type=Path, help="read recorded lspci -nn output instead of running lspci")
    args = parser.parse_args()
    text = args.lspci_output.read_text(encoding="utf-8") if args.lspci_output else None
    result = probe(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"probe-gpu: vendors={result['vendors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

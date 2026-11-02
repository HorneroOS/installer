#!/usr/bin/env python3
"""Verify the installed target before Calamares may report success.

"All done" must mean the target can actually boot: a generated GRUB
configuration, a kernel image, and its initramfs must exist in the
target, a real user must have been created, the target must identify
itself, and no installer-only package repository may remain enabled.
This runs after the bootloader step and before umount; any problem
fails the installation instead of presenting a false success.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _load_plan(root: Path, plan: dict | None) -> dict | None:
    if plan is not None:
        return plan
    plan_path = root / "usr/lib/hornero/installation-plan.json"
    if plan_path.is_file():
        return json.loads(plan_path.read_text(encoding="utf-8"))
    return None


def _service_enabled(root: Path, service: str) -> bool:
    """True when `systemctl enable <service>` left its wants symlink.

    The link lands in the `.target.wants` directory named by the
    unit's own [Install] WantedBy — bluetooth.service, for example,
    enables under `bluetooth.target.wants`, not
    `multi-user.target.wants`. Accept any target's wants dir.
    """
    wants_root = root / "etc/systemd/system"
    if not wants_root.is_dir():
        return False
    return any(wants_root.glob(f"*.target.wants/{service}"))


def verify_install(root: Path, plan: dict | None = None) -> list[str]:
    problems: list[str] = []
    plan = _load_plan(root, plan)

    def require_file(rel: str, what: str) -> None:
        path = root / rel
        if not path.is_file() or path.stat().st_size == 0:
            problems.append(f"missing or empty {what}: {rel}")

    if plan is None:
        # Legacy single-kernel GRUB flow (unchanged).
        require_file("boot/grub/grub.cfg", "GRUB configuration")
        require_file("boot/vmlinuz-linux", "kernel image")
        require_file("boot/initramfs-linux.img", "initramfs")
        # Bluetooth gate (legacy/no-plan only; the plan path below
        # generalizes this via plan["services"]): enabled, not
        # mandatory — pass when bluez absent, fail only if its unit
        # exists but the enablement symlink is missing.
        if (root / "usr/lib/systemd/system/bluetooth.service").is_file():
            if not _service_enabled(root, "bluetooth.service"):
                problems.append(
                    "bluetooth.service installed but not enabled: "
                    "etc/systemd/system/*.target.wants/bluetooth.service"
                )
    else:
        selection = plan.get("selection", {})
        kernels = selection.get("kernels") or ["linux"]
        for kernel in kernels:
            require_file(f"boot/vmlinuz-{kernel}", f"kernel image ({kernel})")
            require_file(f"boot/initramfs-{kernel}.img", f"initramfs ({kernel})")
            require_file(
                f"boot/initramfs-{kernel}-fallback.img",
                f"fallback initramfs ({kernel})",
            )
        # ESP capacity: the plan's espRecommendedMiB must fit the
        # filesystem that holds /boot (the ESP on UEFI installs). A
        # too-small ESP strands kernel updates; fail before success.
        esp_recommended = plan.get("espRecommendedMiB")
        if esp_recommended:
            boot_dir = root / "boot"
            if not boot_dir.is_dir():
                problems.append("missing boot directory: boot")
                boot_total_mib = 0
            else:
                boot_total_mib = shutil.disk_usage(boot_dir).total // (1024 * 1024)
            if boot_total_mib < int(esp_recommended):
                problems.append(
                    f"boot filesystem too small for the selected kernels: "
                    f"{boot_total_mib} MiB available, plan recommends "
                    f"{esp_recommended} MiB (espRecommendedMiB)"
                )
        bootloader = selection.get("bootloader", "grub")
        if bootloader == "systemd-boot":
            require_file("boot/loader/loader.conf", "systemd-boot loader configuration")
            entries = sorted((root / "boot/loader/entries").glob("*.conf")) if (root / "boot/loader/entries").is_dir() else []
            entry_text = "\n".join(
                entry.read_text(encoding="utf-8", errors="replace") for entry in entries
            )
            for kernel in kernels:
                if not re.search(rf"vmlinuz-{re.escape(kernel)}(?![-\w])", entry_text):
                    problems.append(
                        f"no systemd-boot entry for kernel {kernel}: boot/loader/entries/*.conf"
                    )
        else:
            require_file("boot/grub/grub.cfg", "GRUB configuration")
            grub_cfg = root / "boot/grub/grub.cfg"
            if grub_cfg.is_file():
                grub_text = grub_cfg.read_text(encoding="utf-8", errors="replace")
                for kernel in kernels:
                    if not re.search(rf"vmlinuz-{re.escape(kernel)}(?![-\w])", grub_text):
                        problems.append(
                            f"GRUB configuration has no entry for kernel {kernel}: boot/grub/grub.cfg"
                        )
        # Capability services (generalizes the legacy Bluetooth gate):
        # when the plan's service unit was installed, its enablement
        # symlink must exist. Absent unit = capability not installed.
        for service in plan.get("services", []):
            if (root / f"usr/lib/systemd/system/{service}").is_file():
                if not _service_enabled(root, service):
                    problems.append(
                        f"{service} installed but not enabled: "
                        f"etc/systemd/system/*.target.wants/{service}"
                    )

    os_release = root / "etc/os-release"
    if not os_release.is_file() or "ID=" not in os_release.read_text(
        encoding="utf-8", errors="replace"
    ):
        problems.append("missing distribution identity: etc/os-release")

    passwd = root / "etc/passwd"
    has_user = False
    if passwd.is_file():
        for line in passwd.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) >= 1000:
                has_user = True
                break
    if not has_user:
        problems.append("no regular user (uid >= 1000) in etc/passwd")

    pacman_conf = root / "etc/pacman.conf"
    if pacman_conf.is_file() and "hornero-installer" in pacman_conf.read_text(
        encoding="utf-8", errors="replace"
    ):
        problems.append("installer-only repository still enabled in etc/pacman.conf")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Installed target root")
    parser.add_argument("--plan", type=Path, help="installation plan JSON (default: <root>/usr/lib/hornero/installation-plan.json if present)")
    args = parser.parse_args()
    plan = None
    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    problems = verify_install(Path(args.root), plan=plan)
    for problem in problems:
        print(f"verify-install: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("verify-install: target has GRUB config, kernel, initramfs, user, identity; no installer repo left enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Apply a validated installation plan to the target.

Reads <root>/usr/lib/hornero/installation-plan.json (written by
apply-system-plan.py). When no plan exists this job is a no-op, so
the default install is unchanged. With a plan it:

* installs the selected kernels (primary first, fallback second,
  headers only for multi-kernel) and removes unselected kernels
  with one arch-chroot pacman transaction per direction,
* enables/disables the optional services (bluetooth, timesyncd)
  by managing their wants symlinks; NetworkManager and SDDM are
  never touched,
* persists GRUB_DEFAULT=saved in /etc/default/grub (without
  GRUB_SAVEDEFAULT, so a manual boot never becomes sticky), and —
  in the late ``--set-grub-default`` run after the bootloader job
  has generated grub.cfg — calls ``grub-set-default`` with the
  first menu entry that boots the primary kernel, so the primary
  kernel is the actual default boot entry.

All external commands go through an argv-list runner; no shell
interpolation and no package list is hard-coded here beyond the
allowlist passed in.
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import sys
from pathlib import Path

import yaml

ALLOWLIST_PATH = Path(__file__).with_name("system-allowlist.yaml")
PLAN_REL = Path("usr/lib/hornero/installation-plan.json")
BOOT_CONFIRM_UNIT_REL = Path("usr/lib/systemd/system/hornero-boot-confirm.service")
BOOT_CONFIRM_WANTS_REL = Path(
    "etc/systemd/system/graphical.target.wants/hornero-boot-confirm.service"
)
BOOT_TRIAL_HOOK_REL = Path("etc/pacman.d/hooks/95-hornero-boot-trial.hook")

BOOT_CONFIRM_UNIT_CONTENT = """\
[Unit]
Description=Confirm HorneroOS boot trial as healthy
After=graphical.target
ConditionPathExists=/var/lib/hornero/boot-trial.pending

[Service]
Type=oneshot
ExecStart=/usr/bin/sh -c 'mkdir -p /var/lib/hornero && rm -f /var/lib/hornero/boot-trial.pending /var/lib/hornero/boot-trial.tries && /usr/bin/date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ > /var/lib/hornero/boot-confirmed'
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
"""

BOOT_TRIAL_HOOK_CONTENT = """\
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = usr/lib/modules/*/vmlinuz
Target = boot/initramfs-*.img

[Action]
Description = Arm HorneroOS Btrfs snapshot boot trial counter...
When = PostTransaction
Exec = /usr/bin/sh -c 'mkdir -p /var/lib/hornero && printf "3\\n" > /var/lib/hornero/boot-trial.tries && touch /var/lib/hornero/boot-trial.pending'
"""


def _run(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


def load_plan(root: Path) -> dict | None:
    path = root / PLAN_REL
    if not path.is_file():
        return None
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("installation plan must be a JSON object")
    return plan


def has_dkms_packages(root: Path) -> bool:
    """Return True if any *-dkms package is installed in the target pacman DB."""
    local_db = root / "var/lib/pacman/local"
    if not local_db.is_dir():
        return False
    return any(
        entry.is_dir() and "-dkms-" in entry.name
        for entry in local_db.iterdir()
    )


def detect_cpu_ucode(cpuinfo_path: Path = Path("/proc/cpuinfo")) -> str | None:
    """Return 'amd-ucode' or 'intel-ucode' for the host CPU, or None."""
    try:
        text = cpuinfo_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "AuthenticAMD" in text:
        return "amd-ucode"
    if "GenuineIntel" in text:
        return "intel-ucode"
    return None


def configure_zram(root: Path) -> Path:
    """Write a default zram-generator.conf in the target if absent."""
    conf = root / "etc/systemd/zram-generator.conf"
    if conf.is_symlink():
        raise ValueError(f"Refusing symlink in target zram config path: {conf}")
    if not conf.exists():
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(
            "[zram0]\nzram-size = min(ram / 2, 4096)\ncompression-algorithm = zstd\n",
            encoding="utf-8",
        )
    return conf


def configure_boot_trial_rollback(root: Path, *, enabled: bool = True) -> dict[str, str] | None:
    """Provision hornero-boot-confirm.service and 95-hornero-boot-trial.hook."""
    if not enabled:
        return None
    unit_path = root / BOOT_CONFIRM_UNIT_REL
    wants_path = root / BOOT_CONFIRM_WANTS_REL
    hook_path = root / BOOT_TRIAL_HOOK_REL

    for path in (unit_path, hook_path):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink in target boot-trial path: {path}")

    if not unit_path.exists():
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(BOOT_CONFIRM_UNIT_CONTENT, encoding="utf-8")

    if not wants_path.is_symlink() and not wants_path.exists():
        wants_path.parent.mkdir(parents=True, exist_ok=True)
        wants_path.symlink_to("/usr/lib/systemd/system/hornero-boot-confirm.service")

    if not hook_path.exists():
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(BOOT_TRIAL_HOOK_CONTENT, encoding="utf-8")

    return {
        "unit": str(BOOT_CONFIRM_UNIT_REL),
        "wants": str(BOOT_CONFIRM_WANTS_REL),
        "hook": str(BOOT_TRIAL_HOOK_REL),
    }


def install_cpu_ucode(
    root: Path,
    *,
    offline: bool = False,
    cpuinfo_path: Path = Path("/proc/cpuinfo"),
    runner=_run,
) -> str | None:
    """Install matching CPU microcode package when not offline."""
    if offline:
        return None
    ucode = detect_cpu_ucode(cpuinfo_path)
    if ucode is None:
        return None
    argv = ["arch-chroot", str(root), "pacman", "-S", "--noconfirm", "--needed", ucode]
    runner(argv)
    return ucode


def kernel_transaction(root: Path, plan: dict, allowlist: dict, runner=_run) -> list[list[str]]:
    """Pacman argv lists realising the plan kernels; [] when default without DKMS."""
    selection = plan.get("selection") or {}
    kernels = selection.get("kernels") or ["linux"]
    dkms = bool(selection.get("dkms")) or has_dkms_packages(root)
    if kernels == ["linux"] and not dkms:
        return []
    entries = allowlist["kernels"]
    wanted = []
    for kernel in kernels:
        if kernels != ["linux"]:
            wanted.append(entries[kernel]["package"])
    if len(kernels) > 1 or dkms:
        for kernel in kernels:
            if entries[kernel].get("headers"):
                wanted.append(entries[kernel]["headers"])
    commands = [["arch-chroot", str(root), "pacman", "-S", "--noconfirm", "--needed", *wanted]]
    removable = [
        entry["package"]
        for kernel_id, entry in entries.items()
        if kernel_id not in kernels
    ] + [
        entry["headers"]
        for kernel_id, entry in entries.items()
        if kernel_id not in kernels and entry.get("headers")
    ]
    # Only remove the stock kernel when it is not selected; other
    # unselected kernels were never installed by the chooser.
    if "linux" not in kernels:
        commands.append(
            ["arch-chroot", str(root), "pacman", "-R", "--noconfirm", "linux"]
        )
    for argv in commands:
        if runner(argv) != 0:
            raise RuntimeError(f"kernel transaction failed: {' '.join(argv[:4])} ...")
    assert removable is not None
    return commands


def apply_services(root: Path, plan: dict, allowlist: dict) -> list[str]:
    """Enable/disable optional services via wants symlinks."""
    changed: list[str] = []
    services = (plan.get("selection") or {}).get("services") or {}
    optional = allowlist.get("optionalServices") or {}
    for name, enabled in services.items():
        entry = optional[name]
        unit = entry["unit"]
        wants_dir = root / "etc/systemd/system" / entry["wants"]
        link = wants_dir / unit
        unit_file = root / "usr/lib/systemd/system" / unit
        if enabled:
            if unit_file.is_file() and not link.exists():
                wants_dir.mkdir(parents=True, exist_ok=True)
                link.symlink_to(f"/usr/lib/systemd/system/{unit}")
                changed.append(f"enabled {unit}")
        else:
            if link.is_symlink() or link.exists():
                link.unlink()
                changed.append(f"disabled {unit}")
    return changed


def apply_grub_default(root: Path, plan: dict) -> bool:
    """Persist GRUB_DEFAULT=saved; False when there is nothing to do."""
    selection = plan.get("selection") or {}
    if selection.get("bootloader") == "systemd-boot":
        return False  # No GRUB config to persist; bootctl owns the default.
    if (selection.get("kernels") or ["linux"]) == ["linux"]:
        return False
    grub_path = root / "etc/default/grub"
    if not grub_path.is_file() or grub_path.is_symlink():
        return False
    lines = grub_path.read_text(encoding="utf-8").splitlines()
    output, seen = [], False
    for line in lines:
        if line.startswith("GRUB_DEFAULT="):
            output.append("GRUB_DEFAULT=saved")
            seen = True
        elif line.startswith("GRUB_SAVEDEFAULT="):
            # Never sticky: a manual boot must not rewrite the default.
            output.append("GRUB_SAVEDEFAULT=false")
        else:
            output.append(line)
    if not seen:
        output.append("GRUB_DEFAULT=saved")
    if not any(line.startswith("GRUB_SAVEDEFAULT=") for line in output):
        output.append("GRUB_SAVEDEFAULT=false")
    grub_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return True


def find_primary_entry(grub_text: str, primary_package: str) -> str | None:
    """First menuentry title whose body boots *primary_package*."""
    matches = list(re.finditer(r"menuentry\s+['\"]([^'\"]+)['\"]", grub_text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(grub_text)
        body = grub_text[match.start():end]
        if re.search(rf"vmlinuz-{re.escape(primary_package)}(?![-\w])", body):
            return match.group(1)
    return None


def apply_grub_saved_entry(root: Path, plan: dict, allowlist: dict, runner=_run) -> bool:
    """grub-set-default to the primary kernel entry; False for default."""
    selection = plan.get("selection") or {}
    if selection.get("bootloader") == "systemd-boot":
        return False  # kernel-install/bootctl set entries; no grub.cfg.
    kernels = selection.get("kernels") or ["linux"]
    if kernels == ["linux"]:
        return False
    primary = selection.get("primaryKernel") or kernels[0]
    package = allowlist["kernels"][primary]["package"]
    grub_cfg = root / "boot/grub/grub.cfg"
    if not grub_cfg.is_file():
        raise RuntimeError("grub.cfg missing when setting the default kernel entry")
    entry = find_primary_entry(grub_cfg.read_text(encoding="utf-8", errors="replace"), package)
    if entry is None:
        raise RuntimeError(f"no GRUB entry boots the primary kernel {package}")
    argv = ["arch-chroot", str(root), "grub-set-default", entry]
    if runner(argv) != 0:
        raise RuntimeError("grub-set-default failed for the primary kernel entry")
    return True


def apply_system_choices(
    root: Path,
    allowlist: dict,
    runner=_run,
    *,
    offline: bool | None = None,
    cpuinfo_path: Path = Path("/proc/cpuinfo"),
) -> dict | None:
    root = root.resolve()
    if offline is None:
        offline = Path("/run/hornero-installer/offline-mode").is_file()
    plan = load_plan(root)
    if plan is None:
        if has_dkms_packages(root):
            default_plan = {"selection": {"kernels": ["linux"], "dkms": True}}
            kernel_transaction(root, default_plan, allowlist, runner=runner)
        configure_zram(root)
        if (root / "etc/snapper/configs/root").is_file():
            configure_boot_trial_rollback(root, enabled=True)
        return None
    for component in (root / "etc/default/grub",):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Refusing symlink in target GRUB config path: {component}")
    kernel_transaction(root, plan, allowlist, runner=runner)
    services = apply_services(root, plan, allowlist)
    grub = apply_grub_default(root, plan)
    configure_zram(root)
    snapshots_enabled = (plan.get("selection") or {}).get("snapshots", True) is not False
    boot_trial = configure_boot_trial_rollback(root, enabled=snapshots_enabled)
    ucode = install_cpu_ucode(root, offline=offline, cpuinfo_path=cpuinfo_path, runner=runner)
    return {
        "services": services,
        "grubDefaultSaved": grub,
        "ucode": ucode,
        "bootTrial": boot_trial,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="installed target root")
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_PATH)
    parser.add_argument("--set-grub-default", action="store_true",
                        help="late run after bootloader: grub-set-default to the primary kernel")
    args = parser.parse_args()
    allowlist = yaml.safe_load(args.allowlist.read_text(encoding="utf-8"))
    if args.set_grub_default:
        try:
            root = args.root.resolve()
            plan = load_plan(root)
            if plan is None:
                print("apply-system-choices: no installation plan; keeping defaults")
                return 0
            applied = apply_grub_saved_entry(root, plan, allowlist)
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            print(f"apply-system-choices: {error}", file=sys.stderr)
            return 1
        print(f"apply-system-choices: grub default set to primary kernel: {applied}")
        return 0
    try:
        result = apply_system_choices(args.root, allowlist)
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"apply-system-choices: {error}", file=sys.stderr)
        return 1
    if result is None:
        print("apply-system-choices: no installation plan; keeping defaults")
    else:
        print(f"apply-system-choices: applied services={result['services']} grubSaved={result['grubDefaultSaved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

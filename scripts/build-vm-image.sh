#!/usr/bin/env bash
# Deterministic, preinstalled HorneroOS QCOW2 VM image builder.
#
# Follows the Arch `arch-boxes` / `arch-install-scripts` (`pacstrap`) pattern:
# builds a fresh GPT + UEFI systemd-boot disk image directly from pinned
# `installer.lock.yaml` snapshots and `HorneroOS/hornero` `editions/catalogue.yaml`.
# Never clones the running host machine.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LOCK_FILE="$ROOT/installer.lock.yaml"

usage() {
  cat <<'EOF'
Usage: build-vm-image.sh [OPTIONS]

Build a deterministic, preinstalled HorneroOS QCOW2 VM image from
installer.lock.yaml and HorneroOS/hornero editions/catalogue.yaml.

Options:
  --edition EDITION       Edition to build: desktop | studio | gaming (default: desktop)
  --compositor COMP       Wayland compositor: hyprland | niri (default: hyprland)
  --demo                  Enable Playground demo overlay (hornero autologin, idle-lock disabled, Workspace seed)
  --disk-size SIZE        Virtual disk size, e.g. 24G or 32G (default: 24G)
  --output-dir DIR        Output directory for image + .sha256 + .manifest.json (default: <repo>/output)
  --hornero-dir DIR       Path to HorneroOS/hornero checkout (default: auto-detect sibling repo)
  --lock FILE             Path to installer.lock.yaml (default: <repo>/installer.lock.yaml)
  --version VERSION       Artifact version label (default: derived from installer.lock.yaml snapshot)
  --no-compress           Emit uncompressed .qcow2 instead of .qcow2.zst
  --dry-run               Print deterministic JSON build plan and package list without root or disk writes
  -h, --help              Show this help message and exit
EOF
}

edition="desktop"
compositor="hyprland"
demo_mode=0
disk_size="24G"
output_dir="$ROOT/output"
hornero_dir=""
version=""
no_compress=0
dry_run=0

while (($#)); do
  case "$1" in
    --edition)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --edition requires a value" >&2; exit 2; }
      edition=$2
      shift 2
      ;;
    --compositor)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --compositor requires a value" >&2; exit 2; }
      compositor=$2
      shift 2
      ;;
    --demo)
      demo_mode=1
      shift
      ;;
    --disk-size)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --disk-size requires a value" >&2; exit 2; }
      disk_size=$2
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --output-dir requires a directory" >&2; exit 2; }
      output_dir=$2
      shift 2
      ;;
    --hornero-dir)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --hornero-dir requires a directory" >&2; exit 2; }
      hornero_dir=$2
      shift 2
      ;;
    --lock)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --lock requires a file" >&2; exit 2; }
      LOCK_FILE=$2
      shift 2
      ;;
    --version)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "build-vm-image: --version requires a value" >&2; exit 2; }
      version=$2
      shift 2
      ;;
    --no-compress)
      no_compress=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'build-vm-image: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$edition" in
  desktop|studio|gaming) ;;
  *)
    printf "build-vm-image: invalid edition '%s' (expected desktop, studio, or gaming)\n" "$edition" >&2
    exit 2
    ;;
esac

case "$compositor" in
  hyprland|niri) ;;
  *)
    printf "build-vm-image: invalid compositor '%s' (expected hyprland or niri)\n" "$compositor" >&2
    exit 2
    ;;
esac

if [[ ! "$disk_size" =~ ^[1-9][0-9]*[GM]$ ]]; then
  printf "build-vm-image: invalid --disk-size '%s' (expected e.g. 24G or 24576M)\n" "$disk_size" >&2
  exit 2
fi

if [[ -n "$version" && ! "$version" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf "build-vm-image: invalid --version '%s'\n" "$version" >&2
  exit 2
fi

[[ -f "$LOCK_FILE" ]] || { echo "build-vm-image: missing installer.lock.yaml at $LOCK_FILE" >&2; exit 1; }

if [[ "${HORNEROS_ALLOW_PRE_SIGNAL_LOCK:-0}" != 1 ]]; then
  python3 "$ROOT/scripts/check-signal-lock.py" --lock "$LOCK_FILE" >/dev/null || {
    echo "build-vm-image: refusing to build from a pre-Signal lock (set HORNEROS_ALLOW_PRE_SIGNAL_LOCK=1 to override)." >&2
    exit 1
  }
fi

resolve_hornero_dir() {
  if [[ -n "$hornero_dir" ]]; then
    if [[ ! -f "$hornero_dir/editions/catalogue.yaml" ]]; then
      printf 'build-vm-image: editions/catalogue.yaml not found under --hornero-dir %s\n' "$hornero_dir" >&2
      exit 1
    fi
    realpath -m -- "$hornero_dir"
    return 0
  fi

  local -a candidates=()
  if [[ -n "${HORNEROS_PRODUCT_SOURCE:-}" ]]; then
    candidates+=("$HORNEROS_PRODUCT_SOURCE")
  fi
  candidates+=(
    "$ROOT/../hornero"
    "$ROOT/../github.com/HorneroOS/hornero"
  )
  local git_common_dir
  git_common_dir=$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)
  if [[ -n "$git_common_dir" ]]; then
    local abs_common
    abs_common=$(realpath -m -- "$git_common_dir")
    candidates+=("$(dirname -- "$(dirname -- "$abs_common")")/hornero")
  fi

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate/editions/catalogue.yaml" ]]; then
      realpath -m -- "$candidate"
      return 0
    fi
  done

  echo "build-vm-image: could not locate HorneroOS/hornero editions/catalogue.yaml; pass --hornero-dir DIR" >&2
  exit 1
}

hornero_dir=$(resolve_hornero_dir)
output_dir=$(realpath -m -- "$output_dir")

plan_json=$(
  python3 - "$LOCK_FILE" "$hornero_dir" "$edition" "$compositor" "$demo_mode" "$disk_size" "$output_dir" "$version" "$no_compress" "$dry_run" <<'PY'
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import yaml

(
    lock_path_str,
    hornero_dir_str,
    edition,
    compositor,
    demo_mode_str,
    disk_size,
    output_dir,
    version_override,
    no_compress_str,
    dry_run_str,
) = sys.argv[1:11]

lock_path = Path(lock_path_str)
hornero_dir = Path(hornero_dir_str)
catalogue_path = hornero_dir / "editions" / "catalogue.yaml"

lock_bytes = lock_path.read_bytes()
lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
lock_doc = yaml.safe_load(lock_bytes.decode("utf-8"))

catalogue_bytes = catalogue_path.read_bytes()
catalogue_sha256 = hashlib.sha256(catalogue_bytes).hexdigest()
catalogue_doc = yaml.safe_load(catalogue_bytes.decode("utf-8"))


def resolve_packages_fallback(doc: dict, ed_name: str, comp_name: str) -> list[str]:
    editions = doc["editions"]
    sets = doc["packageSets"]
    compositors = doc["compositors"]
    chain: list[dict] = []
    cur = editions[ed_name]
    seen: set[str] = set()
    while True:
        cur_name = next((n for n, v in editions.items() if v is cur), None)
        if cur_name is None or cur_name in seen:
            raise ValueError(f"invalid inheritance chain for {ed_name!r}")
        seen.add(cur_name)
        chain.append(cur)
        parent = cur.get("extends")
        if parent is None:
            break
        cur = editions[parent]
    set_names = ["base"]
    for layer in reversed(chain):
        set_names.extend(layer["packageSets"])
    set_names.append(compositors[comp_name]["packageSet"])
    pkgs: list[str] = []
    for set_name in set_names:
        pkg_set = {"packages": doc["base"]["packages"]} if set_name == "base" else sets[set_name]
        for pkg in pkg_set["packages"]:
            if pkg not in pkgs:
                pkgs.append(pkg)
    for cap in (doc.get("capabilities") or {}).values():
        if not isinstance(cap, dict):
            continue
        if ed_name not in cap.get("appliesTo", []):
            continue
        if (cap.get("defaultByEdition") or {}).get(ed_name) is not True:
            continue
        for pkg in cap.get("packages") or []:
            if pkg not in pkgs:
                pkgs.append(pkg)
    return pkgs


resolver_script = hornero_dir / "scripts" / "resolve-edition.py"
if resolver_script.is_file():
    spec = importlib.util.spec_from_file_location("hornero_resolve_edition", resolver_script)
    assert spec and spec.loader
    resolver_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver_mod)
    resolved = resolver_mod.resolve_edition(catalogue_doc, edition, compositor)
    packages = list(resolved["packages"])
else:
    packages = resolve_packages_fallback(catalogue_doc, edition, compositor)

# Ensure QEMU guest agent and Python (for runtime/identity helpers) are present.
for vm_pkg in ("python", "qemu-guest-agent"):
    if vm_pkg not in packages:
        packages.append(vm_pkg)

arch = str(lock_doc["arch"]["architecture"])
snapshot = str(lock_doc["arch"]["snapshot"])
parts = snapshot.split("/")
derived_version = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else snapshot.replace("/", ".")
effective_version = version_override or derived_version

demo_mode = demo_mode_str == "1"
compress = no_compress_str != "1"
dry_run = dry_run_str == "1"

qcow2_name = f"horneroos-{effective_version}-{edition}-qemu-{arch}.qcow2"
artifact_name = f"{qcow2_name}.zst" if compress else qcow2_name

build_args = [
    "--edition", edition,
    "--compositor", compositor,
    "--disk-size", disk_size,
    "--output-dir", output_dir,
    "--version", effective_version,
]
if demo_mode:
    build_args.append("--demo")
if not compress:
    build_args.append("--no-compress")

hooks = ["hornero-vm-gpu-detect"]
if demo_mode:
    hooks.append("hornero-playground-demo")

plan = {
    "schema": "hornero.vm.image/1",
    "edition": edition,
    "compositor": compositor,
    "version": effective_version,
    "arch": arch,
    "arch_snapshot": snapshot,
    "product_revision": lock_doc["product"]["revision"],
    "lock_sha256": lock_sha256,
    "catalogue_sha256": catalogue_sha256,
    "demo_mode": demo_mode,
    "virtual_gpu_profile": "auto-detect (systemd-detect-virt: virgl/llvmpipe/vmware/oracle)",
    "disk_size": disk_size,
    "disk_layout": {
        "partition_table": "gpt",
        "esp": {"size": "512M", "filesystem": "fat32", "mount": "/boot"},
        "root": {"size": "rest", "filesystem": "ext4", "mount": "/"},
        "bootloader": "systemd-boot",
    },
    "compress": compress,
    "artifact": artifact_name,
    "qcow2_artifact": qcow2_name,
    "checksum_file": f"{artifact_name}.sha256",
    "manifest_file": f"{artifact_name}.manifest.json",
    "output_dir": output_dir,
    "build_args": build_args,
    "hooks": hooks,
    "packages": packages,
    "packages_count": len(packages),
    "dry_run": dry_run,
}
print(json.dumps(plan, indent=2))
PY
)

if [[ "$dry_run" == 1 ]]; then
  printf '%s\n' "$plan_json"
  exit 0
fi

# Real image build (never clones host machine; requires root and Arch tools).
[[ $(id -u) -eq 0 ]] || {
  echo "build-vm-image: root privileges are required for loop-mounting and pacstrap (use --dry-run for unprivileged plan inspection)." >&2
  exit 1
}

required_tools=(
  truncate sfdisk losetup mkfs.fat mkfs.ext4 blkid
  pacstrap genfstab arch-chroot bootctl qemu-img sha256sum python3
)
if [[ "$no_compress" == 0 ]]; then
  required_tools+=(zstd)
fi
for tool in "${required_tools[@]}"; do
  command -v "$tool" >/dev/null || {
    printf 'build-vm-image: missing required build tool: %s\n' "$tool" >&2
    exit 1
  }
done

mkdir -p "$output_dir"
work_dir=$(mktemp -d -t hornero-vm-build-XXXXXX)
mnt="$work_dir/mnt"
loop_dev=""

cleanup() {
  local rc=$?
  if mountpoint -q "$mnt/boot" 2>/dev/null; then
    umount "$mnt/boot" || true
  fi
  if mountpoint -q "$mnt" 2>/dev/null; then
    umount "$mnt" || true
  fi
  if [[ -n "$loop_dev" ]]; then
    losetup -d "$loop_dev" 2>/dev/null || true
  fi
  rm -rf "$work_dir"
  exit "$rc"
}
trap cleanup EXIT

mapfile -t meta < <(
  python3 -c '
import json, sys
plan = json.loads(sys.argv[1])
print(plan["arch_snapshot"])
print(plan["qcow2_artifact"])
print(plan["artifact"])
' "$plan_json"
)
snapshot="${meta[0]}"
qcow2_name="${meta[1]}"
artifact_name="${meta[2]}"

mapfile -t packages < <(
  python3 -c '
import json, sys
for pkg in json.loads(sys.argv[1])["packages"]:
    print(pkg)
' "$plan_json"
)

base_pacman_conf="$work_dir/pacman-base.conf"
cat > "$base_pacman_conf" <<EOF
[options]
HoldPkg = pacman glibc
Architecture = auto
Color
CheckSpace
ParallelDownloads = 5
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch

[extra]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch

[multilib]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch
EOF

repo_dir="${HORNEROS_INSTALLER_REPO:-}"
if [[ -z "$repo_dir" ]]; then
  repo_dir="$work_dir/local-repo"
  export HORNEROS_INSTALLER_DISPOSABLE=1
  export HORNEROS_PRODUCT_SOURCE="$hornero_dir"
  export PACMAN_CONF="$base_pacman_conf"
  bash "$ROOT/scripts/build-package-repository.sh" \
    --work "$work_dir/package-work" \
    --repository "$repo_dir"
fi

target_pacman_conf="$work_dir/pacman-target.conf"
cat > "$target_pacman_conf" <<EOF
[options]
HoldPkg = pacman glibc
Architecture = auto
Color
CheckSpace
ParallelDownloads = 5
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[hornero-installer]
SigLevel = Optional TrustAll
Server = file://$repo_dir

[core]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch

[extra]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch

[multilib]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch
EOF

raw_img="$work_dir/disk.raw"
truncate -s "$disk_size" "$raw_img"
sfdisk --quiet "$raw_img" <<'SFDISK'
label: gpt
size=512M, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="HORNERO_ESP"
type=4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709, name="HORNERO_ROOT"
SFDISK

loop_dev=$(losetup --find --show --partscan "$raw_img")
esp_part="${loop_dev}p1"
root_part="${loop_dev}p2"

mkfs.fat -F32 -n HORNERO_ESP "$esp_part" >/dev/null
mkfs.ext4 -F -L HORNERO_ROOT "$root_part" >/dev/null

mkdir -p "$mnt"
mount "$root_part" "$mnt"
mkdir -p "$mnt/boot"
mount "$esp_part" "$mnt/boot"

pacstrap -C "$target_pacman_conf" -c -M "$mnt" "${packages[@]}"
genfstab -U "$mnt" >> "$mnt/etc/fstab"

python3 "$ROOT/image/calamares/configure-os-identity.py" --root "$mnt"

if [[ "$demo_mode" == 1 ]]; then
  printf 'hornero-playground\n' > "$mnt/etc/hostname"
else
  printf 'horneroos\n' > "$mnt/etc/hostname"
fi

printf 'en_US.UTF-8 UTF-8\n' > "$mnt/etc/locale.gen"
printf 'LANG=en_US.UTF-8\n' > "$mnt/etc/locale.conf"
arch-chroot "$mnt" locale-gen
ln -sf /usr/share/zoneinfo/UTC "$mnt/etc/localtime"

# Install UEFI systemd-boot (deterministic bootloader layout without modifying host NVRAM).
bootctl --esp-path="$mnt/boot" install --no-variables
root_uuid=$(blkid -s UUID -o value "$root_part")
cat > "$mnt/boot/loader/loader.conf" <<'EOF'
default horneroos.conf
timeout 3
console-mode keep
editor no
EOF
cat > "$mnt/boot/loader/entries/horneroos.conf" <<EOF
title   HorneroOS ($edition)
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=UUID=$root_uuid rw quiet
EOF

# Install virtual-GPU environment auto-detector (hardware-neutral on bare metal).
install -Dm755 "$ROOT/image/vm/hornero-vm-gpu-detect.sh" \
  "$mnt/usr/local/bin/hornero-vm-gpu-detect"
install -d "$mnt/etc/systemd/user-environment-generators"
ln -sf /usr/local/bin/hornero-vm-gpu-detect \
  "$mnt/etc/systemd/user-environment-generators/60-hornero-vm-gpu-detect"

# Provision VM user `hornero` and enable core VM services.
arch-chroot "$mnt" useradd -m -G wheel,video,audio,input,storage -s /bin/bash hornero
printf 'hornero:hornero\n' | arch-chroot "$mnt" chpasswd
install -d -m 750 "$mnt/etc/sudoers.d"
printf '%%wheel ALL=(ALL:ALL) NOPASSWD: ALL\n' > "$mnt/etc/sudoers.d/10-hornero-vm-wheel"
chmod 440 "$mnt/etc/sudoers.d/10-hornero-vm-wheel"

arch-chroot "$mnt" systemctl enable NetworkManager.service sddm.service systemd-timesyncd.service qemu-guest-agent.service

session_desktop="${compositor}.desktop"
if [[ "$demo_mode" == 1 ]]; then
  install -d "$mnt/etc/sddm.conf.d"
  cat > "$mnt/etc/sddm.conf.d/10-hornero-demo.conf" <<EOF
[Autologin]
User=hornero
Session=$session_desktop
Relogin=false
EOF

  install -d "$mnt/etc/systemd/logind.conf.d"
  cat > "$mnt/etc/systemd/logind.conf.d/10-hornero-demo.conf" <<'EOF'
[Login]
IdleAction=ignore
HandleLidSwitch=ignore
EOF

  # Disable idle lock in Hornero Shell & hypridle for demo sessions.
  install -d -m 755 "$mnt/home/hornero/.config/hornero" "$mnt/home/hornero/.config/hypr"
  cat > "$mnt/home/hornero/.config/hornero/shell.json" <<'JSON'
{
  "general": {
    "idle": {
      "lockBeforeSleep": false,
      "inhibitWhenAudio": false,
      "timeouts": [
        { "timeout": 180, "idleAction": "lock", "enabled": false },
        { "timeout": 300, "idleAction": "dpms off", "returnAction": "dpms on", "enabled": false },
        { "timeout": 600, "idleAction": ["systemctl", "suspend-then-hibernate"], "enabled": false }
      ]
    }
  }
}
JSON
  cat > "$mnt/home/hornero/.config/hypr/hypridle.conf" <<'CONF'
# HorneroOS Playground demo VM: idle listeners disabled.
CONF

  if [[ -f "$ROOT/image/archiso/airootfs/usr/local/bin/hornero-live-demo-prep" ]]; then
    install -Dm755 "$ROOT/image/archiso/airootfs/usr/local/bin/hornero-live-demo-prep" \
      "$mnt/usr/local/bin/hornero-live-demo-prep"
    python3 "$mnt/usr/local/bin/hornero-live-demo-prep" --home "$mnt/home/hornero"
  fi
  arch-chroot "$mnt" chown -R hornero:hornero /home/hornero
else
  install -d "$mnt/var/lib/sddm"
  cat > "$mnt/var/lib/sddm/state.conf" <<EOF
[Last]
Session=/usr/share/wayland-sessions/$session_desktop
User=hornero
EOF
fi

umount "$mnt/boot"
umount "$mnt"
losetup -d "$loop_dev"
loop_dev=""

qcow2_path="$output_dir/$qcow2_name"
artifact_path="$output_dir/$artifact_name"
qemu-img convert -c -O qcow2 "$raw_img" "$qcow2_path"

if [[ "$no_compress" == 0 ]]; then
  zstd -T"${VJOBS:-2}" -19 --rm "$qcow2_path" -o "$artifact_path"
fi

(cd "$output_dir" && sha256sum "$artifact_name" > "$artifact_name.sha256")

python3 -c '
import hashlib
import json
import sys
from pathlib import Path

plan = json.loads(sys.argv[1])
artifact = Path(sys.argv[2])
manifest_path = Path(sys.argv[3])
plan["dry_run"] = False

hasher = hashlib.sha256()
with artifact.open("rb") as handle:
    for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
        hasher.update(chunk)

plan["artifact_sha256"] = hasher.hexdigest()
plan["artifact_bytes"] = artifact.stat().st_size
manifest_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
' "$plan_json" "$artifact_path" "$output_dir/$artifact_name.manifest.json"

printf 'Built HorneroOS VM image: %s\n' "$artifact_path"

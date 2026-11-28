#!/usr/bin/env bash
# Detect virtualized environments via systemd-detect-virt and configure
# Wayland / Qt6 / Aquamarine virtual-GPU environment variables.
#
# Can be:
#   1. Executed as a systemd user environment.d generator (emits KEY=VALUE).
#   2. Executed with --export (emits `export KEY=VALUE` for shell eval).
#   3. Sourced directly (`source hornero-vm-gpu-detect.sh`) to export into
#      the current shell without printing to stdout.
#
# Bare metal (`none`) emits and exports nothing (strictly hardware-neutral).

_hornero_vm_gpu_detect_usage() {
  cat >&2 <<'EOF'
Usage: hornero-vm-gpu-detect.sh [--detect VIRT] [--dri-dir DIR] [--export] [--help]

Options:
  --detect VIRT   Override systemd-detect-virt output (e.g. none, kvm, qemu, vmware, oracle)
  --dri-dir DIR   Override DRM device directory (default: /dev/dri)
  --export        Emit `export KEY=VALUE` lines instead of KEY=VALUE
  -h, --help      Show this help message and exit
EOF
}

_hornero_vm_gpu_detect_main() {
  local sourced=0
  if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    sourced=1
  fi

  local detect_override=""
  local dri_dir="/dev/dri"
  local emit_export=0

  while (($#)); do
    case "$1" in
      --detect)
        if (($# < 2)) || [[ -z "${2:-}" ]]; then
          printf 'hornero-vm-gpu-detect: --detect requires a value\n' >&2
          return 2
        fi
        detect_override=$2
        shift 2
        ;;
      --dri-dir)
        if (($# < 2)) || [[ -z "${2:-}" ]]; then
          printf 'hornero-vm-gpu-detect: --dri-dir requires a directory\n' >&2
          return 2
        fi
        dri_dir=$2
        shift 2
        ;;
      --export)
        emit_export=1
        shift
        ;;
      -h|--help)
        _hornero_vm_gpu_detect_usage
        return 0
        ;;
      *)
        printf 'hornero-vm-gpu-detect: unknown option: %s\n' "$1" >&2
        _hornero_vm_gpu_detect_usage
        return 2
        ;;
    esac
  done

  local virt="$detect_override"
  if [[ -z "$virt" ]]; then
    if command -v systemd-detect-virt >/dev/null 2>&1; then
      virt=$(systemd-detect-virt 2>/dev/null || true)
    fi
    virt=${virt:-none}
  fi

  local -a vars=()
  local has_3d=0
  if [[ -d "$dri_dir" ]] && compgen -G "$dri_dir/renderD*" >/dev/null; then
    has_3d=1
  fi

  case "$virt" in
    kvm|qemu)
      if [[ "$has_3d" -eq 1 ]]; then
        # VirGL / Venus 3D render node present.
        vars=(
          "AQ_NO_MODIFIERS=1"
          "QSG_RHI_BACKEND=opengl"
          "LIBVA_DRIVER_NAME=virtio_gpu"
        )
      else
        # No 3D render node: fall back to Mesa llvmpipe + Qt software backend.
        vars=(
          "AQ_NO_MODIFIERS=1"
          "LIBGL_ALWAYS_SOFTWARE=1"
          "GALLIUM_DRIVER=llvmpipe"
          "QT_QUICK_BACKEND=software"
        )
      fi
      ;;
    vmware)
      # vmwgfx (SVGA3D): prefer OpenGL RHI; if Quickshell hits EGL/dmabuf
      # black screens on older VMware hosts, fall back to QSG_RHI_BACKEND=software.
      vars=(
        "QSG_RHI_BACKEND=opengl"
      )
      ;;
    oracle)
      # VirtualBox VMSVGA 3D acceleration breaks Hyprland/Niri; force llvmpipe
      # and software Qt Quick + software cursor.
      vars=(
        "LIBGL_ALWAYS_SOFTWARE=1"
        "GALLIUM_DRIVER=llvmpipe"
        "QT_QUICK_BACKEND=software"
        "WLR_NO_HARDWARE_CURSORS=1"
      )
      ;;
    none|*)
      # Bare metal (or non-VM container): remain strictly hardware-neutral.
      return 0
      ;;
  esac

  local entry
  for entry in "${vars[@]}"; do
    if [[ "$sourced" -eq 1 ]]; then
      export "${entry?}"
    elif [[ "$emit_export" -eq 1 ]]; then
      printf 'export %s\n' "$entry"
    else
      printf '%s\n' "$entry"
    fi
  done
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  _hornero_vm_gpu_detect_main "$@"
else
  _hornero_vm_gpu_detect_main "$@"
fi

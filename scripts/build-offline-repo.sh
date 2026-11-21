#!/usr/bin/env bash
# Download the full dependency closure of the given packages from the
# pinned Arch snapshot into a new pacman repository (hornero-offline)
# with a sha256 manifest. Runs inside the disposable build VM as part
# of build-iso.sh --offline; never on the host installation.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
usage() { printf 'Usage: %s --pacman-conf CONF --packages FILE --snapshot YYYY/MM/DD --output NEW_DIRECTORY\n' "$0" >&2; }
pacman_conf=""
packages_file=""
snapshot=""
output=""
while (($#)); do
  case "$1" in
    --pacman-conf) pacman_conf=${2:?}; shift 2 ;;
    --packages) packages_file=${2:?}; shift 2 ;;
    --snapshot) snapshot=${2:?}; shift 2 ;;
    --output) output=${2:?}; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ -n "$pacman_conf" && -n "$packages_file" && -n "$snapshot" && -n "$output" ]] || { usage; exit 2; }
[[ ! -e "$output" && ! -L "$output" ]] || { echo "Refusing to reuse output directory: $output" >&2; exit 1; }
for tool in pacman repo-add python3; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
mapfile -t packages < "$packages_file"
((${#packages[@]})) || { echo 'Offline package list is empty.' >&2; exit 1; }

mkdir -p "$output"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/db"
# -w downloads without installing; the throwaway dbpath keeps the
# build host's pacman state untouched.
pacman --config "$pacman_conf" --dbpath "$tmp/db" --cachedir "$output" \
  -Syw --noconfirm "${packages[@]}"
mapfile -t artifacts < <(find "$output" -maxdepth 1 -type f \( -name '*.pkg.tar.zst' -o -name '*.pkg.tar.xz' -o -name '*.pkg.tar.gz' \) -print | sort)
((${#artifacts[@]})) || { echo 'pacman downloaded no packages for the offline repository.' >&2; exit 1; }
repo-add "$output/hornero-offline.db.tar.gz" "${artifacts[@]}"
python3 "$ROOT/scripts/offline-repo.py" manifest --repo-dir "$output" --snapshot "$snapshot"
python3 "$ROOT/scripts/offline-repo.py" verify --repo-dir "$output"
printf 'Offline repository size: %s (%s packages)\n' "$(du -sh "$output" | cut -f1)" "${#artifacts[@]}"

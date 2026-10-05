#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s --work NEW_EMPTY_DIRECTORY --repository NEW_DIRECTORY\n' "$0" >&2
}

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=""
repository=""
while (($#)); do
  case "$1" in
    --work) work=${2:?}; shift 2 ;;
    --repository) repository=${2:?}; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ -n "$work" && -n "$repository" ]] || { usage; exit 2; }
product_source=${HORNEROS_PRODUCT_SOURCE:-}
[[ -n "$product_source" && -d "$product_source" ]] || {
  echo 'Set HORNEROS_PRODUCT_SOURCE to the locked HorneroOS product checkout.' >&2
  exit 1
}
[[ "${HORNEROS_INSTALLER_DISPOSABLE:-}" == 1 ]] || { echo 'Set HORNEROS_INSTALLER_DISPOSABLE=1 only inside a disposable Arch VM or builder.' >&2; exit 1; }
[[ $(systemd-detect-virt --vm 2>/dev/null) != none ]] || { echo 'Refusing to build AUR recipes on bare metal.' >&2; exit 1; }
[[ $(id -u) -eq 0 ]] || { echo 'Run the isolated package builder as root inside the disposable VM.' >&2; exit 1; }
jobs=${VJOBS:-2}
pacman_conf=${PACMAN_CONF:-/etc/pacman.conf}
[[ "$jobs" =~ ^[1-2]$ ]] || { echo 'VJOBS must be 1 or 2.' >&2; exit 1; }
[[ ! -e "$repository" && ! -L "$repository" ]] || { echo "Repository output already exists: $repository" >&2; exit 1; }
[[ ! -L "$work" ]] || { echo "Work path cannot be a symlink: $work" >&2; exit 1; }
mkdir -p "$work"
[[ -z "$(find "$work" -mindepth 1 -maxdepth 1 -print -quit)" ]] || { echo "Work directory must be empty: $work" >&2; exit 1; }
mkdir -p "$repository"
getent passwd builder >/dev/null || useradd --create-home --shell /bin/bash builder
chown builder:builder "$work"
repo_db="$repository/hornero-installer.db.tar.gz"
base_pacman_conf="$pacman_conf"
dependency_pacman_conf="$pacman_conf"
aur_repository=$(python3 - "$ROOT/installer.lock.yaml" <<'PY'
import sys
import yaml
print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["aur"]["repository"].rstrip("/"))
PY
)

while IFS=$'\t' read -r pkgname revision expected_version; do
  [[ -n "$pkgname" ]] || continue
  source_dir="$work/$pkgname"
  git clone --quiet --no-checkout "$aur_repository/${pkgname}.git" "$source_dir"
  git -C "$source_dir" checkout --quiet --detach "$revision"
  actual_revision=$(git -C "$source_dir" rev-parse HEAD)
  [[ "$actual_revision" == "$revision" ]] || { echo "AUR revision mismatch: $pkgname" >&2; exit 1; }
  chown -R builder:builder "$source_dir"
  srcinfo=$(runuser -u builder -- makepkg --printsrcinfo --dir "$source_dir")
  actual_version=$(printf '%s\n' "$srcinfo" | awk '$1 == "pkgver" { version = $3 } $1 == "pkgrel" { release = $3 } END { print version "-" release }')
  [[ "$actual_version" == "$expected_version" ]] || {
    printf 'Pinned AUR recipe %s declares %s, expected %s. Refresh the lock intentionally.\n' "$pkgname" "$actual_version" "$expected_version" >&2
    exit 1
  }
  mapfile -t build_dependencies < <(printf '%s\n' "$srcinfo" | awk '$1 == "depends" || $1 == "makedepends" || $1 == "checkdepends" || $1 == "depends_x86_64" || $1 == "makedepends_x86_64" || $1 == "checkdepends_x86_64" { dependency = $3; sub(/[<>=].*/, "", dependency); print dependency }' | sort -u)
  if ((${#build_dependencies[@]})); then
    # Refresh the generated package index before resolving a later pinned
    # recipe against dependencies produced by earlier recipes in the lock.
    if [[ -f "$repo_db" ]]; then pacman --config "$pacman_conf" -Sy --noconfirm; fi
    pacman --config "$pacman_conf" -S --needed --noconfirm "${build_dependencies[@]}"
  fi
  runuser -u builder -- env VJOBS="$jobs" MAKEFLAGS="-j$jobs" makepkg --nodeps --noconfirm --force --cleanbuild --dir "$source_dir"
  mapfile -t artifacts < <(find "$source_dir" -maxdepth 1 -type f -name '*.pkg.tar.*' -print | sort)
  ((${#artifacts[@]})) || { echo "makepkg produced no packages: $pkgname" >&2; exit 1; }
  for artifact in "${artifacts[@]}"; do
    [[ -f "$artifact" ]] || { echo "Expected package artifact is missing: $artifact" >&2; exit 1; }
    [[ "$(basename "$artifact")" == *-debug-* ]] && continue
    artifact_info=$(pacman -Qp "$artifact")
    read -r artifact_package artifact_version <<< "$artifact_info"
    [[ -n "$artifact_package" && -n "$artifact_version" ]] || {
      echo "Could not read package metadata from $artifact." >&2; exit 1;
    }
    [[ "$artifact_version" == "$expected_version" ]] || {
      printf 'Built AUR artifact %s has version %s, expected locked version %s.\n' \
        "$(basename "$artifact")" "$artifact_version" "$expected_version" >&2
      exit 1
    }
    install -m644 "$artifact" "$repository/"
    pacman --config "$pacman_conf" -U --noconfirm "$artifact"
    repo-add --new "$repo_db" "$artifact"
    # Subsequent Hornero package builds may depend on an AUR package built
    # earlier in this same locked sequence. Make that repository visible to
    # dependency resolution after its first package has created a valid DB.
    if [[ "$dependency_pacman_conf" == "$base_pacman_conf" && -f "$repo_db" ]]; then
      dependency_pacman_conf="$work/pacman-with-built-aur.conf"
      cp "$pacman_conf" "$dependency_pacman_conf"
      cat >> "$dependency_pacman_conf" <<EOF

[hornero-installer]
SigLevel = Optional TrustAll
Server = file://$repository
EOF
    fi
    pacman_conf="$dependency_pacman_conf"
  done
done < <(python3 - "$ROOT/installer.lock.yaml" <<'PY'
import sys
import yaml

lock = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for name, package in lock["aur"]["packages"].items():
    print(f'{name}\t{package["revision"]}\t{package["version"]}')
PY
)

# The installer needs the selected edition and compositor to remain
# introspectable after installation. These metadata packages are generated
# from the same catalogue/resolver as the package chooser; they do not carry
# their own package lists.
profile_packages="$work/profile-packages"
python3 "$ROOT/scripts/render-installer-catalogue.py" \
  --product-source "$product_source" \
  --cache-dir "$work/profile-cache" \
  --output "$work/profile-package-chooser.conf" \
  --profile-packages-dir "$profile_packages"
for recipe in "$profile_packages"/*/PKGBUILD; do
  [[ -f "$recipe" ]] || { echo 'No installed-profile metadata packages were generated.' >&2; exit 1; }
  source_dir=${recipe%/PKGBUILD}
  chown -R builder:builder "$source_dir"
  runuser -u builder -- env VJOBS="$jobs" MAKEFLAGS="-j$jobs" makepkg --nodeps --noconfirm --force --cleanbuild --dir "$source_dir"
  mapfile -t artifacts < <(find "$source_dir" -maxdepth 1 -type f -name '*.pkg.tar.*' -print | sort)
  ((${#artifacts[@]} == 1)) || { echo "Expected one profile artifact from $source_dir." >&2; exit 1; }
  artifact=${artifacts[0]}
  expected_package=$(sed -n 's/^pkgname=//p' "$recipe")
  expected_version=$(sed -n 's/^pkgver=//p' "$recipe")-$(sed -n 's/^pkgrel=//p' "$recipe")
  artifact_info=$(pacman -Qp "$artifact")
  read -r artifact_package artifact_version <<< "$artifact_info"
  [[ "$artifact_package" == "$expected_package" ]] || {
    echo "Generated profile artifact has an unexpected package name: $artifact" >&2; exit 1;
  }
  [[ "$artifact_version" == "$expected_version" ]] || {
    echo "Generated profile artifact has an unexpected version: $artifact" >&2; exit 1;
  }
  install -m644 "$artifact" "$repository/"
  repo-add --new "$repo_db" "$artifact"
done

calamares_source="${CALAMARES_SOURCE:-$ROOT}"
calamares_tree="$work/installer-source"
mkdir -p "$calamares_tree/packaging" "$calamares_tree/image"
cp -a "$calamares_source/packaging/." "$calamares_tree/packaging/"
cp -a "$calamares_source/image/." "$calamares_tree/image/"
calamares_dir="$calamares_tree/packaging/calamares"
chown -R builder:builder "$calamares_tree"
mapfile -t calamares_deps < <(runuser -u builder -- makepkg --printsrcinfo --dir "$calamares_dir" | awk '$1 == "depends" || $1 == "makedepends" || $1 == "checkdepends" { dependency = $3; sub(/[<>=].*/, "", dependency); print dependency }' | sort -u)
if ((${#calamares_deps[@]})); then pacman --config "$pacman_conf" -S --needed --noconfirm "${calamares_deps[@]}"; fi
runuser -u builder -- env VJOBS="$jobs" MAKEFLAGS="-j$jobs" makepkg --nodeps --noconfirm --force --cleanbuild --dir "$calamares_dir"
mapfile -t calamares_artifacts < <(find "$calamares_dir" -maxdepth 1 -type f -name '*.pkg.tar.*' -print | sort)
((${#calamares_artifacts[@]})) || { echo 'makepkg produced no Calamares packages.' >&2; exit 1; }
for artifact in "${calamares_artifacts[@]}"; do
  [[ -f "$artifact" ]] || { echo "Expected Calamares package is missing: $artifact" >&2; exit 1; }
  [[ "$(basename "$artifact")" == *-debug-* ]] && continue
  install -m644 "$artifact" "$repository/"
  pacman --config "$pacman_conf" -U --noconfirm "$artifact"
  repo-add --new "$repo_db" "$artifact"
done

printf 'Built %s package files into %s\n' "$(find "$repository" -maxdepth 1 -name '*.pkg.tar.*' | wc -l)" "$repository"

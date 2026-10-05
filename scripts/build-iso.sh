#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
usage() { printf 'Usage: %s --work NEW_EMPTY_PATH --output NEW_EMPTY_PATH [--product-source HORNEROS_REPO]\n' "$0" >&2; }
work=""
output=""
product_source=""
while (($#)); do
  case "$1" in
    --work) work=${2:?}; shift 2 ;;
    --output) output=${2:?}; shift 2 ;;
    --product-source) product_source=${2:?}; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ -n "$work" && -n "$output" ]] || { usage; exit 2; }
for path in "$work" "$output"; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Refusing to reuse or overwrite path: $path" >&2; exit 1; }
done
work_path=$(realpath -m -- "$work")
output_path=$(realpath -m -- "$output")
[[ "$work_path" != "$output_path" && "$work_path" != "$output_path"/* && "$output_path" != "$work_path"/* ]] || {
  echo 'Work and output paths must be separate, non-nested directories.' >&2
  exit 1
}
work="$work_path"
output="$output_path"
[[ "$(systemd-detect-virt --vm 2>/dev/null || true)" != none ]] || {
  echo 'ISO builds are allowed only inside a disposable VM, never on the host installation.' >&2
  exit 1
}
[[ $(id -u) -eq 0 ]] || { echo 'Run mkarchiso from root inside the disposable build VM.' >&2; exit 1; }
jobs=${VJOBS:-2}
[[ "$jobs" =~ ^[1-2]$ ]] || { echo 'VJOBS must be 1 or 2.' >&2; exit 1; }
for tool in pacstrap mkinitcpio mkarchiso mksquashfs repo-add makepkg git python3; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
mkdir -p "$work" "$output"
available_kib=$(df -Pk "$work" | awk 'NR == 2 { print $4 }')
(( available_kib >= 41943040 )) || {
  echo 'The build VM needs at least 40 GiB free on its work filesystem.' >&2
  exit 1
}
output_available_kib=$(df -Pk "$output" | awk 'NR == 2 { print $4 }')
(( output_available_kib >= 12582912 )) || {
  echo 'The build VM needs at least 12 GiB free on its output filesystem.' >&2
  exit 1
}
work_device=$(df -P "$work" | awk 'NR == 2 { print $1 }')
output_device=$(df -P "$output" | awk 'NR == 2 { print $1 }')
if [[ "$work_device" == "$output_device" ]] && (( available_kib < 54525952 )); then
  echo 'When work and output share a filesystem, the build VM needs at least 52 GiB free.' >&2
  exit 1
fi

export HORNEROS_INSTALLER_DISPOSABLE=1 VJOBS="$jobs"
profile="$work/profile"
product="$work/product"
package_work="$work/package-work"
repo="$work/local-repo"
mkdir -p "$profile" "$product"
cp -a "$ROOT/image/archiso/." "$profile/"
install -Dm644 "$ROOT/image/calamares/hornero-installer-repo.conf" \
  "$profile/airootfs/etc/pacman.d/hornero-installer.conf"
if [[ -n "$product_source" ]]; then
  cp -a "$product_source/." "$product/"
else
  revision=$(python3 - "$ROOT/installer.lock.yaml" <<'PY'
import sys
import yaml
print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["product"]["revision"])
PY
)
  url=$(python3 - "$ROOT/installer.lock.yaml" <<'PY'
import sys
import yaml
print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["product"]["repository"].removesuffix(".git"))
PY
)
  curl --fail --location --silent --show-error "$url/archive/$revision.tar.gz" -o "$work/product.tar.gz"
  tar -xzf "$work/product.tar.gz" --strip-components=1 -C "$product"
fi
python3 "$product/scripts/resolve-edition.py" desktop --json >/dev/null
python3 "$ROOT/scripts/render-installer-catalogue.py" \
  --product-source "$product" \
  --cache-dir "$work/cache" \
  --output "$profile/calamares/modules/packagechooser.conf"

snapshot=$(python3 - "$ROOT/installer.lock.yaml" <<'PY'
import sys
import yaml
print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["arch"]["snapshot"])
PY
)
iso_month=$(date -d "$snapshot" +%Y.%m)
iso_label_suffix=$(date -d "$snapshot" +%y%m)
sed -i "s|@ARCH_SNAPSHOT@|$snapshot|g" "$profile/pacman.conf"
sed -i "s|@ARCH_SNAPSHOT@|$snapshot|g" \
  "$profile/airootfs/etc/pacman.d/hornero-installer-mirrorlist.conf"
sed -i "s/@ISOYYMM@/$iso_label_suffix/g; s/@ISOVERSION@/$iso_month/g" "$profile/profiledef.sh"
cat > "$work/pacman.conf" <<EOF
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
EOF
export PACMAN_CONF="$work/pacman.conf"
bash "$ROOT/scripts/build-package-repository.sh" --work "$package_work" --repository "$repo"
python3 "$ROOT/scripts/check-installer.py" \
  --config-root "$profile/calamares" \
  --schema-root "$package_work/installer-source/packaging/calamares/src/calamares/src/modules"
install -d "$profile/airootfs/usr/share/hornero-installer/repo"
cp -a "$repo/." "$profile/airootfs/usr/share/hornero-installer/repo/"
cat > "$work/build-repo.conf" <<EOF
[hornero-installer]
SigLevel = Optional TrustAll
Server = file://$repo
EOF
cat > "$work/target-pacman.conf" <<EOF
[options]
HoldPkg = pacman glibc
Architecture = auto
Color
CheckSpace
ParallelDownloads = 5
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
Include = $work/build-repo.conf

[core]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch

[extra]
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch
EOF
target="$work/target-root"
mkdir "$target"
mapfile -t base_packages < <(python3 - "$product/editions/catalogue.yaml" <<'PY'
import sys
import yaml
for package in yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["base"]["packages"]:
    print(package)
PY
)
pacstrap -C "$work/target-pacman.conf" -c -M "$target" "${base_packages[@]}"
install -Dm644 "$profile/airootfs/etc/pacman.conf" "$target/etc/pacman.conf"
install -Dm644 "$profile/airootfs/etc/pacman.d/hornero-installer-mirrorlist.conf" "$target/etc/pacman.d/hornero-installer-mirrorlist.conf"
install -Dm644 "$ROOT/image/calamares/hornero-installer-repo.conf" \
  "$target/etc/pacman.d/hornero-installer.conf"
install -Dm755 "$ROOT/image/calamares/cleanup-package-source.py" "$target/usr/lib/hornero-installer/cleanup-package-source.py"
install -d "$target/usr/share/hornero-installer/repo"
mksquashfs "$target" "$profile/airootfs/usr/share/hornero-installer/base.sqfs" \
  -noappend -comp zstd -Xcompression-level 8 -processors "$jobs"

repo_config="$work/hornero-installer.conf"
cat > "$repo_config" <<EOF
[hornero-installer]
SigLevel = Optional TrustAll
Server = file://$repo
EOF
sed "s|Include = /etc/pacman.d/hornero-installer.conf|Include = $repo_config|" \
  "$profile/pacman.conf" > "$work/archiso-pacman.conf"
sed -i "s|pacman_conf=\"pacman.conf\"|pacman_conf=\"$work/archiso-pacman.conf\"|" "$profile/profiledef.sh"

mkarchiso -v -w "$work/archiso-work" -o "$output" "$profile"
iso=$(find "$output" -maxdepth 1 -type f -name '*.iso' -print -quit)
[[ -n "$iso" ]] || { echo 'mkarchiso completed without producing an ISO.' >&2; exit 1; }
sha256sum "$iso" > "$iso.sha256"
python3 - "$ROOT/installer.lock.yaml" "$profile/calamares/modules/compositions.json" "$iso" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
import yaml

lock = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
choices = json.load(open(sys.argv[2], encoding="utf-8"))
artifact = Path(sys.argv[3])
hasher = hashlib.sha256()
with artifact.open("rb") as image_file:
    for chunk in iter(lambda: image_file.read(4 * 1024 * 1024), b""):
        hasher.update(chunk)
digest = hasher.hexdigest()
manifest = {
    "productRevision": lock["product"]["revision"],
    "calamaresVersion": lock["calamares"]["version"],
    "archSnapshot": lock["arch"]["snapshot"],
    "aurRecipes": lock["aur"]["packages"],
    "installChoices": choices["options"],
    "artifact": artifact.name,
    "sha256": digest,
    "status": "unsigned provisional preview",
}
artifact.with_suffix(artifact.suffix + ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
printf 'Built provisional HorneroOS installer media: %s\n' "$iso"

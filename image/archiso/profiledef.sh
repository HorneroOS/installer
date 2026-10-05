#!/usr/bin/env bash

iso_name="horneroos"
iso_label="HORNER@ISOYYMM@"
iso_publisher="HorneroOS <https://horneroos.com>"
iso_application="HorneroOS provisional installation media"
iso_version="@ISOVERSION@-provisional"
install_dir="hornero"
buildmodes=('iso')
bootmodes=('uefi-x64.systemd-boot.esp' 'bios.syslinux.mbr')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '8' '-processors' '2')
file_permissions=(
  ["/root"]="0:0:750"
  ["/etc/sudoers.d/hornero-live"]="0:0:440"
  ["/usr/local/bin/hornero-installer-start"]="0:0:755"
)

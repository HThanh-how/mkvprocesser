#!/bin/sh
# Proxmox hook cho LXC 106: khong cho app khoi dong tren nham filesystem
# neu SSD Samsung chua mount sau khi host bat may.
set -eu

vmid="${1:-}"
phase="${2:-}"

[ "$vmid" = "106" ] || exit 0
[ "$phase" = "pre-start" ] || exit 0

mountpoint -q /mnt/ssd-512 || {
  echo "LXC 106 blocked: /mnt/ssd-512 is not mounted" >&2
  exit 1
}

source_device="$(findmnt -n -o SOURCE --target /mnt/ssd-512)"
actual_uuid="$(blkid -s UUID -o value "$source_device")"
expected_uuid="215d5874-d70b-4c4e-874c-8e9972c22db9"

[ "$actual_uuid" = "$expected_uuid" ] || {
  echo "LXC 106 blocked: unexpected filesystem UUID on /mnt/ssd-512" >&2
  exit 1
}

[ -d /mnt/ssd-512/mkvtools-data ] || {
  echo "LXC 106 blocked: mkvtools-data directory is missing" >&2
  exit 1
}

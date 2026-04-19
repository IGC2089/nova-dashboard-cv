#!/usr/bin/env bash
# One-time setup: enable Pi OS overlayfs + /data partition for ODO persistence.
# Run ONCE as root after initial Pi OS setup.
set -euo pipefail

echo "=== Nova Dashboard — Read-Only Filesystem Setup ==="

raspi-config nonint enable_overlayfs

mkdir -p /data

if ! grep -q '/data' /etc/fstab; then
    echo '/dev/mmcblk0p3  /data  vfat  rw,sync,noatime,uid=1000,gid=1000  0  2' \
        >> /etc/fstab
    echo "Added /data to /etc/fstab"
fi

cp "$(dirname "$0")/nova-dashboard.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable nova-dashboard.service

echo ""
echo "Setup complete. REBOOT to activate read-only root filesystem."
echo "After reboot, verify with: mount | grep 'on / '"

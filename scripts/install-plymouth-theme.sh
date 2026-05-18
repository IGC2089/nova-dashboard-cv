#!/bin/bash
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

sudo mkdir -p /usr/share/plymouth/themes/nova
sudo cp "$REPO_DIR/scripts/plymouth/nova.plymouth" /usr/share/plymouth/themes/nova/
sudo cp "$REPO_DIR/scripts/plymouth/nova.script"   /usr/share/plymouth/themes/nova/
sudo cp "$REPO_DIR/assets/splash_logo.png"         /usr/share/plymouth/themes/nova/
sudo plymouth-set-default-theme nova
sudo update-initramfs -u
echo "Plymouth theme installed. Reboot to apply."

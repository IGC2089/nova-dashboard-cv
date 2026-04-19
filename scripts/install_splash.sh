#!/bin/bash
set -e

THEME_DIR=/usr/share/plymouth/themes/nova
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Installing Plymouth packages..."
apt-get install -y plymouth plymouth-themes

echo "Creating theme directory..."
mkdir -p "$THEME_DIR"

echo "Copying theme files..."
cp "$REPO_DIR/assets/splash_logo.png"          "$THEME_DIR/"
cp "$REPO_DIR/scripts/plymouth/nova.plymouth"  "$THEME_DIR/"
cp "$REPO_DIR/scripts/plymouth/nova.script"    "$THEME_DIR/"

echo "Setting default theme..."
plymouth-set-default-theme nova

echo "Writing Plymouth daemon config..."
cat > /etc/plymouth/plymouthd.conf << 'EOF'
[Daemon]
Theme=nova
ShowDelay=0
EOF

echo "Updating initramfs (this takes ~30s)..."
update-initramfs -u

echo ""
echo "=== DONE ==="
echo "Now manually edit /boot/firmware/cmdline.txt:"
echo "Add to the END of the existing single line (no newline):"
echo "  quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0"
echo ""
echo "Then run: sudo reboot"

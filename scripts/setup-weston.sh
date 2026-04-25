#!/usr/bin/env bash
set -euo pipefail
REPO=/home/pi/nova-dashboard-cv

echo "=== Installing Sway ==="
apt-get install -y sway avahi-daemon hostapd dnsmasq

echo "=== Configuring wlan0 static IP ==="
# Add static IP assignment to dhcpcd.conf if not already present
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    cat >> /etc/dhcpcd.conf <<'EOF'

interface wlan0
    static ip_address=192.168.50.1/24
    nohook wpa_supplicant
EOF
fi

echo "=== Installing config files ==="
mkdir -p /etc/sway /etc/openauto
install -Dm644 "$REPO/config/sway.conf"          /etc/sway/nova.conf
install -Dm644 "$REPO/config/nova-hostapd.conf"  /etc/hostapd/nova-hostapd.conf
install -Dm644 "$REPO/config/nova-dnsmasq.conf"  /etc/dnsmasq-nova.conf
install -Dm644 "$REPO/config/openauto.ini"        /etc/openauto/openauto.ini

echo "=== Installing systemd services ==="
install -Dm644 "$REPO/scripts/nova-network.service"           /etc/systemd/system/nova-network.service
install -Dm644 "$REPO/scripts/nova-sway.service"              /etc/systemd/system/nova-sway.service
install -Dm644 "$REPO/scripts/nova-dashboard-wayland.service" /etc/systemd/system/nova-dashboard-wayland.service
install -Dm644 "$REPO/scripts/nova-openauto.service"          /etc/systemd/system/nova-openauto.service

echo "=== Switching from KMS service to Wayland stack ==="
systemctl disable nova-dashboard.service 2>/dev/null || true
systemctl daemon-reload
systemctl enable nova-network.service
systemctl enable nova-sway.service
systemctl enable nova-dashboard-wayland.service
systemctl enable nova-openauto.service

echo ""
echo "Setup complete. Reboot to activate."
echo "Rollback: sudo bash $REPO/scripts/rollback-weston.sh"

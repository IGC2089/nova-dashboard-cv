#!/usr/bin/env bash
set -euo pipefail

echo "=== Stopping Weston stack ==="
systemctl stop nova-dashboard-wayland.service 2>/dev/null || true
systemctl stop nova-sway.service            2>/dev/null || true
systemctl stop nova-network.service           2>/dev/null || true

echo "=== Disabling Weston stack services ==="
systemctl disable nova-dashboard-wayland.service 2>/dev/null || true
systemctl disable nova-sway.service            2>/dev/null || true
systemctl disable nova-network.service           2>/dev/null || true

echo "=== Checking KMS service exists ==="
if ! systemctl cat nova-dashboard.service &>/dev/null; then
    echo "ERROR: nova-dashboard.service not found in systemd."
    echo "The original KMS service was not installed or was removed."
    echo "Manual recovery: deploy scripts/nova-dashboard.service to /etc/systemd/system/ first."
    exit 1
fi

echo "=== Restoring KMS-direct dashboard service ==="
systemctl daemon-reload
systemctl enable nova-dashboard.service
systemctl start nova-dashboard.service

echo ""
echo "Rollback complete. Dashboard running via KMS again."
echo "To restore git state: git checkout v1.0-kms-stable"

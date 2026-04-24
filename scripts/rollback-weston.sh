#!/usr/bin/env bash
set -euo pipefail
REPO=/home/pi/nova-dashboard-cv

echo "=== Stopping Weston stack ==="
systemctl stop nova-openauto.service         2>/dev/null || true
systemctl stop nova-dashboard-wayland.service 2>/dev/null || true
systemctl stop nova-weston.service            2>/dev/null || true
systemctl stop nova-network.service           2>/dev/null || true

echo "=== Disabling Weston stack services ==="
systemctl disable nova-openauto.service         2>/dev/null || true
systemctl disable nova-dashboard-wayland.service 2>/dev/null || true
systemctl disable nova-weston.service            2>/dev/null || true
systemctl disable nova-network.service           2>/dev/null || true

echo "=== Restoring KMS-direct dashboard service ==="
systemctl daemon-reload
systemctl enable nova-dashboard.service
systemctl start nova-dashboard.service

echo ""
echo "Rollback complete. Dashboard running via KMS again."
echo "To restore git state: git checkout v1.0-kms-stable"

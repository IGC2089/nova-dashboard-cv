#!/usr/bin/env bash
# Bring up SocketCAN interface at 500 kbps.
# Run as root (called by systemd ExecStartPre).
set -euo pipefail

IFACE="${CAN_IFACE:-can0}"
BITRATE="${CAN_BITRATE:-500000}"

ip link set "$IFACE" down 2>/dev/null || true
ip link set "$IFACE" type can bitrate "$BITRATE"
ip link set "$IFACE" up

# Configure u-blox GPS to 5 Hz if device is present
if [ -e /dev/ttyACM0 ]; then
    printf '\xb5\x62\x06\x08\x06\x00\xc8\x00\x01\x00\x01\x00\xde\x6a' \
        > /dev/ttyACM0 2>/dev/null || true
fi

echo "CAN interface $IFACE up at ${BITRATE} bps"

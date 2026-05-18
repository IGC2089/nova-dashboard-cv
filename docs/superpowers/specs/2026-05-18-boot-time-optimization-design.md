# Boot Time Optimization Design

**Goal:** Cut 8–10 seconds from boot by masking unused services and decoupling the display compositor from the WiFi AP.

**Approach:** Systemd-only changes — no Python code touched. Four targeted changes to service configuration.

**Tech Stack:** systemd, Debian Trixie, Raspberry Pi 5

---

## Changes

### 1. Mask `NetworkManager-wait-online.service`

`NetworkManager-wait-online` blocks the boot sequence for up to 6 seconds waiting for a "fully online" network state. The dashboard does not require internet connectivity, and SSH over ethernet connects without it.

```bash
sudo systemctl mask NetworkManager-wait-online.service
```

NetworkManager itself continues running. SSH, ethernet, and WiFi management are unaffected.

### 2. Disable cloud-init

cloud-init is a cloud VM bootstrapping tool (AWS, GCP, etc.). It has no useful function on bare metal. The official disable method is a sentinel file:

```bash
sudo touch /etc/cloud/cloud-init.disabled
```

This prevents all cloud-init units from running without masking them individually.

### 3. Mask `blueman-mechanism.service`

Blueman is a desktop Bluetooth GUI manager. The dashboard uses BlueZ D-Bus directly via the PairingAgent. Blueman adds ~1.2s to boot and provides nothing.

```bash
sudo systemctl mask blueman-mechanism.service
```

### 4. Decouple `nova-sway` from `nova-network` in the service file

**Current** (`scripts/nova-sway.service`):
```ini
After=nova-network.service seatd.service
Requires=nova-network.service seatd.service
```

**New:**
```ini
After=seatd.service
Requires=seatd.service
Wants=nova-network.service
```

`Wants` means systemd will still start `nova-network` alongside Sway — the WiFi AP comes up within seconds of the display turning on — but Sway no longer waits for it. The display starts immediately once `seatd` is ready.

After editing the file in the repo, it must be copied to the system and the daemon reloaded:
```bash
sudo cp scripts/nova-sway.service /etc/systemd/system/nova-sway.service
sudo systemctl daemon-reload
```

---

## Expected Savings

| Change | Saving |
|--------|--------|
| Mask NetworkManager-wait-online | ~6.0s |
| Disable cloud-init | ~1.0s |
| Mask blueman-mechanism | ~1.2s |
| Decouple nova-sway from nova-network | ~0.3s |
| **Total** | **~8.5s** |

---

## Rollback

All changes are reversible:
- `sudo systemctl unmask NetworkManager-wait-online.service`
- `sudo rm /etc/cloud/cloud-init.disabled`
- `sudo systemctl unmask blueman-mechanism.service`
- Revert `nova-sway.service` in the repo and re-copy

---

## Verification

After applying changes, confirm with:
```bash
systemd-analyze
systemd-analyze blame | head -20
```

The dashboard (`nova-dashboard-wayland.service`) should appear in the critical chain well under 10 seconds from power-on.

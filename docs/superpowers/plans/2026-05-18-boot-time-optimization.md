# Boot Time Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut ~8–10 seconds from boot time by masking three unused systemd services and decoupling the Sway compositor from the WiFi AP service.

**Architecture:** Three one-line systemd mask/disable commands run directly on the Pi, plus one edit to `scripts/nova-sway.service` in the repo (then copied to the Pi). No Python code changes. All changes are reversible.

**Tech Stack:** systemd, Debian Trixie, Raspberry Pi 5

---

## Files

| File | Change |
|------|--------|
| `scripts/nova-sway.service` | Remove `nova-network` from `Requires`/`After`, add `Wants` |

Tasks 1–3 are Pi-side systemd commands only (no repo files change).

---

### Task 1: Mask NetworkManager-wait-online

This service blocks boot for ~6 seconds waiting for full network connectivity. The dashboard does not need internet at boot. SSH over ethernet is unaffected — NetworkManager itself keeps running.

**Files:** none (Pi-side only)

- [ ] **Step 1: Mask the service on the Pi**

```bash
sudo systemctl mask NetworkManager-wait-online.service
```

Expected output:
```
Created symlink /etc/systemd/system/NetworkManager-wait-online.service → /dev/null.
```

- [ ] **Step 2: Verify it is masked**

```bash
systemctl is-enabled NetworkManager-wait-online.service
```

Expected output: `masked`

- [ ] **Step 3: Confirm NetworkManager itself is still running**

```bash
systemctl is-active NetworkManager.service
```

Expected output: `active`

---

### Task 2: Disable cloud-init

cloud-init is a cloud VM bootstrapping tool. It has no function on bare metal Raspberry Pi and adds ~1 second to boot. The official disable method is a sentinel file — safer than masking individual units.

**Files:** none (Pi-side only)

- [ ] **Step 1: Create the disable sentinel**

```bash
sudo touch /etc/cloud/cloud-init.disabled
```

No output expected.

- [ ] **Step 2: Verify the file exists**

```bash
ls -la /etc/cloud/cloud-init.disabled
```

Expected: file exists with recent timestamp.

- [ ] **Step 3: Verify cloud-init will be skipped on next boot**

```bash
cloud-init status
```

Expected output contains: `status: disabled` (may require a reboot to show — skip if command not found).

---

### Task 3: Mask blueman-mechanism

Blueman is a desktop Bluetooth GUI manager. The dashboard uses BlueZ D-Bus directly (via PairingAgent). Blueman adds ~1.2 seconds to boot and is unused.

**Files:** none (Pi-side only)

- [ ] **Step 1: Mask the service on the Pi**

```bash
sudo systemctl mask blueman-mechanism.service
```

Expected output:
```
Created symlink /etc/systemd/system/blueman-mechanism.service → /dev/null.
```

- [ ] **Step 2: Verify it is masked**

```bash
systemctl is-enabled blueman-mechanism.service
```

Expected output: `masked`

- [ ] **Step 3: Verify bluetooth.service (BlueZ) is unaffected**

```bash
systemctl is-active bluetooth.service
```

Expected output: `active`

---

### Task 4: Decouple nova-sway from nova-network

`nova-sway.service` currently `Requires` and waits `After` `nova-network.service` (the hostapd/dnsmasq WiFi AP). This means the display compositor cannot start until the AP is up — adding ~300ms and creating an unnecessary hard dependency. With `Wants` and no `After`, the AP still starts alongside Sway, just without blocking it.

**Files:**
- Modify: `scripts/nova-sway.service:3-4`

- [ ] **Step 1: Edit the service file in the repo**

Change `scripts/nova-sway.service` from:

```ini
[Unit]
Description=Sway Wayland Compositor
After=nova-network.service seatd.service
Requires=nova-network.service seatd.service
```

To:

```ini
[Unit]
Description=Sway Wayland Compositor
After=seatd.service
Requires=seatd.service
Wants=nova-network.service
```

- [ ] **Step 2: Commit**

```bash
git add scripts/nova-sway.service
git commit -m "fix: decouple nova-sway from nova-network to reduce boot time"
```

- [ ] **Step 3: Deploy to Pi — copy file and reload daemon**

```bash
sudo cp scripts/nova-sway.service /etc/systemd/system/nova-sway.service
sudo systemctl daemon-reload
```

No output expected.

- [ ] **Step 4: Verify the new dependency**

```bash
systemctl show nova-sway.service --property=After
systemctl show nova-sway.service --property=Wants
```

Expected: `After` does NOT contain `nova-network.service`. `Wants` contains `nova-network.service`.

---

### Task 5: Reboot and measure

Verify all changes took effect and measure the improvement.

**Files:** none

- [ ] **Step 1: Reboot the Pi**

```bash
sudo reboot
```

Wait for the dashboard to appear on screen and SSH to become available again.

- [ ] **Step 2: Measure boot time**

```bash
systemd-analyze
```

Expected: total boot time under 15 seconds (was ~20+ seconds before).

- [ ] **Step 3: Confirm the three services are gone from the top of blame**

```bash
systemd-analyze blame | head -20
```

Expected: `NetworkManager-wait-online`, `cloud-init-main`, and `blueman-mechanism` no longer appear.

- [ ] **Step 4: Confirm nova-network still starts (just in parallel)**

```bash
systemctl is-active nova-network.service
```

Expected output: `active`

- [ ] **Step 5: Confirm dashboard is running**

```bash
systemctl is-active nova-dashboard-wayland.service
```

Expected output: `active`

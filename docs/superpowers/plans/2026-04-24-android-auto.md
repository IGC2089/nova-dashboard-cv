# Android Auto Wireless Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add wireless Android Auto to the center panel of the Pi 5 dashboard by running Weston as a Wayland compositor, with the dashboard and OpenAuto as separate side-by-side Wayland clients.

**Architecture:** Weston owns KMS/DRM and runs on `/dev/dri/card1`. Dashboard (pygame/SDL Wayland) is launched first as a full-screen 800×480 window. OpenAuto (Qt/Wayland) is launched second and naturally stacks on top in the center zone (200–600 px). The Pi creates a dedicated WiFi AP (`nova-auto`) for wireless AA; phone connects via mDNS discovery.

**Tech Stack:** Weston 12.x, SDL2 Wayland backend, pygame 2.x, OpenAuto (f1xpl/openauto), aasdk (f1xpl/aasdk), hostapd, dnsmasq, avahi-daemon, systemd, Python 3.11, CMake, Qt 5.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `config/weston.ini` | Weston compositor config (KMS backend, DRM device, no idle) |
| Create | `config/nova-hostapd.conf` | WiFi AP: SSID `nova-auto`, WPA2, ch6 |
| Create | `config/nova-dnsmasq.conf` | DHCP for phone subnet 192.168.50.x |
| Create | `config/openauto.ini` | OpenAuto display area and Wayland settings |
| Create | `scripts/nova-network.service` | systemd: hostapd + dnsmasq WiFi AP |
| Create | `scripts/nova-weston.service` | systemd: Weston compositor |
| Create | `scripts/nova-dashboard-wayland.service` | systemd: dashboard as Wayland client |
| Create | `scripts/nova-openauto.service` | systemd: OpenAuto as Wayland client |
| Create | `scripts/setup-weston.sh` | Master installer: installs all above to system |
| Create | `scripts/rollback-weston.sh` | Restores KMS-direct pygame stack |
| Modify | `main.py:17-18` | Change `kmsdrm` → `wayland`, remove `SDL_NOMOUSE`, add `WAYLAND_DISPLAY` |
| Modify | `main.py:77` | Change `pygame.FULLSCREEN` → `pygame.NOFRAME` |

---

## Task 1: Feature branch + Weston config

**Files:**
- Create: `config/weston.ini`

- [ ] **Step 1: Create feature branch**

```bash
cd /home/pi/nova-dashboard-cv
git checkout -b feature/android-auto
```

Expected: `Switched to a new branch 'feature/android-auto'`

- [ ] **Step 2: Create the `config/` directory and `weston.ini`**

```bash
mkdir -p config
```

Create `config/weston.ini` with this exact content:

```ini
[core]
backend=drm-backend.so
shell=desktop-shell.so
idle-time=0
repaint-window=16

[drm]
device=/dev/dri/card1

[output]
name=HDMI-A-1

[shell]
locking=false
animation=none
close-animation=none
startup-animation=none
```

- [ ] **Step 3: Verify config parses correctly**

```bash
weston --config=/home/pi/nova-dashboard-cv/config/weston.ini --help > /dev/null && echo "config syntax OK"
```

If `weston` is not yet installed, skip this check — it will be verified after installation in Task 7.

- [ ] **Step 4: Commit**

```bash
git add config/weston.ini
git commit -m "feat: add Weston compositor config"
```

---

## Task 2: WiFi AP config (hostapd + dnsmasq)

**Files:**
- Create: `config/nova-hostapd.conf`
- Create: `config/nova-dnsmasq.conf`

- [ ] **Step 1: Create hostapd config**

Create `config/nova-hostapd.conf`:

```
interface=wlan0
driver=nl80211
ssid=nova-auto
hw_mode=g
channel=6
wmm_enabled=0
auth_algs=1
wpa=2
wpa_passphrase=novaauto2024
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
ignore_broadcast_ssid=0
```

- [ ] **Step 2: Create dnsmasq config**

Create `config/nova-dnsmasq.conf`:

```
interface=wlan0
bind-interfaces
dhcp-range=192.168.50.10,192.168.50.50,24h
dhcp-option=3,192.168.50.1
dhcp-option=6,8.8.8.8
no-resolv
log-dhcp
```

- [ ] **Step 3: Validate hostapd config syntax**

```bash
sudo hostapd -t /home/pi/nova-dashboard-cv/config/nova-hostapd.conf
```

Expected: exits without errors (note: will warn that wlan0 is not in AP mode — that's OK at this stage).

If `hostapd` is not installed yet: `sudo apt-get install -y hostapd` first.

- [ ] **Step 4: Commit**

```bash
git add config/nova-hostapd.conf config/nova-dnsmasq.conf
git commit -m "feat: add WiFi AP config for nova-auto"
```

---

## Task 3: Port main.py to Wayland SDL backend

**Files:**
- Modify: `main.py:17-18,77`

- [ ] **Step 1: Change the SDL env vars at the top of main.py**

In `main.py`, replace lines 17–18:

```python
os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm')
os.environ.setdefault('SDL_NOMOUSE', '1')
```

with:

```python
os.environ.setdefault('SDL_VIDEODRIVER', 'wayland')
os.environ.setdefault('WAYLAND_DISPLAY', 'wayland-1')
```

- [ ] **Step 2: Change the pygame display mode in `main()`**

Find the line in `main()` (around line 77):

```python
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
```

Replace with:

```python
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
```

Reason: `pygame.FULLSCREEN` in Weston's desktop-shell requests exclusive fullscreen and hides all other windows (including OpenAuto). `pygame.NOFRAME` creates a borderless window at the correct size without exclusivity.

- [ ] **Step 3: Verify Python syntax**

```bash
python3 -m py_compile main.py && echo "syntax OK"
```

Expected: prints `syntax OK`.

- [ ] **Step 4: Verify the env var change is in place**

```bash
grep -n "SDL_VIDEODRIVER.*wayland" main.py
```

Expected: one line showing the `wayland` value.

```bash
grep -n "FULLSCREEN" main.py
```

Expected: no output (FULLSCREEN has been removed).

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: port main.py to Wayland SDL backend"
```

---

## Task 4: Systemd service files

**Files:**
- Create: `scripts/nova-network.service`
- Create: `scripts/nova-weston.service`
- Create: `scripts/nova-dashboard-wayland.service`
- Create: `scripts/nova-openauto.service`

- [ ] **Step 1: Create nova-network.service**

Create `scripts/nova-network.service`:

```ini
[Unit]
Description=Nova WiFi AP (hostapd + dnsmasq)
After=network.target
Before=nova-weston.service

[Service]
Type=forking
ExecStartPre=/sbin/ip addr replace 192.168.50.1/24 dev wlan0
ExecStart=/usr/sbin/hostapd -B /etc/hostapd/nova-hostapd.conf -P /run/hostapd-nova.pid
ExecStartPost=/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq-nova.conf --pid-file=/run/dnsmasq-nova.pid
PIDFile=/run/hostapd-nova.pid
ExecStop=/bin/kill $(cat /run/hostapd-nova.pid)
ExecStopPost=/bin/kill $(cat /run/dnsmasq-nova.pid)
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create nova-weston.service**

Create `scripts/nova-weston.service`:

```ini
[Unit]
Description=Weston Wayland Compositor
After=nova-network.service
Requires=nova-network.service

[Service]
Type=simple
User=root
Environment=XDG_RUNTIME_DIR=/run/user/0
ExecStartPre=/bin/mkdir -p /run/user/0
ExecStartPre=/bin/chmod 700 /run/user/0
ExecStart=/usr/bin/weston --config=/etc/xdg/weston/weston.ini --log=/var/log/weston.log
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Create nova-dashboard-wayland.service**

Create `scripts/nova-dashboard-wayland.service`:

```ini
[Unit]
Description=Nova Dashboard (Wayland client)
After=nova-weston.service
Requires=nova-weston.service

[Service]
Type=simple
User=root
Environment=XDG_RUNTIME_DIR=/run/user/0
Environment=WAYLAND_DISPLAY=wayland-1
Environment=SDL_VIDEODRIVER=wayland
Environment=HOME=/root
WorkingDirectory=/home/pi/nova-dashboard-cv
ExecStartPre=-/bin/bash /home/pi/nova-dashboard-cv/scripts/setup_can.sh
ExecStart=/home/pi/nova-dashboard-cv/.venv/bin/python3 /home/pi/nova-dashboard-cv/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
KillMode=mixed
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Create nova-openauto.service**

Create `scripts/nova-openauto.service`:

```ini
[Unit]
Description=OpenAuto Android Auto
After=nova-weston.service avahi-daemon.service
Requires=nova-weston.service
Wants=avahi-daemon.service

[Service]
Type=simple
User=root
Environment=XDG_RUNTIME_DIR=/run/user/0
Environment=WAYLAND_DISPLAY=wayland-1
Environment=QT_QPA_PLATFORM=wayland
Environment=QT_WAYLAND_DISABLE_WINDOWDECORATION=1
ExecStart=/opt/openauto/bin/autoapp --config /etc/openauto/openauto.ini
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Validate all service files with systemd-analyze**

```bash
for f in scripts/nova-network.service scripts/nova-weston.service \
          scripts/nova-dashboard-wayland.service scripts/nova-openauto.service; do
    systemd-analyze verify "$f" 2>&1 | grep -v "^$" || echo "$f OK"
done
```

Expected: no `[FAILED]` lines. Warnings about missing binaries at this stage are acceptable.

- [ ] **Step 6: Commit**

```bash
git add scripts/nova-network.service scripts/nova-weston.service \
        scripts/nova-dashboard-wayland.service scripts/nova-openauto.service
git commit -m "feat: add systemd service files for Weston stack"
```

---

## Task 5: Build aasdk and OpenAuto on Pi 5

> **Note:** This task is executed directly on the Pi 5, takes approximately 60–120 minutes, and should be run inside a `tmux` session (`tmux new -s build`).

**Files:**
- Create: `/opt/aasdk/` (build output)
- Create: `/opt/openauto/` (install target)

- [ ] **Step 1: Install build dependencies**

```bash
sudo apt-get update
sudo apt-get install -y \
    cmake build-essential git \
    libprotobuf-dev protobuf-compiler \
    libssl-dev libusb-1.0-0-dev \
    libboost-all-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    libgst-dev \
    qtbase5-dev qtbase5-private-dev \
    qt5-qmake qtmultimedia5-dev \
    libqt5bluetooth5 libqt5serialport5-dev \
    libbluetooth-dev librtaudio-dev \
    libavahi-compat-libdnssd-dev avahi-daemon
```

Expected: all packages install without errors.

- [ ] **Step 2: Clone and build aasdk**

```bash
cd /opt
sudo git clone https://github.com/f1xpl/aasdk.git
cd aasdk
sudo cmake -DCMAKE_BUILD_TYPE=Release -B build
sudo cmake --build build -j$(nproc)
sudo cmake --install build --prefix /usr/local
```

Expected: ends with `-- Install configuration: "Release"` and no errors. Takes ~20 minutes.

- [ ] **Step 3: Verify aasdk installed**

```bash
ls /usr/local/include/aasdk/ | head -5
```

Expected: lists header files (e.g., `Channel/`, `Common/`, etc.).

- [ ] **Step 4: Clone and build OpenAuto**

```bash
cd /opt
sudo git clone https://github.com/f1xpl/openauto.git
cd openauto
sudo cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DAASDK_INCLUDE_DIRS=/usr/local/include \
    -DAASDK_LIBRARIES=/usr/local/lib/libaasdk.so \
    -DAASDK_PROTO_INCLUDE_DIRS=/usr/local/include \
    -DAASDK_PROTO_LIBRARIES=/usr/local/lib/libaasdk_proto.so \
    -B build
sudo cmake --build build -j$(nproc)
sudo mkdir -p /opt/openauto/bin /opt/openauto/resources
sudo cp build/bin/autoapp /opt/openauto/bin/
sudo cp -r resources/* /opt/openauto/resources/
```

Expected: ends without errors. Takes ~40–60 minutes.

- [ ] **Step 5: Verify autoapp binary**

```bash
/opt/openauto/bin/autoapp --version 2>&1 | head -3
ls -lh /opt/openauto/bin/autoapp
```

Expected: binary exists, ~5–15 MB.

---

## Task 6: OpenAuto config file

**Files:**
- Create: `config/openauto.ini`

- [ ] **Step 1: Create OpenAuto config**

Create `config/openauto.ini`:

```ini
[general]
hand_drive_mode=false
blank_areas=false

[video]
fps=30
resolution=480p
dpi=140
margin_width=0
margin_height=0

[audio]
music_audio_channel_enabled=true
speech_audio_channel_enabled=true
audio_audio_channel_enabled=true

[bluetooth]
adapter_type=0

[ipc]
type=1
```

> `resolution=480p` constrains OpenAuto to 480px height. The width follows from the Wayland window geometry set by the compositor.

- [ ] **Step 2: Commit**

```bash
git add config/openauto.ini
git commit -m "feat: add OpenAuto config"
```

---

## Task 7: setup-weston.sh master installer

**Files:**
- Create: `scripts/setup-weston.sh`

- [ ] **Step 1: Create the install script**

Create `scripts/setup-weston.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
REPO=/home/pi/nova-dashboard-cv

echo "=== Installing Weston ==="
apt-get install -y weston avahi-daemon hostapd dnsmasq

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
mkdir -p /etc/xdg/weston /etc/openauto
install -Dm644 "$REPO/config/weston.ini"        /etc/xdg/weston/weston.ini
install -Dm644 "$REPO/config/nova-hostapd.conf" /etc/hostapd/nova-hostapd.conf
install -Dm644 "$REPO/config/nova-dnsmasq.conf" /etc/dnsmasq-nova.conf
install -Dm644 "$REPO/config/openauto.ini"       /etc/openauto/openauto.ini

echo "=== Installing systemd services ==="
install -Dm644 "$REPO/scripts/nova-network.service"           /etc/systemd/system/nova-network.service
install -Dm644 "$REPO/scripts/nova-weston.service"            /etc/systemd/system/nova-weston.service
install -Dm644 "$REPO/scripts/nova-dashboard-wayland.service" /etc/systemd/system/nova-dashboard-wayland.service
install -Dm644 "$REPO/scripts/nova-openauto.service"          /etc/systemd/system/nova-openauto.service

echo "=== Switching from KMS service to Wayland stack ==="
systemctl disable nova-dashboard.service 2>/dev/null || true
systemctl daemon-reload
systemctl enable nova-network.service
systemctl enable nova-weston.service
systemctl enable nova-dashboard-wayland.service
systemctl enable nova-openauto.service

echo ""
echo "Setup complete. Reboot to activate."
echo "Rollback: sudo bash $REPO/scripts/rollback-weston.sh"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/setup-weston.sh
```

- [ ] **Step 3: Validate bash syntax**

```bash
bash -n scripts/setup-weston.sh && echo "syntax OK"
```

Expected: prints `syntax OK`.

- [ ] **Step 4: Commit**

```bash
git add scripts/setup-weston.sh
git commit -m "feat: add Weston stack installer script"
```

---

## Task 8: rollback-weston.sh

**Files:**
- Create: `scripts/rollback-weston.sh`

- [ ] **Step 1: Create rollback script**

Create `scripts/rollback-weston.sh`:

```bash
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
```

- [ ] **Step 2: Make executable and validate syntax**

```bash
chmod +x scripts/rollback-weston.sh
bash -n scripts/rollback-weston.sh && echo "syntax OK"
```

Expected: `syntax OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/rollback-weston.sh
git commit -m "feat: add Weston stack rollback script"
```

---

## Task 9: Smoke test on Pi 5

> All steps in this task are run on the Pi 5 hardware. No code changes — this is a verification checklist.

- [ ] **Step 1: Install Weston stack**

```bash
cd /home/pi/nova-dashboard-cv
git pull
sudo bash scripts/setup-weston.sh
```

Expected: ends with `Setup complete. Reboot to activate.`

- [ ] **Step 2: Build OpenAuto if not already done (see Task 5)**

```bash
ls /opt/openauto/bin/autoapp && echo "autoapp present" || echo "RUN TASK 5 FIRST"
```

- [ ] **Step 3: Reboot**

```bash
sudo reboot
```

- [ ] **Step 4: Verify all services started**

After reboot, SSH in:

```bash
systemctl is-active nova-network.service
systemctl is-active nova-weston.service
systemctl is-active nova-dashboard-wayland.service
systemctl is-active nova-openauto.service
```

Expected: all four print `active`.

If any service failed:

```bash
journalctl -u nova-weston.service -n 50 --no-pager
```

- [ ] **Step 5: Verify WiFi AP is broadcasting**

On a phone or laptop: scan for WiFi networks. `nova-auto` should appear.

Connect with password `novaauto2024`. Verify the phone gets an IP in `192.168.50.x`.

```bash
# On Pi: verify DHCP lease was issued
cat /var/lib/misc/dnsmasq.leases
```

- [ ] **Step 6: Verify display layout**

On the HDMI screen:
- Left zone (0–200px): gauge fills visible
- Center zone (200–600px): OpenAuto UI (or waiting-for-phone screen)
- Right zone (600–800px): gauge fills visible

- [ ] **Step 7: Test Android Auto connection**

On Android phone:
1. Connect to `nova-auto` WiFi
2. Open Android Auto app → Wireless setup
3. Pi should appear in discovered devices
4. Tap to connect

Expected: Android Auto session starts in the center zone of the display.

- [ ] **Step 8: Test dashboard swipe paging**

Touch/swipe right of center (x > 600): verify swipe paging still works (BATT/IGN/MAP/CLT/AFR/ODO/TRIP readouts on page 1).

- [ ] **Step 9: Test rollback**

```bash
sudo bash /home/pi/nova-dashboard-cv/scripts/rollback-weston.sh
```

Expected: KMS dashboard restarts within 5 seconds. Verify with:

```bash
systemctl is-active nova-dashboard.service
```

- [ ] **Step 10: Tag the Weston release**

```bash
git tag v1.1-weston-aa
git push origin v1.1-weston-aa
```

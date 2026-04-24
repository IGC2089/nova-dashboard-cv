# Android Auto Wireless Integration — Design Spec

**Date:** 2026-04-24
**Branch:** feature/android-auto

---

## Goal

Integrate wireless Android Auto into the center panel of the nova-dashboard-cv display, with the two gauge fills always visible on either side. The dashboard and Android Auto render side-by-side on a shared Weston Wayland compositor over KMS/DRM on a 800×480 HDMI touchscreen.

---

## Section 1: Architecture

The current stack (pygame direct KMS/DRM) is replaced by a Weston compositor layer that owns the display. Both the dashboard and OpenAuto run as Wayland clients under Weston.

```
KMS/DRM (Pi 5 GPU, /dev/dri/card1)
    └── Weston compositor
            ├── Dashboard window (pygame/SDL Wayland client)  — full 800×480, RGBA, transparent center
            └── OpenAuto window (autoapp Wayland client)       — center zone 400×480 at x=200
```

The dashboard window renders the gauge fills, speed text, page dots, and warnings at full canvas size. The center 400×480 pixels are left transparent (alpha=0) so OpenAuto shows through underneath.

Rollback path: `git checkout v1.0-kms-stable` + disable Weston services restores the original KMS-direct pygame stack. Git tag `v1.0-kms-stable` exists for this purpose.

---

## Section 2: Display Layout

Screen: 800×480

| Zone | x range | Content |
|------|---------|---------|
| Left gauge | 0–200 | Tachometer fill (speed data), fuel fill |
| Center (AA) | 200–600 | OpenAuto Android Auto surface |
| Right gauge | 600–800 | Speedometer fill (RPM data), CLT fill |

OpenAuto is configured to render at position `200,0` with size `400×480`.

The dashboard window covers the full 800×480 but the center pixels are transparent, letting Weston composite OpenAuto beneath them.

---

## Section 3: Components

| Component | File/Location | Purpose |
|-----------|--------------|---------|
| Weston setup script | `scripts/setup-weston.sh` | Install deps, build OpenAuto, configure hostapd/dnsmasq, install systemd services |
| Rollback script | `scripts/rollback-weston.sh` | Stop Weston services, restore KMS-direct pygame stack |
| Weston config | `/etc/xdg/weston/weston.ini` | Compositor config: KMS backend, DRM device, no idle timeout |
| WiFi AP config | `/etc/hostapd/hostapd.conf` | SSID `nova-auto`, WPA2, channel 6 |
| DHCP config | `/etc/dnsmasq.conf` | Serve 192.168.50.10–50 to phone subnet |
| OpenAuto binary | `/opt/openauto/bin/autoapp` | Built from source on Pi 5 |
| OpenAuto config | `/etc/openauto/config.ini` | Display area `200,0,400,480`, Wayland socket |
| Dashboard RGBA | `dashboard_ui.py` | Render to RGBA canvas, leave center transparent |
| Main entry point | `main.py` | Port SDL backend to `wayland`, remove KMS env vars |
| Systemd services | `/etc/systemd/system/nova-*.service` | 4 services in dependency order |

---

## Section 4: Wireless Android Auto Setup

### WiFi Access Point

Pi 5 creates a dedicated AP on `wlan0`:

- SSID: `nova-auto`
- Security: WPA2-PSK
- Channel: 6 (2.4 GHz for range)
- Pi static IP: `192.168.50.1`
- Phone DHCP range: `192.168.50.10–50`

`hostapd` manages the AP; `dnsmasq` serves DHCP on the `wlan0` interface only.

### OpenAuto Build

Built from source on Pi 5 (aarch64):

- Dependencies: `libprotobuf-dev`, `libssl-dev`, `libusb-1.0-0-dev`, `libboost-all-dev`, `cmake`
- Android Auto SDK (`aasdk`) cloned and built first
- OpenAuto cloned, patched for Wayland output, built with CMake
- Install target: `/opt/openauto/`

### Phone Connection Flow

1. Pi AP (`nova-auto`) is up before Weston starts
2. Phone connects to `nova-auto` WiFi
3. `avahi-daemon` advertises `_androidauto._tcp` on the subnet (mDNS)
4. Phone discovers the Pi and initiates AA session over TCP port 5277
5. OpenAuto accepts the session and renders to its Weston Wayland surface at the center zone

No USB dongle required — Pi 5 built-in WiFi handles the connection.

---

## Section 5: Boot Sequence & Systemd

Services start in dependency order:

```
multi-user.target
    └── nova-network.service      # hostapd + dnsmasq — WiFi AP
            └── nova-weston.service   # Weston compositor on KMS/DRM
                    ├── nova-dashboard.service  # pygame dashboard (Wayland client)
                    └── nova-openauto.service   # OpenAuto autoapp (Wayland client)
```

`avahi-daemon` runs in parallel (standard systemd service, no custom ordering needed).

### Service Definitions (outline)

**nova-network.service**
- `After=network.target`
- `ExecStart=/usr/sbin/hostapd /etc/hostapd/hostapd.conf`
- `ExecStartPost=/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq.conf`

**nova-weston.service**
- `After=nova-network.service`
- `ExecStart=/usr/bin/weston --config=/etc/xdg/weston/weston.ini`

**nova-dashboard.service**
- `After=nova-weston.service`
- `Environment=SDL_VIDEODRIVER=wayland WAYLAND_DISPLAY=wayland-1`
- `ExecStart=/usr/bin/python3 /opt/nova-dashboard-cv/main.py`

**nova-openauto.service**
- `After=nova-weston.service`
- `Environment=WAYLAND_DISPLAY=wayland-1`
- `ExecStart=/opt/openauto/bin/autoapp`

### Rollback

```bash
sudo systemctl stop nova-openauto nova-dashboard nova-weston nova-network
sudo systemctl disable nova-openauto nova-dashboard nova-weston nova-network
git checkout v1.0-kms-stable
sudo systemctl enable --now nova-dashboard-kms   # original KMS service
```

Or run `scripts/rollback-weston.sh`.

---

## Open Questions / Constraints

- OpenAuto Pro license: community fork is GPL, verify it supports wireless AA on Pi 5 aarch64 before committing to build time
- Touch input: Weston will route touch events to the focused surface — OpenAuto needs to be the focused window in the center; dashboard touch events (swipe) need to be handled via a separate input region or an overlay window
- DSI display: current design targets HDMI; when migrated to DSI, only the DRM device path in `weston.ini` changes (`/dev/dri/card0` vs `card1`)

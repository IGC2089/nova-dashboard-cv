# Boot Splash Screen — Design Spec

**Date:** 2026-04-19
**Project:** Nova Dashboard CV (1974 Chevrolet Nova, Raspberry Pi 5, 800×480)

---

## Overview

Replace the visible kernel boot log with a custom splash screen using Plymouth. The splash shows `assets/splash_logo.png` from power-on until the dashboard renders its first frame, then fades out smoothly (~0.5s). No boot text is visible at any point.

**Approach:** Plymouth (standard Linux splash daemon) with a minimal script-type theme. Plymouth is installed on the Pi, a custom theme is created from repo files, and `main.py` signals Plymouth to fade out before pygame claims the display.

---

## 1. Plymouth Theme Files

Stored in repo at `scripts/plymouth/`. Installed to `/usr/share/plymouth/themes/nova/` by the install script.

### `scripts/plymouth/nova.plymouth`

```ini
[Plymouth Theme]
Name=Nova Dashboard
Description=1974 Nova instrument cluster splash
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/nova
ScriptFile=/usr/share/plymouth/themes/nova/nova.script
```

### `scripts/plymouth/nova.script`

Scales `splash_logo.png` to fit 800×480, centered, no distortion:

```
wallpaper = Image("splash_logo.png");
sw = Window.GetWidth();
sh = Window.GetHeight();
scale = Math.Min(sw / wallpaper.GetWidth(), sh / wallpaper.GetHeight());
scaled = wallpaper.Scale(wallpaper.GetWidth() * scale, wallpaper.GetHeight() * scale);
sprite = Sprite(scaled);
sprite.SetX((sw - scaled.GetWidth()) / 2);
sprite.SetY((sh - scaled.GetHeight()) / 2);
```

### `assets/splash_logo.png`

Already in repo. Copied alongside theme files by install script.

---

## 2. Kernel Cmdline Changes

File: `/boot/firmware/cmdline.txt` (manual edit — do not automate, a bad write bricks the Pi).

Add these tokens to the existing single line:

| Token | Effect |
|---|---|
| `quiet` | Suppresses kernel log output |
| `splash` | Signals kernel to hand off to Plymouth |
| `plymouth.ignore-serial-consoles` | Prevents Plymouth attaching to UART |
| `logo.nologo` | Removes Raspberry Pi rainbow splash |
| `vt.global_cursor_default=0` | Hides blinking cursor |

Before:
```
console=serial0,115200 console=tty1 root=... rootfstype=ext4 ...
```

After:
```
console=serial0,115200 console=tty1 root=... rootfstype=ext4 ... quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0
```

### Plymouth system config

`/etc/plymouth/plymouthd.conf` — set by install script:
```ini
[Daemon]
Theme=nova
ShowDelay=0
```
`ShowDelay=0` makes the splash appear immediately at boot.

---

## 3. main.py Plymouth Handoff

Add `_quit_plymouth()` helper and call it right before `pygame.init()`. This signals Plymouth to begin its fade-out while pygame takes over the framebuffer.

```python
import subprocess

def _quit_plymouth() -> None:
    """Signal Plymouth to fade out and release the display."""
    try:
        subprocess.run(['plymouth', 'quit', '--retain-splash'],
                       timeout=2.0, check=False, capture_output=True)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Plymouth not installed or not running — safe to ignore
```

Call order in `main()`:
```python
# load config, create state, renderer, start threads...
_quit_plymouth()       # fade begins
pygame.init()          # display takeover
screen = pygame.display.set_mode(...)
# render loop...
```

`--retain-splash` keeps the image visible while Plymouth fades — by the time pygame claims the framebuffer, Plymouth has released it. The `except` block makes this a no-op on Windows/dev machines with no Plymouth.

---

## 4. Install Script

**`scripts/install_splash.sh`** — run once on Pi as root after `git pull`:

```bash
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

echo "Updating initramfs (this takes ~30s)..."
update-initramfs -u

echo "Done. Edit /boot/firmware/cmdline.txt to add:"
echo "  quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0"
echo "Then reboot."
```

The cmdline.txt edit is the only manual step — it is intentionally left to the user.

---

## 5. Files Changed

| File | Action |
|---|---|
| `scripts/plymouth/nova.plymouth` | Create — Plymouth theme metadata |
| `scripts/plymouth/nova.script` | Create — Plymouth display script |
| `scripts/install_splash.sh` | Create — one-time Pi setup script |
| `main.py` | Modify — add `_quit_plymouth()` + call before pygame.init() |

No changes to: config YAML files, dashboard_ui.py, vehicle_state.py, CAN/GPS handlers, tests.

---

## 6. Deployment Steps (after implementation)

1. `git pull` on the Pi
2. `sudo bash scripts/install_splash.sh`
3. Manually edit `/boot/firmware/cmdline.txt` — add the 5 tokens to the existing line
4. `sudo reboot`

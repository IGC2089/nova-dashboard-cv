# Splash Screen Implementation Design

**Goal:** Show `assets/splash_logo.png` from power-on through dashboard load with a smooth fade-in transition.

**Architecture:** A Plymouth script theme covers early boot. The dashboard fade-in covers the Plymouth→Sway handoff and the first frames of rendering. The existing `_quit_plymouth(--retain-splash)` call in `main.py` bridges the two phases seamlessly.

**Tech Stack:** Plymouth (script module), OpenCV (`cv2.addWeighted`), pygame, Python 3

---

## Components

| File | Change |
|------|--------|
| `scripts/plymouth/nova.plymouth` | New — Plymouth theme descriptor |
| `scripts/plymouth/nova.script` | New — Plymouth rendering script |
| `scripts/install-plymouth-theme.sh` | New — install script for Pi |
| `main.py` | Add splash fade-in to render loop |

`assets/splash_logo.png` is used as-is; it gets copied to the Plymouth theme directory by the install script.

---

## Plymouth Theme

### `scripts/plymouth/nova.plymouth`

```ini
[Plymouth Theme]
Name=Nova
Description=Nova Dashboard splash screen
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/nova
ScriptFile=/usr/share/plymouth/themes/nova/nova.script
```

### `scripts/plymouth/nova.script`

```
Window.SetBackgroundTopColor(0, 0, 0);
Window.SetBackgroundBottomColor(0, 0, 0);

logo.image = Image("splash_logo.png");
logo.sprite = Sprite(logo.image);
logo.sprite.SetX(Window.GetWidth() / 2 - logo.image.GetWidth() / 2);
logo.sprite.SetY(Window.GetHeight() / 2 - logo.image.GetHeight() / 2);
logo.sprite.SetZ(1);
```

### `scripts/install-plymouth-theme.sh`

```bash
#!/bin/bash
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

sudo mkdir -p /usr/share/plymouth/themes/nova
sudo cp "$REPO_DIR/scripts/plymouth/nova.plymouth" /usr/share/plymouth/themes/nova/
sudo cp "$REPO_DIR/scripts/plymouth/nova.script"   /usr/share/plymouth/themes/nova/
sudo cp "$REPO_DIR/assets/splash_logo.png"         /usr/share/plymouth/themes/nova/
sudo plymouth-set-default-theme nova
sudo update-initramfs -u
echo "Plymouth theme installed. Reboot to apply."
```

`update-initramfs -u` embeds the theme into the initramfs so Plymouth can display it before the root filesystem is fully mounted.

---

## Dashboard Fade-In

### Change to `main.py`

After `pygame.init()` and before the main loop, load the splash image:

```python
SPLASH_FADE_FRAMES = 36  # ~600ms at 60 FPS

splash_path = os.path.join(os.path.dirname(__file__), 'assets', 'splash_logo.png')
splash_img = cv2.imread(splash_path)
if splash_img is not None:
    splash_img = cv2.resize(splash_img, (WIDTH, HEIGHT))
splash_frame = 0
```

In the render loop, after `renderer.render_frame(canvas, snap, interp, page)` and before the pygame blit:

```python
if splash_frame < SPLASH_FADE_FRAMES and splash_img is not None:
    alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
    cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0, canvas)
    splash_frame += 1
```

If `splash_logo.png` is missing, `cv2.imread` returns `None` and the block is silently skipped.

---

## Transition Sequence

1. Power-on → Plymouth loads from initramfs, shows `splash_logo.png` centered on black
2. `_quit_plymouth(--retain-splash)` (already in `main.py`) — Plymouth releases the display while keeping the image visible until DRM is taken over
3. Sway starts, pygame takes DRM
4. Dashboard frame 0: splash at 100% opacity composited over rendered UI
5. Frames 1–35: `alpha` steps from ~0.97 → 0.03, logo fades out, dashboard fades in
6. Frame 36+: normal rendering, splash no longer composited

---

## Error Handling

- Missing `splash_logo.png`: `cv2.imread` returns `None`; `splash_frame` check is never entered; no crash, no visible change
- Plymouth not installed: `_quit_plymouth()` already catches `FileNotFoundError`; dashboard starts normally
- `update-initramfs` failure: install script uses `set -e` and stops with a clear error; old theme remains active

---

## Installation

On the Pi, after `git pull`:

```bash
bash scripts/install-plymouth-theme.sh
sudo reboot
```

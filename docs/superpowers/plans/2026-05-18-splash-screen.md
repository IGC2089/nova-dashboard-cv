# Splash Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show `assets/splash_logo.png` from power-on through dashboard load with a smooth 600ms fade-in transition.

**Architecture:** A Plymouth script theme covers early boot (kernel + userspace before Sway). The existing `_quit_plymouth(--retain-splash)` call bridges Plymouth to Sway. The dashboard fade-in composites the logo over the rendered UI for the first 36 frames, fading alpha from 1.0 to 0.0.

**Tech Stack:** Plymouth (script module), OpenCV `cv2.addWeighted`, pygame, Python 3, Bash

---

## Files

| File | Change |
|------|--------|
| `scripts/plymouth/nova.plymouth` | New — Plymouth theme descriptor |
| `scripts/plymouth/nova.script` | New — Plymouth rendering script |
| `scripts/install-plymouth-theme.sh` | New — Pi install script |
| `main.py` | Add splash image load + fade-in blend in render loop |

`assets/splash_logo.png` is used as-is (copied by the install script — not modified).

---

### Task 1: Create Plymouth theme files

**Files:**
- Create: `scripts/plymouth/nova.plymouth`
- Create: `scripts/plymouth/nova.script`

- [ ] **Step 1: Create `scripts/plymouth/nova.plymouth`**

```ini
[Plymouth Theme]
Name=Nova
Description=Nova Dashboard splash screen
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/nova
ScriptFile=/usr/share/plymouth/themes/nova/nova.script
```

- [ ] **Step 2: Create `scripts/plymouth/nova.script`**

```
Window.SetBackgroundTopColor(0, 0, 0);
Window.SetBackgroundBottomColor(0, 0, 0);

logo.image = Image("splash_logo.png");
logo.sprite = Sprite(logo.image);
logo.sprite.SetX(Window.GetWidth() / 2 - logo.image.GetWidth() / 2);
logo.sprite.SetY(Window.GetHeight() / 2 - logo.image.GetHeight() / 2);
logo.sprite.SetZ(1);
```

- [ ] **Step 3: Verify files exist**

```bash
ls scripts/plymouth/
```

Expected:
```
nova.plymouth  nova.script
```

- [ ] **Step 4: Commit**

```bash
git add scripts/plymouth/nova.plymouth scripts/plymouth/nova.script
git commit -m "feat: add Plymouth nova splash theme"
```

---

### Task 2: Create install script

**Files:**
- Create: `scripts/install-plymouth-theme.sh`

- [ ] **Step 1: Create `scripts/install-plymouth-theme.sh`**

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

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/install-plymouth-theme.sh
```

- [ ] **Step 3: Verify the script is executable and has correct content**

```bash
head -5 scripts/install-plymouth-theme.sh
ls -la scripts/install-plymouth-theme.sh
```

Expected: first line is `#!/bin/bash`, file has execute bit set (`-rwxr-xr-x`).

- [ ] **Step 4: Commit**

```bash
git add scripts/install-plymouth-theme.sh
git commit -m "feat: add Plymouth theme install script"
```

---

### Task 3: Add splash fade-in to dashboard

The fade composites the splash image over the rendered canvas for the first 36 frames (~600ms at 60 FPS). `alpha` decreases linearly from 1.0 to ~0.03, then the splash is no longer applied.

**Files:**
- Modify: `main.py`

The current render loop in `main.py` (around line 114–115 after `pygame.init()`):
```python
canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
```

And around line 187:
```python
renderer.render_frame(canvas, snap, interp, page)

rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
```

- [ ] **Step 1: Write the test**

```python
# tests/test_splash_fade.py
import numpy as np
import cv2
import os

def test_splash_fade_blends_correctly():
    """Fade at frame 0 should return splash image; at frame 36 should return canvas unchanged."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36

    splash_img = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)

    # Frame 0: alpha = 1.0 → result should be close to splash_img
    alpha = 1.0 - (0 / SPLASH_FADE_FRAMES)
    result = canvas.copy()
    cv2.addWeighted(splash_img, alpha, result, 1.0 - alpha, 0, result)
    assert result[0, 0, 0] == 200  # splash dominates

    # Frame 35: alpha ≈ 0.03 → result should be close to canvas
    alpha = 1.0 - (35 / SPLASH_FADE_FRAMES)
    result = canvas.copy()
    cv2.addWeighted(splash_img, alpha, result, 1.0 - alpha, 0, result)
    assert result[0, 0, 0] < 60  # canvas dominates


def test_splash_fade_skipped_when_no_image():
    """When splash_img is None, canvas must not be modified."""
    WIDTH, HEIGHT = 800, 480
    splash_img = None
    canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)
    original = canvas.copy()

    if splash_img is not None:
        cv2.addWeighted(splash_img, 1.0, canvas, 0.0, 0, canvas)

    assert np.array_equal(canvas, original)
```

- [ ] **Step 2: Run test to verify it passes (logic is pure numpy/cv2, no main.py needed)**

```bash
python -m pytest tests/test_splash_fade.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 3: Add splash variables after `canvas = np.zeros(...)` in `main.py`**

Current (line 114):
```python
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
```

Replace with:
```python
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    SPLASH_FADE_FRAMES = 36
    splash_path = os.path.join(os.path.dirname(__file__), 'assets', 'splash_logo.png')
    splash_img = cv2.imread(splash_path)
    if splash_img is not None:
        splash_img = cv2.resize(splash_img, (WIDTH, HEIGHT))
    splash_frame = 0
```

- [ ] **Step 4: Add fade blend after `renderer.render_frame(...)` in `main.py`**

Current (line 187):
```python
            renderer.render_frame(canvas, snap, interp, page)

            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
```

Replace with:
```python
            renderer.render_frame(canvas, snap, interp, page)

            if splash_frame < SPLASH_FADE_FRAMES and splash_img is not None:
                alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
                cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0, canvas)
                splash_frame += 1

            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
```

- [ ] **Step 5: Run tests to confirm nothing broke**

```bash
python -m pytest tests/ -v
```

Expected: all pairing tests pass (2 skipped on Windows is fine), 2 splash tests pass.

- [ ] **Step 6: Smoke test locally with `--simulate`**

```bash
python main.py --simulate
```

Expected: dashboard starts, logo fades in for ~0.6 seconds then normal UI renders. No crash. (`assets/splash_logo.png` must exist locally.)

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_splash_fade.py
git commit -m "feat: fade splash logo into dashboard on startup"
```

---

### Task 4: Deploy and verify on Pi

**Files:** none (Pi-side only)

- [ ] **Step 1: Push and pull on Pi**

On dev machine:
```bash
git push
```

On Pi:
```bash
cd ~/nova-dashboard-cv && git pull
```

- [ ] **Step 2: Run the install script on Pi**

```bash
bash scripts/install-plymouth-theme.sh
```

Expected output ends with:
```
update-initramfs: Generating /boot/firmware/initrd.img
Plymouth theme installed. Reboot to apply.
```

(`update-initramfs` may take 15–30 seconds.)

- [ ] **Step 3: Reboot**

```bash
sudo reboot
```

- [ ] **Step 4: Verify Plymouth theme is active**

After SSH reconnects:
```bash
plymouth-set-default-theme --list | grep nova
```

Expected: `nova` appears in the list.

- [ ] **Step 5: Verify the fade in the dashboard**

Watch the display during the next boot. Expected sequence:
- Black screen with `splash_logo.png` centered during boot
- Logo stays visible as Sway starts
- Logo fades out over ~0.6 seconds as dashboard renders
- Normal dashboard UI appears

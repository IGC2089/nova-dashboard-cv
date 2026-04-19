# Boot Splash Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide boot text and show a custom splash screen (`assets/splash_logo.png`) from power-on until the dashboard renders its first frame, using Plymouth with a smooth fade-out.

**Architecture:** A minimal Plymouth "script" theme is stored in the repo and deployed to `/usr/share/plymouth/themes/nova/` by a one-shot install script. `main.py` calls `plymouth quit --retain-splash` just before `pygame.init()` so Plymouth fades out while the display is handed off. Kernel cmdline suppresses all boot text.

**Tech Stack:** Plymouth (script module), Bash, Python 3 subprocess, systemd

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/plymouth/nova.plymouth` | Create | Plymouth theme metadata |
| `scripts/plymouth/nova.script` | Create | Plymouth display script (scales + centers image) |
| `scripts/install_splash.sh` | Create | One-time Pi setup: install Plymouth, deploy theme, update initramfs |
| `main.py` | Modify | Add `_quit_plymouth()` helper + call before `pygame.init()` |

`assets/splash_logo.png` already exists in the repo — no changes needed.

---

## Task 1: Plymouth theme files

**Files:**
- Create: `scripts/plymouth/nova.plymouth`
- Create: `scripts/plymouth/nova.script`

No automated tests for Plymouth config — correctness is verified by running the install script and rebooting on the Pi (covered in Task 2 steps).

- [ ] **Step 1: Create `scripts/plymouth/nova.plymouth`**

```bash
mkdir -p scripts/plymouth
```

File contents:

```ini
[Plymouth Theme]
Name=Nova Dashboard
Description=1974 Nova instrument cluster splash
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/nova
ScriptFile=/usr/share/plymouth/themes/nova/nova.script
```

- [ ] **Step 2: Create `scripts/plymouth/nova.script`**

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

- [ ] **Step 3: Commit**

```bash
git add scripts/plymouth/nova.plymouth scripts/plymouth/nova.script
git commit -m "feat: add Plymouth nova theme files for boot splash"
```

---

## Task 2: Install script

**Files:**
- Create: `scripts/install_splash.sh`

- [ ] **Step 1: Create `scripts/install_splash.sh`**

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

echo "Writing Plymouth daemon config..."
cat > /etc/plymouth/plymouthd.conf << 'EOF'
[Daemon]
Theme=nova
ShowDelay=0
EOF

echo "Updating initramfs (this takes ~30s)..."
update-initramfs -u

echo ""
echo "=== DONE ==="
echo "Now manually edit /boot/firmware/cmdline.txt:"
echo "Add to the END of the existing single line (no newline):"
echo "  quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0"
echo ""
echo "Then run: sudo reboot"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/install_splash.sh
```

- [ ] **Step 3: Verify the script references correct paths**

Check that all three source paths exist:

```bash
ls scripts/plymouth/nova.plymouth scripts/plymouth/nova.script assets/splash_logo.png
```

Expected: all three files listed without error.

- [ ] **Step 4: Commit**

```bash
git add scripts/install_splash.sh
git commit -m "feat: add Plymouth install script for boot splash setup"
```

---

## Task 3: main.py Plymouth handoff

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_quit_plymouth.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_quit_plymouth.py`:

```python
import importlib
import sys


def test_quit_plymouth_is_importable():
    """_quit_plymouth must exist as a module-level function in main."""
    import main
    assert hasattr(main, '_quit_plymouth'), \
        "_quit_plymouth not found in main.py"
    assert callable(main._quit_plymouth)


def test_quit_plymouth_safe_when_not_installed(monkeypatch):
    """_quit_plymouth must not raise when the plymouth binary is missing."""
    import main

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("plymouth not found")

    monkeypatch.setattr('subprocess.run', fake_run)
    main._quit_plymouth()  # must not raise


def test_quit_plymouth_safe_on_timeout(monkeypatch):
    """_quit_plymouth must not raise on subprocess timeout."""
    import subprocess
    import main

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=['plymouth'], timeout=2.0)

    monkeypatch.setattr('subprocess.run', fake_run)
    main._quit_plymouth()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main_quit_plymouth.py -v
```

Expected: FAIL — `AssertionError: _quit_plymouth not found in main.py`

- [ ] **Step 3: Add `import subprocess` to main.py**

In `main.py`, find the existing imports block (lines 1–12) and add `subprocess` after `signal`:

```python
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
import math
import logging
import numpy as np
import cv2
```

- [ ] **Step 4: Add `_quit_plymouth()` function to main.py**

Add after the `log = logging.getLogger('main')` line and before `TARGET_FPS`:

```python
def _quit_plymouth() -> None:
    """Signal Plymouth to fade out and release the display."""
    try:
        subprocess.run(['plymouth', 'quit', '--retain-splash'],
                       timeout=2.0, check=False, capture_output=True)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
```

- [ ] **Step 5: Call `_quit_plymouth()` before `pygame.init()` in `main()`**

In `main.py`, find the line `pygame.init()` inside `main()`. Add the call immediately before it:

```python
    _quit_plymouth()
    pygame.init()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_main_quit_plymouth.py -v
```

Expected: 3 PASSED

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS (no regressions)

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_main_quit_plymouth.py
git commit -m "feat: signal Plymouth fade-out before pygame display takeover"
```

---

## Self-Review Checklist

- [x] **Plymouth theme files** — Task 1: nova.plymouth + nova.script created with exact contents from spec
- [x] **Image centered/scaled** — nova.script uses Math.Min scale + SetX/SetY centering
- [x] **Install script** — Task 2: deploys all three files, sets theme, writes plymouthd.conf, updates initramfs
- [x] **ShowDelay=0** — written to plymouthd.conf in install script
- [x] **Cmdline edit** — intentionally manual; install script prints exact tokens to add
- [x] **main.py `_quit_plymouth()`** — Task 3: `subprocess` import + function + call before pygame.init()
- [x] **`--retain-splash`** — present in subprocess.run call
- [x] **FileNotFoundError + TimeoutExpired caught** — both in except tuple
- [x] **Tests cover failure modes** — monkeypatch for missing binary and timeout
- [x] **No automated test for Plymouth rendering** — correctly omitted (requires Pi hardware)

## Deployment (after all tasks complete)

Run on the Pi as root:

```bash
git pull
sudo bash scripts/install_splash.sh
# Manually edit /boot/firmware/cmdline.txt — add tokens shown by script
sudo reboot
```

# ⚡ ProtonLaunch — Steam Deck Edition

A streamlined Windows game installer optimized for Steam Deck. Search, configure, install, and add to Steam — all with a touch-friendly interface designed for 1280×800.

## Features

- **Steam Deck Optimized** — Native 1280×800 resolution, touch-friendly UI
- **Guided steps** — Installer EXE → Match stores / ProtonDB → Runtime & winetricks → Install → Add to Steam
- **Auto-Detect Proton** — Stock Proton, Proton-GE, or system Wine
- **Compatibility Flags** — DXVK, VKD3D, ESync, FSync, MangoHud
- **Isolated Prefixes** — Each game gets its own Wine prefix
- **Steam Integration** — One-click add to Steam library with cover art

## Requirements

- Steam Deck (SteamOS) or Linux with 1280×800 or higher resolution
- Proton installed via Steam **or** Proton-GE in `~/.steam/root/compatibilitytools.d/`
- Python 3.10+
- Dependencies: `pip install -r requirements.txt` (PyQt6, requests, vdf) — or on Steam Deck: `sudo pacman -S python-pyqt6 python-requests` and `pip install --user vdf` if you want safer Steam shortcut merging

## Quick Start

```bash
cd /path/to/protonlaunch
python3 -m protonlaunch.protonlaunch
```

Or add to Steam for Game Mode access:

1. Click **"⚙ Add Tool to Steam"** in the app
2. Restart Steam
3. Launch directly from Game Mode

## Install (Optional)

```bash
chmod +x install.sh
./install.sh
```

## Single-File Build (Steam Deck Recommended)

Build a self-contained executable (no runtime Python package layout needed):

```bash
chmod +x build_onefile.sh
./build_onefile.sh
./install.sh
```

This creates `dist/protonlaunch` and installs it to `~/.local/bin/protonlaunch`.
If no onefile binary is present, `install.sh` falls back to source/Python mode.

## Download a Ready-to-Run Binary

Tagged releases publish a single Linux binary in GitHub Releases:

- `protonlaunch-linux-x86_64`
- `protonlaunch-linux-x86_64.sha256`

On Steam Deck:

```bash
chmod +x protonlaunch-linux-x86_64
./protonlaunch-linux-x86_64
```

## How to Use

1. **Step 1 — Installer** — Browse or **drag-and-drop** your Windows setup `.exe`
2. **Step 2 — Match** — Search Steam + Lutris; status line shows whether each API succeeded. If both fail, you can still use **manual** mode and continue
3. **Step 3 — Runtime** — Proton/Wine, optional **winetricks** verbs (comma-separated), DXVK/VKD3D flags, Steam launch options
4. **Step 4 — Install** — Run the installer; pick the **installed game** `.exe` from suggested paths (or browse). Logs go to `~/.local/share/protonlaunch/logs/`
5. **Add to Steam** — Shortcut uses native + Flatpak Steam `userdata` paths when present

## Develop / test (WSL or Linux)

```bash
export PYTHONPATH=.
pip install -r requirements.txt
PYTHONIOENCODING=utf-8 python3 test_comprehensive.py
QT_QPA_PLATFORM=offscreen python3 scripts/wsl_headless_smoke.py
```

## Compatibility Flags

| Flag | Description | Recommended For |
| :--- | :--- | :--- |
| **DXVK** | DirectX 9/10/11 → Vulkan | Most games (enabled by default) |
| **VKD3D** | DirectX 12 → Vulkan | Modern DX12 titles |
| **ESync** | Event synchronization | Better CPU performance (default) |
| **FSync** | Fast synchronization | Linux 5.16+ kernels |
| **MangoHud** | Performance overlay | FPS/performance monitoring |

## Proton-GE (Recommended)

For maximum compatibility, install Proton-GE:

```bash
# Using ProtonUp-Qt
flatpak install flathub net.davidotek.pupgui2
flatpak run net.davidotek.pupgui2
```

ProtonLaunch auto-detects all installed Proton versions.

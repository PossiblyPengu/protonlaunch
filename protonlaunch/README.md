# ⚡ ProtonLaunch — Steam Deck Edition

A streamlined Windows game installer optimized for Steam Deck. Search, configure, install, and add to Steam — all with a touch-friendly interface designed for 1280×800.

## Features

- **Steam Deck Optimized** — Native 1280×800 resolution, touch-friendly UI
- **One-Flow Install** — Search game → Pick EXE → Configure → Install → Add to Steam
- **Auto-Detect Proton** — Stock Proton, Proton-GE, or system Wine
- **Compatibility Flags** — DXVK, VKD3D, ESync, FSync, MangoHud
- **Isolated Prefixes** — Each game gets its own Wine prefix
- **Steam Integration** — One-click add to Steam library with cover art

## Requirements

- Steam Deck (SteamOS) or Linux with 1280×800 or higher resolution
- Proton installed via Steam **or** Proton-GE in `~/.steam/root/compatibilitytools.d/`
- Python 3.10+
- PyQt6 (`sudo pacman -S python-pyqt6` on Steam Deck)

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

1. **Install Game** — Search for your game on Steam (for cover art), browse to your `.exe` installer
2. **Configure** — Select Proton version, enable compatibility flags
3. **Run Installer** — The Windows installer runs through Proton
4. **Add to Steam** — One click adds the game to your Steam library with proper artwork

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

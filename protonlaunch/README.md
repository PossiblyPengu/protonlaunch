# ⚡ ProtonLaunch

Install and launch Windows games on Steam Deck with one click.

## Features

- Browse and run any Windows `.exe` installer
- Choose from any detected Proton version (stock or Proton-GE)
- Falls back to system Wine if available
- Per-game compatibility flags: DXVK, VKD3D, ESync, FSync, MangoHud
- Isolated Wine prefix per game (no conflicts between games)
- Launch games directly from the app
- Add games to Steam as shortcuts (Game Mode friendly)

## Requirements

- Steam Deck (SteamOS) or any Linux distro
- Proton installed via Steam **or** Proton-GE in `~/.steam/root/compatibilitytools.d/`
- Python 3.10+
- PyQt6

## Install

```bash
chmod +x install.sh
./install.sh
```

Then run `protonlaunch` in a terminal, or find it in your app menu.

## Adding to Steam Game Mode

After installing:
1. Open Steam → **Add a Game → Add a Non-Steam Game**
2. Browse to `~/.local/bin/protonlaunch`
3. Add it — it'll appear in your library and launch from Game Mode

## Compatibility Flags

| Flag     | When to use |
|----------|-------------|
| DXVK     | Most DX9/10/11 games — huge performance boost |
| VKD3D    | DX12 games |
| ESync    | Most games — reduces CPU overhead |
| FSync    | Linux 5.16+ kernel, even better than ESync |
| MangoHud | Performance overlay (requires MangoHud installed) |

## Proton-GE

For better game compatibility, install [Proton-GE](https://github.com/GloriousEggroll/proton-ge-custom):

```bash
# Using ProtonUp-Qt (recommended)
flatpak install flathub net.davidotek.pupgui2
flatpak run net.davidotek.pupgui2
```

ProtonLaunch will automatically detect any GE versions you install.

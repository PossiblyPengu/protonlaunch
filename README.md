# ⚡ ProtonLaunch

**Install Windows programs and games on your Steam Deck. Pick the installer, and ProtonLaunch does the rest.**

1. Tap **Install a Windows program** and pick the setup `.exe` or `.msi`
2. Click through the installer as usual
3. That's it: the program shows up in ProtonLaunch and in your Steam library

ProtonLaunch does these steps for you:

- **Picks Proton:** GE-Proton if you have it, otherwise Proton Experimental or the newest Proton installed (including on the SD card). If you have no Proton at all, it offers a one-tap install through Steam.
- **Makes a separate Windows setup (prefix)** for each program, so one program can't break another
- **Finds the installed program** from the shortcuts its installer made, skipping uninstallers, redistributables and crash reporters. If it can't tell, it shows you its best guesses.
- **Adds it to Steam** for every Steam account on the Deck, under the name from the program's shortcut
- **Handles programs that need no install**: if the file *is* the program, one tap adds it as-is

## Install (Steam Deck)

1. Switch to **Desktop Mode** (hold Power → Switch to Desktop)
2. Open **Konsole** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/PossiblyPengu/protonlaunch/main/get.sh | bash
```

No pip, pacman, or developer mode needed. The script downloads the prebuilt binary and checks its checksum.

**Shortcuts:**
- In Desktop Mode, right-click any setup `.exe` → **Open With → ProtonLaunch**
- To use ProtonLaunch in Game Mode, tap **Add ProtonLaunch to Steam** at the bottom of the app

After installing something, restart Steam (Steam menu → Power → Restart Steam) so it shows up in your library.

## Where things go

| What | Where |
| :--- | :--- |
| Programs (one prefix each) | `~/.local/share/protonlaunch/prefixes/<name>/pfx/drive_c` |
| Launch scripts used by Steam | `~/.local/share/protonlaunch/launchers/` |
| Install logs | `~/.local/share/protonlaunch/logs/` |
| Backup of your Steam shortcuts | `…/userdata/<id>/config/shortcuts.vdf.protonlaunch-bak` |

**Remove** in the app deletes the program's prefix, its launcher and its Steam shortcut.

## Command line

```bash
protonlaunch                   # open the app
protonlaunch ~/Downloads/setup.exe   # open and start installing right away
```

## Develop

```bash
pip install -r requirements.txt         # just PyQt6
python3 -m protonlaunch                 # run from source
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
./protonlaunch/build_onefile.sh         # → dist/protonlaunch
```

The tests use a fake Proton, so they run anywhere, including CI. On minimal Linux images PyQt6 needs
`libegl1 libgl1 libglib2.0-0 libxkbcommon0 libdbus-1-3`.

Pushing a `v*` tag builds `protonlaunch-linux-x86_64` and publishes it to GitHub Releases, which is what `get.sh` downloads.

# ⚡ ProtonLaunch

**Install Windows programs and games on your Steam Deck. Pick the installer; the program ends up in your Steam library.**

ProtonLaunch is an installer, not a launcher: once something is installed you play it from Steam like anything else.

1. Open ProtonLaunch. Setup files in Downloads, on the Desktop or on an SD card/USB drive are already on screen. Pick one, or **Browse files**.
2. Click through the installer as usual.
3. Done: the program is in your Steam library, with its icon and library artwork.

Built for the Deck: full controller support (D-pad/stick to move, **A** select, **B** back, **X** browse, **☰** menu), big touch targets, button hints along the bottom, and full screen in Game Mode.

## What it does for you

- **Picks Proton:** GE-Proton if you have it, otherwise Proton Experimental or the newest Proton installed (including on the SD card). If you have none, it offers a one-tap install through Steam.
- **Runs Proton the way Steam does**, inside the Steam Linux Runtime, so installers that download files work. If the runtime isn't installed yet, it offers a one-tap install through Steam.
- **Gives each program its own Windows setup (prefix)**, so one program can't break another.
- **Shows your internal storage as D: in the installer.** Proton normally offers only C: and Z: ("rootfs", SteamOS's small read-only system partition), which makes installers complain about space. While installing, Z: is hidden and D: is your home folder. Z: comes back afterwards so the program runs normally.
- **Finds the installed program** from the shortcuts its installer made, skipping uninstallers, redistributables and crash reporters. If it can't tell, it shows its best guesses with their icons.
- **Adds it to Steam** for every Steam account on the Deck, using the program's own icon. It also generates library artwork (capsule, wide, hero and logo) so the program doesn't show up as a blank tile. Artwork you've added yourself (SteamGridDB, Decky…) is never overwritten.
- **Frees space afterwards:** one tap deletes the installer, including GOG-style `.bin` parts.
- **Handles programs that need no install:** if the file *is* the program, it's added as-is.

## Install (Steam Deck)

1. Switch to **Desktop Mode** (hold Power → Switch to Desktop)
2. Open **Konsole** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/PossiblyPengu/protonlaunch/main/get.sh | bash
```

No pip, pacman, or developer mode needed. The script downloads the prebuilt binary and checks its checksum.

- To use ProtonLaunch in Game Mode: **☰ Menu → Add ProtonLaunch to Steam**.
- **Updates are built in:** when a new version is out, a banner on the home screen offers **Update now**; the download is checksum-verified and ProtonLaunch restarts into it. You can also use **☰ Menu → Check for updates**, or `protonlaunch --update` in Konsole.
- In Desktop Mode you can also right-click any setup `.exe` → **Open With → ProtonLaunch**.
- After installing something, restart Steam (STEAM button → Power → Restart Steam) to see it in your library.

## Where things go

| What | Where |
| :--- | :--- |
| Installed programs (one prefix each) | `~/.local/share/protonlaunch/prefixes/<name>/pfx/drive_c` |
| Launch scripts used by Steam | `~/.local/share/protonlaunch/launchers/` |
| Install logs | `~/.local/share/protonlaunch/logs/` |
| Backup of your Steam shortcuts | `…/userdata/<id>/config/shortcuts.vdf.protonlaunch-bak` |

**Uninstalling:** Home → **Installed programs** (or ☰ Menu → Installed programs). Each program shows its size and
whether it's still in Steam. Uninstalling deletes its Windows folder (including saves kept inside it), its folder on
D: if it was installed there, and its Steam shortcut, icon and artwork. Programs you removed from Steam show up as
"Removed from Steam" so their files can be cleaned up too. Installed programs don't appear in the Desktop Mode app
menu or in Discover — only in Steam and here.

## Command line

```bash
protonlaunch                         # open the app
protonlaunch ~/Downloads/setup.exe   # open and offer to install that file
protonlaunch --update                # update ProtonLaunch itself
```

## Develop

```bash
pip install -r requirements.txt         # just PyQt6
python3 -m protonlaunch                 # run from source
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
./protonlaunch/build_onefile.sh         # → dist/protonlaunch
```

The tests use a fake Proton and fake Steam install, so they run anywhere, including CI. On minimal Linux images PyQt6 needs
`libegl1 libgl1 libglib2.0-0 libxkbcommon0 libdbus-1-3`. `PROTONLAUNCH_NO_GAMEPAD=1` turns off controller input;
`PROTONLAUNCH_FULLSCREEN=1` forces full screen outside Game Mode.

**Shipping a new version:** bump `__version__` in `protonlaunch/__init__.py`, then run
`scripts/publish_bin.sh "one line of release notes"` and commit `bin/`. That rebuilds the binary and writes
`bin/latest.json`, which `get.sh` and the in-app updater read (from `main`, then the development branch). Pushing a
`v*` tag also publishes a GitHub release; the updater checks releases too and takes whichever version is newest.
`PROTONLAUNCH_UPDATE_BASE=<url of a folder with latest.json>` points the updater elsewhere for testing.

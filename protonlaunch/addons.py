"""Deck add-ons from their official sources: Decky Loader and EmuDeck.

Nothing is repackaged. Decky's own installer (what decky.xyz links to) is downloaded and run as
is; it asks for the admin password in its own windows, so it needs Desktop Mode. EmuDeck is
downloaded the way its own install script (what emudeck.com runs) does it: the latest
EmuDeck.AppImage from its GitHub releases, into ~/Applications, and opened from there.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import core, updater

DECKY_INSTALLER_URL = ("https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/"
                       "user_install_script.sh")
EMUDECK_RELEASE_API = "https://api.github.com/repos/EmuDeck/emudeck-electron/releases/latest"


@dataclass(frozen=True)
class Addon:
    id: str
    name: str
    blurb: str
    site: str
    color: str


ADDONS = (
    Addon("decky", "Decky Loader", "Plugins for the Quick Access menu", "decky.xyz", "#6b35c8"),
    Addon("emudeck", "EmuDeck", "Sets up emulators and adds your retro games to Steam", "emudeck.com", "#d6313f"),
)


def addon(addon_id: str) -> Addon | None:
    return next((a for a in ADDONS if a.id == addon_id), None)


# ── What's installed ─────────────────────────────────────────────────────────


def decky_version(home: Path | None = None) -> str | None:
    """Decky Loader's version if it's installed ("installed" if the version is unknown), else None."""
    services = (home or Path.home()) / "homebrew/services"
    if not (services / "PluginLoader").is_file():
        return None
    try:
        return (services / ".loader.version").read_text().strip() or "installed"
    except OSError:
        return "installed"


def emudeck_app(home: Path | None = None) -> Path | None:
    p = (home or Path.home()) / "Applications/EmuDeck.AppImage"
    return p if p.is_file() else None


def emudeck_set_up(home: Path | None = None) -> bool:
    """EmuDeck has been run and has configured the emulators (it keeps its settings in ~/emudeck)."""
    return ((home or Path.home()) / "emudeck").is_dir()


def status(a: Addon, home: Path | None = None) -> str:
    if a.id == "decky":
        v = decky_version(home)
        return f"Installed ({v})" if v and v != "installed" else ("Installed" if v else "Not installed")
    if emudeck_app(home) is None:
        return "Set up already" if emudeck_set_up(home) else "Not installed"
    return "Installed" if emudeck_set_up(home) else "Downloaded — not set up yet"


# ── Desktop Mode ─────────────────────────────────────────────────────────────


def can_switch_to_desktop() -> bool:
    return shutil.which("steamos-session-select") is not None


def switch_to_desktop() -> None:
    """What the Power menu's "Switch to Desktop" does."""
    subprocess.Popen(["steamos-session-select", "plasma"], env=core.clean_env(), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


# ── Decky Loader ─────────────────────────────────────────────────────────────


def fetch_decky_installer(dest_dir: Path, fetch: Callable[[str], bytes] | None = None) -> Path:
    """Decky's own installer script, checked to be what it should be."""
    raw = (fetch or (lambda url: updater.fetch(url, timeout=60, limit=4 << 20)))(DECKY_INSTALLER_URL)
    text = raw.decode("utf-8", errors="replace")
    if not text.startswith("#!") or "Decky" not in text:
        raise core.InstallError("Decky's installer didn't download correctly (is the Deck online?).")
    dest_dir.mkdir(parents=True, exist_ok=True)
    script = dest_dir / "decky_user_install_script.sh"
    script.write_text(text, encoding="utf-8")
    script.chmod(0o755)
    return script


def run_decky_installer(script: Path, log: Callable[[str], None] = lambda s: None) -> int:
    """Run it and wait. It shows its own windows: password, release/prerelease (or update/uninstall
    when Decky is already there), and progress."""
    proc = subprocess.Popen(["bash", str(script)], env=core.clean_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, errors="replace")
    assert proc.stdout is not None
    with proc.stdout:
        for line in proc.stdout:
            if line.strip():
                log(line.rstrip())
    return proc.wait()


# ── EmuDeck ──────────────────────────────────────────────────────────────────


def emudeck_release(fetch: Callable[[str], bytes] | None = None) -> tuple[str, str]:
    """(version, AppImage URL) of EmuDeck's latest release."""
    data = json.loads((fetch or (lambda url: updater.fetch(url, timeout=30)))(EMUDECK_RELEASE_API))
    url = next((a.get("browser_download_url") for a in data.get("assets", [])
                if str(a.get("name", "")).endswith(".AppImage")), None)
    if not url:
        raise core.InstallError("Couldn't find EmuDeck's download in its latest release. Try again later.")
    return str(data.get("tag_name", "")).lstrip("v"), url


def download_emudeck(progress: Callable[[int, int], None] = lambda done, total: None,
                     fetch: Callable[[str], bytes] | None = None, opener=None, home: Path | None = None) -> str:
    """Download the latest EmuDeck.AppImage into ~/Applications. Returns its version."""
    version, url = emudeck_release(fetch)
    dest = (home or Path.home()) / "Applications/EmuDeck.AppImage"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(".EmuDeck.AppImage.download")
    try:
        with (opener or (lambda u: updater._open(u, 60)))(url) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                progress(done, total)
        with open(tmp, "rb") as f:
            if f.read(4) != b"\x7fELF":
                raise core.InstallError("The EmuDeck download was damaged. Try again.")
        tmp.chmod(0o755)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return version


def open_emudeck(home: Path | None = None) -> None:
    app = emudeck_app(home)
    if app is None:
        raise core.InstallError("EmuDeck isn't downloaded yet.")
    subprocess.Popen([str(app)], env=core.clean_env(), start_new_session=True, cwd=str(app.parent),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

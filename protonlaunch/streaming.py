"""Game streaming services as Steam shortcuts.

Cloud services (Xbox Cloud Gaming, GeForce NOW, …) run full screen in a browser; home streaming
(Moonlight, chiaki-ng) uses its own app. Either way the app comes from Flathub, installed for this
user only (no password needed), and the service ends up in Steam like an installed program: an
App with kind "stream", a launcher script, artwork, and Steam's own add-a-game hand-off.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import core

FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
CHROME, EDGE = "com.google.Chrome", "com.microsoft.Edge"
BROWSERS = (CHROME, EDGE)  # any one of them will do; Chrome is installed if neither is


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    blurb: str
    url: str = ""  # cloud services: the page to open full screen
    app: str = ""  # home streaming: the Flathub app that does it
    args: tuple[str, ...] = ()

    @property
    def is_web(self) -> bool:
        return bool(self.url)


SERVICES = (
    Service("xbox-cloud", "Xbox Cloud Gaming", "Game Pass Ultimate games, streamed", url="https://www.xbox.com/play"),
    Service("geforce-now", "GeForce NOW", "Your Steam, Epic and other PC games, streamed",
            url="https://play.geforcenow.com"),
    Service("amazon-luna", "Amazon Luna", "Luna+ and Prime Gaming, streamed", url="https://luna.amazon.com"),
    Service("boosteroid", "Boosteroid", "Your PC games, streamed", url="https://cloud.boosteroid.com"),
    Service("moonlight", "Moonlight", "Stream from your own gaming PC", app="com.moonlight_stream.Moonlight"),
    Service("chiaki-ng", "chiaki-ng", "Remote Play from your PlayStation", app="io.github.streetpea.Chiaki4deck"),
)

# Full screen at the Deck's resolution, sized for its 7" screen. Kiosk mode has no address bar;
# leave with Steam's own "Exit game".
BROWSER_ARGS = ("--kiosk", "--start-fullscreen", "--window-size=1280,800", "--force-device-scale-factor=1.25",
                "--device-scale-factor=1.25", "--no-first-run", "--no-default-browser-check")


def service(service_id: str) -> Service | None:
    return next((s for s in SERVICES if s.id == service_id), None)


# ── Flatpak ──────────────────────────────────────────────────────────────────


def _flatpak() -> str | None:
    import shutil

    return shutil.which("flatpak")


def installed_apps() -> set[str]:
    """Flatpak app ids installed for this user or system-wide."""
    exe = _flatpak()
    if not exe:
        return set()
    try:
        out = subprocess.run([exe, "list", "--app", "--columns=application"], capture_output=True, text=True,
                             timeout=30, env=core.clean_env()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def browser(installed: set[str]) -> str | None:
    return next((b for b in BROWSERS if b in installed), None)


def needs(svc: Service, installed: set[str]) -> str | None:
    """The Flathub app that must be installed first, or None."""
    if svc.is_web:
        return None if browser(installed) else CHROME
    return None if svc.app in installed else svc.app


def install_app(app_id: str, log: Callable[[str], None] = lambda s: None) -> None:
    """Install a Flathub app for this user (no admin password), adding Flathub for the user if needed."""
    exe = _flatpak()
    if not exe:
        raise core.InstallError("Flatpak isn't available on this system, so ProtonLaunch can't install "
                                f"{app_id}.")
    env = core.clean_env()
    subprocess.run([exe, "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB], env=env,
                   capture_output=True, timeout=120)
    proc = subprocess.Popen([exe, "install", "--user", "-y", "--noninteractive", "flathub", app_id], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                            errors="replace")
    tail: list[str] = []
    assert proc.stdout is not None
    with proc.stdout:
        for line in proc.stdout:
            line = line.strip()
            if line:
                tail = (tail + [line])[-8:]
                log(line)
    if proc.wait() != 0:
        raise core.InstallError(f"Couldn't install {app_id} from Flathub (is the Deck online?).\n\n"
                                + "\n".join(tail))


def allow_controllers(app_id: str) -> None:
    """Let a browser see game controllers (the Gamepad API needs udev's device info)."""
    exe = _flatpak()
    if exe:
        subprocess.run([exe, "override", "--user", "--filesystem=/run/udev:ro", app_id], env=core.clean_env(),
                       capture_output=True, timeout=60)


# ── Launchers and the Steam side ─────────────────────────────────────────────


def command(svc: Service, installed: set[str]) -> list[str]:
    if svc.is_web:
        b = browser(installed) or CHROME
        return ["flatpak", "run", b, *BROWSER_ARGS, *svc.args, svc.url]
    return ["flatpak", "run", svc.app, *svc.args]


def write_launcher(svc: Service, paths: core.Paths, installed: set[str]) -> Path:
    paths.launchers.mkdir(parents=True, exist_ok=True)
    script = paths.launchers / f"stream-{svc.id}.sh"
    log = paths.logs / f"stream-{svc.id}-launch.log"
    script.write_text(
        "#!/bin/bash\n"
        f"# ProtonLaunch: {svc.name}\n"
        f'{{ mkdir -p {shlex.quote(str(log.parent))} && exec >{shlex.quote(str(log))} 2>&1; }} || true\n'
        f"exec {' '.join(shlex.quote(c) for c in command(svc, installed))}\n",
        encoding="utf-8")
    script.chmod(0o755)
    return script


def app_for(svc: Service, paths: core.Paths) -> core.App | None:
    return next((a for a in core.Library(paths).load() if a.kind == "stream" and a.id == f"stream-{svc.id}"), None)


def set_up(svc: Service, paths: core.Paths, status: Callable[[str], None] = lambda s: None,
           roots=None) -> core.App:
    """Install what the service needs, write its launcher and add it to Steam."""
    installed = installed_apps()
    need = needs(svc, installed)
    if need:
        status(f"Installing {'Google Chrome' if need == CHROME else svc.name} from Flathub…")
        install_app(need, lambda line: status(f"Installing from Flathub…  {line[:60]}"))
        installed = installed_apps() | {need}
    if svc.is_web:
        allow_controllers(browser(installed) or CHROME)
    status("Adding to Steam…")
    launcher = write_launcher(svc, paths, installed)
    app = app_for(svc, paths) or core.App(
        id=f"stream-{svc.id}", name=svc.name, exe=str(launcher), prefix="", runtime_name="", runtime_kind="",
        runtime_path="", kind="stream")
    app.launcher = app.exe = str(launcher)
    app.installed_at = time.time()
    core.write_desktop_entry(app)
    core.add_to_steam(app, roots)
    core.Library(paths).upsert(app)
    return app

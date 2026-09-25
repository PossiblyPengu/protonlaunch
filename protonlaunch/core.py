"""ProtonLaunch engine: pick a runtime, run an installer, find the program, add it to Steam.

Nothing in here imports Qt, so it can be tested headless and reused from the CLI.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

INSTALLER_SUFFIXES = (".exe", ".msi")


# ── Paths ────────────────────────────────────────────────────────────────────


@dataclass
class Paths:
    root: Path

    @classmethod
    def default(cls) -> "Paths":
        override = os.environ.get("PROTONLAUNCH_HOME")
        if override:
            return cls(Path(override).expanduser())
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
        return cls(Path(xdg) / "protonlaunch")

    @property
    def prefixes(self) -> Path:
        return self.root / "prefixes"

    @property
    def launchers(self) -> Path:
        return self.root / "launchers"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def library_file(self) -> Path:
        return self.root / "library.json"


def clean_env() -> dict[str, str]:
    """Environment for child processes, minus anything a PyInstaller bundle injected."""
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        for key in ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "SSL_CERT_FILE"):
            orig = env.pop(key + "_ORIG", None)
            if orig is not None:
                env[key] = orig
            else:
                env.pop(key, None)
    return env


# ── Steam + runtime detection ────────────────────────────────────────────────


def steam_roots(home: Path | None = None) -> list[Path]:
    """Steam install roots (native, symlinked and Flatpak), de-duplicated."""
    home = home or Path.home()
    candidates = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]
    out: list[Path] = []
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            continue
        if (r / "steamapps").is_dir() and r not in out:
            out.append(r)
    return out


def steam_library_dirs(root: Path) -> list[Path]:
    """All Steam library folders (internal storage, SD card, …) for a Steam root."""
    dirs = [root]
    vdf_file = root / "steamapps/libraryfolders.vdf"
    try:
        text = vdf_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return dirs
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = Path(m.group(1).replace("\\\\", "\\"))
        if p.is_dir() and p not in dirs:
            dirs.append(p)
    return dirs


@dataclass
class Runtime:
    name: str
    kind: str  # "proton" or "wine"
    path: str  # proton script, or wine binary

    @property
    def is_proton(self) -> bool:
        return self.kind == "proton"

    def wineserver(self) -> str | None:
        if not self.is_proton:
            return shutil.which("wineserver")
        base = Path(self.path).parent
        for rel in ("files/bin/wineserver", "dist/bin/wineserver"):
            if (base / rel).is_file():
                return str(base / rel)
        return None


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", name)[:4])


def runtime_rank(rt: Runtime) -> tuple:
    """Higher is better: GE-Proton > Proton Experimental > Proton > Wine, newest first."""
    low = rt.name.lower()
    if not rt.is_proton:
        tier = 0
    elif "ge-proton" in low or "proton-ge" in low or low.startswith("ge"):
        tier = 3
    elif "experimental" in low:
        tier = 2
    else:
        tier = 1
    return (tier, _version_key(rt.name))


def find_runtimes(
    roots: Iterable[Path] | None = None,
    extra_tool_dirs: Iterable[Path] | None = None,
    include_system_wine: bool = True,
) -> list[Runtime]:
    """Every usable Proton/Wine, best first."""
    roots = list(steam_roots() if roots is None else roots)
    tool_dirs: list[Path] = [r / "compatibilitytools.d" for r in roots]
    if extra_tool_dirs is None:
        extra_tool_dirs = [
            Path.home() / ".steam/root/compatibilitytools.d",
            Path("/usr/share/steam/compatibilitytools.d"),
        ]
    tool_dirs.extend(extra_tool_dirs)

    found: dict[str, Runtime] = {}

    def add(script: Path, name: str) -> None:
        try:
            key = str(script.resolve())
        except OSError:
            return
        if script.is_file() and key not in found:
            found[key] = Runtime(name=name, kind="proton", path=str(script))

    for d in tool_dirs:
        if d.is_dir():
            for sub in sorted(d.iterdir()):
                add(sub / "proton", sub.name)
    for root in roots:
        for lib in steam_library_dirs(root):
            common = lib / "steamapps/common"
            if common.is_dir():
                for sub in sorted(common.iterdir()):
                    if "proton" in sub.name.lower():
                        add(sub / "proton", sub.name)

    runtimes = list(found.values())
    if include_system_wine:
        wine = shutil.which("wine")
        if wine:
            runtimes.append(Runtime(name="System Wine", kind="wine", path=wine))
    runtimes.sort(key=runtime_rank, reverse=True)
    return runtimes


# Steam app id of "Proton Experimental" — used to offer a one-tap install.
PROTON_EXPERIMENTAL_APPID = 1493710

# Steam never runs Proton directly: it runs it inside the Steam Linux Runtime container named by
# the tool's toolmanifest.vdf. The container supplies libraries (e.g. 32-bit TLS/gnutls) that
# SteamOS itself may lack; without them installers can fail to download ("no connection").
_RUNTIME_DIR_NAMES = {
    1628350: "SteamLinuxRuntime_sniper",
    1391110: "SteamLinuxRuntime_soldier",
}


def required_container_appid(proton_script: Path) -> int | None:
    try:
        text = (Path(proton_script).parent / "toolmanifest.vdf").read_text(errors="replace")
    except OSError:
        return None
    m = re.search(r'"require_tool_appid"\s+"(\d+)"', text)
    return int(m.group(1)) if m else None


def container_entry_point(proton_script: Path, roots: Iterable[Path] | None = None) -> Path | None:
    """The Steam Linux Runtime entry point Steam would run this Proton in, if installed."""
    if os.environ.get("PROTONLAUNCH_NO_CONTAINER"):
        return None
    appid = required_container_appid(proton_script)
    if appid is None:
        return None
    for root in steam_roots() if roots is None else roots:
        for lib in steam_library_dirs(root):
            names: list[str] = []
            try:
                acf = (lib / f"steamapps/appmanifest_{appid}.acf").read_text(errors="replace")
                m = re.search(r'"installdir"\s+"([^"]+)"', acf)
                if m:
                    names.append(m.group(1))
            except OSError:
                pass
            if appid in _RUNTIME_DIR_NAMES:
                names.append(_RUNTIME_DIR_NAMES[appid])
            for name in names:
                ep = lib / "steamapps/common" / name / "_v2-entry-point"
                if ep.is_file() and os.access(ep, os.X_OK):
                    return ep
    return None


# ── Naming ───────────────────────────────────────────────────────────────────

_NAME_NOISE = {
    "setup", "install", "installer", "x64", "x86", "x86_64", "win64", "win32", "64bit",
    "32bit", "amd64", "arm64", "windows", "win", "full", "final", "offline", "web",
    "release", "portable", "gog", "en", "us", "multi", "the_setup",
}


_GENERIC_STEMS = {"setup", "install", "installer", "autorun", "start", "launcher", "app"}
_GENERIC_FOLDERS = {"downloads", "download", "desktop", "home", "deck", "tmp", "temp", "documents"}


def guess_name(installer: Path | str) -> str:
    """Turn 'setup_the_witcher_3_goty_1.32_(10709).exe' into 'The Witcher 3 Goty'.

    A plain 'setup.exe' is named after the folder it's in ('Some Game [GOG]/setup.exe').
    """
    p = Path(installer)
    name = _clean_name(p.stem)
    if name.lower() in _GENERIC_STEMS and p.parent.name.lower() not in _GENERIC_FOLDERS:
        folder = _clean_name(p.parent.name)
        if folder and folder.lower() not in _GENERIC_STEMS:
            return folder
    return name


def _clean_name(stem: str) -> str:
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", stem)
    s = re.sub(r"(?i)(?<![a-z0-9])v?\d+(?:\.\d+)+[a-z]?(?![a-z0-9])", " ", s)  # 1.2.3, v2.0
    tokens: list[str] = []
    for t in re.split(r"[\s._\-+]+", s):
        if not t:
            continue
        t = re.sub(r"(?i)(?<=[a-z])(setup|installer|install)$", "", t)  # ChromeSetup
        if t.lower() in _NAME_NOISE or re.fullmatch(r"v?\d{5,}", t, re.I):
            continue
        tokens.append(t[0].upper() + t[1:] if t.islower() else t)
    return " ".join(tokens) or stem


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"


# ── Windows shortcuts (.lnk) ─────────────────────────────────────────────────


def lnk_target(data: bytes) -> str | None:
    """Windows path a .lnk points at (from its LinkInfo block), or None."""
    if len(data) < 0x4C or data[:4] != b"L\x00\x00\x00":
        return None
    try:
        (flags,) = struct.unpack_from("<I", data, 0x14)
        pos = 0x4C
        if flags & 0x01:  # HasLinkTargetIDList
            (idl_size,) = struct.unpack_from("<H", data, pos)
            pos += 2 + idl_size
        if not flags & 0x02:  # HasLinkInfo
            return None
        li = pos
        _size, header_size, li_flags, _vol, base_off = struct.unpack_from("<5I", data, li)
        if not li_flags & 0x01:  # VolumeIDAndLocalBasePath
            return None
        if header_size >= 0x24:
            (ubase_off,) = struct.unpack_from("<I", data, li + 0x1C)
            if ubase_off:
                start = li + ubase_off
                end = start
                while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                    end += 2
                return data[start:end].decode("utf-16-le", errors="replace") or None
        start = li + base_off
        end = data.index(b"\x00", start)
        return data[start:end].decode("cp1252", errors="replace") or None
    except (struct.error, ValueError):
        return None


def windows_to_unix(pfx: Path, win_path: str) -> Path | None:
    """Map 'C:\\Program Files\\X\\x.exe' into the prefix, matching case-insensitively."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", win_path.strip())
    if not m:
        return None
    drive = m.group(1).lower()
    cur = pfx / "drive_c" if drive == "c" else pfx / "dosdevices" / f"{drive}:"
    for part in re.split(r"[\\/]+", m.group(2)):
        if not part:
            continue
        nxt = cur / part
        if not nxt.exists():
            try:
                match = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
            except OSError:
                return None
            if match is None:
                return None
            nxt = match
        cur = nxt
    return cur


# ── Finding the installed program ────────────────────────────────────────────

_SKIP_DIR_NAMES = {
    "temp", "tmp", "$pluginsdir", "package cache", "common files",
    "internet explorer", "windows media player", "windows nt", "windows defender",
    "windowspowershell", "microsoft.net", "dotnet", "redist", "_commonredist",
    "directx", "vcredist", "installer", "__installer", "_installer", "support",
}
_BAD_EXE_WORDS = (
    "unins", "uninstall", "setup", "install", "redist", "vcredist", "vc_redist", "dxsetup",
    "dxwebsetup", "dotnet", "crash", "reporter", "bugreport", "update", "patcher", "helper",
    "prereq", "cleanup", "register", "activation", "notification", "service", "elevate",
    "cefprocess", "webhelper", "diagnostic", "benchmark", "7za", "unitycrash", "ue4prereq",
    "easyanticheat", "battleye", "vconsole", "dump", "repair",
)
_BAD_LNK_WORDS = ("uninstall", "readme", "manual", "help", "website", "license", "support", "remove")
_WALK_LIMIT = 20000


@dataclass
class Candidate:
    exe: Path
    score: float
    shortcut_name: str | None = None


def _start_menu_and_desktop_dirs(drive_c: Path) -> list[tuple[Path, int]]:
    """(directory, bonus) pairs where installers put shortcuts. Desktop beats Start Menu."""
    out: list[tuple[Path, int]] = []
    users = drive_c / "users"
    if users.is_dir():
        for u in users.iterdir():
            out.append((u / "Desktop", 120))
            out.append((u / "Public/Desktop", 120))
            out.append((u / "AppData/Roaming/Microsoft/Windows/Start Menu", 90))
            out.append((u / "Start Menu", 90))
    out.append((drive_c / "ProgramData/Microsoft/Windows/Start Menu", 90))
    return out


def _is_bad_exe(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in _BAD_EXE_WORDS)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 or w.isdigit()}


def scan_exes(drive_c: Path) -> list[Path]:
    """Executables a user installed (everything except Windows itself, temp and redists)."""
    found: list[Path] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(drive_c):
        seen += 1
        if seen > _WALK_LIMIT:
            break
        top = Path(dirpath) == drive_c
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in _SKIP_DIR_NAMES and not (top and d.lower() == "windows")
        ]
        for f in filenames:
            if f.lower().endswith(".exe"):
                found.append(Path(dirpath) / f)
    return found


def _same_file_contents(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                ca, cb = fa.read(1 << 20), fb.read(1 << 20)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except OSError:
        return False


def looks_like_installer(exe: Path, installer: Path | None = None) -> bool:
    """Setup/uninstall/redist tools, or a copy of the installer the user picked."""
    if _is_bad_exe(exe.name):
        return True
    if installer is not None:
        return exe.name.lower() == installer.name.lower() or _same_file_contents(exe, installer)
    return False


def snapshot_dirs(root: Path, depth: int = 3) -> set[Path]:
    """Visible directories under root, a few levels deep — to spot what an installer created."""
    out: set[Path] = set()
    seen = 0
    for dirpath, dirnames, _files in os.walk(root):
        seen += 1
        if seen > _WALK_LIMIT:
            break
        cur = Path(dirpath)
        level = len(cur.relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")] if level < depth else []
        out.update(cur / d for d in dirnames)
    return out


def new_top_dirs(before: set[Path], after: set[Path]) -> list[Path]:
    """Directories in `after` that didn't exist before, without their own subfolders."""
    new = after - before
    return sorted(d for d in new if d.parent not in new)


def find_program(
    pfx: Path,
    name_hint: str = "",
    installer: Path | None = None,
    extra_dirs: Iterable[Path] = (),
) -> list[Candidate]:
    """Rank the installed executables in a prefix by how likely each is 'the program'. Best first.

    `extra_dirs` are folders the installer created outside C: (e.g. on D:, the home folder).
    Copies of the installer itself are never returned: the goal is the finished product.
    """
    drive_c = pfx / "drive_c"
    if not drive_c.is_dir():
        return []
    cands: dict[Path, Candidate] = {}
    hint = _words(name_hint)

    def cand(p: Path) -> Candidate:
        key = p.resolve()
        if key not in cands:
            cands[key] = Candidate(exe=p, score=0.0)
        return cands[key]

    found = [(exe, drive_c) for exe in scan_exes(drive_c)]
    for d in extra_dirs:
        # An installer-created folder is like "Program Files\X": score from the same depth.
        found += [(exe, d.parent.parent) for exe in scan_exes(d)]
    for exe, base in found:
        c = cand(exe)
        rel = exe.relative_to(base)
        c.score -= 3 * (len(rel.parts) - 1)
        try:
            size_mb = exe.stat().st_size / 1_000_000
        except OSError:
            size_mb = 0
        c.score += min(25.0, 5 * max(0.0, size_mb) ** 0.5)
        if rel.parts and rel.parts[0].lower().startswith("program files"):
            c.score += 10
        if "shipping" in exe.name.lower():
            c.score += 10

    for d, bonus in _start_menu_and_desktop_dirs(drive_c):
        if not d.is_dir():
            continue
        for lnk in d.rglob("*.lnk"):
            if any(w in lnk.stem.lower() for w in _BAD_LNK_WORDS):
                continue
            try:
                target = lnk_target(lnk.read_bytes())
            except OSError:
                continue
            if not target or not target.lower().endswith(".exe"):
                continue
            exe = windows_to_unix(pfx, target)
            if exe is None or not exe.is_file():
                continue
            c = cand(exe)
            if c.shortcut_name is None or bonus > 100:
                c.shortcut_name = lnk.stem
            c.score += bonus

    if installer is not None:
        for key in [k for k, c in cands.items() if _same_file_contents(c.exe, installer)]:
            del cands[key]

    for c in cands.values():
        if _is_bad_exe(c.exe.name):
            c.score -= 200
        overlap = hint & (_words(c.exe.stem) | _words(c.exe.parent.name) | _words(c.shortcut_name or ""))
        c.score += 20 * len(overlap)
        if installer is not None and c.exe.name.lower() == installer.name.lower():
            c.score -= 100

    return sorted(cands.values(), key=lambda c: c.score, reverse=True)


# ── Binary VDF (Steam shortcuts.vdf) ─────────────────────────────────────────


class U64(int):
    """Marks a 64-bit VDF value so it round-trips with the right type tag."""


class I64(int):
    pass


def vdf_loads(data: bytes) -> dict:
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = data.index(b"\x00", pos)
        s = data[pos:end].decode("utf-8", errors="surrogateescape")
        pos = end + 1
        return s

    def parse_map() -> dict:
        nonlocal pos
        out: dict = {}
        while True:
            if pos >= len(data):
                raise ValueError("truncated VDF")
            t = data[pos]
            pos += 1
            if t == 0x08:
                return out
            key = cstr()
            if t == 0x00:
                out[key] = parse_map()
            elif t == 0x01:
                out[key] = cstr()
            elif t == 0x02:
                (out[key],) = struct.unpack_from("<i", data, pos)
                pos += 4
            elif t == 0x03:
                (out[key],) = struct.unpack_from("<f", data, pos)
                pos += 4
            elif t == 0x07:
                out[key] = U64(struct.unpack_from("<Q", data, pos)[0])
                pos += 8
            elif t == 0x0A:
                out[key] = I64(struct.unpack_from("<q", data, pos)[0])
                pos += 8
            else:
                raise ValueError(f"unsupported VDF type 0x{t:02x}")

    result = parse_map()
    return result


def vdf_dumps(obj: dict) -> bytes:
    out = bytearray()

    def key(k: str) -> bytes:
        return str(k).encode("utf-8", errors="surrogateescape") + b"\x00"

    def dump_map(m: dict) -> None:
        for k, v in m.items():
            if isinstance(v, dict):
                out.extend(b"\x00" + key(k))
                dump_map(v)
            elif isinstance(v, str):
                out.extend(b"\x01" + key(k) + v.encode("utf-8", errors="surrogateescape") + b"\x00")
            elif isinstance(v, U64):
                out.extend(b"\x07" + key(k) + struct.pack("<Q", v))
            elif isinstance(v, I64):
                out.extend(b"\x0a" + key(k) + struct.pack("<q", v))
            elif isinstance(v, float):
                out.extend(b"\x03" + key(k) + struct.pack("<f", v))
            elif isinstance(v, int):
                out.extend(b"\x02" + key(k) + struct.pack("<I", v & 0xFFFFFFFF))
            else:
                raise TypeError(f"cannot encode {type(v).__name__} in VDF")
        out.append(0x08)

    dump_map(obj)
    return bytes(out)


def shortcut_appid(exe_field: str, name: str) -> int:
    """The id Steam itself gives a non-Steam shortcut (so artwork tools recognise it)."""
    return (zlib.crc32((exe_field + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def _signed32(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def steam_user_config_dirs(roots: Iterable[Path] | None = None) -> list[Path]:
    out: list[Path] = []
    for root in steam_roots() if roots is None else roots:
        ud = root / "userdata"
        if not ud.is_dir():
            continue
        for d in sorted(ud.iterdir()):
            if d.name.isdigit() and d.name != "0" and d.is_dir():
                cfg = (d / "config").resolve()
                if cfg not in out:
                    out.append(cfg)
    return out


def _edit_shortcuts(cfg: Path, edit: Callable[[list[dict]], list[dict]]) -> None:
    f = cfg / "shortcuts.vdf"
    if f.exists():
        raw = f.read_bytes()
        data = vdf_loads(raw) if raw.strip(b"\x00\x08") else {}
        backup = f.with_suffix(".vdf.protonlaunch-bak")
        if not backup.exists():
            backup.write_bytes(raw)
    else:
        data = {}
    sc = data.get("shortcuts")
    entries = list(sc.values()) if isinstance(sc, dict) else []
    entries = edit(entries)
    data["shortcuts"] = {str(i): e for i, e in enumerate(entries)}
    cfg.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".vdf.tmp")
    tmp.write_bytes(vdf_dumps(data))
    os.replace(tmp, f)


def _entry_appid(e: dict) -> int:
    v = e.get("appid", e.get("appId", 0))
    return int(v) & 0xFFFFFFFF if isinstance(v, int) else 0


def add_steam_shortcut(
    name: str,
    exe: str,
    start_dir: str,
    icon: str = "",
    roots: Iterable[Path] | None = None,
) -> tuple[int, int]:
    """Add (or replace) a non-Steam shortcut for every Steam user. Returns (appid, users updated)."""
    exe_field = f'"{exe}"'
    appid = shortcut_appid(exe_field, name)
    entry = {
        "appid": _signed32(appid),
        "AppName": name,
        "Exe": exe_field,
        "StartDir": f'"{start_dir}"',
        "icon": icon,
        "ShortcutPath": "",
        "LaunchOptions": "",
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {},
    }
    updated = 0
    for cfg in steam_user_config_dirs(roots):
        try:
            _edit_shortcuts(
                cfg,
                lambda es: [e for e in es if _entry_appid(e) != appid and e.get("Exe") != exe_field] + [entry],
            )
            updated += 1
        except (OSError, ValueError, TypeError):
            continue
    return appid, updated


def remove_steam_shortcut(appid: int, roots: Iterable[Path] | None = None) -> None:
    for cfg in steam_user_config_dirs(roots):
        if not (cfg / "shortcuts.vdf").exists():
            continue
        try:
            _edit_shortcuts(cfg, lambda es: [e for e in es if _entry_appid(e) != appid])
        except (OSError, ValueError, TypeError):
            continue


# ── Library ──────────────────────────────────────────────────────────────────


@dataclass
class App:
    id: str
    name: str
    exe: str
    prefix: str
    runtime_name: str
    runtime_kind: str
    runtime_path: str
    launcher: str = ""
    steam_appid: int = 0
    installed_at: float = field(default_factory=time.time)

    @property
    def runtime(self) -> Runtime:
        return Runtime(self.runtime_name, self.runtime_kind, self.runtime_path)


class Library:
    def __init__(self, paths: Paths):
        self.paths = paths

    def load(self) -> list[App]:
        try:
            raw = json.loads(self.paths.library_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        known = set(App.__dataclass_fields__)
        return [App(**{k: v for k, v in item.items() if k in known}) for item in raw if isinstance(item, dict)]

    def save(self, apps: list[App]) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        tmp = self.paths.library_file.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(a) for a in apps], indent=2), encoding="utf-8")
        os.replace(tmp, self.paths.library_file)

    def upsert(self, app: App) -> None:
        apps = [a for a in self.load() if a.id != app.id]
        apps.append(app)
        self.save(apps)

    def remove(self, app_id: str) -> None:
        self.save([a for a in self.load() if a.id != app_id])

    def unique_id(self, name: str) -> str:
        base = slugify(name)
        taken = {a.id for a in self.load()}
        if self.paths.prefixes.is_dir():
            taken |= {p.name for p in self.paths.prefixes.iterdir()}
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        return slug


# ── Running things ───────────────────────────────────────────────────────────


def runtime_env(
    rt: Runtime,
    compat_dir: Path,
    steam_root: Path | None,
    mounts: Iterable[Path] = (),
) -> dict[str, str]:
    env = clean_env()
    env["WINEPREFIX"] = str(compat_dir / "pfx")
    env.setdefault("WINEDEBUG", "-all")
    if rt.is_proton:
        env["STEAM_COMPAT_DATA_PATH"] = str(compat_dir)
        # Steam always sets these. Without them GE-Proton's protonfixes looks for a number in
        # STEAM_COMPAT_DATA_PATH and crashes before running anything if there is none.
        env.setdefault("SteamAppId", "0")
        env.setdefault("SteamGameId", "0")
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(steam_root or Path.home() / ".steam/steam")
        # Make Proton itself and anything outside the home folder visible inside the container.
        env["STEAM_COMPAT_TOOL_PATHS"] = str(Path(rt.path).parent)
        extra = [str(m) for m in mounts]
        if extra:
            env["STEAM_COMPAT_MOUNTS"] = ":".join(extra)
    return env


def run_command(rt: Runtime, target: str | Path, *extra: str, entry: Path | None = None) -> list[str]:
    """Command line that runs a Windows .exe/.msi (unix or Windows path) under the runtime.

    With `entry` (a Steam Linux Runtime entry point) Proton runs inside the container, exactly
    as Steam launches games.
    """
    target = str(target)
    args = ["msiexec", "/i", target] if target.lower().endswith(".msi") else [target, *extra]
    if not rt.is_proton:
        return [rt.path, *args]
    if entry is not None:
        return [str(entry), "--verb=waitforexitandrun", "--", rt.path, "waitforexitandrun", *args]
    return [rt.path, "run", *args]


# ── Drive letters ────────────────────────────────────────────────────────────
#
# Proton maps only C: (the prefix) and Z: (the whole filesystem, "/"). On SteamOS "/" is the
# small read-only system partition ("rootfs"), so installers that look at Z: — or that default
# to the drive they were started from — report "not enough space". While installing we hide Z:,
# expose the home folder (where the free space is) as D:, and start the installer from there.

HOME_DRIVE = "d"
INSTALLER_DRIVE = "e"  # only used when the installer lives outside the home folder


def _dosdevices(pfx: Path) -> Path:
    return pfx / "dosdevices"


def map_drive(pfx: Path, letter: str, target: Path) -> None:
    link = _dosdevices(pfx) / f"{letter}:"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_symlink() and os.readlink(link) == str(target):
            return
        link.unlink()
    os.symlink(str(target), link)


def to_windows_path(letter: str, root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return f"{letter.upper()}:\\" + "\\".join(rel.parts)


def hide_system_drive(pfx: Path) -> str | None:
    """Remove Z: for the duration of an install. Returns its old target for restore_system_drive."""
    z = _dosdevices(pfx) / "z:"
    if not z.is_symlink():
        return None
    target = os.readlink(z)
    z.unlink()
    return target


def restore_system_drive(pfx: Path, target: str | None) -> None:
    if target is None:
        return
    z = _dosdevices(pfx) / "z:"
    if not z.is_symlink() and not z.exists():
        os.symlink(target, z)


def free_space(path: Path) -> int:
    """Free bytes on the filesystem holding path (or its nearest existing parent)."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def write_launcher(
    app: App,
    paths: Paths,
    steam_root: Path | None,
    roots: Iterable[Path] | None = None,
) -> Path:
    """A shell script Steam can run directly. It re-finds Proton if the saved one was removed,
    and runs it inside the Steam Linux Runtime like Steam does (plain Proton if that's missing)."""
    paths.launchers.mkdir(parents=True, exist_ok=True)
    script = paths.launchers / f"{app.id}.sh"
    compat = Path(app.prefix)
    q = shlex.quote
    lines = [
        "#!/bin/bash",
        "# ProtonLaunch launcher for " + " ".join(app.name.split()),
        f"export WINEPREFIX={q(str(compat / 'pfx'))}",
        f"cd {q(str(Path(app.exe).parent))} || exit 1",
    ]
    if app.runtime_kind == "proton":
        client = str(steam_root or Path.home() / ".steam/steam")
        entry = container_entry_point(Path(app.runtime_path), roots)
        lines += [
            f"export STEAM_COMPAT_DATA_PATH={q(str(compat))}",
            'export SteamAppId="${SteamAppId:-0}" SteamGameId="${SteamGameId:-0}"',
            f"export STEAM_COMPAT_CLIENT_INSTALL_PATH={q(client)}",
            f"PROTON={q(app.runtime_path)}",
            'if [ ! -x "$PROTON" ]; then',
            "  # Saved Proton is gone (updated/removed): use the newest one still installed.",
            '  PROTON=$(ls -d "$HOME"/.steam/root/compatibilitytools.d/*/proton '
            '"$HOME"/.local/share/Steam/compatibilitytools.d/*/proton '
            '"$HOME"/.local/share/Steam/steamapps/common/Proton*/proton 2>/dev/null | sort -V | tail -n 1)',
            "fi",
            'export STEAM_COMPAT_TOOL_PATHS="$(dirname "$PROTON")"',
            f"ENTRY={q(str(entry or ''))}",
            'if [ -n "$ENTRY" ] && [ -x "$ENTRY" ] && [ -z "$PROTONLAUNCH_NO_CONTAINER" ]; then',
            f'  exec "$ENTRY" --verb=waitforexitandrun -- "$PROTON" waitforexitandrun {q(app.exe)} "$@"',
            "fi",
            f'exec "$PROTON" run {q(app.exe)} "$@"',
        ]
    else:
        lines.append(f'exec {q(app.runtime_path)} {q(app.exe)} "$@"')
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


class Cancelled(Exception):
    pass


class InstallError(Exception):
    pass


@dataclass
class PendingInstall:
    """Result of running an installer: everything needed to finish, plus ranked guesses."""

    id: str
    name: str
    installer: Path
    compat_dir: Path
    runtime: Runtime
    candidates: list[Candidate]
    log_file: Path

    @property
    def pfx(self) -> Path:
        return self.compat_dir / "pfx"


class Installer:
    """Runs one installer end-to-end. Call run(), then finish() with the chosen exe."""

    def __init__(
        self,
        installer: Path,
        paths: Paths | None = None,
        runtime: Runtime | None = None,
        steam_root: Path | None = None,
        status: Callable[[str], None] = lambda s: None,
        log: Callable[[str], None] = lambda s: None,
        steam_roots_override: list[Path] | None = None,
        allow_no_container: bool = False,
    ):
        self.installer = Path(installer).expanduser().resolve()
        self.paths = paths or Paths.default()
        self.home = Path.home().resolve()
        self.entry: Path | None = None
        self._tail: collections.deque[str] = collections.deque(maxlen=12)
        self.allow_no_container = allow_no_container
        self.library = Library(self.paths)
        self._roots = steam_roots() if steam_roots_override is None else steam_roots_override
        self.steam_root = steam_root or (self._roots[0] if self._roots else None)
        self.runtime = runtime
        self.status = status
        self._log_cb = log
        self._log_fh = None
        self._proc: subprocess.Popen | None = None
        self._cancelled = False
        self._skip_wait = False
        self.stage = "idle"
        self._env: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _set(self, stage: str, text: str) -> None:
        self.stage = stage
        self.status(text)

    # logging
    def _log(self, msg: str) -> None:
        self._tail.append(msg.rstrip("\n"))
        if self._log_fh:
            self._log_fh.write(msg.rstrip("\n") + "\n")
            self._log_fh.flush()
        self._log_cb(msg.rstrip("\n"))

    def _stream(self, cmd: list[str]) -> int:
        self._log("$ " + " ".join(shlex.quote(c) for c in cmd))
        with self._lock:
            if self._cancelled:
                raise Cancelled()
            self._proc = subprocess.Popen(
                cmd,
                env=self._env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                errors="replace",
                start_new_session=True,
            )
        assert self._proc.stdout is not None
        with self._proc.stdout:
            for line in self._proc.stdout:
                self._log(line)
        rc = self._proc.wait()
        with self._lock:
            self._proc = None
        return rc

    def _kill_wine(self) -> None:
        ws = self.runtime.wineserver() if self.runtime else None
        if ws and self._env:
            subprocess.run([ws, "-k"], env=self._env, timeout=30, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass

    def cancel(self) -> None:
        """Abort: close every window of the installer and throw the prefix away."""
        self._cancelled = True
        threading.Thread(target=self._kill_wine, daemon=True).start()

    def continue_now(self) -> None:
        """Stop waiting for leftover windows (e.g. the app the installer auto-started)."""
        self._skip_wait = True
        threading.Thread(target=self._kill_wine, daemon=True).start()

    def run(self) -> PendingInstall:
        if not self.installer.is_file():
            raise InstallError(f"File not found: {self.installer}")
        if self.installer.suffix.lower() not in INSTALLER_SUFFIXES:
            raise InstallError("Pick a Windows installer (.exe or .msi).")

        self._set("prepare", "Getting ready…")
        if self.runtime is None:
            runtimes = find_runtimes(self._roots)
            if not runtimes:
                raise InstallError("NO_RUNTIME")
            self.runtime = runtimes[0]

        if self.runtime.is_proton and not self.allow_no_container:
            need = required_container_appid(Path(self.runtime.path))
            if need and container_entry_point(Path(self.runtime.path), self._roots) is None:
                raise InstallError(f"NO_CONTAINER:{need}")

        name = guess_name(self.installer)
        app_id = self.library.unique_id(name)
        compat = self.paths.prefixes / app_id
        compat.mkdir(parents=True, exist_ok=True)
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        log_file = self.paths.logs / f"{app_id}.log"
        self._log_fh = open(log_file, "w", encoding="utf-8")
        mounts = [p for p in (self.installer.parent, self.paths.root) if not p.is_relative_to(self.home)]
        self._env = runtime_env(self.runtime, compat, self.steam_root, mounts)
        self.entry = container_entry_point(Path(self.runtime.path), self._roots) if self.runtime.is_proton else None
        self._log(f"ProtonLaunch: installing {self.installer.name} as '{name}'")
        self._log(f"Runtime: {self.runtime.name} ({self.runtime.path})")
        if self.entry:
            self._log(f"Container: {self.entry.parent.name} (same as Steam)")
        elif self.runtime.is_proton and required_container_appid(Path(self.runtime.path)):
            self._log("Warning: the Steam Linux Runtime this Proton needs isn't installed; running "
                      "Proton directly. Downloads inside installers may fail.")

        pfx = compat / "pfx"
        hidden_z: str | None = None
        ws = self.runtime.wineserver()
        try:
            # 1. Create the Windows environment first, so its drives can be adjusted.
            self._set("prepare", "Setting up Windows… (takes a minute the first time)")
            self._stream(run_command(self.runtime, "cmd.exe", "/c", "exit", entry=self.entry))
            if ws:
                self._stream([ws, "-w"])
            if self._cancelled:
                raise Cancelled()
            if not (pfx / "system.reg").exists():
                tail = "\n".join(line for line in self._tail if not line.startswith("$ "))[-1500:]
                raise InstallError(f"{self.runtime.name} failed to start, so the installer never ran.\n\n"
                                   f"Last lines of the log:\n{tail}")

            # 2. Show the home folder as D: and hide the full system drive Z: (see HOME_DRIVE).
            home = self.home
            map_drive(pfx, HOME_DRIVE, home)
            try:
                target = to_windows_path(HOME_DRIVE, home, self.installer)
            except ValueError:
                map_drive(pfx, INSTALLER_DRIVE, self.installer.parent)
                target = to_windows_path(INSTALLER_DRIVE, self.installer.parent, self.installer)
            hidden_z = hide_system_drive(pfx)
            self._log(f"Drives: C: = {pfx / 'drive_c'} ({human_size(free_space(pfx))} free), "
                      f"D: = {home} ({human_size(free_space(home))} free); Z: hidden")
            home_before = snapshot_dirs(home)

            # 3. Run the installer.
            self._set("installer", "Running the installer — follow the steps on screen.\n"
                      f"Install to C: or D: (both have {human_size(free_space(home))} free).")
            rc = self._stream(run_command(self.runtime, target, entry=self.entry))
            self._log(f"Installer exited with code {rc}")
            if self._cancelled:
                raise Cancelled()

            if ws and not self._skip_wait:
                self._set("wait", "Waiting for the installer's windows to close…")
                self._stream([ws, "-w"])
            if self._cancelled:
                raise Cancelled()
            restore_system_drive(pfx, hidden_z)
            hidden_z = None

            self._set("scan", "Finding the installed program…")
            extra = [d for d in new_top_dirs(home_before, snapshot_dirs(home))
                     if not d.resolve().is_relative_to(self.paths.root.resolve())]
            if extra:
                self._log("New folders outside C: " + ", ".join(map(str, extra)))
            cands = find_program(pfx, name, self.installer, extra)
            self._log("Candidates: " + ", ".join(f"{c.exe.name}={c.score:.0f}" for c in cands[:8]))
            return PendingInstall(app_id, name, self.installer, compat, self.runtime, cands, log_file)
        except Cancelled:
            self._log("Cancelled.")
            self.close()
            shutil.rmtree(compat, ignore_errors=True)
            raise
        except InstallError:
            self.close()
            shutil.rmtree(compat, ignore_errors=True)
            raise
        except BaseException:
            self.close()
            raise
        finally:
            if compat.exists():
                restore_system_drive(pfx, hidden_z)

    def close(self) -> None:
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    def finish(self, pending: PendingInstall, exe: Path, name: str | None = None) -> App:
        """Save the app, write its launcher and add it to Steam."""
        self._set("steam", "Adding to Steam…")
        app = App(
            id=pending.id,
            name=" ".join((name or "").split()) or pending.name,
            exe=str(Path(exe).resolve()),
            prefix=str(pending.compat_dir),
            runtime_name=pending.runtime.name,
            runtime_kind=pending.runtime.kind,
            runtime_path=pending.runtime.path,
        )
        launcher = write_launcher(app, self.paths, self.steam_root, self._roots)
        app.launcher = str(launcher)
        app.steam_appid, users = add_steam_shortcut(
            app.name, str(launcher), str(Path(app.exe).parent), roots=self._roots
        )
        if not users:
            app.steam_appid = 0
        self.library.upsert(app)
        self._log(f"Installed '{app.name}' → {app.exe} (Steam users updated: {users})")
        self.close()
        return app


def adopt_portable(pending: PendingInstall) -> Path:
    """For a program that needs no installing: copy it into the prefix and use it directly."""
    dest_dir = pending.pfx / "drive_c/Program Files" / pending.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / pending.installer.name
    shutil.copy2(pending.installer, dest)
    return dest


def best_name(pending: PendingInstall, chosen: Candidate | None) -> str:
    """Prefer a clean Start Menu/Desktop shortcut name over the one guessed from the file name."""
    if chosen and chosen.shortcut_name and len(chosen.shortcut_name) > 2:
        return chosen.shortcut_name
    return pending.name


def is_confident(cands: list[Candidate], installer: Path | None = None) -> bool:
    """True when the top guess is safe to add to Steam without asking.

    Never true for anything that looks like a setup/uninstall tool or the installer itself.
    """
    return bool(cands) and cands[0].score > -100 and not looks_like_installer(cands[0].exe, installer)


def launch(app: App) -> subprocess.Popen:
    return subprocess.Popen([app.launcher], env=clean_env(), start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def uninstall(app: App, paths: Paths, roots: Iterable[Path] | None = None) -> None:
    if app.steam_appid:
        remove_steam_shortcut(app.steam_appid, roots)
    shutil.rmtree(app.prefix, ignore_errors=True)
    for f in (Path(app.launcher), paths.logs / f"{app.id}.log"):
        try:
            f.unlink()
        except OSError:
            pass
    Library(paths).remove(app.id)


def steam_is_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-x", "steam"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False

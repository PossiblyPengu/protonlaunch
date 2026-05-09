import json
import os
import re
import shutil
import struct
import subprocess
import urllib.request
import urllib.parse
import zlib
from pathlib import Path

# Common winetricks verbs for Windows installers / games (unattended -q).
# Add more in the UI later if needed; heavy verbs (dotnet48) are intentionally omitted.
DEFAULT_WINETRICKS_VERBS = ["vcrun2019", "corefonts"]


def resolve_steam_root() -> Path | None:
    """
    Return the Steam installation root (contains steamapps/, userdata/).
    Tries env, standard Linux/SteamOS paths, and Flatpak Steam (desktop).
    """
    candidates: list[Path] = []
    env_p = (os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH") or "").strip()
    if env_p:
        candidates.append(Path(env_p).expanduser())
    home = Path.home()
    candidates.extend(
        [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".steam/root",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ]
    )
    seen: set[Path] = set()
    for raw in candidates:
        if not raw:
            continue
        try:
            p = raw.resolve()
        except OSError:
            continue
        if p in seen:
            continue
        seen.add(p)
        if (p / "steamapps").is_dir():
            return p
    return None


def steam_shortcut_appid(name: str, exe: str) -> int:
    """Stable 32-bit id for shortcuts.vdf (Python built-in hash() is salted per process)."""
    h = zlib.crc32(f"{name}\0{exe}".encode("utf-8", errors="replace")) & 0xFFFFFFFF
    # Avoid 0; some Steam clients treat it oddly
    return h if h else 1

# ── Paths (imported from main if needed) ──
# These should be passed in or imported as needed

def steam_search(query: str) -> list:
    url = "https://store.steampowered.com/api/storesearch/?" + urllib.parse.urlencode(
        {"term": query, "l": "english", "cc": "US"}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode()).get("items", [])
    except Exception:
        return []


# Friendly names for Lutris provider_games.service values
_LUTRIS_STORE_LABELS = {
    "steam": "Steam",
    "gog": "GOG",
    "epic": "Epic",
    "amazon": "Amazon",
    "humblebundle": "Humble",
    "battlenet": "Battle.net",
    "origin": "EA",
    "ea_app": "EA",
    "uplay": "Ubisoft",
    "itchio": "itch.io",
    "zoomplatform": "ZOOM",
    "legacy": "Legacy Games",
    "square_enix": "Square Enix",
    "egs": "Epic",
    "igdb": "IGDB",
}


def lutris_search(query: str, limit: int = 12) -> list[dict]:
    """
    Search Lutris.net (aggregates Steam, GOG, Epic, Amazon, Humble, Battle.net, etc.).
    Each hit may include a linked Steam app id for ProtonDB / Steam store metadata.
    """
    q = (query or "").strip()
    if not q:
        return []
    url = "https://lutris.net/api/games?" + urllib.parse.urlencode(
        {"search": q, "page_size": min(max(limit, 1), 50)}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.3"})
        with urllib.request.urlopen(req, timeout=14) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return []

    out: list[dict] = []
    for g in (data.get("results") or [])[:limit]:
        providers = g.get("provider_games") or []
        steam_appid = None
        for p in providers:
            if p.get("service") == "steam":
                slug = str(p.get("slug") or "")
                if slug.isdigit():
                    steam_appid = int(slug)
                    break

        labels: list[str] = []
        seen: set[str] = set()
        non_igdb = [p for p in providers if p.get("service") != "igdb"]
        use = non_igdb if non_igdb else providers
        for p in use:
            svc = p.get("service") or ""
            lab = _LUTRIS_STORE_LABELS.get(svc)
            if not lab:
                lab = svc.replace("_", " ").strip().title() if svc else ""
            if lab and lab not in seen:
                seen.add(lab)
                labels.append(lab)
        if not labels:
            labels = ["Lutris"]

        out.append(
            {
                "kind": "lutris",
                "lutris_id": g.get("id"),
                "name": g.get("name") or "Unknown",
                "steam_appid": steam_appid,
                "coverart_url": g.get("coverart") or g.get("banner_url") or "",
                "year": g.get("year"),
                "display_suffix": ", ".join(labels[:6]),
                "platforms": [
                    x.get("name") for x in (g.get("platforms") or []) if x.get("name")
                ],
            }
        )
    return out


def combined_store_search(
    query: str,
    max_steam: int = 6,
    max_lutris: int = 10,
) -> list[dict]:
    """Merge Steam store search with Lutris (multi-platform) hits; dedupe by Steam app id."""
    q = (query or "").strip()
    if not q:
        return []
    merged: list[dict] = []
    steam_ids: set[int] = set()

    for it in steam_search(q)[:max_steam]:
        sid = it.get("id")
        try:
            sid_int = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid_int = None
        if sid_int is not None:
            steam_ids.add(sid_int)
        merged.append(
            {
                "kind": "steam",
                "id": sid_int if sid_int is not None else sid,
                "name": it.get("name", "Unknown"),
                "display_suffix": "Steam",
            }
        )

    for hit in lutris_search(q, limit=max_lutris + len(steam_ids)):
        lsid = hit.get("steam_appid")
        if lsid is not None and lsid in steam_ids:
            continue
        merged.append(hit)

    return merged[: max_steam + max_lutris]


def download_cover_from_url(url: str, dest: Path) -> str:
    """Download remote cover art; return path or "" on failure."""
    if not url:
        return ""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return str(dest)
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.3"})
        with urllib.request.urlopen(req, timeout=14) as r:
            dest.write_bytes(r.read())
        return str(dest)
    except Exception:
        return ""


def steam_app_details(appid: int) -> dict:
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        entry = data.get(str(appid), {})
        if entry.get("success"):
            return entry["data"]
    except Exception:
        pass
    return {}

def fetch_protondb_summary(appid: int) -> dict:
    """Official ProtonDB aggregate summary for a Steam app (community tier, confidence)."""
    url = f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.2"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def suggest_deck_compatibility(
    protondb_summary: dict,
    steam_data: dict,
) -> dict:
    """
    Heuristic compatibility preset for SteamOS / Steam Deck, informed by ProtonDB tier
    and store text (e.g. DirectX 12 → VKD3D). Not a substitute for reading ProtonDB reports.
    """
    tier = (protondb_summary.get("tier") or "").lower()
    best = (protondb_summary.get("bestReportedTier") or "").lower()
    confidence = (protondb_summary.get("confidence") or "").lower()

    text_blob = " ".join(
        filter(
            None,
            [
                steam_data.get("short_description", ""),
                steam_data.get("detailed_description", ""),
                steam_data.get("about_the_game", ""),
                (steam_data.get("pc_requirements") or {}).get("minimum", ""),
                (steam_data.get("pc_requirements") or {}).get("recommended", ""),
            ],
        )
    )
    text_lower = re.sub(r"<[^>]+>", " ", text_blob).lower()
    dx12 = bool(
        re.search(
            r"directx\s*12|\bdx12\b|d3d12|vulkan required for",
            text_lower,
        )
    )

    # Steam Deck / modern SteamOS: fsync is generally safe and beneficial
    out = {
        "dxvk": True,
        "vkd3d": dx12,
        "esync": True,
        "fsync": True,
        "mangohud": False,
        "launch_options": "",
        "protondb_tier": tier or None,
        "protondb_best": best or None,
        "protondb_confidence": confidence or None,
        "note": "",
    }

    if tier in ("borked", "bronze"):
        out["mangohud"] = True
        out["note"] = (
            "ProtonDB reports are rough for this title. Use MangoHud to watch performance, "
            "try Proton Experimental or GE, and read the Steam Deck tab on ProtonDB."
        )
    elif tier == "silver":
        out["note"] = (
            "Mixed reports on ProtonDB. Check the Steam Deck filter on ProtonDB for Deck-specific tips."
        )
    elif tier in ("gold", "platinum"):
        out["note"] = "Community tier looks good; defaults below match typical Steam Deck setups."
    elif tier:
        out["note"] = "Review Steam Deck reports on ProtonDB before a long play session."

    if confidence == "low" and not out["note"]:
        out["note"] = "Few ProtonDB reports — treat suggestions as a starting point."

    return out


def download_cover(appid: int, covers_dir: Path) -> str:
    dest = covers_dir / f"{appid}.jpg"
    if dest.exists():
        return str(dest)
    for url in (
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ProtonLaunch/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                dest.write_bytes(r.read())
            return str(dest)
        except Exception:
            continue
    return ""

def resolve_prefix_layout(prefix_root: Path) -> tuple[Path, Path]:
    """
    Proton expects STEAM_COMPAT_DATA_PATH on a parent folder and WINEPREFIX on .../pfx
    (Steam compatdata layout). Legacy flat prefixes (system.reg next to game id) are kept.
    """
    prefix_root = Path(prefix_root)
    prefix_root.mkdir(parents=True, exist_ok=True)
    pfx = prefix_root / "pfx"
    legacy_reg = prefix_root / "system.reg"
    if (pfx / "system.reg").exists():
        return prefix_root, pfx
    if legacy_reg.exists():
        return prefix_root, prefix_root
    pfx.mkdir(parents=True, exist_ok=True)
    return prefix_root, pfx


def wine_proton_env(
    game: dict,
    steam_dir: Path,
    compat_path: Path,
    wineprefix_path: Path,
) -> dict[str, str]:
    """Environment for Proton/Wine runs (installer, launcher, winetricks)."""
    env: dict[str, str] = {
        "WINEPREFIX": str(wineprefix_path),
        "STEAM_COMPAT_DATA_PATH": str(compat_path),
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(steam_dir),
        "LC_ALL": "C.UTF-8",
    }
    parts: list[str] = []
    if game.get("dxvk"):
        parts.append("d3d9,d3d10core,d3d11,dxgi=n,b")
    if game.get("vkd3d"):
        parts.append("d3d12=n,b")
    if parts:
        env["WINEDLLOVERRIDES"] = ";".join(parts)
    if game.get("esync"):
        env["PROTON_NO_ESYNC"] = "0"
        env["WINEESYNC"] = "1"
    if game.get("fsync"):
        env["PROTON_NO_FSYNC"] = "0"
        env["WINEFSYNC"] = "1"
    if game.get("mangohud"):
        env["MANGOHUD"] = "1"
    return env


def proton_dist_bin_dir(proton_script: Path) -> Path | None:
    """Directory containing Proton's wine binary (for winetricks / PATH)."""
    base = proton_script.resolve().parent
    for rel in ("files/bin", "dist/bin"):
        d = base / rel
        if (d / "wine").is_file():
            return d
        if (d / "wine64").is_file():
            return d
    return None


def is_system_wine_binary(proton_bin: str) -> bool:
    low = proton_bin.lower()
    return "wine" in low and "proton" not in low and "proton" not in Path(proton_bin).parent.name.lower()


def winetricks_available() -> bool:
    return shutil.which("winetricks") is not None


def _proton_name_sort_key(name: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", name)[:6]]
    pad = nums + [0] * (6 - len(nums))
    return tuple(pad)


def recommend_proton_key(versions: dict[str, str], meta: dict | None) -> str | None:
    """
    Pick a reasonable Proton/Wine entry from detected versions using ProtonDB tier heuristics.
    """
    if not versions:
        return None
    keys = [k for k in versions.keys()]
    tier = ""
    if meta:
        tier = ((meta.get("protondb") or {}).get("tier") or "").lower()

    ge = [k for k in keys if "(GE)" in k or "GE" in k]
    experimental = [k for k in keys if "experimental" in k.lower()]
    stock = [
        k
        for k in keys
        if k != "System Wine" and "(GE)" not in k and "experimental" not in k.lower()
    ]
    system_wine = [k for k in keys if k == "System Wine"]

    def newest(cands: list[str]) -> str | None:
        if not cands:
            return None
        return max(cands, key=_proton_name_sort_key)

    if tier in ("borked", "bronze"):
        pick = newest(ge) or newest(experimental) or newest(stock)
        if pick:
            return pick
    if tier == "silver":
        pick = newest(experimental) or newest(ge) or newest(stock)
        if pick:
            return pick
    if tier in ("gold", "platinum", "pending", ""):
        pick = newest(experimental) or newest(stock) or newest(ge)
        if pick:
            return pick

    pick = newest(experimental) or newest(ge) or newest(stock) or (system_wine[0] if system_wine else None)
    return pick or keys[0]


def run_winetricks_for_prefix(
    verbs: list[str],
    game: dict,
    proton_bin: str,
    steam_dir: Path,
    prefix_root: Path,
) -> tuple[bool, str]:
    """Run winetricks -q with the same env Proton uses. verbs e.g. vcrun2019, corefonts."""
    wt = shutil.which("winetricks")
    if not wt or not verbs:
        return True, "skipped"
    compat, wine_pfx = resolve_prefix_layout(prefix_root)
    env = os.environ.copy()
    env.update(wine_proton_env(game, steam_dir, compat, wine_pfx))
    env["WINETRICKS_UNATTENDED"] = "1"

    if not is_system_wine_binary(proton_bin):
        wdir = proton_dist_bin_dir(Path(proton_bin))
        if wdir:
            env["PATH"] = str(wdir) + os.pathsep + env.get("PATH", "")

    cmd = [wt, "-q", *verbs]
    try:
        r = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "")[-2500:]
            return False, f"winetricks failed ({r.returncode}): {tail}"
        return True, "ok"
    except subprocess.TimeoutExpired:
        return False, "winetricks timed out after 1 hour."
    except Exception as e:
        return False, str(e)


def find_proton_versions(steam_dir: Path, proton_ge_dir: Path) -> dict:
    versions = {}
    for path in steam_dir.glob("steamapps/common/Proton*"):
        if (path / "proton").exists():
            versions[path.name] = str(path / "proton")
    if proton_ge_dir.exists():
        for path in proton_ge_dir.iterdir():
            if (path / "proton").exists():
                versions[f"{path.name} (GE)"] = str(path / "proton")
    wine = shutil.which("wine")
    if wine:
        versions["System Wine"] = wine
    return versions

def build_launcher_script(game: dict, prefixes_dir: Path, data_dir: Path, steam_dir: Path) -> str:
    prefix_root = prefixes_dir / game["id"]
    compat, wine_pfx = resolve_prefix_layout(prefix_root)
    script_path = data_dir / f"launch_{game['id']}.sh"
    proton_bin = game["proton_bin"]
    exe = game["exe"]
    is_wine = is_system_wine_binary(proton_bin)
    env_map = wine_proton_env(game, steam_dir, compat, wine_pfx)
    env_lines = [f'export {k}="{v}"' for k, v in env_map.items()]
    launch_cmd = f'"{proton_bin}" "{exe}"' if is_wine else f'"{proton_bin}" run "{exe}"'
    script_path.write_text("#!/bin/bash\n" + "\n".join(env_lines) + f"\n\n{launch_cmd}\n")
    script_path.chmod(0o755)
    return str(script_path)

def write_steam_shortcut(
    name: str,
    exe: str,
    icon: str,
    steam_dir: Path,
    launch_options: str = "",
) -> tuple:
    userdata_dirs = list(steam_dir.glob("userdata/*/config/"))
    if not userdata_dirs:
        return False, "No Steam userdata found. Is Steam installed and logged in?"
    for config_dir in userdata_dirs:
        shortcuts_file = config_dir / "shortcuts.vdf"
        try:
            def s(key, val):
                return b"\x01" + key.encode() + b"\x00" + val.encode("utf-8") + b"\x00"
            def u(key, val):
                return b"\x02" + key.encode() + b"\x00" + struct.pack("<I", val & 0xFFFFFFFF)

            appid = steam_shortcut_appid(name, exe)
            body = (
                u("appid", appid) +
                s("AppName", name) +
                s("Exe", f'"{exe}"') +
                s("StartDir", str(Path(exe).parent)) +
                s("icon", icon) +
                s("ShortcutPath", "") +
                s("LaunchOptions", launch_options) +
                u("IsHidden", 0) +
                u("AllowDesktopConfig", 1) +
                u("AllowOverlay", 1) +
                u("OpenVR", 0) +
                u("LastPlayTime", 0) +
                b"\x08"
            )
            if shortcuts_file.exists():
                raw = shortcuts_file.read_bytes()
                idx = raw.count(b"AppName\x00")
                entry = b"\x00" + str(idx).encode() + b"\x00" + body
                raw = raw.rstrip(b"\x08")
                shortcuts_file.write_bytes(raw + entry + b"\x08")
            else:
                entry = b"\x00" + b"0" + b"\x00" + body
                shortcuts_file.write_bytes(b"\x00shortcuts\x00" + entry + b"\x08")
            return True, "Added! Restart Steam to see it in your library."
        except Exception as e:
            return False, str(e)
    return False, "No Steam config directories found."
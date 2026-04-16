import json
import os
import re
import shutil
import struct
import urllib.request
import urllib.parse
from pathlib import Path

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
    prefix = prefixes_dir / game["id"]
    prefix.mkdir(parents=True, exist_ok=True)
    script_path = data_dir / f"launch_{game['id']}.sh"
    proton_bin = game["proton_bin"]
    exe = game["exe"]
    is_wine = "wine" in proton_bin.lower() and "proton" not in proton_bin.lower()
    env_lines = [
        f'export WINEPREFIX="{prefix}"',
        f'export STEAM_COMPAT_DATA_PATH="{prefix}"',
        f'export STEAM_COMPAT_CLIENT_INSTALL_PATH="{steam_dir}"',
    ]
    if game.get("dxvk"):    env_lines.append('export WINEDLLOVERRIDES="d3d9,d3d10core,d3d11,dxgi=n,b"')
    if game.get("vkd3d"):   env_lines.append('export WINEDLLOVERRIDES="${WINEDLLOVERRIDES};d3d12=n,b"')
    if game.get("esync"):   env_lines.extend(['export PROTON_NO_ESYNC=0', 'export WINEESYNC=1'])
    if game.get("fsync"):   env_lines.extend(['export PROTON_NO_FSYNC=0', 'export WINEFSYNC=1'])
    if game.get("mangohud"):env_lines.append('export MANGOHUD=1')
    launch_cmd = f'"{proton_bin}" "{exe}"' if is_wine else f'"{proton_bin}" run "{exe}"'
    script_path.write_text("#!/bin/bash\n" + "\n".join(env_lines) + f"\n\n{launch_cmd}\n")
    script_path.chmod(0o755)
    return str(script_path)

def write_steam_shortcut(name: str, exe: str, icon: str, steam_dir: Path) -> tuple:
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

            appid = abs(hash(name + exe)) % (2 ** 32)
            body = (
                u("appid", appid) +
                s("AppName", name) +
                s("Exe", f'"{exe}"') +
                s("StartDir", str(Path(exe).parent)) +
                s("icon", icon) +
                s("ShortcutPath", "") +
                s("LaunchOptions", "") +
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
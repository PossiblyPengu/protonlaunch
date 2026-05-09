from PyQt6.QtCore import QThread, pyqtSignal
import re
import zlib
from datetime import datetime
from pathlib import Path

# Import helpers as needed
from protonlaunch.helpers.helpers import (
    steam_app_details,
    download_cover,
    download_cover_from_url,
    wine_proton_env,
    fetch_protondb_summary,
    suggest_deck_compatibility,
    combined_store_search_with_diagnostics,
    resolve_prefix_layout,
    run_winetricks_for_prefix,
    DEFAULT_WINETRICKS_VERBS,
    is_system_wine_binary,
    winetricks_available,
)

class SearchWorker(QThread):
    results_ready = pyqtSignal(list, dict)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        results, diag = combined_store_search_with_diagnostics(self.query)
        self.results_ready.emit(results, diag)

class DetailsWorker(QThread):
    """Resolve metadata from a search pick: Steam row or Lutris (multi-store) row."""
    ready = pyqtSignal(dict, str)
    def __init__(self, pick: dict, covers_dir):
        super().__init__(); self.pick = pick; self.covers_dir = Path(covers_dir)
    def run(self):
        pick = self.pick
        kind = pick.get("kind")
        steam_id = None
        if kind == "steam":
            sid = pick.get("id")
            try:
                steam_id = int(sid) if sid is not None else None
            except (TypeError, ValueError):
                steam_id = None
        elif kind == "lutris":
            steam_id = pick.get("steam_appid")
            if steam_id is not None:
                try:
                    steam_id = int(steam_id)
                except (TypeError, ValueError):
                    steam_id = None

        store_label = pick.get("display_suffix", "")

        if kind == "manual":
            name = (pick.get("name") or "").strip() or "Game"
            deck = suggest_deck_compatibility({}, {})
            deck["note"] = (
                "Manual title only — no store lookup. Defaults are generic; adjust flags as needed."
            )
            meta = {
                "steam_appid": None,
                "description": "",
                "genres": "",
                "developer": "",
                "publisher": "",
                "release_date": "",
                "cover_path": "",
                "protondb": {},
                "deck_suggest": deck,
                "store_source": "Manual",
            }
            self.ready.emit(meta, "")
            return

        if steam_id is not None:
            details = steam_app_details(steam_id)
            cover = download_cover(steam_id, self.covers_dir)
            protondb = fetch_protondb_summary(steam_id)
            meta = {}
            if details:
                meta = {
                    "steam_appid": steam_id,
                    "description": re.sub(r"<[^>]+>", "", details.get("short_description", "")),
                    "genres": ", ".join(g["description"] for g in details.get("genres", [])),
                    "developer": ", ".join(details.get("developers", [])),
                    "publisher": ", ".join(details.get("publishers", [])),
                    "release_date": details.get("release_date", {}).get("date", ""),
                    "cover_path": cover,
                    "protondb": protondb,
                    "deck_suggest": suggest_deck_compatibility(protondb, details),
                    "store_source": "Steam" if kind == "steam" else store_label,
                }
            elif protondb:
                meta = {
                    "steam_appid": steam_id,
                    "cover_path": cover,
                    "protondb": protondb,
                    "deck_suggest": suggest_deck_compatibility(protondb, {}),
                    "store_source": store_label,
                }
            self.ready.emit(meta, cover)
            return

        # Lutris hit without a Steam id (e.g. GOG/Epic-only linkage missing on Lutris)
        cover = ""
        lid = pick.get("lutris_id")
        url = pick.get("coverart_url") or ""
        if url:
            if lid is not None:
                safe = lid
            else:
                safe = zlib.crc32((pick.get("name") or "x").encode("utf-8", errors="replace"))
            cover = download_cover_from_url(url, self.covers_dir / f"lutris_{safe}_cover.jpg")
        plat = ", ".join((pick.get("platforms") or [])[:8])
        blurb = [f"Stores: {store_label}." if store_label else "Multi-platform listing (Lutris)."]
        if plat:
            blurb.append(f"Platforms: {plat}.")
        blurb.append(
            "No Steam app id is linked, so ProtonDB and the Steam store blurb are unavailable. "
            "If the game is on Steam, choose a “Steam” row above or search the exact Steam title."
        )
        deck = suggest_deck_compatibility({}, {})
        deck["note"] = (
            "No Steam / ProtonDB entry for this pick. These are generic SteamOS-friendly defaults."
        )
        meta = {
            "steam_appid": None,
            "description": " ".join(blurb),
            "genres": "",
            "developer": "",
            "publisher": "",
            "release_date": str(pick["year"]) if pick.get("year") else "",
            "cover_path": cover,
            "protondb": {},
            "deck_suggest": deck,
            "store_source": store_label,
        }
        self.ready.emit(meta, cover or "")

class InstallerWorker(QThread):
    done = pyqtSignal(bool, str)
    phase = pyqtSignal(str)

    def __init__(self, game, prefixes_dir, steam_dir, log_path: str | None = None):
        super().__init__()
        self.game = game
        self.prefixes_dir = prefixes_dir
        self.steam_dir = steam_dir
        self.log_path = log_path

    def _log(self, message: str) -> None:
        if not self.log_path:
            return
        try:
            p = Path(self.log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            line = f"{datetime.now().isoformat()} {message}\n"
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def run(self):
        import os
        import subprocess

        try:
            prefix_root = Path(self.prefixes_dir) / self.game["id"]
            compat, wine_pfx = resolve_prefix_layout(prefix_root)
            proton_bin = self.game["proton_bin"]
            exe = self.game["exe"]
            is_wine = is_system_wine_binary(proton_bin)
            self._log(f"start game_id={self.game['id']} proton={proton_bin} installer={exe}")
            if not Path(proton_bin).is_file() or not Path(exe).is_file():
                self._log("abort: missing proton or installer exe")
                self.done.emit(False, "Invalid executable or Proton/Wine binary.")
                return

            if self.game.get("install_winetricks"):
                if not winetricks_available():
                    self._log("abort: winetricks missing")
                    self.done.emit(
                        False,
                        "winetricks is not installed (needed for redistributables). "
                        "On SteamOS try: sudo pacman -S winetricks",
                    )
                    return
                verbs = self.game.get("winetricks_verbs") or list(DEFAULT_WINETRICKS_VERBS)
                self._log(f"winetricks verbs={verbs}")
                self.phase.emit(
                    "Installing Windows redistributables via winetricks (may take several minutes)…"
                )
                ok_wt, msg_wt = run_winetricks_for_prefix(
                    verbs,
                    self.game,
                    proton_bin,
                    Path(self.steam_dir),
                    prefix_root,
                )
                self._log(f"winetricks done ok={ok_wt} msg={msg_wt[:500]!r}")
                if not ok_wt:
                    self.done.emit(False, msg_wt)
                    return

            self.phase.emit("Running the Windows installer…")
            env = os.environ.copy()
            env.update(wine_proton_env(self.game, Path(self.steam_dir), compat, wine_pfx))
            cmd = [proton_bin, exe] if is_wine else [proton_bin, "run", exe]
            self._log(f"installer cmd={cmd}")
            result = subprocess.run(cmd, env=env)
            self._log(f"installer exit_code={result.returncode}")
            self.done.emit(result.returncode == 0, "Installer finished.")
        except Exception as e:
            self._log(f"exception {e!r}")
            self.done.emit(False, str(e))
from PyQt6.QtCore import QThread, pyqtSignal
import re
from pathlib import Path

# Import helpers as needed
from protonlaunch.helpers.helpers import steam_search, steam_app_details, download_cover

class SearchWorker(QThread):
    results_ready = pyqtSignal(list)
    def __init__(self, query):
        super().__init__(); self.query = query
    def run(self):
        self.results_ready.emit(steam_search(self.query)[:8])

class DetailsWorker(QThread):
    ready = pyqtSignal(dict, str)
    def __init__(self, appid, covers_dir):
        super().__init__(); self.appid = appid; self.covers_dir = covers_dir
    def run(self):
        details = steam_app_details(self.appid)
        cover   = download_cover(self.appid, self.covers_dir)
        meta = {}
        if details:
            meta = {
                "steam_appid":  self.appid,
                "description":  re.sub(r"<[^>]+>", "", details.get("short_description", "")),
                "genres":       ", ".join(g["description"] for g in details.get("genres", [])),
                "developer":    ", ".join(details.get("developers", [])),
                "publisher":    ", ".join(details.get("publishers", [])),
                "release_date": details.get("release_date", {}).get("date", ""),
                "cover_path":   cover,
            }
        self.ready.emit(meta, cover)

class InstallerWorker(QThread):
    done = pyqtSignal(bool, str)
    def __init__(self, game, prefixes_dir, steam_dir):
        super().__init__(); self.game = game; self.prefixes_dir = prefixes_dir; self.steam_dir = steam_dir
    def run(self):
        import os, subprocess
        try:
            prefix = self.prefixes_dir / self.game["id"]
            prefix.mkdir(parents=True, exist_ok=True)
            proton_bin = self.game["proton_bin"]
            exe = self.game["exe"]
            is_wine = "wine" in proton_bin.lower() and "proton" not in proton_bin.lower()
            env = os.environ.copy()
            env.update({
                "WINEPREFIX": str(prefix),
                "STEAM_COMPAT_DATA_PATH": str(prefix),
                "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.steam_dir),
            })
            if self.game.get("esync"): env["WINEESYNC"] = "1"
            if self.game.get("fsync"): env["WINEFSYNC"] = "1"
            # Security: Validate exe and proton_bin are files
            if not Path(proton_bin).is_file() or not Path(exe).is_file():
                self.done.emit(False, "Invalid executable or Proton/Wine binary.")
                return
            cmd = [proton_bin, exe] if is_wine else [proton_bin, "run", exe]
            result = subprocess.run(cmd, env=env)
            self.done.emit(result.returncode == 0, "Installer finished.")
        except Exception as e:
            self.done.emit(False, str(e))
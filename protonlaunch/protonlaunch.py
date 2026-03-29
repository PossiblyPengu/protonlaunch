#!/usr/bin/env python3

# ProtonLaunch — Windows game installer for Steam Deck


import sys
import os
import json
import subprocess
import shutil
import re
import struct
import urllib.request
import urllib.parse
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt

# Import helpers and logic modules
from protonlaunch.helpers.helpers import (
    find_proton_versions, load_games, save_games, build_launcher_script, write_steam_shortcut
)
from protonlaunch.logic.workers import InstallerWorker
from protonlaunch.ui.add_game_dialog import AddGameDialog
from protonlaunch.ui.game_card import GameCard

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME          = Path.home()
DATA_DIR      = HOME / ".local" / "share" / "protonlaunch"
PREFIXES_DIR  = DATA_DIR / "prefixes"
COVERS_DIR    = DATA_DIR / "covers"
CONFIG_FILE   = DATA_DIR / "games.json"
STEAM_DIR     = HOME / ".steam" / "steam"
PROTON_GE_DIR = HOME / ".steam" / "root" / "compatibilitytools.d"
SELF_SCRIPT   = Path(__file__).resolve()

for d in (DATA_DIR, PREFIXES_DIR, COVERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Stylesheet ────────────────────────────────────────────────────────────────
STYLE = """
QMainWindow, QDialog { background-color: #0e0e12; }
QWidget {
    background-color: #0e0e12; color: #e8e6e3;
    font-family: 'Liberation Sans', 'Cantarell', sans-serif; font-size: 14px;
}
QPushButton {
    background-color: #1e1e28; color: #e8e6e3;
    border: 1px solid #2e2e3e; border-radius: 6px;
    padding: 8px 18px; font-size: 13px; font-weight: bold;
}
QPushButton:hover  { background-color: #252535; border-color: #4fc3f7; color: #4fc3f7; }
QPushButton:pressed { background-color: #0a1929; }
QPushButton#primary {
    background-color: #0d47a1; border-color: #1565c0;
    color: #fff; padding: 12px 24px; font-size: 14px;
}
QPushButton#primary:hover { background-color: #1565c0; border-color: #4fc3f7; }
QPushButton#danger  { background-color: #1a0a0a; border-color: #5a1a1a; color: #ef9a9a; }
QPushButton#danger:hover  { background-color: #2a1010; border-color: #e57373; color: #e57373; }
QPushButton#launch  { background-color: #0a2a0a; border-color: #1b5e20; color: #a5d6a7; }
QPushButton#launch:hover  { background-color: #0f3a0f; border-color: #66bb6a; color: #66bb6a; }
QPushButton#steam   { background-color: #0d1b2a; border-color: #1a3a5c; color: #7db9e8; }
QPushButton#steam:hover   { background-color: #102236; border-color: #4fc3f7; color: #4fc3f7; }
QComboBox {
    background-color: #1a1a22; border: 1px solid #2e2e3e;
    border-radius: 6px; padding: 8px 12px; color: #e8e6e3; min-height: 36px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a22; border: 1px solid #2e2e3e;
    selection-background-color: #0d47a1; color: #e8e6e3;
}
QLineEdit {
    background-color: #1a1a22; border: 1px solid #2e2e3e;
    border-radius: 6px; padding: 8px 12px; color: #e8e6e3; min-height: 36px;
}
QLineEdit:focus { border-color: #4fc3f7; }
QCheckBox { color: #b0bec5; spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border: 1px solid #3e3e50;
    border-radius: 3px; background-color: #1a1a22;
}
QCheckBox::indicator:checked { background-color: #0d47a1; border-color: #4fc3f7; }
QScrollArea { border: none; background-color: transparent; }
QScrollBar:vertical { background-color: #1a1a22; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background-color: #3e3e50; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background-color: #4fc3f7; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QListWidget {
    background-color: #1a1a22; border: 1px solid #2e2e3e; border-radius: 6px; color: #e8e6e3;
}
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #22222e; }
QListWidget::item:selected { background-color: #0d47a1; color: #fff; }
QListWidget::item:hover:!selected { background-color: #1e1e2c; }
QTextEdit {
    background-color: #1a1a22; border: 1px solid #2e2e3e;
    border-radius: 6px; color: #b0bec5; font-size: 12px; padding: 6px;
}
QLabel { background-color: transparent; }
"""


# ── Main Window ───────────────────────────────────────────────────────────────

class ProtonLaunch(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProtonLaunch")
        self.setMinimumSize(820, 600)
        self.games = load_games(CONFIG_FILE)
        self.proton_versions = find_proton_versions(STEAM_DIR, PROTON_GE_DIR)
        self.worker = None
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #0a0a10; border-bottom: 1px solid #1e1e2c;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        logo = QLabel("⚡ PROTONLAUNCH")
        logo.setStyleSheet("font-size: 19px; font-weight: bold; letter-spacing: 4px; color: #4fc3f7;")
        hl.addWidget(logo)
        hl.addStretch()

        # "Add ProtonLaunch to Steam" in header
        self_steam_btn = QPushButton("＋ Add ProtonLaunch to Steam")
        self_steam_btn.setObjectName("steam")
        self_steam_btn.clicked.connect(self._add_self_to_steam)
        hl.addWidget(self_steam_btn)

        if self.proton_versions:
            st = QLabel(f"  {len(self.proton_versions)} backend(s) found")
            st.setStyleSheet("color: #a5d6a7; font-size: 12px;")
        else:
            st = QLabel("  ⚠ No Proton/Wine found")
            st.setStyleSheet("color: #ef9a9a; font-size: 12px;")
        hl.addWidget(st)
        root.addWidget(header)

        # Body
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 18)
        bl.setSpacing(14)

        action_bar = QHBoxLayout()
        add_btn = QPushButton("＋  Install New Game")
        add_btn.setObjectName("primary")
        add_btn.setMinimumHeight(46)
        add_btn.clicked.connect(self._open_add_dialog)
        action_bar.addWidget(add_btn)
        action_bar.addStretch()
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #555; font-size: 12px;")
        action_bar.addWidget(self.count_label)
        bl.addLayout(action_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.games_container = QWidget()
        self.games_layout = QVBoxLayout(self.games_container)
        self.games_layout.setSpacing(10)
        self.games_layout.setContentsMargins(0, 0, 0, 0)
        self.games_layout.addStretch()
        self.scroll.setWidget(self.games_container)
        bl.addWidget(self.scroll)
        root.addWidget(body)

    def _refresh(self):
        while self.games_layout.count() > 1:
            item = self.games_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for game in self.games:
            card = GameCard(game)
            card.launched.connect(self._launch_game)
            card.removed.connect(self._remove_game)
            card.added_to_steam.connect(self._add_game_to_steam)
            self.games_layout.insertWidget(self.games_layout.count() - 1, card)
        n = len(self.games)
        self.count_label.setText(f"{n} game{'s' if n != 1 else ''}")
        if not self.games:
            empty = QLabel("No games yet.\nClick  ＋ Install New Game  to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #444; font-size: 15px; padding: 60px;")
            self.games_layout.insertWidget(0, empty)

    def _open_add_dialog(self):
        dlg = AddGameDialog(self, self.proton_versions, covers_dir=COVERS_DIR)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_game_data()
            uid = re.sub(r'\W+', '_', data["name"].lower()).strip('_')
            existing = {g["id"] for g in self.games}
            base, c = uid, 2
            while uid in existing:
                uid = f"{base}_{c}"; c += 1
            data["id"] = uid
            self._run_installer(data)

    def _run_installer(self, game):
        self._progress = QProgressDialog(
            f"Running installer for {game['name']}…\n\nComplete any windows that appear.",
            "Hide", 0, 0, self
        )
        self._progress.setWindowTitle("Installing…")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setMinimumWidth(420)
        self._progress.show()
        # Security: Validate exe and proton_bin are files before running
        from pathlib import Path
        if not Path(game["proton_bin"]).is_file() or not Path(game["exe"]).is_file():
            self._progress.close()
            QMessageBox.critical(self, "Invalid Executable", "The selected Proton/Wine binary or installer is not a valid file.")
            return
        self.worker = InstallerWorker(game, PREFIXES_DIR, STEAM_DIR)
        self.worker.done.connect(lambda ok, msg: self._on_install_done(ok, msg, game))
        self.worker.start()

    def _on_install_done(self, ok, msg, game):
        self._progress.close()
        proceed = ok
        if not ok:
            reply = QMessageBox.question(
                self, "Installation",
                f"{msg}\n\nAdd '{game['name']}' to your library anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            proceed = (reply == QMessageBox.StandardButton.Yes)
        if proceed:
            game["launcher_script"] = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
            self.games.append(game)
            save_games(self.games, CONFIG_FILE)
            self._refresh()
            QMessageBox.information(self, "Added", f"'{game['name']}' is now in your library.")

    def _launch_game(self, game_id):
        game = next((g for g in self.games if g["id"] == game_id), None)
        if not game: return
        script = game.get("launcher_script")
        from pathlib import Path
        if not script or not Path(script).exists():
            game["launcher_script"] = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
            save_games(self.games, CONFIG_FILE)
            script = game["launcher_script"]
        try:
            subprocess.Popen([script])
        except Exception as e:
            QMessageBox.critical(self, "Launch Failed", str(e))

    def _remove_game(self, game_id):
        game = next((g for g in self.games if g["id"] == game_id), None)
        if not game: return
        if QMessageBox.question(
            self, "Remove Game",
            f"Remove '{game['name']}' from the library?\n\nWine prefix and game files will NOT be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            script = game.get("launcher_script")
            from pathlib import Path
            if script: Path(script).unlink(missing_ok=True)
            self.games = [g for g in self.games if g["id"] != game_id]
            save_games(self.games, CONFIG_FILE)
            self._refresh()

    def _add_game_to_steam(self, game_id):
        game = next((g for g in self.games if g["id"] == game_id), None)
        if not game: return
        from pathlib import Path
        if not game.get("launcher_script") or not Path(game["launcher_script"]).exists():
            game["launcher_script"] = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
            save_games(self.games, CONFIG_FILE)
        ok, msg = write_steam_shortcut(game["name"], game["launcher_script"], game.get("cover_path", ""), STEAM_DIR)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Steam Shortcut", msg)

    def _add_self_to_steam(self):
        """Add ProtonLaunch itself as a Non-Steam shortcut for Game Mode access."""
        launcher = DATA_DIR / "protonlaunch-launcher.sh"
        launcher.write_text(f"#!/bin/bash\npython3 '{SELF_SCRIPT}'\n")
        launcher.chmod(0o755)
        ok, msg = write_steam_shortcut("ProtonLaunch", str(launcher), "", STEAM_DIR)
        if ok:
            QMessageBox.information(
                self, "ProtonLaunch Added to Steam",
                f"{msg}\n\nYou can now launch ProtonLaunch directly from Game Mode."
            )
        else:
            QMessageBox.warning(self, "Failed", msg)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ProtonLaunch")
    win = ProtonLaunch()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

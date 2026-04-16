#!/usr/bin/env python3

# ProtonLaunch — Windows game installer for Steam Deck
# Simple install tool: Search game → Pick EXE → Configure → Install → Add to Steam

import sys
import os
import time
import shutil
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QMessageBox, QProgressDialog, QDialog,
    QLineEdit, QComboBox, QCheckBox, QGridLayout, QListWidget, QListWidgetItem,
    QTextEdit, QFileDialog, QStackedWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

# Import helpers and logic modules
from protonlaunch.helpers.helpers import (
    find_proton_versions, build_launcher_script, write_steam_shortcut,
    steam_search, steam_app_details, download_cover
)
from protonlaunch.logic.workers import InstallerWorker, SearchWorker, DetailsWorker

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME          = Path.home()
DATA_DIR      = HOME / ".local" / "share" / "protonlaunch"
PREFIXES_DIR  = DATA_DIR / "prefixes"
COVERS_DIR    = DATA_DIR / "covers"
STEAM_DIR     = HOME / ".steam" / "steam"
PROTON_GE_DIR = HOME / ".steam" / "root" / "compatibilitytools.d"
SELF_SCRIPT   = Path(__file__).resolve()

for d in (DATA_DIR, PREFIXES_DIR, COVERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Stylesheet ────────────────────────────────────────────────────────────────
# Modern dark theme for Steam Deck
STYLE = """
QMainWindow, QDialog { 
    background-color: #0d1117; 
}
QWidget {
    background-color: #0d1117; color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
    font-size: 15px;
}

/* Subtle card backgrounds */
QWidget#card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
}

/* Modern buttons */
QPushButton {
    background-color: #21262d; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 8px;
    padding: 10px 20px; font-size: 15px; font-weight: 500;
    min-height: 44px;
}
QPushButton:hover { 
    background-color: #30363d; border-color: #8b949e; 
}
QPushButton:pressed { 
    background-color: #238636; border-color: #238636;
}

/* Primary action button - GitHub green style */
QPushButton#primary {
    background-color: #238636;
    border: 1px solid rgba(46, 160, 67, 0.4); 
    border-radius: 8px;
    color: #ffffff; 
    padding: 12px 24px; 
    font-size: 16px; font-weight: 600;
    min-height: 48px;
}
QPushButton#primary:hover { 
    background-color: #2ea043;
}
QPushButton#primary:pressed { 
    background-color: #1a7f30;
}

/* Secondary/Steam button */
QPushButton#steam {
    background-color: #1f6feb; 
    border: 1px solid rgba(56, 139, 253, 0.4);
    border-radius: 8px; 
    color: #ffffff;
    padding: 10px 20px; font-size: 15px; font-weight: 500;
    min-height: 44px;
}
QPushButton#steam:hover { 
    background-color: #388bfd;
}
QPushButton#steam:disabled {
    background-color: #21262d;
    border-color: #30363d;
    color: #484f58;
}

/* Text button style */
QPushButton#text {
    background-color: transparent;
    border: none;
    color: #58a6ff;
    padding: 8px 16px;
    font-size: 14px;
}
QPushButton#text:hover {
    background-color: rgba(88, 166, 255, 0.1);
}

/* Form inputs */
QComboBox {
    background-color: #21262d; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 12px; 
    color: #c9d1d9; min-height: 40px; font-size: 14px;
}
QComboBox QAbstractItemView {
    background-color: #161b22; border: 1px solid #30363d;
    selection-background-color: #1f6feb; color: #ffffff;
    font-size: 14px; padding: 4px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #c9d1d9; }

QLineEdit {
    background-color: #0d1117; border: 1px solid #30363d;
    border-radius: 6px; padding: 10px 14px; 
    color: #c9d1d9; min-height: 40px; font-size: 15px;
}
QLineEdit:focus { 
    border-color: #58a6ff; 
    background-color: #0d1117;
}

/* Checkboxes */
QCheckBox { 
    color: #c9d1d9; spacing: 10px; font-size: 14px;
    min-height: 32px;
}
QCheckBox::indicator {
    width: 20px; height: 20px; border: 1px solid #30363d;
    border-radius: 4px; background-color: #21262d;
}
QCheckBox::indicator:checked { 
    background-color: #238636; border-color: #238636; 
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNCIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyI+PHBvbHlsaW5lIHBvaW50cz0iMjAgNiA5IDE3IDQgMTIiPjwvcG9seWxpbmU+PC9zdmc+);
}

/* Lists */
QListWidget {
    background-color: #0d1117; border: 1px solid #30363d; 
    border-radius: 8px; color: #c9d1d9; font-size: 14px;
    outline: none;
}
QListWidget::item { 
    padding: 10px 14px; border-bottom: 1px solid #21262d; 
    min-height: 36px;
}
QListWidget::item:selected { 
    background-color: #1f6feb; color: #ffffff; 
}
QListWidget::item:hover:!selected { 
    background-color: #161b22; 
}

/* Scrollbars */
QScrollBar:vertical { 
    background-color: transparent; width: 10px; border-radius: 5px; 
}
QScrollBar::handle:vertical { 
    background-color: #30363d; border-radius: 5px; min-height: 40px; 
}
QScrollBar::handle:vertical:hover { background-color: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollArea { border: none; background-color: transparent; }

/* Text areas */
QTextEdit {
    background-color: #0d1117; border: 1px solid #30363d;
    border-radius: 8px; color: #8b949e; 
    font-size: 13px; padding: 10px;
    line-height: 1.5;
}

QLabel { background-color: transparent; color: #c9d1d9; }

/* Message boxes */
QMessageBox {
    background-color: #161b22;
}
QMessageBox QLabel {
    color: #c9d1d9; font-size: 15px;
}
QMessageBox QPushButton {
    min-width: 80px;
    min-height: 36px;
}
"""


# ── Main Window ───────────────────────────────────────────────────────────────
# Steam Deck optimized: 1280x800 native resolution, touch-friendly layout

class ProtonLaunch(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProtonLaunch")
        self.setStyleSheet(STYLE)
        
        # Steam Deck optimized - fit in 1280x800 with decorations
        self.resize(960, 680)
        self.setMinimumSize(900, 600)
        
        # Center on screen
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            center = screen.availableGeometry().center()
            geo = self.frameGeometry()
            geo.moveCenter(center)
            self.move(geo.topLeft())
        
        self.proton_versions = find_proton_versions(STEAM_DIR, PROTON_GE_DIR)
        self.worker = None
        self.last_game = None
        self.metadata = {}
        self.exe_path = ""
        self._search_worker = None
        self._details_worker = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(40, 20, 40, 15)
        root.setSpacing(0)

        # Header with step dots
        header = QHBoxLayout()
        header.setSpacing(20)
        header.addStretch()
        
        # App title
        title = QLabel("ProtonLaunch")
        title.setStyleSheet("font-size: 24px; font-weight: 600; color: #f0f6fc; letter-spacing: 1px;")
        header.addWidget(title)
        
        header.addSpacing(30)
        
        # Step indicators
        self.step_dots = []
        for i in range(3):
            dot = QLabel("●" if i == 0 else "○")
            dot.setStyleSheet(f"font-size: 12px; color: {'#238636' if i == 0 else '#484f58'};")
            self.step_dots.append(dot)
            header.addWidget(dot)
            if i < 2:
                line = QLabel("—")
                line.setStyleSheet("color: #30363d; font-size: 10px;")
                header.addWidget(line)
        
        header.addStretch()
        root.addLayout(header)

        root.addSpacing(15)

        # Stacked widget for steps
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(480)
        root.addWidget(self.stack)

        # Build steps
        self._build_step1()
        self._build_step2()
        self._build_step3()

        root.addSpacing(15)

        # Navigation bar
        nav_bar = QWidget()
        nav_bar.setObjectName("card")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(15, 8, 15, 8)
        nav_layout.setSpacing(10)
        
        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("text")
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self._prev_step)
        nav_layout.addWidget(self.back_btn)
        
        nav_layout.addStretch()
        
        self.next_btn = QPushButton("Continue →")
        self.next_btn.setObjectName("primary")
        self.next_btn.setMinimumWidth(140)
        self.next_btn.clicked.connect(self._next_step)
        nav_layout.addWidget(self.next_btn)
        
        root.addWidget(nav_bar)

        root.addSpacing(10)

        # Footer
        footer = QHBoxLayout()
        version = QLabel("v1.0")
        version.setStyleSheet("color: #484f58; font-size: 12px;")
        footer.addWidget(version)
        
        footer.addStretch()
        
        self_steam_btn = QPushButton("Add to Steam")
        self_steam_btn.setObjectName("text")
        self_steam_btn.clicked.connect(self._add_self_to_steam)
        footer.addWidget(self_steam_btn)
        
        root.addLayout(footer)

    def _build_step1(self):
        """Step 1: Find Game"""
        page = QWidget()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 20, 30, 20)

        # Title
        title = QLabel("Step 1: Find Your Game")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #f0f6fc;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Search Steam to fetch game artwork and details")
        subtitle.setStyleSheet("font-size: 13px; color: #8b949e; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Search row
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., The Witcher 3, Elden Ring...")
        self.name_input.returnPressed.connect(self._do_search)
        search_row.addWidget(self.name_input)
        
        self.search_btn = QPushButton("Search")
        self.search_btn.setFixedWidth(90)
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)
        layout.addLayout(search_row)

        # Results
        self.results_list = QListWidget()
        self.results_list.setFixedHeight(90)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        layout.addWidget(self.results_list)

        # Info area - more compact
        info = QHBoxLayout()
        info.setSpacing(15)
        info.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.cover_label = QLabel("No cover")
        self.cover_label.setFixedSize(90, 120)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #484f58; font-size: 11px;")
        info.addWidget(self.cover_label)

        meta = QVBoxLayout()
        meta.setSpacing(4)
        meta.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.meta_info = QLabel("")
        self.meta_info.setStyleSheet("font-size: 12px; color: #8b949e;")
        meta.addWidget(self.meta_info)
        
        self.desc_box = QTextEdit()
        self.desc_box.setReadOnly(True)
        self.desc_box.setPlaceholderText("Select a game to see description...")
        self.desc_box.setFixedHeight(60)
        meta.addWidget(self.desc_box)
        
        info.addLayout(meta, stretch=1)
        layout.addLayout(info)

        self.stack.addWidget(page)

    def _build_step2(self):
        """Step 2: Select Installer"""
        page = QWidget()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 20, 30, 20)

        # Title
        title = QLabel("Step 2: Select Installer")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #f0f6fc;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Choose your Windows setup executable")
        subtitle.setStyleSheet("font-size: 13px; color: #8b949e; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # File display box - smaller
        file_box = QWidget()
        file_box.setStyleSheet("background-color: #0d1117; border: 2px dashed #30363d; border-radius: 8px;")
        file_layout = QVBoxLayout(file_box)
        file_layout.setContentsMargins(20, 30, 20, 30)
        
        self.exe_label = QLabel("No file selected")
        self.exe_label.setStyleSheet("color: #484f58; font-size: 14px;")
        self.exe_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_layout.addWidget(self.exe_label)
        
        layout.addWidget(file_box)

        # Browse button
        browse_btn = QPushButton("📁 Browse for .exe...")
        browse_btn.setObjectName("primary")
        browse_btn.clicked.connect(self._browse_exe)
        browse_btn.setMinimumWidth(180)
        layout.addWidget(browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        self.stack.addWidget(page)

    def _build_step3(self):
        """Step 3: Configure & Install"""
        page = QWidget()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 20, 30, 20)

        # Title
        title = QLabel("Step 3: Configure & Install")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #f0f6fc;")
        layout.addWidget(title)

        # Two column layout - more compact
        columns = QHBoxLayout()
        columns.setSpacing(20)

        # Left column - Proton
        left = QVBoxLayout()
        left.setSpacing(6)
        
        proton_label = QLabel("Proton Version")
        proton_label.setStyleSheet("font-size: 13px; color: #8b949e;")
        left.addWidget(proton_label)
        
        self.proton_combo = QComboBox()
        self.proton_combo.setMinimumWidth(200)
        for name in (self.proton_versions or ["No Proton/Wine found"]):
            self.proton_combo.addItem(name)
        left.addWidget(self.proton_combo)
        left.addStretch()
        columns.addLayout(left)

        # Right column - Flags
        right = QVBoxLayout()
        right.setSpacing(4)
        
        flags_label = QLabel("Compatibility Flags")
        flags_label.setStyleSheet("font-size: 13px; color: #8b949e;")
        right.addWidget(flags_label)
        
        self.dxvk_cb = QCheckBox("DXVK")
        self.vkd3d_cb = QCheckBox("VKD3D")
        self.esync_cb = QCheckBox("ESync")
        self.fsync_cb = QCheckBox("FSync")
        self.hud_cb = QCheckBox("MangoHud")
        self.dxvk_cb.setChecked(True)
        self.esync_cb.setChecked(True)
        
        right.addWidget(self.dxvk_cb)
        right.addWidget(self.vkd3d_cb)
        right.addWidget(self.esync_cb)
        right.addWidget(self.fsync_cb)
        right.addWidget(self.hud_cb)
        right.addStretch()
        
        columns.addLayout(right)
        layout.addLayout(columns)

        layout.addSpacing(15)

        # Install button
        self.install_btn = QPushButton("▶ Run Installer")
        self.install_btn.setObjectName("primary")
        self.install_btn.setMinimumHeight(44)
        self.install_btn.clicked.connect(self._run_install)
        layout.addWidget(self.install_btn)

        # Add to Steam button
        self.steam_btn = QPushButton("＋ Add to Steam")
        self.steam_btn.setObjectName("steam")
        self.steam_btn.setMinimumHeight(40)
        self.steam_btn.setEnabled(False)
        self.steam_btn.clicked.connect(self._add_last_to_steam)
        layout.addWidget(self.steam_btn)

        layout.addStretch()
        self.stack.addWidget(page)

    def _next_step(self):
        current = self.stack.currentIndex()
        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
            self._update_nav()

    def _prev_step(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            self._update_nav()

    def _update_nav(self):
        current = self.stack.currentIndex()
        total = self.stack.count()
        
        # Update step dots
        for i, dot in enumerate(self.step_dots):
            if i == current:
                dot.setText("●")
                dot.setStyleSheet("font-size: 12px; color: #238636;")
            elif i < current:
                dot.setText("✓")
                dot.setStyleSheet("font-size: 12px; color: #238636;")
            else:
                dot.setText("○")
                dot.setStyleSheet("font-size: 12px; color: #484f58;")
        
        self.back_btn.setEnabled(current > 0)
        if current == total - 1:
            self.next_btn.setText("Finish")
            self.next_btn.setEnabled(False)
        else:
            self.next_btn.setText("Continue →")
            self.next_btn.setEnabled(True)

    def _do_search(self):
        query = self.name_input.text().strip()
        if not query:
            return
        self.search_btn.setText("...")
        self.search_btn.setEnabled(False)
        self.results_list.clear()
        self._search_worker = SearchWorker(query)
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.start()

    def _on_search_results(self, results):
        self.search_btn.setText("🔍 Search")
        self.search_btn.setEnabled(True)
        self.results_list.clear()
        if not results:
            QListWidgetItem("No results found", self.results_list)
            return
        for item in results:
            li = QListWidgetItem(item.get("name", "Unknown"))
            li.setData(Qt.ItemDataRole.UserRole, item)
            self.results_list.addItem(li)
        self.results_list.setCurrentRow(0)

    def _on_result_selected(self, current, _previous):
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.name_input.setText(data.get("name", self.name_input.text()))
        self.meta_info.setText("Fetching details...")
        self._details_worker = DetailsWorker(data["id"], COVERS_DIR)
        self._details_worker.ready.connect(self._on_details_ready)
        self._details_worker.start()

    def _on_details_ready(self, meta, cover_path):
        self.metadata = meta
        if cover_path and Path(cover_path).exists():
            pix = QPixmap(cover_path).scaled(90, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix)
            self.cover_label.setText("")
        else:
            self.cover_label.setText("No cover")
            self.cover_label.setPixmap(QPixmap())
        parts = [meta[k] for k in ("developer", "release_date", "genres") if meta.get(k)]
        self.meta_info.setText("  ·  ".join(parts) if parts else "")
        self.desc_box.setPlainText(meta.get("description", ""))

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Installer", str(Path.home()), "Windows Executables (*.exe);;All Files (*)")
        if path:
            self.exe_path = path
            self.exe_label.setText(Path(path).name)
            self.exe_label.setStyleSheet("color: #58a6ff; font-size: 14px; font-weight: 500;")
            # Auto-fill name if empty
            if not self.name_input.text():
                stem = re.sub(r'setup|install|installer', '', re.sub(r'[_\-\.]+', ' ', Path(path).stem), flags=re.IGNORECASE).strip()
                self.name_input.setText(stem.title())

    def _run_install(self):
        # Validate inputs
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a game name.")
            return
        if not self.exe_path:
            QMessageBox.warning(self, "Missing Installer", "Please select a .exe installer.")
            return
        if not self.proton_versions:
            QMessageBox.critical(self, "No Proton", "No Proton or Wine installation found.")
            return

        # Build game data
        proton_name = self.proton_combo.currentText()
        game = {
            "name": name,
            "exe": self.exe_path,
            "proton": proton_name,
            "proton_bin": self.proton_versions.get(proton_name, ""),
            "dxvk": self.dxvk_cb.isChecked(),
            "vkd3d": self.vkd3d_cb.isChecked(),
            "esync": self.esync_cb.isChecked(),
            "fsync": self.fsync_cb.isChecked(),
            "mangohud": self.hud_cb.isChecked(),
            **self.metadata,
        }
        
        # Generate ID
        uid = re.sub(r'\W+', '_', name.lower()).strip('_')
        uid = f"{uid}_{int(time.time())}"
        game["id"] = uid
        
        self._run_installer(game)

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
        if ok:
            # Build launcher script for the installed game
            launcher_script = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
            game["launcher_script"] = launcher_script
            self.last_game = game
            self.steam_btn.setEnabled(True)
            self.steam_btn.setText(f"＋ Add '{game['name']}' to Steam")
            QMessageBox.information(
                self, "Installation Complete",
                f"'{game['name']}' has been installed.\n\n"
                f"Launcher script created at:\n{launcher_script}\n\n"
                f"Click 'Add to Steam' to add it to your Steam library."
            )
        else:
            reply = QMessageBox.question(
                self, "Installation Issue",
                f"{msg}\n\nThe installer may have still worked.\n\n"
                f"Would you like to create a launcher script anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                launcher_script = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
                game["launcher_script"] = launcher_script
                self.last_game = game
                self.steam_btn.setEnabled(True)
                self.steam_btn.setText(f"＋ Add '{game['name']}' to Steam")

    def _add_last_to_steam(self):
        if not self.last_game:
            return
        game = self.last_game
        from pathlib import Path
        if not game.get("launcher_script") or not Path(game["launcher_script"]).exists():
            game["launcher_script"] = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
        ok, msg = write_steam_shortcut(game["name"], game["launcher_script"], game.get("cover_path", ""), STEAM_DIR)
        if ok:
            QMessageBox.information(
                self, "Added to Steam",
                f"{msg}\n\n'{game['name']}' will appear in your Steam library after restart."
            )
        else:
            QMessageBox.warning(self, "Failed", msg)

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

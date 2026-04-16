from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QFileDialog, QComboBox, QCheckBox, QGridLayout, QSizePolicy, QSpacerItem, QMessageBox,
    QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
import re
from pathlib import Path

from protonlaunch.logic.workers import SearchWorker, DetailsWorker

class AddGameDialog(QDialog):
    def __init__(self, parent=None, proton_versions=None, covers_dir=None):
        super().__init__(parent)
        self.proton_versions = proton_versions or {}
        self.covers_dir = covers_dir
        self.exe_path = ""
        self.metadata = {}
        self._search_worker  = None
        self._details_worker = None
        self.setWindowTitle("Install Game")
        # Steam Deck screen is 1280x800, leave room for window decorations
        self.resize(900, 600)
        self.setMinimumSize(720, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 16, 20, 16)

        # Title
        title = QLabel("📀 INSTALL NEW GAME")
        title.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            letter-spacing: 3px; 
            color: #00d4aa;
            padding-bottom: 6px;
        """)
        layout.addWidget(title)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3d424d; min-height: 2px;")
        layout.addWidget(sep)
        layout.addSpacing(10)

        # Name + search row
        name_label = QLabel("Game Name")
        name_label.setStyleSheet("font-size: 20px; color: #8b92a8; font-weight: bold;")
        layout.addWidget(name_label)
        
        name_row = QHBoxLayout()
        name_row.setSpacing(16)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. The Witcher 3")
        self.name_input.returnPressed.connect(self._do_search)
        name_row.addWidget(self.name_input)
        
        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.setMinimumWidth(140)
        self.search_btn.clicked.connect(self._do_search)
        name_row.addWidget(self.search_btn)
        layout.addLayout(name_row)
        layout.addSpacing(10)

        # Metadata panel: cover + results + description
        meta_row = QHBoxLayout()
        meta_row.setSpacing(20)

        self.cover_label = QLabel("No\ncover")
        self.cover_label.setFixedSize(150, 200)  # 3:4 aspect ratio, fits better
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet(
            "background-color: #252a33; border: 2px solid #3d424d; border-radius: 12px; "
            "color: #5a6270; font-size: 18px; font-weight: bold;"
        )
        meta_row.addWidget(self.cover_label)

        meta_right = QVBoxLayout()
        meta_right.setSpacing(12)
        
        self.results_list = QListWidget()
        self.results_list.setFixedHeight(120)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        meta_right.addWidget(self.results_list)

        self.meta_info = QLabel()
        self.meta_info.setWordWrap(True)
        self.meta_info.setStyleSheet("color: #8b92a8; font-size: 16px;")
        self.meta_info.setFixedHeight(40)
        meta_right.addWidget(self.meta_info)

        self.desc_box = QTextEdit()
        self.desc_box.setReadOnly(True)
        self.desc_box.setPlaceholderText("Select a game to see details…")
        self.desc_box.setFixedHeight(80)
        meta_right.addWidget(self.desc_box)
        meta_row.addLayout(meta_right)
        layout.addLayout(meta_row)
        layout.addSpacing(10)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background-color: #3d424d; min-height: 2px;")
        layout.addWidget(sep2)
        layout.addSpacing(10)

        # EXE picker
        exe_label = QLabel("Windows Installer (.exe)")
        exe_label.setStyleSheet("font-size: 20px; color: #8b92a8; font-weight: bold;")
        layout.addWidget(exe_label)
        
        exe_row = QHBoxLayout()
        exe_row.setSpacing(16)
        self.exe_label = QLabel("No file selected — Browse to your game installer")
        self.exe_label.setStyleSheet("color: #5a6270; font-size: 18px;")
        self.exe_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        exe_row.addWidget(self.exe_label)
        
        browse_btn = QPushButton("📁 Browse…")
        browse_btn.setMinimumWidth(140)
        browse_btn.clicked.connect(self._browse_exe)
        exe_row.addWidget(browse_btn)
        layout.addLayout(exe_row)
        layout.addSpacing(15)

        # Proton picker
        proton_label = QLabel("Proton / Wine Version")
        proton_label.setStyleSheet("font-size: 20px; color: #8b92a8; font-weight: bold;")
        layout.addWidget(proton_label)
        
        self.proton_combo = QComboBox()
        for name in (self.proton_versions or ["No Proton/Wine found"]):
            self.proton_combo.addItem(name)
        layout.addWidget(self.proton_combo)
        layout.addSpacing(15)

        # Flags
        flags_label = QLabel("Compatibility Flags")
        flags_label.setStyleSheet("font-size: 20px; color: #8b92a8; font-weight: bold;")
        layout.addWidget(flags_label)
        
        flags_grid = QGridLayout()
        flags_grid.setHorizontalSpacing(30)
        flags_grid.setVerticalSpacing(12)
        self.dxvk_cb  = QCheckBox("DXVK — DirectX 9/10/11 → Vulkan")
        self.vkd3d_cb = QCheckBox("VKD3D — DirectX 12 → Vulkan")
        self.esync_cb = QCheckBox("ESync — Better CPU performance")
        self.fsync_cb = QCheckBox("FSync — Linux 5.16+ kernel")
        self.hud_cb   = QCheckBox("MangoHud — Performance overlay")
        self.dxvk_cb.setChecked(True)
        self.esync_cb.setChecked(True)
        flags_grid.addWidget(self.dxvk_cb,  0, 0)
        flags_grid.addWidget(self.vkd3d_cb, 0, 1)
        flags_grid.addWidget(self.esync_cb, 1, 0)
        flags_grid.addWidget(self.fsync_cb, 1, 1)
        flags_grid.addWidget(self.hud_cb,   2, 0)
        layout.addLayout(flags_grid)

        layout.addStretch()
        
        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.install_btn = QPushButton("▶  RUN INSTALLER")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.install_btn)
        layout.addLayout(btn_row)

    def _do_search(self):
        query = self.name_input.text().strip()
        if not query: return
        self.search_btn.setText("…"); self.search_btn.setEnabled(False)
        self.results_list.clear()
        self._search_worker = SearchWorker(query)
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.start()

    def _on_search_results(self, results):
        self.search_btn.setText("🔍 Search"); self.search_btn.setEnabled(True)
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
        if not current: return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data: return
        self.name_input.setText(data.get("name", self.name_input.text()))
        self.meta_info.setText("Fetching details…")
        self._details_worker = DetailsWorker(data["id"], self.covers_dir)
        self._details_worker.ready.connect(self._on_details_ready)
        self._details_worker.start()

    def _on_details_ready(self, meta, cover_path):
        self.metadata = meta
        if cover_path and Path(cover_path).exists():
            pix = QPixmap(cover_path).scaled(150, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setPixmap(pix); self.cover_label.setText("")
        else:
            self.cover_label.setText("No\ncover")
        parts = [meta[k] for k in ("developer", "release_date", "genres") if meta.get(k)]
        self.meta_info.setText("  ·  ".join(parts))
        self.desc_box.setPlainText(meta.get("description", ""))

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Installer", str(Path.home()), "Windows Executables (*.exe);;All Files (*)")
        if path:
            self.exe_path = path
            self.exe_label.setText(Path(path).name)
            self.exe_label.setStyleSheet("color: #00d4aa; font-size: 18px; font-weight: bold;")
            if not self.name_input.text():
                stem = re.sub(r'setup|install|installer', '', re.sub(r'[_\-\.]+', ' ', Path(path).stem), flags=re.IGNORECASE).strip()
                self.name_input.setText(stem.title())

    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Missing Name", "Please enter a game name."); return
        if not self.exe_path:
            QMessageBox.warning(self, "Missing Installer", "Please select a .exe installer."); return
        if not self.proton_versions:
            QMessageBox.critical(self, "No Proton", "No Proton or Wine installation found."); return
        self.accept()

    def get_game_data(self) -> dict:
        proton_name = self.proton_combo.currentText()
        return {
            "name":       self.name_input.text().strip(),
            "exe":        self.exe_path,
            "proton":     proton_name,
            "proton_bin": self.proton_versions.get(proton_name, ""),
            "dxvk":       self.dxvk_cb.isChecked(),
            "vkd3d":      self.vkd3d_cb.isChecked(),
            "esync":      self.esync_cb.isChecked(),
            "fsync":      self.fsync_cb.isChecked(),
            "mangohud":   self.hud_cb.isChecked(),
            **self.metadata,
        }
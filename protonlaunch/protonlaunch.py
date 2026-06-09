#!/usr/bin/env python3

# ProtonLaunch — Windows game installer for Steam Deck
# Streamlined: pick .exe → match Steam + ProtonDB hints → run installer → add to Steam

import sys
import os
import time
import shutil
import re
import shlex
from pathlib import Path
try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QFrame,
        QMessageBox,
        QProgressDialog,
        QLineEdit,
        QComboBox,
        QCheckBox,
        QListWidget,
        QListWidgetItem,
        QTextEdit,
        QFileDialog,
        QStackedWidget,
        QScrollArea,
        QSizePolicy,
        QGridLayout,
        QDialog,
        QDialogButtonBox,
    )
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QPixmap, QFont, QGuiApplication, QDesktopServices
except ModuleNotFoundError as exc:
    if getattr(exc, "name", "") == "PyQt6":
        print(
            "Missing dependency: PyQt6\n"
            "Install it and retry:\n"
            "  Windows: py -3 -m pip install PyQt6\n"
            "  SteamOS: sudo pacman -S python-pyqt6",
            file=sys.stderr,
        )
        raise SystemExit(1)
    raise

# Import helpers and logic modules
from protonlaunch.helpers.helpers import (
    find_proton_versions,
    build_launcher_script,
    write_steam_shortcut,
    resolve_steam_root,
    resolve_prefix_layout,
    recommend_proton_key,
    winetricks_available,
    DEFAULT_WINETRICKS_VERBS,
    parse_winetricks_verbs_field,
    scan_prefix_for_game_exes,
)
from protonlaunch.logic.workers import InstallerWorker, SearchWorker, DetailsWorker

# ── Paths ─────────────────────────────────────────────────────────────────────
HOME = Path.home()
DATA_DIR = HOME / ".local" / "share" / "protonlaunch"
PREFIXES_DIR = DATA_DIR / "prefixes"
COVERS_DIR = DATA_DIR / "covers"
_STEAM_ROOT = resolve_steam_root()
STEAM_DIR = _STEAM_ROOT if _STEAM_ROOT is not None else (HOME / ".steam" / "steam")
PROTON_GE_DIR = STEAM_DIR / "compatibilitytools.d"
SELF_SCRIPT = (
    Path(sys.executable).resolve()
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve()
)
# Steam Game Mode often provides a minimal PATH; prefer SteamOS system Python.
PYTHON_FOR_STEAM = "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else shutil.which("python3") or "python3"

for d in (DATA_DIR, PREFIXES_DIR, COVERS_DIR, DATA_DIR / "logs"):
    d.mkdir(parents=True, exist_ok=True)


def _read_app_version() -> str:
    if getattr(sys, "frozen", False):
        bases = [Path(getattr(sys, "_MEIPASS", ".")), Path(__file__).resolve().parent]
    else:
        bases = [Path(__file__).resolve().parent]
    for base in bases:
        for vf in (base / "VERSION", base / "protonlaunch" / "VERSION"):
            try:
                return vf.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return "0.0.0"


APP_VERSION = _read_app_version()

# ── Stylesheet: deck-first, high contrast, teal + violet accents ─────────────
STYLE = """
QMainWindow {
    background-color: #070709;
}
QWidget#rail {
    background-color: #0c0c12;
    border-right: 1px solid #1e1e2a;
}
QWidget#contentHost {
    background-color: #070709;
}
QFrame#contentCard {
    background-color: #101018;
    border: 1px solid #222232;
    border-radius: 16px;
}
QFrame#dropZone {
    background-color: #0a0a10;
    border: 2px dashed #2a2a3c;
    border-radius: 14px;
}
QFrame#dropZone[state="hasFile"] {
    border-color: #2dd4bf;
    background-color: rgba(45, 212, 191, 0.06);
}
QFrame#pdbPanel {
    background-color: #0a0a10;
    border: 1px solid #252535;
    border-radius: 12px;
}
QLabel#railTitle {
    color: #e8e8ef;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.5px;
}
QLabel#railSubtitle {
    color: #6b6b80;
    font-size: 12px;
}
QLabel#sectionKicker {
    color: #2dd4bf;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
}
QLabel#sectionTitle {
    color: #f4f4f8;
    font-size: 22px;
    font-weight: 700;
}
QLabel#sectionHint {
    color: #8b8b9e;
    font-size: 14px;
}
QLabel#metaLine {
    color: #9a9ab0;
    font-size: 13px;
}
QLabel#coverPlate {
    background-color: #14141f;
    border: 1px solid #2a2a3c;
    border-radius: 10px;
    color: #5c5c70;
    font-size: 12px;
}
QPushButton#stepNav {
    background-color: transparent;
    color: #7a7a90;
    border: none;
    border-radius: 12px;
    padding: 14px 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    min-height: 52px;
}
QPushButton#stepNav:hover {
    background-color: #16161f;
    color: #c4c4d4;
}
QPushButton#stepNav:checked {
    background-color: #16162a;
    color: #f0f0f8;
    border-left: 3px solid #2dd4bf;
    padding-left: 13px;
}
QPushButton#stepNav:disabled {
    color: #45455a;
}
QPushButton {
    background-color: #1a1a26;
    color: #e0e0ea;
    border: 1px solid #2e2e40;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 600;
    min-height: 48px;
}
QPushButton:hover {
    background-color: #222232;
    border-color: #3d3d55;
}
QPushButton:pressed {
    background-color: #2a2a3c;
}
QPushButton#primary {
    background-color: #0d9488;
    color: #ffffff;
    border: 1px solid #14b8a6;
    font-size: 15px;
    min-height: 52px;
}
QPushButton#primary:hover {
    background-color: #14b8a6;
}
QPushButton#primary:pressed {
    background-color: #0f766e;
}
QPushButton#steam {
    background-color: #1e3a5f;
    color: #dbeafe;
    border: 1px solid #3b82f6;
    min-height: 48px;
}
QPushButton#steam:hover {
    background-color: #2563eb;
    color: #ffffff;
}
QPushButton#steam:disabled {
    background-color: #151520;
    border-color: #2a2a3c;
    color: #55556a;
}
QPushButton#ghost {
    background-color: transparent;
    border: none;
    color: #5eead4;
    font-weight: 600;
    min-height: 44px;
}
QPushButton#ghost:hover {
    background-color: rgba(94, 234, 212, 0.08);
}
QPushButton#ghost:disabled {
    color: #45455a;
}
QComboBox {
    background-color: #14141f;
    border: 1px solid #2e2e40;
    border-radius: 10px;
    padding: 10px 14px;
    color: #e8e8ef;
    min-height: 48px;
    font-size: 14px;
}
QComboBox QAbstractItemView {
    background-color: #14141f;
    border: 1px solid #2e2e40;
    selection-background-color: #0d9488;
    color: #ffffff;
    padding: 6px;
    font-size: 14px;
}
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #9a9ab0;
}
QLineEdit {
    background-color: #0a0a10;
    border: 1px solid #2e2e40;
    border-radius: 10px;
    padding: 12px 16px;
    color: #f4f4f8;
    font-size: 15px;
    min-height: 48px;
    selection-background-color: #0d9488;
}
QLineEdit:focus {
    border-color: #2dd4bf;
}
QCheckBox {
    color: #c8c8d8;
    spacing: 12px;
    font-size: 14px;
    min-height: 36px;
}
QCheckBox::indicator {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    border: 1px solid #3d3d55;
    background-color: #14141f;
}
QCheckBox::indicator:checked {
    background-color: #0d9488;
    border-color: #14b8a6;
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNCIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyI+PHBvbHlsaW5lIHBvaW50cz0iMjAgNiA5IDE3IDQgMTIiPjwvcG9seWxpbmU+PC9zdmc+);
}
QListWidget {
    background-color: #0a0a10;
    border: 1px solid #2e2e40;
    border-radius: 12px;
    color: #e0e0ea;
    font-size: 14px;
    outline: none;
    padding: 4px;
}
QListWidget::item {
    padding: 12px 14px;
    border-radius: 8px;
    min-height: 44px;
}
QListWidget::item:selected {
    background-color: #0d9488;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #16161f;
}
QTextEdit {
    background-color: #0a0a10;
    border: 1px solid #2e2e40;
    border-radius: 12px;
    color: #9a9ab0;
    font-size: 13px;
    padding: 12px;
}
QScrollArea { border: none; background-color: transparent; }
QScrollBar:vertical {
    background-color: transparent;
    width: 10px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background-color: #35354a;
    border-radius: 5px;
    min-height: 48px;
}
QScrollBar::handle:vertical:hover { background-color: #4a4a62; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMessageBox { background-color: #101018; }
QMessageBox QLabel { color: #e8e8ef; font-size: 14px; }
QProgressDialog { background-color: #101018; }
QProgressDialog QLabel { color: #c8c8d8; font-size: 14px; }
"""


class InstallerDropFrame(QFrame):
    """Accept .exe drops for the installer step."""

    def __init__(self, parent, on_exe_path):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self._on_exe_path = on_exe_path
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".exe"):
                self._on_exe_path(path)
                event.acceptProposedAction()
                return
        event.ignore()


def _wrap_scroll(inner: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(inner)
    return scroll


# ── Main window ───────────────────────────────────────────────────────────────


class ProtonLaunch(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProtonLaunch")
        self.setStyleSheet(STYLE)

        self.resize(1024, 700)
        self.setMinimumSize(880, 580)

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
        self._search_generation = 0
        self._details_generation = 0
        self._step_nav_buttons = []
        self.drop_zone = None
        self._selected_steam_appid = None
        self._build_ui()
        self._update_proton_suggestion()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # —— Left rail ——
        rail = QWidget()
        rail.setObjectName("rail")
        rail.setFixedWidth(232)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(20, 28, 16, 24)
        rail_layout.setSpacing(8)

        brand = QLabel("ProtonLaunch")
        brand.setObjectName("railTitle")
        rail_layout.addWidget(brand)
        sub = QLabel("Simple guided install flow")
        sub.setObjectName("railSubtitle")
        sub.setWordWrap(True)
        rail_layout.addWidget(sub)
        rail_layout.addSpacing(28)

        steps = [
            ("1", "Installer", "Pick setup .exe"),
            ("2", "Match", "Find game metadata"),
            ("3", "Runtime", "Proton and flags"),
            ("4", "Install", "Run and add to Steam"),
        ]
        for i, (num, title, hint) in enumerate(steps):
            btn = QPushButton(f"{num}  {title}\n    {hint}")
            btn.setObjectName("stepNav")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._go_step(idx))
            self._step_nav_buttons.append(btn)
            rail_layout.addWidget(btn)
        self._step_nav_buttons[0].setChecked(True)

        rail_layout.addStretch()

        pin_btn = QPushButton("Pin app to Steam")
        pin_btn.setObjectName("ghost")
        pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pin_btn.clicked.connect(self._add_self_to_steam)
        rail_layout.addWidget(pin_btn)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("railSubtitle")
        rail_layout.addWidget(ver)

        outer.addWidget(rail)

        # —— Main column ——
        host = QWidget()
        host.setObjectName("contentHost")
        host_col = QVBoxLayout(host)
        host_col.setContentsMargins(28, 24, 28, 20)
        host_col.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        host_col.addWidget(self.stack, stretch=1)

        self._build_step_setup()
        self._build_step_match()
        self._build_step_runtime()
        self._build_step_install()

        # Bottom bar
        bar = QFrame()
        bar.setObjectName("contentCard")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(18, 14, 18, 14)

        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("ghost")
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self._prev_step)
        bar_layout.addWidget(self.back_btn)

        bar_layout.addStretch()

        self.next_btn = QPushButton("Continue")
        self.next_btn.setObjectName("primary")
        self.next_btn.setMinimumWidth(160)
        self.next_btn.clicked.connect(self._next_step)
        bar_layout.addWidget(self.next_btn)

        host_col.addWidget(bar)
        outer.addWidget(host, stretch=1)

    def _make_page_frame(self) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("contentCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        return card, lay

    def _build_step_setup(self):
        page_inner = QWidget()
        layout = QVBoxLayout(page_inner)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        kicker = QLabel("Step 1")
        kicker.setObjectName("sectionKicker")
        layout.addWidget(kicker)
        title = QLabel("Pick your Windows installer")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        hint = QLabel(
            "Choose the installer .exe only. You will select the final installed game .exe later."
        )
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.drop_zone = InstallerDropFrame(self, self._apply_installer_path)
        self.drop_zone.setMinimumHeight(140)
        dz_lay = QVBoxLayout(self.drop_zone)
        dz_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.exe_label = QLabel("No .exe selected")
        self.exe_label.setObjectName("sectionHint")
        self.exe_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.exe_label.setWordWrap(True)
        dz_lay.addWidget(self.exe_label)
        layout.addWidget(self.drop_zone)

        browse_btn = QPushButton("Browse for .exe")
        browse_btn.setObjectName("primary")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_exe)
        layout.addWidget(browse_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch()
        card, card_lay = self._make_page_frame()
        card_lay.addWidget(_wrap_scroll(page_inner))
        self.stack.addWidget(card)

    def _build_step_match(self):
        page_inner = QWidget()
        layout = QVBoxLayout(page_inner)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        kicker = QLabel("Step 2")
        kicker.setObjectName("sectionKicker")
        layout.addWidget(kicker)
        title = QLabel("Match game metadata")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        search_row.setSpacing(12)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Game title…")
        self.name_input.returnPressed.connect(self._do_search)
        search_row.addWidget(self.name_input, stretch=1)
        self.search_btn = QPushButton("Search stores")
        self.search_btn.setFixedWidth(150)
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)
        layout.addLayout(search_row)

        self.search_diag_label = QLabel("")
        self.search_diag_label.setObjectName("sectionHint")
        self.search_diag_label.setWordWrap(True)
        layout.addWidget(self.search_diag_label)

        self.results_list = QListWidget()
        self.results_list.setMinimumHeight(100)
        self.results_list.setMaximumHeight(128)
        self.results_list.currentItemChanged.connect(self._on_result_selected)
        layout.addWidget(self.results_list)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(20)
        self.cover_label = QLabel("Artwork")
        self.cover_label.setObjectName("coverPlate")
        self.cover_label.setFixedSize(128, 171)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_row.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignTop)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(8)
        self.meta_info = QLabel("")
        self.meta_info.setObjectName("metaLine")
        self.meta_info.setWordWrap(True)
        meta_col.addWidget(self.meta_info)
        self.desc_box = QTextEdit()
        self.desc_box.setReadOnly(True)
        self.desc_box.setPlaceholderText("Select a Steam result for the store blurb.")
        self.desc_box.setMinimumHeight(72)
        meta_col.addWidget(self.desc_box)
        detail_row.addLayout(meta_col, stretch=1)
        layout.addLayout(detail_row)

        pdb_frame = QFrame()
        pdb_frame.setObjectName("pdbPanel")
        pdb_lay = QVBoxLayout(pdb_frame)
        pdb_lay.setContentsMargins(16, 14, 16, 14)
        pdb_lay.setSpacing(10)
        pdb_head = QLabel("ProtonDB · Steam Deck hints")
        pdb_head.setObjectName("sectionKicker")
        pdb_head.setStyleSheet("letter-spacing: 1px;")
        pdb_lay.addWidget(pdb_head)
        self.protondb_tier_label = QLabel("Select a Steam listing to load ProtonDB data.")
        self.protondb_tier_label.setObjectName("metaLine")
        self.protondb_tier_label.setWordWrap(True)
        pdb_lay.addWidget(self.protondb_tier_label)
        self.protondb_note_label = QLabel("")
        self.protondb_note_label.setObjectName("sectionHint")
        self.protondb_note_label.setWordWrap(True)
        pdb_lay.addWidget(self.protondb_note_label)
        pdb_btn_row = QHBoxLayout()
        self.apply_suggest_btn = QPushButton("Apply suggested flags")
        self.apply_suggest_btn.setEnabled(False)
        self.apply_suggest_btn.clicked.connect(self._apply_deck_suggestions)
        pdb_btn_row.addWidget(self.apply_suggest_btn)
        self.open_pdb_btn = QPushButton("Open ProtonDB")
        self.open_pdb_btn.setEnabled(False)
        self.open_pdb_btn.clicked.connect(self._open_protondb_page)
        pdb_btn_row.addWidget(self.open_pdb_btn)
        pdb_btn_row.addStretch()
        pdb_lay.addLayout(pdb_btn_row)
        layout.addWidget(pdb_frame)

        layout.addStretch()
        card, card_lay = self._make_page_frame()
        card_lay.addWidget(_wrap_scroll(page_inner))
        self.stack.addWidget(card)

    def _build_step_runtime(self):
        page_inner = QWidget()
        layout = QVBoxLayout(page_inner)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        kicker = QLabel("Step 3")
        kicker.setObjectName("sectionKicker")
        layout.addWidget(kicker)
        title = QLabel("Runtime and compatibility")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        proton_label = QLabel("Proton / Wine")
        proton_label.setObjectName("metaLine")
        grid.addWidget(proton_label, 0, 0)
        self.proton_combo = QComboBox()
        for name in (self.proton_versions or ["No Proton/Wine found"]):
            self.proton_combo.addItem(name)
        grid.addWidget(self.proton_combo, 1, 0)
        self.proton_hint = QLabel("")
        self.proton_hint.setObjectName("sectionHint")
        self.proton_hint.setWordWrap(True)
        grid.addWidget(self.proton_hint, 2, 0)

        verbs_label = ", ".join(DEFAULT_WINETRICKS_VERBS)
        self.winetricks_cb = QCheckBox(
            f"Pre-install common libraries (winetricks: {verbs_label})"
        )
        wt_ok = winetricks_available()
        self.winetricks_cb.setChecked(wt_ok)
        self.winetricks_cb.setEnabled(wt_ok)
        if not wt_ok:
            self.winetricks_cb.setToolTip(
                "Install winetricks to enable — SteamOS: sudo pacman -S winetricks"
            )
        grid.addWidget(self.winetricks_cb, 3, 0)

        wt_extra_l = QLabel("Extra winetricks verbs (optional, comma-separated)")
        wt_extra_l.setObjectName("metaLine")
        grid.addWidget(wt_extra_l, 4, 0)
        default_verbs = ", ".join(DEFAULT_WINETRICKS_VERBS)
        self.winetricks_verbs_edit = QLineEdit()
        self.winetricks_verbs_edit.setPlaceholderText(default_verbs)
        self.winetricks_verbs_edit.setText(default_verbs)
        grid.addWidget(self.winetricks_verbs_edit, 5, 0)

        flags_label = QLabel("Runtime flags")
        flags_label.setObjectName("metaLine")
        grid.addWidget(flags_label, 0, 1)
        flags_inner = QGridLayout()
        self.dxvk_cb = QCheckBox("DXVK (DirectX 9–11)")
        self.vkd3d_cb = QCheckBox("VKD3D (DirectX 12)")
        self.esync_cb = QCheckBox("ESync")
        self.fsync_cb = QCheckBox("FSync (SteamOS)")
        self.hud_cb = QCheckBox("MangoHud")
        self.dxvk_cb.setChecked(True)
        self.esync_cb.setChecked(True)
        self.fsync_cb.setChecked(True)
        flags_inner.addWidget(self.dxvk_cb, 0, 0)
        flags_inner.addWidget(self.vkd3d_cb, 0, 1)
        flags_inner.addWidget(self.esync_cb, 1, 0)
        flags_inner.addWidget(self.fsync_cb, 1, 1)
        flags_inner.addWidget(self.hud_cb, 2, 0)
        grid.addLayout(flags_inner, 1, 1, 6, 1)
        layout.addLayout(grid)

        for w in (
            self.proton_combo,
            self.winetricks_cb,
            self.winetricks_verbs_edit,
            self.dxvk_cb,
            self.vkd3d_cb,
            self.esync_cb,
            self.fsync_cb,
            self.hud_cb,
        ):
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(lambda _i: self._refresh_install_summary())
            elif hasattr(w, "toggled"):
                w.toggled.connect(self._refresh_install_summary)
            else:
                w.textChanged.connect(self._refresh_install_summary)

        lo_label = QLabel("Extra Steam launch options (optional)")
        lo_label.setObjectName("metaLine")
        layout.addWidget(lo_label)
        self.launch_opts = QLineEdit()
        self.launch_opts.setPlaceholderText(
            "e.g. DXVK_ASYNC=1 — KEY=VALUE pairs are written into the launcher script"
        )
        self.launch_opts.textChanged.connect(self._refresh_install_summary)
        layout.addWidget(self.launch_opts)

        layout.addStretch()
        card, card_lay = self._make_page_frame()
        card_lay.addWidget(_wrap_scroll(page_inner))
        self.stack.addWidget(card)

    def _build_step_install(self):
        page_inner = QWidget()
        layout = QVBoxLayout(page_inner)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        kicker = QLabel("Install")
        kicker.setObjectName("sectionKicker")
        layout.addWidget(kicker)
        title = QLabel("Run the installer, then add to Steam")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("sectionHint")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.install_btn = QPushButton("Run Windows installer")
        self.install_btn.setObjectName("primary")
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.clicked.connect(self._run_install)
        layout.addWidget(self.install_btn)

        self.steam_btn = QPushButton("Add to Steam library")
        self.steam_btn.setObjectName("steam")
        self.steam_btn.setEnabled(False)
        self.steam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.steam_btn.clicked.connect(self._add_last_to_steam)
        layout.addWidget(self.steam_btn)

        layout.addStretch()
        card, card_lay = self._make_page_frame()
        card_lay.addWidget(_wrap_scroll(page_inner))
        self.stack.addWidget(card)

    def _go_step(self, index: int):
        self.stack.setCurrentIndex(index)
        self._update_nav()

    def _next_step(self):
        current = self.stack.currentIndex()
        if current == 0:
            if not self.exe_path:
                QMessageBox.warning(self, "Select an installer", "Browse to your Windows .exe first.")
                return
        if current == 1:
            if not self.name_input.text().strip():
                QMessageBox.warning(self, "Game name", "Enter a title or pick a store result.")
                return
        if current == 2:
            self._refresh_install_summary()
        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
            self._update_nav()

    def _validate_setup(self) -> bool:
        if not self.exe_path:
            QMessageBox.warning(self, "Select an installer", "Browse to your Windows .exe first.")
            return False
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Game name", "Enter a title or pick a Steam search result.")
            return False
        return True

    def _refresh_install_summary(self):
        flags = []
        if self.dxvk_cb.isChecked():
            flags.append("DXVK")
        if self.vkd3d_cb.isChecked():
            flags.append("VKD3D")
        if self.esync_cb.isChecked():
            flags.append("ESync")
        if self.fsync_cb.isChecked():
            flags.append("FSync")
        if self.hud_cb.isChecked():
            flags.append("MangoHud")
        proton = self.proton_combo.currentText()
        lo = self.launch_opts.text().strip()
        lines = [
            f"Installer: {Path(self.exe_path).name}",
            f"Title: {self.name_input.text().strip()}",
            f"Proton: {proton}",
            "Launch target: choose installed game .exe after installer finishes",
            f"Flags: {', '.join(flags) if flags else 'none'}",
        ]
        if lo:
            lines.append(f"Steam options: {lo}")
        if self.winetricks_cb.isChecked() and winetricks_available():
            verbs = parse_winetricks_verbs_field(self.winetricks_verbs_edit.text())
            lines.append(
                "Prefix prep: winetricks " + ", ".join(verbs) + " (before installer)"
            )
        elif self.winetricks_cb.isChecked():
            lines.append("Prefix prep: winetricks requested but winetricks not found on PATH")
        else:
            lines.append("Prefix prep: none (installer only)")
        pdb = self.metadata.get("protondb") or {}
        if pdb.get("tier"):
            lines.append(f"ProtonDB tier: {pdb.get('tier')} (community aggregate — check Deck reports)")
        self.summary_label.setText("\n".join(lines))

    def _update_proton_suggestion(self):
        if not getattr(self, "proton_versions", None):
            self.proton_hint.setText("")
            return
        key = recommend_proton_key(self.proton_versions, self.metadata)
        if not key:
            self.proton_hint.setText("")
            return
        idx = self.proton_combo.findText(key)
        if idx >= 0:
            self.proton_combo.setCurrentIndex(idx)
        tier = ((self.metadata or {}).get("protondb") or {}).get("tier") or ""
        tier_bit = f" ProtonDB tier is {tier}." if tier else ""
        self.proton_hint.setText(
            f"Suggested runtime from your installs and game metadata:{tier_bit} “{key}” (change above if you prefer)."
        )

    def _apply_deck_suggestions(self):
        s = self.metadata.get("deck_suggest")
        if not s:
            return
        self.dxvk_cb.setChecked(s.get("dxvk", True))
        self.vkd3d_cb.setChecked(s.get("vkd3d", False))
        self.esync_cb.setChecked(s.get("esync", True))
        self.fsync_cb.setChecked(s.get("fsync", True))
        self.hud_cb.setChecked(s.get("mangohud", False))
        extra = (s.get("launch_options") or "").strip()
        if extra and not self.launch_opts.text().strip():
            self.launch_opts.setText(extra)
        self._update_proton_suggestion()

    def _open_protondb_page(self):
        appid = self.metadata.get("steam_appid") or self._selected_steam_appid
        if appid:
            QDesktopServices.openUrl(QUrl(f"https://www.protondb.com/app/{appid}"))

    def _prev_step(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            self._update_nav()

    def _update_nav(self):
        current = self.stack.currentIndex()
        total = self.stack.count()

        for i, btn in enumerate(self._step_nav_buttons):
            btn.setChecked(i == current)

        self.back_btn.setEnabled(current > 0)
        if current == total - 1:
            self.next_btn.setText("Done")
            self.next_btn.setEnabled(False)
        else:
            self.next_btn.setText("Continue")
            self.next_btn.setEnabled(True)

    def _do_search(self):
        query = self.name_input.text().strip()
        if not query:
            return
        self._selected_steam_appid = None
        self.open_pdb_btn.setEnabled(False)
        self.search_btn.setText("…")
        self.search_btn.setEnabled(False)
        self.results_list.clear()
        self._search_generation += 1
        generation = self._search_generation
        self._search_worker = SearchWorker(query)
        self._search_worker.results_ready.connect(
            lambda results, diag, g=generation: self._on_search_results(results, diag, g)
        )
        self._search_worker.start()

    def _format_search_diag(self, diag: dict) -> str:
        if not diag:
            return ""
        se = (diag.get("steam_error") or "").strip()
        le = (diag.get("lutris_error") or "").strip()
        sc = int(diag.get("steam_count") or 0)
        lc = int(diag.get("lutris_count") or 0)
        if se:
            sm = se if len(se) <= 140 else se[:137] + "…"
            steam_bit = f"Steam: failed ({sm})"
        else:
            steam_bit = f"Steam: OK ({sc} hits)"
        if le:
            lm = le if len(le) <= 140 else le[:137] + "…"
            lut_bit = f"Lutris: failed ({lm})"
        else:
            lut_bit = f"Lutris: OK ({lc} hits)"
        return f"{steam_bit}  ·  {lut_bit}"

    def _on_search_results(self, results, diag=None, generation=None):
        if generation is not None and generation != self._search_generation:
            return
        self.search_btn.setText("Search stores")
        self.search_btn.setEnabled(True)
        self.results_list.clear()
        self.search_diag_label.setText(self._format_search_diag(diag or {}))
        self.protondb_tier_label.setText("Select a listing — Steam rows load ProtonDB; others may link Steam via Lutris.")
        self.protondb_note_label.setText("")
        self.apply_suggest_btn.setEnabled(False)
        self.metadata = {}
        if not results:
            fallback_name = self.name_input.text().strip() or "Manual title"
            li = QListWidgetItem(f"{fallback_name}  ·  Manual entry")
            li.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "kind": "manual",
                    "name": fallback_name,
                    "display_suffix": "Manual",
                },
            )
            self.results_list.addItem(li)
            self.results_list.setCurrentRow(0)
            self.protondb_tier_label.setText(
                "No store results returned. Using manual mode; you can still continue install."
            )
            return
        for item in results:
            name = item.get("name", "Unknown")
            suffix = item.get("display_suffix") or ""
            label = f"{name}  ·  {suffix}" if suffix else name
            li = QListWidgetItem(label)
            li.setData(Qt.ItemDataRole.UserRole, item)
            self.results_list.addItem(li)
        self.results_list.setCurrentRow(0)

    def _on_result_selected(self, current, _previous):
        if not current:
            return
        pick = current.data(Qt.ItemDataRole.UserRole)
        if not pick:
            return
        steam_for_pdb = None
        if pick.get("kind") == "steam":
            try:
                steam_for_pdb = int(pick["id"]) if pick.get("id") is not None else None
            except (TypeError, ValueError):
                steam_for_pdb = None
        elif pick.get("kind") == "lutris":
            sa = pick.get("steam_appid")
            try:
                steam_for_pdb = int(sa) if sa is not None else None
            except (TypeError, ValueError):
                steam_for_pdb = None
        self._selected_steam_appid = steam_for_pdb
        self.name_input.setText(pick.get("name", self.name_input.text()))
        self.meta_info.setText("Fetching game details…")
        self.protondb_tier_label.setText("Loading…")
        self.protondb_note_label.setText("")
        self.apply_suggest_btn.setEnabled(False)
        self.open_pdb_btn.setEnabled(bool(self._selected_steam_appid))
        self._details_generation += 1
        generation = self._details_generation
        self._details_worker = DetailsWorker(pick, COVERS_DIR)
        self._details_worker.ready.connect(
            lambda meta, cover_path, g=generation: self._on_details_ready(meta, cover_path, g)
        )
        self._details_worker.start()

    def _on_details_ready(self, meta, cover_path, generation=None):
        if generation is not None and generation != self._details_generation:
            return
        self.metadata = meta
        if cover_path and Path(cover_path).exists():
            pix = QPixmap(cover_path).scaled(
                128, 171, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.cover_label.setPixmap(pix)
            self.cover_label.setText("")
        else:
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText("No artwork")
        parts = [meta[k] for k in ("developer", "release_date", "genres") if meta.get(k)]
        self.meta_info.setText("  ·  ".join(parts) if parts else "")
        self.desc_box.setPlainText(meta.get("description", ""))

        pdb = meta.get("protondb") or {}
        if pdb:
            tier = pdb.get("tier", "—")
            conf = pdb.get("confidence", "—")
            total = pdb.get("total")
            extra = f" · {total} reports" if total is not None else ""
            self.protondb_tier_label.setText(f"Tier: {tier} · confidence: {conf}{extra}")
        elif meta.get("steam_appid"):
            self.protondb_tier_label.setText("No ProtonDB summary for this Steam app id.")
        else:
            self.protondb_tier_label.setText(
                "ProtonDB only covers Steam releases — pick a row with a Steam id, or the Steam store result."
            )

        ds = meta.get("deck_suggest") or {}
        self.protondb_note_label.setText(ds.get("note", ""))
        self.apply_suggest_btn.setEnabled(bool(ds))
        self.open_pdb_btn.setEnabled(bool(meta.get("steam_appid")))
        self._update_proton_suggestion()

    def _set_drop_zone_state(self, has_file: bool):
        if self.drop_zone is not None:
            self.drop_zone.setProperty("state", "hasFile" if has_file else "")
            self.drop_zone.style().unpolish(self.drop_zone)
            self.drop_zone.style().polish(self.drop_zone)

    def _apply_installer_path(self, path: str):
        path = (path or "").strip()
        if not path.lower().endswith(".exe"):
            QMessageBox.warning(self, "Not an installer", "Please choose a Windows .exe file.")
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, "Missing file", "That path does not exist.")
            return
        self.exe_path = path
        self.exe_label.setText(Path(path).name)
        self.exe_label.setObjectName("")
        self.exe_label.setStyleSheet("color: #5eead4; font-size: 15px; font-weight: 600;")
        self._set_drop_zone_state(True)
        if hasattr(self, "name_input") and not self.name_input.text():
            stem = re.sub(
                r"setup|install|installer",
                "",
                re.sub(r"[_\-\.]+", " ", Path(path).stem),
                flags=re.IGNORECASE,
            ).strip()
            self.name_input.setText(stem.title())
        if hasattr(self, "name_input"):
            self._do_search()

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Installer", str(Path.home()), "Windows Executables (*.exe);;All Files (*)"
        )
        if path:
            self._apply_installer_path(path)

    def _run_install(self):
        if not self._validate_setup():
            return
        if not self.proton_versions:
            QMessageBox.critical(self, "No Proton", "No Proton or Wine installation was found.")
            return

        name = self.name_input.text().strip()
        proton_name = self.proton_combo.currentText()
        game = {
            **self.metadata,
            "name": name,
            "exe": self.exe_path,
            "installer_exe": self.exe_path,
            "proton": proton_name,
            "proton_bin": self.proton_versions.get(proton_name, ""),
            "dxvk": self.dxvk_cb.isChecked(),
            "vkd3d": self.vkd3d_cb.isChecked(),
            "esync": self.esync_cb.isChecked(),
            "fsync": self.fsync_cb.isChecked(),
            "mangohud": self.hud_cb.isChecked(),
            "steam_launch_options": self.launch_opts.text().strip(),
            "install_winetricks": self.winetricks_cb.isChecked() and winetricks_available(),
            "winetricks_verbs": parse_winetricks_verbs_field(self.winetricks_verbs_edit.text()),
        }

        uid = re.sub(r"\W+", "_", name.lower()).strip("_")
        uid = f"{uid}_{int(time.time())}"
        game["id"] = uid

        self._run_installer(game)

    def _run_installer(self, game):
        self.install_btn.setEnabled(False)
        self.install_btn.setText("Installer running…")
        self._progress = QProgressDialog(
            f"Running the installer for “{game['name']}”.\n\nComplete any dialogs that appear.",
            "Hide",
            0,
            0,
            self,
        )
        self._progress.setWindowTitle("Installing")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setMinimumWidth(440)
        self._progress.show()
        if not Path(game["proton_bin"]).is_file() or not Path(game["exe"]).is_file():
            self._progress.close()
            self.install_btn.setEnabled(True)
            self.install_btn.setText("Run Windows installer")
            QMessageBox.critical(
                self,
                "Invalid executable",
                "The selected Proton/Wine binary or installer file is missing.",
            )
            return
        log_path = DATA_DIR / "logs" / f"{game['id']}.log"
        game["install_log"] = str(log_path)
        self.worker = InstallerWorker(game, PREFIXES_DIR, STEAM_DIR, str(log_path))
        self.worker.phase.connect(self._progress.setLabelText)
        self.worker.done.connect(lambda ok, msg: self._on_install_done(ok, msg, game))
        self.worker.start()

    def _pick_installed_exe(self, game) -> str | None:
        prefix_root = PREFIXES_DIR / game["id"]
        _compat, wine_pfx = resolve_prefix_layout(prefix_root)
        candidates = scan_prefix_for_game_exes(
            wine_pfx, game.get("installer_exe"), max_results=60
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Select installed game .exe")
        dlg.setMinimumWidth(520)
        vl = QVBoxLayout(dlg)
        vl.addWidget(
            QLabel(
                "Pick the game’s main executable (not the installer). "
                "Suggestions are sorted by recent changes; use Browse if the list is wrong."
            )
        )
        lw = QListWidget()
        for p in candidates:
            lw.addItem(p)
        vl.addWidget(lw)

        result: list[str | None] = [None]

        def on_ok():
            it = lw.currentItem()
            if it and it.text().strip():
                result[0] = it.text().strip()
            dlg.accept()

        def on_browse():
            start_dir = wine_pfx / "drive_c"
            start = str(start_dir if start_dir.exists() else Path.home())
            path, _ = QFileDialog.getOpenFileName(
                dlg,
                "Browse for game .exe",
                start,
                "Windows Executables (*.exe);;All Files (*)",
            )
            if path:
                result[0] = path.strip()
                dlg.accept()

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(on_browse)
        row = QHBoxLayout()
        row.addWidget(browse_btn)
        row.addStretch()
        vl.addLayout(row)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(on_ok)
        box.rejected.connect(dlg.reject)
        vl.addWidget(box)

        lw.itemDoubleClicked.connect(lambda _it: on_ok())

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return result[0]

    def _on_install_done(self, ok, msg, game):
        self._progress.close()
        self.install_btn.setEnabled(True)
        self.install_btn.setText("Run Windows installer")
        if ok:
            target_exe = self._pick_installed_exe(game)
            if not target_exe:
                QMessageBox.warning(
                    self,
                    "Executable needed",
                    "Select the installed game .exe to create the launcher and Steam shortcut.",
                )
                return
            game["exe"] = target_exe
            launcher_script = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
            game["launcher_script"] = launcher_script
            self.last_game = game
            self.steam_btn.setEnabled(True)
            self.steam_btn.setText(f"Add “{game['name']}” to Steam")
            QMessageBox.information(
                self,
                "Installation complete",
                f"“{game['name']}” installer finished.\n\n"
                f"Launch target:\n{game['exe']}\n\n"
                f"Launcher script:\n{launcher_script}\n\n"
                f"Use “Add to Steam library” when you are ready.\n\n"
                f"Log: {game.get('install_log', '')}",
            )
        else:
            reply = QMessageBox.question(
                self,
                "Installer exit",
                f"{msg}\n\nThe game may still be installed. Create a launcher script anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                target_exe = self._pick_installed_exe(game)
                if not target_exe:
                    QMessageBox.warning(
                        self,
                        "Executable needed",
                        "No launcher created because no installed game .exe was selected.",
                    )
                    return
                game["exe"] = target_exe
                launcher_script = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
                game["launcher_script"] = launcher_script
                self.last_game = game
                self.steam_btn.setEnabled(True)
                self.steam_btn.setText(f"Add “{game['name']}” to Steam")

    def _add_last_to_steam(self):
        if not self.last_game:
            return
        game = self.last_game
        if not game.get("launcher_script") or not Path(game["launcher_script"]).exists():
            game["launcher_script"] = build_launcher_script(game, PREFIXES_DIR, DATA_DIR, STEAM_DIR)
        ok, msg = write_steam_shortcut(
            game["name"],
            game["launcher_script"],
            game.get("cover_path", ""),
            STEAM_DIR,
            launch_options=game.get("steam_launch_options", ""),
        )
        if ok:
            QMessageBox.information(
                self,
                "Added to Steam",
                f"{msg}\n\n“{game['name']}” shows up after you restart Steam.",
            )
        else:
            QMessageBox.warning(self, "Could not add shortcut", msg)

    def _add_self_to_steam(self):
        launcher = DATA_DIR / "protonlaunch-launcher.sh"
        if getattr(sys, "frozen", False):
            exe_q = shlex.quote(str(Path(sys.executable).resolve()))
            launcher.write_text(f"#!/bin/bash\nexec {exe_q} \"$@\"\n")
        else:
            py_q = shlex.quote(PYTHON_FOR_STEAM)
            script_q = shlex.quote(str(SELF_SCRIPT))
            launcher.write_text(f"#!/bin/bash\nexec {py_q} {script_q} \"$@\"\n")
        launcher.chmod(0o755)
        ok, msg = write_steam_shortcut("ProtonLaunch", str(launcher), "", STEAM_DIR)
        if ok:
            QMessageBox.information(
                self,
                "Pinned to Steam",
                f"{msg}\n\nLaunch ProtonLaunch from Game Mode like any other title.",
            )
        else:
            QMessageBox.warning(self, "Could not add shortcut", msg)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ProtonLaunch")
    app.setStyle("Fusion")

    ui_font = QFont()
    ui_font.setPointSize(10)
    if sys.platform == "linux":
        ui_font.setFamily("Noto Sans")
    app.setFont(ui_font)

    win = ProtonLaunch()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

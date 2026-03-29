from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from pathlib import Path

class GameCard(QFrame):
    launched       = pyqtSignal(str)
    removed        = pyqtSignal(str)
    added_to_steam = pyqtSignal(str)

    def __init__(self, game: dict, parent=None):
        super().__init__(parent)
        self.game = game
        self.setObjectName("gameCard")
        self.setStyleSheet("""
            QFrame#gameCard { background-color: #14141c; border: 1px solid #2a2a38; border-radius: 10px; }
            QFrame#gameCard:hover { border-color: #3a3a50; }
        """)
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cover
        cover_lbl = QLabel()
        cover_lbl.setFixedSize(72, 96)
        cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_lbl.setStyleSheet("background-color: #1a1a22; border-radius: 10px 0 0 10px; color: #333; font-size: 10px;")
        cover_path = self.game.get("cover_path", "")
        if cover_path and Path(cover_path).exists():
            pix = QPixmap(cover_path).scaled(72, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            cover_lbl.setPixmap(pix)
        else:
            cover_lbl.setText("🎮")
            cover_lbl.setStyleSheet(cover_lbl.styleSheet() + " font-size: 28px;")
        outer.addWidget(cover_lbl)

        # Right side
        right = QVBoxLayout()
        right.setContentsMargins(14, 12, 14, 12)
        right.setSpacing(6)

        # Name + badge
        top = QHBoxLayout()
        name_lbl = QLabel(self.game["name"])
        name_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #e8e6e3;")
        top.addWidget(name_lbl); top.addStretch()
        proton_name = self.game.get("proton", "")
        color = "#b39ddb" if "GE" in proton_name else "#4fc3f7" if "Proton" in proton_name else "#ffcc80"
        badge = QLabel(proton_name)
        badge.setStyleSheet(f"border: 1px solid {color}; color: {color}; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;")
        top.addWidget(badge)
        right.addLayout(top)

        # Meta
        parts = [self.game[k] for k in ("developer", "release_date", "genres") if self.game.get(k)]
        if parts:
            ml = QLabel("  ·  ".join(parts))
            ml.setStyleSheet("color: #546e7a; font-size: 11px;")
            right.addWidget(ml)

        # Flags
        flags = [f for f, k in [("DXVK","dxvk"),("VKD3D","vkd3d"),("ESync","esync"),("FSync","fsync"),("HUD","mangohud")] if self.game.get(k)]
        if flags:
            fr = QHBoxLayout(); fr.setSpacing(5)
            for f in flags:
                fl = QLabel(f)
                fl.setStyleSheet("background-color: #1e1e2c; color: #78909c; border-radius: 3px; padding: 1px 7px; font-size: 11px;")
                fr.addWidget(fl)
            fr.addStretch()
            right.addLayout(fr)

        # Buttons
        br = QHBoxLayout(); br.setSpacing(8)
        launch_btn = QPushButton("▶  Launch");      launch_btn.setObjectName("launch"); launch_btn.setMinimumHeight(38)
        steam_btn  = QPushButton("＋ Add to Steam"); steam_btn.setObjectName("steam");  steam_btn.setMinimumHeight(38)
        remove_btn = QPushButton("Remove");          remove_btn.setObjectName("danger"); remove_btn.setMinimumHeight(38)
        launch_btn.clicked.connect(lambda: self.launched.emit(self.game["id"]))
        steam_btn.clicked.connect(lambda: self.added_to_steam.emit(self.game["id"]))
        remove_btn.clicked.connect(lambda: self.removed.emit(self.game["id"]))
        br.addWidget(launch_btn); br.addWidget(steam_btn); br.addStretch(); br.addWidget(remove_btn)
        right.addLayout(br)
        outer.addLayout(right)
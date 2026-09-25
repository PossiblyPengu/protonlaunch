"""Colours and stylesheet: Steam Big Picture look, sized for the Deck's 1280×800 screen."""

BG = "#0e141b"
BG_RAISED = "#171d25"
SURFACE = "#1f2733"
SURFACE_HI = "#2a3647"
LINE = "#2e3a4b"
TEXT = "#ffffff"
TEXT_DIM = "#b8bcbf"
MUTED = "#8b929a"
ACCENT = "#1a9fff"
ACCENT_DARK = "#0e6fb8"
GREEN = "#5ba32b"
GREEN_HI = "#70c043"
DANGER = "#e25555"

STYLE = f"""
QWidget {{ background: transparent; color: {TEXT}; font-size: 18px; }}
QMainWindow, QDialog#page {{ background: {BG}; }}
QWidget#root {{ background: {BG}; }}
QLabel#h1 {{ font-size: 32px; font-weight: 700; }}
QLabel#h2 {{ font-size: 22px; font-weight: 700; color: {TEXT}; }}
QLabel#section {{ font-size: 15px; font-weight: 700; color: {MUTED}; letter-spacing: 1px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#status {{ font-size: 22px; }}
QLabel#ok {{ font-size: 30px; font-weight: 700; color: {GREEN_HI}; }}
QLabel#chip {{ background: {SURFACE}; color: {TEXT_DIM}; border-radius: 14px; padding: 4px 14px; font-size: 15px; }}

QPushButton {{
  background: {SURFACE}; border: 3px solid {SURFACE}; border-radius: 10px;
  padding: 10px 26px; min-height: 36px; font-size: 19px; font-weight: 600;
}}
QPushButton:hover {{ background: {SURFACE_HI}; border-color: {SURFACE_HI}; }}
QPushButton:focus {{ background: {SURFACE_HI}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; }}
QPushButton#primary:focus {{ border-color: {TEXT}; }}
QPushButton#play {{ background: {GREEN}; border-color: {GREEN}; font-size: 22px; }}
QPushButton#play:focus, QPushButton#play:hover {{ background: {GREEN_HI}; border-color: {TEXT}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#flat {{ background: transparent; border-color: transparent; color: {TEXT_DIM}; }}
QPushButton#flat:focus {{ border-color: {ACCENT}; }}

QListWidget {{
  background: {BG_RAISED}; border: 2px solid {LINE}; border-radius: 12px; padding: 6px; outline: none;
}}
QListWidget:focus {{ border-color: {ACCENT}; }}
QListWidget::item {{ padding: 12px 14px; border-radius: 8px; margin: 1px 0; }}
QListWidget::item:selected {{ background: {SURFACE_HI}; color: {TEXT}; }}
QListWidget::item:selected:focus {{ background: {ACCENT}; }}
QLineEdit {{
  background: {BG_RAISED}; border: 2px solid {LINE}; border-radius: 10px; padding: 10px 14px; font-size: 20px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPlainTextEdit {{
  background: #0a0f14; border: 2px solid {LINE}; border-radius: 10px; padding: 8px;
  font-family: monospace; font-size: 13px; color: {TEXT_DIM};
}}
QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QProgressBar {{ border: none; background: {SURFACE}; border-radius: 5px; max-height: 10px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 3px; min-height: 40px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE}; }}
"""

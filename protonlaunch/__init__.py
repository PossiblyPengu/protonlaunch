# ProtonLaunch package
from pathlib import Path

_vf = Path(__file__).resolve().parent / "VERSION"
try:
    __version__ = _vf.read_text(encoding="utf-8").strip()
except OSError:
    __version__ = "0.0.0"

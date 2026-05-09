#!/usr/bin/env python3
"""Load ProtonLaunch main window under a headless/minimal Qt platform (CI / WSL)."""
import os
import sys

# Repo root = parent of scripts/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402
from protonlaunch.protonlaunch import ProtonLaunch  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    w = ProtonLaunch()
    print("OK:", w.windowTitle())
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

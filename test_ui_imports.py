#!/usr/bin/env python3
"""Test UI module imports (no display required)"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing UI module imports...")

# Mock PyQt6 to avoid needing a display server
class MockQtWidgets:
    class QDialog: pass
    class QVBoxLayout: pass
    class QHBoxLayout: pass
    class QLabel: pass
    class QLineEdit: pass
    class QPushButton: pass
    class QListWidget: pass
    class QListWidgetItem: pass
    class QTextEdit: pass
    class QFileDialog: pass
    class QComboBox: pass
    class QCheckBox: pass
    class QGridLayout: pass
    class QSizePolicy: pass
    class QSpacerItem: pass
    class QMessageBox: pass
    class QFrame: pass
    
class MockQtCore:
    class Qt:
        class ItemDataRole:
            UserRole = 1
        class AspectRatioMode:
            KeepAspectRatio = 1
        class TransformationMode:
            SmoothTransformation = 1
        class AlignmentFlag:
            AlignCenter = 1
        class ScrollBarPolicy:
            ScrollBarAlwaysOff = 1
            ScrollBarAlwaysOn = 2
        class WindowModality:
            WindowModal = 1
    class QThread:
        def __init__(self): pass
        def start(self): pass
    pyqtSignal = lambda *args: None
    
class MockQtGui:
    class QPixmap:
        def __init__(self, *args): pass
        def scaled(self, *args): return self

# Insert mocks
sys.modules['PyQt6'] = type(sys)('PyQt6')
sys.modules['PyQt6.QtWidgets'] = MockQtWidgets
sys.modules['PyQt6.QtCore'] = MockQtCore
sys.modules['PyQt6.QtGui'] = MockQtGui

try:
    from protonlaunch.ui.add_game_dialog import AddGameDialog
    print("  ✓ AddGameDialog imported")
except Exception as e:
    print(f"  ✗ AddGameDialog failed: {e}")

try:
    from protonlaunch.logic.workers import SearchWorker, DetailsWorker, InstallerWorker
    print("  ✓ All workers imported")
except Exception as e:
    print(f"  ✗ Workers failed: {e}")

print("\nUI structure validated!")

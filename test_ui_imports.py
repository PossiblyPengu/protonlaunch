#!/usr/bin/env python3
"""Test UI module imports (no display required)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing UI module imports...")


class MockQtWidgets:
    class QApplication:
        pass

    class QMainWindow:
        pass

    class QWidget:
        pass

    class QVBoxLayout:
        pass

    class QHBoxLayout:
        pass

    class QLabel:
        pass

    class QLineEdit:
        pass

    class QPushButton:
        pass

    class QListWidget:
        pass

    class QListWidgetItem:
        pass

    class QTextEdit:
        pass

    class QFileDialog:
        pass

    class QComboBox:
        pass

    class QCheckBox:
        pass

    class QGridLayout:
        pass

    class QSizePolicy:
        class Policy:
            Expanding = 1

    class QSpacerItem:
        pass

    class QMessageBox:
        @staticmethod
        def warning(*_a, **_k):
            pass

        @staticmethod
        def critical(*_a, **_k):
            pass

        @staticmethod
        def information(*_a, **_k):
            pass

        @staticmethod
        def question(*_a, **_k):
            pass

        class StandardButton:
            Yes = 1
            No = 0

    class QFrame:
        class Shape:
            HLine = 1
            NoFrame = 0

    class QScrollArea:
        pass

    class QStackedWidget:
        pass

    class QProgressDialog:
        def __init__(self, *_a, **_k):
            pass

        def setLabelText(self, *_a, **_k):
            pass

        def setWindowTitle(self, *_a, **_k):
            pass

        def setWindowModality(self, *_a, **_k):
            pass

        def setMinimumDuration(self, *_a, **_k):
            pass

        def setMinimumWidth(self, *_a, **_k):
            pass

        def show(self):
            pass

        def close(self):
            pass

    class QDialog:
        class DialogCode:
            Accepted = 1

        def exec(self):
            return 0

    class QDialogButtonBox:
        class StandardButton:
            Ok = 1
            Cancel = 2


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
            AlignHCenter = 2
            AlignTop = 3

        class ScrollBarPolicy:
            ScrollBarAlwaysOff = 1

        class WindowModality:
            WindowModal = 1

        class CursorShape:
            PointingHandCursor = 1

        class HighDpiScaleFactorRoundingPolicy:
            PassThrough = 1

    class QThread:
        def __init__(self):
            pass

        def start(self):
            pass

    class QUrl:
        def __init__(self, *_a, **_k):
            pass

    pyqtSignal = lambda *args: None


class MockQtGui:
    class QPixmap:
        def __init__(self, *args):
            pass

        def scaled(self, *args):
            return self

    class QFont:
        def setPointSize(self, *_a, **_k):
            pass

        def setFamily(self, *_a, **_k):
            pass

    class QGuiApplication:
        @staticmethod
        def setHighDpiScaleFactorRoundingPolicy(*_a, **_k):
            pass

        @staticmethod
        def primaryScreen():
            return None

    class QDesktopServices:
        @staticmethod
        def openUrl(*_a, **_k):
            pass


sys.modules["PyQt6"] = type(sys)("PyQt6")
sys.modules["PyQt6.QtWidgets"] = MockQtWidgets
sys.modules["PyQt6.QtCore"] = MockQtCore
sys.modules["PyQt6.QtGui"] = MockQtGui

try:
    from protonlaunch.protonlaunch import ProtonLaunch

    print("  OK ProtonLaunch imported")
except Exception as e:
    print(f"  FAIL ProtonLaunch: {e}")
    raise

try:
    from protonlaunch.logic.workers import SearchWorker, DetailsWorker, InstallerWorker

    print("  OK All workers imported")
except Exception as e:
    print(f"  FAIL Workers: {e}")
    raise

print("\nUI structure validated!")

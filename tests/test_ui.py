"""Drive the real window headless through a full (fake-Proton) install."""
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

from protonlaunch import core  # noqa: E402
from tests.test_core import Env, make_lnk  # noqa: E402


@unittest.skipIf(QApplication is None, "PyQt6 not installed")
class TestWindow(Env):
    @classmethod
    def setUpClass(cls):
        from protonlaunch.app import STYLE
        cls.qapp = QApplication.instance() or QApplication([])
        cls.qapp.setStyleSheet(STYLE)

    def setUp(self):
        super().setUp()
        self._orig_roots = core.steam_roots
        core.steam_roots = lambda home=None: [self.steam]
        from protonlaunch.app import MainWindow
        self.win = MainWindow(self.paths)
        self.win.show()
        self.shots = os.environ.get("PROTONLAUNCH_SCREENSHOTS")

    def tearDown(self):
        core.steam_roots = self._orig_roots
        self.win.close()
        super().tearDown()

    def wait_for(self, cond, timeout=15):
        end = time.time() + timeout
        while not cond():
            self.qapp.processEvents()
            if time.time() > end:
                self.fail("timed out")
            time.sleep(0.02)

    def shot(self, name):
        if self.shots:
            for _ in range(5):
                self.qapp.processEvents()
            Path(self.shots).mkdir(parents=True, exist_ok=True)
            self.win.grab().save(str(Path(self.shots) / f"{name}.png"))

    def test_automatic_install(self):
        lnk = self.tmp / "x.lnk"
        lnk.write_bytes(make_lnk(r"C:\Program Files\Cool Game\bin\CoolGame.exe"))
        os.environ["FAKE_LNK"] = str(lnk)
        os.environ["FAKE_SLEEP"] = "1"
        self.shot("1-home-empty")
        self.win.start_install(self.installer)
        self.wait_for(lambda: "installer" in self.win.status.text())
        self.shot("2-installing")
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        self.shot("3-done")
        self.assertIn("Cool Game Deluxe", self.win.done_title.text())
        self.win.show_page(self.win.home)
        self.assertEqual(self.win.rows.count(), 1)
        self.shot("4-home-library")

    def test_portable_asks(self):
        os.environ["FAKE_NOTHING"] = "1"
        self.win.start_install(self.installer)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.pick)
        self.shot("5-pick")
        self.win.use_portable()
        self.assertIs(self.win.stack.currentWidget(), self.win.done)
        self.assertEqual(len(core.Library(self.paths).load()), 1)


if __name__ == "__main__":
    unittest.main()

"""Drive the real window headless through installs (with a fake Proton), incl. keyboard navigation."""
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PROTONLAUNCH_NO_GAMEPAD"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

from protonlaunch import core  # noqa: E402
from tests.test_core import Env, bmp_icon, make_lnk, make_pe  # noqa: E402


@unittest.skipIf(QApplication is None, "PyQt6 not installed")
class TestWindow(Env):
    @classmethod
    def setUpClass(cls):
        from protonlaunch import theme
        cls.qapp = QApplication.instance() or QApplication([])
        cls.qapp.setStyle("Fusion")
        cls.qapp.setStyleSheet(theme.STYLE)

    def setUp(self):
        super().setUp()
        from protonlaunch import app as app_mod
        from protonlaunch.widgets import Sheet
        self._orig_roots = core.steam_roots
        core.steam_roots = lambda home=None: [self.steam]
        # Sheets are modal; answer them from a queue instead.
        self.answers: list[int] = []
        self.asked: list[str] = []
        self._orig_ask = Sheet.ask
        Sheet.ask = staticmethod(lambda parent, title, *a, **k: (self.asked.append(title),
                                                                 self.answers.pop(0) if self.answers else -1)[1])
        self.downloads = self.home / "Downloads"
        self.win = app_mod.MainWindow(self.paths)
        self.win.installer_dirs = [self.downloads]
        self.win.show()
        self.win.activateWindow()
        self.shots = os.environ.get("PROTONLAUNCH_SCREENSHOTS")

    def tearDown(self):
        from protonlaunch.widgets import Sheet
        Sheet.ask = self._orig_ask
        core.steam_roots = self._orig_roots
        self.win.nav and self.win.nav.stop()
        self.win.close()
        self.win.deleteLater()
        self.pump()
        super().tearDown()

    def pump(self, n=5):
        for _ in range(n):
            self.qapp.processEvents()

    def wait_for(self, cond, timeout=20):
        end = time.time() + timeout
        while not cond():
            self.qapp.processEvents()
            if time.time() > end:
                self.fail("timed out")
            time.sleep(0.02)

    def shot(self, name, widget=None):
        if self.shots:
            self.pump()
            Path(self.shots).mkdir(parents=True, exist_ok=True)
            (widget or self.win).grab().save(str(Path(self.shots) / f"{name}.png"))

    def add_installer(self, name="Cool Game Setup.exe", size=4_000_000):
        p = self.downloads / name
        p.write_bytes(b"MZ" + b"\0" * size)
        return p

    def key(self, k):
        QTest.keyClick(QApplication.focusWidget(), k)
        self.pump()

    def test_home_shows_found_installers(self):
        self.shot("1-home-empty")
        self.add_installer("setup_the_witcher_3_goty_1.32_(10709).exe")
        self.add_installer("Firefox Setup 120.0.exe", 1000)
        self.win.go_home()
        titles = [t.title for t in self.win.home.tiles]
        self.assertEqual(titles[0], "Browse files")
        self.assertEqual(sorted(titles[1:]), ["Firefox", "The Witcher 3 Goty"])
        self.shot("2-home-found")

    def test_install_from_tile_ends_in_steam_with_icon_and_art(self):
        lnk = self.tmp / "x.lnk"
        lnk.write_bytes(make_lnk(r"C:\Program Files\Cool Game\bin\CoolGame.exe"))
        pe = self.tmp / "real.exe"
        pe.write_bytes(make_pe(bmp_icon(32), width=32))
        os.environ.update(FAKE_LNK=str(lnk), FAKE_EXE_SRC=str(pe), FAKE_SLEEP="1")
        inst = self.add_installer()
        (self.downloads / "Cool Game Setup-1.bin").write_bytes(b"x" * 1000)
        self.win.go_home()
        self.answers = [0]  # "Install"
        self.win.home.tiles[1].click()
        self.assertEqual(self.asked, ["Install Cool Game?"])
        self.wait_for(lambda: "installer" in self.win.progress.status.text())
        self.shot("3-installing")
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        self.shot("4-done")
        self.assertIn("Cool Game Deluxe is in your Steam library", self.win.done.heading.text())

        app = core.Library(self.paths).load()[0]
        self.assertTrue(Path(app.icon).is_file())
        grid = self.steam / "userdata/12345/config/grid"
        for suffix in ("p", "", "_hero", "_logo"):
            self.assertTrue((grid / f"{app.steam_appid}{suffix}.png").is_file(), suffix)
        sc = core.vdf_loads((self.steam / "userdata/12345/config/shortcuts.vdf").read_bytes())["shortcuts"]["0"]
        self.assertEqual(sc["icon"], app.icon)

        # Delete the installer (and its .bin part) from the done page.
        self.assertIn("Delete installer", self.win.done.delete_btn.text())
        self.answers = [0]
        self.win.done.delete_btn.click()
        self.assertFalse(inst.exists())
        self.assertFalse((self.downloads / "Cool Game Setup-1.bin").exists())
        self.assertFalse(self.win.done.delete_btn.isVisible())

        # Uninstalling cleans up the generated art and icon too.
        core.uninstall(app, self.paths, roots=[self.steam])
        self.assertFalse(any(grid.iterdir()))
        self.assertFalse(Path(app.icon).exists())

    def test_user_artwork_is_never_overwritten(self):
        from protonlaunch import artwork
        grid = self.steam / "userdata/12345/config/grid"
        grid.mkdir(parents=True)
        (grid / "123p.jpg").write_bytes(b"mine")
        written = artwork.write_steam_artwork(123, "X", None, [grid])
        self.assertNotIn(str(grid / "123p.png"), written)
        self.assertEqual(len(written), 3)

    def test_keyboard_and_controller_style_navigation(self):
        for n in ("a.exe", "b.exe", "c.exe"):
            self.add_installer(n, 10)
        self.win.go_home()
        tiles = self.win.home.tiles
        self.wait_for(lambda: QApplication.focusWidget() is tiles[1])
        self.key(Qt.Key.Key_Right)
        self.assertIs(QApplication.focusWidget(), tiles[2])
        self.key(Qt.Key.Key_Left)
        self.key(Qt.Key.Key_Left)
        self.assertIs(QApplication.focusWidget(), tiles[0])
        self.key(Qt.Key.Key_Left)  # nothing further left: stays put
        self.assertIs(QApplication.focusWidget(), tiles[0])
        self.key(Qt.Key.Key_Return)  # A on "Browse files"
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.browser)
        self.assertEqual(self.win.browser.cwd, self.downloads)
        self.key(Qt.Key.Key_Escape)  # B at a top-level place goes back home
        self.assertIs(self.win.stack.currentWidget(), self.win.home)

    def test_gamepad_actions(self):
        for n in ("a.exe", "b.exe"):
            self.add_installer(n, 10)
        self.win.go_home()
        tiles = self.win.home.tiles
        self.wait_for(lambda: QApplication.focusWidget() is tiles[1])
        nav = self.win.nav
        nav.on_pad("right", True)
        nav.on_pad("right", False)
        self.pump()
        self.assertIs(QApplication.focusWidget(), tiles[2])
        self.answers = [1]  # A opens the confirm sheet; answer Cancel
        nav.on_pad("a", True)
        self.wait_for(lambda: self.asked == ["Install A?"])
        nav.on_pad("a", False)
        nav.on_pad("x", True)  # X = Browse
        self.pump()
        self.assertIs(self.win.stack.currentWidget(), self.win.browser)
        nav.on_pad("x", False)
        nav.on_pad("b", True)
        self.pump()
        self.assertIs(self.win.stack.currentWidget(), self.win.home)

    def test_browser_folders_and_back(self):
        sub = self.downloads / "Some Game"
        sub.mkdir()
        (sub / "setup.exe").write_bytes(b"MZ")
        (sub / "notes.txt").write_text("x")
        self.win.browse_installers()
        rows = [self.win.browser.list.item(i).text() for i in range(self.win.browser.list.count())]
        self.assertEqual(rows, ["Some Game"])
        self.win.browser._activate(self.win.browser.list.item(0))
        rows = [self.win.browser.list.item(i).text().split()[0] for i in range(self.win.browser.list.count())]
        self.assertEqual(rows, ["Up", "setup.exe"])
        self.assertEqual(self.win.browser.list.currentRow(), 1)
        self.shot("5-browse")
        self.answers = [1]  # Cancel on the confirm sheet
        self.win.browser._activate(self.win.browser.list.item(1))
        self.assertEqual(self.asked, ["Install Some Game?"])
        self.win.browser.back()
        self.assertEqual(self.win.browser.cwd, self.downloads)

    def test_nothing_installed_offers_portable(self):
        os.environ["FAKE_NOTHING"] = "1"
        inst = self.add_installer("PortableTool.exe", 10)
        self.win.start_install(inst)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.pick)
        self.assertEqual(self.win.pick.heading.text(), "Nothing was installed")
        self.shot("6-pick-nothing")
        self.win.use_portable()
        self.assertIs(self.win.stack.currentWidget(), self.win.done)

    def test_failure_is_explained(self):
        os.environ["FAKE_BROKEN"] = "1"
        self.win.start_install(self.add_installer())
        self.wait_for(lambda: "Install failed" in self.asked)
        self.assertIs(self.win.stack.currentWidget(), self.win.home)

    def test_update_banner_download_and_restart(self):
        import hashlib
        import json
        from protonlaunch import app as app_mod
        from protonlaunch import updater
        from tests.test_update import NEW_APP, Server
        web = self.tmp / "web" / "bin"
        web.mkdir(parents=True)
        (web / updater.ASSET).write_bytes(NEW_APP)
        (web / "latest.json").write_text(json.dumps(
            {"version": "9.0.0", "sha256": hashlib.sha256(NEW_APP).hexdigest(), "notes": "Shiny new things."}))
        server = Server(self.tmp / "web")
        target = self.tmp / "installed" / "protonlaunch"
        target.parent.mkdir()
        target.write_bytes(b"old app")
        restarted = []
        orig = (updater.self_path, updater.restart)
        updater.self_path = lambda: target
        updater.restart = lambda t, args=None: restarted.append(t)
        os.environ["PROTONLAUNCH_UPDATE_BASE"] = f"{server.url}/bin"
        try:
            win = app_mod.MainWindow(self.paths, check_updates=True)  # checks in the background at start
            win.installer_dirs = [self.downloads]
            win.show()
            self.wait_for(lambda: win.home.banner.isVisible())
            self.assertIn("9.0.0 is available", win.home.banner_text.text())
            self.shot("8-update-banner", win)
            win.home.update_btn.click()
            self.assertIs(win.stack.currentWidget(), win.updating)
            self.wait_for(lambda: win.updating.restart_btn.isVisible())
            self.shot("9-update-done", win)
            self.assertEqual(target.read_bytes(), NEW_APP)
            self.assertFalse(win.home.banner.isVisible())
            win.updating.restart_btn.click()
            self.assertEqual(restarted, [target])
            win.close()
        finally:
            updater.self_path, updater.restart = orig
            del os.environ["PROTONLAUNCH_UPDATE_BASE"]
            server.close()

    def test_sheet_screenshot(self):
        if not self.shots:
            self.skipTest("screenshots only")
        from protonlaunch.widgets import Sheet
        s = Sheet(self.win, "Install Cool Game?", "/home/deck/Downloads/Cool Game Setup.exe\n\nInstaller: 3.8 GB"
                  "   ·   Free space: 200.1 GB", ("Install", "Cancel"))
        s.show()
        self.pump(10)
        self.shot("7-sheet", s)
        s.close()


if __name__ == "__main__":
    unittest.main()

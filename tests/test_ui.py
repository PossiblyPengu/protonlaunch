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
        self.win.pending = None  # (closing would otherwise ask about an unfinished pick)
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
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)

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

    def test_uninstall_from_installed_programs(self):
        os.environ["FAKE_TO_D"] = "1"
        inst = self.add_installer("Cool Game Setup.exe", 10)
        self.win.start_install(inst)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        self.win.go_home()
        self.assertTrue(self.win.home.manage_btn.isVisible())
        self.assertIn("(1)", self.win.home.manage_btn.text())
        self.win.home.manage_btn.click()
        page = self.win.installed
        self.assertIs(self.win.stack.currentWidget(), page)
        self.assertEqual(page.list.count(), 1)
        self.wait_for(lambda: "MB" in page.list.item(0).text())  # size filled in from a background thread
        self.assertIn("In Steam", page.list.item(0).text())
        self.shot("10-installed", self.win)
        app = core.Library(self.paths).load()[0]
        self.answers = [1]  # Keep
        page._activate(page.list.item(0))
        self.assertTrue(Path(app.prefix).exists())
        self.answers = [0]  # Uninstall
        page._activate(page.list.item(0))
        self.assertIn("Uninstall Cool Game?", self.asked)
        self.wait_for(lambda: not Path(app.prefix).exists())  # deleted in the background
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.home)
        self.assertFalse(Path(app.extra_dirs[0]).exists())
        self.assertEqual(core.Library(self.paths).load(), [])
        self.assertIs(self.win.stack.currentWidget(), self.win.home)
        self.assertFalse(self.win.home.manage_btn.isVisible())

    def test_add_back_to_steam_from_installed_programs(self):
        inst = self.add_installer("Cool Game Setup.exe", 10)
        self.win.start_install(inst)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        app = core.Library(self.paths).load()[0]
        core.remove_steam_shortcut(app.steam_appid, [self.steam])  # e.g. Steam dropped it on restart
        self.win.show_installed()
        page = self.win.installed
        self.assertIn("Not in Steam", page.list.item(0).text())
        self.answers = [0]  # "Add to Steam"
        page._activate(page.list.item(0))
        self.assertEqual(self.asked[-1], "Cool Game")
        self.wait_for(lambda: "In Steam" in page.list.item(0).text() and "Not in" not in page.list.item(0).text())
        self.assertTrue(core.in_steam(core.Library(self.paths).load()[0], [self.steam]))

    def test_with_steam_running_the_program_is_sent_once_and_followed(self):
        sent = []
        orig_request, orig_wait = core.request_steam_add, core.STEAM_ADD_WAIT
        core.request_steam_add = lambda f: (sent.append(f), True)[1]  # Steam takes it, saves its list later
        core.STEAM_ADD_WAIT = 0.3
        core.steam_is_running = lambda: True
        vdf = self.steam / "userdata/12345/config/shortcuts.vdf"
        try:
            self.win.start_install(self.add_installer("Cool Game Setup.exe", 10))
            self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
            self.assertIn("sent to Steam", self.win.done.heading.text())
            self.assertEqual(len(sent), 1)
            self.assertFalse(vdf.exists())  # Steam's own list is never edited while it runs
            self.win.show_installed()
            page = self.win.installed
            self.assertIn("Sent to Steam", page.list.item(0).text())
            self.answers = [2]  # Cancel: it's probably there already
            page._activate(page.list.item(0))
            self.assertEqual(self.asked[-1], "Cool Game")
            self.pump(10)
            self.assertEqual(len(sent), 1)
            # Steam saves its list, with the shortcut under an id of its own: ProtonLaunch follows it.
            app = core.Library(self.paths).load()[0]
            vdf.write_bytes(core.vdf_dumps({"shortcuts": {"0": {
                "appid": -1234, "AppName": "Cool Game", "Exe": f'"{app.launcher}"'}}}))
            self.win.sync_steam_ids()
            app = core.Library(self.paths).load()[0]
            self.assertEqual((app.steam_appid, app.steam_added), (-1234 & 0xFFFFFFFF, "live"))
            self.assertTrue(app.artwork)
            self.assertTrue(all(Path(a).name.startswith(str(app.steam_appid)) for a in app.artwork))
            page.refresh()
            self.assertIn("In Steam", page.list.item(0).text())
        finally:
            core.request_steam_add, core.STEAM_ADD_WAIT = orig_request, orig_wait

    def test_leftovers_from_interrupted_installs_are_offered_for_deletion(self):
        keep, gone = self.paths.prefixes / "kept-one", self.paths.prefixes / "cool-game"
        for d in (keep, gone):
            (d / "pfx").mkdir(parents=True)
            (d / "pfx/big").write_bytes(b"x" * 1000)
        self.answers = [1]  # Keep: never asked about these again
        self.win.check_leftovers()
        self.wait_for(lambda: "Unfinished installs" in self.asked)
        self.assertTrue(keep.exists() and gone.exists())
        self.asked.clear()
        self.win.check_leftovers()
        self.pump(20)
        self.assertEqual(self.asked, [])
        self.paths.remember(kept_leftovers=["kept-one"])
        self.answers = [0]  # Delete
        self.win.check_leftovers()
        self.wait_for(lambda: not gone.exists())
        self.assertTrue(keep.exists())

    def test_unfinished_install_is_finished_from_installed_programs(self):
        job = core.Installer(self.add_installer("Cool Game Setup.exe", 10), self.paths,
                             steam_roots_override=[self.steam])
        pending = job.run()
        job.close()  # ProtonLaunch was closed on the pick screen
        self.win.go_home()
        self.assertTrue(self.win.home.manage_btn.isVisible())
        self.assertIn("1 unfinished", self.win.home.manage_btn.text())
        self.win.show_installed()
        page = self.win.installed
        self.assertEqual(page.list.count(), 1)
        self.assertIn("Unfinished install", page.list.item(0).text())
        self.answers = [0]  # Finish setup
        page._activate(page.list.item(0))
        self.wait_for(lambda: self.win.stack.currentWidget() in (self.win.done, self.win.pick))
        if self.win.stack.currentWidget() is self.win.pick:
            self.win.pick.use()
            self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        app = core.Library(self.paths).load()[0]
        self.assertEqual(app.prefix, str(pending.compat_dir))
        self.assertTrue(core.in_steam(app, [self.steam]))

    def test_remove_duplicate_shortcuts_only_with_steam_closed(self):
        vdf = self.steam / "userdata/12345/config/shortcuts.vdf"
        e = {"appid": 1, "AppName": "Emu", "Exe": '"/emu"', "StartDir": '"/"', "LaunchOptions": ""}
        vdf.write_bytes(core.vdf_dumps({"shortcuts": {"0": e, "1": dict(e), "2": dict(e)}}))
        core.steam_is_running = lambda: True
        self.win.remove_duplicates()
        self.assertEqual(self.asked[-1], "Close Steam first")
        self.assertEqual(len(core.steam_shortcuts([self.steam])), 3)
        core.steam_is_running = lambda: False
        self.answers = [0]  # Remove duplicates
        self.win.remove_duplicates()
        self.assertEqual(self.asked[-1], "Remove duplicate shortcuts?")
        self.assertEqual(len(core.steam_shortcuts([self.steam])), 1)
        self.win.remove_duplicates()
        self.assertEqual(self.asked[-1], "No duplicates")

    def test_long_paths_never_widen_the_window(self):
        deep = self.downloads.joinpath(*[f"A Rather Long Folder Name Number {i}" for i in range(8)])
        deep.mkdir(parents=True)
        inst = deep / "setup.exe"
        inst.write_bytes(b"MZ")
        os.environ["FAKE_SLEEP"] = "1"
        self.win.start_install(inst)
        self.wait_for(lambda: "installer" in self.win.progress.status.text())
        self.pump(10)
        self.assertLessEqual(self.win.width(), 1280)
        cancel = self.win.progress.cancel_btn
        self.assertLessEqual(cancel.mapTo(self.win, cancel.rect().bottomRight()).x(), self.win.width())
        self.assertEqual(self.win.progress.source.text(), str(inst))  # full path kept (and in tooltip)
        self.shot("11-long-path", self.win)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)

    def test_reinstall_and_low_space_are_mentioned(self):
        inst = self.add_installer("Cool Game Setup.exe", 10)
        self.win.start_install(inst)
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.done)
        texts = []
        from protonlaunch.widgets import Sheet
        Sheet.ask = staticmethod(lambda parent, title, text="", *a, **k: (texts.append(text), 1)[1])
        self.win.confirm_install(inst)
        self.assertIn("already installed this as Cool Game", texts[-1])
        orig = core.free_space
        core.free_space = lambda p: 5  # bytes
        try:
            self.win.confirm_install(inst)
        finally:
            core.free_space = orig
        self.assertIn("Free space looks tight", texts[-1])

    def test_leaving_the_pick_screen_asks_first(self):
        os.environ["FAKE_NOTHING"] = "1"
        self.win.start_install(self.add_installer("Tool.exe", 10))
        self.wait_for(lambda: self.win.stack.currentWidget() is self.win.pick)
        prefix = self.win.pending.compat_dir
        self.answers = [1]  # Keep
        self.win.pick.back()
        self.assertTrue(prefix.exists())
        self.assertIs(self.win.stack.currentWidget(), self.win.pick)
        self.answers = [0]  # Delete it
        self.win.pick.back()
        self.assertFalse(prefix.exists())
        self.assertIs(self.win.stack.currentWidget(), self.win.home)

    def test_sheet_is_an_overlay_that_confines_focus(self):
        from protonlaunch.widgets import Sheet
        self.win.go_home()
        results = []

        def answer():
            sheet = Sheet.current
            results.append(sheet is not None and sheet.parent() is self.win)
            results.append(self.win.centralWidget().isEnabled())  # everything behind is disabled
            if sheet is None:
                return
            sheet.buttons[0].setFocus()
            self.pump()
            QTest.keyClick(sheet.buttons[0], Qt.Key.Key_Right)  # D-pad moves between the sheet's buttons
            self.pump()
            results.append(QApplication.focusWidget() is sheet.buttons[1])
            QTest.keyClick(sheet.buttons[1], Qt.Key.Key_Escape)  # B closes it
            if Sheet.current is sheet:  # safety net so a failure can't hang the test
                sheet.reject()

        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, answer)
        choice = self._orig_ask(self.win, "Question", "?", ("One", "Two"))
        self.assertEqual(results, [True, False, True])
        self.assertEqual(choice, -1)
        self.assertIsNone(Sheet.current)
        self.assertTrue(self.win.centralWidget().isEnabled())

    def test_second_launch_hands_installer_to_the_open_window(self):
        from protonlaunch.app import SingleInstance
        name = f"protonlaunch-test-{os.getpid()}"
        got = []
        inst = SingleInstance()
        inst.listen(got.append, name=name)
        self.assertTrue(SingleInstance.hand_off(["/home/deck/Downloads/setup.exe"], name=name))
        self.wait_for(lambda: got)
        self.assertEqual(got, [["/home/deck/Downloads/setup.exe"]])
        inst.server.close()
        self.assertFalse(SingleInstance.hand_off(["x"], name=f"{name}-nobody"))

    def test_double_click_picks_once(self):
        from PyQt6.QtTest import QTest
        sub = self.downloads / "Folder"
        sub.mkdir()
        (sub / "inner").mkdir()
        self.win.browse_installers()
        lst = self.win.browser.list
        r = lst.visualItemRect(lst.item(0)).center()
        b, v = Qt.MouseButton.LeftButton, lst.viewport()
        QTest.mousePress(v, b, pos=r)
        QTest.mouseRelease(v, b, pos=r)  # click: opens "Folder"
        QTest.mouseDClick(v, b, pos=r)   # the double-click lands on "Up one folder" now
        QTest.mouseRelease(v, b, pos=r)
        self.pump()
        self.assertEqual(self.win.browser.cwd, sub)  # not bounced back up (or into "inner")

    def test_sheet_screenshot(self):
        if not self.shots:
            self.skipTest("screenshots only")
        from protonlaunch.widgets import Sheet
        s = Sheet(self.win, "Install Cool Game?", "/home/deck/Downloads/Cool Game Setup.exe\n\nInstaller: 3.8 GB"
                  "   ·   Free space: 200.1 GB", ("Install", "Cancel"))
        s.show()
        self.pump(10)
        self.shot("7-sheet", self.win)  # the overlay composited over the window
        s.close()


if __name__ == "__main__":
    unittest.main()

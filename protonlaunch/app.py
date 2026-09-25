"""ProtonLaunch window: pick an installer, everything else is automatic."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, core

STYLE = """
QWidget { background: #171d25; color: #e6edf3; font-size: 18px; }
QLabel#title { font-size: 34px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #8b98a5; }
QLabel#status { font-size: 22px; }
QLabel#done { font-size: 30px; font-weight: 700; color: #59bf40; }
QPushButton {
  background: #2a3441; border: 2px solid #2a3441; border-radius: 12px;
  padding: 12px 24px; min-height: 40px;
}
QPushButton:hover, QPushButton:focus { border-color: #1a9fff; }
QPushButton:pressed { background: #1a9fff; }
QPushButton#primary { background: #1a9fff; border-color: #1a9fff; font-size: 24px; font-weight: 700; }
QPushButton#primary:hover, QPushButton#primary:focus { border-color: #ffffff; }
QPushButton#danger { color: #ff6b6b; }
QFrame#row { background: #1f2731; border-radius: 12px; }
QFrame#row QLabel { background: transparent; }
QListWidget, QPlainTextEdit, QLineEdit {
  background: #10151b; border: 2px solid #2a3441; border-radius: 10px; padding: 6px;
}
QListWidget::item { padding: 14px; border-radius: 8px; }
QListWidget::item:selected { background: #1a9fff; color: white; }
QProgressBar { border: none; background: #2a3441; border-radius: 6px; height: 12px; }
QProgressBar::chunk { background: #1a9fff; border-radius: 6px; }
QScrollArea { border: none; }
"""


def label(text: str, obj: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


def button(text: str, obj: str = "", slot=None) -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def pick_file(parent: QWidget, title: str, start: Path, filters: str) -> Path | None:
    """Qt's own file dialog: works the same in Desktop Mode and Game Mode, with touch-sized text."""
    dlg = QFileDialog(parent, title, str(start), filters)
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    places = [Path.home() / "Downloads", Path.home() / "Desktop", Path.home()]
    media = Path("/run/media")
    if media.is_dir():
        places += [p for p in media.glob("*/*") if p.is_dir()] + [p for p in media.iterdir() if p.is_dir()]
    dlg.setSidebarUrls([QUrl.fromLocalFile(str(p)) for p in places if p.is_dir()])
    dlg.resize(1100, 700)
    if dlg.exec() and dlg.selectedFiles():
        return Path(dlg.selectedFiles()[0])
    return None


class InstallThread(QThread):
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    done = pyqtSignal(object)  # core.PendingInstall
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, installer: Path, paths: core.Paths):
        super().__init__()
        self.job = core.Installer(installer, paths, status=self.status.emit, log=self.log.emit)

    def run(self) -> None:
        try:
            self.done.emit(self.job.run())
        except core.Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001 — anything here is shown to the user
            self.failed.emit(str(e))


class AppRow(QFrame):
    def __init__(self, app: core.App, window: "MainWindow"):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 12, 12, 12)
        text = QVBoxLayout()
        name = label(app.name)
        name.setStyleSheet("font-size: 22px; font-weight: 600;")
        text.addWidget(name)
        text.addWidget(label(Path(app.exe).name, "muted"))
        lay.addLayout(text, 1)
        lay.addWidget(button("▶  Play", "primary", lambda: window.play(app)))
        lay.addWidget(button("Change program", slot=lambda: window.change_exe(app)))
        lay.addWidget(button("Remove", "danger", lambda: window.remove(app)))


class MainWindow(QMainWindow):
    def __init__(self, paths: core.Paths | None = None):
        super().__init__()
        self.paths = paths or core.Paths.default()
        self.library = core.Library(self.paths)
        self.thread: InstallThread | None = None
        self.job: core.Installer | None = None
        self.pending: core.PendingInstall | None = None
        self.last_app: core.App | None = None

        self.setWindowTitle("ProtonLaunch")
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._build_home()
        self._build_progress()
        self._build_pick()
        self._build_done()
        self.refresh_library()
        self.show_page(self.home)

    # ── pages ────────────────────────────────────────────────────────────

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(48, 36, 48, 36)
        lay.setSpacing(16)
        self.stack.addWidget(w)
        return w, lay

    def _build_home(self) -> None:
        self.home, lay = self._page()
        lay.addWidget(label("ProtonLaunch", "title"))
        lay.addWidget(label("Install Windows programs and games on your Steam Deck.", "subtitle"))
        self.install_btn = button("+  Install a Windows program", "primary", self.choose_installer)
        self.install_btn.setMinimumHeight(96)
        lay.addWidget(self.install_btn)
        lay.addWidget(label("Pick the setup .exe or .msi. ProtonLaunch installs it and adds it to Steam.", "muted"))
        lay.addSpacing(12)
        self.library_title = label("Installed", "subtitle")
        self.library_title.setStyleSheet("font-size: 22px; font-weight: 600;")
        lay.addWidget(self.library_title)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(10)
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.rows)
        outer.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)
        foot = QHBoxLayout()
        self.space_label = label("", "muted", wrap=False)
        foot.addWidget(self.space_label)
        foot.addStretch(1)
        foot.addWidget(button("Add ProtonLaunch to Steam", slot=self.add_self_to_steam))
        lay.addLayout(foot)

    def _build_progress(self) -> None:
        self.progress, lay = self._page()
        self.progress_title = label("", "title")
        lay.addWidget(self.progress_title)
        lay.addStretch(1)
        self.status = label("", "status", wrap=False)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        lay.addWidget(bar)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFont(QFont("monospace", 11))
        self.log_view.hide()
        lay.addWidget(self.log_view, 3)
        lay.addStretch(1)
        btns = QHBoxLayout()
        self.details_btn = button("Show details", slot=self.toggle_log)
        btns.addWidget(self.details_btn)
        btns.addStretch(1)
        self.continue_btn = button("Installer is done — continue", "primary", self.continue_now)
        btns.addWidget(self.continue_btn)
        self.cancel_btn = button("Cancel", "danger", self.cancel_install)
        btns.addWidget(self.cancel_btn)
        lay.addLayout(btns)

    def _build_pick(self) -> None:
        self.pick, lay = self._page()
        self.pick_title = label("Which one is the program?", "title")
        lay.addWidget(self.pick_title)
        self.pick_hint = label("", "subtitle")
        lay.addWidget(self.pick_hint)
        self.pick_list = QListWidget()
        self.pick_list.itemDoubleClicked.connect(lambda _i: self.use_picked())
        lay.addWidget(self.pick_list, 10)
        row = QHBoxLayout()
        row.addWidget(label("Name in Steam:", wrap=False))
        self.name_edit = QLineEdit()
        row.addWidget(self.name_edit, 1)
        lay.addLayout(row)
        btns = QHBoxLayout()
        self.portable_btn = button("No install needed — add this file itself", slot=self.use_portable)
        btns.addWidget(self.portable_btn)
        btns.addWidget(button("Browse…", slot=self.browse_picked))
        btns.addStretch(1)
        btns.addWidget(button("Cancel", "danger", self.discard_pending))
        lay.addStretch(1)
        self.use_btn = button("Use this", "primary", self.use_picked)
        btns.addWidget(self.use_btn)
        lay.addLayout(btns)

    def _build_done(self) -> None:
        self.done, lay = self._page()
        lay.addStretch(1)
        self.done_title = label("", "done")
        self.done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_title)
        self.done_text = label("", "subtitle")
        self.done_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_text)
        lay.addStretch(1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(button("Done", slot=lambda: self.show_page(self.home)))
        btns.addWidget(button("▶  Play now", "primary", lambda: self.last_app and self.play(self.last_app)))
        btns.addStretch(1)
        lay.addLayout(btns)

    def show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        if page is self.home:
            self.refresh_library()
            self.install_btn.setFocus()

    def refresh_library(self) -> None:
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        apps = sorted(self.library.load(), key=lambda a: a.name.lower())
        for app in apps:
            self.rows.addWidget(AppRow(app, self))
        self.library_title.setVisible(bool(apps))
        free = core.human_size(core.free_space(self.paths.root))
        self.space_label.setText(f"v{__version__}  ·  {free} free on internal storage")

    # ── install flow ─────────────────────────────────────────────────────

    def choose_installer(self) -> None:
        start = Path.home() / "Downloads"
        path = pick_file(self, "Choose a Windows installer", start if start.is_dir() else Path.home(),
                         "Windows installers (*.exe *.EXE *.msi *.MSI);;All files (*)")
        if path:
            self.start_install(path)

    def start_install(self, installer: Path) -> None:
        if self.thread is not None:
            return
        installer = Path(installer)
        self.progress_title.setText(f"Installing {core.guess_name(installer)}")
        self.status.setText("Getting ready…")
        self.log_view.clear()
        self.continue_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.show_page(self.progress)
        t = InstallThread(installer, self.paths)
        t.status.connect(self.on_status)
        t.log.connect(self.log_view.appendPlainText)
        t.done.connect(self.on_installed)
        t.failed.connect(self.on_failed)
        t.cancelled.connect(self.on_cancelled)
        t.finished.connect(self._thread_finished)
        self.thread = t
        self.job = t.job
        t.start()

    def _thread_finished(self) -> None:
        if self.job:
            # The thread's signals die with it; route any later updates straight to the UI.
            self.job.status = self.status.setText
            self.job._log_cb = self.log_view.appendPlainText
        if self.thread:
            self.thread.deleteLater()
        self.thread = None

    def on_status(self, text: str) -> None:
        self.status.setText(text)
        self.continue_btn.setVisible(bool(self.thread) and self.thread.job.stage == "wait")

    def toggle_log(self) -> None:
        show = not self.log_view.isVisible()
        self.log_view.setVisible(show)
        self.details_btn.setText("Hide details" if show else "Show details")

    def continue_now(self) -> None:
        if self.thread:
            self.continue_btn.hide()
            self.thread.job.continue_now()

    def cancel_install(self) -> None:
        if self.thread:
            self.cancel_btn.setEnabled(False)
            self.status.setText("Cancelling…")
            self.thread.job.cancel()

    def on_cancelled(self) -> None:
        self.show_page(self.home)

    def on_failed(self, message: str) -> None:
        self.show_page(self.home)
        if message == "NO_RUNTIME":
            box = QMessageBox(self)
            box.setWindowTitle("Proton is needed")
            box.setText("ProtonLaunch needs Proton to run Windows programs.\n\n"
                        "Tap “Install Proton” and Steam will download it. "
                        "When it finishes, try again.")
            install = box.addButton("Install Proton", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is install:
                QDesktopServices.openUrl(QUrl(f"steam://install/{core.PROTON_EXPERIMENTAL_APPID}"))
            return
        QMessageBox.warning(self, "Install failed", message)

    def on_installed(self, pending: core.PendingInstall) -> None:
        self.pending = pending
        cands = pending.candidates
        if core.is_confident(cands, pending.installer):
            self.finish(cands[0].exe, core.best_name(pending, cands[0]))
            return
        # Couldn't decide on our own: show the best guesses.
        self.pick_list.clear()
        drive_c = pending.pfx / "drive_c"
        for c in cands[:12]:
            try:
                where = str(c.exe.parent.relative_to(drive_c))
            except ValueError:
                where = str(c.exe.parent)
            item = QListWidgetItem(f"{c.exe.name}    —    {where}")
            item.setData(Qt.ItemDataRole.UserRole, str(c.exe))
            self.pick_list.addItem(item)
        if cands:
            self.pick_list.setCurrentRow(0)
            self.pick_hint.setText("The installer finished. Pick the program to add to Steam.")
        else:
            self.pick_hint.setText("Nothing new was installed. If this file is the program itself "
                                   "(no setup needed), tap the first button. Otherwise the installer "
                                   "may have been closed early — cancel and try again.")
        self.pick_title.setText("Which one is the program?" if cands else "Nothing was installed")
        self.pick_list.setVisible(bool(cands))
        self.use_btn.setVisible(bool(cands))
        self.portable_btn.setVisible(pending.installer.suffix.lower() == ".exe")
        self.portable_btn.setObjectName("" if cands else "primary")
        self.portable_btn.style().polish(self.portable_btn)
        self.name_edit.setText(pending.name)
        self.show_page(self.pick)

    def use_picked(self) -> None:
        item = self.pick_list.currentItem()
        if item and self.pending:
            self.finish(Path(item.data(Qt.ItemDataRole.UserRole)), self.name_edit.text())

    def browse_picked(self) -> None:
        if not self.pending:
            return
        path = pick_file(self, "Choose the program", self.pending.pfx / "drive_c",
                         "Programs (*.exe *.EXE);;All files (*)")
        if path:
            self.finish(path, self.name_edit.text())

    def use_portable(self) -> None:
        if self.pending:
            self.finish(core.adopt_portable(self.pending), self.name_edit.text())

    def discard_pending(self) -> None:
        if self.pending:
            if self.job:
                self.job.close()
            shutil.rmtree(self.pending.compat_dir, ignore_errors=True)
            self.pending = None
        self.show_page(self.home)

    def finish(self, exe: Path, name: str) -> None:
        pending, self.pending = self.pending, None
        assert pending is not None and self.job is not None
        try:
            app = self.job.finish(pending, exe, name)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Couldn't finish", str(e))
            self.show_page(self.home)
            return
        self.last_app = app
        self.done_title.setText(f"✓  {app.name} is installed")
        if app.steam_appid:
            msg = "It's been added to your Steam library."
            if core.steam_is_running():
                msg += "\nRestart Steam to see it (Steam menu → Power → Restart Steam)."
        else:
            msg = "Couldn't find a Steam account to add it to — you can still play it from here."
        self.done_text.setText(f"{msg}\n\nSteam will launch: {Path(app.exe).name}")
        self.show_page(self.done)

    # ── library actions ──────────────────────────────────────────────────

    def play(self, app: core.App) -> None:
        try:
            core.launch(app)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't start", str(e))

    def change_exe(self, app: core.App) -> None:
        path = pick_file(self, f"Choose the program for {app.name}", Path(app.prefix) / "pfx/drive_c",
                         "Programs (*.exe *.EXE);;All files (*)")
        if not path:
            return
        app.exe = str(path)
        core.write_launcher(app, self.paths, (core.steam_roots() or [None])[0])
        self.library.upsert(app)
        self.refresh_library()

    def remove(self, app: core.App) -> None:
        ok = QMessageBox.question(
            self, "Remove", f"Remove {app.name}?\n\nThis deletes the program, its saved data "
            "and its Steam shortcut.",
        )
        if ok == QMessageBox.StandardButton.Yes:
            core.uninstall(app, self.paths)
            self.refresh_library()

    def add_self_to_steam(self) -> None:
        exe = Path(sys.executable if getattr(sys, "frozen", False) else Path.home() / ".local/bin/protonlaunch")
        if not exe.exists():
            QMessageBox.information(self, "Add to Steam", "Install ProtonLaunch with get.sh first.")
            return
        _appid, users = core.add_steam_shortcut("ProtonLaunch", str(exe), str(exe.parent))
        QMessageBox.information(
            self, "Add to Steam",
            "Added! Restart Steam to find ProtonLaunch in your library." if users
            else "No Steam account found on this device.",
        )

    # ── drag & drop ──────────────────────────────────────────────────────

    def _dropped_installer(self, event) -> Path | None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            p = Path(urls[0].toLocalFile())
            if p.suffix.lower() in core.INSTALLER_SUFFIXES:
                return p
        return None

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self.stack.currentWidget() is self.home and self._dropped_installer(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        p = self._dropped_installer(event)
        if p:
            self.start_install(p)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.thread is not None:
            if QMessageBox.question(self, "Quit", "An install is running. Cancel it and quit?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.thread.job.cancel()
            self.thread.wait(15000)
        event.accept()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    if "--version" in args:
        print(f"ProtonLaunch {__version__}")
        return 0
    if "-h" in args or "--help" in args:
        print("usage: protonlaunch [INSTALLER.exe|.msi]\n\n"
              "Opens ProtonLaunch. Given an installer, starts installing it right away.")
        return 0
    app = QApplication(argv[:1])
    app.setApplicationName("ProtonLaunch")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    files = [a for a in args if not a.startswith("-")]
    if files:
        QTimer.singleShot(0, lambda: win.start_install(Path(files[0])))
    return app.exec()

"""ProtonLaunch window: a Steam Deck–first installer. Pick a setup file; the program lands in Steam.

It is deliberately not a launcher or library — once installed, programs live in Steam.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QRectF, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, artwork, core, theme
from .nav import Nav
from .widgets import HintBar, Sheet, Steps, Tile, Toast, button, draw_glyph, label

COLUMNS = 5
MAX_FOUND = 2 * COLUMNS - 1  # two rows of tiles, the first being "Browse files"


def ago(ts: float) -> str:
    d = time.time() - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    if d < 2 * 86400:
        return "yesterday"
    if d < 30 * 86400:
        return f"{int(d // 86400)} days ago"
    return time.strftime("%b %d, %Y", time.localtime(ts))


def glyph_icon(kind: str) -> QIcon:
    pm = QPixmap(48, 48)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_glyph(p, QRectF(8, 8, 32, 32), kind, QColor(theme.TEXT_DIM))
    p.end()
    return QIcon(pm)


def pixmap(img: QImage, w: int, h: int) -> QPixmap:
    return QPixmap.fromImage(img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))


class InstallThread(QThread):
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    done = pyqtSignal(object)  # core.PendingInstall
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, installer: Path, paths: core.Paths, allow_no_container: bool = False):
        super().__init__()
        self.job = core.Installer(installer, paths, status=self.status.emit, log=self.log.emit,
                                  allow_no_container=allow_no_container)

    def run(self) -> None:
        try:
            self.done.emit(self.job.run())
        except core.Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001 — anything here is shown to the user
            self.failed.emit(str(e))


# ── Pages ────────────────────────────────────────────────────────────────────


class Page(QWidget):
    title = ""

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win

    def enter(self) -> None:
        """Called every time the page is shown."""

    def hints(self) -> list[tuple[str, str, Callable]]:
        return [("A", "Select", self.win.nav_activate), ("B", "Back", self.back)]

    def back(self) -> None:
        self.win.go_home()

    def x(self) -> None:
        pass

    def scroll_area(self) -> QScrollArea | None:
        return self.findChild(QScrollArea)


class HomePage(Page):
    """Pick what to install: installers found on the Deck, or browse for one."""

    def __init__(self, win):
        super().__init__(win)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(40, 26, 40, 26)
        lay.setSpacing(12)
        lay.addWidget(label("Install a Windows program", "h1"))
        lay.addWidget(label("Pick a setup file. ProtonLaunch installs it and adds the program to your "
                            "Steam library.", "dim"))
        lay.addSpacing(10)
        self.section = label("", "section")
        lay.addWidget(self.section)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        lay.addLayout(self.grid)
        self.note = label("", "muted")
        lay.addWidget(self.note)
        lay.addStretch(1)
        self.tiles: list[Tile] = []

    def refresh(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:  # hide + delete in place; setParent(None) would make it a stray top-level window
                w.hide()
                w.deleteLater()
        installed = {a.installer for a in self.win.library.load() if a.installer}
        found = core.find_installers(self.win.installer_dirs)
        shown = found[:MAX_FOUND]

        browse = Tile("Browse files", "Any folder or drive", glyph="folder")
        browse.clicked.connect(lambda: self.win.browse_installers())
        self.tiles = [browse]
        for f in shown:
            when = "Installed" if str(f.path) in installed else ago(f.mtime)
            t = Tile(core.guess_name(f.path), f"{core.human_size(f.size)} · {when}", glyph="download")
            t.setToolTip(str(f.path))
            t.clicked.connect(lambda _c=False, f=f: self.win.confirm_install(f.path))
            self.tiles.append(t)
        for i, t in enumerate(self.tiles):
            self.grid.addWidget(t, i // COLUMNS, i % COLUMNS, Qt.AlignmentFlag.AlignLeft)
            t.show()  # layouts show new children lazily; focus needs them visible now
        self.grid.setColumnStretch(COLUMNS, 1)

        self.section.setText(f"FOUND ON THIS DECK  ·  {len(found)}" if found else "FOUND ON THIS DECK")
        if not found:
            self.note.setText("No setup files found in Downloads, on the Desktop or on an SD card or USB "
                              "drive. Use Browse files to look anywhere else.")
        elif len(found) > len(shown):
            more = len(found) - len(shown)
            self.note.setText(f"{more} more installer{'s' if more != 1 else ''} found — use Browse files.")
        else:
            self.note.setText("")
        self.note.setVisible(bool(self.note.text()))

    def enter(self) -> None:
        self.refresh()
        (self.tiles[1] if len(self.tiles) > 1 else self.tiles[0]).setFocus()

    def hints(self):
        return [("A", "Select", self.win.nav_activate), ("X", "Browse", self.x), ("☰", "Menu", self.win.open_menu)]

    def back(self) -> None:
        pass

    def x(self) -> None:
        self.win.browse_installers()


class BrowserPage(Page):
    """A controller-friendly file browser (the desktop file dialog is awkward with a gamepad)."""

    title = "Browse"

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 22, 40, 20)
        lay.setSpacing(12)
        self.heading = label("Choose an installer", "h1")
        lay.addWidget(self.heading)
        self.where = label("", "muted", wrap=False)
        lay.addWidget(self.where)
        self.places = QHBoxLayout()
        self.places.setSpacing(10)
        lay.addLayout(self.places)
        self.list = QListWidget()
        self.list.setIconSize(self.list.iconSize() * 1.6)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        lay.addWidget(self.list, 1)
        self.cwd = Path.home()
        self.roots: list[Path] = []
        self.suffixes: tuple[str, ...] = core.INSTALLER_SUFFIXES
        self.on_pick: Callable[[Path], None] = lambda p: None
        self.on_back: Callable[[], None] = win.go_home
        self.icon_dir, self.icon_file, self.icon_up = glyph_icon("folder"), glyph_icon("download"), glyph_icon("up")

    def open(self, heading: str, places: list[tuple[str, Path]], suffixes: tuple[str, ...],
             on_pick: Callable[[Path], None], on_back: Callable[[], None], start: Path | None = None) -> None:
        self.heading.setText(heading)
        self.suffixes, self.on_pick, self.on_back = suffixes, on_pick, on_back
        places = [(n, p) for n, p in places if p.is_dir()]
        self.roots = [p for _n, p in places]
        while self.places.count():
            it = self.places.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for name, path in places:
            self.places.addWidget(button(name, slot=lambda p=path: self.show_dir(p)))
        self.places.addStretch(1)
        self.show_dir(start if start and start.is_dir() else (self.roots[0] if self.roots else Path.home()))

    def show_dir(self, path: Path) -> None:
        self.cwd = path
        self.where.setText(str(path))
        self.list.clear()
        if path not in self.roots and path.parent != path:
            it = QListWidgetItem(self.icon_up, "Up one folder")
            it.setData(Qt.ItemDataRole.UserRole, str(path.parent))
            self.list.addItem(it)
        try:
            entries = sorted(path.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            entries = []
        dirs = [e for e in entries if e.is_dir() and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and e.name.lower().endswith(self.suffixes)]
        for d in dirs:
            it = QListWidgetItem(self.icon_dir, d.name)
            it.setData(Qt.ItemDataRole.UserRole, str(d))
            self.list.addItem(it)
        for f in files:
            size = core.human_size(core.files_size(core.installer_files(f)))
            it = QListWidgetItem(self.icon_file, f"{f.name}     {size}")
            it.setData(Qt.ItemDataRole.UserRole, str(f))
            self.list.addItem(it)
        if not dirs and not files:
            it = QListWidgetItem("Nothing to pick in this folder")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(it)
        # Start on the first real entry rather than "Up one folder".
        has_up = path not in self.roots and path.parent != path
        self.list.setCurrentRow(1 if has_up and (dirs or files) else 0)
        self.list.setFocus()

    def _activate(self, item: QListWidgetItem) -> None:
        target = item.data(Qt.ItemDataRole.UserRole)
        if not target:
            return
        p = Path(target)
        if p.is_dir():
            self.show_dir(p)
        else:
            self.on_pick(p)

    def enter(self) -> None:
        self.list.setFocus()

    def hints(self):
        return [("A", "Open", self.win.nav_activate), ("B", "Back", self.back)]

    def back(self) -> None:
        if self.cwd not in self.roots and self.cwd.parent != self.cwd:
            self.show_dir(self.cwd.parent)
        else:
            self.on_back()


class InstallPage(Page):
    title = "Installing"
    STEP_OF = {"prepare": 0, "installer": 1, "wait": 1, "scan": 2, "steam": 3}

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 26, 48, 22)
        lay.setSpacing(14)
        self.heading = label("", "h1")
        lay.addWidget(self.heading)
        self.source = label("", "muted", wrap=False)
        lay.addWidget(self.source)
        lay.addSpacing(8)
        self.steps = Steps()
        lay.addWidget(self.steps)
        lay.addStretch(1)
        self.status = label("", "status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.elapsed = label("", "muted")
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.elapsed)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.hide()
        lay.addWidget(self.log, 4)
        lay.addStretch(1)
        row = QHBoxLayout()
        self.details_btn = button("Show details", slot=self.toggle_log)
        row.addWidget(self.details_btn)
        row.addStretch(1)
        self.continue_btn = button("Installer is done — continue", "primary", self.win_continue)
        row.addWidget(self.continue_btn)
        self.cancel_btn = button("Cancel install", "danger", self.back)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.started = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def reset(self, installer: Path) -> None:
        self.heading.setText(f"Installing {core.guess_name(installer)}")
        self.source.setText(str(installer))
        self.steps.set_step(0)
        self.status.setText("Getting ready…")
        self.log.clear()
        self.continue_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.started = time.monotonic()
        self._tick()
        self.timer.start(1000)

    def _tick(self) -> None:
        s = int(time.monotonic() - self.started)
        self.elapsed.setText(f"{s // 60}:{s % 60:02d} elapsed")

    def on_status(self, text: str, stage: str) -> None:
        self.status.setText(text)
        self.steps.set_step(self.STEP_OF.get(stage, self.steps.current))
        self.continue_btn.setVisible(stage == "wait")
        if stage == "wait":
            self.continue_btn.setFocus()

    def stop(self) -> None:
        self.timer.stop()

    def toggle_log(self) -> None:
        show = not self.log.isVisible()
        self.log.setVisible(show)
        self.details_btn.setText("Hide details" if show else "Show details")

    def win_continue(self) -> None:
        self.continue_btn.hide()
        self.win.continue_install()

    def enter(self) -> None:
        self.details_btn.setFocus()

    def hints(self):
        return [("A", "Select", self.win.nav_activate), ("B", "Cancel", self.back)]

    def back(self) -> None:
        self.win.cancel_install()


class PickPage(Page):
    title = "Choose the program"

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 26, 48, 22)
        lay.setSpacing(14)
        self.heading = label("Which one is the program?", "h1")
        lay.addWidget(self.heading)
        self.hint = label("", "dim")
        lay.addWidget(self.hint)
        self.list = QListWidget()
        self.list.setIconSize(self.list.iconSize() * 2)
        self.list.itemActivated.connect(lambda _i: self.use())
        lay.addWidget(self.list, 10)
        row = QHBoxLayout()
        row.addWidget(label("Name in Steam", wrap=False))
        self.name = QLineEdit()
        row.addWidget(self.name, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        btns = QHBoxLayout()
        self.portable = button("No install needed — add this file itself", slot=lambda: self.win.use_portable())
        btns.addWidget(self.portable)
        btns.addWidget(button("Browse…", slot=lambda: self.win.browse_program_for_pending()))
        btns.addStretch(1)
        btns.addWidget(button("Cancel", "danger", self.back))
        self.use_btn = button("Add to Steam", "primary", self.use)
        btns.addWidget(self.use_btn)
        lay.addLayout(btns)

    def load(self, pending: core.PendingInstall) -> None:
        cands = pending.candidates
        self.list.clear()
        drive_c = pending.pfx / "drive_c"
        for c in cands[:12]:
            try:
                where = str(c.exe.parent.relative_to(drive_c))
            except ValueError:
                where = str(c.exe.parent)
            icon = artwork.load_exe_icon(c.exe)
            it = QListWidgetItem(f"{c.exe.name}\n{where}")
            if icon is not None:
                it.setIcon(QIcon(QPixmap.fromImage(icon)))
            it.setData(Qt.ItemDataRole.UserRole, str(c.exe))
            self.list.addItem(it)
        has = bool(cands)
        self.heading.setText("Which one is the program?" if has else "Nothing was installed")
        self.hint.setText("The installer finished. Pick the program to add to Steam." if has else
                          "No new program files were found. If this file is the program itself (no setup "
                          "needed), add it as it is. Otherwise the installer may have been closed early.")
        self.list.setVisible(has)
        self.use_btn.setVisible(has)
        self.portable.setVisible(pending.installer.suffix.lower() == ".exe")
        self.portable.setObjectName("" if has else "primary")
        self.portable.style().polish(self.portable)
        self.name.setText(pending.name)
        if has:
            self.list.setCurrentRow(0)

    def enter(self) -> None:
        (self.list if self.list.isVisible() else self.portable).setFocus()

    def use(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.win.finish_install(Path(item.data(Qt.ItemDataRole.UserRole)), self.name.text())

    def back(self) -> None:
        self.win.discard_pending()


class DonePage(Page):
    title = "Installed"

    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 30, 48, 26)
        lay.setSpacing(14)
        lay.addStretch(1)
        self.art = QLabel()
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.art)
        self.heading = label("", "ok")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.heading)
        self.text = label("", "dim")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.text)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.delete_btn = button("", slot=self.delete_installer)
        row.addWidget(self.delete_btn)
        self.done_btn = button("Done", "primary", self.back)
        self.done_btn.setMinimumWidth(200)
        row.addWidget(self.done_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.app: core.App | None = None

    def load(self, app: core.App) -> None:
        self.app = app
        icon = artwork.load_icon(app.icon)
        self.art.setPixmap(pixmap(artwork.render("", app.name, icon), 460, 215))
        if app.steam_appid:
            self.heading.setText(f"✓  {app.name} is in your Steam library")
            msg = "Restart Steam to see it  (STEAM button → Power → Restart Steam)." \
                if core.steam_is_running() else "It'll be there next time you open Steam."
        else:
            self.heading.setText(f"✓  {app.name} is installed")
            msg = "No Steam account was found on this Deck, so it couldn't be added to Steam."
        self.text.setText(f"{msg}\nSteam will launch: {Path(app.exe).name}")
        self.refresh_delete()

    def installer_files(self) -> list[Path]:
        if not self.app or not self.app.installer:
            return []
        return [f for f in core.installer_files(Path(self.app.installer)) if f.exists()]

    def refresh_delete(self) -> None:
        files = self.installer_files()
        self.delete_btn.setVisible(bool(files))
        if files:
            self.delete_btn.setText(f"Delete installer  ({core.human_size(core.files_size(files))})")

    def delete_installer(self) -> None:
        files = self.installer_files()
        if not files or not self.app:
            return
        names = "\n".join(f"• {f.name}" for f in files[:6]) + ("\n…" if len(files) > 6 else "")
        if Sheet.ask(self, "Delete the installer?", f"{self.app.name} stays installed. This deletes:\n{names}",
                     ("Delete", "Keep"), primary=1, danger=(0,)) != 0:
            return
        freed = core.delete_files(files)
        self.win.flash(f"Freed {core.human_size(freed)}")
        self.win.refresh_space()
        self.refresh_delete()
        self.done_btn.setFocus()

    def enter(self) -> None:
        self.done_btn.setFocus()

    def hints(self):
        return [("A", "Select", self.win.nav_activate), ("B", "Done", self.back)]


# ── Window ───────────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self, paths: core.Paths | None = None, use_nav: bool = True):
        super().__init__()
        self.setObjectName("main")
        self.paths = paths or core.Paths.default()
        self.library = core.Library(self.paths)  # bookkeeping only (ids, launch scripts, cleanup)
        self.installer_dirs: list[Path] | None = None  # None = Downloads, Desktop, SD/USB
        self.thread: InstallThread | None = None
        self.job: core.Installer | None = None
        self.pending: core.PendingInstall | None = None
        self.current_installer: Path | None = None

        self.setWindowTitle("ProtonLaunch")
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._top_bar())
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self.hint_bar = HintBar()
        v.addWidget(self.hint_bar)
        self.toast = Toast(root)

        self.home = HomePage(self)
        self.browser = BrowserPage(self)
        self.progress = InstallPage(self)
        self.pick = PickPage(self)
        self.done = DonePage(self)
        for p in (self.home, self.browser, self.progress, self.pick, self.done):
            self.stack.addWidget(p)

        self.nav = Nav(QApplication.instance(), self.on_action, busy=lambda: self.thread is not None) \
            if use_nav else None
        QApplication.instance().focusChanged.connect(lambda *_: self.update_hints())
        self.refresh_launchers()
        self.go(self.home)

    # chrome
    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(64)
        bar.setStyleSheet(f"QFrame#topbar {{ background: {theme.BG_RAISED}; border-bottom: 1px solid {theme.LINE}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(28, 0, 20, 0)
        h.setSpacing(14)
        h.addWidget(label("⚡ ProtonLaunch", "h2", wrap=False))
        self.crumb = label("", "muted", wrap=False)
        h.addWidget(self.crumb)
        h.addStretch(1)
        self.space = label("", "chip", wrap=False)
        h.addWidget(self.space, 0, Qt.AlignmentFlag.AlignVCenter)
        menu = button("☰", "flat", self.open_menu)
        menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu.setToolTip("Menu")
        h.addWidget(menu)
        return bar

    def update_hints(self) -> None:
        page = self.stack.currentWidget()
        if isinstance(page, Page):
            note = "STEAM + X opens the keyboard" if core.in_game_mode() and \
                isinstance(QApplication.focusWidget(), QLineEdit) else ""
            self.hint_bar.set_hints(page.hints(), note)

    def refresh_space(self) -> None:
        self.space.setText(f"{core.human_size(core.free_space(self.paths.root))} free")

    def go(self, page: Page) -> None:
        self.stack.setCurrentWidget(page)
        self.crumb.setText(f"›  {page.title}" if page.title else "")
        self.refresh_space()
        page.enter()
        self.update_hints()

    def go_home(self) -> None:
        self.go(self.home)

    def nav_activate(self) -> None:
        if self.nav:
            self.nav.activate()

    def on_action(self, action: str) -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, Sheet):
            if action == "b":
                modal.reject()
            return
        page = self.stack.currentWidget()
        if not isinstance(page, Page):
            return
        if action == "b":
            page.back()
        elif action == "x":
            page.x()
        elif action in ("start", "select"):
            self.open_menu()
        elif action in ("lb", "rb"):
            area = page.scroll_area()
            if area:
                sb = area.verticalScrollBar()
                sb.setValue(sb.value() + (-1 if action == "lb" else 1) * area.viewport().height() * 3 // 4)

    def flash(self, text: str) -> None:
        self.toast.show_message(text)

    # ── install flow ─────────────────────────────────────────────────────

    def browse_installers(self) -> None:
        home = Path.home()
        places = [("Downloads", home / "Downloads"), ("Desktop", home / "Desktop"), ("Home", home)]
        places += [(p.name, p) for p in core.removable_media()]
        self.browser.open("Choose an installer", places, core.INSTALLER_SUFFIXES, self.confirm_install,
                          self.go_home)
        self.go(self.browser)

    def confirm_install(self, installer: Path) -> None:
        name = core.guess_name(installer)
        size = core.human_size(core.files_size(core.installer_files(installer)))
        free = core.human_size(core.free_space(self.paths.root))
        choice = Sheet.ask(self, f"Install {name}?",
                           f"{installer}\n\nInstaller: {size}   ·   Free space: {free}\n\n"
                           "The installer opens next — click through it as usual. ProtonLaunch then finds the "
                           "program and adds it to Steam.", ("Install", "Cancel"))
        if choice == 0:
            self.start_install(installer)

    def start_install(self, installer: Path, allow_no_container: bool = False) -> None:
        if self.thread is not None:
            return
        installer = Path(installer)
        self.current_installer = installer
        self.progress.reset(installer)
        self.go(self.progress)
        t = InstallThread(installer, self.paths, allow_no_container)
        t.status.connect(lambda text: self.progress.on_status(text, t.job.stage))
        t.log.connect(self.progress.log.appendPlainText)
        t.done.connect(self.on_installed)
        t.failed.connect(self.on_failed)
        t.cancelled.connect(self.on_cancelled)
        t.finished.connect(self._thread_finished)
        self.thread, self.job = t, t.job
        t.start()

    def _thread_finished(self) -> None:
        if self.job:
            # The thread's signals die with it; route later updates straight to the UI.
            job = self.job
            job.status = lambda text: self.progress.on_status(text, job.stage)
            job._log_cb = self.progress.log.appendPlainText
        if self.thread:
            self.thread.deleteLater()
        self.thread = None

    def continue_install(self) -> None:
        if self.thread:
            self.thread.job.continue_now()

    def cancel_install(self) -> None:
        if not self.thread:
            return
        if Sheet.ask(self, "Cancel the install?", "The installer is closed and everything it installed so far "
                     "is removed.", ("Keep installing", "Cancel install"), danger=(1,)) == 1 and self.thread:
            self.progress.cancel_btn.setEnabled(False)
            self.progress.status.setText("Cancelling…")
            self.thread.job.cancel()

    def on_cancelled(self) -> None:
        self.progress.stop()
        self.go_home()
        self.flash("Install cancelled")

    def on_failed(self, message: str) -> None:
        self.progress.stop()
        self.go_home()
        if message == "NO_RUNTIME":
            if Sheet.ask(self, "Proton is needed", "ProtonLaunch uses Proton to run Windows installers. Steam "
                         "can download it for you — try again when it's done.", ("Install Proton", "Close")) == 0:
                QDesktopServices.openUrl(QUrl(f"steam://install/{core.PROTON_EXPERIMENTAL_APPID}"))
            return
        if message.startswith("NO_CONTAINER:"):
            appid = message.split(":", 1)[1]
            choice = Sheet.ask(self, "One more Steam download needed",
                               "Proton runs inside the Steam Linux Runtime, which isn't installed yet. Without "
                               "it, installers often can't download anything.\n\nSteam can install it (a few "
                               "hundred MB). Run the install again when it's done.",
                               ("Install it", "Continue without it", "Cancel"))
            if choice == 0:
                QDesktopServices.openUrl(QUrl(f"steam://install/{appid}"))
            elif choice == 1 and self.current_installer:
                self.start_install(self.current_installer, allow_no_container=True)
            return
        head, _, rest = message.partition("\n\n")
        Sheet.ask(self, "Install failed", head, ("Close",), detail=rest)

    def on_installed(self, pending: core.PendingInstall) -> None:
        self.pending = pending
        cands = pending.candidates
        if core.is_confident(cands, pending.installer):
            self.finish_install(cands[0].exe, core.best_name(pending, cands[0]))
            return
        self.progress.stop()
        self.pick.load(pending)
        self.go(self.pick)

    def use_portable(self) -> None:
        if self.pending:
            self.finish_install(core.adopt_portable(self.pending), self.pick.name.text())

    def browse_program_for_pending(self) -> None:
        if not self.pending:
            return
        drive_c = self.pending.pfx / "drive_c"
        places = [("C: drive", drive_c), ("Home", Path.home())]
        self.browser.open("Choose the program", places, (".exe",),
                          lambda p: self.finish_install(p, self.pick.name.text()), lambda: self.go(self.pick))
        self.go(self.browser)

    def discard_pending(self) -> None:
        if self.pending:
            if self.job:
                self.job.close()
            shutil.rmtree(self.pending.compat_dir, ignore_errors=True)
            self.pending = None
        self.go_home()

    def finish_install(self, exe: Path, name: str) -> None:
        pending, self.pending = self.pending, None
        if pending is None or self.job is None:
            return
        self.progress.stop()
        icon_img = artwork.load_exe_icon(exe)
        icon_path = artwork.save_icon(icon_img, self.paths.icons / f"{pending.id}.png") if icon_img else ""
        try:
            app = self.job.finish(pending, exe, name, icon=icon_path)
        except Exception as e:  # noqa: BLE001
            Sheet.ask(self, "Couldn't finish", str(e), ("Close",))
            self.go_home()
            return
        app.artwork = artwork.write_steam_artwork(app.steam_appid, app.name, icon_img, core.steam_grid_dirs())
        self.library.upsert(app)
        self.done.load(app)
        self.go(self.done)

    def refresh_launchers(self) -> None:
        """Rewrite launch scripts so programs installed by older versions get current fixes."""
        roots = core.steam_roots()
        for app in self.library.load():
            if app.launcher and Path(app.prefix).is_dir():
                try:
                    core.write_launcher(app, self.paths, roots[0] if roots else None, roots)
                except OSError:
                    pass

    # ── menu ─────────────────────────────────────────────────────────────

    def open_menu(self) -> None:
        if QApplication.activeModalWidget() is not None:
            return
        options = ("Add ProtonLaunch to Steam", "Look for installers again", "About", "Quit ProtonLaunch", "Close")
        choice = Sheet.ask(self, "Menu", "", options, primary=len(options) - 1)
        if choice == 0:
            self.add_self_to_steam()
        elif choice == 1:
            self.go_home()
            self.flash("Checked Downloads, Desktop and SD cards")
        elif choice == 2:
            Sheet.ask(self, f"ProtonLaunch {__version__}",
                      "Installs Windows programs and games on Steam Deck and adds them to your Steam library.\n\n"
                      f"Installed programs: {self.paths.prefixes}\nInstall logs: {self.paths.logs}", ("Close",))
        elif choice == 3:
            self.close()

    def add_self_to_steam(self) -> None:
        exe = Path(sys.executable if getattr(sys, "frozen", False) else Path.home() / ".local/bin/protonlaunch")
        if not exe.exists():
            Sheet.ask(self, "Add to Steam", "Install ProtonLaunch with get.sh first.", ("Close",))
            return
        appid, users = core.add_steam_shortcut("ProtonLaunch", str(exe), str(exe.parent))
        if users:
            artwork.write_steam_artwork(appid, "ProtonLaunch", None, core.steam_grid_dirs())
        Sheet.ask(self, "Add to Steam", "Added! Restart Steam to find ProtonLaunch in your library." if users
                  else "No Steam account found on this device.", ("Close",))

    # ── drag & drop, closing ─────────────────────────────────────────────

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
            self.confirm_install(p)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.thread is not None:
            if Sheet.ask(self, "Quit?", "An install is running. Cancel it and quit?", ("Keep installing", "Quit"),
                         danger=(1,)) != 1:
                event.ignore()
                return
            self.thread.job.cancel()
            self.thread.wait(15000)
        if self.nav:
            self.nav.stop()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    if "--version" in args:
        print(f"ProtonLaunch {__version__}")
        return 0
    if "-h" in args or "--help" in args:
        print("usage: protonlaunch [INSTALLER.exe|.msi]\n\n"
              "Opens ProtonLaunch. Given an installer, asks to install it right away.")
        return 0
    app = QApplication(argv[:1])
    app.setApplicationName("ProtonLaunch")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLE)
    win = MainWindow()
    if core.in_game_mode() or os.environ.get("PROTONLAUNCH_FULLSCREEN"):
        win.showFullScreen()
    else:
        win.show()
    files = [a for a in args if not a.startswith("-")]
    if files:
        QTimer.singleShot(0, lambda: win.confirm_install(Path(files[0])))
    return app.exec()

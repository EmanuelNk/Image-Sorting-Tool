import shutil
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QComboBox, QToolBar, QStatusBar, QFileDialog,
    QMessageBox, QDialog, QGridLayout, QFrame, QCheckBox,
    QApplication, QSizePolicy, QStackedWidget, QSlider, QPushButton,
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import (QKeySequence, QShortcut, QAction, QFont,
                          QColor, QPalette)

from metadata import MetadataStore
from image_loader import scan_folder, get_exif, optional_support_info
from image_viewer import ImageViewerWidget
from filmstrip import FilmstripWidget
from sidebar import SidebarWidget
from grid_view import GridViewWidget, THUMB_MIN, THUMB_MAX, THUMB_DEFAULT
from metadata_panel import MetadataPanelWidget


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setModal(True)
        self.setFixedSize(560, 480)
        self.setStyleSheet("background: #1e1e1e; color: #ccc;")

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Keyboard Shortcuts")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #fff; margin-bottom: 12px;")
        layout.addWidget(title)

        shortcuts = [
            ("Navigation", [
                ("← / →",      "Previous / Next image"),
                ("⌘O",         "Open folder"),
                ("⌘Z",         "Undo last move"),
            ]),
            ("Ratings", [
                ("1 – 5",      "Set star rating"),
                ("0",          "Clear rating"),
            ]),
            ("Flags", [
                ("P",          "Toggle Pick flag"),
                ("X",          "Toggle Reject flag"),
                ("U",          "Clear flag (Unflagged)"),
            ]),
            ("Color Labels", [
                ("6",          "Red label"),
                ("7",          "Yellow label"),
                ("8",          "Green label"),
                ("9",          "Blue label"),
                ("`",          "Purple label  (press again to clear)"),
            ]),
            ("Albums", [
                ("M",          "Move selected image(s) to album"),
                ("⌘A",         "Select all images in filmstrip"),
            ]),
            ("View", [
                ("G",          "Toggle grid / detail view"),
                ("I",          "Toggle info / metadata panel"),
                ("double-click","Open image in detail view (from grid)"),
                ("?",          "Show this help"),
                ("⌘F",         "Toggle filmstrip"),
                ("⌘B",         "Toggle sidebar"),
            ]),
        ]

        grid = QGridLayout()
        grid.setVerticalSpacing(3)
        grid.setHorizontalSpacing(20)
        row = 0

        section_font = QFont()
        section_font.setPointSize(9)
        section_font.setBold(True)
        section_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

        key_font = QFont()
        key_font.setFamily("Monaco")
        key_font.setPointSize(10)

        for section, items in shortcuts:
            if row > 0:
                spacer = QLabel(" ")
                spacer.setFixedHeight(6)
                grid.addWidget(spacer, row, 0)
                row += 1
            section_label = QLabel(section.upper())
            section_label.setFont(section_font)
            section_label.setStyleSheet("color: #666;")
            grid.addWidget(section_label, row, 0, 1, 2)
            row += 1
            for key, desc in items:
                k = QLabel(key)
                k.setFont(key_font)
                k.setStyleSheet("color: #aaa; background: #2a2a2a; padding: 2px 6px; border-radius: 3px;")
                k.setFixedWidth(90)
                d = QLabel(desc)
                d.setStyleSheet("color: #ccc;")
                grid.addWidget(k, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(d, row, 1)
                row += 1

        layout.addLayout(grid)
        layout.addStretch()

        close_hint = QLabel("Press any key or click to close")
        close_hint.setStyleSheet("color: #555; font-size: 11px;")
        close_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(close_hint)

    def keyPressEvent(self, event):
        self.accept()

    def mousePressEvent(self, event):
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Photo Sorter")
        self.resize(1440, 900)

        self._folder: Optional[Path] = None
        self._all_images: List[Path] = []
        self._filtered: List[Path] = []
        self._index: int = -1
        self._metadata = MetadataStore()
        self._exif_cache: Dict[str, dict] = {}
        self._move_history: List[Tuple[Path, Path]] = []
        self._grid_dirty = True   # grid needs reload before first use

        # filter/sort state
        self._filter_rating = 0
        self._filter_flag = "all"
        self._filter_label = "all"
        self._sort_by = "filename"
        self._sort_asc = True

        self._settings = QSettings("PhotoSorter", "PhotoSorter")

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_shortcuts()

        albums_raw = self._settings.value("albums", [])
        if isinstance(albums_raw, str):
            albums_raw = [albums_raw]
        self._sidebar.set_albums([Path(a) for a in albums_raw])

        last = self._settings.value("last_folder", "")
        if last and Path(last).is_dir():
            QTimer.singleShot(0, lambda: self._open_folder(Path(last)))

    # ──────────────────────────── UI setup ───────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #333; }")

        self._sidebar = SidebarWidget()
        self._sidebar.move_requested.connect(self._move_to_album)
        self._sidebar.album_added.connect(self._save_albums)
        self._sidebar.album_removed.connect(self._save_albums)
        splitter.addWidget(self._sidebar)

        # Right area: stacked (detail | grid)
        self._stack = QStackedWidget()

        # Stack index 0 — detail view: large viewer + filmstrip (with meta panel on right)
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(0)

        # Horizontal splitter: viewer (left) | meta panel (right)
        self._detail_hsplit = QSplitter(Qt.Orientation.Horizontal)
        self._detail_hsplit.setHandleWidth(2)
        self._detail_hsplit.setStyleSheet("QSplitter::handle { background: #2a2a2a; }")

        self._viewer = ImageViewerWidget()
        self._detail_hsplit.addWidget(self._viewer)

        self._meta_panel = MetadataPanelWidget()
        self._detail_hsplit.addWidget(self._meta_panel)

        self._detail_hsplit.setStretchFactor(0, 1)
        self._detail_hsplit.setStretchFactor(1, 0)
        self._detail_hsplit.setSizes([9999, 260])

        detail_layout.addWidget(self._detail_hsplit, 1)

        self._filmstrip = FilmstripWidget()
        self._filmstrip.image_selected.connect(self._on_filmstrip_select)
        self._filmstrip.selection_changed.connect(self._update_status)
        detail_layout.addWidget(self._filmstrip)

        self._stack.addWidget(detail_widget)  # index 0

        # Stack index 1 — grid view
        self._grid = GridViewWidget()
        self._grid.image_selected.connect(self._on_grid_select)
        self._grid.selection_changed.connect(self._update_status)
        self._grid.open_detail.connect(self._on_open_detail)
        self._stack.addWidget(self._grid)     # index 1

        splitter.addWidget(self._stack)
        splitter.setSizes([190, 1250])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter

        root.addWidget(splitter, 1)

        # Status bar
        sb = QStatusBar()
        sb.setStyleSheet("QStatusBar { background: #1a1a1a; color: #999; font-size: 11px; border-top: 1px solid #333; } QStatusBar::item { border: none; }")
        self.setStatusBar(sb)
        self._status_left = QLabel()
        self._status_right = QLabel()
        self._status_right.setAlignment(Qt.AlignmentFlag.AlignRight)
        sb.addWidget(self._status_left, 1)
        sb.addPermanentWidget(self._status_right)
        self._update_status()

    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet("QMenuBar { background: #1e1e1e; color: #ccc; } QMenuBar::item:selected { background: #333; } QMenu { background: #252525; color: #ccc; border: 1px solid #444; } QMenu::item:selected { background: #2a4060; }")

        file_menu = mb.addMenu("File")
        open_act = QAction("Open Folder…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._prompt_open_folder)
        file_menu.addAction(open_act)
        file_menu.addSeparator()
        undo_act = QAction("Undo Move", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self._undo_move)
        file_menu.addAction(undo_act)

        view_menu = mb.addMenu("View")
        toggle_film = QAction("Toggle Filmstrip", self)
        toggle_film.setShortcut("Ctrl+F")
        toggle_film.triggered.connect(self._toggle_filmstrip)
        view_menu.addAction(toggle_film)
        toggle_side = QAction("Toggle Sidebar", self)
        toggle_side.setShortcut("Ctrl+B")
        toggle_side.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(toggle_side)

        help_menu = mb.addMenu("Help")
        shortcuts_act = QAction("Keyboard Shortcuts", self)
        shortcuts_act.setShortcut("?")
        shortcuts_act.triggered.connect(self._show_help)
        help_menu.addAction(shortcuts_act)
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _build_toolbar(self):
        tb = QToolBar("Filter & Sort")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setStyleSheet("""
            QToolBar { background: #1e1e1e; border-bottom: 1px solid #333; padding: 4px 8px; spacing: 6px; }
            QLabel { color: #999; font-size: 11px; }
            QComboBox {
                background: #2a2a2a; color: #ccc; border: 1px solid #444;
                border-radius: 3px; padding: 2px 6px; font-size: 11px; min-width: 90px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #252525; color: #ccc; border: 1px solid #555;
                selection-background-color: #2a4060;
            }
            QCheckBox { color: #aaa; font-size: 11px; }
        """)
        self.addToolBar(tb)

        tb.addWidget(QLabel(" Rating:"))
        self._rating_combo = QComboBox()
        self._rating_combo.addItems(["All", "≥ 1 ★", "≥ 2 ★", "≥ 3 ★", "≥ 4 ★", "5 ★"])
        self._rating_combo.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self._rating_combo)

        tb.addWidget(QLabel("  Flag:"))
        self._flag_combo = QComboBox()
        self._flag_combo.addItems(["All", "Pick", "Reject", "Unflagged"])
        self._flag_combo.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self._flag_combo)

        tb.addWidget(QLabel("  Label:"))
        self._label_combo = QComboBox()
        self._label_combo.addItems(["All", "Red", "Yellow", "Green", "Blue", "Purple"])
        self._label_combo.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self._label_combo)

        spacer = QWidget()
        spacer.setMinimumWidth(20)
        tb.addWidget(spacer)

        tb.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Filename", "Date Taken", "Rating"])
        self._sort_combo.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self._sort_combo)

        self._sort_dir_combo = QComboBox()
        self._sort_dir_combo.addItems(["A → Z", "Z → A"])
        self._sort_dir_combo.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self._sort_dir_combo)

        tb.addSeparator()

        # Grid size slider (always visible; only affects grid view)
        self._size_label = QLabel("  Size:")
        tb.addWidget(self._size_label)
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(THUMB_MIN, THUMB_MAX)
        self._size_slider.setValue(THUMB_DEFAULT)
        self._size_slider.setFixedWidth(110)
        self._size_slider.setToolTip("Grid thumbnail size")
        self._size_slider.valueChanged.connect(self._on_grid_size_change)
        self._size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333; height: 4px; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #888; width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
            }
            QSlider::handle:horizontal:hover { background: #aaa; }
            QSlider::sub-page:horizontal { background: #4a80c0; border-radius: 2px; }
        """)
        tb.addWidget(self._size_slider)

        tb.addSeparator()

        # View toggle button
        self._view_btn = QPushButton("⊞  Grid")
        self._view_btn.setToolTip("Switch to grid view  (G)")
        self._view_btn.setCheckable(True)
        self._view_btn.setStyleSheet("""
            QPushButton {
                background: #2e2e2e; color: #ccc; border: 1px solid #555;
                border-radius: 3px; padding: 3px 10px; font-size: 11px;
            }
            QPushButton:checked {
                background: #1a4080; color: #fff; border-color: #2060b0;
            }
            QPushButton:hover:!checked { background: #3a3a3a; }
        """)
        self._view_btn.clicked.connect(self._toggle_view)
        tb.addWidget(self._view_btn)

        right_spacer = QWidget()
        right_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(right_spacer)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #666; font-size: 11px;")
        tb.addWidget(self._count_label)

    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.ShortcutContext.WindowShortcut)
            s.activated.connect(fn)
            return s

        # Store these so we can disable them in grid view (grid handles its own arrow nav)
        self._sc_right = sc("Right", self._next_detail_only)
        self._sc_left  = sc("Left",  self._prev_detail_only)
        sc("1", lambda: self._toggle_rating(1))
        sc("2", lambda: self._toggle_rating(2))
        sc("3", lambda: self._toggle_rating(3))
        sc("4", lambda: self._toggle_rating(4))
        sc("5", lambda: self._toggle_rating(5))
        sc("0",         self._clear_rating)
        sc("p",         self._toggle_pick)
        sc("x",         self._toggle_reject)
        sc("u",         self._clear_flag)
        sc("6", lambda: self._toggle_label("red"))
        sc("7", lambda: self._toggle_label("yellow"))
        sc("8", lambda: self._toggle_label("green"))
        sc("9", lambda: self._toggle_label("blue"))
        sc("`", lambda: self._toggle_label("purple"))
        sc("m",         self._move_shortcut)
        sc("Ctrl+A",    self._select_all)
        sc("g",         self._toggle_view)
        sc("i",         self._toggle_info_panel)
        sc("?",         self._show_help)
        sc("Ctrl+Z",    self._undo_move)
        sc("Ctrl+F",    self._toggle_filmstrip)
        sc("Ctrl+B",    self._toggle_sidebar)

    # ──────────────────────────── folder / navigation ────────────────────────

    def _prompt_open_folder(self):
        start = str(self._folder) if self._folder else ""
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", start)
        if folder:
            self._open_folder(Path(folder))

    def _open_folder(self, path: Path):
        self._folder = path
        self._all_images = scan_folder(path)
        self._metadata.load_folder(path)
        self._exif_cache.clear()
        self._move_history.clear()
        self.setWindowTitle(f"Photo Sorter — {path.name}")
        self._settings.setValue("last_folder", str(path))
        self._apply_filters()
        if self._filtered:
            self._go_to(0)
        else:
            self._index = -1
            self._viewer.clear()
            self._update_status()
            self._update_count_label()

    def _apply_filters(self):
        images = list(self._all_images)

        if self._filter_rating > 0:
            images = [p for p in images if self._metadata.get_rating(p.name) >= self._filter_rating]
        if self._filter_flag != "all":
            images = [p for p in images if self._metadata.get_flag(p.name) == self._filter_flag]
        if self._filter_label != "all":
            images = [p for p in images if self._metadata.get_color_label(p.name) == self._filter_label]

        sort_key = self._sort_by
        rev = not self._sort_asc

        if sort_key == "filename":
            images.sort(key=lambda p: p.name.lower(), reverse=rev)
        elif sort_key == "rating":
            images.sort(key=lambda p: self._metadata.get_rating(p.name), reverse=not rev)
        elif sort_key == "date":
            images.sort(key=self._date_sort_key, reverse=rev)

        self._filtered = images
        self._filmstrip.load_images(images, self._metadata)
        self._grid_dirty = True
        if self._stack.currentIndex() == 1:
            self._grid.load_images(images, self._metadata)
            self._grid_dirty = False
        self._update_count_label()

    def _date_sort_key(self, path: Path) -> str:
        name = path.name
        if name not in self._exif_cache:
            self._exif_cache[name] = get_exif(path)
        date = self._exif_cache[name].get("date_taken", "")
        return date or str(path.stat().st_mtime)

    def _go_to(self, index: int):
        if not self._filtered:
            return
        index = max(0, min(len(self._filtered) - 1, index))
        self._index = index
        path = self._filtered[index]
        self._viewer.load_image(path)
        meta = self._metadata.get(path.name)
        self._viewer.set_metadata(meta.get("rating", 0), meta.get("color_label"), meta.get("flag", "unflagged"))
        self._filmstrip.select_row(index)
        if self._stack.currentIndex() == 1:
            self._grid.select_row(index)
        if self._meta_panel.isVisible():
            self._meta_panel.load(path, meta)
        self._update_status()

    def next_image(self):
        if self._index < len(self._filtered) - 1:
            self._go_to(self._index + 1)

    def prev_image(self):
        if self._index > 0:
            self._go_to(self._index - 1)

    def _next_detail_only(self):
        if self._stack.currentIndex() == 0:   # only in detail view
            self.next_image()

    def _prev_detail_only(self):
        if self._stack.currentIndex() == 0:
            self.prev_image()

    # ──────────────────────────── metadata actions ───────────────────────────

    @property
    def _current_path(self) -> Optional[Path]:
        if 0 <= self._index < len(self._filtered):
            return self._filtered[self._index]
        return None

    def _refresh_current(self):
        p = self._current_path
        if not p:
            return
        meta = self._metadata.get(p.name)
        self._viewer.set_metadata(meta.get("rating", 0), meta.get("color_label"), meta.get("flag", "unflagged"))
        self._filmstrip.update_item_metadata(p, self._metadata)
        self._grid.update_item_metadata(p, self._metadata)
        if self._meta_panel.isVisible():
            self._meta_panel.update_labels(meta)
        self._update_status()

    def _toggle_rating(self, n: int):
        p = self._current_path
        if not p:
            return
        cur = self._metadata.get_rating(p.name)
        self._metadata.set_rating(p.name, 0 if cur == n else n)
        self._refresh_current()

    def _clear_rating(self):
        p = self._current_path
        if p:
            self._metadata.set_rating(p.name, 0)
            self._refresh_current()

    def _toggle_pick(self):
        p = self._current_path
        if not p:
            return
        cur = self._metadata.get_flag(p.name)
        self._metadata.set_flag(p.name, "unflagged" if cur == "pick" else "pick")
        self._refresh_current()

    def _toggle_reject(self):
        p = self._current_path
        if not p:
            return
        cur = self._metadata.get_flag(p.name)
        self._metadata.set_flag(p.name, "unflagged" if cur == "reject" else "reject")
        self._refresh_current()

    def _clear_flag(self):
        p = self._current_path
        if p:
            self._metadata.set_flag(p.name, "unflagged")
            self._refresh_current()

    def _toggle_label(self, color: str):
        p = self._current_path
        if not p:
            return
        cur = self._metadata.get_color_label(p.name)
        self._metadata.set_color_label(p.name, None if cur == color else color)
        self._refresh_current()

    # ──────────────────────────── move ───────────────────────────────────────

    def _move_shortcut(self):
        album = self._sidebar.selected_album()
        if album:
            self._move_to_album(album)

    def _move_to_album(self, dest: Path):
        active = self._grid if self._stack.currentIndex() == 1 else self._filmstrip
        selected = active.selected_paths()
        if not selected:
            p = self._current_path
            if not p:
                QMessageBox.information(self, "No image", "No image is selected.")
                return
            selected = [p]

        count = len(selected)
        if count == 1:
            msg = f"Move <b>{selected[0].name}</b> to:<br><code>{dest}</code>"
        else:
            msg = f"Move <b>{count} images</b> to:<br><code>{dest}</code>"

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Move Images" if count > 1 else "Move Image")
        dlg.setText(msg)
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        dlg.setDefaultButton(QMessageBox.StandardButton.Yes)
        dlg.setStyleSheet("QMessageBox { background: #252525; color: #ccc; } QLabel { color: #ccc; }")
        if dlg.exec() != QMessageBox.StandardButton.Yes:
            return

        dest_meta = MetadataStore()
        dest_meta.load_folder(dest)
        failed = []
        moved = []

        for p in selected:
            target = dest / p.name
            if target.exists():
                failed.append(f"{p.name} (already exists in destination)")
                continue
            try:
                shutil.move(str(p), str(target))
            except OSError as e:
                failed.append(f"{p.name} ({e})")
                continue

            meta = self._metadata.get(p.name)
            dest_meta.import_entry(p.name, meta)
            self._metadata.remove(p.name)
            self._move_history.append((p, target))
            moved.append(p)

        if failed:
            QMessageBox.warning(self, "Some moves failed", "\n".join(failed))

        if not moved:
            return

        moved_set = set(moved)
        self._all_images = [i for i in self._all_images if i not in moved_set]
        old_index = self._index
        self._apply_filters()
        new_index = min(old_index, len(self._filtered) - 1)
        if new_index >= 0:
            self._go_to(new_index)
        else:
            self._index = -1
            self._viewer.clear()
            self._update_status()

    def _undo_move(self):
        if not self._move_history:
            self._status_left.setText("Nothing to undo.")
            return
        src, dst = self._move_history.pop()
        if not dst.exists():
            self._status_left.setText(f"File no longer at {dst} — cannot undo.")
            return
        try:
            shutil.move(str(dst), str(src))
        except OSError as e:
            QMessageBox.critical(self, "Undo failed", str(e))
            return
        self._all_images.append(src)
        self._apply_filters()
        # Try to re-select the restored image
        try:
            idx = self._filtered.index(src)
            self._go_to(idx)
        except ValueError:
            pass

    # ──────────────────────────── filter / sort ──────────────────────────────

    def _on_filter_change(self):
        self._filter_rating = self._rating_combo.currentIndex()
        flag_map = {0: "all", 1: "pick", 2: "reject", 3: "unflagged"}
        self._filter_flag = flag_map.get(self._flag_combo.currentIndex(), "all")
        label_map = {0: "all", 1: "red", 2: "yellow", 3: "green", 4: "blue", 5: "purple"}
        self._filter_label = label_map.get(self._label_combo.currentIndex(), "all")
        sort_map = {0: "filename", 1: "date", 2: "rating"}
        self._sort_by = sort_map.get(self._sort_combo.currentIndex(), "filename")
        self._sort_asc = self._sort_dir_combo.currentIndex() == 0

        if self._folder:
            cur_path = self._current_path
            self._apply_filters()
            # Try to keep current image selected
            if cur_path and cur_path in self._filtered:
                self._go_to(self._filtered.index(cur_path))
            elif self._filtered:
                self._go_to(0)
            else:
                self._index = -1
                self._viewer.clear()
                self._update_status()

    def _on_filmstrip_select(self, row: int):
        if row != self._index:
            self._go_to(row)

    def _select_all(self):
        active = self._grid if self._stack.currentIndex() == 1 else self._filmstrip
        active.select_all_items()

    # ──────────────────────────── status bar ─────────────────────────────────

    def _update_status(self, _sel_count=None):
        p = self._current_path
        if not p:
            self._status_left.setText("No folder open — ⌘O to open")
            self._status_right.setText("")
            return

        active = self._grid if self._stack.currentIndex() == 1 else self._filmstrip
        sel_count = len(active.selectedItems()) if self._filtered else 1
        name = p.name
        meta = self._metadata.get(name)
        rating = meta.get("rating", 0)
        label = meta.get("color_label") or ""
        flag = meta.get("flag", "unflagged")

        stars = "★" * rating + "☆" * (5 - rating) if rating else "☆☆☆☆☆"
        flag_str = {"pick": " · PICK", "reject": " · REJECT"}.get(flag, "")
        label_str = f" · {label.capitalize()}" if label else ""
        sel_str = f"   [{sel_count} selected]" if sel_count > 1 else ""

        left = f"{name}   {stars}{flag_str}{label_str}{sel_str}"
        self._status_left.setText(left)

        # EXIF on right
        if name not in self._exif_cache:
            self._exif_cache[name] = get_exif(p)
        exif = self._exif_cache[name]
        parts = []
        if "width" in exif:
            parts.append(f"{exif['width']}×{exif['height']}")
        if "date_taken" in exif:
            parts.append(exif["date_taken"][:10])
        if "fnumber" in exif:
            parts.append(exif["fnumber"])
        if "exposure" in exif:
            parts.append(exif["exposure"])
        if "iso" in exif:
            parts.append(exif["iso"])
        n = self._index + 1
        total = len(self._filtered)
        parts.append(f"{n}/{total}")
        self._status_right.setText("  ·  ".join(parts))

    def _update_count_label(self):
        total = len(self._all_images)
        shown = len(self._filtered)
        if total == shown:
            self._count_label.setText(f"{total} images")
        else:
            self._count_label.setText(f"{shown} / {total} images")

    # ──────────────────────────── view toggles ───────────────────────────────

    def _toggle_info_panel(self):
        visible = not self._meta_panel.isVisible()
        self._meta_panel.setVisible(visible)
        if visible:
            p = self._current_path
            if p:
                self._meta_panel.load(p, self._metadata.get(p.name))

    def _toggle_filmstrip(self):
        self._filmstrip.setVisible(not self._filmstrip.isVisible())

    def _toggle_sidebar(self):
        self._sidebar.setVisible(not self._sidebar.isVisible())

    def _toggle_view(self):
        if self._stack.currentIndex() == 0:
            # Switch to grid
            if self._grid_dirty and self._filtered:
                self._grid.load_images(self._filtered, self._metadata)
                self._grid_dirty = False
            self._stack.setCurrentIndex(1)
            self._view_btn.setChecked(True)
            self._view_btn.setText("⊟  Detail")
            self._view_btn.setToolTip("Switch to detail view  (G)")
            self._grid.setFocus()
            if self._index >= 0:
                self._grid.select_row(self._index)
        else:
            # Switch to detail
            self._stack.setCurrentIndex(0)
            self._view_btn.setChecked(False)
            self._view_btn.setText("⊞  Grid")
            self._view_btn.setToolTip("Switch to grid view  (G)")
        self._update_status()

    def _on_grid_select(self, row: int):
        if row != self._index:
            self._go_to(row)

    def _on_open_detail(self, row: int):
        """Double-click in grid → jump to that image and switch to detail view."""
        self._go_to(row)
        if self._stack.currentIndex() == 1:
            self._toggle_view()

    def _on_grid_size_change(self, size: int):
        self._grid.set_thumb_size(size)

    # ──────────────────────────── dialogs ────────────────────────────────────

    def _show_help(self):
        dlg = HelpDialog(self)
        dlg.exec()

    def _show_about(self):
        QMessageBox.about(self, "About Photo Sorter",
                          "<b>Photo Sorter</b><br>Lightroom-style photo culling tool.<br><br>"
                          f"<small>{optional_support_info()}</small>")

    # ──────────────────────────── persistence ────────────────────────────────

    def _save_albums(self, _=None):
        albums = self._sidebar.get_albums()
        self._settings.setValue("albums", [str(a) for a in albums])

    def closeEvent(self, event):
        self._save_albums()
        super().closeEvent(event)

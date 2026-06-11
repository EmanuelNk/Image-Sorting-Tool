from pathlib import Path
from typing import List, Optional, Dict, Any

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QListWidget, QListWidgetItem, QPushButton,
                              QFileDialog, QFrame, QDialog, QFormLayout,
                              QLineEdit, QComboBox, QDialogButtonBox,
                              QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

_BTN_STYLE = """
    QPushButton {
        background: #2C2C2E;
        color: rgba(235,235,245,0.7);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 6px;
        padding: 3px 6px;
        font-size: 11px;
    }
    QPushButton:hover { background: #3A3A3C; }
    QPushButton:pressed { background: #1C1C1E; }
    QPushButton:disabled { background: #1C1C1E; color: rgba(235,235,245,0.2); border-color: rgba(255,255,255,0.05); }
"""

_MOVE_BTN_STYLE = """
    QPushButton {
        background: #0A84FF;
        color: #ffffff;
        border: none;
        border-radius: 7px;
        padding: 5px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background: #1A94FF; }
    QPushButton:pressed { background: #0060CC; }
    QPushButton:disabled {
        background: #2C2C2E;
        color: rgba(235,235,245,0.2);
        border: 1px solid rgba(255,255,255,0.05);
    }
"""

_COPY_BTN_STYLE = """
    QPushButton {
        background: rgba(10,132,255,0.18);
        color: #0A84FF;
        border: 1px solid rgba(10,132,255,0.35);
        border-radius: 7px;
        padding: 5px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background: rgba(10,132,255,0.28); }
    QPushButton:pressed { background: rgba(10,132,255,0.12); }
    QPushButton:disabled {
        background: #2C2C2E;
        color: rgba(235,235,245,0.2);
        border: 1px solid rgba(255,255,255,0.05);
    }
"""

_OPEN_BTN_STYLE = """
    QPushButton {
        background: #0A84FF;
        color: #ffffff;
        border: none;
        border-radius: 7px;
        padding: 5px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background: #1A94FF; }
    QPushButton:pressed { background: #0060CC; }
    QPushButton:disabled {
        background: #2C2C2E;
        color: rgba(235,235,245,0.2);
        border: 1px solid rgba(255,255,255,0.05);
    }
"""

_ADD_COLL_BTN_STYLE = """
    QPushButton {
        background: rgba(48,209,88,0.15);
        color: #30D158;
        border: 1px solid rgba(48,209,88,0.3);
        border-radius: 6px;
        padding: 4px 6px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background: rgba(48,209,88,0.25); }
    QPushButton:pressed { background: rgba(48,209,88,0.1); }
    QPushButton:disabled { background: #2C2C2E; color: rgba(235,235,245,0.2); border-color: rgba(255,255,255,0.05); }
"""

_LIST_STYLE = """
    QListWidget {
        background: #2C2C2E;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        color: rgba(235,235,245,0.85);
        font-size: 12px;
        outline: none;
    }
    QListWidget::item { padding: 5px 8px; }
    QListWidget::item:selected { background: #0A84FF; color: #ffffff; }
    QListWidget::item:hover:!selected { background: rgba(255,255,255,0.06); }
"""

_SECTION_FONT_SIZE = 9
_AUTO_IDS = {"picks", "rejects", "5stars", "4stars", "3stars", "this_month"}


class SmartCollectionDialog(QDialog):
    """Dialog to create a new smart collection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Smart Collection")
        self.setModal(True)
        self.setFixedWidth(380)
        self.setStyleSheet("QDialog { background: #1C1C1E; color: rgba(235,235,245,0.85); } "
                           "QLabel { color: rgba(235,235,245,0.85); } "
                           "QLineEdit, QComboBox { background: #2C2C2E; color: rgba(235,235,245,0.85); "
                           "border: 1px solid rgba(255,255,255,0.1); border-radius: 7px; padding: 3px 8px; }")
        self.rule: Optional[Dict] = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Collection name…")
        form.addRow("Name:", self._name)

        self._rating = QComboBox()
        self._rating.addItems(["Any", "1+", "2+", "3+", "4+", "5"])
        form.addRow("Min Rating:", self._rating)

        self._flag = QComboBox()
        self._flag.addItems(["Any", "Pick", "Reject", "Unflagged"])
        form.addRow("Flag:", self._flag)

        self._label = QComboBox()
        self._label.addItems(["Any", "Red", "Yellow", "Green", "Blue", "Purple"])
        form.addRow("Label:", self._label)

        self._date = QComboBox()
        self._date.addItems(["Any time", "This Month", "This Year"])
        form.addRow("Date:", self._date)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            return
        rule: Dict = {}
        ri = self._rating.currentIndex()
        if ri > 0:
            rule["rating_min"] = ri  # index 1→1, 2→2, ..., 5→5
        fi = self._flag.currentIndex()
        flag_map = {1: "pick", 2: "reject", 3: "unflagged"}
        if fi in flag_map:
            rule["flag"] = flag_map[fi]
        li = self._label.currentIndex()
        label_map = {1: "red", 2: "yellow", 3: "green", 4: "blue", 5: "purple"}
        if li in label_map:
            rule["label"] = label_map[li]
        di = self._date.currentIndex()
        if di == 1:
            rule["date_filter"] = "this_month"
        elif di == 2:
            rule["date_filter"] = "this_year"

        self._result_name = name
        self._result_rule = rule
        self.accept()

    @property
    def result_name(self) -> str:
        return getattr(self, "_result_name", "")

    @property
    def result_rule(self) -> dict:
        return getattr(self, "_result_rule", {})


class SidebarWidget(QWidget):
    move_requested = pyqtSignal(Path)    # user wants to move current image here
    copy_requested = pyqtSignal(Path)    # user wants to copy current image here
    album_added = pyqtSignal(Path)
    album_removed = pyqtSignal(Path)
    collection_open = pyqtSignal(str)    # cid
    collection_add = pyqtSignal(str)     # cid

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("SidebarWidget { background: #1C1C1E; }")
        self._albums: List[Path] = []
        self._collections: List[Dict[str, Any]] = []
        self._setup_ui()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont()
        f.setPointSize(_SECTION_FONT_SIZE)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        lbl.setFont(f)
        lbl.setStyleSheet("color: rgba(235,235,245,0.4);")
        return lbl

    def _divider(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3A3A3C;")
        return sep

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        # ── Albums section ────────────────────────────────────────────────────
        layout.addWidget(self._section_label("ALBUMS"))

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(_LIST_STYLE)
        layout.addWidget(self._list, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setToolTip("Add target album folder")
        self._add_btn.setStyleSheet(_BTN_STYLE)
        self._add_btn.clicked.connect(self._add_album)
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setToolTip("Remove selected album")
        self._remove_btn.setStyleSheet(_BTN_STYLE)
        self._remove_btn.clicked.connect(self._remove_album)
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._remove_btn)
        layout.addLayout(btn_layout)

        layout.addWidget(self._divider())

        self._move_btn = QPushButton("Move Here  (M)")
        self._move_btn.setToolTip("Move current image to selected album (M)")
        self._move_btn.setEnabled(False)
        self._move_btn.setStyleSheet(_MOVE_BTN_STYLE)
        self._move_btn.clicked.connect(self._request_move)
        layout.addWidget(self._move_btn)

        self._copy_btn = QPushButton("Copy Here")
        self._copy_btn.setToolTip("Copy current image to selected album")
        self._copy_btn.setEnabled(False)
        self._copy_btn.setStyleSheet(_COPY_BTN_STYLE)
        self._copy_btn.clicked.connect(self._request_copy)
        layout.addWidget(self._copy_btn)

        self._list.currentItemChanged.connect(self._on_album_selection_changed)

        # ── Collections section ───────────────────────────────────────────────
        layout.addWidget(self._divider())
        layout.addWidget(self._section_label("COLLECTIONS"))

        self._coll_list = QListWidget()
        self._coll_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._coll_list.setStyleSheet(_LIST_STYLE)
        layout.addWidget(self._coll_list, 1)

        # Collection management buttons
        coll_btn_row = QHBoxLayout()
        coll_btn_row.setSpacing(3)
        self._coll_add_reg_btn = QPushButton("+ Regular")
        self._coll_add_reg_btn.setToolTip("Create a new regular collection")
        self._coll_add_reg_btn.setStyleSheet(_BTN_STYLE)
        self._coll_add_reg_btn.clicked.connect(self._add_regular_collection)
        self._coll_add_smart_btn = QPushButton("+ Smart")
        self._coll_add_smart_btn.setToolTip("Create a new smart collection")
        self._coll_add_smart_btn.setStyleSheet(_BTN_STYLE)
        self._coll_add_smart_btn.clicked.connect(self._add_smart_collection)
        self._coll_remove_btn = QPushButton("Remove")
        self._coll_remove_btn.setToolTip("Remove selected collection")
        self._coll_remove_btn.setStyleSheet(_BTN_STYLE)
        self._coll_remove_btn.setEnabled(False)
        self._coll_remove_btn.clicked.connect(self._remove_collection)
        coll_btn_row.addWidget(self._coll_add_reg_btn)
        coll_btn_row.addWidget(self._coll_add_smart_btn)
        coll_btn_row.addWidget(self._coll_remove_btn)
        layout.addLayout(coll_btn_row)

        layout.addWidget(self._divider())

        self._open_coll_btn = QPushButton("Open Collection")
        self._open_coll_btn.setToolTip("View images in selected collection")
        self._open_coll_btn.setEnabled(False)
        self._open_coll_btn.setStyleSheet(_OPEN_BTN_STYLE)
        self._open_coll_btn.clicked.connect(self._open_collection)
        layout.addWidget(self._open_coll_btn)

        self._add_to_coll_btn = QPushButton("Add Selected  (C)")
        self._add_to_coll_btn.setToolTip(
            "Add selected images to this collection (C)")
        self._add_to_coll_btn.setEnabled(False)
        self._add_to_coll_btn.setStyleSheet(_ADD_COLL_BTN_STYLE)
        self._add_to_coll_btn.clicked.connect(self._add_to_collection)
        layout.addWidget(self._add_to_coll_btn)

        self._coll_list.currentItemChanged.connect(self._on_coll_selection_changed)

    # ── albums ────────────────────────────────────────────────────────────────

    def _add_album(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Album Folder")
        if folder:
            path = Path(folder)
            if path not in self._albums:
                self._albums.append(path)
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                self._list.addItem(item)
                self.album_added.emit(path)

    def _remove_album(self):
        row = self._list.currentRow()
        if row < 0:
            return
        item = self._list.takeItem(row)
        path = item.data(Qt.ItemDataRole.UserRole)
        if path in self._albums:
            self._albums.remove(path)
        self.album_removed.emit(path)

    def _on_album_selection_changed(self, current, previous):
        has = current is not None
        self._move_btn.setEnabled(has)
        self._copy_btn.setEnabled(has)

    def _request_move(self):
        item = self._list.currentItem()
        if item:
            self.move_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _request_copy(self):
        item = self._list.currentItem()
        if item:
            self.copy_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def selected_album(self) -> Optional[Path]:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def get_albums(self) -> List[Path]:
        return list(self._albums)

    def set_albums(self, albums: List[Path]):
        self._list.clear()
        self._albums = []
        for path in albums:
            if path.exists():
                self._albums.append(path)
                item = QListWidgetItem(path.name)
                item.setToolTip(str(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                self._list.addItem(item)

    # ── collections ────────────────────────────────────────────────────────────

    def set_collections(self, collections: List[Dict[str, Any]]):
        self._collections = list(collections)
        self._populate_coll_list()

    def refresh_collections(self, collections: List[Dict[str, Any]]):
        self.set_collections(collections)

    def selected_collection_id(self) -> Optional[str]:
        item = self._coll_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _populate_coll_list(self):
        self._coll_list.clear()
        for c in self._collections:
            ctype = c.get("type", "regular")
            name = c.get("name", "")
            if ctype in ("smart", "auto"):
                icon = "⚡"
            else:
                icon = "📁"
            item = QListWidgetItem(f"{icon} {name}")
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            item.setToolTip(f"Type: {ctype}")
            self._coll_list.addItem(item)

    def _on_coll_selection_changed(self, current, previous):
        has = current is not None
        self._open_coll_btn.setEnabled(has)
        if has:
            cid = current.data(Qt.ItemDataRole.UserRole)
            # Remove button enabled only for non-auto collections
            is_auto = cid in _AUTO_IDS
            self._coll_remove_btn.setEnabled(not is_auto)
            # Add-to button enabled only for regular (non-auto) collections
            coll = self._get_coll(cid)
            is_regular = coll and coll.get("type") == "regular"
            self._add_to_coll_btn.setEnabled(bool(is_regular))
        else:
            self._coll_remove_btn.setEnabled(False)
            self._add_to_coll_btn.setEnabled(False)

    def _get_coll(self, cid: str) -> Optional[Dict]:
        for c in self._collections:
            if c["id"] == cid:
                return c
        return None

    def _add_regular_collection(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Collection", "Collection name:")
        if ok and name.strip():
            # Signal main window to create it; main window will call refresh_collections
            # We emit a special signal via collection_add with a sentinel prefix
            self.collection_add.emit("__new_regular__:" + name.strip())

    def _add_smart_collection(self):
        dlg = SmartCollectionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Encode as "new_smart:<name>:<rule_json>"
            import json as _json
            payload = _json.dumps({
                "name": dlg.result_name,
                "rule": dlg.result_rule,
            })
            self.collection_add.emit("__new_smart__:" + payload)

    def _remove_collection(self):
        cid = self.selected_collection_id()
        if cid:
            self.collection_add.emit("__remove__:" + cid)

    def _open_collection(self):
        cid = self.selected_collection_id()
        if cid:
            self.collection_open.emit(cid)

    def _add_to_collection(self):
        cid = self.selected_collection_id()
        if cid:
            self.collection_add.emit(cid)

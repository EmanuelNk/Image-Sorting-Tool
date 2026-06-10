from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QListWidget, QListWidgetItem, QPushButton,
                              QFileDialog, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class SidebarWidget(QWidget):
    move_requested = pyqtSignal(Path)   # user wants to move current image here
    album_added = pyqtSignal(Path)
    album_removed = pyqtSignal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(190)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._albums: List[Path] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        title = QLabel("ALBUMS")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        title.setFont(title_font)
        title.setStyleSheet("color: #777;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet("""
            QListWidget {
                background: #1e1e1e;
                border: 1px solid #333;
                border-radius: 4px;
                color: #ccc;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 6px;
            }
            QListWidget::item:selected {
                background: #2a4060;
                color: #fff;
            }
            QListWidget::item:hover:!selected {
                background: #2a2a2a;
            }
        """)
        layout.addWidget(self._list, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setToolTip("Add target album folder")
        self._add_btn.clicked.connect(self._add_album)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setToolTip("Remove selected album")
        self._remove_btn.clicked.connect(self._remove_album)

        for btn in (self._add_btn, self._remove_btn):
            btn.setStyleSheet("""
                QPushButton {
                    background: #2e2e2e;
                    color: #ccc;
                    border: 1px solid #444;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background: #3a3a3a; }
                QPushButton:pressed { background: #252525; }
            """)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        self._move_btn = QPushButton("Move Here  (M)")
        self._move_btn.setToolTip("Move current image to selected album (M)")
        self._move_btn.setEnabled(False)
        self._move_btn.clicked.connect(self._request_move)
        self._move_btn.setStyleSheet("""
            QPushButton {
                background: #1a4080;
                color: #fff;
                border: 1px solid #2060b0;
                border-radius: 3px;
                padding: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1e50a0; }
            QPushButton:pressed { background: #153060; }
            QPushButton:disabled {
                background: #252525;
                color: #555;
                border-color: #333;
            }
        """)
        layout.addWidget(self._move_btn)

        self._list.currentItemChanged.connect(self._on_selection_changed)

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

    def _on_selection_changed(self, current, previous):
        self._move_btn.setEnabled(current is not None)

    def _request_move(self):
        item = self._list.currentItem()
        if item:
            path: Path = item.data(Qt.ItemDataRole.UserRole)
            self.move_requested.emit(path)

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

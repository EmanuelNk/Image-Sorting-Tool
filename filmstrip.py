from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QListWidget, QListWidgetItem
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QObject, pyqtSlot,
                           QRunnable, QThreadPool, QSize, QRect)
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QPen, QIcon
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle

from image_loader import load_thumbnail
from metadata import MetadataStore

THUMB_W = 128
THUMB_H = 96
ITEM_W = THUMB_W + 8
ITEM_H = THUMB_H + 28

COLOR_MAP = {
    "red": QColor(192, 57, 43),
    "yellow": QColor(212, 172, 13),
    "green": QColor(30, 132, 73),
    "blue": QColor(26, 82, 118),
    "purple": QColor(108, 52, 131),
}

_PATH_ROLE = Qt.ItemDataRole.UserRole
_META_ROLE = Qt.ItemDataRole.UserRole + 1
_PIXMAP_ROLE = Qt.ItemDataRole.UserRole + 2
_SUBFOLDER_ROLE = Qt.ItemDataRole.UserRole + 3


class _ThumbSignals(QObject):
    loaded = pyqtSignal(str, QImage)


class _ThumbLoader(QRunnable):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.signals = _ThumbSignals()
        self.setAutoDelete(True)

    def run(self):
        img = load_thumbnail(self.path, (THUMB_W * 2, THUMB_H * 2))
        if img is None:
            return
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
        self.signals.loaded.emit(str(self.path), qimg.copy())


class _Delegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(ITEM_W, ITEM_H)

    def paint(self, painter, option, index):
        painter.save()
        r = option.rect
        thumb_r = QRect(r.x() + 3, r.y() + 3, THUMB_W, THUMB_H)
        bottom_r = QRect(r.x(), r.y() + THUMB_H + 3, r.width(), ITEM_H - THUMB_H - 3)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Item background
        painter.fillRect(r, QColor(22, 22, 22))

        # Thumbnail area
        painter.fillRect(thumb_r, QColor(40, 40, 40))
        pixmap: Optional[QPixmap] = index.data(_PIXMAP_ROLE)
        if pixmap:
            px = thumb_r.x() + (THUMB_W - pixmap.width()) // 2
            py = thumb_r.y() + (THUMB_H - pixmap.height()) // 2
            painter.drawPixmap(px, py, pixmap)

        meta: dict = index.data(_META_ROLE) or {}
        rating = meta.get("rating", 0)
        color_label = meta.get("color_label")
        flag = meta.get("flag", "unflagged")

        # Reject tint
        if flag == "reject":
            painter.fillRect(thumb_r, QColor(180, 0, 0, 70))

        # Color label strip at bottom of thumbnail
        if color_label and color_label in COLOR_MAP:
            strip = QRect(thumb_r.x(), thumb_r.bottom() - 3, THUMB_W, 4)
            painter.fillRect(strip, COLOR_MAP[color_label])

        # Selection border
        pen = QPen(QColor(255, 195, 30) if selected else QColor(55, 55, 55), 2)
        painter.setPen(pen)
        painter.drawRect(thumb_r.adjusted(1, 1, -1, -1))

        # Bottom strip
        painter.fillRect(bottom_r, QColor(18, 18, 18))

        # Stars
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        for i in range(5):
            painter.setPen(QColor(255, 195, 0) if i < rating else QColor(55, 55, 55))
            painter.drawText(bottom_r.x() + 2 + i * 13, bottom_r.bottom() - 3,
                             "★" if i < rating else "☆")

        # Flag indicator
        if flag == "pick":
            painter.setPen(QColor(52, 152, 219))
            flag_font = QFont()
            flag_font.setPointSize(7)
            flag_font.setBold(True)
            painter.setFont(flag_font)
            painter.drawText(bottom_r.right() - 14, bottom_r.bottom() - 3, "P")
        elif flag == "reject":
            painter.setPen(QColor(231, 76, 60))
            flag_font = QFont()
            flag_font.setPointSize(7)
            flag_font.setBold(True)
            painter.setFont(flag_font)
            painter.drawText(bottom_r.right() - 14, bottom_r.bottom() - 3, "✕")

        # Subfolder banner
        subfolder = index.data(_SUBFOLDER_ROLE) or ""
        if subfolder:
            banner_h = 13
            banner_r = QRect(thumb_r.x(), thumb_r.bottom() - banner_h - 4,
                             THUMB_W, banner_h)
            painter.fillRect(banner_r, QColor(0, 0, 0, 160))
            sf_font = QFont()
            sf_font.setPointSize(6)
            painter.setFont(sf_font)
            painter.setPen(QColor(220, 220, 220))
            painter.drawText(banner_r.adjusted(3, 0, -2, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             subfolder)

        painter.restore()


class FilmstripWidget(QListWidget):
    image_selected = pyqtSignal(int)     # current (viewer) row changed
    selection_changed = pyqtSignal(int)  # total selected count changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.ResizeMode.Fixed)
        self.setFixedHeight(ITEM_H + 22)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.setItemDelegate(_Delegate(self))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self.setStyleSheet("""
            QListWidget {
                background: #161616;
                border: none;
                border-top: 1px solid #333;
                outline: none;
            }
            QListWidget::item { background: #161616; }
            QScrollBar:horizontal {
                background: #1e1e1e; height: 8px; margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #484848; border-radius: 4px; min-width: 30px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)

        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(4)
        self._path_to_row: dict = {}
        self._programmatic = False

        self.currentRowChanged.connect(self._on_row_changed)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def load_images(self, paths: List[Path], metadata: MetadataStore,
                    root: Optional[Path] = None):
        self.blockSignals(True)
        self.clear()
        self._path_to_row.clear()

        for i, path in enumerate(paths):
            subfolder = path.parent.name if (root and path.parent != root) else ""
            item = QListWidgetItem()
            item.setSizeHint(QSize(ITEM_W, ITEM_H))
            item.setData(_PATH_ROLE, str(path))
            item.setData(_META_ROLE, metadata.get(path))
            item.setData(_PIXMAP_ROLE, None)
            item.setData(_SUBFOLDER_ROLE, subfolder)
            self.addItem(item)
            self._path_to_row[str(path)] = i

            loader = _ThumbLoader(path)
            loader.signals.loaded.connect(self._on_thumb_loaded)
            self._pool.start(loader)

        self.blockSignals(False)

    def update_item_metadata(self, path: Path, metadata: MetadataStore):
        key = str(path)
        row = self._path_to_row.get(key)
        if row is not None:
            item = self.item(row)
            if item:
                item.setData(_META_ROLE, metadata.get(path))
                self.update(self.indexFromItem(item))

    def select_row(self, row: int):
        """Select a single row programmatically (arrow-key navigation)."""
        if 0 <= row < self.count():
            self._programmatic = True
            self.clearSelection()
            self.setCurrentRow(row)
            item = self.item(row)
            if item:
                item.setSelected(True)
            self._programmatic = False
            self.scrollToItem(self.currentItem(),
                              QListWidget.ScrollHint.PositionAtCenter)
            self.selection_changed.emit(1)

    def selected_paths(self) -> List[Path]:
        paths = []
        for item in self.selectedItems():
            path_str = item.data(_PATH_ROLE)
            if path_str:
                paths.append(Path(path_str))
        return paths

    def select_all_items(self):
        self.selectAll()

    def _on_thumb_loaded(self, path_str: str, qimg: QImage):
        row = self._path_to_row.get(path_str)
        if row is None:
            return
        item = self.item(row)
        if item is None:
            return
        pixmap = QPixmap.fromImage(qimg).scaled(
            THUMB_W, THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        item.setData(_PIXMAP_ROLE, pixmap)
        self.update(self.indexFromItem(item))

    def _on_row_changed(self, row: int):
        if not self._programmatic and row >= 0:
            self.image_selected.emit(row)

    def _on_selection_changed(self):
        if not self._programmatic:
            self.selection_changed.emit(len(self.selectedItems()))

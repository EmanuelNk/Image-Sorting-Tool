from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QStyledItemDelegate,
                              QStyle, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QThreadPool, QObject, QSize, QRect
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QPen

from image_loader import load_thumbnail
from metadata import MetadataStore

THUMB_MIN = 80
THUMB_MAX = 360
THUMB_DEFAULT = 180
_LABEL_H = 26

_PATH_ROLE = Qt.ItemDataRole.UserRole
_META_ROLE = Qt.ItemDataRole.UserRole + 1
_PIXMAP_ROLE = Qt.ItemDataRole.UserRole + 2

_COLOR_MAP = {
    "red":    QColor(192, 57, 43),
    "yellow": QColor(212, 172, 13),
    "green":  QColor(30, 132, 73),
    "blue":   QColor(26, 82, 118),
    "purple": QColor(108, 52, 131),
}


class _ThumbSignals(QObject):
    loaded = pyqtSignal(str, QImage)


class _ThumbLoader(QRunnable):
    LOAD_SIZE = 600  # load at fixed high-res; delegate scales down

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.signals = _ThumbSignals()
        self.setAutoDelete(True)

    def run(self):
        img = load_thumbnail(self.path, (self.LOAD_SIZE, self.LOAD_SIZE))
        if img is None:
            return
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height,
                      img.width * 3, QImage.Format.Format_RGB888)
        self.signals.loaded.emit(str(self.path), qimg.copy())


class _GridDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumb_size = THUMB_DEFAULT

    def _rects(self, base):
        s = self.thumb_size
        thumb = QRect(base.x() + 3, base.y() + 3, s, s)
        bottom = QRect(base.x(), base.y() + s + 3, base.width(), _LABEL_H)
        return thumb, bottom

    def sizeHint(self, option, index):
        s = self.thumb_size
        return QSize(s + 6, s + _LABEL_H + 6)

    def paint(self, painter, option, index):
        painter.save()
        thumb_r, bottom_r = self._rects(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.fillRect(option.rect, QColor(22, 22, 22))
        painter.fillRect(thumb_r, QColor(40, 40, 40))

        pixmap: Optional[QPixmap] = index.data(_PIXMAP_ROLE)
        if pixmap:
            scaled = pixmap.scaled(
                thumb_r.width(), thumb_r.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = thumb_r.x() + (thumb_r.width() - scaled.width()) // 2
            py = thumb_r.y() + (thumb_r.height() - scaled.height()) // 2
            painter.drawPixmap(px, py, scaled)
        else:
            painter.setPen(QColor(60, 60, 60))
            painter.drawText(thumb_r, Qt.AlignmentFlag.AlignCenter, "…")

        meta: dict = index.data(_META_ROLE) or {}
        rating = meta.get("rating", 0)
        color_label = meta.get("color_label")
        flag = meta.get("flag", "unflagged")

        if flag == "reject":
            painter.fillRect(thumb_r, QColor(180, 0, 0, 70))

        if color_label and color_label in _COLOR_MAP:
            strip = QRect(thumb_r.x(), thumb_r.bottom() - 3, thumb_r.width(), 4)
            painter.fillRect(strip, _COLOR_MAP[color_label])

        pen = QPen(QColor(255, 195, 30) if selected else QColor(50, 50, 50),
                   2 if selected else 1)
        painter.setPen(pen)
        painter.drawRect(thumb_r.adjusted(1, 1, -1, -1))

        painter.fillRect(bottom_r, QColor(18, 18, 18))

        # Scale star font with thumb size
        star_pt = max(6, min(11, self.thumb_size // 18))
        star_w = star_pt + 5
        font = QFont()
        font.setPointSize(star_pt)
        painter.setFont(font)
        for i in range(5):
            painter.setPen(QColor(255, 195, 0) if i < rating else QColor(55, 55, 55))
            painter.drawText(bottom_r.x() + 2 + i * star_w,
                             bottom_r.bottom() - 4,
                             "★" if i < rating else "☆")

        if flag in ("pick", "reject"):
            ff = QFont()
            ff.setPointSize(star_pt)
            ff.setBold(True)
            painter.setFont(ff)
            painter.setPen(QColor(52, 152, 219) if flag == "pick" else QColor(231, 76, 60))
            painter.drawText(bottom_r.right() - star_w - 2,
                             bottom_r.bottom() - 4,
                             "P" if flag == "pick" else "✕")

        painter.restore()


class GridViewWidget(QListWidget):
    image_selected = pyqtSignal(int)
    selection_changed = pyqtSignal(int)
    open_detail = pyqtSignal(int)   # double-click → switch to detail view

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSpacing(4)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._delegate = _GridDelegate()
        self.setItemDelegate(self._delegate)
        self._thumb_size = THUMB_DEFAULT

        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(6)
        self._path_to_row: dict = {}
        self._programmatic = False

        self.setStyleSheet("""
            QListWidget {
                background: #161616;
                border: none;
                outline: none;
            }
            QListWidget::item { background: #161616; border: none; }
            QScrollBar:vertical {
                background: #1e1e1e; width: 8px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #484848; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.currentRowChanged.connect(self._on_row_changed)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.doubleClicked.connect(self._on_double_click)

    # ── size control ──────────────────────────────────────────────────────────

    @property
    def thumb_size(self) -> int:
        return self._thumb_size

    def set_thumb_size(self, size: int):
        size = max(THUMB_MIN, min(THUMB_MAX, size))
        self._thumb_size = size
        self._delegate.thumb_size = size
        hint = QSize(size + 6, size + _LABEL_H + 6)
        for i in range(self.count()):
            item = self.item(i)
            if item:
                item.setSizeHint(hint)
        self.scheduleDelayedItemsLayout()

    # ── population ────────────────────────────────────────────────────────────

    def load_images(self, paths: List[Path], metadata: MetadataStore):
        self.blockSignals(True)
        self.clear()
        self._path_to_row.clear()

        hint = QSize(self._thumb_size + 6, self._thumb_size + _LABEL_H + 6)
        for i, path in enumerate(paths):
            item = QListWidgetItem()
            item.setSizeHint(hint)
            item.setData(_PATH_ROLE, str(path))
            item.setData(_META_ROLE, metadata.get(path.name))
            item.setData(_PIXMAP_ROLE, None)
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
                item.setData(_META_ROLE, metadata.get(path.name))
                self.update(self.indexFromItem(item))

    # ── selection helpers (mirror filmstrip API) ──────────────────────────────

    def select_row(self, row: int):
        if 0 <= row < self.count():
            self._programmatic = True
            self.clearSelection()
            self.setCurrentRow(row)
            item = self.item(row)
            if item:
                item.setSelected(True)
            self._programmatic = False
            self.scrollToItem(self.currentItem(),
                              QListWidget.ScrollHint.EnsureVisible)
            self.selection_changed.emit(1)

    def selected_paths(self) -> List[Path]:
        paths = []
        for item in self.selectedItems():
            s = item.data(_PATH_ROLE)
            if s:
                paths.append(Path(s))
        return paths

    def select_all_items(self):
        self.selectAll()

    # ── private slots ─────────────────────────────────────────────────────────

    def _on_thumb_loaded(self, path_str: str, qimg: QImage):
        row = self._path_to_row.get(path_str)
        if row is None:
            return
        item = self.item(row)
        if item is None:
            return
        item.setData(_PIXMAP_ROLE, QPixmap.fromImage(qimg))
        self.update(self.indexFromItem(item))

    def _on_row_changed(self, row: int):
        if not self._programmatic and row >= 0:
            self.image_selected.emit(row)

    def _on_selection_changed(self):
        if not self._programmatic:
            self.selection_changed.emit(len(self.selectedItems()))

    def _on_double_click(self, index):
        if index.row() >= 0:
            self.open_detail.emit(index.row())

    # ── keyboard: block type-ahead for shortcut keys ──────────────────────────

    def keyPressEvent(self, event):
        nav = {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
               Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown}
        key = event.key()
        mod = event.modifiers()

        if key in nav:
            super().keyPressEvent(event)
            return
        # Ctrl+A → select all (handled by QListWidget)
        if key == Qt.Key.Key_A and mod == Qt.KeyboardModifier.ControlModifier:
            super().keyPressEvent(event)
            return
        # All other keys: accept without forwarding so type-ahead doesn't fire.
        # The window-level QShortcuts fire independently and handle ratings etc.
        event.accept()

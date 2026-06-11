from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QListWidget, QListWidgetItem
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QObject, pyqtSlot,
                           QRunnable, QThreadPool, QSize, QRect, QRectF,
                           QPoint, QTimer)
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QPen, QIcon, QPainterPath, QTransform
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        r = option.rect
        thumb_r = QRect(r.x() + 3, r.y() + 3, THUMB_W, THUMB_H)
        bottom_r = QRect(r.x(), r.y() + THUMB_H + 3, r.width(), ITEM_H - THUMB_H - 3)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        corner_r = 5

        painter.fillRect(r, QColor(28, 28, 30))

        # Rounded thumbnail background
        thumb_path = QPainterPath()
        thumb_path.addRoundedRect(QRectF(thumb_r), corner_r, corner_r)
        painter.fillPath(thumb_path, QColor(44, 44, 46))

        pixmap = index.data(_PIXMAP_ROLE)
        if pixmap:
            rotation = (index.data(_META_ROLE) or {}).get("rotation", 0)
            if rotation:
                pixmap = pixmap.transformed(QTransform().rotate(rotation),
                                            Qt.TransformationMode.SmoothTransformation)
                pixmap = pixmap.scaled(THUMB_W, THUMB_H,
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
            px = thumb_r.x() + (THUMB_W - pixmap.width()) // 2
            py = thumb_r.y() + (THUMB_H - pixmap.height()) // 2
            painter.save()
            painter.setClipPath(thumb_path)
            painter.drawPixmap(px, py, pixmap)
            painter.restore()

        meta: dict = index.data(_META_ROLE) or {}
        rating = meta.get("rating", 0)
        color_label = meta.get("color_label")
        flag = meta.get("flag", "unflagged")

        if flag == "reject":
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(thumb_r, QColor(255, 69, 58, 60))
            painter.restore()

        if color_label and color_label in COLOR_MAP:
            strip = QRect(thumb_r.x(), thumb_r.bottom() - 3, THUMB_W, 4)
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(strip, COLOR_MAP[color_label])
            painter.restore()

        # Rounded selection border
        pen = QPen(QColor(10, 132, 255) if selected else QColor(58, 58, 60, 160), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_path = QPainterPath()
        border_path.addRoundedRect(QRectF(thumb_r).adjusted(1, 1, -1, -1), corner_r, corner_r)
        painter.drawPath(border_path)

        painter.fillRect(bottom_r, QColor(22, 22, 24))

        # Stars
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        for i in range(5):
            painter.setPen(QColor(255, 214, 10) if i < rating else QColor(72, 72, 74))
            painter.drawText(bottom_r.x() + 2 + i * 13, bottom_r.bottom() - 3,
                             "★" if i < rating else "☆")

        if flag == "pick":
            painter.setPen(QColor(48, 209, 88))
            flag_font = QFont()
            flag_font.setPointSize(7)
            flag_font.setBold(True)
            painter.setFont(flag_font)
            painter.drawText(bottom_r.right() - 14, bottom_r.bottom() - 3, "P")
        elif flag == "reject":
            painter.setPen(QColor(255, 69, 58))
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
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(banner_r, QColor(0, 0, 0, 170))
            painter.restore()
            sf_font = QFont()
            sf_font.setPointSize(6)
            painter.setFont(sf_font)
            painter.setPen(QColor(235, 235, 245, 200))
            painter.drawText(banner_r.adjusted(3, 0, -2, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             subfolder)

        painter.restore()


class FilmstripWidget(QListWidget):
    image_selected = pyqtSignal(int)     # current (viewer) row changed
    selection_changed = pyqtSignal(int)  # total selected count changed
    load_progress = pyqtSignal(int, int)  # (loaded, total) for the queued batch

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
                background: #1C1C1E;
                border: none;
                border-top: 1px solid #3A3A3C;
                outline: none;
            }
            QListWidget::item { background: #1C1C1E; }
            QScrollBar:horizontal {
                background: #2C2C2E; height: 8px; margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #48484A; border-radius: 4px; min-width: 30px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)

        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(3)
        self._path_to_row: dict = {}
        self._queued: set = set()
        self._loaded_count = 0
        self._programmatic = False

        self.horizontalScrollBar().valueChanged.connect(self._queue_visible_thumbs)
        self.currentRowChanged.connect(self._on_row_changed)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def load_images(self, paths: List[Path], metadata: MetadataStore,
                    root: Optional[Path] = None):
        # Cancel any pending (not-yet-started) loads from a previous folder
        self._pool.clear()
        self._queued.clear()
        self._loaded_count = 0

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

        self.blockSignals(False)
        # Defer so layout settles before we hit-test for visible items
        QTimer.singleShot(50, self._queue_visible_thumbs)

    # ── lazy thumbnail loading ────────────────────────────────────────────────

    _LOAD_BUFFER = 12  # items left/right of the visible range to pre-load

    def _queue_visible_thumbs(self):
        count = self.count()
        if count == 0:
            return
        vr = self.viewport().rect()
        left = self.indexAt(QPoint(vr.left() + 1, vr.center().y()))
        right = self.indexAt(QPoint(vr.right() - 1, vr.center().y()))

        left_col = left.row() if left.isValid() else 0
        right_col = right.row() if right.isValid() else count - 1
        if right_col < left_col:
            right_col = count - 1

        start = max(0, left_col - self._LOAD_BUFFER)
        end = min(count - 1, right_col + self._LOAD_BUFFER)

        for row in range(start, end + 1):
            item = self.item(row)
            if item is None:
                continue
            path_str = item.data(_PATH_ROLE)
            if not path_str or path_str in self._queued:
                continue
            self._queued.add(path_str)
            loader = _ThumbLoader(Path(path_str))
            loader.signals.loaded.connect(self._on_thumb_loaded)
            self._pool.start(loader)
        self._emit_progress()

    def _emit_progress(self):
        total = len(self._queued)
        self.load_progress.emit(self._loaded_count, total)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_visible_thumbs()

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
            # EnsureVisible (not PositionAtCenter): when the row is already
            # visible — e.g. the user just clicked it — this does nothing, so the
            # thumbnail stays put instead of snapping to center. Force-centering
            # made clicks on near-identical consecutive frames look like the
            # selection jumped a couple of items to the right.
            self.scrollToItem(self.currentItem(),
                              QListWidget.ScrollHint.EnsureVisible)
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
        self._loaded_count += 1
        self._emit_progress()
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

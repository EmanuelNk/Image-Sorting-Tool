from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QStyledItemDelegate,
                              QStyle, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QThreadPool, QObject, QSize, QRect, QRectF, QPoint, QTimer
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QPen, QPainterPath, QTransform

from image_loader import load_thumbnail_cached
from metadata import MetadataStore

THUMB_MIN = 80
THUMB_MAX = 360
THUMB_DEFAULT = 180
_LABEL_H = 26

_PATH_ROLE = Qt.ItemDataRole.UserRole
_META_ROLE = Qt.ItemDataRole.UserRole + 1
_PIXMAP_ROLE = Qt.ItemDataRole.UserRole + 2
_SUBFOLDER_ROLE  = Qt.ItemDataRole.UserRole + 3
_FILETYPE_ROLE   = Qt.ItemDataRole.UserRole + 4

_RAW_EXTS = {".raf", ".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2", ".raw", ".pef"}
_HEIF_EXTS = {".hif", ".heic", ".heif"}

def _filetype_label(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "JPG"
    if ext in (".tiff", ".tif"):
        return "TIF"
    return ext.lstrip(".").upper()

def _filetype_color(label: str) -> QColor:
    if label == "JPG":
        return QColor(58, 58, 60, 230)
    if label in ("HIF", "HEIC", "HEIF"):
        return QColor(0, 70, 140, 230)
    # RAW formats
    if label in ("RAF", "NEF", "CR2", "CR3", "ARW", "DNG", "ORF", "RW2", "PEF", "RAW"):
        return QColor(110, 65, 0, 230)
    return QColor(44, 44, 46, 230)

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
    LOAD_SIZE = 400  # cached thumbnails; sharp at THUMB_MAX (360px)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.signals = _ThumbSignals()
        self.setAutoDelete(True)

    def run(self):
        img = load_thumbnail_cached(self.path, (self.LOAD_SIZE, self.LOAD_SIZE))
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        thumb_r, bottom_r = self._rects(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        corner_r = max(4, self.thumb_size // 30)

        painter.fillRect(option.rect, QColor(28, 28, 30))

        # Rounded thumbnail background
        thumb_path = QPainterPath()
        thumb_path.addRoundedRect(QRectF(thumb_r), corner_r, corner_r)
        painter.fillPath(thumb_path, QColor(44, 44, 46))

        pixmap: Optional[QPixmap] = index.data(_PIXMAP_ROLE)
        if pixmap:
            rotation = (index.data(_META_ROLE) or {}).get("rotation", 0)
            if rotation:
                pixmap = pixmap.transformed(QTransform().rotate(rotation),
                                            Qt.TransformationMode.SmoothTransformation)
            scaled = pixmap.scaled(
                thumb_r.width(), thumb_r.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = thumb_r.x() + (thumb_r.width() - scaled.width()) // 2
            py = thumb_r.y() + (thumb_r.height() - scaled.height()) // 2
            painter.save()
            painter.setClipPath(thumb_path)
            painter.drawPixmap(px, py, scaled)
            painter.restore()
        else:
            painter.setPen(QColor(72, 72, 74))
            painter.drawText(thumb_r, Qt.AlignmentFlag.AlignCenter, "…")

        # File type badge — top-left corner, pill-shaped
        ft_label = index.data(_FILETYPE_ROLE) or ""
        if ft_label:
            ft_font = QFont()
            ft_font.setPointSize(max(6, min(9, self.thumb_size // 22)))
            ft_font.setBold(True)
            painter.setFont(ft_font)
            fm = painter.fontMetrics()
            badge_w = fm.horizontalAdvance(ft_label) + 8
            badge_h = fm.height() + 4
            badge_r = QRect(thumb_r.x() + 5, thumb_r.y() + 5, badge_w, badge_h)
            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(badge_r), 4, 4)
            painter.fillPath(badge_path, _filetype_color(ft_label))
            painter.setPen(QColor(235, 235, 245))
            painter.drawText(badge_r, Qt.AlignmentFlag.AlignCenter, ft_label)

        meta: dict = index.data(_META_ROLE) or {}
        rating = meta.get("rating", 0)
        color_label = meta.get("color_label")
        flag = meta.get("flag", "unflagged")

        if flag == "reject":
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(thumb_r, QColor(255, 69, 58, 60))
            painter.restore()

        if color_label and color_label in _COLOR_MAP:
            strip = QRect(thumb_r.x(), thumb_r.bottom() - 3, thumb_r.width(), 4)
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(strip, _COLOR_MAP[color_label])
            painter.restore()

        # Rounded selection border
        pen = QPen(QColor(10, 132, 255) if selected else QColor(58, 58, 60, 160),
                   2 if selected else 1)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_path = QPainterPath()
        border_path.addRoundedRect(
            QRectF(thumb_r).adjusted(1, 1, -1, -1), corner_r, corner_r
        )
        painter.drawPath(border_path)

        painter.fillRect(bottom_r, QColor(22, 22, 24))

        # Scale star font with thumb size
        star_pt = max(6, min(11, self.thumb_size // 18))
        star_w = star_pt + 5
        font = QFont()
        font.setPointSize(star_pt)
        painter.setFont(font)
        for i in range(5):
            painter.setPen(QColor(255, 214, 10) if i < rating else QColor(72, 72, 74))
            painter.drawText(bottom_r.x() + 2 + i * star_w,
                             bottom_r.bottom() - 4,
                             "★" if i < rating else "☆")

        if flag in ("pick", "reject"):
            ff = QFont()
            ff.setPointSize(star_pt)
            ff.setBold(True)
            painter.setFont(ff)
            painter.setPen(QColor(48, 209, 88) if flag == "pick" else QColor(255, 69, 58))
            painter.drawText(bottom_r.right() - star_w - 2,
                             bottom_r.bottom() - 4,
                             "P" if flag == "pick" else "✕")

        # Subfolder banner
        subfolder = index.data(_SUBFOLDER_ROLE) or ""
        if subfolder:
            banner_h = max(14, star_pt + 6)
            banner_r = QRect(thumb_r.x(), thumb_r.bottom() - banner_h - 4,
                             thumb_r.width(), banner_h)
            painter.save()
            painter.setClipPath(thumb_path)
            painter.fillRect(banner_r, QColor(0, 0, 0, 170))
            painter.restore()
            sf_font = QFont()
            sf_font.setPointSize(max(6, star_pt - 1))
            painter.setFont(sf_font)
            painter.setPen(QColor(235, 235, 245, 200))
            painter.drawText(banner_r.adjusted(3, 0, -2, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             subfolder)

        painter.restore()


class GridViewWidget(QListWidget):
    image_selected = pyqtSignal(int)
    selection_changed = pyqtSignal(int)
    open_detail = pyqtSignal(int)   # double-click → switch to detail view
    load_progress = pyqtSignal(int, int)  # (loaded, total) for the queued batch

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
        self._pool.setMaxThreadCount(2)
        self._path_to_row: dict = {}
        self._queued: set = set()
        self._loaded_count = 0
        self._programmatic = False

        self.setStyleSheet("""
            QListWidget {
                background: #1C1C1E;
                border: none;
                outline: none;
            }
            QListWidget::item { background: #1C1C1E; border: none; }
            QScrollBar:vertical {
                background: #2C2C2E; width: 8px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #48484A; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.verticalScrollBar().valueChanged.connect(self._queue_visible_thumbs)

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
        QTimer.singleShot(50, self._queue_visible_thumbs)

    # ── population ────────────────────────────────────────────────────────────

    def load_images(self, paths: List[Path], metadata: MetadataStore,
                    root: Optional[Path] = None):
        # Cancel pending (not-yet-started) loads from any previous folder
        self._pool.clear()
        self._queued.clear()
        self._loaded_count = 0

        self.blockSignals(True)
        self.clear()
        self._path_to_row.clear()

        hint = QSize(self._thumb_size + 6, self._thumb_size + _LABEL_H + 6)
        for i, path in enumerate(paths):
            subfolder = path.parent.name if (root and path.parent != root) else ""
            item = QListWidgetItem()
            item.setSizeHint(hint)
            item.setData(_PATH_ROLE, str(path))
            item.setData(_META_ROLE, metadata.get(path))
            item.setData(_PIXMAP_ROLE, None)
            item.setData(_SUBFOLDER_ROLE, subfolder)
            item.setData(_FILETYPE_ROLE, _filetype_label(path))
            self.addItem(item)
            self._path_to_row[str(path)] = i

        self.blockSignals(False)
        # Defer so the widget finishes layout before we hit-test for visible rows
        QTimer.singleShot(50, self._queue_visible_thumbs)

    def update_item_metadata(self, path: Path, metadata: MetadataStore):
        key = str(path)
        row = self._path_to_row.get(key)
        if row is not None:
            item = self.item(row)
            if item:
                item.setData(_META_ROLE, metadata.get(path))
                self.update(self.indexFromItem(item))

    # ── lazy thumbnail loading ────────────────────────────────────────────────

    _LOAD_BUFFER = 30  # rows above/below the visible area to pre-load

    def _queue_visible_thumbs(self):
        """Queue thumbnail loads only for visible items plus a scroll buffer."""
        count = self.count()
        if count == 0:
            return
        vr = self.viewport().rect()

        top_idx = self.indexAt(vr.topLeft())
        bot_idx = self.indexAt(QPoint(vr.center().x(), vr.bottom() - 1))

        top_row = top_idx.row() if top_idx.isValid() else 0
        bot_row = bot_idx.row() if bot_idx.isValid() else count - 1
        if bot_row < top_row:
            bot_row = count - 1

        start = max(0, top_row - self._LOAD_BUFFER)
        end = min(count - 1, bot_row + self._LOAD_BUFFER)

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
        self.load_progress.emit(self._loaded_count, len(self._queued))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_visible_thumbs()

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
        self._loaded_count += 1
        self.load_progress.emit(self._loaded_count, len(self._queued))
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

from collections import OrderedDict
from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import (Qt, pyqtSignal, QObject, QRunnable, QThreadPool)
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QTransform


COLOR_MAP = {
    "red": "#FF453A",
    "yellow": "#FFD60A",
    "green": "#30D158",
    "blue": "#0A84FF",
    "purple": "#BF5AF2",
}

FLAG_COLORS = {
    "pick": "#30D158",
    "reject": "#FF453A",
    "unflagged": "#48484A",
}

FLAG_LABELS = {"pick": "PICK", "reject": "REJECT", "unflagged": ""}


class _PreviewSignals(QObject):
    done = pyqtSignal(str, QImage)
    failed = pyqtSignal(str)


class _PreviewTask(QRunnable):
    """Decode a fit-to-window preview off the UI thread. QImage (unlike QPixmap)
    is safe to build on a worker thread; the widget turns it into a QPixmap.

    The signals object is owned by the viewer (passed in), not created per-task —
    QThreadPool takes C++ ownership of the runnable and the Python wrapper can be
    collected, which would take a per-task signals object down with it."""

    def __init__(self, path_str: str, signals: _PreviewSignals):
        super().__init__()
        self.path_str = path_str
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        from image_loader import load_preview
        img = load_preview(Path(self.path_str))
        if img is None:
            self.signals.failed.emit(self.path_str)
            return
        if img.mode != "RGB":
            img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height,
                      img.width * 3, QImage.Format.Format_RGB888)
        self.signals.done.emit(self.path_str, qimg.copy())


class ImageViewerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._pixmap: Optional[QPixmap] = None
        self._loading_path: Optional[str] = None
        self._current_path: Optional[str] = None
        self._rating = 0
        self._color_label: Optional[str] = None
        self._flag = "unflagged"
        self._rotation = 0
        self._rot_key = None
        self._rot_pixmap: Optional[QPixmap] = None

        # Decoded-preview cache (path_str -> QImage) with LRU eviction, plus a
        # small thread pool. Together with prefetch() this makes navigation feel
        # instant: neighbours are decoded before you arrive, revisits are cached.
        self._cache: "OrderedDict[str, QImage]" = OrderedDict()
        self._cache_max = 12
        self._inflight: set = set()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(3)
        # One signals object, owned by the widget, shared by all decode tasks.
        self._signals = _PreviewSignals()
        self._signals.done.connect(self._on_loaded)
        self._signals.failed.connect(self._on_failed)

        self._placeholder_text = "Open a folder to begin  (⌘O)"

    # ── loading ───────────────────────────────────────────────────────────────

    def load_image(self, path: Path):
        path_str = str(path)
        if path_str == self._current_path:
            return
        self._loading_path = path_str

        cached = self._cache.get(path_str)
        if cached is not None:
            # Instant: already decoded (prefetched or revisited).
            self._cache.move_to_end(path_str)
            self._current_path = path_str
            self._pixmap = QPixmap.fromImage(cached)
            self._placeholder_text = ""
            self.update()
            return

        self._current_path = None
        # Show the cached thumbnail instantly (blurry); the sharp preview replaces
        # it as soon as the decode finishes.
        self._pixmap = self._cached_placeholder(path)
        self._placeholder_text = "" if self._pixmap else "Loading…"
        self.update()
        self._start_task(path_str)

    def prefetch(self, paths: List[Path]):
        """Decode these previews in the background so navigating to them is instant."""
        for p in paths:
            self._start_task(str(p))

    def _start_task(self, path_str: str):
        if path_str in self._cache or path_str in self._inflight:
            return
        self._inflight.add(path_str)
        self._pool.start(_PreviewTask(path_str, self._signals))

    def _cache_put(self, path_str: str, qimg: QImage):
        self._cache[path_str] = qimg
        self._cache.move_to_end(path_str)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _cached_placeholder(self, path: Path) -> Optional[QPixmap]:
        from image_loader import get_cached_thumbnail
        img = get_cached_thumbnail(path)
        if img is None:
            return None
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height,
                      img.width * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    def set_metadata(self, rating: int, color_label: Optional[str], flag: str,
                     rotation: int = 0):
        self._rating = rating
        self._color_label = color_label
        self._flag = flag
        self._rotation = rotation % 360
        self.update()

    def _display_pixmap(self) -> Optional[QPixmap]:
        """The current pixmap with the user's display rotation applied (cached)."""
        if self._pixmap is None or not self._rotation:
            return self._pixmap
        key = (self._pixmap.cacheKey(), self._rotation)
        if self._rot_key != key:
            self._rot_pixmap = self._pixmap.transformed(
                QTransform().rotate(self._rotation),
                Qt.TransformationMode.SmoothTransformation)
            self._rot_key = key
        return self._rot_pixmap

    def clear(self):
        self._pixmap = None
        self._current_path = None
        self._loading_path = None
        self._cache.clear()
        self._inflight.clear()
        self._placeholder_text = "Open a folder to begin  (⌘O)"
        self.update()

    def _on_loaded(self, path_str: str, qimg: QImage):
        self._inflight.discard(path_str)
        self._cache_put(path_str, qimg)
        # Only paint it if it's the image the user is currently on (a prefetch
        # result just sits in the cache until navigated to).
        if path_str == self._loading_path:
            self._current_path = path_str
            self._pixmap = QPixmap.fromImage(qimg)
            self._placeholder_text = ""
            self.update()

    def _on_failed(self, path_str: str):
        self._inflight.discard(path_str)
        if path_str == self._loading_path:
            self._placeholder_text = "Could not load image"
            self._pixmap = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(18, 18, 20))

        display = self._display_pixmap()
        if display:
            scaled = display.scaled(
                w, h - 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - 40 - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(99, 99, 102))
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        # Overlay bar at bottom
        bar_y = h - 36
        painter.fillRect(0, bar_y, w, 36, QColor(28, 28, 30, 235))

        # Stars
        star_font = QFont()
        star_font.setPointSize(14)
        painter.setFont(star_font)
        for i in range(5):
            if i < self._rating:
                painter.setPen(QColor(255, 214, 10))
                painter.drawText(12 + i * 22, bar_y + 24, "★")
            else:
                painter.setPen(QColor(72, 72, 74))
                painter.drawText(12 + i * 22, bar_y + 24, "☆")

        # Flag badge
        flag_text = FLAG_LABELS.get(self._flag, "")
        if flag_text:
            flag_color = QColor(FLAG_COLORS.get(self._flag, "#555"))
            badge_x = 130
            badge_w = 60
            painter.fillRect(badge_x, bar_y + 6, badge_w, 22, flag_color)
            painter.setPen(QColor(255, 255, 255))
            badge_font = QFont()
            badge_font.setPointSize(9)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            from PyQt6.QtCore import QRect
            painter.drawText(QRect(badge_x, bar_y + 6, badge_w, 22),
                             Qt.AlignmentFlag.AlignCenter, flag_text)

        # Color label dot
        if self._color_label and self._color_label in COLOR_MAP:
            dot_x = 200
            dot_size = 16
            painter.setBrush(QColor(COLOR_MAP[self._color_label]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dot_x, bar_y + 10, dot_size, dot_size)
            label_font = QFont()
            label_font.setPointSize(9)
            painter.setFont(label_font)
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(dot_x + 22, bar_y + 24, self._color_label.capitalize())

    def closeEvent(self, event):
        self._pool.clear()
        self._pool.waitForDone(1000)
        super().closeEvent(event)

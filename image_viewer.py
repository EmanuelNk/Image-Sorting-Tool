from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont


COLOR_MAP = {
    "red": "#c0392b",
    "yellow": "#d4ac0d",
    "green": "#1e8449",
    "blue": "#1a5276",
    "purple": "#6c3483",
}

FLAG_COLORS = {
    "pick": "#3498db",
    "reject": "#e74c3c",
    "unflagged": "#555555",
}

FLAG_LABELS = {"pick": "PICK", "reject": "REJECT", "unflagged": ""}


class _LoadWorker(QObject):
    load_requested = pyqtSignal(str)
    done = pyqtSignal(str, QImage)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.load_requested.connect(self._do_load)

    @pyqtSlot(str)
    def _do_load(self, path_str: str):
        from image_loader import load_full
        img = load_full(Path(path_str))
        if img is None:
            self.failed.emit(path_str)
            return
        img = img.convert("RGB")
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
        self.done.emit(path_str, qimg.copy())


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

        # Background worker thread
        self._thread = QThread()
        self._worker = _LoadWorker()
        self._worker.moveToThread(self._thread)
        self._worker.done.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

        self._placeholder_text = "Open a folder to begin  (⌘O)"

    def load_image(self, path: Path):
        path_str = str(path)
        if path_str == self._current_path:
            return
        self._loading_path = path_str
        self._pixmap = None
        self._placeholder_text = "Loading…"
        self.update()
        # Signal is connected with QueuedConnection across threads
        self._worker.load_requested.emit(path_str)

    def set_metadata(self, rating: int, color_label: Optional[str], flag: str):
        self._rating = rating
        self._color_label = color_label
        self._flag = flag
        self.update()

    def clear(self):
        self._pixmap = None
        self._current_path = None
        self._loading_path = None
        self._placeholder_text = "Open a folder to begin  (⌘O)"
        self.update()

    def _on_loaded(self, path_str: str, qimg: QImage):
        if path_str != self._loading_path:
            return
        self._current_path = path_str
        self._pixmap = QPixmap.fromImage(qimg)
        self._placeholder_text = ""
        self.update()

    def _on_failed(self, path_str: str):
        if path_str == self._loading_path:
            self._placeholder_text = "Could not load image"
            self._pixmap = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(15, 15, 15))

        if self._pixmap:
            scaled = self._pixmap.scaled(
                w, h - 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - 40 - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(80, 80, 80))
            font = QFont()
            font.setPointSize(16)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        # Overlay bar at bottom
        bar_y = h - 36
        painter.fillRect(0, bar_y, w, 36, QColor(20, 20, 20, 220))

        # Stars
        star_font = QFont()
        star_font.setPointSize(14)
        painter.setFont(star_font)
        for i in range(5):
            if i < self._rating:
                painter.setPen(QColor(255, 200, 0))
                painter.drawText(12 + i * 22, bar_y + 24, "★")
            else:
                painter.setPen(QColor(55, 55, 55))
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
        self._thread.quit()
        self._thread.wait(1000)
        super().closeEvent(event)

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer


class LoadingOverlay(QWidget):
    """A small floating pill, centered near the top of its parent, showing
    thumbnail-loading progress with a percentage. Click-through (does not block
    the thumbnails beneath it) and auto-hides shortly after loading completes."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("""
            QWidget#pill {
                background: rgba(28, 28, 30, 235);
                border: 1px solid #3A3A3C;
                border-radius: 11px;
            }
            QLabel { color: rgba(235,235,245,0.85); font-size: 11px; }
            QProgressBar {
                background: #2C2C2E; border: none; border-radius: 3px;
                height: 6px; max-height: 6px;
            }
            QProgressBar::chunk { background: #0A84FF; border-radius: 3px; }
        """)
        self._pill = QWidget(self)
        self._pill.setObjectName("pill")
        layout = QHBoxLayout(self._pill)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(10)

        self._label = QLabel("Loading…")
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(120)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def set_progress(self, loaded: int, total: int):
        if total <= 0:
            self.hide()
            return
        if loaded >= total:
            # Snap to 100%, then auto-hide a moment later.
            self._label.setText("Loaded")
            self._bar.setMaximum(total)
            self._bar.setValue(total)
            self._reposition()
            self._hide_timer.start(500)
            return

        self._hide_timer.stop()
        pct = int(loaded * 100 / total)
        self._label.setText(f"Loading previews  {pct}%")
        self._bar.setMaximum(total)
        self._bar.setValue(loaded)
        self._reposition()
        if not self.isVisible():
            self.show()
        self.raise_()

    def _reposition(self):
        self._pill.adjustSize()
        self.resize(self._pill.size())
        parent = self.parentWidget()
        if parent is not None:
            x = (parent.width() - self.width()) // 2
            self.move(max(0, x), 12)

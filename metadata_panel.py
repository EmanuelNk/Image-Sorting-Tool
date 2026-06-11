from pathlib import Path
from typing import Optional, Dict

from PyQt6.QtWidgets import (QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
                              QLabel, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor

from image_loader import get_all_metadata


class _MetaWorker(QObject):
    loaded = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self):
        result = get_all_metadata(self._path)
        self.loaded.emit(result)
        self.finished.emit()


# ── section/field layout helpers ─────────────────────────────────────────────

_SECTION_STYLE = "color: rgba(235,235,245,0.4); font-size: 9px; letter-spacing: 1.2px; margin-top: 10px; margin-bottom: 2px;"
_KEY_STYLE     = "color: rgba(235,235,245,0.35); font-size: 9px;"
_VAL_STYLE     = "color: rgba(235,235,245,0.85); font-size: 11px; word-wrap: break-all;"

_LABEL_COLORS = {
    "red": "#FF453A", "yellow": "#FFD60A", "green": "#30D158",
    "blue": "#0A84FF", "purple": "#BF5AF2",
}
_FLAG_COLORS = {"pick": "#30D158", "reject": "#FF453A", "unflagged": "#48484A"}


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(_SECTION_STYLE)
    lbl.setFont(QFont())
    return lbl


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #3A3A3C; margin: 0;")
    return line


class _FieldRow(QWidget):
    def __init__(self, key: str, val: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(1)

        k = QLabel(key)
        k.setStyleSheet(_KEY_STYLE)
        layout.addWidget(k)

        v = QLabel(val)
        v.setStyleSheet(_VAL_STYLE)
        v.setWordWrap(True)
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(v)


# ── main panel widget ─────────────────────────────────────────────────────────

class MetadataPanelWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #1C1C1E;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QLabel("  INFO")
        header.setFixedHeight(26)
        header.setStyleSheet(
            "background: #2C2C2E; color: rgba(235,235,245,0.4); font-size: 9px; "
            "letter-spacing: 1.5px; border-bottom: 1px solid #3A3A3C;"
        )
        outer.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #1C1C1E; }
            QScrollBar:vertical {
                background: #2C2C2E; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #48484A; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        outer.addWidget(scroll, 1)

        self._content = QWidget()
        self._content.setStyleSheet("background: #1C1C1E;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(10, 6, 10, 16)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        scroll.setWidget(self._content)

        self._thread: Optional[QThread] = None
        self._worker: Optional[_MetaWorker] = None
        self._current_path: Optional[Path] = None
        self._last_meta: Dict = {}

        self._loading_label = QLabel("Loading…")
        self._loading_label.setStyleSheet("color: rgba(235,235,245,0.25); font-size: 11px; padding: 16px;")

    # ── public API ────────────────────────────────────────────────────────────

    def load(self, path: Path, store_entry: dict):
        """Load full metadata for path asynchronously. Overlay store_entry labels."""
        self._current_path = path
        self._last_meta = dict(store_entry)
        self._show_loading()
        self._start_worker(path)

    def update_labels(self, store_entry: dict):
        """Refresh only the rating/flag/label section (no file I/O)."""
        self._last_meta.update(store_entry)
        if self._last_meta:
            self._last_meta["rating"]      = store_entry.get("rating", 0)
            self._last_meta["flag"]        = store_entry.get("flag", "unflagged")
            self._last_meta["color_label"] = store_entry.get("color_label")
            # Only re-render if we already have file metadata (not still loading)
            if self._layout.count() > 1:
                self._render(self._last_meta)

    def clear(self):
        self._current_path = None
        self._last_meta = {}
        self._clear_layout()

    # ── worker management ─────────────────────────────────────────────────────

    def _start_worker(self, path: Path):
        # Cancel any in-flight worker
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(500)

        self._thread = QThread()
        self._worker = _MetaWorker(path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_loaded(self, meta: dict):
        # Only display if this result still matches the current path
        if self._current_path and meta.get("filename") == self._current_path.name:
            meta["rating"]      = self._last_meta.get("rating", 0)
            meta["flag"]        = self._last_meta.get("flag", "unflagged")
            meta["color_label"] = self._last_meta.get("color_label")
            self._last_meta = meta
            self._render(meta)

    # ── rendering ─────────────────────────────────────────────────────────────

    def _show_loading(self):
        self._clear_layout()
        self._layout.insertWidget(0, self._loading_label)
        self._loading_label.setVisible(True)

    def _clear_layout(self):
        self._loading_label.setParent(None)
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render(self, meta: dict):
        self._clear_layout()

        def section(title: str):
            self._layout.addWidget(_section_label(title))
            self._layout.addWidget(_divider())

        def field(key: str, val, allow_zero=False):
            if val is None or val == "":
                return
            sv = str(val).strip()
            if not sv or sv in ("unflagged", "None"):
                return
            if sv == "0" and not allow_zero:
                return
            self._layout.addWidget(_FieldRow(key, sv))

        # ── FILE ──────────────────────────────────────────────────────────────
        section("File")
        field("Filename",      meta.get("filename"))
        field("Size",          meta.get("file_size"))
        field("Dimensions",    meta.get("dimensions"))
        field("Date Taken",    meta.get("date_taken"))
        field("Date Modified", meta.get("date_modified"))

        # ── CAMERA ────────────────────────────────────────────────────────────
        camera_fields = [
            ("Make",          meta.get("make")),
            ("Model",         meta.get("model")),
            ("Lens",          meta.get("lens_model")),
            ("Lens Make",     meta.get("lens_make")),
            ("Serial Number", meta.get("serial_number")),
            ("Software",      meta.get("software")),
        ]
        if any(v for _, v in camera_fields):
            section("Camera")
            for k, v in camera_fields:
                field(k, v)

        # ── EXPOSURE ──────────────────────────────────────────────────────────
        exp_fields = [
            ("ISO",             meta.get("iso")),
            ("Aperture",        meta.get("fnumber")),
            ("Shutter Speed",   meta.get("exposure_time")),
            ("Focal Length",    meta.get("focal_length")),
            ("35mm Equiv.",     meta.get("focal_length_35mm")),
            ("Exp. Bias",       meta.get("exposure_bias")),
            ("White Balance",   meta.get("white_balance")),
            ("WB Shift",        meta.get("wb_shift")),
            ("Metering",        meta.get("metering_mode")),
            ("Exposure Mode",   meta.get("exposure_mode")),
            ("Flash",           meta.get("flash")),
            ("Scene Type",      meta.get("scene_type")),
            ("Color Space",     meta.get("color_space")),
        ]
        if any(v for _, v in exp_fields):
            section("Exposure")
            for k, v in exp_fields:
                field(k, v)

        # ── FILM / STYLE ──────────────────────────────────────────────────────
        film_fields = [
            ("Film Simulation",  meta.get("film_simulation")),
            ("Film Recipe",      meta.get("film_recipe")),
            ("Dynamic Range",    meta.get("dynamic_range")),
            ("Highlight Tone",   meta.get("highlight_tone")),
            ("Shadow Tone",      meta.get("shadow_tone")),
            ("Color",            meta.get("color_saturation")),
            ("Sharpness",        meta.get("sharpness")),
            ("Noise Reduction",  meta.get("noise_reduction")),
            ("Grain",            meta.get("grain_effect")),
            ("Grain Size",       meta.get("grain_effect_size")),
            ("Color Chrome",     meta.get("color_chrome")),
            ("Color Chrome Blue",meta.get("color_chrome_blue")),
        ]
        clarity = meta.get("clarity")
        has_film = any(v for _, v in film_fields) or clarity is not None
        if has_film:
            section("Film / Style")
            for k, v in film_fields:
                field(k, v)
            if clarity is not None:
                field("Clarity", clarity, allow_zero=True)

        # ── LABELS ────────────────────────────────────────────────────────────
        section("Labels")
        self._render_labels(meta)

        # ── CREATOR ───────────────────────────────────────────────────────────
        creator_fields = [
            ("Creator",     meta.get("creator")),
            ("Copyright",   meta.get("copyright")),
            ("Title",       meta.get("title")),
            ("Description", meta.get("description")),
            ("Keywords",    meta.get("keywords")),
        ]
        if any(v for _, v in creator_fields):
            section("Creator")
            for k, v in creator_fields:
                field(k, v)

        # ── GPS ───────────────────────────────────────────────────────────────
        if meta.get("gps"):
            section("GPS")
            field("Location",  meta.get("gps"))
            field("Altitude",  meta.get("gps_altitude"))

        # ── EXTRA ─────────────────────────────────────────────────────────────
        extra = meta.get("_extra")
        if extra:
            section("Extra")
            for k, v in list(extra.items())[:40]:  # cap at 40 to avoid overwhelming
                field(k, v)

        self._layout.addStretch()

    def _render_labels(self, meta: dict):
        rating      = meta.get("rating", 0)
        flag        = meta.get("flag", "unflagged")
        color_label = meta.get("color_label")

        # Stars row
        stars_w = QWidget()
        stars_l = QHBoxLayout(stars_w)
        stars_l.setContentsMargins(0, 2, 0, 4)
        stars_l.setSpacing(2)
        key_lbl = QLabel("Rating")
        key_lbl.setStyleSheet(_KEY_STYLE)
        self._layout.addWidget(key_lbl)

        stars_row = QWidget()
        sr_layout = QHBoxLayout(stars_row)
        sr_layout.setContentsMargins(0, 0, 0, 4)
        sr_layout.setSpacing(1)
        for i in range(5):
            s = QLabel("★" if i < rating else "☆")
            s.setStyleSheet(f"color: {'#FFD60A' if i < rating else '#48484A'}; font-size: 14px;")
            sr_layout.addWidget(s)
        sr_layout.addStretch()
        self._layout.addWidget(stars_row)

        # Flag row
        flag_k = QLabel("Flag")
        flag_k.setStyleSheet(_KEY_STYLE)
        self._layout.addWidget(flag_k)
        flag_v = QLabel(flag.capitalize())
        flag_v.setStyleSheet(f"color: {_FLAG_COLORS.get(flag, '#555')}; font-size: 11px; margin-bottom: 4px;")
        self._layout.addWidget(flag_v)

        # Color label row
        color_k = QLabel("Color Label")
        color_k.setStyleSheet(_KEY_STYLE)
        self._layout.addWidget(color_k)
        if color_label:
            color_v = QLabel(color_label.capitalize())
            color_hex = _LABEL_COLORS.get(color_label, "#555")
            color_v.setStyleSheet(
                f"color: {color_hex}; font-size: 11px; margin-bottom: 4px;"
            )
        else:
            color_v = QLabel("None")
            color_v.setStyleSheet("color: rgba(235,235,245,0.2); font-size: 11px; margin-bottom: 4px;")
        self._layout.addWidget(color_v)

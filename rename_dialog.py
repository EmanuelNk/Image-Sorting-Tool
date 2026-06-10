"""
Batch rename dialog.

Pattern tokens:
  {orig}       original filename without extension
  {n}          sequence number (default format)
  {n:04d}      sequence number with zero-padding (any Python int format)
  {date}       YYYY-MM-DD from EXIF DateTimeOriginal, or file mtime
  {camera}     camera model from EXIF
  {folder}     parent folder name
"""
import re
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QPushButton,
    QMessageBox, QHeaderView,
)
from PyQt6.QtCore import Qt

_TOKEN_RE = re.compile(r"\{(\w+(?::[^}]+)?)\}")


def _build_name(pattern: str, orig: str, n: int, date: str,
                camera: str, folder: str, ext: str) -> str:
    """Expand pattern tokens and append extension."""
    result = pattern

    def replace_token(m):
        token = m.group(1)
        if token == "orig":
            return orig
        if token == "n":
            return str(n)
        if token.startswith("n:"):
            fmt = token[2:]
            try:
                return format(n, fmt)
            except (ValueError, TypeError):
                return str(n)
        if token == "date":
            return date or "nodate"
        if token == "camera":
            return camera or "unknown"
        if token == "folder":
            return folder
        return m.group(0)  # unknown token — keep as-is

    result = _TOKEN_RE.sub(replace_token, result)
    # Sanitise: replace path separators
    result = result.replace("/", "_").replace("\\", "_")
    return result + ext


def _get_image_info(path: Path, exif_cache: dict) -> Tuple[str, str]:
    """Return (date_str YYYY-MM-DD, camera_model)."""
    key = str(path)
    if key not in exif_cache:
        try:
            from image_loader import get_exif
            exif_cache[key] = get_exif(path)
        except Exception:
            exif_cache[key] = {}
    exif = exif_cache.get(key, {})

    # Date
    date_raw = exif.get("date_taken", "")
    date_str = ""
    if date_raw:
        # Normalise "2026:05:11 12:04:48" → "2026-05-11"
        date_str = date_raw[:10].replace(":", "-")
    if not date_str:
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(path.stat().st_mtime)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = "nodate"

    # Camera
    model = exif.get("model", "") or exif.get("make", "")
    camera = model.strip().replace(" ", "-") if model else ""

    return date_str, camera


class BatchRenameDialog(QDialog):
    def __init__(self, paths: List[Path], exif_cache: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Rename")
        self.setModal(True)
        self.setMinimumSize(600, 440)
        self.setStyleSheet("""
            QDialog { background: #252525; color: #ccc; }
            QLabel  { color: #ccc; font-size: 12px; }
            QLineEdit, QSpinBox {
                background: #2a2a2a; color: #ccc; border: 1px solid #444;
                border-radius: 3px; padding: 3px 6px; font-size: 12px;
            }
            QTableWidget {
                background: #1e1e1e; color: #ccc; border: 1px solid #333;
                gridline-color: #333; font-size: 11px;
            }
            QHeaderView::section {
                background: #2a2a2a; color: #aaa; border: none;
                padding: 4px; font-size: 11px;
            }
            QPushButton {
                background: #2e2e2e; color: #ccc; border: 1px solid #444;
                border-radius: 3px; padding: 5px 14px; font-size: 12px;
            }
            QPushButton:hover { background: #3a3a3a; }
            QPushButton#apply_btn {
                background: #1a4080; color: #fff; border-color: #2060b0;
            }
            QPushButton#apply_btn:hover { background: #1e50a0; }
        """)

        self._paths = paths
        self._exif_cache = dict(exif_cache)
        self.result_pairs: List[Tuple[Path, Path]] = []

        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Pattern row
        pat_row = QHBoxLayout()
        pat_row.addWidget(QLabel("Pattern:"))
        self._pattern = QLineEdit("{orig}_{n:04d}")
        self._pattern.setToolTip(
            "Tokens: {orig} {n} {n:04d} {date} {camera} {folder}"
        )
        self._pattern.textChanged.connect(self._update_preview)
        pat_row.addWidget(self._pattern, 1)
        layout.addLayout(pat_row)

        # Start number row
        num_row = QHBoxLayout()
        num_row.addWidget(QLabel("Start number:"))
        self._start_spin = QSpinBox()
        self._start_spin.setRange(0, 99999)
        self._start_spin.setValue(1)
        self._start_spin.setFixedWidth(80)
        self._start_spin.valueChanged.connect(self._update_preview)
        num_row.addWidget(self._start_spin)
        num_row.addStretch()
        layout.addLayout(num_row)

        # Preview table
        layout.addWidget(QLabel("Preview:"))
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Original Name", "New Name"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self._table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        apply_btn = QPushButton("Rename")
        apply_btn.setObjectName("apply_btn")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    def _compute_new_name(self, path: Path, index: int) -> str:
        pattern = self._pattern.text()
        n = self._start_spin.value() + index
        orig = path.stem
        ext = path.suffix
        folder = path.parent.name
        date_str, camera = _get_image_info(path, self._exif_cache)
        return _build_name(pattern, orig, n, date_str, camera, folder, ext)

    def _update_preview(self):
        self._table.setRowCount(len(self._paths))
        for i, path in enumerate(self._paths):
            new_name = self._compute_new_name(path, i)
            old_item = QTableWidgetItem(path.name)
            new_item = QTableWidgetItem(new_name)
            # Highlight conflicts in red
            target = path.parent / new_name
            if target.exists() and target != path:
                from PyQt6.QtGui import QColor
                new_item.setForeground(QColor(231, 76, 60))
                new_item.setToolTip("Conflict: file already exists")
            self._table.setItem(i, 0, old_item)
            self._table.setItem(i, 1, new_item)

    def _apply(self):
        pattern = self._pattern.text()
        if not pattern.strip():
            QMessageBox.warning(self, "Empty Pattern", "Please enter a rename pattern.")
            return

        pairs: List[Tuple[Path, Path]] = []
        conflicts: List[str] = []

        for i, path in enumerate(self._paths):
            new_name = self._compute_new_name(path, i)
            target = path.parent / new_name
            if target.exists() and target != path:
                conflicts.append(f"{path.name} → {new_name} (already exists)")
            else:
                pairs.append((path, target))

        if conflicts:
            msg = "The following renames would conflict:\n" + "\n".join(conflicts)
            msg += "\n\nProceed with the non-conflicting renames?"
            if QMessageBox.question(
                self, "Conflicts Found", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            ) != QMessageBox.StandardButton.Yes:
                return

        failed: List[str] = []
        done: List[Tuple[Path, Path]] = []
        for src, dst in pairs:
            try:
                src.rename(dst)
                done.append((src, dst))
            except OSError as e:
                failed.append(f"{src.name}: {e}")

        if failed:
            QMessageBox.warning(self, "Some Renames Failed", "\n".join(failed))

        self.result_pairs = done
        self.accept()

"""
Collections store: virtual groupings of images (paths stored as absolute strings).

Types:
  - regular: manually curated, paths stored in QSettings
  - smart:   auto-populated by rule dict
  - auto:    pre-created smart collections, cannot be deleted
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import QSettings

# ── Auto-collections (pre-created, undeletable) ───────────────────────────────

_AUTO = [
    ("picks",      "Picks",      "smart", {"flag": "pick"}),
    ("rejects",    "Rejects",    "smart", {"flag": "reject"}),
    ("5stars",     "5 Stars",    "smart", {"rating_min": 5}),
    ("4stars",     "4+ Stars",   "smart", {"rating_min": 4}),
    ("3stars",     "3+ Stars",   "smart", {"rating_min": 3}),
    ("this_month", "This Month", "smart", {"date_filter": "this_month"}),
]

_AUTO_IDS = {row[0] for row in _AUTO}


class CollectionsStore:
    """
    Persists collections in QSettings.

    Each collection is a dict:
      {
        "id":    str  (unique, stable),
        "name":  str,
        "type":  "regular" | "smart" | "auto",
        "rule":  dict  (for smart/auto),
        "paths": list[str]  (for regular only),
      }
    """

    def __init__(self, settings: QSettings):
        self._settings = settings
        self._collections: List[Dict[str, Any]] = []
        self._load()

    # ── public API ─────────────────────────────────────────────────────────────

    def all(self) -> List[Dict[str, Any]]:
        return list(self._collections)

    def get(self, cid: str) -> Optional[Dict[str, Any]]:
        for c in self._collections:
            if c["id"] == cid:
                return dict(c)
        return None

    def add_regular(self, name: str) -> str:
        cid = str(uuid.uuid4())
        self._collections.append({"id": cid, "name": name, "type": "regular", "paths": []})
        self._save()
        return cid

    def add_smart(self, name: str, rule_dict: dict) -> str:
        cid = str(uuid.uuid4())
        self._collections.append({"id": cid, "name": name, "type": "smart", "rule": rule_dict})
        self._save()
        return cid

    def remove(self, cid: str):
        if cid in _AUTO_IDS:
            return  # auto-collections cannot be deleted
        self._collections = [c for c in self._collections if c["id"] != cid]
        self._save()

    def add_paths(self, cid: str, paths: List[Path]):
        for c in self._collections:
            if c["id"] == cid and c["type"] == "regular":
                existing = set(c["paths"])
                for p in paths:
                    s = str(p)
                    if s not in existing:
                        c["paths"].append(s)
                        existing.add(s)
                self._save()
                return

    def remove_paths(self, cid: str, paths: List[Path]):
        remove_set = {str(p) for p in paths}
        for c in self._collections:
            if c["id"] == cid and c["type"] == "regular":
                c["paths"] = [p for p in c["paths"] if p not in remove_set]
                self._save()
                return

    def resolve_regular(self, cid: str) -> List[Path]:
        c = self.get(cid)
        if c is None or c["type"] != "regular":
            return []
        return [Path(p) for p in c.get("paths", []) if Path(p).exists()]

    def resolve_smart(self, cid: str, all_images: List[Path],
                      metadata) -> List[Path]:
        """Filter all_images by the smart rule for collection cid."""
        c = self.get(cid)
        if c is None or c["type"] not in ("smart", "auto"):
            return []
        rule = c.get("rule", {})
        return _apply_rule(rule, all_images, metadata)

    # ── persistence ────────────────────────────────────────────────────────────

    def _load(self):
        raw = self._settings.value("collections", None)
        if raw is None:
            self._collections = []
        else:
            try:
                if isinstance(raw, list):
                    self._collections = raw
                else:
                    self._collections = []
            except Exception:
                self._collections = []

        # Ensure all auto-collections are present (in order, at the top)
        existing_ids = {c["id"] for c in self._collections}
        auto_entries = []
        for cid, name, ctype, rule in _AUTO:
            if cid not in existing_ids:
                auto_entries.append({
                    "id": cid, "name": name, "type": "auto", "rule": rule
                })
        self._collections = auto_entries + self._collections

    def _save(self):
        # Only persist non-auto entries to avoid duplicating them on reload
        to_save = [c for c in self._collections if c["id"] not in _AUTO_IDS]
        self._settings.setValue("collections", to_save)


# ── rule evaluation ────────────────────────────────────────────────────────────

def _apply_rule(rule: dict, images: List[Path], metadata) -> List[Path]:
    from image_loader import get_exif  # local import to avoid circular

    rating_min = rule.get("rating_min")
    flag_filter = rule.get("flag")
    label_filter = rule.get("label")
    date_filter = rule.get("date_filter")

    now = datetime.now()
    result = []

    for p in images:
        if rating_min is not None:
            if metadata.get_rating(p) < rating_min:
                continue
        if flag_filter is not None:
            if metadata.get_flag(p) != flag_filter:
                continue
        if label_filter is not None:
            if metadata.get_color_label(p) != label_filter:
                continue
        if date_filter == "this_month":
            if not _is_this_month(p, now):
                continue
        elif date_filter == "this_year":
            if not _is_this_year(p, now):
                continue
        result.append(p)

    return result


def _parse_exif_date(date_str: str) -> Optional[datetime]:
    """Parse EXIF date string like '2026:05:11 12:04:48'."""
    try:
        return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except Exception:
            return None


def _image_date(p: Path, now: datetime) -> datetime:
    """Get the best available date for an image (EXIF > mtime)."""
    try:
        from image_loader import get_exif
        exif = get_exif(p)
        date_str = exif.get("date_taken", "")
        if date_str:
            dt = _parse_exif_date(date_str)
            if dt:
                return dt
    except Exception:
        pass
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except Exception:
        return now


def _is_this_month(p: Path, now: datetime) -> bool:
    dt = _image_date(p, now)
    return dt.year == now.year and dt.month == now.month


def _is_this_year(p: Path, now: datetime) -> bool:
    dt = _image_date(p, now)
    return dt.year == now.year

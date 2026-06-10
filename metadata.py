"""
Metadata store using embedded XMP (JPEG) or XMP sidecar files (everything else).

JPEG  → XMP written into the file's APP1 marker, exactly as Lightroom does.
Other → <stem>.xmp sidecar written alongside the file (RAW, PNG, HEIC, TIFF…).

XMP fields:
  xmp:Rating      0-5 stars; -1 = rejected (Lightroom convention)
  xmp:Label       "Red" | "Yellow" | "Green" | "Blue" | "Purple"
  lr:pickStatus   1 = pick | -1 = reject | 0 = unflagged
"""
import json
import os
import struct
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict

_DEFAULT: dict = {"rating": 0, "color_label": None, "flag": "unflagged"}

_LABEL_TO_XMP: dict = {
    "red": "Red", "yellow": "Yellow", "green": "Green",
    "blue": "Blue", "purple": "Purple",
}
_XMP_TO_LABEL: dict = {v.lower(): k for k, v in _LABEL_TO_XMP.items()}

_XMP_NS  = "http://ns.adobe.com/xap/1.0/"
_RDF_NS  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_LR_NS   = "http://ns.adobe.com/lightroom/1.0/"

_JPEG_EXTS = {".jpg", ".jpeg"}
_XMP_SIG   = b"http://ns.adobe.com/xap/1.0/\x00"


class MetadataStore:
    def __init__(self):
        self._folder: Optional[Path] = None
        self._cache: Dict[str, dict] = {}

    def load_folder(self, folder: Path):
        self._folder = folder
        self._cache = {}
        self._migrate_json(folder)

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, filename: str) -> dict:
        if filename not in self._cache:
            self._cache[filename] = self._read(filename)
        return dict(self._cache[filename])

    def get_rating(self, filename: str) -> int:
        return self.get(filename).get("rating", 0)

    def get_color_label(self, filename: str) -> Optional[str]:
        return self.get(filename).get("color_label")

    def get_flag(self, filename: str) -> str:
        return self.get(filename).get("flag", "unflagged")

    def set_rating(self, filename: str, rating: int):
        entry = self.get(filename)
        entry["rating"] = max(0, min(5, rating))
        self._update(filename, entry)

    def set_color_label(self, filename: str, color: Optional[str]):
        entry = self.get(filename)
        entry["color_label"] = color
        self._update(filename, entry)

    def set_flag(self, filename: str, flag: str):
        entry = self.get(filename)
        entry["flag"] = flag
        self._update(filename, entry)

    def remove(self, filename: str):
        """Clear metadata when an image is moved out of this folder."""
        self._cache.pop(filename, None)
        # Remove sidecar if one exists
        xmp = self._sidecar_path(filename)
        try:
            if xmp.exists():
                xmp.unlink()
        except OSError:
            pass

    def import_entry(self, filename: str, entry: dict):
        """Copy a full metadata dict into this folder (used on image move)."""
        self._update(filename, entry)

    # ── routing ───────────────────────────────────────────────────────────────

    def _is_jpeg(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in _JPEG_EXTS

    def _sidecar_path(self, filename: str) -> Path:
        return self._folder / (Path(filename).stem + ".xmp")

    def _update(self, filename: str, entry: dict):
        self._cache[filename] = entry
        self._write(filename, entry)

    # ── reading ───────────────────────────────────────────────────────────────

    def _read(self, filename: str) -> dict:
        if self._is_jpeg(filename):
            # Embedded XMP is canonical for JPEGs
            img = self._folder / filename
            if img.exists():
                result = self._read_jpeg_xmp(img)
                if self._is_non_default(result):
                    return result
            # Fall back to sidecar (handles migration from old app version)
            xmp = self._sidecar_path(filename)
            if xmp.exists():
                try:
                    return self._parse_xmp(xmp.read_text(encoding="utf-8"))
                except Exception:
                    pass
        else:
            xmp = self._sidecar_path(filename)
            if xmp.exists():
                try:
                    return self._parse_xmp(xmp.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return dict(_DEFAULT)

    def _is_non_default(self, entry: dict) -> bool:
        return (entry.get("rating", 0) != 0
                or entry.get("color_label") is not None
                or entry.get("flag", "unflagged") != "unflagged")

    def _read_jpeg_xmp(self, path: Path) -> dict:
        data = path.read_bytes()
        idx = data.find(_XMP_SIG)
        if idx == -1:
            return dict(_DEFAULT)
        start = idx + len(_XMP_SIG)
        end = data.find(b"<?xpacket end", start)
        end = (data.find(b"?>", end) + 2) if end != -1 else min(start + 65536, len(data))
        return self._parse_xmp(data[start:end].decode("utf-8", errors="replace"))

    def _parse_xmp(self, xml_text: str) -> dict:
        result = dict(_DEFAULT)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return result

        for desc in root.iter(f"{{{_RDF_NS}}}Description"):
            r_str = desc.get(f"{{{_XMP_NS}}}Rating")
            l_str = desc.get(f"{{{_XMP_NS}}}Label", "")
            p_str = desc.get(f"{{{_LR_NS}}}pickStatus", "")

            for child in desc:
                tag, text = child.tag, (child.text or "").strip()
                if not text:
                    continue
                if tag == f"{{{_XMP_NS}}}Rating":
                    r_str = text
                elif tag == f"{{{_XMP_NS}}}Label":
                    l_str = text
                elif tag == f"{{{_LR_NS}}}pickStatus":
                    p_str = text

            if p_str:
                try:
                    ps = int(p_str)
                    if ps == 1:
                        result["flag"] = "pick"
                    elif ps == -1:
                        result["flag"] = "reject"
                except ValueError:
                    pass

            if r_str is not None:
                try:
                    r = int(r_str)
                    if r == -1:
                        result["flag"] = "reject"
                        result["rating"] = 0
                    else:
                        result["rating"] = max(0, min(5, r))
                except ValueError:
                    pass

            if l_str:
                result["color_label"] = _XMP_TO_LABEL.get(l_str.strip().lower())

        return result

    # ── writing ───────────────────────────────────────────────────────────────

    def _write(self, filename: str, entry: dict):
        if not self._folder:
            return

        if self._is_jpeg(filename):
            img = self._folder / filename
            if not img.exists():
                return
            is_default = not self._is_non_default(entry)
            xmp_xml = None if is_default else self._build_xmp_xml(entry)
            try:
                original = img.read_bytes()
                modified = self._embed_xmp_jpeg(original, xmp_xml)
                if modified != original:
                    self._atomic_write(img, modified)
            except Exception:
                # Fallback: write sidecar if JPEG embedding fails
                self._write_sidecar(filename, entry)
        else:
            self._write_sidecar(filename, entry)

    def _write_sidecar(self, filename: str, entry: dict):
        xmp_path = self._sidecar_path(filename)
        if not self._is_non_default(entry):
            try:
                if xmp_path.exists():
                    xmp_path.unlink()
            except OSError:
                pass
            return
        try:
            xmp_path.write_text(self._build_xmp_xml(entry), encoding="utf-8")
        except OSError:
            pass

    def _build_xmp_xml(self, entry: dict) -> str:
        rating      = entry.get("rating", 0)
        color_label = entry.get("color_label")
        flag        = entry.get("flag", "unflagged")

        xmp_rating  = -1 if flag == "reject" else rating
        pick_status = {"pick": "1", "reject": "-1", "unflagged": "0"}[flag]
        label_str   = _LABEL_TO_XMP.get(color_label, "") if color_label else ""

        attrs = [f'xmp:Rating="{xmp_rating}"']
        if label_str:
            attrs.append(f'xmp:Label="{label_str}"')
        if flag != "unflagged":
            attrs.append(f'lr:pickStatus="{pick_status}"')

        attrs_block = "\n      ".join(attrs)

        # ﻿ is the BOM character Lightroom uses in the xpacket begin attribute
        return (
            '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
            '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '    <rdf:Description rdf:about=""\n'
            '      xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
            '      xmlns:lr="http://ns.adobe.com/lightroom/1.0/"\n'
            f'      {attrs_block}/>\n'
            '  </rdf:RDF>\n'
            '</x:xmpmeta>\n'
            '<?xpacket end="w"?>'
        )

    # ── JPEG XMP embedding ────────────────────────────────────────────────────

    def _embed_xmp_jpeg(self, jpeg: bytes, xmp_xml: Optional[str]) -> bytes:
        """
        Return JPEG bytes with XMP inserted/replaced/removed.
        Preserves all other APP segments (EXIF, IPTC, ICC, etc.).
        xmp_xml=None removes any existing XMP block.
        """
        if jpeg[:2] != b"\xff\xd8":
            raise ValueError("Not a JPEG")

        new_xmp_seg: Optional[bytes] = None
        if xmp_xml is not None:
            payload = _XMP_SIG + xmp_xml.encode("utf-8")
            if len(payload) + 2 > 65535:
                raise ValueError("XMP payload too large for JPEG APP1")
            new_xmp_seg = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload

        # Walk the APP header region, collecting every segment except existing XMP
        i = 2
        exif_segs: list = []
        other_segs: list = []
        sos_pos = len(jpeg)

        while i + 1 < len(jpeg):
            if jpeg[i] != 0xFF:
                sos_pos = i
                break

            m = jpeg[i + 1]

            if m == 0xFF:       # padding
                i += 1
                continue
            if m == 0xDA:       # SOS — image data begins
                sos_pos = i
                break
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                other_segs.append(jpeg[i:i+2])
                i += 2
                continue

            if i + 3 >= len(jpeg):
                sos_pos = i
                break

            length = struct.unpack(">H", jpeg[i+2:i+4])[0]
            seg = jpeg[i:i + 2 + length]

            # Drop existing XMP
            if (seg[:2] == b"\xff\xe1"
                    and len(seg) > 4 + len(_XMP_SIG)
                    and seg[4:4+len(_XMP_SIG)] == _XMP_SIG):
                pass
            # Bucket EXIF separately so it stays first
            elif (seg[:2] == b"\xff\xe1"
                  and len(seg) > 10
                  and seg[4:10] in (b"Exif\x00\x00", b"Exif\x00\xff")):
                exif_segs.append(seg)
            else:
                other_segs.append(seg)

            i += 2 + length

        parts: list = [b"\xff\xd8"]
        parts.extend(exif_segs)
        if new_xmp_seg:
            parts.append(new_xmp_seg)
        parts.extend(other_segs)
        parts.append(jpeg[sos_pos:])
        return b"".join(parts)

    @staticmethod
    def _atomic_write(path: Path, data: bytes):
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".~tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ── JSON → XMP migration ──────────────────────────────────────────────────

    def _migrate_json(self, folder: Path):
        json_path = folder / "_labels.json"
        if not json_path.exists():
            return
        try:
            data: dict = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return

        migrated = 0
        for filename, entry in data.items():
            if self._is_jpeg(filename):
                img = folder / filename
                if img.exists() and not self._read_jpeg_xmp(img) != dict(_DEFAULT):
                    self._write(filename, entry)
                    migrated += 1
            else:
                if not self._sidecar_path(filename).exists():
                    self._write(filename, entry)
                    migrated += 1

        if migrated:
            try:
                json_path.rename(folder / "_labels.json.bak")
            except OSError:
                pass

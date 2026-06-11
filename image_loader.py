import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict
from PIL import Image

# macOS ImageIO via `sips` — hardware-accelerated HEIF/HEIC decode, far faster
# and far cooler than libde265 software decoding in pillow-heif.
_SIPS = shutil.which("sips")

# Native Apple ImageIO (PyObjC). Same hardware decoder Finder/Photos use, but
# called directly — no subprocess, no temp file — and it applies EXIF
# orientation. Preferred over `sips` whenever available.
try:
    import Quartz  # from pyobjc-framework-Quartz
    _IMAGEIO = True
except Exception:
    _IMAGEIO = False

_heif_available = False
_rawpy_available = False

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _heif_available = True
except ImportError:
    pass

try:
    import rawpy  # noqa: F401
    _rawpy_available = True
except ImportError:
    pass

# Check for exiftool once at import time
try:
    _et = subprocess.run(["exiftool", "-ver"], capture_output=True, timeout=3)
    _EXIFTOOL = _et.returncode == 0
except Exception:
    _EXIFTOOL = False

_BASE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
_HEIC_EXTS = {".heic", ".heif", ".hif"}
_RAW_EXTS  = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2", ".raw", ".raf", ".pef"}

# Disk thumbnail cache — keyed by (absolute_path, mtime_ns) so stale entries
# are simply orphaned and never re-read.
_CACHE_DIR: Optional[Path] = None
try:
    _c = Path.home() / ".cache" / "sorting-tool-thumbs"
    _c.mkdir(parents=True, exist_ok=True)
    _CACHE_DIR = _c
except Exception:
    pass


def cache_info() -> Tuple[int, int]:
    """Return (file_count, total_bytes) for the on-disk thumbnail cache."""
    if _CACHE_DIR is None or not _CACHE_DIR.exists():
        return (0, 0)
    count = 0
    total = 0
    for f in _CACHE_DIR.glob("*.jpg"):
        try:
            total += f.stat().st_size
            count += 1
        except OSError:
            pass
    return (count, total)


def clear_cache() -> Tuple[int, int]:
    """Delete every cached thumbnail. Returns (files_removed, bytes_freed).
    Safe at any time — thumbnails are regenerated from the originals on demand."""
    if _CACHE_DIR is None or not _CACHE_DIR.exists():
        return (0, 0)
    removed = 0
    freed = 0
    for f in _CACHE_DIR.glob("*.jpg"):
        try:
            size = f.stat().st_size
            f.unlink()
            removed += 1
            freed += size
        except OSError:
            pass
    return (removed, freed)


# ── public image-loading API (unchanged) ──────────────────────────────────────

def supported_extensions() -> set:
    exts = set(_BASE_EXTS)
    if _heif_available:
        exts |= _HEIC_EXTS
    if _rawpy_available:
        exts |= _RAW_EXTS
    return exts


# File-type groups for the type filter. JPEG is split out from the rest of the
# base formats so it can be selected on its own (Fuji shoots RAW+JPEG / HIF+JPEG).
FILE_TYPE_GROUPS: Dict[str, set] = {
    "raw":  set(_RAW_EXTS),
    "jpeg": {".jpg", ".jpeg"},
    "hif":  set(_HEIC_EXTS),
}


def scan_folder(folder: Path, recursive: bool = False) -> list:
    exts = supported_extensions()
    if recursive:
        files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in exts]
    else:
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts]
    return sorted(files, key=lambda p: p.name.lower())


def has_image_subfolders(folder: Path) -> bool:
    """Return True if folder has any subdirectory containing images."""
    exts = supported_extensions()
    for sub in folder.iterdir():
        if sub.is_dir():
            for f in sub.iterdir():
                if f.is_file() and f.suffix.lower() in exts:
                    return True
    return False


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode not in ("RGB", "RGBA"):
        return img.convert("RGB")
    return img


def load_full(path: Path) -> Optional[Image.Image]:
    ext = path.suffix.lower()
    if ext in _RAW_EXTS and _rawpy_available:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False)
                return Image.fromarray(rgb)
        except Exception:
            return None
    try:
        img = Image.open(str(path))
        img.load()
        return _to_rgb(img)
    except Exception:
        return None


def _thumb_cache_path(source: Path) -> Optional[Path]:
    if _CACHE_DIR is None:
        return None
    try:
        mtime_ns = source.stat().st_mtime_ns
    except OSError:
        return None
    # The version suffix invalidates thumbnails cached by older code (e.g. the
    # pre-ImageIO path that didn't apply EXIF orientation → sideways portraits).
    key = f"{source.resolve()}:{mtime_ns}:v2"
    h = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.jpg"


def _load_heic_thumbnail(path: Path, size: Tuple[int, int]) -> Optional[Image.Image]:
    """Extract the embedded JPEG preview from HIF/HEIC rather than doing a full decode."""
    # Fujifilm HIF: LibRaw can extract the embedded full-size JPEG preview
    if _rawpy_available:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                else:
                    img = Image.fromarray(thumb.data)
                img.thumbnail(size, Image.LANCZOS)
                return _to_rgb(img)
        except Exception:
            pass
    # Fallback: exiftool can pull the embedded PreviewImage JPEG
    if _EXIFTOOL:
        try:
            r = subprocess.run(
                ["exiftool", "-b", "-PreviewImage", str(path)],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0 and len(r.stdout) > 500:
                img = Image.open(io.BytesIO(r.stdout))
                img.thumbnail(size, Image.LANCZOS)
                return _to_rgb(img)
        except Exception:
            pass
    return None


def load_thumbnail_cached(path: Path, size: Tuple[int, int] = (400, 400)) -> Optional[Image.Image]:
    """Load a thumbnail, serving from disk cache when available."""
    cache_path = _thumb_cache_path(path)
    if cache_path is not None and cache_path.exists():
        try:
            img = Image.open(str(cache_path))
            img.load()
            return img
        except Exception:
            cache_path.unlink(missing_ok=True)

    img = load_thumbnail(path, size)
    if img is not None and cache_path is not None:
        try:
            img.convert("RGB").save(str(cache_path), "JPEG", quality=85, optimize=True)
        except Exception:
            pass
    return img


def get_cached_thumbnail(path: Path) -> Optional[Image.Image]:
    """Return the on-disk cached thumbnail only if it already exists — never builds
    one. Used for instant low-res placeholders while the full preview loads."""
    cache_path = _thumb_cache_path(path)
    if cache_path is not None and cache_path.exists():
        try:
            img = Image.open(str(cache_path))
            img.load()
            return img
        except Exception:
            pass
    return None


def _imageio_decode(path: Path, max_dim: int) -> Optional[Image.Image]:
    """Decode + downscale + orient via Apple ImageIO (hardware-accelerated).

    Returns an upright RGB PIL image whose longest side is <= max_dim, or None
    if ImageIO is unavailable or can't read the file. No subprocess, no temp
    file — it decodes straight into a memory bitmap."""
    if not _IMAGEIO:
        return None
    try:
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, str(path), Quartz.kCFURLPOSIXPathStyle, False)
        src = Quartz.CGImageSourceCreateWithURL(url, None)
        if src is None:
            return None
        opts = {
            Quartz.kCGImageSourceCreateThumbnailFromImageAlways: True,
            Quartz.kCGImageSourceThumbnailMaxPixelSize: int(max_dim),
            Quartz.kCGImageSourceCreateThumbnailWithTransform: True,  # apply orientation
        }
        cg = Quartz.CGImageSourceCreateThumbnailAtIndex(src, 0, opts)
        if cg is None:
            return None
        w = int(Quartz.CGImageGetWidth(cg))
        h = int(Quartz.CGImageGetHeight(cg))
        if w <= 0 or h <= 0:
            return None
        cs = Quartz.CGColorSpaceCreateDeviceRGB()
        # Own the backing buffer so there is no dangling pointer to free memory.
        buffer = bytearray(w * h * 4)
        ctx = Quartz.CGBitmapContextCreate(
            buffer, w, h, 8, w * 4, cs,
            Quartz.kCGImageAlphaNoneSkipLast | Quartz.kCGBitmapByteOrder32Big)
        if ctx is None:
            return None
        Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), cg)
        img = Image.frombuffer("RGB", (w, h), bytes(buffer), "raw", "RGBX", 0, 1)
        # frombuffer reports mode "RGBX"; hand back a plain RGB image.
        return img if img.mode == "RGB" else img.convert("RGB")
    except Exception:
        return None


def _sips_decode(path: Path, max_dim: int) -> Optional[Image.Image]:
    """Decode (and downscale) via macOS `sips` to a temp JPEG. Hardware-accelerated.
    Fallback only — does not apply EXIF orientation."""
    if not _SIPS:
        return None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        r = subprocess.run(
            [_SIPS, "-Z", str(max_dim), "-s", "format", "jpeg",
             str(path), "--out", tmp],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0:
            img = Image.open(tmp)
            img.load()
            return img
    except Exception:
        pass
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return None


def _apply_orientation(img: Image.Image) -> Image.Image:
    """Apply the EXIF orientation tag (rotate/flip) so the image is upright."""
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def load_preview(path: Path, max_dim: int = 2560) -> Optional[Image.Image]:
    """Fit-to-window quality image for the detail viewer.

    The viewer has no zoom — it always scales to fit — so a capped-resolution
    preview is visually lossless while being dramatically faster than a full
    decode. HEIF/HEIC go through Apple ImageIO (hardware-accelerated, upright)."""
    ext = path.suffix.lower()
    if ext in _HEIC_EXTS:
        img = _imageio_decode(path, max_dim)   # fast + correct orientation
        if img is not None:
            return img
        img = _sips_decode(path, max_dim)       # fallback
        if img is not None:
            return _apply_orientation(_to_rgb(img))
    img = load_full(path)
    if img is not None:
        if ext in _HEIC_EXTS:
            img = _apply_orientation(img)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img


def load_thumbnail(path: Path, size: Tuple[int, int] = (200, 150)) -> Optional[Image.Image]:
    ext = path.suffix.lower()
    if ext in _RAW_EXTS and _rawpy_available:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                else:
                    img = Image.fromarray(thumb.data)
                img.thumbnail(size, Image.LANCZOS)
                return _to_rgb(img)
        except Exception:
            pass
    if ext in _HEIC_EXTS:
        # ImageIO first: hardware-fast AND applies orientation (so portrait
        # HEIC thumbnails aren't shown sideways).
        img = _imageio_decode(path, max(size))
        if img is not None:
            return img
        img = _load_heic_thumbnail(path, size)
        if img is not None:
            return img
    try:
        img = Image.open(str(path))
        img.thumbnail(size, Image.LANCZOS)
        return _to_rgb(img)
    except Exception:
        return None


def get_exif(path: Path) -> Dict:
    """Lightweight EXIF for status bar (unchanged)."""
    result: Dict = {}
    try:
        from PIL.ExifTags import TAGS
        img = Image.open(str(path))
        result["width"]  = img.width
        result["height"] = img.height
        exif_raw = img._getexif() if hasattr(img, "_getexif") else None
        if exif_raw:
            for tag_id, value in exif_raw.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    result["date_taken"] = str(value)
                elif tag == "Make":
                    result["make"] = str(value).strip()
                elif tag == "Model":
                    result["model"] = str(value).strip()
                elif tag == "FNumber" and hasattr(value, "numerator") and value.denominator:
                    result["fnumber"] = f"f/{value.numerator / value.denominator:.1f}"
                elif tag == "ExposureTime" and hasattr(value, "numerator") and value.numerator:
                    d = int(value.denominator / value.numerator)
                    result["exposure"] = f"1/{d}s" if d > 1 else f"{value.numerator/value.denominator:.1f}s"
                elif tag == "ISOSpeedRatings":
                    result["iso"] = f"ISO {value}"
    except Exception:
        pass
    return result


def optional_support_info() -> str:
    parts = []
    parts.append("HEIC ✓" if _heif_available else "HEIC ✗ (pip install pillow-heif)")
    parts.append("RAW ✓"  if _rawpy_available  else "RAW ✗ (pip install rawpy + brew install libraw)")
    parts.append("exiftool ✓" if _EXIFTOOL else "exiftool ✗ (brew install exiftool — needed for film simulation)")
    parts.append("ImageIO ✓" if _IMAGEIO else "ImageIO ✗ (pip install pyobjc-framework-Quartz — faster HEIC)")
    return "  |  ".join(parts)


# ── comprehensive metadata for the info panel ─────────────────────────────────

def get_all_metadata(path: Path) -> Dict:
    """Return a rich metadata dict for the info panel.
    Uses exiftool when available; falls back to Pillow + MakerNote parsing."""
    if _EXIFTOOL:
        result = _meta_exiftool(path)
        if result:
            return result
    return _meta_pillow(path)


# ── exiftool path ─────────────────────────────────────────────────────────────

def _meta_exiftool(path: Path) -> Dict:
    try:
        r = subprocess.run(
            ["exiftool", "-json", "-charset", "UTF8",
             "-d", "%Y-%m-%d %H:%M:%S", str(path)],
            capture_output=True, timeout=20,
        )
        raw_list = json.loads(r.stdout.decode("utf-8", errors="replace"))
        if not raw_list:
            return {}
        return _normalise_exiftool(raw_list[0], path)
    except Exception:
        return {}


def _first(*keys, src: dict, default="") -> str:
    for k in keys:
        v = src.get(k)
        if v and str(v).strip() not in ("", "0", "undef", "Unknown", "None"):
            return str(v).strip()
    return default


def _normalise_exiftool(raw: dict, path: Path) -> Dict:
    out: Dict = {}
    f = lambda *keys, d="": _first(*keys, src=raw, default=d)

    # File
    out["filename"]  = path.name
    out["file_size"] = _fmt_size(path.stat().st_size)
    w = raw.get("ImageWidth") or raw.get("ExifImageWidth") or raw.get("PixelXDimension")
    h = raw.get("ImageHeight") or raw.get("ExifImageHeight") or raw.get("PixelYDimension")
    if w and h:
        out["dimensions"] = f"{w} × {h}"
    out["date_taken"]    = f("DateTimeOriginal", "CreateDate", "FileModifyDate")
    out["date_modified"] = f("FileModifyDate")

    # Camera
    out["make"]          = f("Make")
    out["model"]         = f("Model")
    out["lens_model"]    = f("LensModel", "LensID", "Lens")
    out["lens_make"]     = f("LensMake")
    out["serial_number"] = f("SerialNumber", "InternalSerialNumber")
    out["software"]      = f("Software")

    # Exposure
    iso = raw.get("ISO") or raw.get("ISOSpeedRatings")
    if iso:
        out["iso"] = f"ISO {iso}"
    fn = raw.get("FNumber") or raw.get("Aperture")
    if fn:
        out["fnumber"] = f"f/{fn}"
    et = raw.get("ExposureTime") or raw.get("ShutterSpeed")
    if et:
        out["exposure_time"] = str(et)
    fl = raw.get("FocalLength")
    if fl:
        out["focal_length"] = str(fl)
    fl35 = raw.get("FocalLengthIn35mmFormat") or raw.get("ScaleFactor35efl")
    if fl35:
        out["focal_length_35mm"] = str(fl35)
    eb = raw.get("ExposureCompensation") or raw.get("ExposureBiasValue")
    if eb is not None and str(eb) != "0":
        out["exposure_bias"] = _fmt_signed_str(str(eb))
    wb_mode = f("WhiteBalance")
    color_temp = raw.get("ColorTemperature")
    if wb_mode == "Kelvin" and color_temp:
        out["white_balance"] = f"{color_temp}K"
    else:
        out["white_balance"] = wb_mode
    wb_shift = raw.get("WhiteBalanceFineTune")
    if wb_shift:
        out["wb_shift"] = _fmt_wb_finetune(str(wb_shift))
    out["metering_mode"]  = f("MeteringMode")
    out["exposure_mode"]  = f("ExposureMode", "ExposureProgram")
    flash = raw.get("Flash")
    if flash and str(flash) not in ("No flash", "0", "Off, Did not fire"):
        out["flash"] = str(flash)
    out["scene_type"] = f("SceneCaptureType")

    # Fujifilm / film simulation
    out["film_simulation"]  = f("FilmMode", "FilmSimulation")
    out["film_recipe"]      = f("FilmRecipe", "Recipe")
    out["grain_effect"]     = f("GrainEffect", "GrainEffectRoughness")
    out["grain_effect_size"]= f("GrainEffectSize")
    out["color_chrome"]     = f("ColorChromeEffect", "ChromeEffect")
    out["color_chrome_blue"]= f("ColorChromeFXBlue", "ColorChromeEffectBlue")
    clarity = raw.get("Clarity")
    if clarity is not None:
        out["clarity"] = str(clarity)
    ht = raw.get("HighlightTone") or raw.get("Highlights")
    if ht is not None and str(ht) != "0":
        out["highlight_tone"] = _fmt_signed_str(str(ht))
    st = raw.get("ShadowTone") or raw.get("Shadows")
    if st is not None and str(st) != "0":
        out["shadow_tone"] = _fmt_signed_str(str(st))
    sat = raw.get("Saturation") or raw.get("ColorSaturation")
    if sat and str(sat) not in ("Normal", "0"):
        out["color_saturation"] = str(sat)
    out["sharpness"]        = f("Sharpness")
    out["noise_reduction"]  = f("NoiseReduction", "HighISONoiseReduction")
    dev_dr = raw.get("DevelopmentDynamicRange")
    if dev_dr and str(dev_dr) not in ("0", "100"):
        out["dynamic_range"] = f"DR{dev_dr}"
    elif not dev_dr:
        dr = raw.get("DynamicRange")
        if dr and str(dr) not in ("Standard", ""):
            out["dynamic_range"] = str(dr)
    out["color_space"]      = f("ColorSpace")

    # XMP / labels (filled in by caller from MetadataStore — set defaults here)
    out["rating"]       = 0
    out["flag"]         = "unflagged"
    out["color_label"]  = None

    # Creator / rights from XMP or IPTC
    out["creator"]     = f("Creator", "Artist", "By-line")
    out["copyright"]   = f("Rights", "Copyright", "CopyrightNotice")
    out["title"]       = f("Title", "ObjectName")
    out["description"] = f("Description", "Caption-Abstract", "ImageDescription")
    out["keywords"]    = _join_list(raw.get("Keywords") or raw.get("Subject"))

    # GPS
    lat = raw.get("GPSLatitude")
    lon = raw.get("GPSLongitude")
    if lat and lon:
        out["gps_lat"]  = str(lat)
        out["gps_lon"]  = str(lon)
        out["gps"]      = f"{lat}, {lon}"
    out["gps_altitude"] = f("GPSAltitude")

    # Extra XMP fields not already captured
    xmp_keys = {k for k in raw if k.startswith("XMP-") or ":" not in k}
    captured = set(out.keys()) | {"SourceFile", "ExifToolVersion", "FileType",
                                   "FileTypeExtension", "MIMEType", "JFIFVersion",
                                   "ExifByteOrder", "CurrentIPTCDigest", "EncodingProcess",
                                   "BitsPerSample", "ColorComponents", "YCbCrSubSampling",
                                   "ImageSize", "Megapixels", "ThumbnailImage",
                                   "PreviewImage", "ThumbnailOffset", "ThumbnailLength",
                                   "PreviewImageStart", "PreviewImageLength"}
    extra: Dict = {}
    for k, v in raw.items():
        if k in captured or not v:
            continue
        sv = str(v).strip()
        if sv in ("", "0", "undef", "Unknown", "None", "Binary data"):
            continue
        if len(sv) > 200:  # skip binary/huge blobs
            continue
        # Show ungrouped fields under their raw key name
        extra[k] = sv

    if extra:
        out["_extra"] = extra

    return out


# ── Pillow fallback path ───────────────────────────────────────────────────────

_EXIF_TAGS = {}

def _ensure_tags():
    global _EXIF_TAGS
    if not _EXIF_TAGS:
        from PIL.ExifTags import TAGS
        _EXIF_TAGS = TAGS


_EXPOSURE_PROGRAMS = {
    0: "Not Defined", 1: "Manual", 2: "Program AE",
    3: "Aperture-priority AE", 4: "Shutter-priority AE",
    5: "Creative (Slow speed)", 6: "Action (High speed)",
    7: "Portrait", 8: "Landscape",
}
_METERING_MODES = {
    0: "Unknown", 1: "Average", 2: "Center-weighted",
    3: "Spot", 4: "Multi-spot", 5: "Multi-segment", 6: "Partial",
}
_WHITE_BALANCE = {0: "Auto", 1: "Manual"}
_FLASH = {0: "No Flash", 1: "Fired", 5: "Fired (no return)", 7: "Fired (return)", 9: "On", 16: "Off"}


def _meta_pillow(path: Path) -> Dict:
    out: Dict = {"filename": path.name, "file_size": _fmt_size(path.stat().st_size)}
    _ensure_tags()

    try:
        img = Image.open(str(path))
        out["dimensions"] = f"{img.width} × {img.height}"
        out["color_space"] = img.mode

        exif_raw = img._getexif() if hasattr(img, "_getexif") else None
        if not exif_raw:
            return out

        makernote: Optional[bytes] = None

        for tag_id, value in exif_raw.items():
            tag = _EXIF_TAGS.get(tag_id, "")

            if tag == "Make":
                out["make"] = str(value).strip()
            elif tag == "Model":
                out["model"] = str(value).strip()
            elif tag == "Software":
                out["software"] = str(value).strip()
            elif tag == "DateTimeOriginal":
                out["date_taken"] = str(value)
            elif tag == "LensModel":
                out["lens_model"] = str(value).strip()
            elif tag == "LensMake":
                out["lens_make"] = str(value).strip()
            elif tag == "BodySerialNumber":
                out["serial_number"] = str(value).strip()
            elif tag == "ISOSpeedRatings":
                out["iso"] = f"ISO {value}"
            elif tag == "FNumber" and _ratio(value):
                out["fnumber"] = f"f/{_ratio(value):.1f}"
            elif tag == "ExposureTime" and _ratio(value):
                r = _ratio(value)
                out["exposure_time"] = f"1/{int(1/r)}s" if r < 1 else f"{r:.1f}s"
            elif tag == "FocalLength" and _ratio(value):
                out["focal_length"] = f"{_ratio(value):.0f}mm"
            elif tag == "FocalLengthIn35mmFilm":
                out["focal_length_35mm"] = f"{value}mm"
            elif tag == "ExposureBiasValue" and _ratio(value) != 0:
                out["exposure_bias"] = _fmt_signed_str(f"{_ratio(value):+.1f}")
            elif tag == "Flash":
                f_str = _FLASH.get(value, str(value))
                if "No" not in f_str and "Off" not in f_str:
                    out["flash"] = f_str
            elif tag == "WhiteBalance":
                out["white_balance"] = _WHITE_BALANCE.get(value, str(value))
            elif tag == "MeteringMode":
                out["metering_mode"] = _METERING_MODES.get(value, str(value))
            elif tag == "ExposureProgram":
                out["exposure_mode"] = _EXPOSURE_PROGRAMS.get(value, str(value))
            elif tag == "MakerNote" and isinstance(value, bytes):
                makernote = value
            elif tag == "GPSInfo" and isinstance(value, dict):
                gps = _parse_gps(value)
                if gps:
                    out.update(gps)

        # Fujifilm MakerNote
        if makernote and makernote[:8] == b"FUJIFILM":
            fuji = _parse_fujifilm_makernote(makernote)
            out.update(fuji)

    except Exception:
        pass

    out["rating"]      = 0
    out["flag"]        = "unflagged"
    out["color_label"] = None
    return out


def _ratio(v) -> float:
    try:
        if hasattr(v, "numerator") and v.denominator:
            return v.numerator / v.denominator
        return float(v)
    except Exception:
        return 0.0


# ── Fujifilm MakerNote parser ─────────────────────────────────────────────────

_FUJI_FILM_SIM = {
    0x000: "Provia / Standard",  0x100: "Velvia / Vivid",
    0x200: "Astia / Soft",       0x300: "Classic Chrome",
    0x301: "Acros",              0x310: "Acros + Ye Filter",
    0x311: "Acros + Ye Filter",  0x320: "Acros + R Filter",
    0x321: "Acros + R Filter",   0x330: "Acros + G Filter",
    0x331: "Acros + G Filter",   0x400: "Pro Neg. Hi",
    0x500: "Pro Neg. Std",       0x600: "B&W",
    0x610: "B&W + Ye Filter",    0x620: "B&W + R Filter",
    0x630: "B&W + G Filter",     0x700: "Sepia",
    0x800: "Classic Neg.",       0x900: "Eterna / Cinema",
    0xa00: "Eterna Bleach Bypass", 0xb00: "Nostalgic Neg.",
    0xc00: "Reala Ace",
}
_TONE_MAP  = {0: "Off", 0x100: "Weak", 0x200: "Strong", 0x300: "Very Strong"}
_SHARP_MAP = {0x1: "Soft", 0x2: "Soft", 0x3: "Standard",
              0x4: "Hard", 0x5: "Very Hard", 0x82: "Medium Soft", 0x84: "Medium Hard"}
_SAT_MAP   = {0x0: "Standard", 0x80: "Medium Low", 0x100: "Low",
              0x180: "Medium High", 0x200: "High", 0x8000: "B&W Filter"}
_NR_MAP    = {0x40: "Low", 0x80: "Normal", 0x100: "High"}


def _parse_fujifilm_makernote(data: bytes) -> Dict:
    out: Dict = {}
    if len(data) < 16:
        return out
    try:
        ifd_off = struct.unpack_from("<I", data, 8)[0]
        if ifd_off + 2 > len(data):
            return out
        num = struct.unpack_from("<H", data, ifd_off)[0]
        i = ifd_off + 2

        for _ in range(min(num, 300)):
            if i + 12 > len(data):
                break
            tag, type_, count = struct.unpack_from("<HHI", data, i)
            vraw = data[i + 8: i + 12]
            ts = {1:1, 2:1, 3:2, 4:4, 5:8, 6:1, 7:1, 8:2, 9:4, 10:8}.get(type_, 0)
            total = ts * count
            if total == 0:
                i += 12; continue
            if total <= 4:
                vb = vraw[:total]
            else:
                vo = struct.unpack_from("<I", vraw)[0]
                vb = data[vo:vo+total] if vo + total <= len(data) else b""
            if not vb:
                i += 12; continue

            def sh():
                return struct.unpack_from("<H", vb)[0] if len(vb) >= 2 else 0
            def sl():
                v = sh(); return v - 65536 if v > 32767 else v

            if tag == 0x1401:
                out["film_simulation"] = _FUJI_FILM_SIM.get(sh(), f"0x{sh():03X}")
            elif tag == 0x1002:
                out["sharpness"] = _SHARP_MAP.get(sh(), str(sh()))
            elif tag == 0x1003:
                out["white_balance"] = _decode_fuji_wb(sh())
            elif tag == 0x1004:
                out["color_saturation"] = _SAT_MAP.get(sh(), str(sh()))
            elif tag == 0x1040:
                out["highlight_tone"] = _fmt_signed(sl())
            elif tag == 0x1041:
                out["shadow_tone"] = _fmt_signed(sl())
            elif tag == 0x1047:
                out["color_chrome"] = _TONE_MAP.get(sh(), str(sh()))
            elif tag == 0x1048:
                out["color_chrome_blue"] = _TONE_MAP.get(sh(), str(sh()))
            elif tag == 0x104D:
                r = _TONE_MAP.get(sh(), str(sh()))
                if r and r != "Off":
                    out["grain_effect"] = r
            elif tag == 0x104E:
                sz_map = {0: "", 0x100: "Small", 0x200: "Large"}
                out["grain_effect_size"] = sz_map.get(sh(), "")
            elif tag == 0x1023:
                v = sl()
                if v != 0:
                    out["clarity"] = _fmt_signed(v)
            elif tag == 0x100E:
                out["noise_reduction"] = _NR_MAP.get(sh(), str(sh()))
            elif tag == 0x1006:
                out["dynamic_range"] = f"{sh()}%"

            i += 12
    except Exception:
        pass
    return out


def _decode_fuji_wb(val: int) -> str:
    m = {0x000: "Auto", 0x100: "Daylight", 0x200: "Cloudy",
         0x300: "Daylight Fluorescent", 0x301: "Day White Fluorescent",
         0x302: "White Fluorescent", 0x303: "Warm White Fluorescent",
         0x304: "Living Room Warm White", 0x400: "Incandescent",
         0x500: "Flash", 0xf00: "Custom", 0xff0: "Kelvin"}
    return m.get(val, f"0x{val:03X}")


def _parse_gps(gps_info: dict) -> Dict:
    try:
        def dms(val, ref_key, refs):
            d, m, s = [_ratio(x) for x in val]
            dd = d + m / 60 + s / 3600
            if gps_info.get(ref_key) in refs:
                dd = -dd
            return dd
        lat = dms(gps_info[2], 1, ("S",))
        lon = dms(gps_info[4], 3, ("W",))
        return {"gps_lat": f"{abs(lat):.5f}° {'N' if lat >= 0 else 'S'}",
                "gps_lon": f"{abs(lon):.5f}° {'E' if lon >= 0 else 'W'}",
                "gps": f"{lat:.5f}, {lon:.5f}"}
    except Exception:
        return {}


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_wb_finetune(raw_str: str) -> str:
    """Convert exiftool's raw WB fine-tune string (e.g. 'Red +80, Blue -120')
    to camera-display units (÷20), e.g. 'R+4 B-6'. Returns '' if no shift."""
    import re
    nums = re.findall(r'([+-]?\d+)', raw_str)
    if len(nums) < 2:
        return ""
    r, b = int(nums[0]) // 20, int(nums[1]) // 20
    if r == 0 and b == 0:
        return ""
    parts = []
    if r != 0:
        parts.append(f"R{r:+d}")
    if b != 0:
        parts.append(f"B{b:+d}")
    return "  ".join(parts)


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def _fmt_signed_str(s: str) -> str:
    try:
        v = float(s)
        return f"+{v:.1f}" if v > 0 else f"{v:.1f}"
    except Exception:
        return s


def _join_list(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)

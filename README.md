# Photo Sorter

A fast, keyboard-driven photo culling tool for macOS - built with Python and PyQt6. Designed to feel like a lightweight Lightroom, with a dark UI, filmstrip, grid view, star ratings, color labels, flags, and a full metadata panel that reads Fujifilm film simulation and recipe data.

---

## Features

- **Detail view** - large image preview with filmstrip; neighbours are prefetched so navigation feels instant
- **Grid view** - zoomable thumbnail grid (drag the size slider); default view on open
- **Metadata panel** - full EXIF + Fujifilm recipe info (film sim, grain, color chrome, WB shift, DR, tones, etc.)
- **Star ratings** - 1–5 stars, stored as XMP
- **Flags** - Pick, Reject, Unflagged
- **Color labels** - Red, Yellow, Green, Blue, Purple
- **Rotate** - non-destructive rotate left/right (stored in metadata, never alters the original)
- **Albums / folders** - move *or copy* images to any folder via the sidebar
- **Collections** - regular (manual) and smart (rule-based) collections in the sidebar
- **Batch rename** - rename multiple selected images at once
- **Auto-advance** - automatically jump to the next image after rating (detail view)
- **Multi-select** - batch move, copy, label, rotate, rename
- **Filtering & sorting** - filter by rating, flag, label, **and file type** (RAW / JPEG / HIF, and combinations); sort by filename, date, or rating
- **Recursive scanning** - loads images from a folder and all its subfolders
- **XMP metadata** - embedded into JPEG files (Lightroom-compatible), sidecar `.xmp` for RAW/HEIF
- **Formats** - JPEG, PNG, TIFF, HEIC, HEIF, HIF (Fuji), RAF, NEF, CR2, CR3, ARW, DNG, and more

### Performance

- **Hardware-accelerated HEIC/HIF decode** via Apple ImageIO (PyObjC) - fast and cool, and it applies EXIF orientation so portrait shots are upright
- **Disk thumbnail cache** (`~/.cache/sorting-tool-thumbs/`) - thumbnails are generated once and reused; clear it any time via **File → Clear Thumbnail Cache…**
- **Lazy thumbnail loading** - only on-screen thumbnails (plus a small buffer) are decoded, with a progress indicator
- **In-memory preview cache + prefetch** - recently viewed and neighbouring images stay decoded for instant display

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| PyQt6 | UI framework |
| Pillow | Image loading |
| pillow-heif | HEIC / HIF support (fallback decoder) |
| pyobjc-framework-Quartz | Fast hardware HEIC/HIF decode via Apple ImageIO (macOS; optional but recommended) |
| rawpy + libraw | RAW file support |
| exiftool | Full metadata (film simulation, recipe, GPS…) |

---

## Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd "Sorting Tool"

# 2. Install Python dependencies
pip install PyQt6 Pillow pillow-heif rawpy pyobjc-framework-Quartz
# (or: pip install -r requirements.txt)

# 3. Install system dependencies (macOS)
brew install libraw exiftool

# 4. Run
python3 app.py
```

> **Note:** `rawpy` requires `libraw`. Install `libraw` via Homebrew before `pip install rawpy`.

---

## Keyboard Shortcuts

### Navigation
| Key | Action |
|---|---|
| `←` / `→` | Previous / Next image (detail view) |
| `G` | Toggle grid ↔ detail view |
| `Double-click` | Open image in detail view (from grid) |
| `⌘O` | Open folder |

### Rating
| Key | Action |
|---|---|
| `1` – `5` | Set star rating (press same key again to clear) |
| `0` | Clear rating |

### Flags
| Key | Action |
|---|---|
| `P` | Toggle Pick |
| `X` | Toggle Reject |
| `U` | Clear flag (Unflagged) |

### Color Labels
| Key | Action |
|---|---|
| `6` | Red |
| `7` | Yellow |
| `8` | Green |
| `9` | Blue |
| `` ` `` | Purple (press again to clear) |

### Albums & Collections
| Key | Action |
|---|---|
| `M` | Move selected image(s) to selected album |
| `C` | Add selected image(s) to collection |
| `⌘A` | Select all |
| `⌘R` | Batch rename selected images |
| `⌘Z` | Undo last move |

### View & Rotate
| Key | Action |
|---|---|
| `[` | Rotate left |
| `]` | Rotate right |
| `I` | Toggle info / metadata panel |
| `⌘F` | Toggle filmstrip |
| `⌘B` | Toggle sidebar |
| `?` | Keyboard shortcut reference |

---

## Metadata Panel

Press `I` to show or hide the panel on the right side of the detail view. It reads data asynchronously (via exiftool) and displays:

- **File** - filename, size, dimensions, date taken
- **Camera** - make, model, lens, serial number
- **Exposure** - ISO, aperture, shutter, focal length, WB mode, WB shift, metering
- **Film / Style** - film simulation, dynamic range, highlight/shadow tone, color, sharpness, clarity, noise reduction, grain, color chrome
- **Labels** - current star rating, flag, color label
- **GPS** - coordinates and altitude (if present)

---

## Albums

Albums are just folders on disk. Add any folder via the `+` button in the sidebar. Select an image (or multi-select with `Shift`/`⌘` click), select an album, then press `M` to move (or enable **Copy instead of Move** in the dialog to copy). The image's XMP metadata travels with it.

**Collections** live in the sidebar too: *regular* collections are manual sets you add images to with `C`, and *smart* collections gather images automatically by rule (e.g. rating ≥ 4, a given flag or label).

---

## Metadata Storage

Ratings, flags, and color labels are written as XMP:

- **JPEG** - embedded directly into the file's APP1 marker, same format as Lightroom
- **RAW / HEIF / other** - written as a `.xmp` sidecar file alongside the original

This means metadata is immediately readable by Lightroom, Capture One, and any other XMP-aware tool.

Rotation is stored alongside the rest, in a private `photosort:` XMP namespace, as a **non-destructive display rotation** - it is applied on top of the file's own EXIF orientation and never rewrites the original image.

---

## Project Structure

```
app.py              Entry point, dark palette setup
main_window.py      Main window, toolbar, shortcuts, filter/sort logic
image_viewer.py     Large image preview widget
filmstrip.py        Horizontal filmstrip (detail view)
grid_view.py        Thumbnail grid view
metadata_panel.py   Async metadata info panel
metadata.py         XMP read/write (JPEG embed + sidecar), incl. rotation
image_loader.py     Image loading, ImageIO/thumbnail decode + cache, exiftool metadata
loading_overlay.py  Floating thumbnail-loading progress indicator
sidebar.py          Albums + collections sidebar
```

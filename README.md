# Photo Sorter

A fast, keyboard-driven photo culling tool for macOS — built with Python and PyQt6. Designed to feel like a lightweight Lightroom, with a dark UI, filmstrip, grid view, star ratings, color labels, flags, and a full metadata panel that reads Fujifilm film simulation and recipe data.

---

## Features

- **Detail view** — large image preview with filmstrip
- **Grid view** — zoomable thumbnail grid (drag the size slider)
- **Metadata panel** — full EXIF + Fujifilm recipe info (film sim, grain, color chrome, WB shift, DR, tones, etc.)
- **Star ratings** — 1–5 stars, stored as XMP
- **Flags** — Pick, Reject, Unflagged
- **Color labels** — Red, Yellow, Green, Blue, Purple
- **Albums / folders** — move images to any folder via the sidebar
- **Multi-select** — batch move, batch label
- **Filtering & sorting** — filter by rating, flag, label; sort by filename, date, or rating
- **XMP metadata** — embedded into JPEG files (Lightroom-compatible), sidecar `.xmp` for RAW/HEIF
- **Formats** — JPEG, PNG, TIFF, HEIC, HEIF, HIF (Fuji), RAF, NEF, CR2, CR3, ARW, DNG, and more

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| PyQt6 | UI framework |
| Pillow | Image loading |
| pillow-heif | HEIC / HIF support |
| rawpy + libraw | RAW file support |
| exiftool | Full metadata (film simulation, recipe, GPS…) |

---

## Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd "Sorting Tool"

# 2. Install Python dependencies
pip install PyQt6 Pillow pillow-heif rawpy

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

### Albums & Selection
| Key | Action |
|---|---|
| `M` | Move selected image(s) to selected album |
| `⌘A` | Select all |
| `⌘Z` | Undo last move |

### View Toggles
| Key | Action |
|---|---|
| `I` | Toggle info / metadata panel |
| `⌘F` | Toggle filmstrip |
| `⌘B` | Toggle sidebar |
| `?` | Keyboard shortcut reference |

---

## Metadata Panel

Press `I` to show or hide the panel on the right side of the detail view. It reads data asynchronously (via exiftool) and displays:

- **File** — filename, size, dimensions, date taken
- **Camera** — make, model, lens, serial number
- **Exposure** — ISO, aperture, shutter, focal length, WB mode, WB shift, metering
- **Film / Style** — film simulation, dynamic range, highlight/shadow tone, color, sharpness, clarity, noise reduction, grain, color chrome
- **Labels** — current star rating, flag, color label
- **GPS** — coordinates and altitude (if present)

---

## Albums

Albums are just folders on disk. Add any folder via the `+` button in the sidebar. Select an image (or multi-select with `Shift`/`⌘` click), select an album, then press `M` to move. The image's XMP metadata travels with it.

---

## Metadata Storage

Ratings, flags, and color labels are written as XMP:

- **JPEG** — embedded directly into the file's APP1 marker, same format as Lightroom
- **RAW / HEIF / other** — written as a `.xmp` sidecar file alongside the original

This means metadata is immediately readable by Lightroom, Capture One, and any other XMP-aware tool.

---

## Project Structure

```
app.py              Entry point, dark palette setup
main_window.py      Main window, toolbar, shortcuts, filter/sort logic
image_viewer.py     Large image preview widget
filmstrip.py        Horizontal filmstrip (detail view)
grid_view.py        Thumbnail grid view
metadata_panel.py   Async metadata info panel
metadata.py         XMP read/write (JPEG embed + sidecar)
image_loader.py     Image loading, thumbnail generation, exiftool metadata extraction
sidebar.py          Albums sidebar
```

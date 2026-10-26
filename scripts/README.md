# Scripts

Helpers for the stages before the layout engine (`python -m photobook`).
All take their paths as arguments; run any of them with `--help`.

| Script | Purpose |
|---|---|
| `build_index.py` | Indexes every photo in zip archives/folders once: stable idx, capture time, GPS, size, sharpness, thumbnails → `recs_sorted.json`. `build_index.py PROJECT_DIR raw/*.zip` |
| `make_manifest.py` | Selection → `final_manifest.json`, upright photo files in `fullres/`, `fullres_idx_map.json` and a `book.json` skeleton. `make_manifest.py PROJECT_DIR --select selection.txt` |
| `photo_source.py` | Shared helper: reads photos straight out of zips or folders, HEIC included. |
| `heic_extract.py` | Manual ISOBMFF box parser for HEIC files that fail on the standard `libheif` path (grid-type primary images). Needs ffmpeg. `heic_extract.py IN.heic OUT.jpg` |
| `batch_heic.py` | Converts every `.heic` in a folder via `heic_extract.py`. `batch_heic.py SRC_DIR OUT_DIR` |
| `build_contact_sheets.py` | One thumbnail sheet per day with idx labels, for choosing photos. `build_contact_sheets.py PROJECT_DIR/recs_sorted.json` |
| `extract_photos.py` | Copies photos by printed number out of the zip archives into a review folder. `extract_photos.py PROJECT_DIR 12 40` |
| `package_skill.py` | Builds the Claude skill (`dist/photobook/`, `dist/photobook.skill`). |

Everything that used to be a script here – the layout build in a review
and a print copy, the partial-render and numbered-reference harnesses, the
PATTERN probe – is now part of the engine: see the main
[`README.md`](../README.md) and [`docs/ENGINE.md`](../docs/ENGINE.md).

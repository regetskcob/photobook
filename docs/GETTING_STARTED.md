# Getting started: from camera exports to print files

A walk-through for a first book. Each step names the command and what to
check before moving on. Background on every mechanism:
[`ENGINE.md`](ENGINE.md); the full format of `book.json`:
[`../schema/book_schema.md`](../schema/book_schema.md).

## 0. Install

```bash
git clone <this repo> && cd <repo>
pip install -e .            # Python 3.9+; installs reportlab, pillow, numpy, pypdf
```

Optional: `pip install pillow-heif` for HEIC photos (otherwise HEIC goes
through `scripts/heic_extract.py`, which needs `ffmpeg`), and `exiftool`
for capture times of HEIC files.

Keep each book in its own project folder, outside this repo:

```bash
mkdir ~/Photobooks/alps-2027 && cd ~/Photobooks/alps-2027
mkdir raw && cp ~/Downloads/*.zip raw/      # camera/phone exports, zipped or as folders
```

## 1. Index every photo

```bash
python <repo>/scripts/build_index.py . raw/*.zip raw/some_folder
```

Writes `recs_sorted.json` (one entry per photo: stable `idx`, capture time,
GPS, size, sharpness) and `thumbs/`. Build it **once**: from here on,
everything refers to photos by `idx`, so it must not change. Photos without
a capture time are listed – check them.

## 2. Choose photos

Print contact sheets – one image per day with every thumbnail and its
idx:

```bash
python <repo>/scripts/build_contact_sheets.py recs_sorted.json --out contact_sheets
```

Write the chosen idx values into `selection.txt`, one per line (`#`
starts a comment). Then:

```bash
python <repo>/scripts/make_manifest.py . --select selection.txt
# or, for a first look at everything: --all --min-sharpness 40
```

This groups the photos into days by capture date, numbers them through
the whole book, writes upright JPEGs to `fullres/`, and creates
`final_manifest.json`, `fullres_idx_map.json` and a `book.json` skeleton
with one chapter per day.

## 3. Fit the print product

Open `book.json`:

- `profile`: the product geometry. `saal_professional_30x21_landscape`
  ships with the repo. For another product, export the publisher's
  template from InDesign as "raw format including bleed, no marks" and run
  `python -m photobook profile-from-pdf cover.pdf pages.pdf > my_product.json`.
  Read "The print-ready export fix" in [`ENGINE.md`](ENGINE.md) first –
  never use the downloadable proof-sheet templates.
- `pages`: the product's exact interior page count.

```bash
python -m photobook pages book.json           # the plan, spread by spread
python -m photobook pattern-search book.json  # batch sizes that hit the page count
```

Copy a suggested `pattern` into `book.json` and re-run `pages` until it
reports the right count and no unplaced photos you care about.

## 4. Titles, texts, highlights

Fill in each chapter's `title`, `date`, `intro`, pick an `opener` photo
(and maybe a `hero` and panoramas), the `cover` photo and the closing
spread. Per-photo captions, crops and text paragraphs go under `photos`,
keyed by idx. [`../examples/demo/book.json`](../examples/demo/book.json)
uses every option.

## 5. Feedback rounds

```bash
python -m photobook build book.json --mode numbers   # big photo numbers, small file
```

Send that PDF to whoever reviews the book. Notes like "photo 037: crop
from the top" refer to the printed number; look it up in
`python -m photobook pages book.json` or the manifest (`order` → `idx`)
and edit `book.json`. When photos are added or removed:

```bash
python -m photobook renumber book.json   # then send a fresh numbers PDF
```

[`TEXTE_VORLAGE_PROTOCOL.md`](TEXTE_VORLAGE_PROTOCOL.md) describes a text
template that worked well for collecting texts and notes per round.

To check a fix quickly, render just the spreads involved:
`build book.json --mode review --spreads 12-13`.

## 6. Print files

```bash
python -m photobook build book.json --mode print
```

Produces `build/<prefix>_cover_print.pdf` and `build/<prefix>_pages_print.pdf`
at 300 dpi with TrimBox/BleedBox set and no numbers. Check the list of
photos below 200 dpi at the end of the output, rasterise a few spreads and
look at them, then upload.

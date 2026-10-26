---
name: photobook
description: Build a print-ready photobook (Fotobuch) from someone's trip or event photos - select and order photos by day, lay out chapter openers, grids, panoramas and captions, run numbered feedback rounds with the user, and export upload-ready cover and interior PDFs with correct trim/bleed for a print service such as Saal Digital. Use this whenever the user wants to turn a pile of holiday/vacation/wedding/family photos into a printed book, asks for help with a photobook layout, captions or texts for one, wants to fix or swap photos in a book by their number ("Bild 037 tauschen"), needs to hit a fixed page count, or has trouble with print PDFs being rejected or showing crop marks or white edges - even if they don't say "photobook".
---

# Photobook

A layout engine plus the workflow that produced a real 84-page book. The
engine (`photobook/` in this skill's folder) turns a curated photo list and
a `book.json` into PDFs. Your job is mostly editing `book.json` and the
manifest with the user, rendering, and checking the result visually.

Paths below are relative to this skill's folder (`<skill>`).

## Before you start: the brief

A new book needs eight answers. Take what the user's message already says,
and ask for the rest in **one** message – each question with the default
you'd use, so "yes, defaults" is a complete answer. Don't guess the ones
marked ⚠: they change everything after them.

1. **Photos** – where (folder or zip exports), roughly how many, which
   devices, edited versions? (default: index everything found there)
2. ⚠ **Print product** – service, format, orientation, exact page count.
   No default: ask neutrally. Mention that Saal Digital Professional Line
   30×21 landscape is ready to use; for anything else you need the
   service's template exported as "raw format incl. bleed, no marks"
   (`references/ENGINE.md`, "Format profile").
3. **Occasion, reader, tone** – trip/wedding/year; for themselves or a
   gift; personal or neutral. (default: personal, for themselves)
4. **Structure** – chapters by day, place or theme; short arrival/departure
   days folded in or used as closing photo. (default: one per day, short
   days folded into the day before, last photo closes the book)
5. ⚠ **Selection** – does the user choose, or do you draft? Must-haves and
   no-gos (people, screenshots, black and white).
6. **Texts** – language, who writes them, how much. (default: the user's
   language, placeholders for titles and intros, written by the user)
7. **Feedback** – who reviews and how (annotated PDF, screenshots, a text
   file per round – `references/TEXTE_VORLAGE_PROTOCOL.md`). (default: notes
   by photo number on the numbers PDF)
8. **Deadline and project folder** – order date, and where the project
   lives: index, copies of the chosen photos (~6 MB each), book.json,
   PDFs. Never inside the photo folder or this skill. (default: a new
   folder next to the photos, e.g. `<photos> – Fotobuch/`; PDFs in its
   `build/`; print files only on their go-ahead)

Indexing can start while you wait for answers – it only reads the photos.
Repeat the brief back in a few lines before the first build, so a
misunderstanding costs one message, not a round.

## Setup

```bash
pip install reportlab pillow numpy pypdf      # reportlab >= 4.0
cd <skill> && python -m photobook --help        # or: PYTHONPATH=<skill> python -m photobook ...
```

Run everything from `<skill>` (or with `PYTHONPATH=<skill>`); there is
nothing to clone or `pip install -e` - instructions in the references that
say so are for people using the GitHub repository. To see every feature on
placeholder photos: `python examples/demo/make_demo_photos.py`, then
`python -m photobook build examples/demo/book.json --mode review`.

## The project folder

Each book lives in its own folder (never inside this skill):

```
<project>/
  book.json             layout + all texts, keyed by photo idx   (format: references/book_schema.md)
  final_manifest.json   curated photos: idx, day, order, file    (format: references/manifest_schema.md)
  photos/ ...           the actual files (or a photo_map JSON idx -> path)
  build/                output of `photobook build`
```

Start a new `book.json` by copying `examples/demo/book.json`.

## Commands

| Command | Use it for |
|---|---|
| `python -m photobook check BOOK` | config, page count and duplicate photos – run before sending anything to the user |
| `python -m photobook pages BOOK` | page plan with printed numbers, unplaced photos – instant, run after every edit |
| `python -m photobook build BOOK --mode numbers` | big readable photo numbers – send this to the user before every feedback round |
| `python -m photobook build BOOK --mode review` | the finished look with tiny numbers, for proofreading |
| `python -m photobook build BOOK --mode print` | upload files: no numbers, 300 dpi, TrimBox/BleedBox set |
| `build ... --spreads 3-5` / `--kind opener` | re-render just what you changed, in seconds |
| `build ... --keep-spreads` | keep one PDF per spread to rasterise and look at (`pdftoppm -r 80`, or `sips -s format png` on macOS) |
| `python -m photobook renumber BOOK` | after adding/removing photos – then send a fresh numbers PDF |
| `python -m photobook pattern-search BOOK` | the page count no longer adds up after adding/removing photos |
| `python -m photobook profile-from-pdf COVER PAGES` | geometry for a new print product |

Timings on a real trip (1,105 photos, 9.5 GB of zips, 158 in the book):
index 2.5 min, manifest 2 s (plus ~1 GB of full-resolution copies in
`fullres/`), numbers PDF 20 s / 17 MB. A 300 dpi print build takes a few
minutes – run it in the background if your shell has a short timeout.

## Workflow

1. **Raw material → manifest.** Photos usually come as zip archives from
   several phones; leave them zipped.
   - `python scripts/build_index.py PROJECT raw/*.zip` – full index with
     stable `idx`, capture time, sharpness, thumbnails. Run it once; the
     idx values must never change afterwards.
   - `python scripts/build_contact_sheets.py PROJECT/recs_sorted.json` –
     sheets of 24 thumbnails per day, with idx, time, sharpness and edited
     exports framed; written to `PROJECT/contact_sheets/`.
   - `python scripts/suggest_selection.py PROJECT --pages 84` – only when the
     user wants you to pick: a first draft in `selection.txt`, one photo per
     burst, spread through each day, sized to the page count.
   - `python scripts/make_manifest.py PROJECT --select selection.txt
     --pages 84 --lang de --name Trip` – days by capture date (days with
     fewer than 5 photos fold into the day before), numbering, upright photo
     files, and a `book.json` skeleton with the best landscape photo per day
     as opener, the best overall as cover, the trip's last photo as the
     closing spread.
   Command-by-command walk-through: `references/GETTING_STARTED.md`;
   background: `references/PIPELINE.md`.
2. **Print product.** Each product has fixed geometry and usually a fixed
   page count. `profiles/` has Saal Digital Professional Line 30×21 cm. For
   anything else read "Format profile" and "The print-ready export fix" in
   `references/ENGINE.md` before measuring anything.
3. **First `book.json`**: days with titles, dates, opener photos. Run
   `pages`; adjust `pattern` until the page count fits.
4. **Feedback rounds.** Render `--mode numbers`, send it, let the user
   write notes and texts against the printed numbers
   (`references/TEXTE_VORLAGE_PROTOCOL.md` describes the template). Apply
   them to `book.json`, re-render the affected spreads, look at them. After
   adding or removing photos: `renumber`, then a fresh numbers PDF.
5. **Print files** with `--mode print` – only after the user explicitly
   says go. Check the DPI warnings at the end of the build output.

## Choosing photos (when the user asks you to pick)

Selection is the user's call, but a first draft often starts with "pick
for me". Criteria that held up on the original book (details:
`references/CHOOSING_PHOTOS.md`):

- prefer `"edited": true` versions in the index – someone already chose how
  that moment should look
- one or two favourites per burst; photos seconds apart are one series
- `sharpness` finds shaky outliers within a set – don't rank by it
- mix landscape, people, animals, details; skip black-and-white edits in a
  colour book
- how many: 2 per chapter (opener, inset) + 1 closing + about 2.2 per
  remaining page – 84 pages with 7 chapters ≈ 160 photos. Too few and the
  page count can only be met with many single-photo pages
- name chapters from `scripts/gps_report.py`, not from guesses

`scripts/suggest_selection.py` applies all of this mechanically; treat its
result as a draft. Show the user the contact sheets and your pick before
building on it, and say which picks you are unsure about.

## Things that went wrong before (and why the rules exist)

- **Printed numbers move; idx doesn't.** `order` is the number printed on
  each photo and shifts whenever photos are added or removed. Everything in
  `book.json` is keyed by `idx`. When the user says "Bild 027", look up
  `order == 27` in the *current* manifest – never from memory or an older
  note. After any add/remove, run `renumber` (it renumbers the whole book;
  renumbering only the changed day once printed two photos with the same
  number) and send a fresh numbers PDF before the user writes more notes.
- **One notes file can mix two numbering schemes** if it was written across
  rounds. When a note edits existing text, the current caption text in
  `book.json` tells you which idx is meant, not the raw number.
- **Trust the user's screenshot over your reconstruction.** A PDF viewer's
  page counter is the spread number (one PDF page per spread). If a page
  reference doesn't match what you expect, ask for a screenshot of the PDF
  they're looking at.
- **Never merge onto a publisher's downloaded template PDF.** Those were
  proof sheets with visible crop marks and no trim metadata; every print
  file of the original book carried the marks until someone looked. The
  engine renders its own pages and sets TrimBox/BleedBox – keep it that
  way. Geometry comes from the user's own "raw format incl. bleed, no marks"
  export of the publisher's template. If cover and interior disagree on
  bleed, add bleed to the one missing it, never remove it.
- **Look at renders.** Crop choices, captions near the cut line, text
  slots – rasterise the spread and look before claiming it's fixed. A
  portrait photo in a landscape box can't be saved by `crop` alone (see the
  worked example in `references/ENGINE.md`).
- **Turning off a much-tuned detail**: switch it off with a flag
  (`style.chapter_silhouette`), don't delete it.

## Translating requests into `book.json`

| The user says | Change |
|---|---|
| "Bild 012 bitte oben ausrichten" / head cut off | `photos.<idx>.crop`: `top` (or `bottom`, `left`, `right`) |
| caption / short text for a photo | `photos.<idx>.caption` |
| a longer paragraph instead of a photo | `photos.<idx>.text` (+ `text_companion`, `text_align`) |
| "this one deserves a full page" | day's `solo_fullbleed` |
| "these three together, X big" | day's `groups` with `manual3` (fixed order) – `portrait3` only if the most portrait photo should win |
| two photos edge to edge | `groups` with `bleed2` |
| swap two page blocks | `page_swaps` – changes position only, numbers stay |
| swap a photo for another file | point its file at the new one; idx, order and day stay |
| remove a photo | delete it from the manifest, `renumber`, re-run `pages` and fix any errors it names |
| add a photo | add it to the manifest (idx from `recs_sorted.json`, its file to the photo map), `renumber`, `pages` |
| other script than Latin (Greek, Cyrillic, …) or a different look | `style.font_files`, `style.dark_color` |
| chapter pages: "Text mittig", "Foto links", "ohne große Nummer" | `style.opener_align: center`, `style.opener_photo_side: left`, `style.opener_number: false` |
| one chapter: no small photo / a caption on the chapter photo / its own colour | that day's `inset: false`, `opener_caption`, `color` |

The engine refuses references to photos that aren't in that day, a photo
with two roles, duplicate numbers, broken spread pairing, missing or
unreadable files, text the font can't draw, and **look-alike photos** (the
same moment twice: original and edit, a messenger copy, a burst). Read the
error, it names the photos and what to change. Only list photos in
`allow_duplicates` when the user wants both in the book – don't do it to
make an error go away.

New books use `"layout": 2` (staggered landscape pairs, fewer accidental
single-photo pages). Don't switch an existing book to it without asking:
every page after the first change point would move. Full key reference:
`references/book_schema.md`; how each mechanism behaves on the page:
`references/ENGINE.md`; short list of every pitfall:
`references/LESSONS_LEARNED.md`.

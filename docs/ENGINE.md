# The layout engine (`photobook/`) – mechanics & conventions

How the engine turns a book into PDFs, and the lessons behind its design.
The config format itself is specified in
[`../schema/book_schema.md`](../schema/book_schema.md).

## Three inputs, one engine

| Input | Belongs to | Lives in |
|---|---|---|
| `book.json` | one specific book: texts, captions, opener photos, crop tweaks, page count, `pattern` | the book's project folder, next to its photos |
| `final_manifest.json` | one specific book: the curated photos, their day and printed number | same project folder |
| profile JSON | the print product: page, trim and bleed geometry | `profiles/` in this repo (or any path) |

The engine (`photobook/`) holds none of these. Before this split, all of
it lived as Python constants inside two ~1,700-line copies of one script
(a review copy and a print copy) that had to be kept in sync by hand.

```
photobook/book.py     load + validate book.json, manifest and profile
photobook/layout.py   plan: book -> flat list of logical pages (no image I/O)
photobook/render.py   draw: logical pages -> PDF, set TrimBox/BleedBox
photobook/cli.py      `python -m photobook build|pages|renumber|pattern-search|profile-from-pdf`
```

## Build modes

One code path, three modes – they differ only in the page numbers drawn
and the default resolution:

| Mode | Page numbers | Default DPI | Output |
|---|---|---|---|
| `print` | none | 300 | `<prefix>_cover_print.pdf`, `<prefix>_pages_print.pdf` – the upload files |
| `review` | small, discreet (5 pt) | 150 | same, `_review` – the finished look, for proofreading |
| `numbers` | big, high-contrast | 110 | `<prefix>_pages_numbers.pdf` – for feedback rounds by number |

`--spreads 0,3-5` and `--kind opener` render a subset in seconds (used to
need a hand-copied script "head" exec'd up to a cut marker). `--dpi`
overrides the resolution; low-resolution review PDFs stay small enough to
send without chunking.

Every mode sets `/TrimBox` and `/BleedBox` from the profile, so a review
PDF already shows exactly what the printer will cut.

## Format profile

The boxes (`media`, `trim`, `bleed` for cover and interior spread) **must
come from the publisher's own documented "raw format including bleed"
export, not from a downloaded proof-sheet template** – see "The
print-ready export fix" below for why the first measurement was wrong.
For a new product, have the user export their InDesign document from the
publisher's placed template with those settings, then:

```bash
python -m photobook profile-from-pdf cover_export.pdf pages_export.pdf --name "..." > profiles/<name>.json
```

It warns when a file carries no TrimBox. Render the result to PNG and look
at it before trusting it.

`INSET` (10 mm) is the safety margin for text from the trim edge;
cover text uses 20 mm.

## Days and the `order` field

The book's chapters are `days` in `book.json`, in book order. Each day's
`id` must match the `day` values in the manifest. Photos of a day are
sorted by `order`, and `order` is also the number printed on each photo in
review builds.

**Critical lesson:** `order` must be unique across the ENTIRE book, not
just per day. If only some days get renumbered after photos are added
there, ranges can overlap and two photos show the same number. The engine
now refuses a manifest with duplicate `order` values. After every manifest
change, renumber the whole book in chapter order (each chapter keeps its
relative order):

```bash
python -m photobook renumber book.json
```

Layout groups strictly by day before sorting, so this only changes the
printed digits – but every number the user has seen may now be stale, so
send a fresh `--mode numbers` PDF before the next round of notes.

## Everything is keyed by `idx`

`photos` entries, `opener`, `hero`, `groups`, `page_swaps` – every photo
reference in `book.json` is an `idx`: the stable photo ID from the full
index, never reused. **Never** the printed `order` number. User notes talk
in printed numbers ("Bild 027"); always translate `order → idx` against
the current manifest (`python -m photobook pages` prints both), never from
memory or an old note.

### Stale references fail loudly now

The old script silently ignored an override whose idx no longer matched
(most painfully `MANUAL_GRID_ORDER`, keyed by the exact set of photos in a
batch – any photo added earlier that day shifted the batches and the key
quietly stopped matching). The engine instead:

- **errors** when a day-level reference (`opener`, `inset`, `hero`,
  panoramas, `solo_fullbleed`, `groups`) is not a photo of that day,
- **warns** when a `photos` entry refers to an idx not in the manifest,
- **errors** when the page count, spread pairing or "no photo twice"
  invariants break, naming the day and what to change,
- lists photos that ended up on no page (`photobook pages`).

`MANUAL_GRID_ORDER` itself is gone: a fixed placement is a `groups` entry
with style `manual3`, keyed by the photos themselves and placed at the
chronological position of its first member, so it survives reflows.

## Page planning

### `pattern` and the exact page count

The publisher's product has a FIXED interior page count (84 for the
Oberstdorf book). Each day's remaining photos are batched into grid pages
by the cyclic `pattern` (e.g. `[2, 2, 2, 2, 3]`) – **restarting at index
0 for every day**. Special pages (hero, solo, groups, panoramas) interrupt
the batching at their chronological position.

Because a day's opener is always 2 pages, a day must have an even number
of remaining pages or the next opener would straddle two spreads.
`fix_parity()` splits the first plain grid page with 2+ photos to fix
that; if there is none, planning fails with the day's name – or, with
`fill_odd_days_with_blank` (set in the `make_manifest.py` skeleton for
first drafts), the day gets a blank page.

When the photo count changes, search for a new pattern instead of
guessing:

```bash
python -m photobook pattern-search book.json --lengths 4,5,6 --values 2,3,4
```

Planning does no image I/O, so this tries hundreds of candidates per
second and lists those hitting the page count, fewest unrequested
single-photo pages first. Pick the one closest to the last reviewed
pattern to minimise visual churn.

### Opener, inset, hero

- `opener`: the day's big photo, full-bleed on the right-hand page of the
  chapter spread. The left page is dark, with the day number, title,
  `label · date` tagline and `intro` text.
- inset: a small teaser photo bottom-right on the opener's text page.
  Auto-picked as the day's first photo (excluding opener and panorama)
  unless `inset` names one. The inset is removed from the grid pool so it
  doesn't appear twice.
- `hero`: a captioned full-page highlight at its chronological position.
  `hero_before_previous_page` swaps it with the page right before it (same
  spread, other side).

### Panoramas

- `panorama_after_opener`: a two-page spread right after the opener. It
  keeps its own (later) printed number, so numbers don't strictly follow
  page order – expected.
- `mid_day_panorama`: a two-page spread at its chronological position.
  Parity is fixed separately before and after it so it starts on a left
  page.

### Hand-placed groups

| Style | Layout |
|---|---|
| `manual3` | big-left + two small right, in the given order |
| `portrait3` | same, but the most portrait photo is sorted into the big slot |
| `portrait3_bleed` | `portrait3` with the big photo bleeding top and bottom |
| `mirror3` | two small left, big right, in the given order |
| `bleed2` | two photos edge to edge with a thin gutter |

Prefer `manual3` over `portrait3` when a specific photo must get the big
slot: the auto-sort picks the most portrait photo, which may not be the
one asked for (several Oberstdorf rounds hit exactly this).

### Post-hoc page swaps (`page_swaps`)

Sometimes the wanted order matches neither camera time nor the day logic
(a panorama shot on the way back was timestamped before the "still at the
hut" photos). `page_swaps` swaps two adjacent blocks of finished pages,
identified by the idx sets they show:

```json
"page_swaps": [{"a": [2000], "b": [648, 650, 651, 655, 657, 658]}]
```

Only physical position changes; printed numbers stay, so no renumbering
and no new reference PDF is needed. The blocks must be contiguous,
adjacent (`a` before `b`) and contain exactly the listed photos – the
engine errors otherwise.

**Resolving which pages a user means:** a PDF viewer's page counter IS the
1-based spread number (one PDF page per spread). `photobook pages` prints
spreads 0-based. When the user's reference doesn't match your own idea of
the layout, ask for a screenshot of the actual PDF instead of
reconstructing past structure.

## Drawing details

### Cropping (`photos.<idx>.crop`) – worked example

`load_crop()` crops only ONE axis – whichever the source has too much of
relative to the box – and keeps the full extent of the other. `crop`
(`top`/`bottom`/`left`/`right`/`center`) only picks WHERE on that axis
the window sits; it can't rescue a box/photo pairing whose aspect ratios
are far apart.

Concrete case: an opener inset box is landscape (ratio ≈1.16), the source
selfie a tall portrait (≈0.56). The engine keeps the full width and crops
height; `center` cut straight through both foreheads. `top` kept both
heads – but the crop height is fixed by the box ratio, so whatever sat
between hairline and shoulders (a pool in the background) is unavoidably
in. With a mismatch this large no alignment satisfies "whole subject" and
"nothing else" at once; the real fixes are accepting it, a different box
(e.g. a `manual3` big slot), or a different photo. Compute `box_ratio`
vs. `im_ratio` and render the candidates before picking.

### Captions next to the cut line

Normal grid cells sit `MARGIN` (10 mm) inside the bleed edge, so a small
fixed caption padding is safe. `bleed2` and `portrait3_bleed` draw flush
against the true bleed edge; the same padding put captions inside the
~3 mm strip that is cut off. The renderer derives a trim-safe padding
from the profile (bleed strip width + `INSET`) for any side flush with the
bleed edge. Any new full-bleed style must do the same.

### Text slots

`photos.<idx>.text` replaces a grid cell's photo with a paragraph. The idx
must stay in the manifest: the grid still needs a real photo to plan and
measure against. `text_companion` brings the photo back as a square below
top-aligned text; `text_align: "right"` sets the text flush against a
photo to its right.

### A reversible feature flag for a repeatedly-revisited detail

The chapter-opener ridgeline (`style.chapter_silhouette`) went through
many tuning rounds before the user decided they didn't want it at all.
For a detail iterated on this often, don't delete the code when asked to
turn it off – gate it behind one flag so the work stays recoverable. It
is drawn seeded per day id, so it's reproducible.

## The print-ready export fix

**The bug.** Every print file delivered for Oberstdorf through round v9.6
was built by rendering our content and merging it with the publisher's
downloaded template PDFs. Those turned out to be pre-press **proof
sheets** – registration crosshairs, crop ticks, colour bars, a timestamp
header – not a blank canvas. Rendering them to PNG made that obvious in a
minute; until then nobody had looked, only checked their page size. The
merge target also had no `/TrimBox`/`/BleedBox`, so none survived. Two
stacked defects: visible marks in the art and no machine-readable trim.

The publisher's own InDesign guide says the opposite: no registration or
crop marks, and export the "raw format including bleed" – trim and bleed
travel as PDF box metadata, not ink.

**The fix.** No template merge at all. Our own rendered page IS the final
page; `set_print_boxes()` sets `/TrimBox` and `/BleedBox` with pypdf
(`pg.trimbox`, `pg.bleedbox`; settable since pypdf 3.x).

**Where correct geometry comes from.** Not from proof-sheet templates
already on disk. Have the user re-export from the publisher's placed
template with the documented settings, then read the boxes
(`profile-from-pdf`). It took two iterations here:

1. The first re-export had a correct cover with real bleed, but interior
   pages with **zero bleed** (media box = old trim size, no box keys). A
   cover/interior mismatch is a real print risk.
2. **Add bleed to the half missing it, never remove it from the half that
   has it.** Bleed absorbs cutting tolerance; zero bleed is what produces
   white edges. The interior was re-exported with 3 mm all around.

**Verifying a geometry change cheaply.** Render the cover plus one day
with a mix of page types (`--kind opener`, `--spreads`), rasterise
(`pdftoppm -r 150`) and look at it, and re-read the boxes with pypdf –
don't trust that the numbers you typed are the numbers in the file. Only
then the full build.

## Known pitfalls

- **Long builds vs. tool timeouts**: a full 300 dpi build can exceed a
  2-minute shell timeout. Run it in the background and follow the log.
  Review builds at lower `--dpi` are much faster.
- **DPI warnings**: photos below 200 dpi in their box are listed at the
  end of every build – check them before a print delivery.
- **f-strings**: `f"{x[\"key\"]}"` is a SyntaxError before Python 3.12;
  assign to a variable first.

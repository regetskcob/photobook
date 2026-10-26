# The pipeline, stage by stage

End-to-end path from raw photo exports to the print-ready PDF, as it
evolved over several rounds on "Oberstdorf 2026".

## 1. Raw material

Photos arrive as several large `.zip` archives (e.g. `Oberstdorf_01.zip`
… `Oberstdorf_12.zip`, 300–500 MB each), each with a mix of JPEG/HEIC
files from multiple cameras/phones. These archives stay zipped — nothing
gets fully extracted, which would be unnecessarily heavy for 1000+ photos.
Instead, individual files are read directly out of the zip on demand
(`zipfile` module, using the `entry` path from the manifest).

**HEIC pitfall:** Some modern iPhone photos are stored as "grid-type" HEIC
(split into tiles). The standard decode path via `pillow-heif`/`libheif`
regularly aborts on such files with an `iref`/aux-image validation error,
even though the file itself is perfectly fine. `scripts/heic_extract.py`
is a hand-written, minimal ISOBMFF box parser that pulls the primary
image's tiles directly out of the file, decodes them via `ffmpeg` (raw
HEVC decoder), and reassembles them with PIL. If a 2027 photo batch again
contains HEIC files, it's worth first checking whether the standard path
works before reaching for this workaround — but it's here if needed.
`scripts/batch_heic.py SRC_DIR OUT_DIR` converts a whole folder.

## 2. Full photo index (`recs_sorted.json`)

`scripts/build_index.py PROJECT_DIR SOURCES...` indexes **every** photo
across all zips and folders once: per photo an `idx` (a stable ID, never
reused, assigned in capture-time order), `zip`, `entry` (path inside the
zip), `datetime` (EXIF, for chronological sorting), `gps`,
`width`/`height` (upright), a `sharpness` score (for filtering out shaky
shots), a thumbnail in `thumbs/`, and `bytes`. This index is the foundation
for every later selection step and is never modified again – the script
refuses to overwrite it. Schema:
[`schema/manifest_schema.md`](../schema/manifest_schema.md).

## 3. Selection → `final_manifest.json`

A curated subset of the 1000+ photos is chosen (161 photos for the
Oberstdorf book). `scripts/make_manifest.py PROJECT_DIR --select
selection.txt` groups it into days by capture date, numbers it, writes the
photos upright to `fullres/` and creates a `book.json` skeleton. Each entry
gets, in addition to `idx`:

- `day`: the day key (e.g. `"Tag3_Fellhornbahn_Einoedsbach"`), must match
  a `days[].id` in `book.json`.
- `order`: an integer that (a) determines sort order within a day and
  (b) gets printed as a small number in the corner of each photo in
  review builds. **Important:** `order` must be unique across the *whole*
  book, not just per day – see the lesson in
  [`TEXTE_VORLAGE_PROTOCOL.md`](TEXTE_VORLAGE_PROTOCOL.md). The engine
  refuses duplicates.
- the photo file: either a `file` path per entry or a separate
  `fullres_idx_map.json` (`photo_map` in `book.json`).

Selection criteria in practice: sharpness (`sharpness` score), redundancy
(filtering out near-duplicate shots of the same scene), day coverage (no
day should end up empty), and subjective picks by the user from contact
sheets (see step 4).

## 4. Review material for the user

Before the finished design is worth reviewing, the user gets lightweight
overviews to check the selection against:

- `scripts/build_contact_sheets.py` – one thumbnail sheet per day, for
  rough triage of candidates.
- `python -m photobook build book.json --mode numbers` – the book in its
  real layout with big, readable photo numbers, as soon as a first
  `book.json` exists (a few days with titles is enough).
- `scripts/extract_photos.py` – copies photos by printed number out of
  the zip archives into a review folder.

These rounds produce the first user feedback (photos in/out, reorder) –
which flows straight back into `final_manifest.json`.

## 5. Curate texts (`Texte_Vorlage.md`)

In parallel with photo selection, the user writes texts (day intros,
captions, longer paragraphs) into a markdown template that references the
printed photo numbers (`order`). The format, and – very importantly – the
pitfalls, are documented in
[`TEXTE_VORLAGE_PROTOCOL.md`](TEXTE_VORLAGE_PROTOCOL.md). The texts end up
in `book.json` (`days[].intro`, `photos.<idx>.caption`, `.text`, …), keyed
by idx.

## 6. Build the book (`python -m photobook build`)

The engine reads `book.json`, the manifest and the product profile and
renders cover and interior. One code path, three modes: `review` (small
numbers, for proofreading), `numbers` (big numbers, for feedback rounds)
and `print` (no numbers, full resolution – the upload files). Every mode
sets `/TrimBox`/`/BleedBox` from the profile on our own rendered pages –
**no merge onto a publisher-supplied template**. An earlier version of
this pipeline did merge onto the publisher's downloaded template and
shipped visible crop/registration marks in every delivered file; see "The
print-ready export fix" in [`ENGINE.md`](ENGINE.md).

`python -m photobook pages book.json` prints the page plan (every spread
with its printed photo numbers) without rendering anything, and lists
photos that landed on no page.

## 7. Fast iteration loops

A full 84-page build at print resolution takes minutes – too slow for
layout iteration ("is the opener right now?"):

- **Partial renders**: `build ... --kind opener` or `--spreads 3-5`
  renders just those spreads, in seconds.
- **Lower resolution**: review and numbers builds default to 150/110 dpi;
  `--dpi` overrides.
- **Page-count search**: the product has a FIXED page count (Saal Digital
  "Professional Line" 30×21 cm: 84 interior pages), so photo count and
  grid batch sizes (`pattern`) must add up exactly.
  `python -m photobook pattern-search book.json` plans hundreds of
  `pattern` candidates per second (planning does no image I/O) and lists
  those that hit the page count.

## 8. Delivery

The finished cover and interior PDFs go to the user. Actual print files
always come from `--mode print`, never from a review or numbers build.
If you work through a remote device bridge with upload limits, see
[`DEVICE_DELIVERY.md`](DEVICE_DELIVERY.md).

**Important:** deliver the print files only after explicit user go-ahead –
not automatically after every build. For the Oberstdorf book that went
through an extra verification loop: a cover-only geometry test, then one
full day (opener, full-bleed panorama, plain grid and a hand-placed group
in one spread range) rendered and visually checked, *then* the full
42-spread build – see "Verifying a geometry change cheaply" in
[`ENGINE.md`](ENGINE.md).

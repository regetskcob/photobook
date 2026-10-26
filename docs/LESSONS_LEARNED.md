# Lessons learned – quick reference

Concrete bugs/pitfalls from the Oberstdorf 2026 project, in bullet form
for fast lookup. Fuller explanations are linked in each item.

- **Photo numbers aren't stable** → see
  [`TEXTE_VORLAGE_PROTOCOL.md`](TEXTE_VORLAGE_PROTOCOL.md). Renumber
  globally after every manifest change, or you get collisions/drift.
- **Overrides keyed by a batch's photo set silently go stale** – the old
  script's `MANUAL_GRID_ORDER` stopped matching whenever a photo was added
  earlier that day, with no error. The engine replaced it with `groups`
  (keyed by the photos themselves) and validates every idx reference
  against the manifest. See [`ENGINE.md`](ENGINE.md).
- **`idx` ≠ `order`** – `idx` is the stable photo ID (never reused),
  `order` is the printed, shiftable display number. Everything in
  `book.json` is keyed by `idx`. But user notes talk in `order`
  numbers ("photo 027") – always resolve that translation against the
  current manifest, never from memory/old notes.
- **`pattern` cycles per day, not globally** – its index resets at the
  start of every day in `build_day_units()`.
- **f-string with a backslash inside braces is invalid** – e.g.
  `f"{x[\"key\"]}"` raises a `SyntaxError`. Assign to a variable first:
  `k = x["key"]; f"{k}"`.
- **Default tool timeout (~2 minutes) isn't enough for full print
  builds** – run them in the background and follow the log; use lower
  `--dpi` or `--spreads`/`--kind` while iterating.
- **HEIC grid-type files break the standard decoder** – see
  `scripts/heic_extract.py`, a manual ISOBMFF box parser workaround.
- **Full-print-quality PDFs built unnecessarily often for pure review
  purposes** – ~110 dpi is enough for number/content checks and keeps the
  file small enough to send without chunking. `--mode numbers` defaults
  to that.
- **A portrait photo in a landscape-shaped box can't be fully fixed by
  `align` alone** – `load_crop()` only crops one axis; if source and box
  aspect ratios are far apart, "keep the whole subject" and "exclude
  everything else" can be mutually impossible. Compute `box_ratio` vs.
  `im_ratio` and render candidate crops before picking an alignment — see
  the worked example in [`ENGINE.md`](ENGINE.md).
- **Full-bleed grid styles need different caption padding** – any cell
  drawn flush against the true bleed edge (not the usual `MARGIN`-inset
  position) needs padding re-derived from the profile's bleed vs. trim
  box, or captions silently land in the strip that gets trimmed off at
  print. See "Captions next to the cut line" in [`ENGINE.md`](ENGINE.md).
- **Numbering-scheme drift can hide WITHIN a single `Texte_Vorlage.md`**,
  not just across rounds – a layout-only round that doesn't touch the text
  file leaves the door open for a later, big text update to mix old and
  new Bildnummern in one document. Resolve by matching caption TEXT against
  the `idx`-keyed entries in `book.json`, not by trusting the raw number. See
  [`TEXTE_VORLAGE_PROTOCOL.md`](TEXTE_VORLAGE_PROTOCOL.md).
- **A PDF viewer's own page counter IS the spread number** – when a user's
  page reference doesn't match your own reconstruction of past structure,
  the reconstruction is more likely wrong than the user. Ask for a
  screenshot/annotation of the actual current PDF before concluding a
  reference is stale or mistaken.
- **For a visual detail that's been iterated on repeatedly without landing
  ("turn it off for now")** – gate the call site behind a single flag
  (here `style.chapter_silhouette`) instead of deleting the code. Keeps all
  the tuning work recoverable with a one-line flip. See "A reversible
  feature flag" in [`ENGINE.md`](ENGINE.md).
- **Photo-SWAP requests need no renumbering** – resolve `order → idx`,
  point the photo's file (manifest `file` or `fullres_idx_map.json[idx]`)
  at the new one, done. Don't over-trust
  a replacement photo's EXIF date as a sanity check against its target day
  — this project's photos already have dates that don't match their
  narrative position.
- **A downloaded publisher "template" PDF may itself be a pre-press proof
  sheet, not a blank canvas** – this project's `templates/cover.pdf`/
  `pages.pdf` had visible registration crosshairs, crop tick marks, and
  colour bars baked in; `merge_page()`-ing rendered content onto them
  shipped those marks straight into every "final" PDF through round v9.6,
  and separately meant no `/TrimBox`/`/BleedBox` metadata survived either.
  Always render an unfamiliar template to PNG and actually look at it
  before merging content onto it — page *dimensions* matching is not the
  same as the file being upload-safe. See "The print-ready export fix" in
  [`ENGINE.md`](ENGINE.md).
- **Trim/bleed belongs in PDF box metadata (`/TrimBox`, `/BleedBox`), not
  as visible ink** – Saal Digital's own docs explicitly ask for no visible
  crop/registration marks and rely on the export's own bleed settings.
  `pypdf` (3.17.4+) can set `pg.trimbox`/`pg.bleedbox` directly — no
  template merge needed at all once you have your own rendered content.
- **When two halves of one deliverable (cover vs. interior pages) need
  matching bleed and only one has it, ADD bleed to the one missing it —
  never remove it from the one that already has it.** Zero bleed is what
  causes white-edge cutting artifacts, not the presence of bleed on the
  other half. This follows directly from what bleed is *for* (absorbing
  cutting-tolerance), so when in doubt, reason from the mechanics rather
  than from "make the numbers match" instinct.
- **A stale "format constants" section can look authoritative and still be
  wrong** – the original `COVER_TRIM`/`PAGES_TRIM`/etc. were measured from
  the flawed proof-sheet templates above and were themselves the vehicle
  for the mark/metadata bug. When re-measuring geometry, get it from a
  fresh export the user produces from the publisher's actual documented
  settings, not from whatever template file happens to already be on
  disk.

- **An edited export usually beats the camera original** – about one in
  fifteen photos in the original archive was a Photomator or Instagram
  export of a moment that also existed unedited; the edit was the one to
  keep. `build_index.py` marks them from the EXIF software tag. See
  [`CHOOSING_PHOTOS.md`](CHOOSING_PHOTOS.md).
- **Don't upscale a low-resolution image to silence the DPI check** – the
  original book's map was a generated illustration at ~1,500 px (≈127 dpi
  full-page). Keeping it at native size kept the warning visible and the
  decision with the user; an upscaled file would have looked "fine" in the
  log and soft in print.
- **Check photo order against GPS time, not just the camera clock** – when
  pages looked out of sequence, comparing EXIF time with GPS time showed the
  clocks were right and the bug was in the layout (a second highlight
  jumping to the start of its day). `scripts/gps_report.py` lists each
  day's stops with times.
- **The "InDesign export" can come from any layout program** – the Saal
  geometry was in fact exported from Affinity Publisher. What matters is
  "raw format incl. bleed, no marks", not the tool.

- **Measure resolution on the file, not on a reduced decode** – the
  renderer lets JPEG decoding shrink big photos for low-dpi review builds.
  The DPI check ran on that shrunken copy, so a 24 MP camera photo reported
  ~190 dpi: 41 false warnings on a real book, hiding the 2 real ones. It
  now uses the source's own size.
- **Low colour saturation isn't black and white** – fog, cloud and snow
  photos are nearly grey. A saturation threshold that looked safe (0.06)
  flagged 99 colour photos of a mountain trip; real b/w edits sit below
  0.01.
- **A photo count that is too low can still "fit" the page count** – only
  through many single-photo pages. Estimate photos from the page count
  (see [`CHOOSING_PHOTOS.md`](CHOOSING_PHOTOS.md)) before selecting, not
  after.

## Only when working through a remote device bridge

These came from a session where Claude worked in a cloud workspace and
reached the user's files through a device bridge. Irrelevant when running
locally.

- **Multiple copies of the same file in the user's folder** – e.g.
  `Texte_Vorlage.md` existed simultaneously in the main folder (an old,
  empty template Claude itself had written there), in `review/` (an
  orphaned upload leftover), and in `review/v3/` (the actually current,
  user-filled version). Before reading a reference file, ALWAYS check
  the real device folder (modification date!) instead of
  trusting whatever's most recently cached in the cloud workspace.
- **`device_bash` has no network and can't delete anything** – see
  [`DEVICE_DELIVERY.md`](DEVICE_DELIVERY.md).
- **`git` on the device-bridge mount can't `unlink()`** – `git add`/
  `git commit` still work functionally (verified via `git fsck`) but
  leave stray lock files behind that block the next call unless moved
  out of the way first. See [`DEVICE_DELIVERY.md`](DEVICE_DELIVERY.md).
  `git push` needs network the bridge doesn't have — ask the user to
  push themselves.

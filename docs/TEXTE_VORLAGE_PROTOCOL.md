# The `Texte_Vorlage.md` protocol

The convention through which the user provides texts and photo notes
without having to touch code or JSON directly. (The filename stays German
— `Texte_Vorlage` = "text template" — since that's what the user's own
working file is called; only this documentation is in English.)

## Format

A single markdown file, one section per day (`## Tag N · Title`), containing:

- A plain paragraph = the day's intro text (goes into the day's `intro` in `book.json`).
- `Bild NNN: Text` – a short caption for the photo currently printed with
  number `NNN` (goes into `photos.<idx>.caption`, where `idx` is resolved
  via `order == NNN` in the current manifest).
- `Bild NNN: $absatz` followed by the actual text on the next line(s) –
  marks a LONGER, narrative paragraph instead of just a short title
  (usually goes into `photos.<idx>.text` when the whole photo should be
  replaced by text, or as a longer `caption` when needed).
- `Hinweise:` (German for "notes") followed by bullet points – anything
  that isn't a plain text addition: remove/swap photos, reorder, fix crop
  alignment, etc. Almost always references printed `Bild NNN` numbers.

Book title/subtitle/closing text sit outside the day sections, at the
start/end (`# Buchtitel: ...`, `# Buchende: ...`).

## ⚠️ The most important lesson (round 5)

**The printed `Bild NNN` number is NOT stable.** It's the `order` value
from the manifest (see `ENGINE.md`), and `order` shifts whenever a
day's photo count changes — even for days that weren't touched
themselves, if a PRECEDING day gains/loses photos (because that shifts
all the numbering after it, unless `order` gets reassigned for the whole
book after every change).

What actually happened in round 5: the user had filled out
`Texte_Vorlage.md` against a specific PDF version
(`..._v2_reviewed.pdf`). Afterward, round 4 added three new photos
(2× day 5, 1× day 7). Only the `order` values for the directly affected
days (5 and 7) got reassigned — days 6 and 8 were left untouched. Result:
the `order` ranges of days 5/6 and 7/8 overlapped (two different photos
showed the same number), AND the numbers in the already-filled-out
`Texte_Vorlage.md` suddenly pointed at different photos than originally
intended.

**Rule derived from this for future rounds:**

1. After EVERY change to `final_manifest.json` (photos added/removed/
   moved between days), immediately reassign `order` for the WHOLE book
   (not just the changed day) — see the code snippet in `ENGINE.md`.
2. Before processing `Hinweise:` entries from a `Texte_Vorlage.md`, ALWAYS
   check whether the file still refers to the current photo/number state
   (compare file dates, spot-check one or two photo numbers against the
   current manifest).
3. After a round of photo changes, send the user a fresh, numbered
   reference PDF (`python -m photobook build book.json --mode numbers` –
   big readable numbers, low resolution, small file)
   BEFORE they write further notes referencing numbers.
4. Multiple copies of the same file can end up scattered in the user's
   folder (different subfolders, different ages). ALWAYS check the actual
   modification date before trusting a
   reference file — don't just trust the most recently uploaded/cached
   copy in the cloud workspace, it can be stale.

## Numbering drift ACROSS rounds (not just within one)

The round-5 lesson above covers a single bad round. A subtler version
showed up in round v9: a layout-only round (8.3) removed one photo but,
because it touched no text, `Texte_Vorlage.md` was never resent/rewritten
that round. When the user later filled out a curated `Texte_Vorlage.md` in
one sitting, it ended up mixing OLD (pre-8.3) Bildnummern for edits to
already-present captions with NEW (post-8.3) Bildnummern for fresh notes
written against the freshly-delivered post-8.3 reference PDF — both
numbering schemes present in the same document, no way to tell which
applies to which line from the number alone.

**Resolution technique that worked:** match the caption/description TEXT
content against the captions already in `book.json` (`photos.<idx>.caption`,
`hero`, `spread_caption` – keyed by `idx`, not `order`, and therefore
numbering-scheme-agnostic) to find the correct `idx`, rather than trusting
the raw number in isolation. If a note is clearly editing existing text
("change the wording of Bild 049's caption"), the CURRENT caption text is
the ground truth for which photo is meant, regardless of which round's
number the user happened to type. Only trust the raw number directly for
genuinely NEW notes written against a reference PDF you know is current.

When in doubt which scheme a batch of Hinweise uses, keep a backup of the
manifest from before the relevant round (e.g. `final_manifest.json.bak_before_round8_3`)
so the old→new `order` mapping can be reconstructed and cross-checked
(`old_by_order[o] → idx → new_by_idx[idx]`) instead of guessing.

## Trust the user's own screenshot over your own simulation

Round v9.2: the user referenced page numbers ("Seite 25", "Seite 32") that
didn't match any structure a manual re-simulation of an earlier round's
`pages_spec` produced — easy to conclude the numbers were simply wrong and
turn it into an open question back to the user. That conclusion was itself
wrong: it rested on a flawed assumption (that chronological EXIF order was
also the "narratively correct" order used to decide page placement), and
manually re-simulating a past round's structure by hand is exactly the kind
of derived, error-prone artifact that's easy to get subtly wrong.

What actually resolved it: the user sent screenshots of the actual
delivered PDF with their own annotations. The PDF viewer's own "Seite N von
42" counter directly IS the 1-indexed spread number — no simulation needed,
just trust it and read off `pages_spec[2*(N-1)]`/`[2*(N-1)+1]`. **When a
user's page/number reference doesn't seem to match anything, prefer asking
them to point at the actual current reference material (a screenshot, an
annotation) over reconstructing history by hand** — the reconstruction is
more likely to be the thing that's wrong.

## Photo-swap requests ("Bild NNN durch X.jpeg austauschen")

A request to swap the PHOTO at a given Bildnummer for a different image
(the user supplies a replacement file) is simpler than it looks and needs
**no renumbering at all**:

1. Resolve `order == NNN` in the current manifest to get that entry's
   `idx` (same lookup as any other Bildnummer reference).
2. Add the new file into the fullres pool with a sensible name (matching
   the existing `NNN_Day_OriginalFilename.ext` convention is fine even
   though the numeric prefix won't necessarily match `order` again later —
   it's just a filename, not read for meaning) and point the photo's file
   (manifest `file`, or `fullres_idx_map.json[idx]`) at it. The manifest entry itself
   (`idx`, `order`, `day`) is untouched.
3. Re-render just the affected spread(s) (`build --spreads N`)
   and LOOK at the result before rebuilding the whole book — check both
   that the new photo's content/orientation fits the box it lands in (a
   portrait replacement for a landscape slot, or vice versa, can reintroduce
   the cropping problem described in `ENGINE.md`) and that its
   thematic content actually fits the surrounding day/caption.

Don't over-trust EXIF datetime on a replacement photo as a sanity check —
this project's photo set already has photos with EXIF timestamps that don't
match their narrative position (see the round v9.2 lesson above), so a
replacement photo's date not matching its target day isn't by itself a
reason to question the swap if the visual content clearly fits.

## Additional photos / open questions

When the user mentions a photo that isn't in the selection yet ("more
photos", or a reference to an `additional`/`review` subfolder with extra
photos), first identify the photo in the full archive index
(`recs_sorted.json`) or on the device, then add it to
`final_manifest.json` (new `idx`, matching `day`, `order` at the end of
that day's range — then don't forget the global renumbering pass).

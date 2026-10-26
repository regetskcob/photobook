# photobook

A small layout engine that turns a curated photo selection plus a
`book.json` (texts, captions, which photo goes where) into print-ready
photobook PDFs – and the workflow and lessons from building a real one
(Saal Digital "Professional Line", 30×21 cm landscape, 84 interior pages /
42 spreads). Also packaged as a Claude skill, so Claude can run the whole
workflow with you.

The engine contains no book data and no product geometry: a book is a
`book.json` next to its photos, a print product is a profile JSON in
`profiles/`.

Two ways to use it: **with Claude** (install the skill, describe what you
want, review PDFs) or **by hand** (run the commands yourself). Both use
the same engine and files, so you can switch at any point.

## Starting a book with Claude

1. **Install the skill** – see [As a Claude skill](#as-a-claude-skill)
   below. You need Python 3.9+ with `reportlab pillow numpy pypdf`.
2. **Describe the goal in one message.** The more of these points you
   cover, the fewer rounds it takes – they are exactly what the original
   book had to settle after the fact:

   | Point | Why it matters |
   |---|---|
   | **Photos** – where (folder, zip exports), roughly how many, which devices, any edited versions | indexing reads them in place; edited exports are preferred over originals |
   | **Occasion and reader** – trip, wedding, year in review; for yourselves or a gift; tone | decides texts, cover, how personal captions get |
   | **Print product** – service, format, orientation, **fixed page count** | the layout is planned to the exact page count; other products need a profile from the service's template |
   | **Structure** – chapters by day, place or theme; what happens to short days (arrival, departure) | one chapter per capture day is the default |
   | **Selection** – you choose, or Claude drafts; must-haves and no-gos (people, screenshots, black and white) | a draft is mechanical: sharp, no bursts, spread over each day – not what a photo shows |
   | **Texts** – language, who writes them, how much (titles only, intros, captions) | placeholders and dates come in that language |
   | **Feedback** – who reviews, how (annotated PDF, screenshots, a text file per round) | every round starts from a PDF with big photo numbers |
   | **Deadline and delivery** – order date, where the PDFs should go | print files only on your explicit go-ahead |

   A brief that worked (write yours in any language):

   > I'd like a photobook of our week in the Alps, as a keepsake for the
   > two of us, personal in tone. The photos are 12 zip exports in
   > `~/Pictures/Alps 2026/`, from an iPhone and a Fujifilm camera, some
   > edited in Photomator. Printing at Saal Digital,
   > Professional Line 30×21 cm landscape, 84 interior pages. One chapter
   > per day; the departure morning only as the closing photo. Please
   > suggest a first draft of about 160 photos – selfies are fine,
   > screenshots not. We'll write the texts ourselves in German: chapter
   > intros and a few captions. We both give feedback on the numbered PDF.
   > We want to order by the end of June.

   Missing points aren't a problem – Claude asks for them before it
   starts, and suggests a default for each.
3. **What happens then:** Claude indexes the photos, shows contact sheets
   (and a suggested selection, if you asked for one), builds the manifest
   and a `book.json` skeleton for your page count, and sends a **numbers
   PDF** – every photo with a big printed number.
4. **Rounds:** you answer with notes by number ("037 crop from the top",
   "remove 041", "these three on one page") and your texts; Claude applies
   them, checks the result and sends the next PDF. See
   [Working in rounds](#working-in-rounds--tips-from-a-real-book).
5. **Print files** when you say go – cover and interior with trim/bleed
   set, ready to upload.

## Quickstart

```bash
git clone https://github.com/regetskcob/photobook.git && cd photobook
pip install -e .                                  # or: pip install reportlab pillow numpy pypdf
python examples/demo/make_demo_photos.py          # placeholder photos for the demo book
python -m photobook pages examples/demo/book.json # page plan, no rendering
python -m photobook build examples/demo/book.json --mode review
```

The PDFs land in `examples/demo/build/`.

| Command | Purpose |
|---|---|
| `build BOOK --mode print` | upload files: cover + interior, no numbers, 300 dpi, TrimBox/BleedBox set |
| `build BOOK --mode review` | the finished look with small photo numbers, for proofreading |
| `build BOOK --mode numbers` | big readable photo numbers, for feedback rounds ("Bild 037 bitte tauschen") |
| `build ... --spreads 3-5` / `--kind opener` | render only some spreads, in seconds |
| `check BOOK` | everything checkable without rendering: config, page count, duplicate photos |
| `pages BOOK` | page plan with printed numbers, unplaced photos |
| `renumber BOOK` | renumber photos through the whole book after adding/removing some |
| `pattern-search BOOK` | find grid batch sizes that hit the product's exact page count |
| `profile-from-pdf COVER PAGES` | read trim/bleed geometry from the publisher's template export |

## As a Claude skill

```bash
python scripts/package_skill.py        # -> dist/photobook/ and dist/photobook.skill
```

- **Claude Code**: copy `dist/photobook/` to `~/.claude/skills/photobook/`.
- **claude.ai**: upload `dist/photobook.skill` under Settings → Capabilities → Skills.

The skill's instructions are in [`skill/SKILL.md`](skill/SKILL.md); the
package bundles the engine, profiles, docs (as `references/`), helper
scripts and the demo book. It triggers when you ask Claude to make a
photobook from your photos, fix photos by their number, hit a page count
or produce print PDFs.

## A new book by hand

**Step by step: [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).** In short:

1. **Index your photos**: `scripts/build_index.py` reads zip exports and
   folders (HEIC included) into `recs_sorted.json` with thumbnails;
   `scripts/build_contact_sheets.py` lays them out per day.
2. **Choose**: write the idx values you want into `selection.txt` – or let
   `scripts/suggest_selection.py --pages 84` draft one to correct.
3. **Pick or create a product profile** – `profiles/` has the Saal Digital
   30×21 cm one; for another product, export the service's template as
   "raw format incl. bleed, no marks" and run `profile-from-pdf`. Read
   "The print-ready export fix" in [`docs/ENGINE.md`](docs/ENGINE.md)
   first.
4. **Build the skeleton**: `scripts/make_manifest.py . --select
   selection.txt --pages 84 --lang de` writes the manifest, upright photo
   files and a `book.json` that already fits the page count.
5. **Fill in `book.json`** – titles, texts, highlights, chapter openers;
   format in [`schema/book_schema.md`](schema/book_schema.md), every
   option in use in `examples/demo/book.json`.
6. **Iterate**: `check`, then `--mode numbers` for feedback rounds (resend
   after every photo change – the numbers shift, see
   [`docs/TEXTE_VORLAGE_PROTOCOL.md`](docs/TEXTE_VORLAGE_PROTOCOL.md)),
   `--mode review` for proofreading, `renumber` and `pattern-search` after
   adding or removing photos.
7. **Print files**: `--mode print` once everyone involved has said go.

## Structure

```
photobook/   the engine (book loading + validation, page planning, rendering, CLI)
profiles/    print product geometry
examples/    demo/: placeholder photos and a book.json using every feature
schema/      data formats: manifest, book.json
scripts/     helpers before the layout stage (HEIC, contact sheets, photo extraction), skill packaging
skill/       SKILL.md, the skill's instructions
docs/        workflow and lessons learned
tests/       python -m unittest discover tests (demo book + raw-zip-to-PDF pipeline)
```

## Docs

- [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) – a first book,
  command by command.
- [`docs/CHOOSING_PHOTOS.md`](docs/CHOOSING_PHOTOS.md) – selection
  criteria that held up: edited exports, series, sharpness, how many photos
  a page count needs.
- [`docs/PIPELINE.md`](docs/PIPELINE.md) – the full path from memory card
  to print file, stage by stage.
- [`docs/ENGINE.md`](docs/ENGINE.md) – how the engine plans and draws
  pages, and why: build modes, profiles, idx vs. printed number, page
  count, groups, page swaps, crop and caption pitfalls, the print-ready
  export fix.
- [`docs/TEXTE_VORLAGE_PROTOCOL.md`](docs/TEXTE_VORLAGE_PROTOCOL.md) – the
  text/notes collaboration with the user, and the numbering-drift lessons.
- [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) – concrete bugs and
  pitfalls in short bullet form.
- [`docs/DEVICE_DELIVERY.md`](docs/DEVICE_DELIVERY.md) – only for working
  through a remote device bridge: getting large files onto the user's
  device.

## Working in rounds – tips from a real book

The original book took about a dozen feedback rounds between two people
(one curating, one reviewing) before it was ordered. What worked:

**The loop**

1. **Build a numbers PDF** – `check book.json`, then `build book.json --mode numbers`. Big photo
   numbers, small file, easy to read on a phone or tablet. Put the round in
   the file name (`Book_numbers_round5.pdf`) so everyone knows which
   numbers a note refers to.
2. **Annotate** – the reviewer marks up the PDF in any annotation app
   (circles, arrows, "remove", "swap with 041") or sends screenshots of the
   page with notes on it. Screenshots beat descriptions: "page 25" in a PDF
   viewer is a spread, and your idea of the layout may be a round behind.
3. **Curate into one text file** – collect texts and notes per chapter in a
   markdown file instead of scattered messages:

   ```markdown
   ## Day 3 · Into the mountains
   A paragraph here becomes the chapter's intro text.

   Bild 034: Leaving for the summit            ← caption for photo 034
   Bild 041: $absatz                            ← a longer paragraph for photo 041
   The cable car swayed so much that …

   Hinweise:
   - 038 remove, 040 into the big slot instead
   - 045 crop from the top, heads are cut off
   ```

   Format and pitfalls: [`docs/TEXTE_VORLAGE_PROTOCOL.md`](docs/TEXTE_VORLAGE_PROTOCOL.md).
4. **Apply** to `book.json` (by hand, or let Claude do it with the skill):
   texts → `intro` / `caption` / `text`, crops → `crop`, "these three
   together" → `groups`, page order → `page_swaps`. Look every photo
   number up in the *current* plan (`photobook pages`).
5. **Check just what changed** – `build --mode review --spreads 12-14`,
   look at the spreads as images, fix, repeat. Seconds instead of minutes.
6. **Next round** – back to step 1.

**What changes the numbers – and what doesn't**

| Change | Numbers | Do afterwards |
|---|---|---|
| texts, captions, crops, groups, page swaps | stay | next round as usual |
| swap a photo for another file | stay | re-render that spread |
| remove or add photos | **shift** | `photobook renumber`, `pattern-search` if the page count broke, then a **fresh numbers PDF before anyone writes new notes** |

Notes written against an old numbers PDF are the most common source of
mistakes: two numbering schemes end up mixed in one notes file. Batch photo
removals into one round, renumber once, send the new PDF right away. When a
note edits an existing caption, the caption's text tells you which photo is
meant better than the number does.

**Before printing**

- Read the whole `--mode review` PDF once, cover to cover, just for typos.
- Check the low-resolution list at the end of the print build.
- Rasterise the cover and a few spreads of the `--mode print` PDFs and look
  at the edges: nothing important within ~5 mm of the trim.
- Upload only after everyone involved has said "go".

## What it does – and what's still up to you

**The engine and scripts do**

- index thousands of photos straight from zip exports (HEIC included),
  sort them by capture time, group them into days and number them
- plan the whole book to the product's exact page count, with chapter
  openers, grids, panoramas, full-bleed pages and text paragraphs
- keep typography, margins and captions consistent on every page, and keep
  captions clear of the cut line
- refuse broken settings loudly (a photo in the wrong chapter, duplicate
  numbers, pages that don't add up) instead of silently ignoring them
- produce review PDFs for every round and print PDFs with correct
  TrimBox/BleedBox, no marks
- with the Claude skill: turn notes like "Bild 015 oben ausrichten" into
  the right `book.json` change and re-render the affected spreads

**You still do**

- **Choose the photos.** The sharpness score only flags shaky shots; which
  photos tell the story is your call.
- **Write the texts** – titles, intros, captions.
- **Judge every crop by eye.** The engine has no face or subject detection;
  `crop: top` is a manual fix after you saw a cut-off head.
- **Edit photos** beforehand if needed. There is no colour correction,
  retouching or colour management: embedded colour profiles are dropped
  and every photo is treated as sRGB. Photos shot in Display P3 (most
  recent iPhones) can look slightly less saturated in print – convert them
  to sRGB first if that matters to you.
- **Pick the product and check its rules.** One profile ships (Saal Digital
  Professional Line 30×21 cm). For anything else, export the publisher's
  template and measure it (`profile-from-pdf`), and check their page
  counts, file size limits and colour requirements yourself.
- **Live with – or change – the design.** One fixed style (dark chapter
  openers, serif type, white grid margins); fonts and colours are
  configurable, anything beyond that means changing code. There is no
  drag-and-drop editor: layout happens in `book.json`.
- **Proofread, approve and order** at the print service.

## Origin

Built for a real book (ordered after review round v9.6). That book's
`book.json`, photos and print PDFs are private and not part of this repo.
The engine reproduces the original production script's output for it
page for page (verified on synthetic stand-in photos).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT, see [`LICENSE`](LICENSE).

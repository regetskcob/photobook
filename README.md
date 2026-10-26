# claude-book-helper

A small layout engine that turns a curated photo selection plus a
`book.json` (texts, captions, which photo goes where) into print-ready
photobook PDFs – and the workflow and lessons from building a real one
(Saal Digital "Professional Line", 30×21 cm landscape, 84 interior pages /
42 spreads). Also packaged as a Claude skill, so Claude can run the whole
workflow with you.

The engine contains no book data and no product geometry: a book is a
`book.json` next to its photos, a print product is a profile JSON in
`profiles/`.

## Quickstart

```bash
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

## A new book

**Step by step: [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).** In short:

1. **Index the raw material**: `scripts/build_index.py` reads zip
   archives and folders (HEIC included) into `recs_sorted.json`.
2. **Select**: `scripts/make_manifest.py` turns a list of chosen photos into
   `final_manifest.json`, upright photo files and a `book.json` skeleton –
   schema in [`schema/manifest_schema.md`](schema/manifest_schema.md).
3. **Pick or create a product profile** – `profiles/` has the Saal Digital
   30×21 cm one; for another product, export the publisher's template as
   "raw format incl. bleed, no marks" and run `profile-from-pdf`. Read
   "The print-ready export fix" in [`docs/ENGINE.md`](docs/ENGINE.md)
   first.
4. **Fill in `book.json`** – titles, texts, highlights; format in
   [`schema/book_schema.md`](schema/book_schema.md), every option in use in
   `examples/demo/book.json`.
5. **Curate texts with the user** – convention in
   [`docs/TEXTE_VORLAGE_PROTOCOL.md`](docs/TEXTE_VORLAGE_PROTOCOL.md).
   **Read this first**: photo numbers shift whenever the selection
   changes, and user notes refer to numbers.
6. **Iterate**: `--mode numbers` for feedback rounds (resend after every
   photo/order change), `--mode review` for proofreading,
   `pattern-search` when the page count no longer adds up.
7. **Print files**: `--mode print`, only after the user's explicit
   go-ahead.

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

## Origin

Built for a real book (ordered after review round v9.6). That book's
`book.json`, photos and print PDFs are private and not part of this repo.
The engine reproduces the original production script's output for it
page for page (verified on synthetic stand-in photos).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT, see [`LICENSE`](LICENSE).

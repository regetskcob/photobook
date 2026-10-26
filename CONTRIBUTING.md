# Contributing

Issues and pull requests are welcome – especially profiles for other print
products and layout styles.

## Setup

```bash
pip install -e .
python -m unittest discover tests
```

## Guidelines

- **No book data in the engine.** Anything specific to one book belongs in
  its `book.json`; anything specific to a print product belongs in a
  profile. New layout options get a `book.json` key with a default that
  keeps existing books rendering exactly as before.
- **Fail loudly.** A setting that silently stops applying (a stale idx, a
  page count that doesn't add up) cost whole review rounds on the original
  book. Validate new keys in `photobook/book.py` and name the day and what
  to change in the error.
- **Look at the output.** For any drawing change, render the demo book
  (`python examples/demo/make_demo_photos.py`, then `build --mode review`)
  and check the affected spreads as images, not just that the build runs.
- **New profiles**: measure from the publisher's own "raw format incl.
  bleed, no marks" export (`python -m photobook profile-from-pdf`), never
  from a proof-sheet template, and say in `source` where the numbers come
  from.
- Keep docs in English. The `Texte_Vorlage` template name and the German
  quotes in the docs are historical and stay as they are.

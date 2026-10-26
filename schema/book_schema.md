# `book.json` – one book's layout and texts

Everything specific to one book. Relative paths resolve against the
folder that contains `book.json`. Complete example:
[`../examples/demo/book.json`](../examples/demo/book.json) (every feature,
placeholder photos). How each mechanism behaves on the page:
[`../docs/ENGINE.md`](../docs/ENGINE.md).

**Every photo reference is an `idx`** (stable photo ID), never the printed
`order` number.

## Top level

| Key | Required | Meaning |
|---|---|---|
| `pages` | yes | exact interior page count of the product (e.g. 84) |
| `profile` | yes | name of a file in `profiles/` (without `.json`) or a path to a profile JSON |
| `pattern` | yes | cyclic grid batch sizes, e.g. `[2, 2, 2, 2, 3]`; restarts every day |
| `manifest` | no | photo list, default `final_manifest.json` |
| `photo_map` | no | JSON `{"idx": "path"}` for photo files; alternatively a `file` field per manifest entry |
| `output_prefix` | no | output file name prefix, default `book` |
| `day_label` | no | day label template, default `"Day {n}"` (e.g. `"Tag {n}"`) |
| `fill_odd_days_with_blank` | no | `true`: a day whose pages don't add up to whole spreads gets a blank page instead of an error – handy for drafts, `photobook pages` shows where. Default `false` |
| `style` | no | see below |
| `cover` | yes | `photo` (idx), `title`, `subtitle` |
| `front` | no | opening spread: `title`, `tagline`, `intro` (list of paragraphs), `image` (right page, e.g. a map; blank if absent) |
| `days` | yes | the chapters, in book order – see below. `chapters` works as an alias |
| `closing` | yes | closing spread: `photo` (idx, left page), `caption`, and `lead`, `headline`, `date` (text on the right page) |
| `page_swaps` | no | list of `{"a": [idx...], "b": [idx...]}` – swap two adjacent page blocks |
| `photos` | no | per-photo options, keyed by idx as a string – see below |

## `days[]`

| Key | Meaning |
|---|---|
| `id` | must match the manifest's `day` values |
| `title` | chapter title |
| `date` | shown in the opener tagline as `LABEL · DATE`; optional |
| `intro` | paragraph(s) on the opener page (string or list) |
| `number` / `label` | default: position in the list / `day_label` with that number |
| `opener` | idx of the full-bleed opener photo; without it the day has no opener spread |
| `inset` | idx of the small photo on the opener page; default: the day's first other photo |
| `hero` | `{"photo": idx, "caption": "..."}` – a captioned full-page highlight; `caption` may be `["bold line", "lighter line"]` |
| `hero_before_previous_page` | `true` swaps the hero with the page before it |
| `panorama_after_opener` | idx shown as a two-page spread right after the opener |
| `mid_day_panorama` | idx shown as a two-page spread at its chronological position |
| `solo_fullbleed` | idxs that get a full page of their own |
| `groups` | `[{"photos": [idx, idx, idx], "style": "..."}]` – styles: `manual3`, `portrait3`, `portrait3_bleed`, `mirror3`, `bleed2` |

The photos of a day that has no `days` entry are not placed (apart from
the cover and closing photos) – `photobook pages` lists them.

## `photos.<idx>`

| Key | Meaning |
|---|---|
| `caption` | caption on the photo (grid, solo page, inset) |
| `spread_caption` | caption of a two-page panorama |
| `crop` | `center` (default), `top`, `bottom`, `left`, `right` |
| `text` | the grid cell shows this paragraph instead of the photo |
| `text_companion` | `true`: the photo comes back as a square below the text |
| `text_align` | `left` (default) or `right` |

## `style`

| Key | Default |
|---|---|
| `font_regular` / `font_bold` / `font_italic` | `Times-Roman` / `Times-Bold` / `Times-Italic` (reportlab built-ins, Latin-1 only) |
| `font_files` | `{}` – e.g. `{"regular": "fonts/X.ttf", "bold": ..., "italic": ...}`; TTF files override the names above |
| `dark_color` | `[0.11, 0.13, 0.16]` – RGB 0–1, background of title, opener and closing pages |
| `text_color` | `[0.18, 0.18, 0.18]` – paragraphs on white pages |
| `caption_size` | `10.5` |
| `text_slot_size` | `13` |
| `chapter_icon` | `true` – small mountain mark on title and opener pages |
| `chapter_silhouette` | `false` – generated ridgeline on opener pages |

## Profile JSON

```json
{
  "name": "...",
  "cover": {"media": [x0, y0, x1, y1], "trim": [...], "bleed": [...]},
  "pages": {"media": [...], "trim": [...], "bleed": [...]}
}
```

PDF points. `pages` describes one double-page spread. Generate it with
`python -m photobook profile-from-pdf` from the publisher's template
export – see "Format profile" in [`../docs/ENGINE.md`](../docs/ENGINE.md).

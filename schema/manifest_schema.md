# Data formats

## `recs_sorted.json` – full photo index

One entry per photo across all zip archives and folders (1105 entries
for the original book), written by `scripts/build_index.py`, sorted by
capture time. Built once, never modified afterward.

```json
{
  "idx": 92,
  "zip": "Oberstdorf_02.zip",
  "entry": "Oberstdorf_02/IMG_1234.jpeg",
  "datetime": "2026-05-16T09:12:03",
  "gps": [48.1374, 11.5755],
  "width": 4032,
  "height": 3024,
  "camera": "Apple iPhone 15 Pro",
  "software": "Photomator 3.4.14",
  "edited": true,
  "sharpness": 182.4,
  "thumb": "thumbs/000092.jpg",
  "bytes": 3145728
}
```

- `idx`: stable, never-reused ID — every photo reference in `book.json`
  uses it.
- `zip` / `entry`: the archive and the path inside it – relative to the
  project folder for files inside it, absolute for sources elsewhere (so
  the project folder can move). For a loose file in a folder, `zip` is `null` and
  `entry` is the file path.
- `width` / `height`: upright size (camera rotation applied).
- `camera` / `software`: from EXIF. `edited` is true when `software` names
  a photo editor (Photomator, Lightroom, Instagram, …) – usually the
  version of a moment to keep.
- `sharpness`: variance of the Laplacian (higher = sharper), only
  meaningful relative to the other photos of the set – used to filter out
  shaky shots (`make_manifest.py --min-sharpness`). The original book's
  index used a `blur` score instead (lower = sharper).
- `error`: set instead of the image fields when a file couldn't be read.
- `thumb`: small preview image for contact sheets/review material.

## `final_manifest.json` – curated selection

A subset of `recs_sorted.json` entries (same base fields), plus:

```json
{
  "idx": 92,
  "zip": "Oberstdorf_02.zip",
  "entry": "Oberstdorf_02/IMG_1234.jpeg",
  "datetime": "2026-05-16T09:12:03",
  "day": "Tag2_Kanzelwandbahn_Sonnenuntergang",
  "order": 12
}
```

- `day`: must match a `days[].id` in `book.json` (photos of other days
  are not placed, except the cover and closing photo).
- `file` (optional): path to the photo, relative to the manifest. Without
  it, `book.json` needs a `photo_map` (see below).
- `order`: sort key within the day AND the number printed on the page.
  **Must be unique across the whole book** — see
  [`../docs/TEXTE_VORLAGE_PROTOCOL.md`](../docs/TEXTE_VORLAGE_PROTOCOL.md).

## `fullres_idx_map.json` – photo files by idx

Referenced as `photo_map` in `book.json`. Maps `idx` (as a string) to a
photo file, relative to `book.json` – the engine reads photos from here
(or from a manifest `file` field), never from the zip archives. Also how
extra photos from another source (uploaded later) get in:

```json
{
  "564": "fullres/NEW4_idx564_IMG_3582.jpeg",
  "567": "fullres/NEW4_idx567_dji_fly_642.jpeg"
}
```

Naming convention for newly added files: `NEW<round>_idx<idx>_<original filename>`
— makes it obvious at a glance which round a photo was added in.

## `Texte_Vorlage.md`

See [`../docs/TEXTE_VORLAGE_PROTOCOL.md`](../docs/TEXTE_VORLAGE_PROTOCOL.md)
for the full format including an example.

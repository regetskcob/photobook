# Choosing photos

How the original book got from 1,105 photos in 12 zip exports to the ~160
in print, and what to look at in `recs_sorted.json` and the contact sheets
along the way. Taste stays yours – these are the criteria that held up
over a dozen review rounds.

## Criteria that worked

- **Prefer versions someone already edited.** If a moment exists both as
  the raw camera file and as an edited export (Photomator, Lightroom,
  Instagram, …), take the edit – someone already decided how it should
  look. `build_index.py` marks these as `"edited": true` (from the EXIF
  software tag), and the contact sheets flag them.
- **Thin out series to one or two favourites.** Bursts and near-identical
  shots (fog studies on a grey morning, ten frames of the same view) make
  pages repetitive. Photos taken seconds apart are usually one series –
  pick the sharpest or best-composed.
- **Sharp and well exposed first.** `sharpness` (higher = sharper) is only
  comparable within one set and one camera; use it to find shaky outliers,
  not to rank good photos. Check blown highlights by eye.
- **Mix the subjects.** Landscape and panorama, people, animals, details
  (food, coffee, a postcard), places. A day of only landscapes reads flat.
- **Leave out black-and-white edits** in an otherwise colour book – they
  stand out on a page full of colour photos rather than in a good way.
- **Every day needs enough material.** A chapter with one or two photos
  can't fill its own spreads; fold it into a neighbour or make it the
  closing spread (as the original book did with the departure day).
- **Check the order, not just the set.** Camera clocks can be off, and
  photos from several devices interleave. If something feels out of
  sequence, compare capture time with GPS position (`gps_report.py`) before
  moving anything.

## How many

Each chapter takes 2 photos for its opener spread (the big photo and the
small inset), the closing spread takes 1, and every remaining page about
2.2:

    photos ≈ 2 × chapters + 1 + 2.2 × (pages − 4 − 2 × chapters)

84 pages with 7 chapters: 14 + 1 + 2.2 × 66 ≈ 160 – the original book had
161. Too few photos and the page count can only be met with many
single-photo pages; too many and the grids get small, which also lowers
the effective resolution per photo. `suggest_selection.py --pages N` uses
this estimate; `python -m photobook pattern-search book.json` shows what's
achievable with the photos you have.

## A first draft by script

`scripts/suggest_selection.py PROJECT --pages 84` applies the criteria
above mechanically: bursts collapse to one photo (edited export, else the
sharpest), shaky outliers per day, black-and-white edits and files under
2,400 px are dropped, each day gets a share that grows with its number of
photos, and picks are spread over the day with no two look-alikes minutes
apart. It writes `selection.txt` with a comment per photo. It can't judge
what a photo shows – a dashboard shot through the windscreen can be the
sharpest photo of the morning. Go through its pick on contact sheets.

Black and white is detected as practically zero colour saturation. Fog,
cloud and snow photos are low in saturation too but not zero: on the
original archive, a threshold of 0.06 took 99 fog shots for black and
white; the script uses 0.012.

## Resolution

A photo printed across a full page needs about 3,500 px on the long side
for 300 dpi on a 30 cm page; 200 dpi is the warning threshold. Phone
photos are fine full-page; crops, screenshots, messenger copies and
generated illustrations often aren't. **Don't upscale a small image to make
the warning go away** – the original book's map was an illustration at
~1,500 px (≈127 dpi full-page); keeping it at native size kept the check
honest, and the decision (accept it, or make it smaller) stayed visible.

## Naming chapters and places

`scripts/gps_report.py` groups each day's photos into time windows with a
map link per stop. That's usually enough to name chapters and captions
("cable car up", "the gorge") without guessing from the photos alone.

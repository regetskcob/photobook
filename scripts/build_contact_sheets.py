"""Contact sheets for a first rough review: one JPEG per day, thumbnails with labels.

Input is a JSON list of photos, e.g. recs_sorted.json from build_index.py
or a list of candidate favourites. Each entry needs `file` or `thumb` (path
relative to the JSON file); it is grouped by `day`, or by capture date when
there is no `day`. `idx`, `order` and the time are shown in the label.

    python scripts/build_contact_sheets.py PROJECT_DIR/recs_sorted.json --out contact_sheets
"""
import argparse
import json
import os
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont, ImageOps

THUMB_W = 340
THUMB_H = 260
PAD = 10
LABEL_H = 40
COLS = 4

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
    "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS
    "C:/Windows/Fonts/arial.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def image_of(r):
    return r.get('file') or r.get('thumb')


def label_for(r):
    parts = []
    if 'order' in r:
        parts.append(f"{r['order']:03d}")
    if 'idx' in r:
        parts.append(f"idx {r['idx']}")
    parts.append(os.path.basename(r.get('entry') or image_of(r)))
    if r.get('datetime'):
        parts.append(r['datetime'][11:16])
    return "  ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('photos', help='JSON list with day + file per photo')
    ap.add_argument('--out', default='contact_sheets')
    ap.add_argument('--title', default='', help='added to each sheet heading')
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(args.photos))
    with open(args.photos) as f:
        rows = json.load(f)
    by_day = defaultdict(list)
    for r in rows:
        if image_of(r):
            by_day[r.get('day') or (r.get('datetime') or 'undated')[:10]].append(r)
    font, font_b = load_font(14), load_font(15)
    os.makedirs(args.out, exist_ok=True)

    for day, items in sorted(by_day.items()):
        n = len(items)
        cols = min(COLS, n)
        rows_n = (n + cols - 1) // cols
        cell_w = THUMB_W + PAD
        cell_h = THUMB_H + LABEL_H + PAD
        sheet = Image.new('RGB', (cols * cell_w + PAD, rows_n * cell_h + PAD + 40), 'white')
        d = ImageDraw.Draw(sheet)
        heading = f"{day} – {args.title} ({n})" if args.title else f"{day} ({n})"
        d.text((PAD, 8), heading, font=font_b, fill='black')
        for i, r in enumerate(items):
            row, col = divmod(i, cols)
            x = PAD + col * cell_w
            y = 40 + PAD + row * cell_h
            try:
                with Image.open(os.path.join(base, image_of(r))) as src:
                    im = ImageOps.exif_transpose(src)
                    im.thumbnail((THUMB_W, THUMB_H))
                    sheet.paste(im, (x + (THUMB_W - im.width) // 2, y + (THUMB_H - im.height) // 2))
            except Exception as e:
                d.text((x + 5, y + 5), f"ERR {e}", font=font, fill='red')
            d.rectangle([x, y, x + THUMB_W, y + THUMB_H], outline='gray')
            d.text((x, y + THUMB_H + 4), label_for(r), font=font, fill='black')
        out = os.path.join(args.out, f'{day}.jpg')
        sheet.save(out, quality=85)
        print('wrote', out, sheet.size)


if __name__ == '__main__':
    main()

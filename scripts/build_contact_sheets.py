"""Contact sheets for a first rough review: one JPEG per day, thumbnails with labels.

Input is a JSON list of photos, e.g. recs_sorted.json from build_index.py
or a list of candidate favourites. Each entry needs `file` or `thumb` (path
relative to the JSON file); it is grouped by `day`, or by capture date when
there is no `day`. `idx`, `order` and the time are shown in the label;
edited exports get an orange frame.

    python scripts/build_contact_sheets.py PROJECT_DIR/recs_sorted.json --out contact_sheets
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont, ImageOps

THUMB_W = 340
THUMB_H = 260
PAD = 10
LABEL_H = 40
COLS = 4
ROWS_PER_SHEET = 6  # 24 photos per image - taller sheets are unreadable on screen

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


def day_of(iso, start_hour):
    if not iso:
        return 'undated'
    return (datetime.fromisoformat(iso) - timedelta(hours=start_hour)).date().isoformat()


def image_of(r):
    return r.get('file') or r.get('thumb')


def label_for(r):
    """Two lines: what you choose by (number, idx, time, sharpness, edited),
    then the file name, which is only for finding the original."""
    parts = []
    if 'order' in r:
        parts.append(f"{r['order']:03d}")
    if 'idx' in r:
        parts.append(f"idx {r['idx']}")
    if r.get('datetime'):
        parts.append(r['datetime'][11:16])
    if r.get('sharpness') is not None:
        parts.append(f"sharp {r['sharpness']:.0f}")
    if r.get('edited'):
        parts.append("EDITED")
    return "  ".join(parts), os.path.basename(r.get('entry') or image_of(r))


def fit(d, text, font, width):
    """Shorten from the middle until the text fits the cell."""
    if d.textlength(text, font=font) <= width:
        return text
    while len(text) > 8 and d.textlength(text[:len(text) // 2 - 1] + "…" + text[len(text) // 2 + 1:], font=font) > width:
        text = text[:len(text) // 2 - 1] + text[len(text) // 2 + 1:]
    return text[:len(text) // 2 - 1] + "…" + text[len(text) // 2 + 1:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('photos', help='JSON list with day + file per photo')
    ap.add_argument('--out', help='output folder (default: contact_sheets/ next to the JSON file)')
    ap.add_argument('--title', default='', help='added to each sheet heading')
    ap.add_argument('--day-start-hour', type=int, default=4, help='same day boundary as make_manifest.py')
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(args.photos))
    with open(args.photos) as f:
        rows = json.load(f)
    by_day = defaultdict(list)
    for r in rows:
        if image_of(r):
            by_day[r.get('day') or day_of(r.get('datetime'), args.day_start_hour)].append(r)
    font, font_b = load_font(14), load_font(15)
    out_dir = args.out or os.path.join(base, 'contact_sheets')
    os.makedirs(out_dir, exist_ok=True)

    per_sheet = COLS * ROWS_PER_SHEET
    for day, all_items in sorted(by_day.items()):
        n_sheets = (len(all_items) + per_sheet - 1) // per_sheet
        for sheet_no in range(n_sheets):
            items = all_items[sheet_no * per_sheet:(sheet_no + 1) * per_sheet]
            name = f"{day}_{sheet_no + 1}.jpg" if n_sheets > 1 else f"{day}.jpg"
            heading = f"{day}{' – ' + args.title if args.title else ''} ({len(all_items)})"
            if n_sheets > 1:
                heading += f", sheet {sheet_no + 1}/{n_sheets}"
            draw_sheet(items, heading, os.path.join(out_dir, name), base, font, font_b)


def draw_sheet(items, heading, out, base, font, font_b):
    n = len(items)
    cols = min(COLS, n)
    rows_n = (n + cols - 1) // cols
    cell_w = THUMB_W + PAD
    cell_h = THUMB_H + LABEL_H + PAD
    sheet = Image.new('RGB', (cols * cell_w + PAD, rows_n * cell_h + PAD + 40), 'white')
    d = ImageDraw.Draw(sheet)
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
        # edited exports get a thick orange frame: usually the version to keep
        if r.get('edited'):
            d.rectangle([x - 3, y - 3, x + THUMB_W + 3, y + THUMB_H + 3], outline=(230, 120, 0), width=4)
        else:
            d.rectangle([x, y, x + THUMB_W, y + THUMB_H], outline='gray')
        line1, line2 = label_for(r)
        d.text((x, y + THUMB_H + 3), fit(d, line1, font, THUMB_W), font=font, fill='black')
        d.text((x, y + THUMB_H + 20), fit(d, line2, font, THUMB_W), font=font, fill=(110, 110, 110))
    sheet.save(out, quality=85)
    print('wrote', out, sheet.size)


if __name__ == '__main__':
    main()

"""Turn a selection from the index into final_manifest.json, photo files and a book.json skeleton.

    python scripts/make_manifest.py PROJECT_DIR --select selection.txt
    python scripts/make_manifest.py PROJECT_DIR --all --min-sharpness 40

The selection file lists idx values from recs_sorted.json (one per line, or
a JSON list; '#' starts a comment). Photos are grouped into days by capture
date (a day starts at --day-start-hour, so a 1 a.m. photo still belongs to
the evening before), numbered through the whole book, and written to
fullres/ as JPEG with the camera orientation applied.

Writes final_manifest.json, fullres_idx_map.json and - only if there is
none yet - a book.json skeleton with one chapter per day. Refuses to
overwrite an existing manifest: after the first round, edit it and run
`python -m photobook renumber book.json` instead.
"""
import argparse
import io
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timedelta

from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from photo_source import open_image, read_bytes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_selection(path):
    with open(path) as f:
        text = f.read()
    try:
        return [int(i) for i in json.loads(text)]
    except ValueError:
        return [int(m) for line in text.splitlines() for m in re.findall(r'\d+', line.split('#')[0])[:1]]


def day_key(rec, start_hour):
    if not rec.get('datetime'):
        return 'undated'
    return (datetime.fromisoformat(rec['datetime']) - timedelta(hours=start_hour)).date().isoformat()


def write_photo(rec, project_dir, out_rel):
    """JPEGs without a rotation flag are copied byte for byte; everything
    else is decoded, turned upright and re-encoded."""
    src_zip = os.path.join(project_dir, rec['zip']) if rec['zip'] else None
    entry = rec['entry'] if rec['zip'] else os.path.join(project_dir, rec['entry'])
    out_path = os.path.join(project_dir, out_rel)
    if os.path.exists(out_path):
        return
    ext = os.path.splitext(entry)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        data = read_bytes(src_zip, entry)
        with Image.open(io.BytesIO(data)) as probe:
            upright = probe.getexif().get(0x0112, 1) == 1
        if upright:
            with open(out_path, 'wb') as f:
                f.write(data)
            return
    im = ImageOps.exif_transpose(open_image(src_zip, entry)).convert('RGB')
    im.save(out_path, quality=93)


def skeleton(days, profile):
    # undated photos stay out of the chapters until someone sorts them in
    days = {d: idxs for d, idxs in days.items() if d != 'undated'}
    first_day = next(iter(days.values()))
    last_day = list(days.values())[-1]
    closing = last_day[-1]
    return {
        "pages": 0,
        "profile": profile,
        "pattern": [2, 3],
        "manifest": "final_manifest.json",
        "photo_map": "fullres_idx_map.json",
        "output_prefix": "book",
        "day_label": "Day {n}",
        # first drafts often leave a day one page short - fill it instead of failing
        "fill_odd_days_with_blank": True,
        "cover": {"photo": first_day[0], "title": "TITLE", "subtitle": "subtitle · dates"},
        "front": {"title": "TITLE", "tagline": "TAGLINE", "intro": ["Intro paragraph."]},
        "days": [
            dict({"id": day_id, "title": "Title of this day", "date": day_id, "intro": []},
                 **({"opener": idxs[0]} if idxs[0] != closing else {}))
            for day_id, idxs in days.items()
        ],
        "closing": {"photo": closing, "caption": "", "lead": "", "headline": "THE END", "date": ""},
        "photos": {},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project_dir')
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument('--select', help='file with the chosen idx values')
    sel.add_argument('--all', action='store_true', help='take every readable photo')
    ap.add_argument('--min-sharpness', type=float, help='drop photos below this sharpness score')
    ap.add_argument('--day-start-hour', type=int, default=4)
    ap.add_argument('--profile', default='saal_professional_30x21_landscape')
    args = ap.parse_args()

    pd = args.project_dir
    manifest_path = os.path.join(pd, 'final_manifest.json')
    if os.path.exists(manifest_path):
        sys.exit(f"{manifest_path} exists - edit it and run `python -m photobook renumber book.json` instead")
    with open(os.path.join(pd, 'recs_sorted.json')) as f:
        recs = json.load(f)
    by_idx = {r['idx']: r for r in recs}

    if args.all:
        chosen = [r['idx'] for r in recs if 'error' not in r]
    else:
        chosen = read_selection(args.select)
        missing = [i for i in chosen if i not in by_idx or 'error' in by_idx[i]]
        if missing:
            sys.exit(f"not in the index or unreadable: {missing}")
    if args.min_sharpness is not None:
        dropped = [i for i in chosen if by_idx[i].get('sharpness', 0) < args.min_sharpness]
        chosen = [i for i in chosen if i not in dropped]
        print(f"dropped {len(dropped)} photos below sharpness {args.min_sharpness}")
    chosen = sorted(set(chosen), key=lambda i: (by_idx[i].get('datetime') or '9999', i))

    days = OrderedDict()
    for i in chosen:
        days.setdefault(day_key(by_idx[i], args.day_start_hour), []).append(i)
    if 'undated' in days:
        days.move_to_end('undated')
        print(f"{len(days['undated'])} photos without capture time are in day 'undated' - move them by hand")

    os.makedirs(os.path.join(pd, 'fullres'), exist_ok=True)
    manifest, photo_map, order = [], {}, 1
    for day_id, idxs in days.items():
        for i in idxs:
            rec = by_idx[i]
            stem = re.sub(r'[^A-Za-z0-9_\-]+', '_', os.path.splitext(os.path.basename(rec['entry']))[0])
            rel = f"fullres/{i:05d}_{stem}.jpg"
            write_photo(rec, pd, rel)
            photo_map[str(i)] = rel
            manifest.append({'idx': i, 'day': day_id, 'order': order, 'datetime': rec.get('datetime'),
                             'zip': rec['zip'], 'entry': rec['entry']})
            order += 1
        print(f"{day_id}: {len(idxs)} photos", flush=True)

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    with open(os.path.join(pd, 'fullres_idx_map.json'), 'w') as f:
        json.dump(photo_map, f, indent=1)
    print(f"wrote {len(manifest)} photos to final_manifest.json and fullres/")

    book_path = os.path.join(pd, 'book.json')
    if not os.path.exists(book_path):
        book = skeleton(days, args.profile)
        sys.path.insert(0, ROOT)
        from photobook.book import Book
        from photobook.layout import LayoutError, plan
        with open(book_path, 'w') as f:
            json.dump(book, f, indent=2, ensure_ascii=False)
        try:
            book["pages"] = len(plan(Book(book_path), check_page_count=False))
        except LayoutError as e:
            print(f"note: {e}")
        with open(book_path, 'w') as f:
            json.dump(book, f, indent=2, ensure_ascii=False)
        print(f"wrote a book.json skeleton ({book['pages']} pages as planned now). Set 'pages' to your "
              "product's page count and run `python -m photobook pattern-search book.json`.")


if __name__ == '__main__':
    main()

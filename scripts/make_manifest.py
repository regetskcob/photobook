"""Turn a selection from the index into final_manifest.json, photo files and a book.json skeleton.

    python scripts/make_manifest.py PROJECT_DIR --select selection.txt
    python scripts/make_manifest.py PROJECT_DIR --all --min-sharpness 40

The selection file lists idx values from recs_sorted.json (one per line, or
a JSON list; '#' starts a comment). Photos are grouped into days by capture
date (a day starts at --day-start-hour, so a 1 a.m. photo still belongs to
the evening before), numbered through the whole book, and written to
fullres/ as JPEG with the camera orientation applied.

Days with fewer than --min-day-photos photos (a departure morning with two
shots) are folded into the day before. fullres/ holds full-resolution
copies for print - plan about 6 MB per photo.

Writes final_manifest.json, fullres_idx_map.json and - only if there is
none yet - a book.json skeleton with one chapter per day: the sharpest
landscape photo of each day as its opener, the best landscape photo
overall as cover, placeholder texts in --lang. Refuses to overwrite an
existing manifest: after the first round, edit it and run
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

TEXTS = {
    'en': {'day_label': 'Day {n}', 'day_title': 'Title of this day', 'title': 'TITLE',
           'subtitle': 'Subtitle · dates', 'tagline': 'TAGLINE', 'intro': 'Intro paragraph.',
           'headline': 'THE END',
           'weekdays': 'Monday Tuesday Wednesday Thursday Friday Saturday Sunday',
           'months': 'January February March April May June July August September October November December',
           'date': '{weekday}, {day} {month} {year}'},
    'de': {'day_label': 'Tag {n}', 'day_title': 'Titel dieses Tages', 'title': 'TITEL',
           'subtitle': 'Untertitel · Daten', 'tagline': 'UNTERZEILE', 'intro': 'Einleitungstext.',
           'headline': 'ENDE',
           'weekdays': 'Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonntag',
           'months': 'Januar Februar März April Mai Juni Juli August September Oktober November Dezember',
           'date': '{weekday}, {day}. {month} {year}'},
}


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


def format_date(day_id, t):
    if day_id == 'undated':
        return ""
    d = datetime.fromisoformat(day_id)
    return t['date'].format(weekday=t['weekdays'].split()[d.weekday()], day=d.day,
                            month=t['months'].split()[d.month - 1], year=d.year)


def best_photos(idxs, by_idx):
    """Best first: edited exports, then landscape format (openers and the
    cover fill a landscape page), then sharpness relative to the rest of
    the group - absolute scores differ a lot between scenes and cameras."""
    by_sharp = sorted(idxs, key=lambda i: by_idx[i].get('sharpness', 0))
    pct = {i: n / max(1, len(idxs) - 1) for n, i in enumerate(by_sharp)}

    def score(i):
        r = by_idx[i]
        landscape = r.get('width', 0) >= 1.2 * r.get('height', 1)
        return (bool(r.get('edited')), landscape, pct[i])
    return sorted(idxs, key=score, reverse=True)


def skeleton(days, by_idx, profile, lang, output_prefix):
    t = TEXTS[lang]
    # undated photos stay out of the chapters until someone sorts them in
    days = {d: idxs for d, idxs in days.items() if d != 'undated'}
    closing = list(days.values())[-1][-1]
    chapters, openers = [], []
    for day_id, idxs in days.items():
        ranked = [i for i in best_photos(idxs, by_idx) if i != closing]
        chapter = {"id": day_id, "title": t['day_title'], "date": format_date(day_id, t), "intro": []}
        if ranked:
            chapter["opener"] = ranked[0]
            openers.append(ranked[0])
            if len(ranked) > 1:
                # the default inset (the day's first photo) is often a throwaway shot
                chapter["inset"] = ranked[1]
        chapters.append(chapter)
    cover = best_photos([i for idxs in days.values() for i in idxs], by_idx)[0]
    return {
        "pages": 0,
        "profile": profile,
        "pattern": [2, 3],
        "manifest": "final_manifest.json",
        "photo_map": "fullres_idx_map.json",
        "output_prefix": output_prefix,
        "day_label": t['day_label'],
        # first drafts often leave a day one page short - fill it instead of failing
        "fill_odd_days_with_blank": True,
        "cover": {"photo": cover, "title": t['title'], "subtitle": t['subtitle']},
        "front": {"title": t['title'], "tagline": t['tagline'], "intro": [t['intro']]},
        "days": chapters,
        # the last photo of the trip closes the book; it is not part of its day's pages
        "closing": {"photo": closing, "caption": "", "lead": "", "headline": t['headline'], "date": ""},
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
    ap.add_argument('--min-day-photos', type=int, default=5,
                    help='fold days with fewer photos into the day before')
    ap.add_argument('--profile', default='saal_professional_30x21_landscape')
    ap.add_argument('--pages', type=int, help="the product's interior page count (default: as planned)")
    ap.add_argument('--lang', choices=sorted(TEXTS), default='en', help='language of placeholders and dates')
    ap.add_argument('--name', default='book', help='output file prefix')
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
    for day_id in [d for d, idxs in days.items() if d != 'undated' and len(idxs) < args.min_day_photos]:
        keys = [d for d in days if d != 'undated']
        if len(keys) < 2:
            break
        pos = keys.index(day_id)
        target = keys[pos - 1] if pos > 0 else keys[1]
        moved = days.pop(day_id)
        days[target] = sorted(days[target] + moved, key=lambda i: (by_idx[i].get('datetime') or '9999', i))
        print(f"{day_id}: only {len(moved)} photo(s) - folded into {target}")

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
    megabytes = sum(os.path.getsize(os.path.join(pd, rel)) for rel in photo_map.values()) / 1e6
    print(f"wrote {len(manifest)} photos to final_manifest.json and fullres/ ({megabytes:.0f} MB)")

    book_path = os.path.join(pd, 'book.json')
    if not os.path.exists(book_path):
        book = skeleton(days, by_idx, args.profile, args.lang, args.name)
        sys.path.insert(0, ROOT)
        from photobook.book import Book
        from photobook.layout import LayoutError, plan
        with open(book_path, 'w') as f:
            json.dump(book, f, indent=2, ensure_ascii=False)
        try:
            planned = len(plan(Book(book_path), check_page_count=False))
            book["pages"] = args.pages or planned
        except LayoutError as e:
            print(f"note: {e}")
        with open(book_path, 'w') as f:
            json.dump(book, f, indent=2, ensure_ascii=False)
        if args.pages:
            print(f"wrote a book.json skeleton for {args.pages} pages - run "
                  "`python -m photobook pattern-search book.json` if `pages` reports a different count.")
        else:
            print(f"wrote a book.json skeleton ({book['pages']} pages as planned now). Set 'pages' to your "
                  "product's page count and run `python -m photobook pattern-search book.json`.")


if __name__ == '__main__':
    main()

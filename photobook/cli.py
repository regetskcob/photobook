"""Command line: python -m photobook <command> ...

  build           render the book (print / review / numbers mode)
  pages           print the page plan with printed photo numbers, no rendering
  renumber        renumber the printed photo numbers after adding/removing photos
  pattern-search  find PATTERNs that hit the book's exact page count
  profile-from-pdf  read page geometry from a publisher template export
"""
import argparse
import itertools
import json
import os
import sys

from .book import Book, BookError
from .layout import LayoutError, describe, plan, unplaced_photos

# print: upload files for the publisher - no numbers, full resolution
# review: proof of the finished look, with the small discreet numbers
# numbers: big readable numbers, for feedback rounds by number
MODES = {
    'print': {'tag_numbers': 'off', 'dpi': 300, 'cover': True},
    'review': {'tag_numbers': 'small', 'dpi': 150, 'cover': True},
    'numbers': {'tag_numbers': 'big', 'dpi': 110, 'cover': False},
}


def parse_spreads(text):
    """'0,3-5' -> [0, 3, 4, 5]"""
    out = []
    for part in text.split(','):
        if '-' in part:
            a, b = part.split('-')
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def _load(path):
    book = Book(path)
    for w in book.warnings:
        print("warning:", w, file=sys.stderr)
    return book


def cmd_build(args):
    from .render import Renderer, set_print_boxes

    book = _load(args.book)
    pages_spec = plan(book)
    mode = MODES[args.mode]
    r = Renderer(book, tag_numbers=mode['tag_numbers'], target_dpi=args.dpi or mode['dpi'])

    spreads = None
    if args.spreads:
        spreads = parse_spreads(args.spreads)
    if args.kind:
        spreads = [s for s in (spreads or range(len(pages_spec) // 2))
                   if args.kind in (pages_spec[2 * s][0], pages_spec[2 * s + 1][0])]
    partial = spreads is not None

    out_dir = args.out or os.path.join(book.dir, 'build')
    work_dir = os.path.join(out_dir, f'spreads_{args.mode}')
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.join(out_dir, book.output_prefix)
    suffix = args.mode + ('_partial' if partial else '')
    p = book.profile

    raw_pages = os.path.join(work_dir, 'pages.pdf')
    n = r.render_pages(pages_spec, raw_pages, work_dir, spreads=spreads)
    pages_out = f"{prefix}_pages_{suffix}.pdf"
    set_print_boxes(raw_pages, p.pages_trim, p.pages_bleed, pages_out)
    print(f"wrote {pages_out} ({n} spreads)")

    if mode['cover'] and not partial:
        raw_cover = os.path.join(work_dir, 'cover.pdf')
        r.render_cover(raw_cover)
        cover_out = f"{prefix}_cover_{suffix}.pdf"
        set_print_boxes(raw_cover, p.cover_trim, p.cover_bleed, cover_out)
        print(f"wrote {cover_out}")

    if r.res_warnings:
        print(f"\n{len(r.res_warnings)} photo(s) below 200 dpi in their box:")
        for label, path, dpi in r.res_warnings:
            print(f"  {label}: {os.path.basename(path)} ~{dpi} dpi")


def cmd_pages(args):
    book = _load(args.book)
    pages_spec = plan(book, check_page_count=False)
    for s in range(len(pages_spec) // 2):
        print(f"spread {s:02d}  L {describe(pages_spec[2 * s]):<44} R {describe(pages_spec[2 * s + 1])}")
    print(f"\n{len(pages_spec)} pages (book needs {book.page_count})")
    for m in unplaced_photos(book, pages_spec):
        print(f"not placed: idx {m['idx']} (number {m['order']:03d}, day {m['day']})")
    if len(pages_spec) != book.page_count:
        return 1


def cmd_renumber(args):
    """Reassign the printed numbers ('order') through the whole book, in
    chapter order, keeping each chapter's relative order. Renumbering only
    the changed chapter lets ranges overlap - two photos with one number.
    Works on the raw files, since a book with duplicate numbers doesn't
    pass validation."""
    book_path = os.path.abspath(args.book)
    with open(book_path) as f:
        data = json.load(f)
    manifest_path = os.path.join(os.path.dirname(book_path), data.get("manifest", "final_manifest.json"))
    with open(manifest_path) as f:
        manifest = json.load(f)
    chapter_ids = [d["id"] for d in data.get("days", data.get("chapters", []))]
    # chapters not in book.json (e.g. the closing photo's day) keep their place after the others
    extra = sorted({m["day"] for m in manifest} - set(chapter_ids),
                   key=lambda day: min(m["order"] for m in manifest if m["day"] == day))
    rank = {day: i for i, day in enumerate(chapter_ids + extra)}
    changed = 0
    for new, m in enumerate(sorted(manifest, key=lambda m: (rank[m["day"]], m["order"])), start=1):
        changed += m["order"] != new
        m["order"] = new
    if args.dry_run:
        print(f"{changed} of {len(manifest)} numbers would change")
        return
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"{changed} of {len(manifest)} numbers changed in {manifest_path}")
    if changed:
        print("send a fresh `--mode numbers` PDF before the next round of notes - old numbers are stale now")


def cmd_pattern_search(args):
    """Planning is cheap (no image I/O), so hundreds of candidates per second
    can be tried against the exact page count."""
    book = _load(args.book)
    values = [int(v) for v in args.values.split(',')]
    hits = []
    for length in (int(n) for n in args.lengths.split(',')):
        for combo in itertools.product(values, repeat=length):
            try:
                pages_spec = plan(book, pattern=list(combo))
            except LayoutError:
                continue
            # single-photo pages that were not asked for read as orphans
            orphans = sum(1 for s in pages_spec if s[0] == 'grid1' and len(s) == 2) - \
                sum(len(d['solo_fullbleed']) for d in book.days)
            hits.append((orphans, -sum(combo) / len(combo), list(combo)))
    hits.sort()
    print(f"{len(hits)} PATTERNs hit exactly {book.page_count} pages (fewest orphan single-photo pages first):")
    for orphans, neg_avg, combo in hits[:args.limit]:
        print(f"  {combo}  orphans={orphans}  avg photos/page={-neg_avg:.2f}")
    print(f"current: {book.pattern}")


def cmd_profile_from_pdf(args):
    import pypdf

    def boxes(path):
        page = pypdf.PdfReader(path).pages[0]
        media = [round(float(v), 5) for v in page.mediabox]
        trim = [round(float(v), 5) for v in page.trimbox]
        bleed = [round(float(v), 5) for v in page.bleedbox]
        if trim == media:
            print(f"warning: {path} has no TrimBox (it equals the MediaBox). "
                  "Export from the publisher's template as 'raw format incl. bleed, no marks' "
                  "with the document's bleed settings.", file=sys.stderr)
        return {'media': media, 'trim': trim, 'bleed': bleed}

    profile = {
        'name': args.name,
        'source': f"read from {os.path.basename(args.cover)} and {os.path.basename(args.pages)}",
        'cover': boxes(args.cover),
        'pages': boxes(args.pages),
    }
    print(json.dumps(profile, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='photobook', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    b = sub.add_parser('build', help='render the book')
    b.add_argument('book', help='path to book.json')
    b.add_argument('--mode', choices=MODES, default='review')
    b.add_argument('--out', help='output folder (default: build/ next to book.json)')
    b.add_argument('--dpi', type=int, help='target resolution (default: print 300, review 150, numbers 110)')
    b.add_argument('--spreads', help="render only these spreads, e.g. '0,3-5' (0-based)")
    b.add_argument('--kind', help="render only spreads with this page kind, e.g. 'opener'")
    b.set_defaults(func=cmd_build)

    p = sub.add_parser('pages', help='print the page plan')
    p.add_argument('book')
    p.set_defaults(func=cmd_pages)

    r = sub.add_parser('renumber', help='renumber the printed photo numbers through the whole book')
    r.add_argument('book')
    r.add_argument('--dry-run', action='store_true')
    r.set_defaults(func=cmd_renumber)

    s = sub.add_parser('pattern-search', help='find PATTERNs that hit the page count')
    s.add_argument('book')
    s.add_argument('--lengths', default='4,5,6')
    s.add_argument('--values', default='2,3,4')
    s.add_argument('--limit', type=int, default=20)
    s.set_defaults(func=cmd_pattern_search)

    f = sub.add_parser('profile-from-pdf', help='print a profile JSON from template exports')
    f.add_argument('cover', help='cover PDF exported from the publisher template')
    f.add_argument('pages', help='interior (one spread) PDF exported from the publisher template')
    f.add_argument('--name', default='')
    f.set_defaults(func=cmd_profile_from_pdf)

    args = ap.parse_args(argv)
    try:
        return args.func(args) or 0
    except (BookError, LayoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

"""Suggest a first-draft selection from the index: one photo per burst, spread through each day.

A starting point for the user to correct, not a replacement for choosing.
Per capture day:

1. bursts - photos a few seconds apart, or up to 90 s apart and looking
   alike - collapse to one: an edited export if there is one, else the
   sharpest;
2. drops shaky outliers (below the day's 25th sharpness percentile -
   sharpness is only comparable within a day/scene), black-and-white edits
   and files too small to print large (unless kept with flags below);
3. gives each day a share of --count that grows with its number of photos
   but less than linearly, so a busy day doesn't swallow the book;
4. picks the best photo per time slot of the day, so the whole day is
   covered, and never two photos that are minutes apart and look alike.

    python scripts/suggest_selection.py PROJECT_DIR --pages 84
    python scripts/suggest_selection.py PROJECT_DIR --count 150

Writes PROJECT_DIR/selection.txt (one idx per line with a comment), which
make_manifest.py --select reads. Look at the picks on contact sheets
before building on them.
"""
import argparse
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

BURST_S, SIMILAR_S, HAMMING = 4, 90, 14  # burst: <= 4 s, or <= 90 s and dHash distance <= 14
MIN_APART_S, LOOKALIKE_S, LOOKALIKE_CORR = 150, 1800, 0.8
# Black-and-white edits sit at practically zero saturation (toned ones just
# under 0.01); foggy mountain photos are colour photos from about 0.014 up.
# On the original archive a threshold of 0.06 took 99 fog shots for b/w.
BW_SATURATION = 0.012
PHOTOS_PER_GRID_PAGE = 2.2
MIN_CHAPTER_PHOTOS = 5  # make_manifest.py --min-day-photos


def dhash(im):
    g = np.asarray(im.convert('L').resize((9, 8), Image.LANCZOS), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).ravel()
    return int(''.join('1' if b else '0' for b in bits), 2)


def colour_vector(im):
    """Mean-free, normalised 24x24 colour thumbnail; dot product = similarity.
    Catches re-framed shots of the same view that dHash misses."""
    a = np.asarray(im.convert('RGB').resize((24, 24)), dtype=np.float32).ravel()
    a -= a.mean()
    return a / (np.linalg.norm(a) or 1)


def saturation(im):
    hsv = np.asarray(im.convert('RGB').resize((64, 64)).convert('HSV'), dtype=np.float32)
    return float(hsv[..., 1].mean() / 255)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project_dir')
    size = ap.add_mutually_exclusive_group()
    size.add_argument('--count', type=int, help='number of photos to pick')
    size.add_argument('--pages', type=int, default=84, help='interior page count to estimate --count from')
    ap.add_argument('--day-start-hour', type=int, default=4, help='same day boundary as make_manifest.py')
    ap.add_argument('--min-long-side', type=int, default=2400,
                    help='drop smaller files (messenger copies, screenshots); 0 keeps all')
    ap.add_argument('--keep-bw', action='store_true', help='keep black-and-white edits')
    ap.add_argument('--force', action='store_true', help='overwrite an existing selection.txt')
    args = ap.parse_args()

    out_path = os.path.join(args.project_dir, 'selection.txt')
    if os.path.exists(out_path) and not args.force:
        sys.exit(f"{out_path} exists - it may hold the user's own choices. Use --force to replace it.")
    with open(os.path.join(args.project_dir, 'recs_sorted.json')) as f:
        recs = json.load(f)

    days = OrderedDict()
    undated = 0
    for r in recs:
        if 'error' in r or not r.get('thumb'):
            continue
        if not r.get('datetime'):
            undated += 1
            continue
        t = datetime.fromisoformat(r['datetime'])
        with Image.open(os.path.join(args.project_dir, r['thumb'])) as im:
            r['_hash'], r['_vec'], r['_sat'] = dhash(im), colour_vector(im), saturation(im)
        r['_t'] = t.timestamp()
        days.setdefault((t - timedelta(hours=args.day_start_hour)).date().isoformat(), []).append(r)

    count = args.count
    if count is None:
        # Pages: 2 front, 2 closing, 2 per chapter opener, the rest grids.
        # Photos: opener + inset per chapter, the closing photo, the grids.
        # Days too small for a chapter (make_manifest.py folds them) don't count.
        chapters = sum(1 for rs in days.values() if len(rs) >= MIN_CHAPTER_PHOTOS)
        count = 2 * chapters + 1 + round((args.pages - 4 - 2 * chapters) * PHOTOS_PER_GRID_PAGE)
        print(f"aiming for ~{count} photos for {args.pages} pages and {chapters} chapters (--count overrides)")

    dropped = {'shaky': 0, 'black-and-white': 0, 'low resolution': 0}
    candidates = OrderedDict()
    for day, rs in days.items():
        rs.sort(key=lambda r: r['_t'])
        bursts = [[rs[0]]]
        for r in rs[1:]:
            prev = bursts[-1][-1]
            dt = r['_t'] - prev['_t']
            if dt <= BURST_S or (dt <= SIMILAR_S and bin(r['_hash'] ^ prev['_hash']).count('1') <= HAMMING):
                bursts[-1].append(r)
            else:
                bursts.append([r])
        reps = [max(b, key=lambda r: (bool(r.get('edited')), r.get('sharpness', 0))) for b in bursts]
        sharp = sorted(r.get('sharpness', 0) for r in rs)
        p25 = sharp[len(sharp) // 4]
        keep = []
        for r in reps:
            if r.get('sharpness', 0) < p25 and not r.get('edited'):
                dropped['shaky'] += 1
            elif r['_sat'] < BW_SATURATION and not args.keep_bw:
                dropped['black-and-white'] += 1
            elif args.min_long_side and max(r.get('width', 0), r.get('height', 0)) < args.min_long_side:
                dropped['low resolution'] += 1
            else:
                keep.append(r)
        candidates[day] = (len(rs), len(bursts), keep)

    weights = {d: c[0] ** 0.6 for d, c in candidates.items()}
    total_w = sum(weights.values())
    quota = {d: min(len(c[2]), max(1, round(count * weights[d] / total_w))) for d, c in candidates.items()}

    selected = []
    print(f"\n{'day':<12}{'photos':>8}{'bursts':>8}{'usable':>8}{'picked':>8}")
    for day, (n_photos, n_bursts, cand) in candidates.items():
        q = quota[day]
        chosen = []

        def fits(r):
            for c in chosen:
                dt = abs(r['_t'] - c['_t'])
                if dt < MIN_APART_S or (dt < LOOKALIKE_S and float(r['_vec'] @ c['_vec']) > LOOKALIKE_CORR):
                    return False
            return True

        rank = lambda r: (not r.get('edited'), -r.get('sharpness', 0))  # noqa: E731
        n = len(cand)
        for b in range(q):  # best photo per time slot first, so the whole day is covered
            for r in sorted(cand[b * n // q:(b + 1) * n // q], key=rank):
                if fits(r):
                    chosen.append(r)
                    break
        for r in sorted(cand, key=rank):  # then top up with the best of the rest
            if len(chosen) >= q:
                break
            if r not in chosen and fits(r):
                chosen.append(r)
        selected += chosen
        note = "  <- too few for a chapter; make_manifest.py folds it into the day before" if len(chosen) < MIN_CHAPTER_PHOTOS else ""
        print(f"{day:<12}{n_photos:>8}{n_bursts:>8}{n:>8}{len(chosen):>8}{note}")

    selected.sort(key=lambda r: r['_t'])
    with open(out_path, 'w') as f:
        f.write("# first-draft suggestion from suggest_selection.py - edit freely\n")
        for r in selected:
            flags = " edited" if r.get('edited') else ""
            f.write(f"{r['idx']}  # {r['datetime'][:16].replace('T', ' ')}  sharpness {r.get('sharpness')}{flags}\n")
    print(f"\npicked {len(selected)} photos -> {out_path}")
    print("dropped before picking: " + ", ".join(f"{v} {k}" for k, v in dropped.items()))
    if undated:
        print(f"{undated} photos without capture time were not considered")


if __name__ == '__main__':
    main()

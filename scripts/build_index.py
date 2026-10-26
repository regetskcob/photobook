"""Build the full photo index (recs_sorted.json) from zip archives and/or folders.

One entry per photo with a stable `idx`, capture time, GPS, size, a
sharpness score and a thumbnail for review. Built ONCE per project: `idx`
values are what book.json refers to, so they must never change afterwards.

    python scripts/build_index.py PROJECT_DIR SOURCE [SOURCE ...]

SOURCEs are zip files or folders. Writes PROJECT_DIR/recs_sorted.json and
PROJECT_DIR/thumbs/. Next step: make_manifest.py.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

import numpy as np
from PIL import ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from photo_source import iter_sources, open_image  # noqa: E402

THUMB_SIZE = 480
EXIF_IFD, GPS_IFD = 0x8769, 0x8825
DATETIME_ORIGINAL, DATETIME = 36867, 306


def exif_datetime(exif):
    raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def exif_gps(exif):
    gps = exif.get_ifd(GPS_IFD)
    try:
        def deg(v, ref):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if ref in ('S', 'W') else d
        return [round(deg(gps[2], gps[1]), 6), round(deg(gps[4], gps[3]), 6)]
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return None


def exiftool_datetime(zip_path, entry):
    """Capture time for files PIL can't read EXIF from (HEIC without
    pillow-heif), via exiftool when it is installed."""
    if zip_path is not None or not shutil.which('exiftool'):
        return None
    out = subprocess.run(['exiftool', '-s3', '-DateTimeOriginal', entry], capture_output=True, text=True).stdout.strip()
    try:
        return datetime.strptime(out[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def sharpness(im):
    """Variance of the Laplacian on a downscaled greyscale copy - higher is
    sharper. Only meaningful relative to other photos of the same set."""
    g = im.convert('L')
    g.thumbnail((800, 800))
    a = np.asarray(g, dtype=np.float32)
    lap = a[1:-1, 1:-1] * -4 + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    return round(float(lap.var()), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project_dir')
    ap.add_argument('sources', nargs='+', help='zip files or folders with photos')
    ap.add_argument('--force', action='store_true', help='overwrite an existing index (renumbers idx!)')
    args = ap.parse_args()

    out_path = os.path.join(args.project_dir, 'recs_sorted.json')
    if os.path.exists(out_path) and not args.force:
        sys.exit(f"{out_path} exists. idx values must stay stable once book.json refers to them - "
                 "use --force only if nothing refers to them yet.")
    thumbs = os.path.join(args.project_dir, 'thumbs')
    os.makedirs(thumbs, exist_ok=True)

    recs, failed = [], []
    sources = list(iter_sources(args.sources))
    for n, (zip_path, entry, size) in enumerate(sources, start=1):
        rec = {'zip': os.path.relpath(zip_path, args.project_dir) if zip_path else None,
               'entry': entry if zip_path else os.path.relpath(entry, args.project_dir),
               'bytes': size}
        try:
            im = open_image(zip_path, entry)
            exif = im.getexif()
            rec['datetime'] = exif_datetime(exif) or exiftool_datetime(zip_path, entry)
            rec['gps'] = exif_gps(exif)
            im = ImageOps.exif_transpose(im).convert('RGB')
            rec['width'], rec['height'] = im.size
            rec['sharpness'] = sharpness(im)
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            # final name needs the idx, known only after sorting
            rec['_thumb_tmp'] = os.path.join(thumbs, f"_tmp_{n:06d}.jpg")
            im.save(rec['_thumb_tmp'], quality=82)
        except Exception as e:
            rec['error'] = f"{type(e).__name__}: {e}"
            failed.append(rec)
        recs.append(rec)
        if n % 50 == 0:
            print(f"{n}/{len(sources)}", flush=True)

    # idx in capture-time order, so neighbouring idx are neighbouring moments
    recs.sort(key=lambda r: (r.get('datetime') or '9999', r['zip'] or '', r['entry']))
    for idx, rec in enumerate(recs):
        rec['idx'] = idx
        tmp = rec.pop('_thumb_tmp', None)
        if tmp is not None:
            rec['thumb'] = f"thumbs/{idx:06d}.jpg"
            os.replace(tmp, os.path.join(args.project_dir, rec['thumb']))
    recs = [{'idx': r.pop('idx'), **r} for r in recs]

    with open(out_path, 'w') as f:
        json.dump(recs, f, indent=1, ensure_ascii=False)
    undated = sum(1 for r in recs if not r.get('datetime'))
    print(f"indexed {len(recs)} photos -> {out_path}")
    if undated:
        print(f"{undated} without capture time (sorted last) - check them before assigning days")
    for r in failed:
        print(f"could not read {r['entry']}: {r['error']}")


if __name__ == '__main__':
    main()

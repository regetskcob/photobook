"""Convert every .heic file in a folder to JPEG via heic_extract.py.

Use this when the standard decoder (libheif / pillow-heif) fails on
grid-type HEIC files, as it does for many full-resolution iPhone photos.
Needs ffmpeg on PATH.

    python scripts/batch_heic.py SRC_DIR OUT_DIR [--max-dim 1600]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heic_extract as h  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src_dir')
    ap.add_argument('out_dir')
    ap.add_argument('--max-dim', type=int, default=1600, help='longest side of the output (0 = full size)')
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    heics = sorted(f for f in os.listdir(args.src_dir) if f.lower().endswith('.heic'))
    ok, fail = [], []
    for fn in heics:
        dst = os.path.join(args.out_dir, os.path.splitext(fn)[0] + '.jpg')
        try:
            h.convert(os.path.join(args.src_dir, fn), dst, max_dim=args.max_dim)
            ok.append(fn)
            print('OK', fn, flush=True)
        except Exception as e:
            fail.append((fn, str(e)))
            print('FAIL', fn, e, flush=True)
    print('DONE OK:', len(ok), 'FAIL:', len(fail))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())

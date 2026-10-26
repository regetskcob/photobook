"""Copy selected photos out of the camera-export zip archives, by printed number.

For the user's review folder: each file is named NNN_<day>_<original name>
so it sorts in book order and matches the numbers in the numbered PDF.
Reads `zip` / `entry` / `order` / `day` from final_manifest.json; zip paths
are relative to the manifest's folder.

    python scripts/extract_photos.py PROJECT_DIR 12 40     # numbers 12..40
    python scripts/extract_photos.py PROJECT_DIR 186       # just number 186
"""
import argparse
import json
import os
import re
import zipfile


def safe_stem(entry):
    stem = os.path.splitext(os.path.basename(entry))[0]
    return re.sub(r'[^A-Za-z0-9_\-]+', '_', stem)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project_dir', help='folder with final_manifest.json and the zip archives')
    ap.add_argument('first', type=int, help='first printed number')
    ap.add_argument('last', type=int, nargs='?', help='last printed number (default: same as first)')
    ap.add_argument('--manifest', default='final_manifest.json')
    ap.add_argument('--out', default='Fotobuch_Auswahl', help='output folder, relative to project_dir')
    args = ap.parse_args()
    last = args.first if args.last is None else args.last

    with open(os.path.join(args.project_dir, args.manifest)) as f:
        manifest = json.load(f)
    out_dir = os.path.join(args.project_dir, args.out)
    os.makedirs(out_dir, exist_ok=True)

    count = 0
    for m in sorted(manifest, key=lambda m: m['order']):
        if not (args.first <= m['order'] <= last):
            continue
        out_path = os.path.join(out_dir, f"{m['order']:03d}_{m['day']}_{safe_stem(m['entry'])}.jpeg")
        if not os.path.exists(out_path):
            with zipfile.ZipFile(os.path.join(args.project_dir, m['zip'])) as z, open(out_path, 'wb') as f:
                f.write(z.read(m['entry']))
        count += 1
    print(f"{count} file(s) for numbers {args.first}-{last} in {out_dir}")


if __name__ == '__main__':
    main()

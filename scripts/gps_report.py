"""Where were we when? A per-day list of stops from the photos' GPS data.

Groups each day's photos into time windows (a new window starts after a
gap of --gap-minutes without photos) and lists, per window, the time span,
number of photos and the first/last position as map links, with an empty
"Name:" to fill in. On the original book this was the basis for chapter
titles and captions - and an independent check of the photo order, since
GPS time doesn't depend on the camera clock.

    python scripts/gps_report.py PROJECT_DIR/recs_sorted.json > places.md
    python scripts/gps_report.py recs_sorted.json --home 48.14,11.58   # leave out photos at the accommodation

Only photos with GPS data appear (usually the phone's, not a camera's).
The output contains exact positions - keep it with the project's private
files.
"""
import argparse
import json
import math
from collections import OrderedDict
from datetime import datetime, timedelta


def km(a, b):
    """Great-circle distance between two [lat, lon] points."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def link(p):
    return f"[{p[0]:.4f}, {p[1]:.4f}](https://www.openstreetmap.org/?mlat={p[0]:.5f}&mlon={p[1]:.5f}#map=15/{p[0]:.5f}/{p[1]:.5f})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('index', help='recs_sorted.json (or any JSON list with datetime + gps)')
    ap.add_argument('--gap-minutes', type=int, default=60, help='a pause this long starts a new stop')
    ap.add_argument('--day-start-hour', type=int, default=4, help='same day boundary as make_manifest.py')
    ap.add_argument('--home', help='LAT,LON of the accommodation - photos taken there are left out')
    ap.add_argument('--home-radius-km', type=float, default=0.3)
    args = ap.parse_args()

    with open(args.index) as f:
        recs = json.load(f)
    home = [float(v) for v in args.home.split(',')] if args.home else None

    days = OrderedDict()
    skipped_home = 0
    for r in sorted((r for r in recs if r.get('datetime') and r.get('gps')), key=lambda r: r['datetime']):
        if home and km(r['gps'], home) <= args.home_radius_km:
            skipped_home += 1
            continue
        t = datetime.fromisoformat(r['datetime'])
        days.setdefault((t - timedelta(hours=args.day_start_hour)).date(), []).append((t, r['gps']))

    with_gps = sum(1 for r in recs if r.get('gps'))
    print("# Where we were – GPS stops from the photos\n")
    print(f"{with_gps} of {len(recs)} photos have GPS data.", end="")
    print(f" {skipped_home} taken at home are left out." if home else "")
    gap = timedelta(minutes=args.gap_minutes)
    for n, (day, shots) in enumerate(days.items(), start=1):
        print(f"\n## Day {n} ({day.isoformat()})\n")
        stops = [[shots[0]]]
        for shot in shots[1:]:
            if shot[0] - stops[-1][-1][0] > gap:
                stops.append([])
            stops[-1].append(shot)
        for stop in stops:
            (t0, p0), (t1, p1) = stop[0], stop[-1]
            span = t0.strftime('%H:%M') if t0 == t1 else f"{t0:%H:%M}–{t1:%H:%M}"
            where = link(p0) if km(p0, p1) < 0.2 else f"from {link(p0)} to {link(p1)}"
            print(f"- **{span}** ({len(stop)} photo{'s' if len(stop) > 1 else ''}): {where}, Name: ")


if __name__ == '__main__':
    main()

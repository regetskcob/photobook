"""Generate placeholder photos + final_manifest.json for the demo book.

The demo needs no real photos: every "photo" is a coloured test card that
shows its idx and printed number, in a mix of landscape, portrait, square and
panorama shapes, so every layout mechanism has something to work on.

    python examples/demo/make_demo_photos.py
    python -m photobook build examples/demo/book.json --mode review
"""
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

SHAPES = {
    "landscape": (1200, 900),
    "portrait": (900, 1200),
    "wide": (1600, 900),
    "tall": (900, 1600),
    "square": (1000, 1000),
    "panorama": (3200, 1300),
}

# (day, idx, shape) in chronological order. The idx values are arbitrary but
# stable - book.json refers to photos only by idx.
PHOTOS = [
    ("day1", 1, "landscape"), ("day1", 2, "wide"), ("day1", 3, "portrait"), ("day1", 4, "landscape"),
    ("day1", 5, "square"), ("day1", 6, "landscape"), ("day1", 7, "portrait"), ("day1", 8, "wide"),
    ("day1", 9, "landscape"), ("day1", 10, "landscape"), ("day1", 11, "portrait"),
    ("day2", 20, "landscape"), ("day2", 21, "wide"), ("day2", 22, "tall"), ("day2", 23, "landscape"),
    ("day2", 24, "landscape"), ("day2", 30, "landscape"), ("day2", 31, "square"), ("day2", 25, "panorama"), ("day2", 26, "portrait"), ("day2", 27, "landscape"),
    ("day2", 28, "wide"), ("day2", 29, "landscape"),
    ("day3", 40, "landscape"), ("day3", 41, "portrait"), ("day3", 42, "wide"), ("day3", 43, "landscape"),
    ("day3", 44, "tall"), ("day3", 45, "landscape"), ("day3", 46, "landscape"), ("day3", 47, "wide"), ("day3", 48, "landscape"), ("day3", 49, "portrait"),
    ("day4", 60, "landscape"),
]

PALETTE = [(52, 92, 125), (103, 140, 92), (171, 120, 76), (122, 82, 120), (68, 120, 120), (150, 95, 90)]


def make_card(path, idx, order, shape):
    w, h = SHAPES[shape]
    base = PALETTE[idx % len(PALETTE)]
    im = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(im)
    # diagonal stripes make crops and alignment easy to see
    for x in range(-h, w, 80):
        d.line([(x, h), (x + h, 0)], fill=tuple(min(255, c + 25) for c in base), width=18)
    # a few shapes placed per idx, so no two cards look alike - the engine
    # refuses look-alike photos in one book
    rng = random.Random(idx)
    for _ in range(6):
        x0, y0 = rng.randrange(w), rng.randrange(h)
        r = rng.randrange(min(w, h) // 10, min(w, h) // 4)
        shade = tuple(max(0, c - 60) for c in base) if rng.random() < 0.5 else (235, 235, 225)
        d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=shade)
    try:
        font = ImageFont.load_default(size=64)
    except TypeError:  # Pillow < 10.1 has no scalable default font
        font = ImageFont.load_default()
    d.rectangle([w // 2 - 260, h // 2 - 130, w // 2 + 260, h // 2 + 130], fill=(20, 20, 20))
    d.multiline_text((w // 2 - 220, h // 2 - 100), f"idx {idx}\nnumber {order:03d}\n{shape}",
                     fill=(255, 255, 255), font=font, spacing=12)
    im.save(path, quality=88)


def main():
    os.makedirs(os.path.join(HERE, "photos"), exist_ok=True)
    manifest = []
    for order, (day, idx, shape) in enumerate(PHOTOS, start=1):
        rel = f"photos/{idx:04d}.jpg"
        make_card(os.path.join(HERE, rel), idx, order, shape)
        manifest.append({"idx": idx, "day": day, "order": order, "file": rel})
    map_path = os.path.join(HERE, "photos", "map.jpg")
    Image.new("RGB", (1600, 1100), (205, 214, 200)).save(map_path, quality=88)
    with open(os.path.join(HERE, "final_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"wrote {len(manifest)} placeholder photos and final_manifest.json to {HERE}")


if __name__ == "__main__":
    main()

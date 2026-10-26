"""Loading and validating a book: book.json + manifest + product profile.

Everything that belongs to ONE specific book (texts, captions, which photo
opens which day, crop tweaks, page count, ...) lives in book.json next to the
project's photos. Everything that belongs to the print product (page and
bleed geometry) lives in a profile JSON. The engine itself holds neither.
See schema/book_schema.md for the full format.
"""
import json
import os
from collections import defaultdict

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")

GROUP_STYLES = ("manual3", "portrait3", "portrait3_bleed", "mirror3", "bleed2")
CROP_ALIGNS = ("center", "top", "bottom", "left", "right")

DEFAULT_STYLE = {
    "font_regular": "Times-Roman",
    "font_bold": "Times-Bold",
    "font_italic": "Times-Italic",
    "caption_size": 10.5,
    "text_slot_size": 13,
    "font_files": {},
    "dark_color": [0.11, 0.13, 0.16],  # title, opener and closing pages
    "text_color": [0.18, 0.18, 0.18],  # paragraphs on white pages
    "chapter_icon": True,
    # The chapter-opener ridgeline was tuned over many rounds and then
    # switched off for the Oberstdorf book - kept behind a flag so the work
    # stays recoverable with a one-line change.
    "chapter_silhouette": False,
}


class BookError(Exception):
    pass


class Profile:
    def __init__(self, data, source=""):
        self.name = data.get("name", source)
        try:
            self.cover_media = tuple(data["cover"]["media"])
            self.cover_trim = tuple(data["cover"]["trim"])
            self.cover_bleed = tuple(data["cover"]["bleed"])
            self.pages_media = tuple(data["pages"]["media"])
            self.pages_trim = tuple(data["pages"]["trim"])
            self.pages_bleed = tuple(data["pages"]["bleed"])
        except KeyError as e:
            raise BookError(f"profile {source}: missing box {e}") from None
        self.trim_center_x = (self.pages_trim[0] + self.pages_trim[2]) / 2

    @classmethod
    def load(cls, ref, base_dir="."):
        """`ref` is either a path to a profile JSON or the name of one in
        the repo's profiles/ folder (without .json)."""
        candidates = [os.path.join(base_dir, ref), os.path.join(PROFILES_DIR, ref + ".json")]
        for path in candidates:
            if os.path.isfile(path):
                with open(path) as f:
                    return cls(json.load(f), source=path)
        raise BookError(f"profile not found: {ref} (looked in {', '.join(candidates)})")


class Book:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        with open(self.path) as f:
            data = json.load(f)
        self.data = data
        self.warnings = []

        self.page_count = data["pages"]
        self.pattern = list(data["pattern"])
        self.output_prefix = data.get("output_prefix", "book")
        self.day_label = data.get("day_label", "Day {n}")
        self.fill_odd_days_with_blank = bool(data.get("fill_odd_days_with_blank", False))
        self.style = dict(DEFAULT_STYLE, **data.get("style", {}))
        self.profile = Profile.load(data["profile"], self.dir)

        with open(self.resolve(data.get("manifest", "final_manifest.json"))) as f:
            self.manifest = json.load(f)
        self.by_idx = {m["idx"]: m for m in self.manifest}
        self.by_day = defaultdict(list)
        for m in self.manifest:
            self.by_day[m["day"]].append(m)

        # Photo files: either a 'file' field on each manifest entry, or an
        # idx -> path map (keyed by idx, never by the printed number - that
        # one shifts whenever photos are added or removed).
        self.photo_files = {m["idx"]: m["file"] for m in self.manifest if "file" in m}
        if data.get("photo_map"):
            with open(self.resolve(data["photo_map"])) as f:
                self.photo_files.update({int(k): v for k, v in json.load(f).items()})

        # "chapters" reads better than "days" for books that aren't a trip
        chapters = data.get("days", data.get("chapters"))
        if chapters is None:
            raise BookError("book.json needs a 'days' (or 'chapters') list")
        self.days = []
        for n, d in enumerate(chapters, start=1):
            day = dict(d)
            day.setdefault("number", n)
            day.setdefault("label", self.day_label.format(n=day["number"]))
            day.setdefault("intro", [])
            day.setdefault("solo_fullbleed", [])
            day.setdefault("groups", [])
            if isinstance(day["intro"], str):
                day["intro"] = [day["intro"]]
            self.days.append(day)

        self.cover = data["cover"]
        self.front = data.get("front", {})
        self.closing = data["closing"]
        self.page_swaps = data.get("page_swaps", [])
        self.photos = {int(k): v for k, v in data.get("photos", {}).items()}

        self._validate()

    # ---- paths ----
    def resolve(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.dir, rel)

    def img_path(self, m):
        idx = m["idx"] if isinstance(m, dict) else m
        try:
            return self.resolve(self.photo_files[idx])
        except KeyError:
            raise BookError(f"no file for photo idx {idx} (neither manifest 'file' nor photo_map)") from None

    # ---- per-photo options (all keyed by stable idx) ----
    def _opt(self, idx, key, default=None):
        return self.photos.get(idx, {}).get(key, default)

    def caption(self, idx):
        return self._opt(idx, "caption")

    def spread_caption(self, idx):
        return self._opt(idx, "spread_caption")

    def crop(self, idx):
        return self._opt(idx, "crop", "center")

    def text_slot(self, idx):
        return self._opt(idx, "text")

    def text_companion(self, idx):
        return bool(self._opt(idx, "text_companion", False))

    def text_align(self, idx):
        return self._opt(idx, "text_align", "left")

    # ---- validation ----
    def _validate(self):
        """Every idx the config points at must exist - and, for day-level
        settings, belong to that day. A stale reference used to be silently
        ignored, which cost several review rounds; now it fails loudly."""
        errors = []
        orders = defaultdict(list)
        for m in self.manifest:
            orders[m["order"]].append(m["idx"])
        for order, idxs in orders.items():
            if len(idxs) > 1:
                errors.append(f"printed number 'order' {order} is used by several photos: {idxs} (renumber the whole book)")

        for d in self.days:
            day_id = d["id"]
            day_idxs = {m["idx"] for m in self.by_day.get(day_id, [])}
            if not day_idxs:
                errors.append(f"day {day_id}: no photos in the manifest")
            refs = [("opener", d.get("opener")), ("inset", d.get("inset")),
                    ("panorama_after_opener", d.get("panorama_after_opener")),
                    ("mid_day_panorama", d.get("mid_day_panorama"))]
            if d.get("hero"):
                refs.append(("hero", d["hero"]["photo"]))
            refs += [("solo_fullbleed", i) for i in d["solo_fullbleed"]]
            for g in d["groups"]:
                if g.get("style") not in GROUP_STYLES:
                    errors.append(f"day {day_id}: unknown group style {g.get('style')!r} (one of {GROUP_STYLES})")
                refs += [("groups", i) for i in g["photos"]]
            for what, idx in refs:
                if idx is not None and idx not in day_idxs:
                    errors.append(f"day {day_id}: {what} idx {idx} is not a photo of this day")
                if idx is not None and idx == self.data["closing"]["photo"]:
                    errors.append(f"day {day_id}: {what} idx {idx} is also the closing photo")
            if d.get("inset") is not None and d.get("opener") is None:
                errors.append(f"day {day_id}: an inset needs an opener")

        for what, idx in (("cover", self.cover["photo"]), ("closing", self.closing["photo"])):
            if idx not in self.by_idx:
                errors.append(f"{what} photo idx {idx} is not in the manifest")
        for swap in self.page_swaps:
            for idx in swap["a"] + swap["b"]:
                if idx not in self.by_idx:
                    errors.append(f"page_swaps: idx {idx} is not in the manifest")

        for idx, opts in self.photos.items():
            if idx not in self.by_idx:
                self.warnings.append(f"photos.{idx}: not in the manifest - stale entry, it has no effect")
            if opts.get("crop", "center") not in CROP_ALIGNS:
                errors.append(f"photos.{idx}: crop must be one of {CROP_ALIGNS}")
        for m in self.manifest:
            if m["idx"] not in self.photo_files:
                errors.append(f"photo idx {m['idx']}: no file (neither manifest 'file' nor photo_map)")

        if errors:
            raise BookError("book config is invalid:\n  " + "\n  ".join(errors))

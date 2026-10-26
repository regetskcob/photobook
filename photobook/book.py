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
        # Layout rules. 1 is what the original book was printed with and stays
        # the default so an existing book.json renders unchanged; 2 (written
        # by make_manifest.py) stacks landscape pairs and splits the largest
        # grid page when a day's page count is odd - see docs/ENGINE.md.
        self.layout = data.get("layout", 1)
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
        # groups of idx that may appear together although they look alike
        # (see photobook/similarity.py) - deliberate, never a default
        self.allow_duplicates = data.get("allow_duplicates", [])
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

    def reserved_photos(self):
        """Photos with a fixed page outside the chapters: they never also go
        into their day's grids."""
        return {self.closing["photo"]} | ({self.front["photo"]} if self.front.get("photo") is not None else set())

    # ---- validation ----
    def texts(self):
        """(where, text) for every string that ends up on a page."""
        out = []
        for key in ("title", "tagline"):
            out.append((f"front.{key}", self.front.get(key, "")))
        out += [("front.intro", t) for t in self.front.get("intro", [])]
        for key in ("title", "subtitle"):
            out.append((f"cover.{key}", self.cover.get(key, "")))
        for key in ("caption", "lead", "headline", "date"):
            value = self.closing.get(key) or ""
            out += [(f"closing.{key}", v) for v in (value if isinstance(value, list) else [value])]
        for d in self.days:
            for key in ("title", "date", "label"):
                out.append((f"day {d['id']} {key}", d.get(key) or ""))
            out += [(f"day {d['id']} intro", t) for t in d["intro"]]
            if d.get("hero"):
                cap = d["hero"].get("caption") or ""
                out += [(f"day {d['id']} hero caption", t) for t in (cap if isinstance(cap, list) else [cap])]
        for idx, opts in self.photos.items():
            for key in ("caption", "text", "spread_caption"):
                value = opts.get(key) or ""
                out += [(f"photos.{idx}.{key}", t) for t in (value if isinstance(value, list) else [value])]
        return out

    def _check_text_glyphs(self):
        """Characters the fonts can't draw would print as gaps or boxes.
        The built-in PDF fonts cover Western European text (cp1252) only;
        a TTF in style.font_files covers whatever its glyphs cover."""
        files = self.style.get("font_files") or {}
        if files:
            from reportlab.pdfbase.ttfonts import TTFont
            covered = set()
            for i, path in enumerate(files.values()):
                try:
                    font = TTFont(f"glyph-check-{i}", self.resolve(path))
                except Exception as e:
                    return [f"style.font_files: cannot load {path}: {e}"]
                cmap = set(font.face.charToGlyph)
                covered = cmap if not covered else covered & cmap

            def drawable(ch):
                return ord(ch) in covered
        else:
            def drawable(ch):
                try:
                    ch.encode('cp1252')
                    return True
                except UnicodeEncodeError:
                    return False
        errors = []
        for where, text in self.texts():
            bad = sorted({ch for ch in text if not ch.isspace() and not drawable(ch)})
            if bad:
                errors.append(f"{where}: the font can't draw {' '.join(bad)} - "
                              + ("pick a font that has them" if files else "set style.font_files to a TTF that has them"))
        return errors

    def _validate(self):
        """Every idx the config points at must exist - and, for day-level
        settings, belong to that day. A stale reference used to be silently
        ignored, which cost several review rounds; now it fails loudly."""
        errors = []
        if not self.pattern or any(v not in (1, 2, 3, 4) for v in self.pattern):
            errors.append(f"pattern {self.pattern}: grid pages hold 1 to 4 photos")
        # the same photo twice, detectable without looking at the pixels
        seen_idx, seen_file, seen_entry = set(), {}, {}
        for m in self.manifest:
            if m["idx"] in seen_idx:
                errors.append(f"idx {m['idx']} is listed twice in the manifest")
            seen_idx.add(m["idx"])
            if m["idx"] in self.photo_files:
                path = os.path.normpath(self.resolve(self.photo_files[m["idx"]]))
                if path in seen_file:
                    errors.append(f"idx {seen_file[path]} and {m['idx']} use the same file {self.photo_files[m['idx']]}")
                seen_file.setdefault(path, m["idx"])
            if m.get("zip") is not None and m.get("entry"):
                key = (os.path.basename(m["zip"]), m["entry"])
                if key in seen_entry:
                    errors.append(f"idx {seen_entry[key]} and {m['idx']} are the same archive entry {m['entry']}")
                seen_entry.setdefault(key, m["idx"])
        for group in self.allow_duplicates:
            for idx in group:
                if idx not in self.by_idx:
                    errors.append(f"allow_duplicates: idx {idx} is not in the manifest")

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
            for n, g in enumerate(d["groups"], start=1):
                if g.get("style") not in GROUP_STYLES:
                    errors.append(f"day {day_id}: unknown group style {g.get('style')!r} (one of {GROUP_STYLES})")
                refs += [(f"group {n}", i) for i in g["photos"]]
            # One page role per photo: a photo that is both the opener and the
            # hero used to vanish from the hero's page without a word.
            roles = defaultdict(list)
            for what, idx in refs:
                if idx is not None:
                    roles[idx].append(what)
            for idx, what in roles.items():
                if len(what) > 1:
                    errors.append(f"day {day_id}: idx {idx} has more than one role ({', '.join(what)})")
            for what, idx in refs:
                if idx is not None and idx not in day_idxs:
                    errors.append(f"day {day_id}: {what} idx {idx} is not a photo of this day")
                if idx is not None and idx == self.data["closing"]["photo"]:
                    errors.append(f"day {day_id}: {what} idx {idx} is also the closing photo")
                if idx is not None and idx == self.data.get("front", {}).get("photo"):
                    errors.append(f"day {day_id}: {what} idx {idx} is also the photo next to the title")
            if d.get("inset") is not None and d.get("opener") is None:
                errors.append(f"day {day_id}: an inset needs an opener")

        if self.layout not in (1, 2):
            errors.append(f"layout {self.layout!r}: must be 1 or 2")
        if self.front.get("photo") is not None and self.front.get("image"):
            errors.append("front: give either 'photo' (an idx) or 'image' (a file), not both")
        named = [("cover", self.cover["photo"]), ("closing", self.closing["photo"])]
        if self.front.get("photo") is not None:
            named.append(("front", self.front["photo"]))
        for what, idx in named:
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
        missing = []
        for m in self.manifest:
            if m["idx"] not in self.photo_files:
                errors.append(f"photo idx {m['idx']}: no file (neither manifest 'file' nor photo_map)")
            elif not os.path.isfile(self.resolve(self.photo_files[m["idx"]])):
                missing.append(f"idx {m['idx']} ({self.photo_files[m['idx']]})")
        if missing:
            # found now rather than minutes into a build
            errors.append(f"{len(missing)} photo file(s) not found: " + ", ".join(missing[:8])
                          + (" …" if len(missing) > 8 else ""))
        errors += self._check_text_glyphs()

        if errors:
            raise BookError("book config is invalid:\n  " + "\n  ".join(errors))

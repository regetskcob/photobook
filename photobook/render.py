"""Drawing: logical pages -> PDF.

One Renderer instance per build. It holds the book, the product geometry and
the build options (which page numbers to draw, target DPI), so every draw
function below only needs the rect it draws into.
"""
import gc
import io
import os
import random
import textwrap
import zlib

import numpy as np
import pypdf
from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PT_PER_MM = 72 / 25.4
MIN_DPI_WARN = 200
INSET = 10 * PT_PER_MM  # safety inset for text from the trim edge
COVER_TEXT_INSET = 20 * PT_PER_MM  # cover text needs more room from the cut line than a photo
MARGIN = 10 * PT_PER_MM  # white margin around grid pages
GAP = 2.2 * PT_PER_MM  # gutter between grid cells
EXIF_ORIENTATION = 0x0112

# Which page number to draw on each photo:
#   'off'   - print build, no numbers
#   'small' - review build, the discreet 5pt number in the corner
#   'big'   - numbered reference for feedback rounds, readable on a phone
TAG_NUMBER_MODES = ('off', 'small', 'big')


def _caption_lines(caption):
    """A caption is a string, or [line1, line2] for a bold line plus a
    lighter second line."""
    if isinstance(caption, (list, tuple)):
        return list(caption)
    return [caption] if caption else []


class Renderer:
    def __init__(self, book, tag_numbers='off', target_dpi=300, jpeg_quality=90):
        assert tag_numbers in TAG_NUMBER_MODES
        self.book = book
        self.p = book.profile
        self.tag_numbers = tag_numbers
        self.target_dpi = target_dpi
        self.jpeg_quality = jpeg_quality
        st = book.style
        fonts = {}
        for key in ('regular', 'bold', 'italic'):
            # a TTF file (e.g. for scripts the built-in Times can't set)
            # wins over a built-in font name
            path = st.get('font_files', {}).get(key)
            if path:
                fonts[key] = f"book-{key}"
                pdfmetrics.registerFont(TTFont(fonts[key], book.resolve(path)))
            else:
                fonts[key] = st[f"font_{key}"]
        self.serif, self.serif_b, self.serif_i = fonts['regular'], fonts['bold'], fonts['italic']
        self.dark_color = tuple(st["dark_color"])
        self.text_color = tuple(st["text_color"])
        self.caption_size = st["caption_size"]
        self.text_slot_size = st["text_slot_size"]
        self.res_warnings = []
        # A grid item drawn flush against the true bleed edge (not MARGIN
        # inside it) needs its caption padding re-derived from the bleed
        # strip width, or the caption lands in the strip that gets cut off.
        self.caption_bleed_pad = (self.p.pages_trim[0] - self.p.pages_bleed[0]) + INSET

    # ---------- image helpers ----------

    def load_crop(self, path, box_w_pt, box_h_pt, label="", align="center"):
        with Image.open(path) as src:
            # the source's real width, taken before draft() shrinks the decode -
            # the print resolution has to be judged on the file, not on the
            # reduced copy a low-dpi review build works with
            full_w = src.size[1] if src.getexif().get(EXIF_ORIENTATION, 1) in (5, 6, 7, 8) else src.size[0]
            # fast approximate downscale during JPEG decode for huge source files
            approx_w = int(box_w_pt / 72 * self.target_dpi * 1.6)
            approx_h = int(box_h_pt / 72 * self.target_dpi * 1.6)
            try:
                src.draft('RGB', (approx_w, approx_h))
            except Exception:
                pass
            # honour the camera's rotation flag - phones store most portrait
            # photos as landscape pixels plus an orientation tag
            im = ImageOps.exif_transpose(src).convert('RGB')
        iw, ih = im.size
        box_ratio = box_w_pt / box_h_pt
        im_ratio = iw / ih
        # Only one axis is ever cropped: if source and box ratios are far
        # apart, 'align' picks which end survives.
        if im_ratio > box_ratio:
            new_w = ih * box_ratio
            if align == "left":
                offset = 0
            elif align == "right":
                offset = iw - new_w
            else:
                offset = (iw - new_w) / 2
            crop = im.crop((int(offset), 0, int(offset + new_w), ih))
        else:
            new_h = iw / box_ratio
            if align == "top":
                offset = 0
            elif align == "bottom":
                offset = ih - new_h
            else:
                offset = (ih - new_h) / 2
            crop = im.crop((0, int(offset), iw, int(offset + new_h)))
        im.close()
        del im
        cw, ch = crop.size
        dpi = cw * (full_w / iw) / (box_w_pt / 72)
        if dpi < MIN_DPI_WARN:
            self.res_warnings.append((label, path, round(dpi)))
        target_w = int(box_w_pt / 72 * self.target_dpi)
        target_h = int(box_h_pt / 72 * self.target_dpi)
        if cw > target_w:  # only downscale, never upscale
            resized = crop.resize((target_w, target_h), Image.LANCZOS)
            crop.close()
            crop = resized
        return crop

    def load_photo(self, m, w, h, label=""):
        return self.load_crop(self.book.img_path(m), w, h, label=label, align=self.book.crop(m['idx']))

    @staticmethod
    def apply_bottom_scrim(im, strength=0.72, start_frac=0.45):
        arr = np.asarray(im).astype(np.float32)
        h = arr.shape[0]
        ramp = np.zeros(h, dtype=np.float32)
        start = int(h * (1 - start_frac))
        for y in range(start, h):
            frac = (y - start) / max(1, (h - start))
            ramp[y] = frac * strength
        ramp = ramp[:, None, None]
        arr = arr * (1 - ramp)
        return Image.fromarray(np.clip(arr, 0, 255).astype('uint8'))

    def draw_pil(self, c, im, x, y, w, h):
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=self.jpeg_quality, optimize=True)
        buf.seek(0)
        # reportlab keeps a caption's fill alpha in the graphics state; without
        # this reset it bleeds into the next image and washes it out.
        c.setFillAlpha(1)
        c.drawImage(ImageReader(buf), x, y, width=w, height=h)

    def _photo_size(self, m):
        """Upright size, without decoding the pixels."""
        with Image.open(self.book.img_path(m)) as im:
            w, h = im.size
            if im.getexif().get(EXIF_ORIENTATION, 1) in (5, 6, 7, 8):
                w, h = h, w
            return w, h

    def caption_wrap(self, text, box_w_pt, pad=10):
        """Wrap a caption to its real box width (a fixed character count left
        captions in big boxes stranded in a sliver of their width)."""
        max_chars = max(12, int((box_w_pt - pad) / (self.caption_size * 0.5)))
        return textwrap.wrap(text, max_chars)

    def tag_number(self, c, x, y, order):
        if self.tag_numbers == 'off':
            return
        label = f"{order:03d}"
        if self.tag_numbers == 'big':
            fsize, pad = 26, 5
            w = stringWidth(label, self.serif_b, fsize)
            c.setFillColorRGB(0, 0, 0, alpha=0.6)
            c.rect(x - w - 2 * pad, y - 6, w + 2 * pad, fsize * 0.95, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1, alpha=1.0)
            c.setFont(self.serif_b, fsize)
            c.drawRightString(x - pad, y, label)
        else:
            c.setFillColorRGB(1, 1, 1, alpha=0.5)
            c.setFont(self.serif, 5)
            c.drawRightString(x, y, label)
        # One canvas page is a whole spread, so a leftover alpha would wash out
        # a solid background drawn next on the other half.
        c.setFillAlpha(1)

    # ---------- layout drawers, parameterized by rect ----------

    def draw_full_bleed(self, c, bleed, trim, m, caption=None, label=""):
        bx0, by0, bx1, by1 = bleed
        w, h = bx1 - bx0, by1 - by0
        crop = self.load_photo(m, w, h, label=label)
        lines = _caption_lines(caption)
        if lines:
            crop = self.apply_bottom_scrim(crop, strength=0.78, start_frac=0.42)
        self.draw_pil(c, crop, bx0, by0, w, h)
        tx0, ty0, tx1, ty1 = trim
        if len(lines) >= 2:
            c.setFillColorRGB(1, 1, 1)
            c.setFont(self.serif_b, self.caption_size)
            c.drawString(tx0 + INSET, ty0 + 26, lines[0])
            c.setFont(self.serif, self.caption_size - 1.5)
            c.setFillColorRGB(1, 1, 1, alpha=0.85)
            c.drawString(tx0 + INSET, ty0 + 14, lines[1])
        elif lines:
            c.setFillColorRGB(1, 1, 1)
            c.setFont(self.serif_b, self.caption_size)
            c.drawString(tx0 + INSET, ty0 + 14, lines[0])
        self.tag_number(c, tx1 - 6, ty0 + 6, m['order'])

    def draw_text_slot(self, c, text, x0, y0, w, h, top_align=False, companion_m=None, label="", right_align=False):
        # A text-only grid cell on the plain white page. Vertically centered,
        # unless a companion photo sits below it (then top-aligned).
        # Right-aligned reads flush against a photo to its right.
        pad = 6 * PT_PER_MM
        avail_w = w - 2 * pad
        max_chars = max(14, int(avail_w / (self.text_slot_size * 0.45)))
        lines = textwrap.wrap(text, max_chars)
        leading = self.text_slot_size + 4.5
        block_h = len(lines) * leading
        c.setFillColorRGB(*self.text_color)
        c.setFont(self.serif, self.text_slot_size)
        if top_align:
            y = y0 + h - pad - 10
        else:
            y = y0 + h / 2 + block_h / 2 - leading
        for ln in lines:
            if right_align:
                c.drawRightString(x0 + w - pad, y, ln)
            else:
                c.drawString(x0 + pad, y, ln)
            y -= leading
        if companion_m is not None:
            square_side = min(avail_w, h * 0.64)
            sq_x0 = x0 + (w - square_side) / 2
            sq_y0 = y0 + pad
            crop = self.load_photo(companion_m, square_side, square_side, label=label)
            self.draw_pil(c, crop, sq_x0, sq_y0, square_side, square_side)

    def draw_grid_item(self, c, m, x0, y0, w, h, label="", bleed_left=False, bleed_bottom=False):
        book = self.book
        text = book.text_slot(m['idx'])
        if text is not None:
            # The cell shows text instead of the photo; with a companion, the
            # photo itself comes back as a square below the text.
            has_companion = book.text_companion(m['idx'])
            self.draw_text_slot(c, text, x0, y0, w, h, top_align=has_companion,
                                companion_m=m if has_companion else None, label=label,
                                right_align=book.text_align(m['idx']) == "right")
            return
        caption = " ".join(_caption_lines(book.caption(m['idx'])))
        crop = self.load_photo(m, w, h, label=label)
        if caption:
            crop = self.apply_bottom_scrim(crop, strength=0.7, start_frac=0.3)
        self.draw_pil(c, crop, x0, y0, w, h)
        if caption:
            c.setFillColorRGB(1, 1, 1)
            c.setFont(self.serif_b, self.caption_size)
            pad_x = self.caption_bleed_pad if bleed_left else 5
            pad_y = self.caption_bleed_pad if bleed_bottom else 6
            for i, ln in enumerate(reversed(self.caption_wrap(caption, w))):
                c.drawString(x0 + pad_x, y0 + pad_y + i * (self.caption_size + 3.5), ln)
        self.tag_number(c, x0 + w - 4, y0 + 4, m['order'])

    def draw_grid(self, c, bleed, trim, items, label="", manual_order=False, style=None):
        bx0, by0, bx1, by1 = bleed
        W, H = bx1 - bx0, by1 - by0
        c.setFillColorRGB(1, 1, 1)
        c.rect(bx0, by0, W, H, fill=1, stroke=0)
        n = len(items)
        if n == 1:
            self.draw_full_bleed(c, bleed, trim, items[0], caption=self.book.caption(items[0]['idx']), label=label)
            return
        if n == 2:
            if style == 'bleed2':
                # edge to edge, just a thin gutter between the two photos
                gap = 2 * PT_PER_MM
                w = (W - gap) / 2
                h = H
                xs = [bx0, bx0 + w + gap]
                for i, (m, x0) in enumerate(zip(items, xs)):
                    # only the left item touches the left bleed edge; both
                    # touch the bottom one
                    self.draw_grid_item(c, m, x0, by0, w, h, label=label,
                                        bleed_left=(i == 0), bleed_bottom=True)
                return
            w = (W - 2 * MARGIN - GAP) / 2
            h = H - 2 * MARGIN
            xs = [bx0 + MARGIN, bx0 + MARGIN + w + GAP]
            for m, x0 in zip(items, xs):
                self.draw_grid_item(c, m, x0, by0 + MARGIN, w, h, label=label)
        elif n == 3:
            # The big-left slot is portrait-leaning, the two small ones
            # landscape-leaning: route the most portrait photo into the big
            # slot, unless a manual order pins the placement.
            if not manual_order:
                items = sorted(items, key=lambda m: -(self._photo_size(m)[1] / self._photo_size(m)[0]))
            big_w = (W - 2 * MARGIN - GAP) * 0.62
            small_w = (W - 2 * MARGIN - GAP) - big_w
            h = H - 2 * MARGIN
            small_h = (h - GAP) / 2
            ys = [by0 + MARGIN + small_h + GAP, by0 + MARGIN]
            if style == 'mirror3':
                # two small slots stacked on the LEFT, big slot on the RIGHT;
                # items in order [top-left, bottom-left, big-right]
                x0_small = bx0 + MARGIN
                x0_big = bx0 + MARGIN + small_w + GAP
                for m, y0 in zip(items[0:2], ys):
                    self.draw_grid_item(c, m, x0_small, y0, small_w, small_h, label=label)
                self.draw_grid_item(c, items[2], x0_big, by0 + MARGIN, big_w, h, label=label)
            else:
                m0 = items[0]
                if style == 'portrait3_bleed':
                    # the big photo runs into the bleed top and bottom; the
                    # left margin and the gap to the small column stay
                    self.draw_grid_item(c, m0, bx0 + MARGIN, by0, big_w, H, label=label, bleed_bottom=True)
                else:
                    self.draw_grid_item(c, m0, bx0 + MARGIN, by0 + MARGIN, big_w, h, label=label)
                x1 = bx0 + MARGIN + big_w + GAP
                for m, y0 in zip(items[1:3], ys):
                    self.draw_grid_item(c, m, x1, y0, small_w, small_h, label=label)
        elif n == 4:
            w = (W - 2 * MARGIN - GAP) / 2
            h = (H - 2 * MARGIN - GAP) / 2
            positions = [(bx0 + MARGIN, by0 + MARGIN + h + GAP), (bx0 + MARGIN + w + GAP, by0 + MARGIN + h + GAP),
                         (bx0 + MARGIN, by0 + MARGIN), (bx0 + MARGIN + w + GAP, by0 + MARGIN)]
            for m, (x0, y0) in zip(items, positions):
                self.draw_grid_item(c, m, x0, y0, w, h, label=label)

    def draw_chapter_icon(self, c, cx, icon_y):
        # mountain-range mark: a fainter back peak, two solid peaks in front
        if not self.book.style["chapter_icon"]:
            return
        icon_w = 26
        back = c.beginPath()
        back.moveTo(cx - icon_w / 2, icon_y)
        back.lineTo(cx - 2, icon_y + 20)
        back.lineTo(cx + icon_w / 2, icon_y)
        back.close()
        c.setFillColorRGB(1, 1, 1, alpha=0.45)
        c.drawPath(back, fill=1, stroke=0)

        left = c.beginPath()
        left.moveTo(cx - icon_w / 2 - 4, icon_y)
        left.lineTo(cx - icon_w / 2 + 6, icon_y + 13)
        left.lineTo(cx - icon_w / 2 + 15, icon_y)
        left.close()
        c.setFillColorRGB(1, 1, 1, alpha=0.85)
        c.drawPath(left, fill=1, stroke=0)

        right = c.beginPath()
        right.moveTo(cx + icon_w / 2 - 15, icon_y)
        right.lineTo(cx + icon_w / 2 - 5, icon_y + 15)
        right.lineTo(cx + icon_w / 2 + 4, icon_y)
        right.close()
        c.setFillColorRGB(1, 1, 1, alpha=0.85)
        c.drawPath(right, fill=1, stroke=0)

        c.setStrokeColorRGB(1, 1, 1, alpha=0.4)
        c.setLineWidth(0.6)
        c.line(cx - 16, icon_y - 10, cx + 16, icon_y - 10)

    def draw_chapter_silhouette(self, c, day_id, bx0, by0, right_x, keep_clear=None, edge_x=None, max_peak=165):
        # A faint single-stroke ridgeline low on a chapter-opener page: tallest
        # peak at the book edge (bx0), trailing off flat toward `right_x` (the
        # inset photo's left edge). Seeded per day, so reproducible.
        # `keep_clear` = (x0, x1, min_y) is the ghosted day number's footprint,
        # which the line clears by construction. `edge_x` extends the flat
        # run-out to the bleed edge so the line never stops in mid-air.
        # `max_peak` is taller on days with a short intro text.
        rng = random.Random(zlib.crc32(day_id.encode()))
        baseline_y = by0 + 14
        span = right_x - bx0

        # Coarse skeleton: peaks decreasing rightward, valleys part-way up,
        # then a flat run-out; roughened by midpoint displacement below.
        n_peaks = rng.randint(4, 6)
        heights = [max_peak * rng.uniform(0.88, 1.0)]
        for _ in range(1, n_peaks):
            heights.append(max(heights[-1] * rng.uniform(0.6, 0.85), max_peak * 0.12))
        peak_run_frac = 0.68  # peaks occupy the left ~68% of the span
        peak_xs = [bx0]
        for i in range(1, n_peaks):
            frac = (i / (n_peaks - 1)) * peak_run_frac + rng.uniform(-0.015, 0.015)
            peak_xs.append(bx0 + max(frac, 0.02) * span)

        # Clear the day number by splicing extra peak/valley pairs across its
        # footprint (clamping afterwards produced visibly straight plateaus).
        clear_x0 = clear_x1 = None
        if keep_clear is not None:
            kx0, kx1, kmin_y = keep_clear
            clearance_h = (kmin_y - baseline_y) + 18
            heights[0] = max(heights[0], clearance_h * 1.1)
            clear_x0, clear_x1 = kx0, kx1 + 24
            if len(peak_xs) > 1 and peak_xs[1] < clear_x1:
                n_extra = 2 if (clear_x1 - peak_xs[0]) > span * 0.22 else 1
                extra_xs = [peak_xs[0] + (clear_x1 - peak_xs[0]) * (i + 1) / (n_extra + 1) for i in range(n_extra)]
                extra_heights = [clearance_h * rng.uniform(1.0, 1.18) for _ in extra_xs]
                peak_xs = [peak_xs[0]] + extra_xs + peak_xs[1:]
                heights = [heights[0]] + extra_heights + heights[1:]
                n_peaks = len(peak_xs)
            elif n_peaks > 1:
                heights[1] = max(heights[1], clearance_h * 1.05)

        pts = [(peak_xs[0], baseline_y + heights[0])]
        for i in range(1, n_peaks):
            valley_x = (peak_xs[i - 1] + peak_xs[i]) / 2 + rng.uniform(-8, 8)
            if clear_x0 is not None and (clear_x0 - 10) <= valley_x <= clear_x1:
                valley_h = max(min(heights[i - 1], heights[i]) * rng.uniform(0.78, 0.9), clearance_h)
            else:
                valley_h = min(heights[i - 1], heights[i]) * rng.uniform(0.4, 0.62)
            pts.append((valley_x, baseline_y + valley_h))
            pts.append((peak_xs[i], baseline_y + heights[i]))
        runout_x0 = peak_xs[-1]
        for frac in (0.35, 0.7):
            rx = runout_x0 + (right_x - runout_x0) * frac
            pts.append((rx, baseline_y + heights[-1] * (1 - frac) * 0.3))
        pts.append((right_x, baseline_y))
        if edge_x is not None and edge_x > right_x:
            pts.append((edge_x, baseline_y))

        # midpoint displacement for natural jaggedness
        roughness = max_peak * 0.065
        for _ in range(4):
            refined = [pts[0]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                my += rng.uniform(-1, 1) * roughness
                my = max(my, baseline_y - 2)
                refined.append((mx, my))
                refined.append((x1, y1))
            pts = refined
            roughness *= 0.5

        # light moving-average smoothing (x stays fixed)
        for _ in range(2):
            smoothed = [pts[0]]
            for i in range(1, len(pts) - 1):
                x, y = pts[i]
                _, yp = pts[i - 1]
                _, yn = pts[i + 1]
                smoothed.append((x, (yp + 2 * y + yn) / 4))
            smoothed.append(pts[-1])
            pts = smoothed

        if keep_clear is not None:
            # safety net: nudge up only the odd point that still dips under
            kx0, kx1, kmin_y = keep_clear
            pad = 10
            pts = [
                (x, kmin_y + (kmin_y - y) * 0.15) if (kx0 - pad <= x <= kx1 + pad and y < kmin_y) else (x, y)
                for x, y in pts
            ]

        path = c.beginPath()
        path.moveTo(*pts[0])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        c.setStrokeColorRGB(0.78, 0.79, 0.81, alpha=0.38)
        c.setLineWidth(0.85)
        c.drawPath(path, fill=0, stroke=1)

    def _dark_background(self, c, bleed):
        bx0, by0, bx1, by1 = bleed
        c.setFillColorRGB(*self.dark_color)
        c.rect(bx0, by0, bx1 - bx0, by1 - by0, fill=1, stroke=0)

    def draw_title_page(self, c, bleed, trim):
        front = self.book.front
        self._dark_background(c, bleed)
        tx0, ty0, tx1, ty1 = trim
        cx = (tx0 + tx1) / 2
        cy = (ty0 + ty1) / 2

        self.draw_chapter_icon(c, cx, cy + 108)

        c.setFillColorRGB(1, 1, 1)
        c.setFont(self.serif_b, 32)
        c.drawCentredString(cx, cy + 56, front.get("title", ""))
        c.setStrokeColorRGB(1, 1, 1, alpha=0.5)
        c.setLineWidth(0.75)
        c.line(cx - 50, cy + 38, cx + 50, cy + 38)
        c.setFont(self.serif_i, 11)
        c.setFillColorRGB(1, 1, 1, alpha=0.85)
        c.drawCentredString(cx, cy + 18, front.get("tagline", ""))

        c.setFont(self.serif, 10.5)
        c.setFillColorRGB(1, 1, 1, alpha=0.82)
        y = cy - 20
        for para in front.get("intro", []):
            for ln in textwrap.wrap(para, 46):
                c.drawCentredString(cx, y, ln)
                y -= 15
            y -= 8

    def draw_front_image(self, c, bleed, trim, label=""):
        # usually a map of the trip; without one the page stays blank
        image = self.book.front.get("image")
        if not image:
            self.draw_blank(c, bleed, trim)
            return
        bx0, by0, bx1, by1 = bleed
        w, h = bx1 - bx0, by1 - by0
        crop = self.load_crop(self.book.resolve(image), w, h, label=label)
        self.draw_pil(c, crop, bx0, by0, w, h)

    def draw_closing_text(self, c, bleed, trim):
        closing = self.book.closing
        self._dark_background(c, bleed)
        tx0, ty0, tx1, ty1 = trim
        cx = (tx0 + tx1) / 2
        cy = (ty0 + ty1) / 2
        c.setFont(self.serif_i, 10.5)
        c.setFillColorRGB(1, 1, 1, alpha=0.8)
        c.drawCentredString(cx, cy + 34, closing.get("lead", ""))
        c.setFillColorRGB(1, 1, 1)
        c.setFont(self.serif_b, 17)
        c.drawCentredString(cx, cy + 10, closing.get("headline", ""))
        c.setFont(self.serif, 10)
        c.setFillColorRGB(1, 1, 1, alpha=0.8)
        c.drawCentredString(cx, cy - 12, closing.get("date", ""))

    def draw_blank(self, c, bleed, trim):
        bx0, by0, bx1, by1 = bleed
        c.setFillColorRGB(0.93, 0.92, 0.89)
        c.rect(bx0, by0, bx1 - bx0, by1 - by0, fill=1, stroke=0)

    def draw_chapter_opener(self, c, bleed, trim, day, inset_m=None, label=""):
        bx0, by0, bx1, by1 = bleed
        w, h = bx1 - bx0, by1 - by0
        self._dark_background(c, bleed)
        tx0, ty0, tx1, ty1 = trim

        inset_w = w * 0.36
        inset_h = h * 0.44
        ix0 = bx1 - inset_w
        iy0 = by0 + h * 0.10
        silhouette_right = ix0 if inset_m is not None else (tx1 - INSET)

        number = str(day["number"]).zfill(2)
        title_lines = textwrap.wrap(day["title"].upper(), 20)

        # the ghosted day number (74pt, baseline ty0+26) is a keep-clear zone
        text_x = tx0 + INSET
        num_y0 = ty0 + 26
        num_top = num_y0 + 74 * 0.72
        num_x0 = text_x
        num_x1 = text_x + c.stringWidth(number, self.serif_b, 74)

        intro = day["intro"]
        wrap_at = 34 if inset_m is not None else 46
        if self.book.style["chapter_silhouette"]:
            # fewer intro lines -> more open space -> taller leftmost peak
            intro_lines = sum(len(textwrap.wrap(p, wrap_at)) for p in intro)
            max_peak = min(210, 158 + 13 * max(0, 4 - intro_lines))
            self.draw_chapter_silhouette(c, day["id"], bx0, by0, silhouette_right,
                                         keep_clear=(num_x0, num_x1, num_top + 14), edge_x=bx1,
                                         max_peak=max_peak)

        # title, tagline and intro are left-aligned on the same margin as the
        # ghosted number; the icon's left edge lines up with it too
        icon_y = ty1 - 90
        self.draw_chapter_icon(c, text_x + 17, icon_y)

        c.setFillColorRGB(1, 1, 1)
        c.setFont(self.serif_b, 22)
        title_y = icon_y - 44
        for i, ln in enumerate(title_lines):
            c.drawString(text_x, title_y - i * 27, ln)
        rule_y = title_y - (len(title_lines) - 1) * 27 - 28
        c.setStrokeColorRGB(1, 1, 1, alpha=0.5)
        c.setLineWidth(0.75)
        c.line(text_x, rule_y, text_x + 88, rule_y)

        tagline = day['label'].upper()
        if day.get('date'):
            tagline += f" · {day['date'].upper()}"
        tagline_y = rule_y - 20
        c.setFont(self.serif_i, 10)
        c.setFillColorRGB(1, 1, 1, alpha=0.8)
        c.drawString(text_x, tagline_y, tagline)

        c.setFont(self.serif_b, 74)
        c.setFillColorRGB(1, 1, 1, alpha=0.22)
        c.drawString(tx0 + INSET, ty0 + 26, number)

        if inset_m is not None:
            crop = self.load_photo(inset_m, inset_w, inset_h, label=label)
            inset_caption = " ".join(_caption_lines(self.book.caption(inset_m['idx'])))
            if inset_caption:
                crop = self.apply_bottom_scrim(crop, strength=0.7, start_frac=0.3)
            self.draw_pil(c, crop, ix0, iy0, inset_w, inset_h)
            if inset_caption:
                c.setFillColorRGB(1, 1, 1)
                c.setFont(self.serif_b, self.caption_size)
                for i, ln in enumerate(reversed(self.caption_wrap(inset_caption, inset_w))):
                    c.drawString(ix0 + 6, iy0 + 7 + i * (self.caption_size + 3.5), ln)

        # the intro column stays left of the inset photo
        if intro:
            c.setFont(self.serif, 9.5)
            c.setFillColorRGB(1, 1, 1, alpha=0.8)
            y = tagline_y - 34
            for para in intro:
                for ln in textwrap.wrap(para, wrap_at):
                    c.drawString(text_x, y, ln)
                    y -= 13
                y -= 7

    def draw_spread_half(self, c, side, m, label=""):
        bleed, trim = self.rect_for_side(side)
        bx0, by0, bx1, by1 = bleed
        pb = self.p.pages_bleed
        full_crop = self.load_crop(self.book.img_path(m), pb[2] - pb[0], pb[3] - pb[1], label=label)
        cw, ch = full_crop.size
        half_px = cw // 2
        if side == 'left':
            half = full_crop.crop((0, 0, half_px, ch))
        else:
            half = full_crop.crop((half_px, 0, cw, ch))
        # Both halves get the scrim so it runs across the seam as one bar;
        # only the left half carries the caption text. No page number - the
        # caption is the only label a panorama gets.
        caption = self.book.spread_caption(m['idx'])
        if caption:
            half = self.apply_bottom_scrim(half, strength=0.65, start_frac=0.25)
        self.draw_pil(c, half, bx0, by0, bx1 - bx0, by1 - by0)
        if caption and side == 'left':
            tx0, ty0, tx1, ty1 = trim
            c.setFillColorRGB(1, 1, 1)
            c.setFont(self.serif_b, self.caption_size)
            for i, ln in enumerate(reversed(self.caption_wrap(caption, (tx1 - tx0) - INSET))):
                c.drawString(tx0 + INSET, ty0 + 14 + i * (self.caption_size + 3.5), ln)

    def rect_for_side(self, side):
        pb, pt, cx = self.p.pages_bleed, self.p.pages_trim, self.p.trim_center_x
        if side == 'left':
            return (pb[0], pb[1], cx, pb[3]), (pt[0], pt[1], cx, pt[3])
        return (cx, pb[1], pb[2], pb[3]), (cx, pt[1], pt[2], pt[3])

    def draw_logical_page(self, c, spec, side, page_no):
        bleed, trim = self.rect_for_side(side)
        kind = spec[0]
        label = f"p{page_no:03d}"
        if kind == 'title':
            self.draw_title_page(c, bleed, trim)
        elif kind == 'front_image':
            self.draw_front_image(c, bleed, trim, label=label)
        elif kind == 'opener':
            _, m, extra = spec
            self.draw_chapter_opener(c, bleed, trim, extra['day'], inset_m=extra.get('inset'), label=label)
        elif kind == 'opener_photo':
            self.draw_full_bleed(c, bleed, trim, spec[1], label=label)
        elif kind in ('hero_float', 'closing_photo'):
            _, m, extra = spec
            self.draw_full_bleed(c, bleed, trim, m, caption=extra.get('caption'), label=label)
        elif kind == 'spread_image':
            self.draw_spread_half(c, side, spec[1], label=label)
        elif kind.startswith('grid'):
            extra = spec[2] if len(spec) > 2 else {}
            self.draw_grid(c, bleed, trim, spec[1], label=label,
                           manual_order=extra.get('manual_order', False), style=extra.get('style'))
        elif kind == 'closing_text':
            self.draw_closing_text(c, bleed, trim)
        elif kind == 'blank':
            self.draw_blank(c, bleed, trim)
        else:
            raise ValueError(f"unknown page kind {kind!r}")

    # ---------- whole documents ----------

    def render_pages(self, pages_spec, out_path, work_dir, spreads=None):
        """Render the interior. Each spread goes into its own small PDF that
        is flushed right away - one long-lived canvas accumulated image
        buffers and showed as a grey wash on later pages."""
        os.makedirs(work_dir, exist_ok=True)
        n_spreads = len(pages_spec) // 2
        wanted = range(n_spreads) if spreads is None else spreads
        spread_paths = []
        for s in wanted:
            path = os.path.join(work_dir, f"spread_{s:03d}.pdf")
            c = canvas.Canvas(path, pagesize=(self.p.pages_media[2], self.p.pages_media[3]))
            self.draw_logical_page(c, pages_spec[2 * s], 'left', 2 * s)
            self.draw_logical_page(c, pages_spec[2 * s + 1], 'right', 2 * s + 1)
            c.showPage()
            c.save()
            del c
            gc.collect()
            spread_paths.append(path)
            print(f"spread {s + 1}/{n_spreads} done", flush=True)
        writer = pypdf.PdfWriter()
        for path in spread_paths:
            writer.add_page(pypdf.PdfReader(path).pages[0])
        with open(out_path, 'wb') as f:
            writer.write(f)
        return len(spread_paths)

    def render_cover(self, out_path):
        p, cover = self.p, self.book.cover
        c = canvas.Canvas(out_path, pagesize=(p.cover_media[2], p.cover_media[3]))
        bx0, by0, bx1, by1 = p.cover_bleed
        w, h = bx1 - bx0, by1 - by0
        crop = self.load_photo(self.book.by_idx[cover["photo"]], w, h, label="cover")
        crop = self.apply_bottom_scrim(crop, strength=0.8, start_frac=0.55)
        self.draw_pil(c, crop, bx0, by0, w, h)
        tx0, ty0, tx1, ty1 = p.cover_trim
        c.setFillColorRGB(1, 1, 1)
        c.setFont(self.serif_b, 26)
        c.drawString(tx0 + COVER_TEXT_INSET, ty0 + 108, cover.get("title", ""))
        c.setFont(self.serif, 12)
        c.drawString(tx0 + COVER_TEXT_INSET, ty0 + 86, cover.get("subtitle", ""))
        c.showPage()
        c.save()


def set_print_boxes(pdf_path, trim_rect, bleed_rect, out_path):
    """Set /TrimBox and /BleedBox on every page of our own rendered PDF.

    Don't merge the publisher's downloadable template PDF onto the content:
    those are proof sheets with visible crop/registration marks and no trim
    metadata. MediaBox (= CropBox) already is the raw format incl. bleed."""
    reader = pypdf.PdfReader(pdf_path)
    writer = pypdf.PdfWriter()
    for pg in reader.pages:
        pg.trimbox = pypdf.generic.RectangleObject(trim_rect)
        pg.bleedbox = pypdf.generic.RectangleObject(bleed_rect)
        writer.add_page(pg)
    with open(out_path, 'wb') as f:
        writer.write(f)

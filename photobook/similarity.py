"""Finding the same photo twice: copies, re-exports, edits, bursts.

A book shouldn't show one moment twice by accident - the original book had
the same selfie in three files (camera original, a messenger copy and an
edited export, hours apart in the index) and one of them slipped through to
a late review round. Every pair of photos placed in the book is compared;
pairs that look alike stop the build unless book.json lists them in
`allow_duplicates`.

The signature is the edge structure of a small, centred square crop.
Edges survive what edits change - colour, brightness, resolution,
compression - and differ between two shots of the same view. Measured on
1,105 photos of a real trip (610,000 pairs): every pair at or above 0.85
was either the same file, an edited/messenger copy of it, or a burst shot
seconds apart; distinct photos stayed at or below about 0.3. A copy that
was cropped differently is not caught reliably.
"""
import hashlib
import json
import os

import numpy as np
from PIL import Image, ImageOps

from .book import BookError

THRESHOLD = 0.9
CACHE_FILE = ".photobook-signatures.json"


def signature(path):
    with Image.open(path) as src:
        src.draft('L', (256, 256))
        im = ImageOps.exif_transpose(src).convert('L')
    w, h = im.size
    s = min(w, h)
    sq = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    g = np.asarray(sq.resize((33, 32), Image.LANCZOS), dtype=np.float32)
    edges = np.abs(np.diff(g, axis=1)).ravel()
    edges -= edges.mean()
    return edges / (np.linalg.norm(edges) or 1)


def _cache_key(path):
    st = os.stat(path)
    return hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()


def signatures(book, idxs):
    """idx -> signature, cached next to book.json so repeated builds stay fast."""
    cache_path = os.path.join(book.dir, CACHE_FILE)
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    out, dirty = {}, False
    for idx in idxs:
        path = book.img_path(idx)
        try:
            key = _cache_key(path)
        except OSError as e:
            raise BookError(f"photo idx {idx}: {e}") from None
        if key not in cache:
            try:
                cache[key] = [round(float(v), 5) for v in signature(path)]
            except Exception as e:
                raise BookError(f"photo idx {idx}: cannot read {path} ({e})") from None
            dirty = True
        out[idx] = np.asarray(cache[key], dtype=np.float32)
    if dirty:
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
        except OSError:
            pass  # a read-only project still works, just slower
    return out


def find_duplicates(book, idxs, threshold=THRESHOLD):
    """Pairs (a, b, similarity) among idxs that look alike and are not
    covered by an allow_duplicates group, most similar first."""
    idxs = sorted(set(idxs))
    sigs = signatures(book, idxs)
    allowed = [set(group) for group in book.allow_duplicates]
    mat = np.stack([sigs[i] for i in idxs])
    sim = mat @ mat.T
    pairs = []
    for a in range(len(idxs)):
        for b in range(a + 1, len(idxs)):
            if sim[a, b] >= threshold and not any({idxs[a], idxs[b]} <= g for g in allowed):
                pairs.append((idxs[a], idxs[b], float(sim[a, b])))
    return sorted(pairs, key=lambda p: -p[2])


def describe_duplicates(book, pairs):
    lines = []
    for a, b, sim in pairs:
        ma, mb = book.by_idx[a], book.by_idx[b]
        lines.append(f"numbers {ma['order']:03d} and {mb['order']:03d} (idx {a} / {b}) look alike ({sim:.2f})")
    return lines

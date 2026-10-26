"""Page planning: turns a Book into a flat list of logical pages.

No image is decoded here (except the photo headers that 3-photo grids read
to sort by aspect ratio at render time - not here), so planning a whole
book takes milliseconds. That is what makes `photobook pages` and the
PATTERN search fast.

A logical page is a tuple `(kind, payload, extra)`; two consecutive logical
pages form one physical spread (left, right). Kinds:

  title, front_image            the opening spread
  opener, opener_photo          a day's two-page chapter opener
  spread_image (x2)             a two-page panorama, left and right half
  gridN                         a grid page with N photos (N=1: full-bleed)
  hero_float                    a captioned full-bleed highlight page
  closing_photo, closing_text   the closing spread
  blank                         filler for a day with an odd page count
                                (only with fill_odd_days_with_blank)
"""


class LayoutError(Exception):
    pass


def build_day_units(remaining, pattern, hero_idx=None, by_idx_item=None, solo_idxs=(), special_groups=(), mid_spread_idx=None):
    """Walk a day's chronologically-sorted remaining photos and group them into
    'units' - each unit is exactly ONE physical page (a grid batch of 2-4
    photos, the floating hero as its own full-bleed page, a solo full-bleed
    photo, or a hand-placed group of several photos) - interrupting the
    current grid batch at each special item/group's true chronological
    position instead of always leading the day with it.

    PATTERN cycles per day: its index restarts at 0 for every day.

    `mid_spread_idx`, if given, is a photo that becomes a 2-page panorama
    spread positioned mid-day - represented as TWO consecutive
    ('spread_pano', m) units so the parity math below still treats each
    physical page as one list entry."""
    solo_idxs = set(solo_idxs)
    group_member_idx = {}
    groups = {}
    for gi, g in enumerate(special_groups):
        groups[gi] = (g["photos"], g["style"])
        for ix in g["photos"]:
            group_member_idx[ix] = gi
    emitted_groups = set()
    units = []
    i = 0
    batch = []

    def flush():
        nonlocal batch, i
        if batch:
            units.append(('grid', list(batch)))
            batch = []
            i += 1

    for m in remaining:
        idx = m['idx']
        if mid_spread_idx is not None and idx == mid_spread_idx:
            flush()
            units.append(('spread_pano', m))
            units.append(('spread_pano', m))
            continue
        if idx in group_member_idx:
            gi = group_member_idx[idx]
            if gi in emitted_groups:
                continue  # a later member of an already-emitted group - skip
            flush()
            ordered_idxs, style = groups[gi]
            payload = [by_idx_item[i2] for i2 in ordered_idxs]
            # 'portrait3' / 'portrait3_bleed' rely on the grid's aspect-ratio
            # auto-sort (most-portrait photo wins the big slot); every other
            # style keeps the given order.
            units.append(('grid', payload, {'manual_order': style not in ('portrait3', 'portrait3_bleed'), 'style': style}))
            emitted_groups.add(gi)
            continue
        if idx in solo_idxs:
            flush()
            units.append(('grid', [m]))
            continue
        if hero_idx is not None and idx == hero_idx:
            flush()
            units.append(('hero_float', m))
            continue
        step = pattern[i % len(pattern)]
        batch.append(m)
        if len(batch) >= step:
            flush()
    flush()
    return units


def fix_parity(units, where=""):
    """The opener (and an optional panorama) is always exactly 2 pages, so a
    day stays a whole number of spreads only if its count of single-page
    units is even - otherwise the NEXT day's opener would straddle two
    spreads. If odd, split the first plain grid batch with >=2 photos into
    two smaller ones, without dropping or duplicating a photo. Hand-placed
    groups (units carrying a style dict) are never split."""
    if len(units) % 2 == 0:
        return units
    for i, unit in enumerate(units):
        kind = unit[0]
        if kind == 'grid' and len(unit) == 2 and len(unit[1]) >= 2:
            payload = unit[1]
            half = len(payload) // 2
            return units[:i] + [('grid', payload[:half]), ('grid', payload[half:])] + units[i + 1:]
    raise LayoutError(f"{where}: odd number of pages and no plain grid page with 2+ photos to split - "
                      "add or remove a photo, or change 'pattern', 'solo_fullbleed' or 'groups'")


def _day_pages(book, day, pattern):
    day_id = day["id"]
    items = sorted(book.by_day[day_id], key=lambda m: m['order'])
    by_idx_item = {m['idx']: m for m in items}
    op_idx = day.get("opener")
    hero = day.get("hero")
    hero_idx = hero["photo"] if hero else None
    pano_idx = day.get("panorama_after_opener")
    # the closing photo gets its own page at the end of the book
    closing_idx = book.closing["photo"]

    # The opener's small inset teaser is picked up front (the first
    # chronological photo of the day, excluding opener and panorama) so it
    # can be excluded from the grid pool - otherwise it shows up twice.
    inset_m = None
    if op_idx is not None:
        if day.get("inset") is not None:
            inset_m = by_idx_item[day["inset"]]
        else:
            candidates = [m for m in items if m['idx'] not in (op_idx, pano_idx, closing_idx)]
            inset_m = candidates[0] if candidates else None

    exclude = {op_idx, pano_idx, closing_idx} | ({inset_m['idx']} if inset_m else set())
    # The hero, solo, group and mid-day-panorama photos deliberately stay in
    # `remaining`: build_day_units places them at their chronological spot.
    remaining = [m for m in items if m['idx'] not in exclude]
    mid_spread_idx = day.get("mid_day_panorama")
    day_units = build_day_units(
        remaining, pattern, hero_idx=hero_idx, by_idx_item=by_idx_item,
        solo_idxs=day["solo_fullbleed"], special_groups=day["groups"],
        mid_spread_idx=mid_spread_idx,
    )
    def parity(units, where):
        try:
            return fix_parity(units, where)
        except LayoutError:
            # early drafts: rather a visible blank page than no plan at all
            if book.fill_odd_days_with_blank:
                return units + [('blank',)]
            raise

    if mid_spread_idx is not None:
        # The mid-day panorama must start on a left page, so parity is fixed
        # separately before and after it.
        marker_pos = next(ui for ui, u in enumerate(day_units) if u[0] == 'spread_pano')
        before = parity(day_units[:marker_pos], f"day {day_id}, before the mid-day panorama")
        after = parity(day_units[marker_pos + 2:], f"day {day_id}, after the mid-day panorama")
        units = before + day_units[marker_pos:marker_pos + 2] + after
    else:
        units = parity(day_units, f"day {day_id}")

    if day.get("hero_before_previous_page"):
        # Swap the hero with the page right before it (same spread, other
        # side) - doesn't change chronology or page count.
        for ui in range(1, len(units)):
            if units[ui][0] == 'hero_float':
                units[ui - 1], units[ui] = units[ui], units[ui - 1]
                break

    pages = []
    if op_idx is not None:
        m0 = by_idx_item[op_idx]
        pages.append(('opener', m0, {'day': day, 'inset': inset_m}))
        pages.append(('opener_photo', m0))
    if pano_idx is not None:
        pm = by_idx_item[pano_idx]
        pages.append(('spread_image', pm))
        pages.append(('spread_image', pm))
    for unit in units:
        if unit[0] == 'blank':
            pages.append(('blank',))
            continue
        kind, payload = unit[0], unit[1]
        if kind == 'grid':
            if len(unit) > 2:
                pages.append((f'grid{len(payload)}', payload, unit[2]))
            else:
                pages.append((f'grid{len(payload)}', payload))
        elif kind == 'spread_pano':
            pages.append(('spread_image', payload))
        else:
            pages.append(('hero_float', payload, {'caption': hero.get("caption")}))
    return pages


def entry_idxs(spec):
    """The photo idx(s) a logical page shows."""
    kind = spec[0]
    if kind.startswith('grid'):
        return {m['idx'] for m in spec[1]}
    if kind in ('opener', 'opener_photo', 'closing_photo', 'hero_float', 'spread_image'):
        return {spec[1]['idx']}
    return set()


def _find_block(pages_spec, idxs):
    """Contiguous run of pages whose photos are all inside `idxs` - the
    physical block occupied by exactly that group of photos."""
    matches = [i for i, s in enumerate(pages_spec) if entry_idxs(s) & idxs]
    if not matches:
        raise LayoutError(f"page_swaps: no pages found for {sorted(idxs)}")
    start, end = matches[0], matches[-1] + 1
    if matches != list(range(start, end)):
        raise LayoutError(f"page_swaps: pages for {sorted(idxs)} are not contiguous: {matches}")
    if not all(entry_idxs(pages_spec[i]) <= idxs for i in matches):
        raise LayoutError(f"page_swaps: block for {sorted(idxs)} also contains photos not listed")
    return start, end


def swap_adjacent_blocks(pages_spec, idxs_a, idxs_b):
    sa, ea = _find_block(pages_spec, set(idxs_a))
    sb, eb = _find_block(pages_spec, set(idxs_b))
    if ea != sb:
        raise LayoutError(f"page_swaps: blocks {sorted(idxs_a)} (ends {ea}) and {sorted(idxs_b)} (starts {sb}) are not adjacent, a before b")
    pages_spec[sa:eb] = pages_spec[sb:eb] + pages_spec[sa:ea]


def check(pages_spec, page_count=None):
    """Structural invariants of a finished page list."""
    if page_count is not None and len(pages_spec) != page_count:
        raise LayoutError(f"expected {page_count} pages, got {len(pages_spec)} - adjust 'pattern' (see `photobook pattern-search`)")
    if len(pages_spec) % 2:
        raise LayoutError(f"odd number of pages ({len(pages_spec)}) - pages come in spreads")
    # every opener / panorama must start on a left page (even index)
    prev_kind = None
    for i, spec in enumerate(pages_spec):
        kind = spec[0]
        if kind in ('opener', 'spread_image') and kind != prev_kind and i % 2 != 0:
            raise LayoutError(f"page-pairing bug: {kind} at page {i} does not start on a left page")
        prev_kind = kind
    # A photo used as opener/hero/inset/closing must never show up again in a
    # grid. 'opener' carries its photo only as metadata (it is drawn once,
    # via 'opener_photo'), but its inset IS drawn. 'spread_image' appears
    # twice on purpose (two halves of one panorama).
    seen = set()
    for spec in pages_spec:
        kind = spec[0]
        if kind.startswith('grid'):
            photos = spec[1]
        elif kind in ('opener_photo', 'hero_float', 'closing_photo'):
            photos = [spec[1]]
        elif kind == 'opener':
            photos = [spec[2]['inset']] if spec[2].get('inset') else []
        else:
            continue
        for m in photos:
            if m['idx'] in seen:
                raise LayoutError(f"duplicate photo: idx {m['idx']} is drawn more than once (kind={kind})")
            seen.add(m['idx'])


def plan(book, pattern=None, check_page_count=True):
    """The book's full logical page list."""
    pattern = pattern or book.pattern
    pages_spec = [('title',), ('front_image',)]
    for day in book.days:
        pages_spec += _day_pages(book, day, pattern)
    # Mirrors the opening spread: photo on the left, farewell text closes
    # the book on the right.
    closing = book.closing
    pages_spec.append(('closing_photo', book.by_idx[closing["photo"]], {'caption': closing.get("caption")}))
    pages_spec.append(('closing_text',))

    # Hand-requested block swaps that the chronological placement can't
    # produce, applied to the finished list so nothing about day
    # construction (PATTERN cycling, printed numbers) changes.
    for swap in book.page_swaps:
        swap_adjacent_blocks(pages_spec, swap["a"], swap["b"])

    check(pages_spec, book.page_count if check_page_count else None)
    return pages_spec


def unplaced_photos(book, pages_spec):
    placed = set()
    for spec in pages_spec:
        placed |= entry_idxs(spec)
        if spec[0] == 'opener' and spec[2].get('inset'):
            placed.add(spec[2]['inset']['idx'])
    return [m for m in book.manifest if m['idx'] not in placed]


def describe(spec):
    """One-line summary of a logical page, with printed numbers - the same
    numbers the user writes feedback against."""
    kind = spec[0]
    if kind.startswith('grid'):
        style = spec[2].get('style', '') if len(spec) > 2 else ''
        nums = ", ".join(f"{m['order']:03d}" for m in spec[1])
        return f"{kind}{' ' + style if style else ''}: {nums}"
    if kind == 'opener':
        inset = spec[2].get('inset')
        return f"opener {spec[2]['day']['id']}" + (f" (inset {inset['order']:03d})" if inset else "")
    if len(spec) > 1 and isinstance(spec[1], dict):
        return f"{kind}: {spec[1]['order']:03d}"
    return kind

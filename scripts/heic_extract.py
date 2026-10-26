#!/usr/bin/env python3
"""Minimal HEIC primary-image extractor: bypasses libheif's iref/aux-image
validation bug by manually parsing the ISOBMFF boxes we need (meta/iinf/pitm/
iloc/iprp/ipco/ipma/iref) to pull out the primary item's HEVC bitstream(s)
and hvcC decoder config, decode via ffmpeg's raw hevc decoder, and (for
grid-type primary items, common for full-res iPhone photos) reassemble the
tiles into the full image with PIL.
"""
import sys, struct, subprocess, os, tempfile
from PIL import Image

def read_box_header(data, pos):
    size = struct.unpack('>I', data[pos:pos+4])[0]
    btype = data[pos+4:pos+8].decode('latin1')
    hdr = 8
    if size == 1:
        size = struct.unpack('>Q', data[pos+8:pos+16])[0]
        hdr = 16
    elif size == 0:
        size = len(data) - pos
    return btype, pos, hdr, size

def iter_boxes(data, start, end):
    pos = start
    while pos < end:
        btype, bpos, hdr, size = read_box_header(data, pos)
        if size < hdr:
            break
        yield btype, bpos + hdr, bpos + size
        pos = bpos + size

def find_box(data, start, end, target):
    for btype, cstart, cend in iter_boxes(data, start, end):
        if btype == target:
            return cstart, cend
    return None, None

def parse_infe_items(data, start, end):
    items = {}
    for btype, cstart, cend in iter_boxes(data, start, end):
        if btype != 'infe':
            continue
        p = cstart
        version = data[p]
        p += 4
        if version >= 2:
            idsize = 2 if version == 2 else 4
            item_id = int.from_bytes(data[p:p+idsize], 'big'); p += idsize
            p += 2
            item_type = data[p:p+4].decode('latin1'); p += 4
            items[item_id] = item_type
    return items

def parse_pitm(data, start, end):
    p = start
    version = data[p]
    p += 4
    idsize = 2 if version == 0 else 4
    return int.from_bytes(data[p:p+idsize], 'big')

def parse_iloc(data, start, end, idat_start=None):
    p = start
    version = data[p]
    p += 4
    b = data[p]; p += 1
    offset_size = b >> 4
    length_size = b & 0xF
    # base_offset_size is present in every version; the low nibble is
    # index_size in v1/v2 and reserved in v0
    b2 = data[p]; p += 1
    base_offset_size = b2 >> 4
    index_size = (b2 & 0xF) if version in (1, 2) else 0
    if version < 2:
        item_count = int.from_bytes(data[p:p+2], 'big'); p += 2
    else:
        item_count = int.from_bytes(data[p:p+4], 'big'); p += 4
    items = {}
    construction = {}
    for _ in range(item_count):
        if version < 2:
            item_id = int.from_bytes(data[p:p+2], 'big'); p += 2
        else:
            item_id = int.from_bytes(data[p:p+4], 'big'); p += 4
        constr_method = 0
        if version in (1, 2):
            cm = int.from_bytes(data[p:p+2], 'big'); p += 2
            constr_method = cm & 0xF
        p += 2
        base_offset = int.from_bytes(data[p:p+base_offset_size], 'big') if base_offset_size else 0
        p += base_offset_size
        extent_count = int.from_bytes(data[p:p+2], 'big'); p += 2
        extents = []
        for _ in range(extent_count):
            if index_size:
                p += index_size
            ext_offset = int.from_bytes(data[p:p+offset_size], 'big') if offset_size else 0
            p += offset_size
            ext_length = int.from_bytes(data[p:p+length_size], 'big') if length_size else 0
            p += length_size
            # construction_method 1 = offsets relative to the 'idat' box content
            origin = (idat_start or 0) if constr_method == 1 else 0
            extents.append((origin + base_offset + ext_offset, ext_length))
        items[item_id] = extents
        construction[item_id] = constr_method
    return items

def parse_ipco(data, start, end):
    return list(iter_boxes(data, start, end))

def parse_ipma(data, start, end):
    p = start
    version = data[p]
    flags = int.from_bytes(data[p+1:p+4], 'big')
    p += 4
    entry_count = int.from_bytes(data[p:p+4], 'big'); p += 4
    assoc = {}
    for _ in range(entry_count):
        if version < 1:
            item_id = int.from_bytes(data[p:p+2], 'big'); p += 2
        else:
            item_id = int.from_bytes(data[p:p+4], 'big'); p += 4
        assoc_count = data[p]; p += 1
        idxs = []
        for _ in range(assoc_count):
            if flags & 1:
                v = int.from_bytes(data[p:p+2], 'big'); p += 2
                idx = v & 0x7FFF
            else:
                v = data[p]; p += 1
                idx = v & 0x7F
            idxs.append(idx)
        assoc[item_id] = idxs
    return assoc

def parse_iref(data, start, end):
    p = start
    version = data[p]
    p += 4
    refs = {}
    idsize = 2 if version == 0 else 4
    for btype, cs, ce in iter_boxes(data, p, end):
        q = cs
        from_id = int.from_bytes(data[q:q+idsize], 'big'); q += idsize
        ref_count = int.from_bytes(data[q:q+2], 'big'); q += 2
        to_ids = []
        for _ in range(ref_count):
            to_id = int.from_bytes(data[q:q+idsize], 'big'); q += idsize
            to_ids.append(to_id)
        refs.setdefault(btype, {})[from_id] = to_ids
    return refs

def nal_units_from_hvcc(hvcc_data):
    p = 22
    num_arrays = hvcc_data[p]; p += 1
    nals = []
    for _ in range(num_arrays):
        p += 1
        num_nalus = int.from_bytes(hvcc_data[p:p+2], 'big'); p += 2
        for _ in range(num_nalus):
            nal_len = int.from_bytes(hvcc_data[p:p+2], 'big'); p += 2
            nals.append(hvcc_data[p:p+nal_len])
            p += nal_len
    return nals

def length_prefixed_to_annexb(data, length_size=4):
    out = bytearray()
    p = 0
    while p < len(data):
        if p + length_size > len(data):
            break
        nal_len = int.from_bytes(data[p:p+length_size], 'big')
        p += length_size
        nal = data[p:p+nal_len]
        p += nal_len
        out += b'\x00\x00\x00\x01' + nal
    return bytes(out)

class HeicDoc:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = f.read()
        n = len(self.data)
        meta_start, meta_end = find_box(self.data, 0, n, 'meta')
        if meta_start is None:
            raise ValueError('no meta box')
        mp = meta_start + 4
        iinf_s, iinf_e = find_box(self.data, mp, meta_end, 'iinf')
        pitm_s, pitm_e = find_box(self.data, mp, meta_end, 'pitm')
        iloc_s, iloc_e = find_box(self.data, mp, meta_end, 'iloc')
        iprp_s, iprp_e = find_box(self.data, mp, meta_end, 'iprp')
        iref_s, iref_e = find_box(self.data, mp, meta_end, 'iref')
        idat_s, idat_e = find_box(self.data, mp, meta_end, 'idat')
        p = iinf_s
        iinf_ver = self.data[p]; p += 4
        ecsize = 2 if iinf_ver == 0 else 4
        p += ecsize
        self.items = parse_infe_items(self.data, p, iinf_e)
        self.primary_id = parse_pitm(self.data, pitm_s, pitm_e)
        self.ilocs = parse_iloc(self.data, iloc_s, iloc_e, idat_start=idat_s)
        ipco_s, ipco_e = find_box(self.data, iprp_s, iprp_e, 'ipco')
        ipma_s, ipma_e = find_box(self.data, iprp_s, iprp_e, 'ipma')
        self.props = parse_ipco(self.data, ipco_s, ipco_e)
        self.assoc = parse_ipma(self.data, ipma_s, ipma_e)
        self.iref = parse_iref(self.data, iref_s, iref_e) if iref_s else {}

    def item_props(self, item_id):
        out = []
        for idx in self.assoc.get(item_id, []):
            if 1 <= idx <= len(self.props):
                out.append(self.props[idx - 1])
        return out

    def item_prop(self, item_id, ptype):
        for btype, cs, ce in self.item_props(item_id):
            if btype == ptype:
                return self.data[cs:ce]
        return None

    def item_ispe(self, item_id):
        raw = self.item_prop(item_id, 'ispe')
        if raw is None:
            return None
        w = int.from_bytes(raw[4:8], 'big')
        h = int.from_bytes(raw[8:12], 'big')
        return w, h

    def decode_hvc1_item(self, item_id, tmpdir):
        hvcc = self.item_prop(item_id, 'hvcC')
        if hvcc is None:
            raise ValueError(f'item {item_id}: no hvcC')
        extents = self.ilocs.get(item_id)
        if not extents:
            raise ValueError(f'item {item_id}: no iloc extents')
        coded = b''.join(self.data[off:off+ln] for off, ln in extents)
        annexb = bytearray()
        for nal in nal_units_from_hvcc(hvcc):
            annexb += b'\x00\x00\x00\x01' + nal
        annexb += length_prefixed_to_annexb(coded, length_size=4)
        raw_path = os.path.join(tmpdir, f'item{item_id}.hevc')
        out_path = os.path.join(tmpdir, f'item{item_id}.png')
        with open(raw_path, 'wb') as f:
            f.write(annexb)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'hevc', '-i', raw_path, out_path],
                        check=True)
        return Image.open(out_path).convert('RGB')

    def parse_grid_box(self, item_id):
        extents = self.ilocs[item_id]
        raw = b''.join(self.data[off:off+ln] for off, ln in extents)
        flags = raw[1]
        field_len = 4 if (flags & 1) else 2
        rows = raw[2] + 1
        cols = raw[3] + 1
        p = 4
        out_w = int.from_bytes(raw[p:p+field_len], 'big'); p += field_len
        out_h = int.from_bytes(raw[p:p+field_len], 'big'); p += field_len
        return rows, cols, out_w, out_h

    def item_rotation(self, item_id):
        raw = self.item_prop(item_id, 'irot')
        if raw is None:
            return 0
        return (raw[0] & 0x3) * 90

    def decode_primary(self, tmpdir):
        pid = self.primary_id
        rot = self.item_rotation(pid)
        img = self._decode_primary_unrotated(pid, tmpdir)
        if rot:
            # irot angle is counterclockwise; PIL rotate() is also counterclockwise
            img = img.rotate(rot, expand=True)
        return img

    def _decode_primary_unrotated(self, pid, tmpdir):
        ptype = self.items.get(pid)
        if ptype == 'grid':
            rows, cols, out_w, out_h = self.parse_grid_box(pid)
            tile_ids = self.iref.get('dimg', {}).get(pid)
            if not tile_ids:
                raise ValueError('grid item has no dimg tile references')
            if len(tile_ids) != rows * cols:
                raise ValueError(f'tile count {len(tile_ids)} != rows*cols {rows*cols}')
            tw, th = self.item_ispe(tile_ids[0])
            canvas = Image.new('RGB', (cols * tw, rows * th))
            for i, tid in enumerate(tile_ids):
                r, c = divmod(i, cols)
                tile_img = self.decode_hvc1_item(tid, tmpdir)
                canvas.paste(tile_img, (c * tw, r * th))
            return canvas.crop((0, 0, out_w, out_h))
        elif ptype == 'hvc1':
            return self.decode_hvc1_item(pid, tmpdir)
        else:
            raise ValueError(f'unsupported primary item type: {ptype}')

def convert(src, dst, quality=88, max_dim=1600):
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = HeicDoc(src)
        img = doc.decode_primary(tmpdir)
        if max_dim:
            img.thumbnail((max_dim, max_dim))
        img.save(dst, quality=quality)

if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
    print('OK', sys.argv[2])

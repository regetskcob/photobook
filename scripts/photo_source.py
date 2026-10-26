"""Reading photos straight out of camera-export zips or plain folders.

Shared by build_index.py and make_manifest.py. Archives stay zipped: with
1000+ photos at several hundred MB per archive, extracting everything up
front is wasted time and disk. A photo is addressed by (zip, entry) - or by
(None, path) for a loose file in a folder.
"""
import io
import os
import sys
import tempfile
import zipfile

from PIL import Image

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.tif', '.tiff'}
HEIC_EXTS = {'.heic', '.heif'}

try:  # optional, decodes most HEIC files directly
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAVE_PILLOW_HEIF = True
except ImportError:
    HAVE_PILLOW_HEIF = False


def iter_sources(paths):
    """Yield (zip_path or None, entry_or_file_path, size_bytes) for every
    image in the given zip files and folders, in a stable order."""
    for src in paths:
        if os.path.isdir(src):
            for base, _, files in sorted(os.walk(src)):
                for name in sorted(files):
                    if name.startswith('.') or os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
                        continue
                    path = os.path.join(base, name)
                    yield None, path, os.path.getsize(path)
        elif zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                for info in sorted(z.infolist(), key=lambda i: i.filename):
                    name = os.path.basename(info.filename)
                    if info.is_dir() or name.startswith('.') or '__MACOSX' in info.filename:
                        continue
                    if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                        yield src, info.filename, info.file_size
        else:
            print(f"skipping {src}: neither a folder nor a zip file", file=sys.stderr)


def read_bytes(zip_path, entry):
    if zip_path is None:
        with open(entry, 'rb') as f:
            return f.read()
    with zipfile.ZipFile(zip_path) as z:
        return z.read(entry)


def open_image(zip_path, entry):
    """Return a PIL image. HEIC goes through pillow-heif when installed, else
    through heic_extract.py (needs ffmpeg) - the standard decoder path
    rejects grid-type HEIC files from many iPhones."""
    data = read_bytes(zip_path, entry)
    ext = os.path.splitext(entry)[1].lower()
    if ext in HEIC_EXTS and not HAVE_PILLOW_HEIF:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import heic_extract
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'in' + ext)
            with open(src, 'wb') as f:
                f.write(data)
            with tempfile.TemporaryDirectory() as dec_tmp:
                im = heic_extract.HeicDoc(src).decode_primary(dec_tmp)
                im.load()
                return im
    im = Image.open(io.BytesIO(data))
    im.load()
    return im

"""From raw zip archive to print PDF: index, manifest, renumber, plan, build.

    python -m unittest discover tests
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from photobook.book import Book, BookError  # noqa: E402
from photobook.layout import plan  # noqa: E402


def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.project = os.path.join(cls.tmp, "trip")
        os.makedirs(os.path.join(cls.project, "raw"))
        t0 = datetime(2026, 5, 15, 9, 0)
        with zipfile.ZipFile(os.path.join(cls.project, "raw", "cam.zip"), "w") as z:
            for i in range(30):
                im = Image.new("RGB", (1200, 900), (40 + i * 6, 90, 150))
                exif = im.getexif()
                exif.get_ifd(0x8769)[36867] = (t0 + timedelta(hours=i * 3)).strftime("%Y:%m:%d %H:%M:%S")
                if i == 4:
                    exif[0x0112] = 6  # stored sideways, tagged "rotate 90"
                if i == 7:
                    exif[305] = "Photomator 3.4.14"  # an edited export
                buf = io.BytesIO()
                im.save(buf, "JPEG", exif=exif)
                z.writestr(f"cam/IMG_{i:04d}.JPG", buf.getvalue())
        run("scripts/build_index.py", cls.project, os.path.join(cls.project, "raw", "cam.zip"))
        run("scripts/make_manifest.py", cls.project, "--all")
        cls.book_path = os.path.join(cls.project, "book.json")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def load(self, name):
        with open(os.path.join(self.project, name)) as f:
            return json.load(f)

    def test_index_reads_time_and_orientation(self):
        recs = self.load("recs_sorted.json")
        self.assertEqual(len(recs), 30)
        self.assertEqual(recs[0]["datetime"], "2026-05-15T09:00:00")
        rotated = next(r for r in recs if r["entry"].endswith("IMG_0004.JPG"))
        self.assertEqual((rotated["width"], rotated["height"]), (900, 1200))

    def test_index_flags_edited_exports(self):
        recs = self.load("recs_sorted.json")
        edited = [r["entry"] for r in recs if r["edited"]]
        self.assertEqual(edited, ["cam/IMG_0007.JPG"])

    def test_suggest_selection_picks_and_protects_existing_file(self):
        project = os.path.join(self.tmp, "suggest")
        os.makedirs(project)
        shutil.copy(os.path.join(self.project, "recs_sorted.json"), project)
        shutil.copytree(os.path.join(self.project, "thumbs"), os.path.join(project, "thumbs"))
        run("scripts/suggest_selection.py", project, "--count", "12", "--min-long-side", "0")
        with open(os.path.join(project, "selection.txt")) as f:
            picked = [line for line in f if line[:1].isdigit()]
        self.assertTrue(8 <= len(picked) <= 12, len(picked))
        # an existing selection may hold the user's own choices
        result = subprocess.run([sys.executable, "scripts/suggest_selection.py", project], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_gps_report_runs(self):
        index = self.load("recs_sorted.json")
        index[0]["gps"] = [48.14, 11.58]
        index[1]["gps"] = [48.15, 11.59]
        path = os.path.join(self.project, "gps_variant.json")
        with open(path, "w") as f:
            json.dump(index, f)
        out = subprocess.run([sys.executable, "scripts/gps_report.py", path, "--gap-minutes", "240"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout
        self.assertIn("2 of 30 photos have GPS data", out)
        self.assertIn("(2 photos)", out)

    def test_manifest_groups_days_and_writes_upright_files(self):
        manifest = self.load("final_manifest.json")
        self.assertEqual([m["order"] for m in manifest], list(range(1, 31)))
        # 3-hourly photos from 09:00; a day starts at 04:00
        self.assertEqual(len({m["day"] for m in manifest}), 4)
        photo_map = self.load("fullres_idx_map.json")
        rotated = next(m for m in manifest if m["entry"].endswith("IMG_0004.JPG"))
        with Image.open(os.path.join(self.project, photo_map[str(rotated["idx"])])) as im:
            self.assertEqual(im.size, (900, 1200))

    def test_skeleton_plans_and_builds(self):
        book = Book(self.book_path)
        pages = plan(book)
        self.assertEqual(len(pages), book.page_count)
        out = os.path.join(self.tmp, "out")
        run("-m", "photobook", "build", self.book_path, "--mode", "print", "--dpi", "40", "--out", out)
        self.assertTrue(os.path.exists(os.path.join(out, "book_pages_print.pdf")))

    def test_renumber_closes_gaps_and_overlaps(self):
        path = os.path.join(self.project, "final_manifest.json")
        backup = self.load("final_manifest.json")
        try:
            broken = [dict(m, order=m["order"] * 2) for m in backup]
            broken[1]["order"] = broken[0]["order"]  # duplicate
            with open(path, "w") as f:
                json.dump(broken, f)
            with self.assertRaisesRegex(BookError, "used by several photos"):
                Book(self.book_path)
            run("-m", "photobook", "renumber", self.book_path)
            self.assertEqual(sorted(m["order"] for m in self.load("final_manifest.json")), list(range(1, 31)))
            Book(self.book_path)
        finally:
            with open(path, "w") as f:
                json.dump(backup, f)

    def test_closing_photo_cannot_also_open_a_chapter(self):
        data = self.load("book.json")
        data["closing"]["photo"] = data["days"][0]["opener"]
        path = os.path.join(self.project, "variant.json")
        with open(path, "w") as f:
            json.dump(data, f)
        with self.assertRaisesRegex(BookError, "also the closing photo"):
            Book(path)

    def test_chapters_alias_and_no_date(self):
        data = self.load("book.json")
        data["chapters"] = data.pop("days")
        data["chapters"][0]["date"] = ""
        path = os.path.join(self.project, "variant.json")
        with open(path, "w") as f:
            json.dump(data, f)
        self.assertEqual(len(plan(Book(path))), data["pages"])


if __name__ == "__main__":
    unittest.main()

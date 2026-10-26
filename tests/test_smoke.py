"""Smoke test: the demo book plans, validates and renders.

    python -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pypdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from photobook.book import Book, BookError  # noqa: E402
from photobook.layout import LayoutError, plan, unplaced_photos  # noqa: E402

DEMO = os.path.join(ROOT, "examples", "demo")


class DemoBookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.demo = os.path.join(cls.tmp, "demo")
        shutil.copytree(DEMO, cls.demo, ignore=shutil.ignore_patterns("photos", "build", "final_manifest.json"))
        subprocess.run([sys.executable, os.path.join(cls.demo, "make_demo_photos.py")], check=True, stdout=subprocess.DEVNULL)
        cls.book_path = os.path.join(cls.demo, "book.json")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _variant(self, change):
        with open(self.book_path) as f:
            data = json.load(f)
        change(data)
        path = os.path.join(self.demo, "variant.json")
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_plan_hits_page_count_and_places_every_photo(self):
        book = Book(self.book_path)
        pages = plan(book)
        self.assertEqual(len(pages), book.page_count)
        self.assertEqual(unplaced_photos(book, pages), [])

    def test_stale_day_reference_fails_loudly(self):
        def change(d):
            d["days"][0]["groups"][0]["photos"][0] = 999
        with self.assertRaisesRegex(BookError, "idx 999 is not a photo of this day"):
            Book(self._variant(change))

    def test_stale_photo_option_warns(self):
        def change(d):
            d["photos"]["999"] = {"caption": "gone"}
        book = Book(self._variant(change))
        self.assertTrue(any("photos.999" in w for w in book.warnings))

    def test_wrong_page_count_fails(self):
        def change(d):
            d["pages"] += 2
        with self.assertRaisesRegex(LayoutError, "expected"):
            plan(Book(self._variant(change)))

    def test_build_print_sets_trim_and_bleed_boxes(self):
        out = os.path.join(self.tmp, "out")
        subprocess.run([sys.executable, "-m", "photobook", "build", self.book_path, "--mode", "print",
                        "--dpi", "40", "--out", out], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        book = Book(self.book_path)
        pages = pypdf.PdfReader(os.path.join(out, "Demo_pages_print.pdf")).pages
        self.assertEqual(len(pages), book.page_count // 2)
        self.assertEqual([round(float(v), 3) for v in pages[0].trimbox],
                         [round(v, 3) for v in book.profile.pages_trim])
        cover = pypdf.PdfReader(os.path.join(out, "Demo_cover_print.pdf")).pages[0]
        self.assertEqual([round(float(v), 3) for v in cover.trimbox],
                         [round(v, 3) for v in book.profile.cover_trim])


if __name__ == "__main__":
    unittest.main()

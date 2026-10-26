"""Page-planning rules that don't need photos.

    python -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from photobook.layout import LayoutError, fix_parity  # noqa: E402


def grid(*idxs):
    return ('grid', [{'idx': i} for i in idxs])


def sizes(units):
    return [len(u[1]) for u in units]


class ParityTest(unittest.TestCase):
    def test_even_day_is_left_alone(self):
        units = [grid(1, 2), grid(3, 4)]
        self.assertIs(fix_parity(units), units)

    def test_layout_1_splits_the_first_page(self):
        # the rule the original book was printed with: two single pages
        units = [grid(1, 2), grid(3, 4, 5, 6), grid(7, 8)]
        self.assertEqual(sizes(fix_parity(units)), [1, 1, 4, 2])

    def test_layout_2_splits_the_fullest_page(self):
        units = [grid(1, 2), grid(3, 4, 5, 6), grid(7, 8)]
        self.assertEqual(sizes(fix_parity(units, largest=True)), [2, 2, 2, 2])

    def test_no_photo_is_lost_or_doubled(self):
        units = [grid(1, 2, 3), grid(4, 5)]
        out = fix_parity(units, largest=True)
        self.assertEqual(sorted(m['idx'] for u in out for m in u[1]), [1, 2, 3, 4, 5])

    def test_hand_placed_groups_are_never_split(self):
        units = [('grid', [{'idx': 1}, {'idx': 2}, {'idx': 3}], {'style': 'manual3'})]
        with self.assertRaises(LayoutError):
            fix_parity(units, "day x", largest=True)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The maths of SciForge's hole-centre snaps (sciforge/hole_snaps_core.py): outline centres,
X of a hole, which dot the pointer takes, finding a hole again after an edit."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import hole_snaps_core as core  # noqa: E402

Z = (0.0, 0.0, 1.0)


def close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Centroids(unittest.TestCase):
    def test_square(self):
        pts = [(0, 0, 2), (4, 0, 2), (4, 4, 2), (0, 4, 2)]
        c, area = core.polygon_centroid(pts, Z)
        self.assertTrue(close(c, (2, 2, 2)))
        self.assertAlmostEqual(area, 16.0)

    def test_clockwise_and_l_shape(self):
        # an L: 2x2 square plus a 2x1 bar; the centre of area is not the corners' average
        pts = [(0, 0, 0), (0, 2, 0), (1, 2, 0), (1, 1, 0), (2, 1, 0), (2, 0, 0)]  # clockwise
        c, area = core.polygon_centroid(pts, Z)
        self.assertAlmostEqual(area, 3.0)
        # unit squares at (0.5,0.5), (0.5,1.5), (1.5,0.5)
        self.assertTrue(close(c, (2.5 / 3, 2.5 / 3, 0)))

    def test_tilted_plane(self):
        n = core.unit((0.0, 1.0, 1.0))
        pts = [(0, 0, 0), (2, 0, 0), (2, -1, 1), (0, -1, 1)]
        c, area = core.polygon_centroid(pts, n)
        self.assertTrue(close(c, (1.0, -0.5, 0.5)))
        self.assertAlmostEqual(area, 2.0 * math.sqrt(2.0))

    def test_rounded_square(self):
        side, r = 8.0, 1.5
        h = side / 2.0
        pts, arcs = [], {}
        # corners of the straight sides, counter-clockwise, each corner rounded
        centres = [(h - r, -h + r), (h - r, h - r), (-h + r, h - r), (-h + r, -h + r)]
        starts = [-90, 0, 90, 180]
        for (cx, cy), a0 in zip(centres, starts):
            p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)), 0)
            p1 = (
                cx + r * math.cos(math.radians(a0 + 90)),
                cy + r * math.sin(math.radians(a0 + 90)),
                0,
            )
            mid = (
                cx + r * math.cos(math.radians(a0 + 45)),
                cy + r * math.sin(math.radians(a0 + 45)),
                0,
            )
            arcs[len(pts)] = ((cx, cy, 0), r, math.pi / 2, mid)
            pts += [p0, p1]
        c, area = core.outline_centroid(pts, arcs, Z)
        self.assertTrue(close(c, (0, 0, 0), 1e-9))
        self.assertAlmostEqual(area, side * side - (4 - math.pi) * r * r, places=9)

    def test_slot_and_bulging_in(self):
        # a slot: 10 long between its arc centres, radius 5
        pts = [(0, -5, 0), (10, -5, 0), (10, 5, 0), (0, 5, 0)]
        arcs = {
            1: ((10, 0, 0), 5.0, math.pi, (15, 0, 0)),
            3: ((0, 0, 0), 5.0, math.pi, (-5, 0, 0)),
        }
        c, area = core.outline_centroid(pts, arcs, Z)
        self.assertTrue(close(c, (5, 0, 0)))
        self.assertAlmostEqual(area, 100 + math.pi * 25)
        # a D bitten on one side: the half disc goes inward
        arcs = {1: ((10, 0, 0), 5.0, math.pi, (5, 0, 0))}
        c, area = core.outline_centroid(pts, arcs, Z)
        self.assertAlmostEqual(area, 100 - math.pi * 25 / 2)
        self.assertLess(c[0], 5.0)

    def test_circumradius(self):
        self.assertAlmostEqual(core.circumradius((0, 0, 0), [(3, 4, 0), (1, 0, 0)]), 5.0)


class XDirection(unittest.TestCase):
    def test_longest_side(self):
        sides = [((0, 0, 0), (6, 0, 0)), ((6, 0, 0), (6, 2, 0))]
        self.assertTrue(close(core.x_direction(sides), (1, 0, 0)))

    def test_ties_follow_the_hint(self):
        square = [((0, 0, 0), (2, 0, 0)), ((2, 0, 0), (2, 2, 0)), ((2, 2, 0), (0, 2, 0))]
        self.assertTrue(close(core.x_direction(square, hint=(0, -1, 0)), (0, -1, 0)))
        self.assertTrue(close(core.x_direction(square, hint=(-1, 0, 0)), (-1, 0, 0)))

    def test_no_straight_side(self):
        self.assertIsNone(core.x_direction([]))


class ChooseHot(unittest.TestCase):
    def test_hole_zone_wins_over_far_dots(self):
        rows = [((0, 0), None), ((100, 100), None), ((50, 50), 20.0)]
        self.assertEqual(core.choose_hot(rows, (60, 58)), 2)

    def test_dot_right_under_the_pointer_wins(self):
        rows = [((0, 0), None), ((62, 60), None), ((50, 50), 20.0)]
        self.assertEqual(core.choose_hot(rows, (61, 60)), 1)

    def test_hole_centre_closer_than_the_dot(self):
        rows = [((56, 50), None), ((50, 50), 20.0)]
        self.assertEqual(core.choose_hot(rows, (51, 50)), 1)

    def test_outside_every_zone_nearest_within_reach(self):
        rows = [((0, 0), None), ((100, 0), None), ((50, 50), 5.0)]
        self.assertEqual(core.choose_hot(rows, (90, 2)), 1)
        self.assertIsNone(core.choose_hot(rows, (75, 0), reach=10))

    def test_deepest_zone(self):
        rows = [((0, 0), 30.0), ((40, 0), 30.0)]
        self.assertEqual(core.choose_hot(rows, (25, 0)), 1)

    def test_zone_pixels(self):
        self.assertEqual(core.zone_pixels(1.0), core.MIN_ZONE_PIXELS)
        self.assertAlmostEqual(core.zone_pixels(20.0), 20.0 * core.ZONE)


class FindAgain(unittest.TestCase):
    stored = {"c": [10, 0, 2], "n": [0, 0, 1], "a": 21.3, "r": 3.27}

    def test_same(self):
        self.assertTrue(core.same_loop(self.stored, {"c": (10, 0, 2), "n": (0, 0, 1), "a": 21.3}))
        self.assertFalse(core.same_loop(self.stored, {"c": (10, 0, 2), "n": (0, 0, -1), "a": 21.3}))
        self.assertFalse(core.same_loop(self.stored, {"c": (10, 1, 2), "n": (0, 0, 1), "a": 21.3}))
        self.assertFalse(core.same_loop(self.stored, {"c": (10, 0, 2), "n": (0, 0, 1), "a": 30.0}))

    def test_best(self):
        loops = [
            {"c": (22.7, 0, 2), "n": (0, 0, 1), "a": 21.3},  # the next hole
            {"c": (10.2, 0, 2), "n": (0, 0, 1), "a": 21.3},  # this one, moved a little
            {"c": (10, 0, 0), "n": (0, 0, -1), "a": 21.3},  # its other end
            {"c": (10, 0, 2), "n": (0, 0, 1), "a": 50.0},  # a bigger hole in its place
        ]
        self.assertEqual(core.best_loop(self.stored, loops), 1)

    def test_gone(self):
        loops = [{"c": (22.7, 0, 2), "n": (0, 0, 1), "a": 21.3}]
        self.assertIsNone(core.best_loop(self.stored, loops))


class ManyDots(unittest.TestCase):
    def test_dedupe(self):
        pts = [(0, 0, 0), (1e-9, 0, 0), (1, 0, 0), (1, 5e-8, 0), (2, 0, 0)]
        self.assertEqual(core.dedupe_points(pts, 1e-7), [0, 2, 4])

    def test_dedupe_thousands_quickly(self):
        import time

        pts = [(i * 0.5, j * 0.5, 0.0) for i in range(80) for j in range(40)] * 2
        t0 = time.perf_counter()
        kept = core.dedupe_points(pts, 1e-7)
        self.assertEqual(len(kept), 3200)
        self.assertLess(time.perf_counter() - t0, 2.0)

    def test_nearest(self):
        pts = [(5, 0, 0), (1, 0, 0), (3, 0, 0)]
        self.assertEqual(core.nearest_indices(pts, (0, 0, 0), 2), [1, 2])


if __name__ == "__main__":
    unittest.main()

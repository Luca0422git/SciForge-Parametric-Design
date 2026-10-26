# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's rules (sciforge/simulation_results_core.py). Runs without FreeCAD; the mesh
tests need numpy (FreeCAD and the CI's Python have it)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import simulation_core as sim  # noqa: E402
from sciforge import simulation_results_core as core  # noqa: E402

try:
    import numpy  # noqa: F401

    HAVE_NUMPY = True
except ImportError:  # (FreeCAD and the CI's Python have numpy)
    HAVE_NUMPY = False


class ResultListTests(unittest.TestCase):
    def test_every_engine_result_is_listed(self):
        engine = [k for k, _t, _u in sim.RESULTS]
        extra = [k for k, _n in core.EXTRA_RESULTS]
        self.assertEqual(sorted(core.result_keys()), sorted(engine + extra))
        self.assertEqual(core.result_name("strain_1"), "Strain: 1st Principal")
        self.assertEqual(core.result_name("von_mises"), "Stress: Von Mises")

    @unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
    def test_principal_values(self):
        import numpy as np

        big, small = core.principal(
            np.array([1.0, 2.0]),
            np.array([0.0, 2.0]),
            np.array([0.0, 2.0]),
            np.array([0.0, 1.0]),
            np.array([0.0, 0.0]),
            np.array([0.0, 0.0]),
        )
        self.assertAlmostEqual(big[0], 1.0)
        self.assertAlmostEqual(small[0], 0.0)
        self.assertAlmostEqual(big[1], 3.0)  # [[2,1,0],[1,2,0],[0,0,2]]: 3, 2, 1
        self.assertAlmostEqual(small[1], 1.0)

    def test_groups_follow_fusion(self):
        self.assertEqual(
            [name for _k, name in core.groups()],
            ["Safety Factor", "Stress", "Displacement", "Strain"],
        )
        self.assertEqual(core.group_of("von_mises"), "stress")
        self.assertEqual(core.group_of("dz"), "displacement")
        self.assertEqual(core.components("displacement")[0], ("displacement", "Total"))
        self.assertEqual(core.DEFAULT_RESULT, "safety")

    def test_units(self):
        self.assertEqual(core.units_for("safety"), [""])
        self.assertEqual(core.units_for("sxx")[0], "MPa")
        self.assertEqual(core.units_for("dx")[0], "mm")
        self.assertAlmostEqual(core.convert(1.0, "psi"), 145.0377, places=3)
        self.assertAlmostEqual(core.convert(25.4, "in"), 1.0)
        self.assertAlmostEqual(core.convert(2.0, "kPa"), 2000.0)
        self.assertIsNone(core.convert(None, "mm"))
        self.assertEqual(core.with_unit(1.23456, "mm"), "1.235 mm")
        self.assertEqual(core.fmt(float("nan")), "-")
        self.assertEqual(core.fmt_plain(200000.0), "200000")
        self.assertEqual(core.fmt_plain(0.3), "0.3")
        self.assertEqual(core.fmt_plain(7850), "7850")
        self.assertEqual(core.fmt_plain(0.0012346), "0.001235")
        self.assertEqual(core.fmt_plain(None), "-")


class LegendTests(unittest.TestCase):
    def test_safety_factor_scale_is_capped(self):
        leg = core.legend("safety", {"min": 3.5, "max": 15.0})
        self.assertEqual((leg["lo"], leg["hi"], leg["reverse"]), (0.0, sim.SAFETY_CAP, True))
        self.assertEqual(len(leg["ticks"]), 11)  # every 1.5
        self.assertEqual(leg["ticks"][0][1], "15")
        self.assertEqual(leg["ticks"][1][1], "13.5")
        self.assertEqual(leg["ticks"][-1][1], "0")
        self.assertEqual(leg["min_text"], "3.5")
        self.assertEqual(leg["unit"], "")
        self.assertEqual(leg["title"], "Safety Factor")

    def test_stress_legend_in_psi(self):
        leg = core.legend("von_mises", {"min": 1.0, "max": 59.17}, unit="psi")
        self.assertEqual(leg["unit"], "psi")
        self.assertAlmostEqual(leg["max"], 59.17 * 145.0377377, places=2)
        self.assertEqual(leg["ticks"][0][2], 1.0)
        self.assertEqual(leg["ticks"][-1][2], 0.0)
        self.assertFalse(leg["reverse"])
        # a unit the result does not have falls back to the base unit
        self.assertEqual(core.legend("von_mises", {"min": 0, "max": 1}, unit="in")["unit"], "MPa")

    def test_legend_min_max(self):
        leg = core.legend("von_mises", {"min": 1.0, "max": 59.0}, span=(0.0, 40.0))
        self.assertTrue(leg["custom"])
        self.assertEqual((leg["lo"], leg["hi"]), (0.0, 40.0))
        self.assertEqual(leg["ticks"][0][1], "40")
        self.assertEqual(leg["max_text"], "59 MPa")  # the result's own max still shown
        self.assertIn("0 MPa to 40 MPa", leg["span_text"])
        # never for the safety factor (Fusion offers no legend range for it)
        sf = core.legend("safety", {"min": 2.0, "max": 15.0}, span=(0.0, 4.0))
        self.assertFalse(sf["custom"])
        self.assertEqual(sf["hi"], sim.SAFETY_CAP)
        # a range given upside down is turned round; an empty one is ignored
        self.assertEqual(core.span_ok((40, 0)), (0.0, 40.0))
        self.assertEqual(core.span_ok((5, 5), 1, 2), (1, 2))
        self.assertEqual(core.span_ok(None, 1, 2), (1, 2))

    def test_target_bands_in_the_legend(self):
        leg = core.legend("safety", {"min": 2, "max": 15}, targets=(3.0, 6.0))
        self.assertEqual([b[0] for b in leg["bands"]], ["above", "meets", "below"])
        self.assertIsNone(core.legend("von_mises", {"min": 0, "max": 1}, targets=(3, 6))["bands"])


class ColourTests(unittest.TestCase):
    def test_safety_low_is_red_high_is_blue(self):
        lo, hi, rev = core.scale("safety", 3.5, 15.0)
        red = core.map_colour(core.position(0.5, lo, hi, rev))
        blue = core.map_colour(core.position(15.0, lo, hi, rev))
        self.assertGreater(red[0], 0.9)
        self.assertLess(red[2], 0.1)
        self.assertGreater(blue[2], 0.9)
        self.assertLess(blue[0], 0.1)

    def test_no_value_is_grey(self):
        self.assertIsNone(core.position(float("nan"), 0, 1))
        self.assertEqual(core.map_colour(None), core.NO_VALUE)
        self.assertEqual(core.texture_coordinate(None), (0.5, 0.75))
        self.assertEqual(core.texture_coordinate(0.3), (0.3, 0.25))

    def test_bands(self):
        a = core.map_colour(0.01, banded=True)
        b = core.map_colour(0.05, banded=True)
        self.assertEqual(a, b)
        self.assertNotEqual(core.map_colour(0.01), core.map_colour(0.05))

    def test_texture(self):
        data = core.texture_rows()
        self.assertEqual(len(data), core.TEXELS * 3 * 2)
        self.assertEqual(data[0:3], bytes([0, 2, 255]))  # blue at the left
        right = data[(core.TEXELS - 1) * 3 : core.TEXELS * 3]
        self.assertGreater(right[0], 250)
        self.assertLess(right[2], 5)
        banded = core.texture_rows(targets=(3.0, 6.0))
        self.assertEqual(len(banded), len(data))
        # position 0 (value 15, above the upper target) is the "above" colour
        self.assertEqual(
            tuple(banded[0:3]), tuple(int(round(255 * c)) for c in core.BAND_COLOURS["above"])
        )


class TargetTests(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(core.target_band(1.0, 3, 6), "below")
        self.assertEqual(core.target_band(4.0, 3, 6), "meets")
        self.assertEqual(core.target_band(7.0, 3, 6), "above")
        self.assertIsNone(core.target_band(None, 3, 6))

    def test_targets_are_kept_sane(self):
        self.assertEqual(core.targets(), core.DEFAULT_TARGETS)
        self.assertEqual(core.targets(5, 2), (5.0, 5.0))
        self.assertEqual(core.targets(-1, 99), (0.01, sim.SAFETY_CAP))

    def test_short_verdicts(self):
        self.assertEqual(core.short_verdict(0.5, 3, 6)[1], "Lowest 0.5: below 1, the part yields")
        self.assertEqual(core.short_verdict(2.0, 3, 6), ("below", "Lowest 2: below the target 3"))
        self.assertEqual(core.short_verdict(4.0, 3, 6)[0], "meets")
        self.assertEqual(core.short_verdict(9.0, 3, 6)[0], "above")
        self.assertEqual(core.short_verdict(None, 3, 6)[0], "none")

    def test_verdicts(self):
        state, head, advice = core.verdict(0.8, 3, 6)
        self.assertEqual(state, "below")
        self.assertIn("yields", head)
        state, head, advice = core.verdict(2.0, 3, 6)
        self.assertEqual(state, "below")
        self.assertIn("does not yield", advice[0])
        self.assertEqual(core.verdict(4.0, 3, 6)[0], "meets")
        self.assertEqual(core.verdict(9.0, 3, 6)[0], "above")
        self.assertEqual(core.verdict(None, 3, 6)[0], "none")
        self.assertEqual(core.verdict(float("nan"), 3, 6)[0], "none")


class CompareTests(unittest.TestCase):
    def test_offsets_put_models_side_by_side(self):
        boxes = [(0, 0, 0, 100, 10, 10), (0, 0, 0, 100, 10, 10), (-10, 0, 0, 40, 10, 10)]
        shifts = core.compare_offsets(boxes)
        self.assertEqual(shifts[0], 0.0)
        self.assertAlmostEqual(shifts[1], 125.0)  # 100 + a quarter of the widest (100)
        self.assertAlmostEqual(shifts[2] + boxes[2][0], 250.0)  # starts after the second + gap
        self.assertEqual(core.compare_offsets([]), [])

    def test_shared_scale(self):
        both = core.combined_stats([{"min": 1, "max": 5}, {"min": 0.5, "max": 3}, None])
        self.assertEqual(both, {"min": 0.5, "max": 5})
        self.assertEqual(core.combined_stats([]), {"min": None, "max": None})


class AnimationTests(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(core.animation_fraction(0, 5, "once"), 0.0)
        self.assertEqual(core.animation_fraction(4, 5, "once"), 1.0)
        self.assertEqual(core.animation_fraction(9, 5, "once"), 1.0)
        self.assertTrue(core.animation_done(4, 5, "once"))
        self.assertFalse(core.animation_done(4, 5, "loop"))
        self.assertEqual(core.animation_fraction(5, 5, "loop"), 0.0)
        self.assertEqual(core.animation_fraction(6, 5, "mirror"), 0.5)
        self.assertEqual(core.animation_fraction(8, 5, "mirror"), 0.0)

    def test_speed(self):
        slow = core.animation_interval_ms(0.25, 20)
        fast = core.animation_interval_ms(2.0, 20)
        self.assertGreater(slow, fast)
        self.assertGreaterEqual(fast, 15)

    def test_deformations(self):
        self.assertEqual(core.deformations()[0], ("undeformed", "Undeformed"))
        self.assertEqual(core.DEFORMATION_DEFAULT, "adjusted")
        # Adjusted draws the largest displacement at 5 % of the model size
        self.assertAlmostEqual(core.deformation_factor("adjusted", 0.2, 100.0) * 0.2, 5.0)
        self.assertEqual(core.deformation_factor("actual", 0.2, 100.0), 1.0)


def _cube():
    """A unit cube as 5 straight tetrahedra."""
    pts = [
        (0, 0, 0),
        (1, 0, 0),
        (1, 1, 0),
        (0, 1, 0),
        (0, 0, 1),
        (1, 0, 1),
        (1, 1, 1),
        (0, 1, 1),
    ]
    tets = [(0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6)]
    return pts, tets


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class MeshTests(unittest.TestCase):
    def _signed_volume(self, pts, tris):
        import numpy as np

        p = np.asarray(pts, dtype=float)
        a, b, c = p[tris[:, 0]], p[tris[:, 1]], p[tris[:, 2]]
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    def test_cube_surface_faces_out(self):
        import numpy as np

        pts, tets = _cube()
        surf = core.surface(pts, tets)
        self.assertEqual(len(surf["triangles"]), 12)  # 6 squares, 2 triangles each
        self.assertEqual(sorted(surf["nodes"].tolist()), list(range(8)))
        sub = np.asarray(pts, dtype=float)[surf["nodes"]]
        self.assertAlmostEqual(self._signed_volume(sub, surf["triangles"]), 1.0)
        # 12 cube edges + 6 face diagonals; the 12 cube edges are the sharp ones
        self.assertEqual(len(surf["lines"]), 18)
        self.assertEqual(len(surf["features"]), 12)

    def test_quadratic_tet(self):
        import numpy as np

        corners = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        pts = list(corners)
        for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
            pts.append(tuple((corners[a][k] + corners[b][k]) / 2.0 for k in range(3)))
        surf = core.surface(pts, [list(range(10))])
        self.assertEqual(len(surf["triangles"]), 16)
        self.assertEqual(len(surf["nodes"]), 10)
        sub = np.asarray(pts, dtype=float)[surf["nodes"]]
        self.assertAlmostEqual(self._signed_volume(sub, surf["triangles"]), 1.0 / 6.0)
        self.assertEqual(surf["lines"].shape, (6, 3))
        # every polyline's middle node lies halfway along it
        for i, m, j in surf["lines"]:
            mid = (sub[i] + sub[j]) / 2.0
            self.assertTrue(np.allclose(mid, sub[m]))

    def test_ray(self):
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        hit = core.ray_hit((0.2, 0.2, 5), (0, 0, -1), verts, [(0, 1, 2)])
        self.assertAlmostEqual(hit[0], 5.0)
        self.assertEqual(hit[1], 0)
        self.assertAlmostEqual(sum(hit[2]), 1.0)
        self.assertIsNone(core.ray_hit((2, 2, 5), (0, 0, -1), verts, [(0, 1, 2)]))
        self.assertIsNone(core.ray_hit((0.2, 0.2, 5), (0, 0, 1), verts, [(0, 1, 2)]))

    def test_nearest(self):
        pts = [(0, 0, 0), (10, 0, 0), (0, 10, 0)]
        self.assertEqual(core.nearest(pts, (9, 1, 0)), 1)
        self.assertEqual(core.nearest(pts, (9, 1, 0), candidates=[0, 2]), 0)

    def test_cut_cube(self):
        pts, tets = _cube()
        values = [p[0] for p in pts]  # value = x
        tris, vals = core.cut(pts, values, core.straight_tets(tets), (0.5, 0.5, 0.5), (1, 0, 0))
        import numpy as np

        area = 0.0
        for a, b, c in tris:
            area += 0.5 * np.linalg.norm(np.cross(np.subtract(b, a), np.subtract(c, a)))
            for p in (a, b, c):
                self.assertAlmostEqual(p[0], 0.5)
        self.assertAlmostEqual(area, 1.0)
        for a, b, c in tris:  # each faces against the normal (+X)
            self.assertLess(np.dot(np.cross(np.subtract(b, a), np.subtract(c, a)), (1, 0, 0)), 0)
        for v in vals:
            for x in v:
                self.assertAlmostEqual(x, 0.5)

    def test_split10(self):
        import numpy as np

        corners = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        pts = list(corners)
        for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
            pts.append(tuple((corners[a][k] + corners[b][k]) / 2.0 for k in range(3)))
        pieces = core.straight_tets([list(range(10))])
        self.assertEqual(pieces.shape, (8, 4))
        p = np.asarray(pts, dtype=float)
        total = 0.0
        for t in pieces:
            a, b, c, d = p[t]
            total += abs(np.dot(b - a, np.cross(c - a, d - a))) / 6.0
        self.assertAlmostEqual(total, 1.0 / 6.0)


class ReportTests(unittest.TestCase):
    def test_report_has_the_numbers(self):
        text = core.report_html(
            {
                "title": "Bracket <check>",
                "design": "Bracket",
                "study": "Study 1 - Static Stress",
                "settings": [("Average element size", "10 %")],
                "materials": [("Body", "Steel", 210000, 0.3, 7850, 207, 345, "Yield strength")],
                "constraints": [("Fixed 1", "Fixed", "Body: Face1", "")],
                "loads": [("Force 1", "Force", "Body: Face2", "100 N")],
                "mesh": [("Nodes", 451)],
                "results": [("von_mises", 0.62, 59.17, "MPa"), ("safety", 3.499, 15.0, "")],
                "bodies": [("Body", "Steel", 207, 59.17, 3.499, 0.1995)],
                "verdict": core.verdict(3.499, 3, 6),
                "out_of_date": True,
                "images": [("Safety Factor", "data:image/png;base64,AAAA")],
            }
        )
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("Bracket &lt;check&gt;", text)
        self.assertIn("59.17", text)
        self.assertIn("3.499", text)
        self.assertIn("Stress: Von Mises", text)
        self.assertIn("out of date", text)
        self.assertIn("data:image/png;base64,AAAA", text)
        self.assertIn("Meets the safety factor target", text)

    def test_empty_report(self):
        text = core.report_html({})
        self.assertIn("Static Stress report", text)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's rules (sciforge/simulation_results_core.py). Runs without FreeCAD; the mesh
tests need numpy (FreeCAD and the CI's Python have it)."""

import math
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
    def test_the_design_units_come_first(self):
        self.assertEqual(core.design_unit("displacement", "in"), "in")
        self.assertEqual(core.design_unit("dz", "ft"), "in")
        self.assertEqual(core.design_unit("von_mises", "in"), "psi")
        self.assertEqual(core.design_unit("von_mises", "cm"), "MPa")
        self.assertEqual(core.design_unit("displacement", "cm"), "cm")
        self.assertEqual(core.design_unit("displacement", "m"), "m")
        self.assertEqual(core.design_unit("safety", "in"), "")
        self.assertEqual(core.design_unit("strain", "in"), "")
        self.assertEqual(core.design_unit("displacement", "parsec"), "mm")

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

    def test_dragged_legend_ends(self):
        # the top dragged half way down: the colours end at the middle of the range shown
        self.assertEqual(core.dragged_span(0.0, 200.0, "hi", 0.5), (0.0, 100.0))
        self.assertEqual(core.dragged_span(0.0, 200.0, "lo", 0.25), (50.0, 200.0))
        # dragged past the other end: they stay 1 % of the range apart
        self.assertEqual(core.dragged_span(0.0, 200.0, "hi", -1.0), (0.0, 2.0))
        self.assertEqual(core.dragged_span(0.0, 200.0, "lo", 2.0), (198.0, 200.0))
        self.assertEqual(core.dragged_span(5.0, 5.0, "hi", 0.5), (5.0, 5.0))

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
        # beams long in X lie side by side along Y, 10 mm apart (a tenth of their size)
        self.assertEqual(core.compare_axis(boxes[:2]), 1)
        self.assertEqual(core.compare_offsets(boxes[:2], axis=1), [0.0, 20.0])

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

    def test_saved_cycle(self):
        self.assertEqual(core.animation_cycle(5, "once"), [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertEqual(core.animation_cycle(5, "loop"), [0.0, 0.25, 0.5, 0.75, 1.0])
        # mirror: up and back down, each turning point once (it loops without a stutter)
        self.assertEqual(
            core.animation_cycle(5, "mirror"), [0.0, 0.25, 0.5, 0.75, 1.0, 0.75, 0.5, 0.25]
        )
        self.assertEqual(len(core.animation_cycle(100, "loop")), 100)

    def test_saved_file_name(self):
        self.assertEqual(core.animation_file("/tmp/beam"), "/tmp/beam.gif")
        self.assertEqual(core.animation_file(" /tmp/beam.WEBP "), "/tmp/beam.WEBP")
        self.assertEqual(core.animation_file("/tmp/beam.gif"), "/tmp/beam.gif")

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

    def test_quadratic_faces_drawn_smoothly(self):
        import numpy as np

        corners = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        pts = list(corners)
        for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
            pts.append(tuple((corners[a][k] + corners[b][k]) / 2.0 for k in range(3)))
        surf = core.surface(pts, [list(range(10))])
        self.assertEqual(surf["faces6"].shape, (4, 6))
        sub = np.asarray(pts, dtype=float)[surf["nodes"]]
        tris, nodes, weights = core.refine_quadratic(surf["faces6"], len(sub))
        self.assertEqual(tris.shape, (4 * 16, 3))
        self.assertEqual(len(nodes), 4 * 9)  # 15 grid points a face, 6 of them its nodes
        self.assertTrue(np.allclose(weights.sum(axis=1), 1.0))
        new = np.einsum("vk,vkd->vd", weights, sub[nodes])
        drawn = np.vstack([sub, new])
        # the faces still enclose the tetrahedron (straight sides: its volume) and face out
        self.assertAlmostEqual(self._signed_volume(drawn, tris), 1.0 / 6.0)
        # a quadratic field is followed exactly: z^2 at the new points
        field = sub[:, 2] ** 2
        self.assertTrue(np.allclose(np.einsum("vk,vk->v", weights, field[nodes]), new[:, 2] ** 2))
        self.assertIsNone(core.surface(*_cube())["faces6"])

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
        tris, vals, _rest = core.cut(
            pts, values, core.straight_tets(tets), (0.5, 0.5, 0.5), (1, 0, 0)
        )
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

    def _area(self, tris):
        import numpy as np

        tris = np.asarray(tris, dtype=float)
        if not len(tris):
            return 0.0
        cross = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        return float(0.5 * np.linalg.norm(cross, axis=1).sum())

    def test_cut_carries_the_rest_places(self):
        import numpy as np

        pts, tets = _cube()
        moved = np.asarray(pts, dtype=float) + (0.0, 0.0, 2.0)  # the part drawn moved up
        tris, _vals, rest = core.cut(
            moved, [0.0] * 8, core.straight_tets(tets), (0.25, 0, 0), (1, 0, 0), carry=pts
        )
        self.assertEqual(rest.shape, tris.shape)
        self.assertTrue(np.allclose(rest[:, :, 2] + 2.0, tris[:, :, 2]))
        self.assertTrue(np.allclose(rest[:, :, 0], 0.25))
        self.assertAlmostEqual(self._area(tris), 1.0)

    def test_iso_surface(self):
        import numpy as np

        pts, tets = _cube()
        values = [p[0] + p[1] for p in pts]  # x + y: the iso-surface at 1 is a diagonal plane
        tris, vals, _rest = core.iso_surface(pts, values, core.straight_tets(tets), 1.0)
        self.assertAlmostEqual(self._area(tris), math.sqrt(2.0))
        self.assertTrue(np.allclose(tris[:, :, 0] + tris[:, :, 1], 1.0))
        self.assertTrue(np.allclose(vals, 1.0))
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        big = np.linalg.norm(normals, axis=1) > 1e-12
        # every triangle faces the lower values
        self.assertTrue((normals[big] @ np.array([1.0, 1.0, 0.0]) < 0).all())
        none, _v, _r = core.iso_surface(pts, values, core.straight_tets(tets), 5.0)
        self.assertEqual(len(none), 0)

    def test_iso_surface_skips_missing_values(self):
        import numpy as np

        pts, tets = _cube()
        values = [p[0] for p in pts]
        values[6] = float("nan")  # (1, 1, 1): no value (a body without strength)
        tris, vals, _rest = core.iso_surface(pts, values, core.straight_tets(tets), 0.5)
        self.assertGreater(len(tris), 0)
        self.assertFalse(np.isnan(tris).any())
        self.assertFalse(np.isnan(vals).any())
        self.assertLess(self._area(tris), 1.0)  # the tetrahedra at (1, 1, 1) are left out

    def test_quadratic_iso_matches_linear_field(self):
        import numpy as np

        corners = [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)]
        pts = list(corners)
        for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
            pts.append(tuple((corners[a][k] + corners[b][k]) / 2.0 for k in range(3)))
        values = [p[2] for p in pts]  # z
        tris, _vals, _rest = core.iso_surface(pts, values, core.straight_tets([range(10)]), 1.0)
        # the cut at z = 1 of the tetrahedron: a right triangle with legs 1
        self.assertAlmostEqual(self._area(tris), 0.5)
        self.assertTrue(np.allclose(tris[:, :, 2], 1.0))

    def test_mesh_lines_of_a_cut(self):
        import numpy as np

        corners = [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)]
        pts = list(corners)
        for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
            pts.append(tuple((corners[a][k] + corners[b][k]) / 2.0 for k in range(3)))
        straight = core.straight_tets([list(range(10))])
        tris, _v, _r, owners = core.cut(
            pts, [0.0] * 10, straight, (0, 0, 0.5), (0, 0, 1), owners=True
        )
        self.assertEqual(len(owners), len(tris))
        lines = core.cut_lines(tris, owners, 1)
        # one 10-node element: only its outline (the cut of its outer faces), not the pieces'
        length = float(np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1).sum())
        self.assertAlmostEqual(length, 3.0 + 1.5 * math.sqrt(2.0))
        # the cube of 5 straight tetrahedra cut across X: the square, and the faces between
        # the tetrahedra where the plane crosses them (drawn once from each side)
        pts, tets = _cube()
        tris, _v, _r, owners = core.cut(
            pts, [0.0] * 8, core.straight_tets(tets), (0.5, 0.5, 0.5), (1, 0, 0), owners=True
        )
        lines = core.cut_lines(tris, owners, len(tets))
        self.assertTrue(np.allclose(lines[:, :, 0], 0.5))
        on_square = [
            s
            for s in lines
            if all(min(abs(c), abs(c - 1.0)) < 1e-9 for c in (s[0][1], s[1][1]))
            or all(min(abs(c), abs(c - 1.0)) < 1e-9 for c in (s[0][2], s[1][2]))
        ]
        outline = sum(float(np.linalg.norm(s[1] - s[0])) for s in on_square)
        self.assertAlmostEqual(outline, 4.0)
        self.assertEqual(len(core.cut_lines([], [], 3)), 0)

    def test_vector_arrows(self):
        import numpy as np

        # a 10 x 10 grid of points on the plane x = 0, all moving down -Z, more to the right
        ys, zs = np.meshgrid(np.arange(10.0) + 0.5, np.arange(10.0) + 0.5)
        pts = np.column_stack([np.zeros(100), ys.ravel(), zs.ravel()])
        moves = np.column_stack([np.zeros(100), np.zeros(100), -(1.0 + ys.ravel())])
        chosen, segments, arrow = core.vector_arrows(pts, moves, (1, 0, 0), 2.0, 2.0)
        self.assertEqual(len(chosen), 25)  # one per 2 x 2 square
        self.assertEqual(segments.shape, (75, 2, 3))
        shafts = segments[:25]
        lengths = np.linalg.norm(shafts[:, 1] - shafts[:, 0], axis=1)
        self.assertAlmostEqual(float(lengths.max()), 2.0)  # the biggest is `length` long
        self.assertTrue(np.allclose(shafts[:, 0], pts[chosen]))  # from the points kept
        down = (shafts[:, 1] - shafts[:, 0])[:, 2]
        self.assertTrue((down < 0).all())  # the way they move
        self.assertTrue(np.allclose(segments[:, :, 0], 0.0))  # the heads in the plane too
        self.assertEqual(sorted(set(arrow.tolist())), list(range(25)))
        none = core.vector_arrows(pts, np.zeros((100, 3)), (1, 0, 0), 2.0, 2.0)
        self.assertEqual(len(none[0]), 0)

    def test_slice_planes(self):
        import numpy as np

        origin, normal = core.slice_plane({"axis": "y", "offset": 4.0})
        self.assertEqual((origin, normal), ((0.0, 4.0, 0.0), (0.0, 1.0, 0.0)))
        origin, normal = core.slice_plane({"axis": "x", "offset": 2.0, "flip": True})
        self.assertEqual((origin, normal), ((2.0, 0.0, 0.0), (-1.0, -0.0, -0.0)))
        spec = {"axis": "face", "normal": (0.0, 3.0, 4.0), "offset": 10.0}
        origin, normal = core.slice_plane(spec)
        self.assertTrue(np.allclose(normal, (0.0, 0.6, 0.8)))
        self.assertAlmostEqual(float(np.dot(origin, normal)), 10.0)
        pts, _tets = _cube()
        self.assertEqual(core.slice_range({"axis": "z"}, pts), (0.0, 1.0))
        lo, hi = core.slice_range({"axis": "face", "normal": (1, 1, 0)}, pts)
        self.assertAlmostEqual(hi - lo, math.sqrt(2.0))

    def test_plane_slice(self):
        spec = core.plane_slice((0, 0, -1), (5, 5, 7.5))
        self.assertEqual((spec["axis"], spec["offset"], spec["flip"]), ("z", 7.5, False))
        spec = core.plane_slice((0, 3, 4), (0, 0, 10))
        self.assertEqual(spec["axis"], "face")
        self.assertAlmostEqual(spec["offset"], 8.0)
        origin, normal = core.slice_plane(spec)
        self.assertAlmostEqual(sum(a * b for a, b in zip(origin, normal)), 8.0)
        self.assertIsNone(core.plane_slice((0, 0, 0), (0, 0, 0)))

    def test_face_slice(self):
        pts = [(0, 0, 0), (100, 0, 0), (100, 10, 10), (0, 10, 10)]
        # the top face (outward +Z): across Z at half height, the lower half kept (its cut face
        # looks up, at whoever clicked the top)
        spec = core.face_slice((0, 0, 1), pts)
        self.assertEqual(spec, {"axis": "z", "flip": True, "style": "clip", "offset": 5.0})
        origin, normal = core.slice_plane(spec)
        self.assertEqual(normal[2], -1.0)
        # the end face at x = 0 (outward -X): across X, the far side kept
        spec = core.face_slice((-1, 0, 0), pts, "slice")
        self.assertEqual((spec["axis"], spec["flip"], spec["offset"]), ("x", False, 50.0))
        self.assertEqual(spec["style"], "slice")
        # a sloped face: its own direction
        spec = core.face_slice((0, -1, 1), pts)
        self.assertEqual(spec["axis"], "face")
        self.assertAlmostEqual(spec["normal"][1], math.sqrt(0.5))
        self.assertAlmostEqual(spec["normal"][2], -math.sqrt(0.5))
        self.assertIsNone(core.face_slice((0, 0, 0), pts))

    def test_locate(self):
        import numpy as np

        pts, tets = _cube()
        straight = core.straight_tets(tets)
        field = [p[0] + 2 * p[1] + 3 * p[2] for p in pts]
        for point in ((0.3, 0.6, 0.2), (0.9, 0.1, 0.95), (0.5, 0.5, 0.5)):
            where = core.locate(pts, straight, point)
            self.assertIsNotNone(where)
            row, weights = where
            self.assertAlmostEqual(float(np.sum(weights)), 1.0)
            self.assertTrue((weights >= -1e-9).all())
            expect = point[0] + 2 * point[1] + 3 * point[2]
            self.assertAlmostEqual(float(core.at_point(field, straight, where)), expect)
        # on the surface and at a corner: found; outside: None
        self.assertIsNotNone(core.locate(pts, straight, (1.0, 0.4, 0.4)))
        self.assertIsNotNone(core.locate(pts, straight, (1.0, 1.0, 1.0)))
        self.assertIsNone(core.locate(pts, straight, (1.2, 0.5, 0.5)))
        self.assertIsNone(core.locate(pts, straight, (0.5, 0.5, -0.01)))
        # a displacement per point: a vector back
        moves = [(p[0], 0.0, -p[2]) for p in pts]
        where = core.locate(pts, straight, (0.25, 0.5, 0.75))
        moved = core.at_point(moves, straight, where)
        self.assertTrue(np.allclose(moved, (0.25, 0.0, -0.75)))
        boxes = core.tet_boxes(pts, straight)
        self.assertEqual(
            core.locate(pts, straight, (0.3, 0.6, 0.2), boxes)[0],
            core.locate(pts, straight, (0.3, 0.6, 0.2))[0],
        )

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


class SolverDataTests(unittest.TestCase):
    SUMMARY = {
        "solved": "2026-10-26 20:15:00",
        "seconds": 3.21,
        "timings": {"model": 0.1, "mesh": 1.2, "solve": 1.5, "results": 0.2, "odd_step": 0.01},
        "mesh": {
            "nodes": 12345,
            "elements": 6789,
            "size": 2.5,
            "order": "parabolic",
            "smallest": 0.8,
            "largest": 3.1,
            "worst_aspect": 4.25,
            "over_limit": 0,
            "mesher": "gmsh",
        },
        "safety_basis": "yield",
        "adaptive": {
            "result": "von_mises",
            "passes": [
                {"nodes": 5000, "elements": 2500, "value": 120.0},
                {"nodes": 12345, "elements": 6789, "value": 131.5},
            ],
        },
        "notes": ["Netgen meshed this part (Gmsh could not)."],
    }

    def test_rows(self):
        rows = dict(core.solver_rows(self.SUMMARY))
        self.assertEqual(
            list(dict(core.solver_rows(self.SUMMARY))),
            ["Solve", "Mesh", "Adaptive mesh refinement", "Messages"],
        )
        solve = dict(rows["Solve"])
        self.assertEqual(solve["Time taken"], "3.21 s")
        self.assertEqual(solve["    Meshing"], "1.2 s")
        self.assertEqual(solve["    Odd step"], "0.01 s")
        self.assertEqual(solve["Safety factor from"], "Yield strength")
        mesh = dict(rows["Mesh"])
        self.assertEqual(mesh["Nodes"], "12,345")
        self.assertEqual(mesh["Degrees of freedom"], "37,035")
        self.assertEqual(mesh["Element order"], "Parabolic (10-node tetrahedra)")
        self.assertEqual(mesh["Smallest element edge"], "0.8 mm")
        self.assertEqual(mesh["Mesher"], "Gmsh")
        passes = dict(rows["Adaptive mesh refinement"])
        self.assertIn("131.5 MPa", passes["Solve 2"])
        self.assertIn("12,345 nodes", passes["Solve 2"])
        self.assertEqual(rows["Messages"], [("", "Netgen meshed this part (Gmsh could not).")])
        text = core.solver_text(core.solver_rows(self.SUMMARY))
        self.assertIn("  Nodes: 12,345", text)
        self.assertIn("  Netgen meshed this part (Gmsh could not).", text)

    def test_mesh_statistics_fill_in(self):
        rows = dict(core.solver_rows({"solved": "x"}, {"nodes": 10, "elements": 2}))
        self.assertEqual(dict(rows["Mesh"])["Elements"], "2")
        self.assertEqual(core.solver_rows({}), [])

    def test_coordinates(self):
        self.assertEqual(core.fmt_mm(12.5), "12.5")
        self.assertEqual(core.fmt_mm(-0.0001), "0")
        self.assertEqual(core.fmt_mm(1234.56789), "1234.568")
        self.assertEqual(core.fmt_mm(None), "-")


class ConvergenceTests(unittest.TestCase):
    ADAPTIVE = {
        "result": "von_mises",
        "passes": [
            {"nodes": 459, "elements": 200, "value": 50.0},
            {"nodes": 1200, "elements": 600, "value": 58.0},
            {"nodes": 2900, "elements": 1500, "value": 60.0},
        ],
    }

    def test_each_solve_and_its_change(self):
        data = core.convergence(self.ADAPTIVE, 5.0)
        self.assertEqual(data["title"], "Stress: Von Mises")
        self.assertEqual(data["extreme"], "highest")
        self.assertEqual(data["unit"], "MPa")
        self.assertEqual([s["solve"] for s in data["solves"]], [1, 2, 3])
        self.assertEqual([s["nodes"] for s in data["solves"]], [459, 1200, 2900])
        self.assertIsNone(data["solves"][0]["change"])
        # the engine's own rule (simulation_core.converged): % of the larger of the two
        self.assertAlmostEqual(data["solves"][1]["change"], 8.0 / 58.0 * 100.0)
        self.assertAlmostEqual(data["solves"][2]["change"], 2.0 / 60.0 * 100.0)
        self.assertTrue(data["converged"])
        self.assertTrue(sim.converged(58.0, 60.0, 5.0))
        self.assertIn("Converged", data["sentence"])
        self.assertIn("3.33 %", data["sentence"])
        self.assertIn("5 % tolerance", data["sentence"])

    def test_not_converged_says_what_to_do(self):
        data = core.convergence(self.ADAPTIVE, 2.0)
        self.assertFalse(data["converged"])
        self.assertFalse(sim.converged(58.0, 60.0, 2.0))
        self.assertIn("Not converged", data["sentence"])
        self.assertIn("Adaptive Mesh Refinement", data["sentence"])

    def test_units_and_odd_cases(self):
        inches = core.convergence(
            {"result": "displacement", "passes": [{"nodes": 9, "value": 2.54}]}, 5.0, "in"
        )
        self.assertEqual(inches["unit"], "in")
        self.assertAlmostEqual(inches["solves"][0]["value"], 0.1)
        self.assertIsNone(inches["converged"])
        self.assertIn("One solve", inches["sentence"])
        wrong = core.convergence({"result": "von_mises", "passes": [{"value": 1.0}]}, None, "in")
        self.assertEqual(wrong["unit"], "MPa")  # (inches are no stress unit)
        lowest = core.convergence(
            {"result": "principal_3", "passes": [{"value": -10.0}, {"value": -10.2}]}, None
        )
        self.assertEqual(lowest["extreme"], "lowest")
        self.assertIsNone(lowest["converged"])  # (no tolerance known)
        self.assertIn("changed by 1.96 %", lowest["sentence"])
        self.assertIsNone(core.convergence(None))
        self.assertIsNone(core.convergence({"result": "von_mises", "passes": []}))

    def test_round_ticks(self):
        self.assertEqual(core.nice_ticks(98.3, 112.7), [95.0, 100.0, 105.0, 110.0, 115.0])
        self.assertEqual(core.nice_ticks(-30.0, -10.0), [-30.0, -25.0, -20.0, -15.0, -10.0])
        ticks = core.nice_ticks(0.1995, 0.2005)
        self.assertLessEqual(ticks[0], 0.1995)
        self.assertGreaterEqual(ticks[-1], 0.2005)
        self.assertIn(0.2, ticks)
        same = core.nice_ticks(5.0, 5.0)  # one value: a range around it
        self.assertLess(same[0], 5.0)
        self.assertGreater(same[-1], 5.0)
        self.assertEqual(core.change_pct(None, 1.0), None)
        self.assertEqual(core.change_pct(0.0, 0.0), 0.0)


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

    def test_cover_and_two_studies(self):
        text = core.report_html(
            {
                "title": "Bracket",
                "logo": "data:image/png;base64,AAA",
                "picture": "data:image/png;base64,BBB",
                "summary": "First line\nsame paragraph\n\nSecond <paragraph>",
                "project": "P-1",
                "approver": "M. Rossi",
                "revision": "C",
                "studies": [
                    {"study": "Light", "results": [("safety", 4.0, 15.0, "")]},
                    {"study": "Heavy", "results": [("safety", 1.5, 15.0, "")], "out_of_date": 1},
                ],
            }
        )
        self.assertIn('class="logo" src="data:image/png;base64,AAA"', text)
        self.assertIn('class="cover" src="data:image/png;base64,BBB"', text)
        self.assertIn("First line<br>same paragraph", text)
        self.assertIn("Second &lt;paragraph&gt;", text)
        self.assertIn("<td>M. Rossi</td>", text)
        self.assertIn("Studies: Light, Heavy", text)
        self.assertEqual(text.count('<h1 class="study">'), 2)
        self.assertEqual(text.count("<h2>Results</h2>"), 2)
        self.assertEqual(text.count('class="warning"'), 1)  # only Heavy is out of date

    def test_empty_report(self):
        text = core.report_html({})
        self.assertIn("Static Stress report", text)
        self.assertNotIn("Adaptive mesh refinement", text)

    def test_adaptive_refinement_in_the_report(self):
        adaptive = ConvergenceTests.ADAPTIVE
        text = core.report_html({"study": "S", "convergence": core.convergence(adaptive, 5.0)})
        self.assertIn("<h3>Adaptive mesh refinement</h3>", text)
        self.assertIn("Stress: Von Mises, highest (MPa)", text)
        self.assertIn("<td>2,900</td>", text)
        self.assertIn("<td>3.33 %</td>", text)
        self.assertIn("Converged: the result changed by 3.33 %", text)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline recognition, the pure-Python half (sciforge/recognize_core.py): numbers with
float noise and measured values, the origin planes, 2D loops (clean-up, areas, the
create_sketch geometry they become), patterns of equal features (grids, circles, rows; noise
tolerated), the plan's ids and Fusion's order, the plan's arguments passing the AI
catalogue's own check, and the mesh helpers (circle / cylinder fits, arcs fitted on a
polygon). Runs without FreeCAD."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import recognize_core as core  # noqa: E402
from sciforge.ai import catalog  # noqa: E402


def line(a, b):
    return {"kind": "line", "a": a, "b": b}


def arc(c, r, a, b, ccw=True):
    return {"kind": "arc", "c": c, "r": r, "a": a, "b": b, "ccw": ccw}


def rect_loop(x0, y0, x1, y1):
    return [
        line((x0, y0), (x1, y0)),
        line((x1, y0), (x1, y1)),
        line((x1, y1), (x0, y1)),
        line((x0, y1), (x0, y0)),
    ]


class Numbers(unittest.TestCase):
    def test_snap_takes_float_noise_off(self):
        self.assertEqual(core.snap(9.9999999997), 10.0)
        self.assertEqual(core.snap(0.30000000004), 0.3)
        self.assertEqual(core.snap(-1e-12), 0.0)
        self.assertEqual(str(core.snap(-0.0)), "0.0")
        self.assertAlmostEqual(core.snap(25.980762113533), 25.980762, places=6)

    def test_nice_picks_the_roundest_value_within_the_tolerance(self):
        self.assertEqual(core.nice(5.98, 0.06), 6.0)
        self.assertEqual(core.nice(12.49, 0.02), 12.5)
        self.assertEqual(core.nice(3.1416, 0.001), 3.142)
        self.assertEqual(core.nice(7.3, 0.001), 7.3)

    def test_measured_values_keep_what_was_measured(self):
        rounded, measured = core.round_measured(5.98)
        self.assertEqual(rounded, 6.0)
        self.assertEqual(measured, 5.98)
        self.assertEqual(core.round_measured(40.001)[0], 40.0)

    def test_fmt_writes_numbers_as_a_person_does(self):
        self.assertEqual(core.fmt(10.0), "10")
        self.assertEqual(core.fmt(2.5), "2.5")
        self.assertEqual(core.fmt(0.125), "0.125")
        self.assertEqual(core.fmt(5.9999999999), "6")


class Planes(unittest.TestCase):
    def test_frames_are_right_handed_like_sciforges_sketches(self):
        for name, frame in core.PLANES.items():
            self.assertEqual(core.cross(frame["x"], frame["y"]), frame["n"], name)
        self.assertEqual(core.PLANES["XZ"]["n"], (0.0, -1.0, 0.0))

    def test_to_plane_and_back(self):
        for plane in core.PLANES:
            x, y, h = core.to_plane(plane, (3.0, -4.0, 5.0))
            back = core.from_plane(plane, x, y, h)
            for a, b in zip(back, (3.0, -4.0, 5.0)):
                self.assertAlmostEqual(a, b)
        self.assertEqual(core.to_plane("XZ", (1.0, -20.0, 7.0)), (1.0, 7.0, 20.0))

    def test_origin_axis_and_the_plane_for_a_direction(self):
        self.assertEqual(core.origin_axis((0, 0, -3)), "Z")
        self.assertEqual(core.origin_axis((1, 1e-9, 0)), "X")
        self.assertIsNone(core.origin_axis((1, 1, 0)))
        self.assertEqual(core.plane_for_direction((0, 1, 0)), ("XZ", -1))
        self.assertEqual(core.plane_for_direction((0, 0, 1)), ("XY", 1))
        self.assertEqual(core.plane_for_direction((1, 1, 0)), (None, 0))

    def test_canonical_direction_names_a_line_once(self):
        self.assertEqual(core.canonical_direction((0, 0, -2)), (-0.0, -0.0, 1.0))
        self.assertTrue(core.parallel((1, 2, 3), (-2, -4, -6)))
        self.assertTrue(core.square((1, 0, 0), (0, 5, 0)))


class Loops(unittest.TestCase):
    def test_area_of_a_rectangle_and_of_a_rounded_one(self):
        self.assertAlmostEqual(core.signed_area(rect_loop(0, 0, 40, 20)), 800.0)
        r = 5.0  # a 40 x 20 rectangle with its four corners rounded r 5
        loop = [
            line((5, 0), (35, 0)),
            arc((35, 5), r, (35, 0), (40, 5)),
            line((40, 5), (40, 15)),
            arc((35, 15), r, (40, 15), (35, 20)),
            line((35, 20), (5, 20)),
            arc((5, 15), r, (5, 20), (0, 15)),
            line((0, 15), (0, 5)),
            arc((5, 5), r, (0, 5), (5, 0)),
        ]
        self.assertAlmostEqual(core.signed_area(loop), 800 - (4 - math.pi) * 25, places=6)
        self.assertAlmostEqual(
            core.signed_area([{"kind": "circle", "c": (0, 0), "r": 2}]), 4 * math.pi
        )

    def test_clockwise_loops_have_a_negative_area(self):
        loop = list(reversed([line(s["b"], s["a"]) for s in rect_loop(0, 0, 4, 2)]))
        self.assertAlmostEqual(core.signed_area(loop), -8.0)

    def test_point_inside(self):
        loop = rect_loop(0, 0, 10, 10)
        self.assertTrue(core.point_inside((5, 5), loop))
        self.assertFalse(core.point_inside((15, 5), loop))

    def test_clean_merges_collinear_lines_and_closes_the_loop(self):
        loop = [
            line((0, 0), (10, 0)),
            line((10, 0), (20.0000000001, 0)),
            line((20, 0), (20, 10)),
            line((20, 10), (0, 10)),
            line((0, 10), (0, 0)),
        ]
        clean = core.clean_loop(loop)
        self.assertEqual(len(clean), 4)
        for i, seg in enumerate(clean):
            self.assertEqual(seg["a"], clean[i - 1]["b"])
        self.assertEqual(core.loop_geometry(clean), {"rect": [0.0, 0.0, 20.0, 10.0]})

    def test_clean_merges_arcs_of_one_circle_and_drops_zero_lines(self):
        loop = [
            arc((0, 0), 5, (5, 0), (0, 5)),
            arc((0, 0), 5, (0, 5), (-5, 0)),
            line((-5, 0), (-5, 0)),
            line((-5, 0), (5, 0)),
        ]
        clean = core.clean_loop(loop)
        self.assertEqual([s["kind"] for s in clean], ["arc", "line"])
        self.assertAlmostEqual(core.arc_sweep(clean[0]), math.pi)
        full = core.clean_loop([arc((1, 2), 3, (4, 2), (4, 2))])
        self.assertEqual(full, [{"kind": "circle", "c": (1.0, 2.0), "r": 3.0}])

    def test_geometry_items(self):
        self.assertEqual(
            core.loop_geometry([{"kind": "circle", "c": (25, 15), "r": 5}], name="bore"),
            {"circle": [25, 15, 5], "name": "bore"},
        )
        slot = [
            line((30, 20), (50, 20)),
            arc((50, 25), 5, (50, 20), (50, 30)),
            line((50, 30), (30, 30)),
            arc((30, 25), 5, (30, 30), (30, 20)),
        ]
        self.assertEqual(
            core.loop_geometry(core.clean_loop(slot)), {"slot": [50, 25, 30, 25, 10.0]}
        )
        tri = [line((0, 0), (10, 0)), line((10, 0), (0, 10)), line((0, 10), (0, 0))]
        self.assertEqual(core.loop_geometry(tri), {"polyline": [[0, 0], [10, 0], [0, 10]]})
        d_shape = [
            line((0, 0), (10, 0)),
            arc((10, 5), 5, (10, 0), (10, 10)),
            line((10, 10), (0, 10)),
        ]
        d_shape.append(line((0, 10), (0, 0)))
        item = core.loop_geometry(core.clean_loop(d_shape))
        self.assertIn("segments", item)
        self.assertEqual(item["segments"][1], {"arc": [10, 5, 5, -90.0, 90.0]})
        self.assertIsNone(core.loop_geometry([{"kind": "other", "a": (0, 0), "b": (1, 1)}]))

    def test_a_clockwise_arc_is_written_counter_clockwise(self):
        seg = arc((0, 0), 2, (0, 2), (2, 0), ccw=False)  # quarter turn clockwise
        self.assertEqual(core._arc_item(seg), {"arc": [0, 0, 2, 0.0, 90.0]})

    def test_geometry_of_loops_passes_create_sketch(self):
        loops = [
            rect_loop(0, 0, 60, 40),
            [{"kind": "circle", "c": (10, 10), "r": 3}],
            [line((0, 0), (10, 0)), arc((10, 5), 5, (10, 0), (10, 10)), line((10, 10), (0, 0))],
        ]
        geometry = [core.loop_geometry(core.clean_loop(lp)) for lp in loops]
        args = core.sketch_args("XZ", 5.0, geometry)
        self.assertEqual(catalog.validate("create_sketch", args), [])

    def test_describe_loop(self):
        self.assertEqual(core.describe_loop(rect_loop(0, 0, 40, 20)), "rectangle 40 x 20")
        self.assertEqual(
            core.describe_loop([{"kind": "circle", "c": (0, 0), "r": 4}]), "circle d 8"
        )


class Patterns(unittest.TestCase):
    def test_a_grid(self):
        pts = [(10 + 20 * i, 10 + 20 * j) for j in range(2) for i in range(3)]
        found = core.find_pattern(pts)
        self.assertEqual(found["kind"], "rectangular")
        self.assertEqual((found["count"], found["count2"]), (3, 2))
        self.assertAlmostEqual(found["spacing"], 20)
        self.assertAlmostEqual(found["spacing2"], 20)
        self.assertEqual(found["origin"], (10, 10))

    def test_a_grid_with_noise_and_shuffled(self):
        pts = [
            (10 + 15 * i + 2e-5 * ((i * 7 + j) % 3), 12 + 15 * j)
            for i in range(4)
            for j in range(3)
        ]
        pts.reverse()
        found = core.find_pattern(pts, 1e-4)
        self.assertEqual(found["kind"], "rectangular")
        self.assertEqual((found["count"], found["count2"]), (4, 3))

    def test_a_row_along_y(self):
        found = core.find_pattern([(5, 0), (5, 10), (5, 20)])
        self.assertEqual(found["kind"], "rectangular")
        self.assertEqual(found["axis"], "y")
        self.assertEqual(found["count"], 3)
        self.assertEqual(found["count2"], 1)

    def test_a_grid_with_a_missing_node_is_no_grid(self):
        pts = [(0, 0), (10, 0), (0, 10)]
        found = core.find_pattern(pts)
        self.assertNotEqual((found or {}).get("kind"), "rectangular")

    def test_uneven_spacing_is_no_pattern(self):
        self.assertIsNone(core.find_pattern([(0, 0), (10, 0), (25, 0)]))

    def test_a_bolt_circle(self):
        pts = [
            (30 * math.cos(math.radians(60 * k)), 30 * math.sin(math.radians(60 * k)))
            for k in range(6)
        ]
        found = core.find_pattern(pts)
        self.assertEqual(found["kind"], "circular")
        self.assertEqual(found["count"], 6)
        self.assertTrue(found["full"])
        self.assertAlmostEqual(found["radius"], 30)
        self.assertAlmostEqual(found["step"], 60)

    def test_a_partial_arc_of_holes(self):
        pts = [
            (50 + 20 * math.cos(math.radians(a)), 20 * math.sin(math.radians(a)))
            for a in (10, 40, 70, 100)
        ]
        found = core.find_pattern(pts)
        self.assertEqual(found["kind"], "circular")
        self.assertFalse(found["full"])
        self.assertAlmostEqual(found["step"], 30)
        self.assertAlmostEqual(found["start"], 10)
        self.assertAlmostEqual(found["center"][0], 50)

    def test_four_holes_on_a_square_grid_or_a_flange(self):
        pts = [(10, 10), (-10, 10), (-10, -10), (10, -10)]
        self.assertEqual(core.find_pattern(pts)["kind"], "rectangular")
        found = core.find_pattern(pts, circle_centres=[(0, 0)])
        self.assertEqual(found["kind"], "circular")

    def test_a_diagonal_row(self):
        found = core.find_pattern([(0, 0), (3, 4), (6, 8)])
        self.assertEqual(found["kind"], "linear")
        self.assertAlmostEqual(found["spacing"], 5)

    def test_pattern_order_starts_with_the_drawn_feature(self):
        pts = [(30, 10), (10, 10), (20, 10)]
        found = core.find_pattern(pts)
        self.assertEqual(core.pattern_order(pts, found)[0], (10, 10))
        ring = [
            (30 * math.cos(math.radians(a)), 30 * math.sin(math.radians(a))) for a in (120, 0, 240)
        ]
        found = core.find_pattern(ring)
        ordered = core.pattern_order(ring, found)
        self.assertAlmostEqual(ordered[0][0], 30)

    def test_ideal_points_put_measured_holes_where_the_pattern_says(self):
        pts = [
            (30.003 * math.cos(math.radians(a)) + 0.002, 29.998 * math.sin(math.radians(a)))
            for a in range(0, 360, 60)
        ]
        found = core.find_pattern(pts, 0.02)
        self.assertEqual(found["kind"], "circular")
        ideal = core.ideal_points(pts, found, 0.01)
        for p in ideal:
            self.assertAlmostEqual(math.hypot(*p), 30.0, places=9)
        self.assertAlmostEqual(ideal[0][0], 30.0, places=9)
        self.assertAlmostEqual(ideal[0][1], 0.0, places=9)


class ThePlan(unittest.TestCase):
    def test_ids_follow_sciforges_naming(self):
        plan = core.Plan()
        s1 = plan.add("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 1, 1]}]}, "a")
        e1 = plan.add("extrude", {"profile": s1, "distance": 1}, "b", uses={"profile": 1})
        s2 = plan.add("create_sketch", {"plane": "XY", "geometry": [{"circle": [0, 0, 1]}]}, "c")
        p1 = plan.add("circular_pattern", {"features": [e1], "axis": "Z", "quantity": 3}, "d")
        self.assertEqual((s1, e1, s2, p1), ("Sketch1", "Extrude1", "Sketch2", "Pattern1"))
        self.assertEqual(plan.steps[1]["uses"], {"profile": 1})
        self.assertEqual(plan.step_of("Sketch2"), 3)
        self.assertEqual([s["step"] for s in plan.steps], [1, 2, 3, 4])

    def test_ids_skip_the_ones_the_design_has(self):
        plan = core.Plan(taken={"Sketch1", "Sketch2", "Extrude1"})
        self.assertEqual(plan.new_id("create_sketch"), "Sketch3")
        self.assertEqual(plan.new_id("extrude"), "Extrude2")
        self.assertEqual(plan.new_id("fillet"), "Fillet1")

    def test_extents(self):
        self.assertEqual(core.base_extrude_args(0, 10), (0.0, {"distance": 10.0}))
        self.assertEqual(core.base_extrude_args(-20, 0), (0.0, {"distance": 20.0, "flip": True}))
        self.assertEqual(
            core.base_extrude_args(-5, 5), (0.0, {"distance": 10.0, "direction": "symmetric"})
        )
        self.assertEqual(
            core.base_extrude_args(-3, 5),
            (0.0, {"distance": 5.0, "direction": "two_sides", "distance2": 3.0}),
        )
        self.assertEqual(core.base_extrude_args(4, 9), (4.0, {"distance": 5.0}))
        self.assertEqual(
            core.extent_args(12, 20, "cut"),
            (20, {"distance": 8.0, "operation": "cut", "flip": True}),
        )
        self.assertEqual(core.extent_args(5, 10, "join"), (5, {"distance": 5.0}))

    def test_every_extent_passes_the_extrude_tool(self):
        for h0, h1 in ((0, 10), (-20, 0), (-5, 5), (-3, 5), (4, 9)):
            _offset, args = core.base_extrude_args(h0, h1)
            self.assertEqual(catalog.validate("extrude", dict(args, profile="Sketch1")), [])
        for op in ("cut", "join"):
            _offset, args = core.extent_args(1, 3, op)
            self.assertEqual(catalog.validate("extrude", dict(args, profile="Sketch1")), [])

    def test_fusions_order(self):
        kinds = ["fillet", "hole", "chamfer", "pattern", "boss", "pocket", "base"]
        got = [f["kind"] for f in core.ordered([{"kind": k} for k in kinds])]
        self.assertEqual(got, ["base", "boss", "pocket", "hole", "pattern", "chamfer", "fillet"])

    def test_check_plan_uses_the_catalogue(self):
        steps = [
            {"step": 1, "tool": "extrude", "args": {"profile": "Sketch1", "distance": -1}},
            {"step": 2, "tool": "fillet", "args": {"radius": 2, "edges": {"all": True}}},
        ]
        problems = core.check_plan(steps, catalog.validate)
        self.assertEqual([n for n, _s in problems], [1])
        self.assertIn("distance", problems[0][1])

    def test_typical_plan_arguments_pass_the_catalogue(self):
        calls = [
            ("hole", {"sketch": "Sketch2", "diameter": 6, "through_all": True}),
            (
                "hole",
                {
                    "sketch": "Sketch2",
                    "diameter": 6.6,
                    "through_all": True,
                    "counterbore": {"diameter": 11, "depth": 6.5},
                },
            ),
            (
                "hole",
                {
                    "sketch": "Sketch2",
                    "diameter": 5,
                    "depth": 6,
                    "drill_point": "angle",
                    "drill_angle": 118,
                },
            ),
            (
                "rectangular_pattern",
                {
                    "features": ["Hole1"],
                    "direction": "X",
                    "quantity": 3,
                    "distance": 20,
                    "distribution": "spacing",
                    "direction2": "Y",
                    "quantity2": 2,
                    "distance2": 20,
                },
            ),
            ("circular_pattern", {"features": ["Hole1"], "axis": "Z", "quantity": 6}),
            (
                "circular_pattern",
                {
                    "features": ["Hole1"],
                    "axis": {"face": {"type": "cylinder", "radius": 40, "count": 1}},
                    "quantity": 4,
                    "type": "angle",
                    "angle": 90,
                },
            ),
            (
                "fillet",
                {
                    "edges": {"type": "line", "at": {"axis": "z", "value": "max"}, "count": 4},
                    "radius": 2,
                },
            ),
            (
                "chamfer",
                {
                    "edges": {"any_of": [{"type": "line", "count": 1}], "count": 1},
                    "distance": 1,
                    "distance2": 2,
                },
            ),
            ("revolve", {"profile": "Sketch1", "axis": "Z"}),
        ]
        for tool, args in calls:
            self.assertEqual(catalog.validate(tool, args), [], tool)

    def test_confidence(self):
        self.assertEqual(core.confidence(100, 100, 0, 1000), 1.0)
        self.assertEqual(core.confidence(50, 100, 0, 1000), 0.5)
        self.assertLess(core.confidence(100, 100, 10, 1000), 1.0)
        self.assertEqual(core.confidence(100, 100, 1000, 1000), 0.0)
        self.assertEqual(core.confidence(0, 0, 0, 0), 0.0)


class ExactSketches(unittest.TestCase):
    def test_lines_meet_arcs_exactly(self):
        """A line written with 6 decimals missed an arc's end by 4e-7 mm: more than FreeCAD's
        1e-7 closing tolerance, so the sketch had no area. Lines now take the arc's ends."""
        r = 20.0
        loop = [
            line((14.142136, 14.142136), (7.071068, 7.071068)),
            arc((0, 0), 10.0, (7.071068, 7.071068), (7.071068, -7.071068), ccw=False),
            line((7.071068, -7.071068), (14.142136, -14.142136)),
            arc((0, 0), r, (14.142136, -14.142136), (14.142136, 14.142136), ccw=True),
        ]
        item = core.loop_geometry(core.clean_loop(loop))
        segs = item["segments"]
        ends = []
        for seg in segs:
            if "line" in seg:
                x0, y0, x1, y1 = seg["line"]
                ends.append(((x0, y0), (x1, y1)))
            else:
                cx, cy, rr, a0, a1 = seg["arc"]
                p0 = (cx + rr * math.cos(math.radians(a0)), cy + rr * math.sin(math.radians(a0)))
                p1 = (cx + rr * math.cos(math.radians(a1)), cy + rr * math.sin(math.radians(a1)))
                ends.append((p0, p1))
        points = [p for pair in ends for p in pair]
        for p in points:  # every end meets another end within 1e-12
            near = [q for q in points if q is not p and math.dist(p, q) < 1e-12]
            self.assertTrue(near, p)

    def test_shift_and_compare_items(self):
        items = [
            {"circle": [1, 2, 3]},
            {"rect": [0, 0, 4, 2]},
            {"slot": [0, 0, 10, 0, 4]},
            {"polyline": [[0, 0], [1, 0], [0, 1]]},
            {"segments": [{"line": [0, 0, 1, 0]}, {"arc": [1, 1, 1, -90, 90]}]},
        ]
        moved = [core.shift_item(i, 5, -2) for i in items]
        self.assertEqual(moved[0], {"circle": [6, 0, 3]})
        self.assertEqual(moved[1], {"rect": [5, -2, 9, 0]})
        back = [core.shift_item(i, -5, 2) for i in moved]
        self.assertTrue(core.same_items(items, back))
        self.assertTrue(core.same_items(list(reversed(items)), back))
        self.assertFalse(core.same_items(items, moved))
        self.assertFalse(core.same_items(items[:2], items[:1]))


class Frames(unittest.TestCase):
    def test_euler_round_trip(self):
        for rx, ry, rz in ((30, 0, 20), (-45, 10, 170), (0, 89, 0), (12.5, -33, -90)):
            rot = core.rotation_xyz(rx, ry, rz)
            again = core.rotation_xyz(*core.euler_xyz(rot))
            for i in range(3):
                for j in range(3):
                    self.assertAlmostEqual(rot[i][j], again[i][j], places=9)

    def test_straight_up_or_down(self):
        rot = core.rotation_xyz(25, 90, 0)
        again = core.rotation_xyz(*core.euler_xyz(rot))
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(rot[i][j], again[i][j], places=9)

    def test_closest_frame_is_the_smallest_turn(self):
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        rot = core.closest_frame((0, -s, c), (1, 0, 0))  # turned 30 degrees about X
        self.assertAlmostEqual(core.euler_xyz(rot)[0], 30.0, places=6)
        self.assertAlmostEqual(core.euler_xyz(rot)[1], 0.0, places=6)
        self.assertAlmostEqual(core.euler_xyz(rot)[2], 0.0, places=6)
        same = core.closest_frame((0, 0, 1), (1, 0, 0))
        self.assertEqual(
            [[round(v, 12) for v in row] for row in same], [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        )

    def test_a_frame_is_a_turn_not_a_mirror(self):
        rot = core.closest_frame((0.6, 0.8, 0), (0, 0, 1))
        det = (
            rot[0][0] * (rot[1][1] * rot[2][2] - rot[1][2] * rot[2][1])
            - rot[0][1] * (rot[1][0] * rot[2][2] - rot[1][2] * rot[2][0])
            + rot[0][2] * (rot[1][0] * rot[2][1] - rot[1][1] * rot[2][0])
        )
        self.assertAlmostEqual(det, 1.0)


class MeshHelpers(unittest.TestCase):
    def test_fit_circle(self):
        pts = [(3 + 7 * math.cos(t), -2 + 7 * math.sin(t)) for t in (0.1, 0.9, 2.0, 3.3, 5.0)]
        cx, cy, r = core.fit_circle(pts)
        self.assertAlmostEqual(cx, 3)
        self.assertAlmostEqual(cy, -2)
        self.assertAlmostEqual(r, 7)
        self.assertIsNone(core.fit_circle([(0, 0), (1, 1)]))

    def test_eigen(self):
        pairs = core.eigen_symmetric3([[2, 0, 0], [0, 5, 0], [0, 0, 1]])
        self.assertEqual([round(v, 9) for v, _ in pairs], [1, 2, 5])
        value, vec = pairs[0]
        self.assertAlmostEqual(abs(vec[2]), 1.0)

    def test_fit_cylinder_from_points_and_normals(self):
        pts, normals = [], []
        for k in range(12):
            t = 2 * math.pi * k / 12
            for z in (0.0, 8.0):
                pts.append((10 + 3 * math.cos(t), 5 + 3 * math.sin(t), z))
                normals.append((math.cos(t), math.sin(t), 0.0))
        centre, axis, r, rms = core.fit_cylinder(pts, normals)
        self.assertAlmostEqual(abs(axis[2]), 1.0)
        self.assertAlmostEqual(r, 3.0)
        self.assertAlmostEqual(centre[0], 10.0)
        self.assertAlmostEqual(centre[1], 5.0)
        self.assertLess(rms, 1e-9)

    def test_fit_arcs_on_a_meshed_rounded_rectangle(self):
        pts = [(5, 0), (35, 0)]
        for k in range(1, 9):  # corner r 5 about (35, 5), 8 steps
            t = -math.pi / 2 + (math.pi / 2) * k / 8
            pts.append((35 + 5 * math.cos(t), 5 + 5 * math.sin(t)))
        pts += [(40, 15), (35, 20), (5, 20), (0, 15), (0, 5)]
        loop = core.fit_arcs(pts, [(35, 5, 5)], tol=1e-6)
        kinds = [s["kind"] for s in loop]
        self.assertEqual(kinds.count("arc"), 1)
        a = [s for s in loop if s["kind"] == "arc"][0]
        self.assertTrue(a["ccw"])
        self.assertAlmostEqual(core.arc_sweep(a), math.pi / 2)

    def test_fit_arcs_turns_a_ring_into_a_circle(self):
        ring = [
            (4 * math.cos(2 * math.pi * k / 24), 4 * math.sin(2 * math.pi * k / 24))
            for k in range(24)
        ]
        self.assertEqual(core.fit_arcs(ring, [(0, 0, 4)], tol=1e-6)[0]["kind"], "circle")
        lines = core.fit_arcs([(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 0, 4)])
        self.assertEqual([s["kind"] for s in lines], ["line"] * 4)

    def test_snap_loop_rounds_and_keeps_the_loop_closed(self):
        loop = [
            line((0.0004, 0.0003), (34.9996, 0.0)),
            arc((35.0004, 4.9997), 5.0006, (34.9996, 0.0), (40.0001, 5.0)),
            line((40.0001, 5.0), (0.0004, 0.0003)),
        ]
        out = core.snap_loop(loop, 0.01)
        self.assertEqual(out[1]["c"], (35.0, 5.0))
        self.assertEqual(out[1]["r"], 5.0)
        self.assertEqual(out[0]["b"], out[1]["a"])
        self.assertEqual(out[2]["a"], out[1]["b"])
        self.assertAlmostEqual(out[1]["a"][0], 35.0, places=6)


if __name__ == "__main__":
    unittest.main()

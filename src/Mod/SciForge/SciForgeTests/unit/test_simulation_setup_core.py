# SPDX-License-Identifier: LGPL-2.1-or-later
"""Unit tests for simulation_setup_core: the SETUP side's rules without FreeCAD (builder sim-ui)."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import simulation_core as core  # noqa: E402
from sciforge import simulation_setup_core as s  # noqa: E402


class StudyRows(unittest.TestCase):
    def test_every_type_in_fusions_order(self):
        rows = s.study_rows()
        self.assertEqual([r[0] for r in rows], [k for k, _t, _a in core.STUDY_TYPES])
        self.assertTrue(all(r[3] for r in rows), "every type has a description")

    def test_only_static_stress_available(self):
        available = [r[0] for r in s.study_rows() if r[2]]
        self.assertEqual(available, ["static_stress"])

    def test_greyed_types_say_so(self):
        for key, _title, available, text in s.study_rows():
            if not available:
                self.assertIn("Not in SciForge yet", text, key)

    def test_limits_sentence(self):
        for word in ("linear", "3D-printed", "guide"):
            self.assertIn(word, s.LIMITS)


class Light(unittest.TestCase):
    def test_traffic_light(self):
        self.assertEqual(s.light([]), "green")
        self.assertEqual(s.light([("warning", "a")]), "yellow")
        self.assertEqual(s.light([("warning", "a"), ("error", "b")]), "red")

    def test_icons_and_texts(self):
        for state in ("green", "yellow", "red", None):
            self.assertTrue(s.light_icon(state).startswith("sim_precheck"))
            self.assertTrue(s.light_text(state))

    def test_errors_first(self):
        checks = [("warning", "w1"), ("error", "e1"), ("warning", "w2"), ("error", "e2")]
        self.assertEqual([t for _l, t in s.ordered_checks(checks)], ["e1", "e2", "w1", "w2"])


class Stages(unittest.TestCase):
    def test_rows_while_running(self):
        rows = s.stage_rows("solve", "running")
        self.assertEqual([r[2] for r in rows], ["done", "done", "done", "running", "waiting"])

    def test_rows_done_and_failed(self):
        self.assertEqual({r[2] for r in s.stage_rows("results", "done")}, {"done"})
        rows = s.stage_rows("mesh", "failed")
        self.assertEqual([r[2] for r in rows], ["done", "failed", "waiting", "waiting", "waiting"])

    def test_mesh_only_stages(self):
        rows = s.stage_rows("mesh", "running", ["model", "mesh"])
        self.assertEqual([r[0] for r in rows], ["model", "mesh"])

    def test_elapsed(self):
        self.assertEqual(s.elapsed_text(7), "0:07")
        self.assertEqual(s.elapsed_text(754), "12:34")
        self.assertEqual(s.elapsed_text(3723), "1:02:03")
        self.assertEqual(s.elapsed_text(None), "0:00")

    def test_button_names_the_count(self):
        self.assertEqual(s.solve_button_text(1), "Solve 1 Study")
        self.assertEqual(s.solve_button_text(3), "Solve 3 Studies")
        self.assertEqual(s.solve_button_text(0), "Solve")


class Forces(unittest.TestCase):
    def test_components_round_trip(self):
        size, unit = s.force_from_components(0, 30, -40)
        self.assertAlmostEqual(size, 50.0)
        self.assertAlmostEqual(unit[1], 0.6)
        back = s.components_of(size, unit)
        self.assertAlmostEqual(back[2], -40.0)

    def test_zero_force_refused(self):
        with self.assertRaises(core.SimulationError):
            s.force_from_components(0, 0, 0)


class Quantities(unittest.TestCase):
    def test_plain_number_in_the_engines_unit(self):
        self.assertEqual(s.parse_quantity("100", "force"), 100.0)
        self.assertEqual(s.parse_quantity("2,5", "pressure"), 2.5)

    def test_unit_override(self):
        self.assertAlmostEqual(s.parse_quantity("0.5 kN", "force"), 500.0)
        self.assertAlmostEqual(s.parse_quantity("10 lbf", "force"), 44.482216, 5)
        self.assertAlmostEqual(s.parse_quantity("1 bar", "pressure"), 0.1)
        self.assertAlmostEqual(s.parse_quantity("2 N m", "moment"), 2000.0)
        self.assertAlmostEqual(s.parse_quantity("1 in", "length"), 25.4)
        self.assertAlmostEqual(s.parse_quantity("9.80665 m/s^2", "acceleration"), 9806.65)
        self.assertAlmostEqual(s.parse_quantity("1e3 Pa", "pressure"), 0.001)

    def test_bad_values_say_why(self):
        for text, family in (("", "force"), ("abc", "force"), ("10 furlongs", "length")):
            with self.assertRaises(core.SimulationError):
                s.parse_quantity(text, family)

    def test_format(self):
        self.assertEqual(s.format_quantity(250.0, "force"), "250 N")
        self.assertEqual(s.format_quantity(0.1, "pressure"), "0.1 MPa")
        self.assertEqual(s.format_quantity(3.0, "number"), "3")


def _study(name="SimStudy", constraints=(), loads=(), **extra):
    data = {
        "name": name,
        "label": "Study 1 - Static Stress",
        "constraints": list(constraints),
        "loads": list(loads),
    }
    data.update(extra)
    return data


def _item(name, category="constraint", kind="fixed", **extra):
    data = {"name": name, "label": name, "category": category, "kind": kind}
    data.update(extra)
    return data


def _walk(node):
    yield node
    for child in node["children"]:
        yield from _walk(child)


class Tree(unittest.TestCase):
    def test_fusions_study_tree(self):
        tree = s.tree(
            "Bracket",
            "mm",
            [
                _study(
                    constraints=[_item("Fixed1")],
                    loads=[_item("Force1", "load", "force")],
                    gravity=True,
                )
            ],
            "SimStudy",
            [{"name": "Body", "label": "Body1", "visible": True, "in_study": True}],
        )
        labels = [n["label"] for n in _walk(tree)]
        for want in (
            "Document Settings",
            "Named Views",
            "Simulation Model",
            "Bodies",
            "Body1",
            "Study 1 - Static Stress",
            "Study Materials",
            "Load Case 1",
            "Constraints",
            "Loads",
            "Gravity",
            "Contacts",
            "Mesh",
            "Fixed1",
            "Force1",
        ):
            self.assertIn(want, labels)
        self.assertNotIn("Results", labels, "no Results row before a solve")
        study = next(n for n in _walk(tree) if n["kind"] == "sim_study")
        self.assertTrue(study["active"])
        keys = [n["key"] for n in _walk(tree)]
        self.assertEqual(len(keys), len(set(keys)), "keys are unique")

    def test_item_status(self):
        tree = s.tree(
            "D",
            "mm",
            [
                _study(
                    constraints=[
                        _item("A", suppressed=True),
                        _item("B", lost=True),
                        _item("C", unbuilt=True),
                    ]
                )
            ],
            None,
            [],
        )
        nodes = {n["object"]: n for n in _walk(tree) if n["kind"] == "sim_item"}
        self.assertEqual(nodes["A"]["status"], "suppressed")
        self.assertEqual(nodes["B"]["status"], "error")
        self.assertEqual(nodes["C"]["status"], "warning")

    def test_results_out_of_date(self):
        tree = s.tree("D", "mm", [_study(solved=True, out_of_date=True)], "SimStudy", [])
        results = next(n for n in _walk(tree) if n["kind"] == "sim_results")
        self.assertEqual(results["status"], "warning")
        self.assertIn("out of date", results["label"])

    def test_body_left_out(self):
        tree = s.tree(
            "D", "mm", [], None, [{"name": "B", "label": "B", "visible": True, "in_study": False}]
        )
        body = next(n for n in _walk(tree) if n["kind"] == "sim_body")
        self.assertEqual(body["status"], "suppressed")
        self.assertIn("Include in Study", s.menu_for(body))

    def test_icons(self):
        for category, kind in s.ITEM_ICONS:
            self.assertTrue(s.item_icon(category, kind).startswith("sim_"))
        self.assertEqual(s.item_icon("constraint", "new_kind"), "sim_constraints")


class Menus(unittest.TestCase):
    def test_study_menu(self):
        self.assertIn("Activate", s.menu_for({"kind": "sim_study", "active": False}))
        entries = s.menu_for({"kind": "sim_study", "active": True})
        self.assertNotIn("Activate", entries)
        for want in ("Settings", "Clone Study", "Rename", "Delete"):
            self.assertIn(want, entries)

    def test_item_menu(self):
        load = s.menu_for({"kind": "sim_item", "category": "load"})
        self.assertEqual(load[0], "Edit Load")
        self.assertIn("Suppress", load)
        held = s.menu_for({"kind": "sim_item", "category": "constraint", "status": "suppressed"})
        self.assertEqual(held[0], "Edit Constraint")
        self.assertIn("Unsuppress", held)

    def test_every_menu_known(self):
        for kind in s.MENUS:
            self.assertIsInstance(s.menu_for({"kind": kind}), list)


class Glyphs(unittest.TestCase):
    def test_size_follows_the_zoom(self):
        self.assertAlmostEqual(s.glyph_size(0.1), 0.1 * s.GLYPH_PIXELS)
        self.assertEqual(s.glyph_size(0.0), s.GLYPH_MIN_MM)

    def test_perpendicular(self):
        for v in ((0, 0, 1), (1, 0, 0), (0.3, 0.4, 0.5)):
            p = s.perpendicular(v)
            n = s.norm(v)
            self.assertAlmostEqual(sum(a * b for a, b in zip(p, n)), 0.0)
            self.assertAlmostEqual(math.sqrt(sum(c * c for c in p)), 1.0)

    def test_arc_turns_about_the_axis(self):
        pts = s.arc_points((0, 0, 0), (0, 0, 1), 2.0, 90.0, 4, start=(1, 0, 0))
        self.assertAlmostEqual(pts[0][0], 2.0)
        self.assertAlmostEqual(pts[-1][1], 2.0)  # right-hand turn about +Z: x then y
        for p in pts:
            self.assertAlmostEqual(math.hypot(p[0], p[1]), 2.0)
        tangent = s.arc_tangent((0, 0, 1), pts[0], (0, 0, 0))
        self.assertAlmostEqual(tangent[1], 1.0)

    def test_sampling(self):
        self.assertEqual(s.grid_fractions(2), [0.25, 0.75])
        self.assertEqual(s.samples_per_side(10.0, 5.0), 2)
        self.assertEqual(s.samples_per_side(1000.0, 1.0, most=4), 4)
        self.assertEqual(s.samples_per_side(1.0, 5.0), 1)


if __name__ == "__main__":
    unittest.main()

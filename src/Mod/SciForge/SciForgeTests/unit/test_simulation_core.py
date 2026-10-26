# SPDX-License-Identifier: LGPL-2.1-or-later
"""sciforge/simulation_core.py: the rules of Static Stress studies without FreeCAD (study types,
settings, constraint and load options and checks, materials, the safety factor, statistics,
colours, the pre-check)."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import simulation_core as core  # noqa: E402


class StudyTypes(unittest.TestCase):
    def test_only_static_stress_is_available(self):
        available = [k for k, _t, ok in core.STUDY_TYPES if ok]
        self.assertEqual(available, ["static_stress"])
        self.assertTrue(core.study_type_available("static_stress"))
        self.assertFalse(core.study_type_available("modal"))
        self.assertEqual(core.study_type_title("static_stress"), "Static Stress")


class Settings(unittest.TestCase):
    def test_defaults(self):
        s = core.settings()
        self.assertEqual(s["mesh"]["order"], "parabolic")
        self.assertEqual(s["mesh"]["size_pct"], 10.0)
        self.assertFalse(s["gravity"]["on"])
        self.assertEqual(s["safety_basis"], "yield")

    def test_merge_and_repair(self):
        s = core.settings({"mesh": {"size_pct": 5, "order": "cubic"}, "gravity": {"on": "yes"}})
        self.assertEqual(s["mesh"]["size_pct"], 5)
        self.assertEqual(s["mesh"]["order"], "parabolic")  # unknown order: the default
        self.assertFalse(s["gravity"]["on"])  # wrong type: the default
        self.assertEqual(core.settings('{"safety_basis": "ultimate"}')["safety_basis"], "ultimate")
        self.assertEqual(core.settings("not json")["safety_basis"], "yield")
        self.assertEqual(core.settings({"mesh": {"size_pct": 500}})["mesh"]["size_pct"], 50.0)

    def test_element_size(self):
        bbox = (0, 0, 0, 100, 10, 10)
        self.assertAlmostEqual(core.model_size(bbox), math.sqrt(100**2 + 200), 9)
        self.assertAlmostEqual(core.element_size(bbox, 10), core.model_size(bbox) / 10, 9)
        self.assertEqual(core.element_size((0, 0, 0, 0, 0, 0), 10), 0.05)


class Items(unittest.TestCase):
    def test_options_and_descriptions(self):
        opts = core.options("load", "force", {"magnitude": 250, "bogus": 1})
        self.assertEqual(opts["magnitude"], 250)
        self.assertNotIn("bogus", opts)
        self.assertEqual(core.describe("load", "force", opts), "Force 250 N")
        self.assertEqual(core.describe("load", "pressure", {"magnitude": 0.5}), "Pressure 0.5 MPa")
        self.assertEqual(core.describe("constraint", "fixed", {}), "Fixed")
        self.assertEqual(core.describe("constraint", "fixed", {"z": False}), "Fixed (X, Y)")

    def test_checks(self):
        face = ("faces", "plane")
        self.assertEqual(core.check("constraint", "fixed", {}, [face]), [])
        self.assertIn("needs at least one pick", core.check("constraint", "fixed", {}, [])[0])
        self.assertTrue(
            core.check("constraint", "fixed", {"x": False, "y": False, "z": False}, [face])
        )
        self.assertTrue(core.check("load", "pressure", {}, [("edges", None)]))
        self.assertTrue(core.check("load", "force", {"magnitude": 0}, [face]))
        self.assertTrue(
            core.check("load", "force", {"direction": "vector", "vector": [0, 0, 0]}, [face])
        )
        self.assertTrue(core.check("constraint", "pin", {}, [face]))  # a pin needs round faces
        self.assertEqual(core.check("constraint", "pin", {}, [("faces", "cylinder")]), [])
        self.assertIn("Unknown", core.check("load", "torque", {}, [face])[0])

    def test_unit_vector(self):
        self.assertEqual(core.unit_vector([0, 0, -5]), [0.0, 0.0, -1.0])
        with self.assertRaises(core.SimulationError):
            core.unit_vector([0, 0, 0])

    def test_fmt(self):
        self.assertEqual(core.fmt(100.0), "100")
        self.assertEqual(core.fmt(0.000123456), "0.0001235")
        self.assertEqual(core.fmt(-0.0), "0")
        self.assertEqual(core.fmt(12345678.0), "1.235e7")


class Materials(unittest.TestCase):
    def test_problems_and_strength(self):
        steel = {"youngs_mpa": 210000.0, "poisson": 0.3, "yield_mpa": 207.0, "ultimate_mpa": 345.0}
        self.assertEqual(core.material_problems("Steel", steel), [])
        self.assertTrue(core.material_problems("X", {"youngs_mpa": None, "poisson": 0.3}))
        self.assertTrue(core.material_problems("X", {"youngs_mpa": 1.0, "poisson": 0.5}))
        self.assertEqual(core.strength(steel, "yield"), 207.0)
        self.assertEqual(core.strength(steel, "ultimate"), 345.0)
        self.assertIsNone(core.strength({"ultimate_mpa": 345.0}, "yield"))
        self.assertIsNone(core.strength({"yield_mpa": float("nan")}, "yield"))

    def test_fallback_covers_freecad_gaps(self):
        self.assertIn("yield_mpa", core.FALLBACK["Steel-Generic"])
        self.assertIn("poisson", core.FALLBACK["PEEK-Generic"])


class Results(unittest.TestCase):
    def test_safety_factor(self):
        self.assertEqual(core.safety_factors([100.0, 0.0], 200.0, cap=8.0), [2.0, 8.0])
        self.assertEqual(core.safety_factors([1.0], 200.0, cap=8.0), [8.0])
        self.assertTrue(math.isinf(core.safety_factors([0.0], 200.0)[0]))

    def test_stats(self):
        st = core.stats([3.0, float("nan"), -1.0, 7.0, None])
        self.assertEqual(
            (st["min"], st["max"], st["min_index"], st["max_index"]), (-1.0, 7.0, 2, 3)
        )
        self.assertEqual(st["count"], 3)
        self.assertIsNone(core.stats([])["min"])

    def test_colours(self):
        self.assertEqual(core.colour(0, 0, 10), (0.0, 0.0, 1.0))
        self.assertEqual(core.colour(10, 0, 10), (1.0, 0.0, 0.0))
        self.assertEqual(core.colour(10, 0, 10, reverse=True), (0.0, 0.0, 1.0))
        self.assertEqual(core.colour(5, 0, 10), (0.0, 1.0, 0.0))
        self.assertEqual(core.colour(99, 0, 10), (1.0, 0.0, 0.0))  # clamped
        self.assertEqual(core.colour(3, 3, 3), (0.0, 0.0, 1.0))  # flat scale
        self.assertEqual(core.scale_for("safety", 0.5, 300.0), (0.0, core.SAFETY_CAP, True))
        self.assertEqual(core.SAFETY_CAP, 15.0)
        self.assertEqual(core.scale_for("von_mises", 1.0, 9.0), (1.0, 9.0, False))

    def test_deformation(self):
        self.assertEqual(core.deformation_factor("undeformed", 0.2, 100.0), 0.0)
        self.assertEqual(core.deformation_factor("actual", 0.2, 100.0), 1.0)
        self.assertAlmostEqual(core.deformation_factor("adjusted", 0.2, 100.0), 25.0)
        self.assertAlmostEqual(core.deformation_factor("adjusted_5", 0.2, 100.0), 125.0)
        self.assertEqual(core.deformation_factor("adjusted", 0.0, 100.0), 0.0)
        with self.assertRaises(core.SimulationError):
            core.deformation_factor("huge", 1.0, 1.0)

    def test_pin_default_leaves_tangential_free(self):
        self.assertEqual(
            core.options("constraint", "pin"), {"radial": True, "axial": True, "tangential": False}
        )

    def test_legend(self):
        ticks = core.legend_ticks(0.0, 8.0, 5)
        self.assertEqual(ticks, [8.0, 6.0, 4.0, 2.0, 0.0])
        self.assertEqual(core.legend_ticks(None, 1.0), [])
        self.assertEqual(core.legend_ticks(2.0, 2.0), [2.0])

    def test_result_names(self):
        self.assertEqual(core.result_title("safety"), "Safety Factor")
        self.assertEqual(core.result_unit("von_mises"), "MPa")
        self.assertEqual(core.result_unit("displacement"), "mm")


class Precheck(unittest.TestCase):
    STEEL = ("Steel", {"youngs_mpa": 210000.0, "poisson": 0.3, "yield_mpa": 207.0})

    def summary(self, **extra):
        out = {
            "bodies": ["Body"],
            "materials": {"Body": self.STEEL},
            "constraints": [("fixed", 1, False)],
            "loads": [("force", 1, False)],
            "gravity": False,
        }
        out.update(extra)
        return out

    def test_ready(self):
        checks = core.precheck(self.summary())
        self.assertEqual(checks, [])
        self.assertTrue(core.can_solve(checks))

    def test_errors(self):
        self.assertFalse(core.can_solve(core.precheck(self.summary(bodies=[], materials={}))))
        not_held = core.precheck(self.summary(constraints=[("fixed", 1, True)]))
        self.assertFalse(core.can_solve(not_held))
        self.assertIn("Nothing holds", not_held[0][1])
        lost = core.precheck(self.summary(lost=["Force 1"]))
        self.assertIn("Force 1 lost", lost[0][1])
        no_e = core.precheck(self.summary(materials={"Body": ("Odd", {"poisson": 0.3})}))
        self.assertFalse(core.can_solve(no_e))

    def test_warnings(self):
        no_load = core.precheck(self.summary(loads=[]))
        self.assertTrue(core.can_solve(no_load))
        self.assertEqual(no_load[0][0], "warning")
        self.assertEqual(core.precheck(self.summary(loads=[], gravity=True)), [])
        no_yield = core.precheck(
            self.summary(materials={"Body": ("Glass", {"youngs_mpa": 7e4, "poisson": 0.22})})
        )
        self.assertEqual(no_yield[0][0], "warning")
        self.assertIn("safety factor", no_yield[0][1])


if __name__ == "__main__":
    unittest.main()

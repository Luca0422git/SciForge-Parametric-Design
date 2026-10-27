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

    def test_ultimate_basis_in_compression(self):
        # pulled: the 1st principal stress (Fusion); pushed together: the 3rd in size, not 0
        # (a bar crushed at 100 MPa read safety factor 15 on the ultimate basis)
        divided = core.ultimate_stresses([100.0, 0.0, 5.0, -2.0], [0.0, -100.0, -50.0, -8.0])
        self.assertEqual(divided, [100.0, 100.0, 50.0, 8.0])
        sf = core.safety_factors(divided, 345.0, core.SAFETY_CAP)
        self.assertAlmostEqual(sf[1], 3.45)
        self.assertAlmostEqual(sf[2], 6.9)
        nan = core.ultimate_stresses([float("nan")], [-1.0])[0]
        self.assertNotEqual(nan, nan)

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
    STEEL = (
        "Steel",
        {"youngs_mpa": 210000.0, "poisson": 0.3, "yield_mpa": 207.0, "density": 7850.0},
    )

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


class NewKinds(unittest.TestCase):
    def test_every_kind_is_built(self):
        for table in (core.CONSTRAINTS, core.LOADS, core.MESH_CONTROLS):
            for kind, info in table.items():
                self.assertTrue(info["built"], kind)
        self.assertEqual(core.kind_info("mesh", "local")["title"], "Local Mesh Control")
        with self.assertRaises(core.SimulationError):
            core.kind_info("contact", "bonded")

    def test_checks_of_new_kinds(self):
        face = ("faces", "plane")
        round_face = ("faces", "cylinder")
        self.assertEqual(core.check("constraint", "pin", {}, [round_face]), [])
        self.assertTrue(
            core.check(
                "constraint", "pin", {"radial": False, "axial": False}, [round_face]
            )  # holds nothing
        )
        self.assertEqual(core.check("constraint", "frictionless", {}, [round_face]), [])
        self.assertEqual(core.check("constraint", "frictionless", {}, [face]), [])
        self.assertTrue(core.check("constraint", "frictionless", {}, [("edges", None)]))
        self.assertEqual(core.check("constraint", "displacement", {"x": 0.5}, [face]), [])
        self.assertTrue(
            core.check("constraint", "displacement", {"x": None, "y": None, "z": None}, [face])
        )
        self.assertTrue(core.check("constraint", "displacement", {"x": "a"}, [face]))
        self.assertEqual(core.check("load", "moment", {}, [face]), [])
        self.assertTrue(core.check("load", "bearing", {}, [face]))  # round faces only
        self.assertEqual(core.check("load", "bearing", {}, [round_face]), [])
        self.assertEqual(core.check("load", "remote_force", {"point": [1, 2, 3]}, [face]), [])
        self.assertTrue(core.check("load", "remote_force", {"point": [1, 2]}, [face]))
        self.assertTrue(core.check("load", "force", {"direction": "sideways"}, [face]))
        self.assertEqual(core.check("mesh", "local", {"size": 2.0}, [("bodies", None)]), [])
        self.assertTrue(core.check("mesh", "local", {"size": 0}, [face]))

    def test_force_picks(self):
        face, edge, corner = ("faces", "plane"), ("edges", None), ("vertices", None)
        vector = {"direction": "vector", "vector": [0, 0, -1]}
        # along the normal: faces only (the edges or corners of a mix were left out)
        problems = core.check("load", "force", {"direction": "normal"}, [face, edge])
        self.assertTrue(any("no normal" in p for p in problems), problems)
        self.assertTrue(core.check("load", "force", {"direction": "normal"}, [corner]))
        self.assertEqual(core.check("load", "force", {"direction": "normal"}, [face, face]), [])
        # shared: one kind of pick (a face and a corner each got the whole force: twice it)
        problems = core.check("load", "force", vector, [face, corner])
        self.assertTrue(any("one kind" in p for p in problems), problems)
        self.assertTrue(core.check("load", "force", vector, [face, edge]))
        self.assertEqual(core.check("load", "force", vector, [edge, edge]), [])
        # per entity: every pick its own whole force, any mix
        self.assertEqual(
            core.check("load", "force", dict(vector, per_entity=True), [face, edge, corner]), []
        )

    def test_normal_needs_flat_faces(self):
        # a round face's "normal" was the one at the middle of its parameters: an arbitrary
        # direction (a hole pushed sideways)
        flat, round_ = ("faces", "plane"), ("faces", "cylinder")
        problems = core.check("load", "force", {"direction": "normal"}, [flat, round_])
        self.assertTrue(any("flat faces" in p for p in problems), problems)
        self.assertEqual(core.check("load", "force", {"direction": "vector"}, [round_]), [])
        self.assertTrue(core.check("load", "moment", {"direction": "normal"}, [round_, flat]))
        self.assertEqual(core.check("load", "moment", {"direction": "normal"}, [flat, round_]), [])
        self.assertEqual(core.check("load", "moment", {"direction": "vector"}, [round_]), [])

    def test_descriptions(self):
        self.assertEqual(core.describe("constraint", "pin", {}), "Pin")
        self.assertEqual(
            core.describe("constraint", "pin", {"tangential": True}),
            "Pin (radial, axial, tangential)",
        )
        self.assertEqual(core.describe("load", "moment", {"magnitude": 5000}), "Moment 5000 N mm")
        self.assertEqual(core.describe("mesh", "local", {"size": 0.5}), "Local Mesh Control 0.5 mm")
        self.assertEqual(
            core.describe("constraint", "displacement", {"x": None, "z": -0.2}),
            "Prescribed Displacement (Z -0.2 mm)",
        )


class MoreSettings(unittest.TestCase):
    def test_new_defaults_and_clamps(self):
        s = core.settings()
        self.assertFalse(s["remove_rigid"])
        self.assertTrue(s["keep_results"])
        self.assertEqual(s["adaptive"]["level"], "none")
        self.assertEqual(s["mesh"]["adjacent_ratio"], 1.5)
        bad = core.settings(
            {
                "mesh": {"min_pct": 0, "max_turn": 500, "size_mm": -3},
                "adaptive": {"level": "extreme", "passes": 99, "result": "colour"},
                "contact_tolerance": 50,
            }
        )
        self.assertEqual(bad["mesh"]["min_pct"], 1.0)
        self.assertEqual(bad["mesh"]["max_turn"], 90.0)
        self.assertEqual(bad["mesh"]["size_mm"], 0.0)
        self.assertEqual(bad["adaptive"]["level"], "none")
        self.assertEqual(bad["adaptive"]["passes"], 10)
        self.assertEqual(bad["adaptive"]["result"], "von_mises")
        self.assertEqual(bad["contact_tolerance"], 10.0)

    def test_size_as_a_length(self):
        bbox = (0, 0, 0, 100, 10, 10)
        self.assertEqual(core.element_size(bbox, 10, 2.5), 2.5)
        self.assertAlmostEqual(core.element_size(bbox, 10, 0.0), core.model_size(bbox) / 10)

    def test_adaptive_plan(self):
        self.assertIsNone(core.adaptive_plan({"level": "none"}))
        self.assertEqual(core.adaptive_plan({"level": "medium"}), core.ADAPTIVE_LEVELS["medium"])
        custom = {"level": "custom", "passes": 3, "tolerance": 2.0, "portion": 20.0}
        self.assertEqual(core.adaptive_plan(custom), (3, 2.0, 20.0))
        self.assertTrue(core.converged(100.0, 101.0, 2.0))
        self.assertFalse(core.converged(100.0, 110.0, 2.0))
        self.assertFalse(core.converged(None, 1.0, 2.0))


class NodeConstraints(unittest.TestCase):
    def test_fixed_and_conflict(self):
        rows = [(1, "Fixed 1", "spc", (d, 0.0)) for d in range(3)]
        rows.append((1, "Prescribed 1", "spc", (2, 0.5)))
        out = core.node_constraints(rows)
        self.assertEqual(out["spc"], {1: {0: 0.0, 1: 0.0, 2: 0.0}})
        self.assertEqual(out["equations"], [])
        self.assertEqual(out["conflicts"], [(1, "Prescribed 1", "Fixed 1")])

    def test_frictionless_tilted(self):
        n = (1.0, 1.0, 0.0)
        out = core.node_constraints([(7, "F", "eq", n)])
        self.assertEqual(out["spc"], {})
        ((node, terms),) = out["equations"]
        self.assertEqual(node, 7)
        self.assertEqual(terms[0][1], 1.0)  # the dependent term first, coefficient 1
        self.assertEqual(sorted(d for d, _c in terms), [0, 1])
        self.assertAlmostEqual(terms[1][1], 1.0)  # ux + uy = 0

    def test_three_planes_hold_a_corner(self):
        rows = [(3, "a", "eq", (1, 0, 0)), (3, "b", "eq", (0, 1, 0)), (3, "c", "eq", (0, 0, 1))]
        out = core.node_constraints(rows)
        self.assertEqual(out["equations"], [])
        self.assertEqual(out["spc"], {3: {0: 0.0, 1: 0.0, 2: 0.0}})

    def test_axis_plane_becomes_a_value(self):
        # z prescribed 0.2 and a frictionless plane x + z = 0: x must be -0.2
        rows = [(5, "d", "spc", (2, 0.2)), (5, "f", "eq", (1.0, 0.0, 1.0))]
        out = core.node_constraints(rows)
        self.assertAlmostEqual(out["spc"][5][0], -0.2)
        self.assertAlmostEqual(out["spc"][5][2], 0.2)
        self.assertEqual(out["equations"], [])

    def test_pivots_are_distinct_and_free(self):
        # a pin's radial and axial directions on one node plus Fixed in Y
        radial = (0.6, 0.0, 0.8)
        axial = (0.0, 1.0, 0.0)
        rows = [(9, "pin", "eq", radial), (9, "pin", "eq", axial), (9, "fix", "spc", (1, 0.0))]
        out = core.node_constraints(rows)
        dependents = [terms[0][0] for _n, terms in out["equations"]]
        self.assertEqual(len(dependents), len(set(dependents)))
        for d in dependents:
            self.assertNotIn(d, out["spc"].get(9, {}))
        # every equation still holds for a movement that obeys them
        self.assertEqual(out["spc"][9][1], 0.0)

    def test_impossible_request_is_a_conflict(self):
        rows = [(2, "d", "spc", (0, 0.5)), (2, "f", "eq", (1.0, 0.0, 0.0))]
        out = core.node_constraints(rows)
        self.assertEqual(len(out["conflicts"]), 1)

    def test_inp_lines(self):
        self.assertEqual(core.inp_boundaries({4: {0: 0.0, 2: 0.25}}), ["4,1,1,0", "4,3,3,0.25"])
        eq = core.inp_equations([(4, [(0, 1.0), (1, -0.5)])])
        self.assertEqual(eq, ["*EQUATION", "2", "4,1,1,4,2,-0.5"])
        self.assertEqual(core.inp_loads({3: [0.0, -2.5, 0.0]}), ["3,2,-2.5"])


class Distributions(unittest.TestCase):
    PTS = [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0)]

    def sums(self, points, forces):
        total = [sum(f[i] for f in forces) for i in range(3)]
        middle = core.weighted_middle(points, [1.0] * len(points))
        moment = [0.0, 0.0, 0.0]
        for p, f in zip(points, forces):
            r = [p[i] - middle[i] for i in range(3)]
            m = core._cross(r, f)
            moment = [moment[i] + m[i] for i in range(3)]
        return total, moment

    def test_force_and_moment_add_up(self):
        forces = core.distribute(self.PTS, [1.0] * 4, (0.0, 0.0, -8.0), (0.0, 0.0, 6.0))
        total, moment = self.sums(self.PTS, forces)
        for got, want in zip(total + moment, [0, 0, -8, 0, 0, 6]):
            self.assertAlmostEqual(got, want)

    def test_bending_moment_on_a_flat_face(self):
        forces = core.distribute(self.PTS, [1.0] * 4, (0, 0, 0), (2.0, 0.0, 0.0))
        total, moment = self.sums(self.PTS, forces)
        self.assertAlmostEqual(moment[0], 2.0)
        self.assertAlmostEqual(sum(abs(c) for c in total), 0.0)

    def test_a_line_cannot_carry_a_moment_about_itself(self):
        line = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)]
        with self.assertRaises(core.SimulationError):
            core.distribute(line, [1.0, 1.0, 1.0], (0, 0, 0), (1.0, 0.0, 0.0))

    def test_remote_force_lever(self):
        moment = core.remote_moment(self.PTS, [1.0] * 4, (0.0, 0.0, -10.0), (5.0, 0.0, 0.0))
        self.assertEqual([round(c, 9) for c in moment], [0.0, 50.0, 0.0])

    def test_bearing_pushes_only_into_the_loaded_half(self):
        pts, inward = [], []
        for i in range(36):
            a = 2 * math.pi * i / 36
            pts.append((math.cos(a), math.sin(a), 0.0))
            inward.append((math.cos(a), math.sin(a), 0.0))  # a hole: into the material
        forces = core.bearing_forces(pts, [1.0] * 36, inward, (0.0, 1.0, 0.0), 100.0)
        total = [sum(f[i] for f in forces) for i in range(3)]
        self.assertAlmostEqual(total[1], 100.0)
        self.assertAlmostEqual(total[0], 0.0)
        for p, f in zip(pts, forces):
            if p[1] <= 1e-9:
                self.assertEqual(f, [0.0, 0.0, 0.0])
            else:
                self.assertGreaterEqual(core._dot(f, p), 0.0)  # pushes, never pulls
        with self.assertRaises(core.SimulationError):
            core.bearing_forces(pts[:1], [1.0], [(0.0, -1.0, 0.0)], (0.0, 1.0, 0.0), 1.0)

    def test_three_two_one(self):
        nodes = [(1, (0.0, 0.0, 0.0)), (2, (10.0, 0.0, 0.0)), (3, (0.0, 5.0, 0.0)), (4, (5, 2, 1))]
        rows = core.three_two_one(nodes)
        self.assertEqual(len(rows), 6)
        merged = core.node_constraints(rows)
        count = sum(len(v) for v in merged["spc"].values()) + len(merged["equations"])
        self.assertEqual(count, 6)
        with self.assertRaises(core.SimulationError):
            core.three_two_one([(1, (0, 0, 0)), (2, (1, 0, 0)), (3, (2, 0, 0))])


class HeldEnough(unittest.TestCase):
    CORNERS = [(0, 0, 0), (0, 10, 0), (0, 0, 10), (0, 10, 10)]
    AXES = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    def test_a_fixed_face_holds_everything(self):
        rows = [(p, d) for p in self.CORNERS for d in self.AXES]
        self.assertEqual(core.free_modes(rows, (50, 5, 5), 100), [])

    def test_held_along_x_only(self):
        rows = [(p, (1, 0, 0)) for p in self.CORNERS]
        words = [core.describe_free_mode(m) for m in core.free_modes(rows, (50, 5, 5), 100)]
        self.assertEqual(
            sorted(words),
            ["slide along Y", "slide along Z", "turn about an axis along X through (50, 5, 5)"],
        )

    def test_a_pin_lets_it_turn_about_the_pin(self):
        rows = []
        for i in range(8):
            a = i * math.pi / 4
            for y in (0.0, 5.0, 10.0):
                p = (10 + 3 * math.cos(a), y, 5 + 3 * math.sin(a))
                rows.append((p, (math.cos(a), 0.0, math.sin(a))))  # radial
                rows.append((p, (0.0, 1.0, 0.0)))  # axial
        free = core.free_modes(rows, (50, 5, 5), 100)
        self.assertEqual(len(free), 1)
        kind, axis, through = free[0]
        self.assertEqual(kind, "turn")
        self.assertEqual([round(c, 6) for c in axis], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(through[0], 10.0, 6)
        self.assertAlmostEqual(through[2], 5.0, 6)
        # with tangential held too it is held completely
        rows += [((10 + 3 * math.cos(0.3), 5, 5 + 3 * math.sin(0.3)), (0, 0, 1))]
        self.assertEqual(core.free_modes(rows, (50, 5, 5), 100), [])

    def test_jacobi(self):
        values, vectors = core._jacobi([[2.0, 1.0], [1.0, 2.0]])
        self.assertEqual(sorted(round(v, 9) for v in values), [1.0, 3.0])
        for value, vector in zip(values, vectors):
            mv = [2 * vector[0] + vector[1], vector[0] + 2 * vector[1]]
            self.assertAlmostEqual(mv[0], value * vector[0])
            self.assertAlmostEqual(mv[1], value * vector[1])


class SolverText(unittest.TestCase):
    def test_reactions_from_dat(self):
        text = (
            "\n total force (fx,fy,fz) for set SFR1 and time  0.1000000E+01\n\n"
            "       -4.2E-10  8.5E-10  1.007686E+02\n"
        )
        self.assertEqual(core.reactions_from_dat(text), {"SFR1": [-4.2e-10, 8.5e-10, 100.7686]})
        self.assertEqual(core.reactions_from_dat(""), {})

    def test_mesh_quality(self):
        regular = core.tetra_aspect((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1))
        self.assertAlmostEqual(regular, 1.0)
        flat = core.tetra_aspect((0, 0, 0), (10, 0, 0), (0, 10, 0), (3, 3, 0.1))
        self.assertGreater(flat, 10)
        q = core.mesh_quality([1.0, 2.0, 0.5], [1.2, 30.0], 10.0)
        self.assertEqual((q["smallest"], q["largest"], q["worst_aspect"]), (0.5, 2.0, 30.0))
        self.assertEqual(q["over_limit"], 1)


def _tet10(corners):
    """A straight parabolic tetrahedron: its 4 corners and the middles of its 6 edges."""
    mids = [[(corners[a][k] + corners[b][k]) / 2.0 for k in range(3)] for a, b in core.TET10_EDGES]
    return [list(c) for c in corners] + mids


TET = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 4.0)]  # volume 4


class HeldNodeLoads(unittest.TestCase):
    """The loads acting right at held nodes (CalculiX's RF leaves them out of the reaction)."""

    def test_volume_shares(self):
        shares = core.tet_volume_shares(_tet10(TET))
        for value in shares[:4]:
            self.assertAlmostEqual(value, -4.0 / 20.0)
        for value in shares[4:]:
            self.assertAlmostEqual(value, 4.0 / 5.0)
        self.assertAlmostEqual(sum(core.tet_volume_shares(TET)), 4.0)

    def test_face_shares_point_into_the_element(self):
        # face 1 (nodes 1, 2, 3) lies in z = 0, area 3; node 4 is above it: +Z is inward
        shares = dict(core.tet_face_shares(_tet10(TET), 1))
        self.assertEqual(sorted(shares), [1, 2, 3, 5, 6, 7])
        for node in (1, 2, 3):
            self.assertAlmostEqual(core._norm(shares[node]), 0.0)
        for node in (5, 6, 7):
            self.assertAlmostEqual(shares[node][2], 1.0)  # a third of the area each
        linear = dict(core.tet_face_shares(TET, 1))
        self.assertAlmostEqual(sum(v[2] for v in linear.values()), 3.0)

    def test_loads_at_held_nodes_from_an_input(self):
        corners = ["%d, %r, %r, %r" % (i + 1, *p) for i, p in enumerate(_tet10(TET))]
        text = "\n".join(
            ["** a test", "*NODE, NSET=Nall"]
            + corners
            + ["*ELEMENT, TYPE=C3D10, ELSET=Evolumes", "7, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10"]
            + ["*ELSET, ELSET=Eall", "Evolumes", "*ELSET,ELSET=M1Solid", "Eall"]
            + ["*MATERIAL, NAME=M1", "*ELASTIC", "200000, 0.3", "*DENSITY", "7.9E-09"]
            + ["*SOLID SECTION, ELSET=M1Solid, MATERIAL=M1", "*STEP", "*STATIC"]
            + ["*DLOAD", "Eall,GRAV,9806.65,0,0,-1", "*DLOAD", "7,P1,2.0"]
            + ["*CLOAD", "5,3,-1.5", "1,1,2.0", "*NSET,NSET=SFR1", "5, 6, 7", "*END STEP"]
        )
        at = core.inp_loads_at(text, {5, 6, 7, 1})
        weight = 7.9e-9 * 9806.65 * 4.0
        # node 5: pressure 2 MPa x 1 mm2 into the element (+Z), the CLOAD, its weight share
        self.assertAlmostEqual(at[5][2], 2.0 - 1.5 - weight / 5.0)
        self.assertAlmostEqual(at[6][2], 2.0 - weight / 5.0)
        self.assertAlmostEqual(at[1][0], 2.0)
        self.assertAlmostEqual(at[1][2], weight / 20.0)  # (a corner's share is negative)
        # node 4, the corner above the face: only its weight share (a corner's is negative)
        self.assertAlmostEqual(core.inp_loads_at(text, {4})[4][2], weight / 20.0)

    def test_forces_from_dat(self):
        dat = "\n".join(
            [
                " forces (fx,fy,fz) for set SFRHELD and time  0.1000000E+01",
                "",
                "         5  1.000000E+00 -2.000000E+00  3.000000E-01",
                "         6  0.000000E+00  0.000000E+00  1.000000E+00",
                "",
                " total force (fx,fy,fz) for set SFR1 and time  0.1000000E+01",
                "",
                "        1.000000E+00 -2.000000E+00  1.300000E+00",
            ]
        )
        self.assertEqual(
            core.node_forces_from_dat(dat, "SFRHELD"), {5: [1.0, -2.0, 0.3], 6: [0.0, 0.0, 1.0]}
        )
        self.assertEqual(core.node_forces_from_dat(dat, "SFR1"), {})

    def test_reactions_split_node_by_node(self):
        x, y, z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        held = {
            1: [("Fixed 1", x), ("Fixed 1", y), ("Fixed 1", z)],
            # an edge node: Fixed 1 holds X, Y and Z, a Frictionless plane (normal Y) holds Y
            2: [("Fixed 1", x), ("Fixed 1", y), ("Fixed 1", z), ("Plane", y)],
            3: [("Plane", y)],
        }
        forces = {1: [1.0, 2.0, 3.0], 2: [4.0, 6.0, 5.0], 3: [0.5, 7.0, 0.0]}
        # node 3 is free along X and Z: its force there is the load acting at it
        applied = {3: [0.5, 1.0, 0.0], 1: [0.0, 0.0, -1.0]}
        out = core.split_reactions(forces, applied, held)
        self.assertEqual([round(v, 9) for v in out["Fixed 1"]], [5.0, 5.0, 9.0])
        self.assertEqual([round(v, 9) for v in out["Plane"]], [0.0, 9.0, 0.0])
        # nothing counted twice: the two add up to every node's force less its loads
        total = [out["Fixed 1"][k] + out["Plane"][k] for k in range(3)]
        self.assertEqual([round(v, 9) for v in total], [5.0, 14.0, 9.0])
        # a tilted plane and an axis at one node: the force split along each
        tilted = (0.0, math.sqrt(0.5), math.sqrt(0.5))
        out = core.split_reactions({7: [0.0, 1.0, 3.0]}, {}, {7: [("A", z), ("B", tilted)]})
        self.assertAlmostEqual(out["B"][1], 1.0)
        self.assertAlmostEqual(out["B"][2], 1.0)
        self.assertAlmostEqual(out["A"][2], 2.0)


class ProgramText(unittest.TestCase):
    def test_solver_failures_become_sentences(self):
        self.assertIn("not held enough", core.solver_failure(" *ERROR: zero pivot in node 12"))
        self.assertIn("distorted", core.solver_failure("nonpositive jacobian determinant"))
        self.assertIn("memory", core.solver_failure("allocation of 9 GB failed"))
        self.assertIn("same corner", core.solver_failure("*ERROR in mpc: dependent dof"))
        other = core.solver_failure("a\nb\nc\nd\ne\nsomething odd")
        self.assertTrue(other.startswith("CalculiX could not solve the study."))
        self.assertIn("something odd", other)
        self.assertNotIn("a b", other)  # the last four lines only

    def test_a_stop_without_a_reason_is_tried_again_with_spooles(self):
        # (Windows' CalculiX stopped after reading the input of two small cantilevers)
        silent = " data points in all amplitudes: 2\n print requests: 2\n property cards: 0\n"
        self.assertTrue(core.solver_unexplained(silent))
        self.assertTrue(core.solver_unexplained(""))
        self.assertFalse(core.solver_unexplained(" *ERROR: zero pivot in node 12"))
        self.assertFalse(core.solver_unexplained("nonpositive jacobian determinant"))
        inp = "*STEP\r\n*STATIC\r\n1.0,1.0,1e-05,1.0\r\n*END STEP\r\n"
        text, changed = core.with_spooles(inp)
        self.assertTrue(changed)
        self.assertEqual(
            text, "*STEP\r\n*STATIC, SOLVER=SPOOLES\r\n1.0,1.0,1e-05,1.0\r\n*END STEP\r\n"
        )
        text, changed = core.with_spooles("*Static, DIRECT\n1,1\n")
        self.assertEqual((text, changed), ("*Static, DIRECT, SOLVER=SPOOLES\n1,1\n", True))
        # a solver already named, or no static step: left as it is
        named = "*STATIC, SOLVER=PASTIX\n"
        self.assertEqual(core.with_spooles(named), (named, False))
        self.assertEqual(core.with_spooles("*FREQUENCY\n10\n"), ("*FREQUENCY\n10\n", False))

    def test_mesh_quality_note(self):
        fine = {"worst_aspect": 15.2, "over_limit": 6, "elements": 73561}
        self.assertIsNone(core.mesh_quality_note(fine, 10))
        thin = {"worst_aspect": 131.3, "over_limit": 40, "elements": 2400}
        note = core.mesh_quality_note(thin, 10)
        self.assertIn("40 of the 2400", note)
        self.assertIn("131", note)
        rod = {"worst_aspect": 16.4, "over_limit": 56, "elements": 67}  # (bends within 2 %)
        self.assertIsNone(core.mesh_quality_note(rod, 10))
        self.assertIsNone(core.mesh_quality_note({}, 10))

    def test_thin_wall_note(self):
        # a 2.5 mm plate at the default size: elements 5 times its thickness (10 % too stiff)
        note = core.thin_wall_note([("Plate", 2.38, 12.17), ("Block", 4.76, 8.42)])
        self.assertIn("Plate's walls are about 2.4 mm thick", note)
        self.assertNotIn("Block", note)  # a solid block: 2V/A is a third of its size
        self.assertIsNone(core.thin_wall_note([("Beam", 4.76, 8.42), ("Ball", 2.0, 5.09)]))
        self.assertIsNone(core.thin_wall_note([]))

    def test_gmsh_errors(self):
        out = (
            "Info    : Meshing 2D...\n"
            "Error   : Invalid boundary mesh (overlapping facets) on surface 12 surface 15\n"
            "Warning : something\n"
            "Error   : No elements in volume 1\n"
        )
        errors, numbers = core.gmsh_errors(out)
        self.assertEqual(len(errors), 2)
        self.assertEqual(numbers, [12, 15])
        self.assertEqual(core.gmsh_errors(""), ([], []))
        summary = (
            "Error   : PLC Error:  A segment and a facet intersect at point\n"
            "Error   : Invalid boundary mesh (segment-facet intersection) on surface 4\n"
            "Error   : ------------------------------\n"
            "Error   : Mesh generation error summary\n"
            "Error   :     2 errors\n"
            "Error   : Check the full log for details\n"
        )
        errors, numbers = core.gmsh_errors(summary)
        self.assertEqual(len(errors), 2)  # (the summary lines are no reasons)
        self.assertEqual(numbers, [4])
        self.assertTrue(core.mesh_crossed_itself(summary))
        self.assertFalse(core.mesh_crossed_itself("Error   : No elements in volume 1"))

    def test_contact_types(self):
        self.assertTrue(core.contact_type_available("bonded"))
        self.assertFalse(core.contact_type_available("sliding"))
        self.assertEqual(len(core.CONTACT_TYPES), 6)
        self.assertIn("nonlinear", core.CONTACT_NOT_AVAILABLE)


class MorePrecheck(unittest.TestCase):
    STEEL = (
        "Steel",
        {"youngs_mpa": 210000.0, "poisson": 0.3, "yield_mpa": 207.0, "density": 7850.0},
    )

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

    def test_gravity_needs_density(self):
        odd = ("Odd", {"youngs_mpa": 1000.0, "poisson": 0.3, "yield_mpa": 10.0})
        checks = core.precheck(self.summary(materials={"Body": odd}, gravity=True))
        self.assertFalse(core.can_solve(checks))
        self.assertIn("density", checks[0][1])

    def test_remove_rigid_body_modes(self):
        free = core.precheck(self.summary(constraints=[], remove_rigid=True))
        self.assertTrue(core.can_solve(free))
        self.assertIn("balance", free[0][1])
        both = core.precheck(self.summary(remove_rigid=True))
        self.assertTrue(core.can_solve(both))
        self.assertIn("reactions may be wrong", both[0][1])
        loose = core.precheck(self.summary(loose=["Body2"], remove_rigid=True))
        self.assertTrue(core.can_solve(loose))

    def test_linear_elements_warned(self):
        checks = core.precheck(self.summary(order="linear"))
        self.assertTrue(core.can_solve(checks))
        self.assertTrue(any("Linear elements" in t for _l, t in checks))
        self.assertFalse(
            any("Linear elements" in t for _l, t in core.precheck(self.summary(order="parabolic")))
        )

    def test_loose_overlaps_twice(self):
        checks = core.precheck(self.summary(loose=["Body2"]))
        self.assertFalse(core.can_solve(checks))
        self.assertIn("Body2", checks[0][1])
        checks = core.precheck(self.summary(overlaps=[("A", "B", 12.5)], twice=[("F1", "F2")]))
        self.assertTrue(core.can_solve(checks))
        self.assertIn("A and B overlap", checks[0][1])
        self.assertIn("F1 and F2", checks[1][1])


try:
    import numpy  # noqa: F401

    HAVE_NUMPY = True
except ImportError:  # (FreeCAD always has it; a bare Python may not)
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "numpy is not installed")
class CurvedElements(unittest.TestCase):
    """Curved parabolic tetrahedra that turn inside out are made straight-sided."""

    @staticmethod
    def tet10(corners):
        import numpy as np

        pts = [list(map(float, c)) for c in corners]
        for a, b in core.TET10_EDGES:
            pts.append([(pts[a][i] + pts[b][i]) / 2.0 for i in range(3)])
        return np.array(pts)

    def test_straight_and_curved(self):
        import numpy as np

        xyz = self.tet10([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)])
        rows = np.arange(10).reshape(1, 10)
        self.assertAlmostEqual(core.tet10_distortion(xyz, rows)[0], 1.0, places=9)
        # a gently curved edge (the mid-side node of 2-3 pushed out a little): still good
        xyz[5] += [0.05, 0.05, 0.0]
        self.assertGreater(core.tet10_distortion(xyz, rows)[0], core.DISTORTION_LIMIT)
        # pushed through the opposite corner: inside out
        xyz[5] = [-0.6, -0.6, 0.0]
        self.assertLess(core.tet10_distortion(xyz, rows)[0], 0.0)

    def test_straighten_one_and_its_neighbour(self):
        import numpy as np

        # two tetrahedra sharing the face 1-2-3: the first one's edge 2-3 is pushed inside out
        first = self.tet10([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)])
        second = self.tet10([(1, 1, 1), (1, 0, 0), (0, 0, 1), (0, 1, 0)])
        xyz = np.vstack([first, second])
        rows = np.array([list(range(10)), list(range(10, 20))])
        # the second shares the first's mid-side node of the edge (1, 0, 0)-(0, 1, 0): its
        # own corners 2 and 4 (CalculiX's node 9)
        rows[1][8] = 5
        self.assertGreater(core.tet10_distortion(xyz, rows)[1], 0.99)
        xyz[5] = [-0.6, -0.6, 0.0]
        before = core.tet10_distortion(xyz, rows)
        self.assertLess(before[0], 0.0)
        moved, straightened, left = core.straighten_tets(xyz, rows)
        self.assertEqual((straightened, left), (1, 0))
        self.assertIn(5, moved)
        self.assertEqual(list(xyz[5]), [0.5, 0.5, 0.0])
        after = core.tet10_distortion(xyz, rows)
        self.assertTrue(all(after > 0.99), after)

    def test_corners_inside_out_are_left(self):
        import numpy as np

        xyz = self.tet10([(0, 0, 0), (0, 1, 0), (1, 0, 0), (0, 0, 1)])  # mirrored order
        rows = np.arange(10).reshape(1, 10)
        self.assertEqual(core.tet10_distortion(xyz, rows)[0], -np.inf)
        moved, straightened, left = core.straighten_tets(xyz, rows)
        self.assertEqual((moved, straightened, left), ([], 0, 1))


if __name__ == "__main__":
    unittest.main()

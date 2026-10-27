# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline's words (sciforge/rebuild_core.py): what a region of missing / extra
material looks like, equal regions grouped, faces in words, the verdict, the chat message.
Plain Python (no FreeCAD): the numbers are what rebuild.region_facts measures."""

import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sciforge import rebuild_core as core  # noqa: E402


def plane(normal, area=10.0):
    return {"type": "plane", "area": area, "normal": list(normal)}


def cylinder(radius, length, convex=True, axis=(0, 0, 1), point=(10, 10, 5), span=None):
    return {
        "type": "cylinder",
        "area": (span or 2 * math.pi) * radius * length,
        "radius": radius,
        "length": length,
        "axis": list(axis),
        "point": list(point),
        "span": span or 2 * math.pi,
        "convex": convex,
    }


def hole_region(x=10.0, y=10.0, r=3.0, depth=10.0):
    return {
        "volume": math.pi * r * r * depth,
        "center": [x, y, depth / 2],
        "bbox": [x - r, y - r, 0.0, x + r, y + r, depth],
        "faces": [
            cylinder(r, depth, True, (0, 0, -1), (x, y, depth / 2)),
            plane((0, 0, 1), math.pi * r * r),
            plane((0, 0, -1), math.pi * r * r),
        ],
    }


def fillet_region(r=3.0, length=10.0):
    return {
        "volume": (1 - math.pi / 4) * r * r * length,
        "center": [r / 4, r / 4, length / 2],
        "bbox": [0, 0, 0, r, r, length],
        "faces": [
            cylinder(r, length, False, (0, 0, 1), (r, r, length / 2), span=math.pi / 2),
            plane((-1, 0, 0), r * length),
            plane((0, -1, 0), r * length),
            plane((0, 0, 1), r * r * (1 - math.pi / 4)),
            plane((0, 0, -1), r * r * (1 - math.pi / 4)),
        ],
    }


class Words(unittest.TestCase):
    def test_numbers_as_a_person_writes_them(self):
        self.assertEqual(core.num(6.0), "6")
        self.assertEqual(core.num(2.5), "2.5")
        self.assertEqual(core.num(-0.0), "0")
        self.assertEqual(core.about(5.99998), "6")
        self.assertEqual(core.about(2.4996), "2.5")
        self.assertEqual(core.about(12.34), "12.3")
        self.assertEqual(core.about(0.1234), "0.123")

    def test_points_seen_along_an_axis(self):
        self.assertEqual(core.point_text([10, 20, 5], [0, 0, -1]), "(10, 20)")
        self.assertEqual(core.point_text([10, 20, 5], [0, 1, 0]), "(10, 5)")
        self.assertEqual(core.point_text([10, 20, 5], [1, 1, 0]), "(10, 20, 5)")
        self.assertEqual(core.axis_name([0, 0, -1]), "Z")
        self.assertEqual(core.direction_text([0, -1, 0]), "-Y")

    def test_mesh_tolerance_follows_the_size_within_limits(self):
        self.assertAlmostEqual(core.mesh_tolerance(72.0), 0.144)
        self.assertEqual(core.mesh_tolerance(1.0), core.MESH_TOL_MIN)
        self.assertEqual(core.mesh_tolerance(1e6), core.MESH_TOL_MAX)


class Regions(unittest.TestCase):
    def test_a_hole_not_cut_yet(self):
        found = core.classify_region(hole_region(), "extra")
        self.assertEqual(found["kind"], "cylinder")
        self.assertAlmostEqual(found["diameter"], 6.0)
        self.assertAlmostEqual(found["depth"], 10.0)
        self.assertEqual(found["looks_like"], "a round hole about 6 mm across, 10 deep")

    def test_a_boss_not_built_yet(self):
        found = core.classify_region(hole_region(r=4, depth=8), "missing")
        self.assertEqual(found["looks_like"], "a round boss (pin) about 8 mm across, 8 tall")

    def test_a_counterbore(self):
        region = hole_region()
        region["faces"].append(cylinder(5.0, 3.0, True, (0, 0, -1), (10, 10, 8.5)))
        region["volume"] += math.pi * 25 * 3.0
        found = core.classify_region(region, "extra")
        self.assertEqual(found["kind"], "stepped_cylinder")
        self.assertIn("counterbore", found["looks_like"])
        self.assertIn("10 mm across 3 deep", found["looks_like"])

    def test_a_rolled_back_marker_said_for_a_person(self):
        said = core.person_words(
            "The history marker is rolled back: 2 step(s) of B (Sketch1, Extrude1) are not "
            "computed, so the rebuild cannot be compared as it is. Move the marker to the end "
            "(roll_timeline with to: end; in the window, drag the history marker to the end of "
            "the timeline), then try again."
        )
        self.assertNotIn("roll_timeline", said)
        self.assertIn("(drag the history marker to the end of the timeline)", said)

    def test_a_drill_point_and_a_chamfered_rim(self):
        # (beta 3 QA: a hole with a chamfered rim was "a round hole ... with a pointed
        # (drilled) end")
        def cone(r_min, r_max):
            return {
                "type": "cone",
                "area": 5.0,
                "axis": [0, 0, -1],
                "point": [10, 10, 0],
                "convex": True,
                "r_min": r_min,
                "r_max": r_max,
            }

        pointed = hole_region()
        pointed["faces"].append(cone(0.0, 3.0))
        pointed["volume"] += math.pi * 9 * 1.0 / 3
        found = core.classify_region(pointed, "extra")
        self.assertIn("with a pointed (drilled) end", found["looks_like"])
        rim = hole_region()
        rim["faces"].append(cone(3.0, 3.5))
        rim["volume"] += 0.5
        found = core.classify_region(rim, "extra")
        self.assertIn("with a widened rim (a countersink or a chamfer)", found["looks_like"])
        self.assertNotIn("pointed", found["looks_like"])

    def test_a_hole_of_a_mesh(self):
        n, r, depth = 32, 4.0, 8.0
        area = n / 2.0 * r * r * math.sin(2 * math.pi / n)
        sides = [
            plane(
                (math.cos(2 * math.pi * (i + 0.5) / n), math.sin(2 * math.pi * (i + 0.5) / n), 0.0)
            )
            for i in range(n)
        ]
        region = {
            "volume": area * depth,
            "center": [15, 20, 4],
            "bbox": [11, 16, 0, 19, 24, 8],
            "faces": sides + [plane((0, 0, 1)), plane((0, 0, -1))],
        }
        found = core.classify_region(region, "extra")
        self.assertEqual(found["kind"], "cylinder")
        self.assertTrue(found["faceted"])
        self.assertEqual(found["diameter"], 8.0)
        self.assertEqual(found["ends"], [[15, 20, 8], [15, 20, 0]])
        self.assertIn("a round hole about 8 mm across, 8 deep (32 facets", found["looks_like"])

    def test_a_rounded_edge(self):
        found = core.classify_region(fillet_region(), "extra")
        self.assertEqual(found["kind"], "fillet")
        self.assertAlmostEqual(found["radius"], 3.0)
        self.assertEqual(found["looks_like"], "a rounded edge, radius about 3")
        inside = core.classify_region(fillet_region(2.0), "missing")
        self.assertIn("inside corner", inside["looks_like"])

    def test_a_chamfered_edge(self):
        region = {
            "volume": 0.5 * 1 * 1 * 30,
            "center": [0.3, 0.3, 15],
            "bbox": [0, 0, 0, 1, 1, 30],
            "faces": [plane((1, 0, 0))] * 5,
        }
        found = core.classify_region(region, "extra")
        self.assertEqual(found["kind"], "chamfer")
        self.assertEqual(found["looks_like"], "a chamfered edge, about 1 (30 mm long)")

    def test_a_block_and_a_layer(self):
        block = {
            "volume": 10 * 5 * 3,
            "center": [5, 2.5, 1.5],
            "bbox": [0, 0, 0, 10, 5, 3],
            "faces": [plane((1, 0, 0))] * 6,
        }
        found = core.classify_region(block, "extra")
        self.assertEqual(found["kind"], "block")
        self.assertIn("10 x 5 x 3", found["looks_like"])
        layer = dict(block, volume=60 * 40 * 2, bbox=[0, 0, 10, 60, 40, 12])
        found = core.classify_region(layer, "extra")
        self.assertEqual(found["kind"], "layer")
        self.assertEqual(found["thin_axis"], "z")
        self.assertIn("2 thick", found["looks_like"])

    def test_anything_else_is_said_by_its_size(self):
        odd = {
            "volume": 100.0,
            "center": [0, 0, 0],
            "bbox": [0, 0, 0, 10, 10, 10],
            "faces": [{"type": "bspline", "area": 1.0}],
        }
        found = core.classify_region(odd, "missing")
        self.assertEqual(found["kind"], "other")
        self.assertIn("10 x 10 x 10", found["looks_like"])


class Groups(unittest.TestCase):
    def regions(self):
        out = []
        for x, y in ((10, 10), (50, 10), (10, 30), (50, 30)):
            facts = hole_region(x, y)
            out.append(
                {
                    "side": "extra",
                    "volume": facts["volume"],
                    "center": facts["center"],
                    "shape": core.classify_region(facts, "extra"),
                }
            )
        for _ in range(4):
            facts = fillet_region()
            out.append(
                {
                    "side": "extra",
                    "volume": facts["volume"],
                    "center": facts["center"],
                    "shape": core.classify_region(facts, "extra"),
                }
            )
        return out

    def test_equal_holes_are_one_group_and_fillets_come_last(self):
        groups = core.group_regions(self.regions(), reference_volume=22791.77)
        self.assertEqual([g["kind"] for g in groups], ["cylinder", "fillet"])
        self.assertEqual(groups[0]["count"], 4)
        text = core.group_text(groups[0])
        self.assertEqual(
            text,
            "4 round holes about 6 mm across, 10 deep (along Z) are not cut yet, at (10, 10), "
            "(50, 10), (10, 30), (50, 30)",
        )
        self.assertEqual(
            core.group_text(groups[1]),
            "4 rounded edges of radius about 3 are still sharp in the rebuild",
        )

    def test_a_big_difference_comes_first(self):
        regions = self.regions()
        regions.append(
            {
                "side": "missing",
                "volume": 5000.0,
                "center": [0, 0, 0],
                "shape": {"kind": "block", "size": [50, 10, 10], "looks_like": "a block"},
            }
        )
        groups = core.group_regions(regions, reference_volume=22791.77)
        self.assertEqual(groups[0]["kind"], "block")

    def test_the_verdict_says_what_to_do_next(self):
        groups = core.group_regions(self.regions(), reference_volume=22791.77)
        groups[1]["fix_at"] = 1
        groups[1]["regions"][0]["fix"] = {"tool": "fillet"}
        result = {
            "match": 0.949657,
            "faces": {"reference": 14, "matched": 6, "unmatched_rebuilt": []},
            "groups": groups,
        }
        text = core.verdict(result)
        self.assertTrue(text.startswith("Match 0.9497 (1 is identical); 6 of 14 faces"), text)
        self.assertIn("4 round holes", text)
        self.assertIn("the fillet call is ready in groups[1].fix", text)
        self.assertTrue(text.endswith("then compare_to_reference again."), text)
        self.assertLess(text.index("round holes"), text.index("rounded edges"))

    def test_done_and_empty(self):
        done = core.verdict({"match": 1.0, "done": True, "faces": {"reference": 14}})
        self.assertEqual(
            done,
            "Done: the rebuilt part matches the original (match 1, all 14 faces matched). "
            "Call finish_rebuild.",
        )
        empty = core.verdict({"empty": True, "faces": {}})
        self.assertIn("still empty", empty)
        self.assertIn("describe_reference", empty)

    def test_only_faces_left(self):
        result = {
            "match": 0.99995,
            "faces": {
                "reference": 14,
                "matched": 13,
                "unmatched_reference": [{"describe": "a round hole face 6 mm across"}],
                "unmatched_rebuilt": [],
            },
            "groups": [],
        }
        text = core.verdict(result)
        self.assertIn("1 face of the original is not matched yet", text)
        self.assertIn("a round hole face 6 mm across", text)

    def test_the_verdict_for_a_person(self):
        groups = core.group_regions(self.regions(), reference_volume=22791.77)
        groups[1]["fix_at"] = 1
        groups[1]["regions"][0]["fix"] = {"tool": "fillet"}
        result = {
            "match": 0.949657,
            "faces": {"reference": 14, "matched": 6, "unmatched_rebuilt": []},
            "groups": groups,
        }
        text = core.person_words(core.verdict(result))
        self.assertTrue(text.startswith("Next: 4 round holes"), text)  # (the window has the match)
        self.assertNotIn("groups[", text)
        self.assertTrue(text.endswith("Fix that, then Compare Again."), text)
        done = core.verdict({"match": 1.0, "done": True, "faces": {"reference": 14}})
        self.assertTrue(core.person_words(done).endswith("Press Finish Rebuild..."))
        empty = core.person_words(core.verdict({"empty": True, "faces": {}}))
        self.assertEqual(
            empty,
            "The rebuilt body is still empty: build the base shape first, then Compare Again.",
        )
        for refusal in (
            "The rebuilt body of Plate is gone (deleted?): undo that, or call start_rebuild on "
            "Plate again for a new one.",
            "Plate is already being rebuilt in Plate (rebuilt) (reference R): carry on there, or "
            "finish_rebuild first.",
            "Plate (rebuilt) is still empty: build the part first (describe_reference gives the "
            "plan).",
        ):
            self.assertNotIn("_", core.person_words(refusal))
        self.assertEqual(core.person_words(None), "")

    def test_sampled_volumes_are_said_as_such(self):
        result = {
            "match": 0.9505,
            "method": "sampled",
            "volume": {"missing": 0.0, "extra": 1160.2},
            "faces": {
                "reference": 10,
                "matched": 6,
                "unmatched_reference": [{"describe": "a round hole face 6 mm across"}],
                "unmatched_rebuilt": [],
            },
            "groups": [],
        }
        text = core.verdict(result)
        self.assertIn("could not be listed", text)
        self.assertIn("about 1160.2 mm3 is extra", text)
        self.assertIn("a round hole face 6 mm across", text)
        self.assertNotIn("No material differs", text)

    def test_size_notes(self):
        notes = core.size_notes([0, 0, 0, 60, 40, 10], [0, 0, 0, 60, 40, 12])
        self.assertEqual(notes, ["it is 2 mm taller along Z (0 to 12; the original 0 to 10)"])
        shifted = core.size_notes([0, 0, 0, 60, 40, 10], [5, 0, 0, 65, 40, 10])
        self.assertEqual(shifted, ["it is shifted 5 mm along X (5 to 65; the original 0 to 60)"])


class FacesAndMessage(unittest.TestCase):
    def test_faces_in_words(self):
        flat = core.describe_face(
            {
                "type": "plane",
                "area_mm2": 2400,
                "normal": [0, 0, 1],
                "bbox_mm": [0, 0, 10, 60, 40, 10],
            }
        )
        self.assertEqual(flat, "a flat face 60 x 40 facing +Z at z = 10 (2400 mm2)")
        hole = core.describe_face(
            {
                "type": "cylinder",
                "area_mm2": 188.5,
                "radius_mm": 3,
                "axis": [0, 0, 1],
                "axis_point_mm": [10, 30, 0],
                "concave": True,
            }
        )
        self.assertEqual(hole, "a round hole face 6 mm across along Z at (10, 30) (188.5 mm2)")

    def test_the_chat_message(self):
        text = core.chat_message("Bracket")
        self.assertIn('Rebuild the body "Bracket" with a timeline', text)
        self.assertIn('"Bracket (rebuilt)"', text)
        for word in (
            "recipes/reverse-engineer.md",
            "describe_reference",
            "compare_to_reference",
            "finish_rebuild",
        ):
            self.assertIn(word, text)
        self.assertIn("mesh body", core.chat_message("Scan", mesh=True))


class FollowTest(unittest.TestCase):
    """Finish moves what used the original onto the rebuild (beta 3 QA): the links' paths
    and element names."""

    MAP = {"Face7": "Face3", "Edge12": "Edge9"}

    def element_for(self, name):
        return self.MAP.get(name)

    def test_split_sub(self):
        self.assertEqual(core.split_sub("Body001.Face7"), (["Body001"], "Face7"))
        self.assertEqual(core.split_sub("Face7"), ([], "Face7"))
        self.assertEqual(core.split_sub("Body001."), (["Body001"], ""))
        self.assertEqual(
            core.split_sub("Body001.;#7:1;:G0;XTR;:H1:7,F.Face7"), (["Body001"], "Face7")
        )
        self.assertEqual(core.split_sub(""), ([], ""))

    def test_a_path_through_the_original(self):
        names = {"Body001": "Body003", "BaseFeature": ""}
        self.assertEqual(
            core.rewrite_sub("Body001.Face7", names, self.element_for), ("Body003.Face3", True)
        )
        # a step inside the original is dropped: the rebuilt body holds the whole shape
        self.assertEqual(
            core.rewrite_sub("Body001.BaseFeature.Edge12", names, self.element_for),
            ("Body003.Edge9", True),
        )
        # a nested component on the way stays
        self.assertEqual(
            core.rewrite_sub("Part2.Body001.Face7", names, self.element_for),
            ("Part2.Body003.Face3", True),
        )
        # the whole body (no element)
        self.assertEqual(core.rewrite_sub("Body001.", names, self.element_for), ("Body003.", True))
        # an element the rebuild has not: it cannot follow
        self.assertEqual(core.rewrite_sub("Body001.Face1", names, self.element_for), (None, True))
        # an object of the original with no counterpart (its sketch): it cannot follow
        names_sketch = dict(names, Sketch=None)
        self.assertEqual(
            core.rewrite_sub("Body001.Sketch.Edge12", names_sketch, self.element_for), (None, True)
        )
        # a path that does not reach the original stays as it is
        self.assertEqual(
            core.rewrite_sub("Body002.Face7", names, self.element_for), ("Body002.Face7", False)
        )

    def test_links_straight_to_the_original(self):
        self.assertEqual(
            core.rewrite_direct(["Face7", "Edge12"], self.element_for), ["Face3", "Edge9"]
        )
        self.assertEqual(core.rewrite_direct([""], self.element_for), [""])
        self.assertIsNone(core.rewrite_direct(["Face7", "Vertex1"], self.element_for))

    def test_keys_between(self):
        keys = core.keys_between(3, 5.0, 7.0)
        self.assertEqual(len(keys), 3)
        self.assertTrue(all(5.0 < k < 7.0 for k in keys))
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(core.keys_between(0, 5.0, 7.0), [])
        keys = core.keys_between(2, 5.0, None)  # nothing after the original
        self.assertTrue(all(5.0 < k < 6.0 for k in keys))


if __name__ == "__main__":
    unittest.main()

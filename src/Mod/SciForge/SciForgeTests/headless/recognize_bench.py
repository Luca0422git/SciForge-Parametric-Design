# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline benchmark (builder at-recognize, beta 3): how well recognize.describe() reads a
part that has no timeline, and whether its plan builds the part again.

For each model (golden models of SciForgeTests/golden/models, plus a few parts written here in
the same step language: a stepped shaft, a knob, a bracket with holes in two directions...):

  1. build it in real FreeCAD (the golden builder: the same code as the AI tools);
  2. export its solid to STEP and import it back as a featureless body
     (sciforge/step_import.import_file, what File > Open does);
  3. describe() that body's solid;
  4. check what was found against what the model's steps made (base kind, hole diameters,
     fillet radii, chamfer distances, patterns);
  5. run the plan through the headless AI executor (sciforge/ai/headless.py: the same
     executor the AI bridge uses) in a new design, giving each step the id an earlier step
     really got ("uses");
  6. compare the rebuilt solid with the original: volume within 0.1 % and every face of the
     original matched by a face of the rebuild (same kind, area and place).

Then 3 meshes (STL of simple golden models) through sciforge/recognize_mesh.py.

    freecadcmd -c "from SciForgeTests.headless import recognize_bench; recognize_bench.main()"

tools/sciforge/run_tests.sh runs it with --only recognize (and --only base). It writes
recognize-report.json / .md to SCIFORGE_RECOGNIZE_OUT (default: SCIFORGE_HEADLESS_OUT, else
FreeCAD's user data folder); SCIFORGE_RECOGNIZE_FILTER runs only the models whose id contains
that text.
"""

import copy
import json
import math
import os
import platform
import re
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(os.path.dirname(HERE), "golden", "models")

VOLUME_TOL = 1e-3  # 0.1 %
SPEED_LIMIT = 5.0  # seconds for describe() on the 300-face part

# Parts written here (the golden step language), for shapes no golden model has.
EXTRA_MODELS = {
    "bench_stepped_shaft": {
        "title": "Stepped shaft turned about Z (d24 x 15, d16 x 45, d10 x 10)",
        "steps": [
            {
                "op": "sketch",
                "id": "s1",
                "plane": "XZ",
                "geometry": [
                    {
                        "polyline": [
                            [0, 0],
                            [12, 0],
                            [12, 15],
                            [8, 15],
                            [8, 60],
                            [5, 60],
                            [5, 70],
                            [0, 70],
                        ]
                    }
                ],
            },
            {"op": "sf_revolve", "id": "r1", "profile": "s1", "axis": "Z"},
        ],
    },
    "bench_knob": {
        "title": "Knob: d40 x 8 with a cone up to d30 at 15, a d6 x 10 shaft hole underneath",
        "steps": [
            {
                "op": "sketch",
                "id": "s1",
                "plane": "XZ",
                "geometry": [{"polyline": [[0, 0], [20, 0], [20, 8], [15, 15], [0, 15]]}],
            },
            {"op": "sf_revolve", "id": "r1", "profile": "s1", "axis": "Z"},
            {
                "op": "sketch",
                "id": "s2",
                "plane": "XY",
                "geometry": [{"circle": [0, 0, 3]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s2", "diameter": 6, "depth": 10},
        ],
    },
    "bench_bracket_holes": {
        "title": "L bracket 40 x 20 x 30 (5 thick), two holes d5 in the foot, one d6 in the leg, "
        "inside corner r3",
        "steps": [
            {
                "op": "sketch",
                "id": "s1",
                "plane": "XZ",
                "geometry": [{"polyline": [[0, 0], [40, 0], [40, 5], [5, 5], [5, 30], [0, 30]]}],
            },
            {"op": "extrude", "id": "e1", "profile": "s1", "distance": 20},
            {
                "op": "sketch",
                "id": "s2",
                "plane": "XY",
                "offset": 5,
                "geometry": [{"circle": [25, -6, 2.5]}, {"circle": [25, -14, 2.5]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s2", "diameter": 5, "through_all": True},
            {
                "op": "sketch",
                "id": "s3",
                "plane": "YZ",
                "offset": 5,
                "geometry": [{"circle": [-10, 20, 3]}],
            },
            {"op": "hole", "id": "h2", "sketch": "s3", "diameter": 6, "through_all": True},
            {
                "op": "fillet",
                "id": "f1",
                "radius": 3,
                "edges": {
                    "type": "line",
                    "parallel": [0, 1, 0],
                    "at": [{"axis": "x", "value": 5}, {"axis": "z", "value": 5}],
                    "count": 1,
                },
            },
        ],
    },
    "bench_mount_plate": {
        "title": "Mounting plate 80 x 50 x 6, corners r6, a centre slot 30 x 10, four d5 holes "
        "on a 64 x 34 grid",
        "steps": [
            {
                "op": "sketch",
                "id": "s1",
                "plane": "XY",
                "geometry": [{"rect": [0, 0, 80, 50]}],
            },
            {"op": "extrude", "id": "e1", "profile": "s1", "distance": 6},
            {
                "op": "fillet",
                "id": "f1",
                "radius": 6,
                "edges": {"type": "line", "parallel": [0, 0, 1], "count": 4},
            },
            {
                "op": "sketch",
                "id": "s2",
                "plane": "XY",
                "offset": 6,
                "geometry": [{"slot": [30, 25, 50, 25, 10]}],
            },
            {
                "op": "extrude",
                "id": "c1",
                "profile": "s2",
                "operation": "cut",
                "extent": "through_all",
                "flip": True,
            },
            {
                "op": "sketch",
                "id": "s3",
                "plane": "XY",
                "offset": 6,
                "geometry": [{"circle": [8, 8, 2.5]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s3", "diameter": 5, "through_all": True},
            {
                "op": "rectangular_pattern",
                "id": "p1",
                "features": ["h1"],
                "direction": "X",
                "quantity": 2,
                "distance": 64,
                "distribution": "spacing",
                "direction2": "Y",
                "quantity2": 2,
                "distance2": 34,
            },
        ],
    },
    "bench_shaft_cross_hole": {
        "title": "Shaft d20 x 50 along Z with a d4 hole across it (along X) at height 25",
        "steps": [
            {"op": "sketch", "id": "s1", "plane": "XY", "geometry": [{"circle": [0, 0, 10]}]},
            {"op": "extrude", "id": "e1", "profile": "s1", "distance": 50},
            {
                "op": "sketch",
                "id": "s2",
                "plane": "YZ",
                "offset": 15,
                "geometry": [{"circle": [0, 25, 2]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s2", "diameter": 4, "through_all": True},
        ],
    },
    "bench_offset_flange": {
        "title": "Flange d60 x 8 centred at (40, 30) with a d20 bore and 5 holes d6 on a d44 "
        "circle around it (not around the origin)",
        "steps": [
            {"op": "sketch", "id": "s1", "plane": "XY", "geometry": [{"circle": [40, 30, 30]}]},
            {"op": "extrude", "id": "e1", "profile": "s1", "distance": 8},
            {
                "op": "sketch",
                "id": "s2",
                "plane": "XY",
                "offset": 8,
                "geometry": [{"circle": [40, 30, 10]}],
            },
            {"op": "hole", "id": "h0", "sketch": "s2", "diameter": 20, "through_all": True},
            {
                "op": "sketch",
                "id": "s3",
                "plane": "XY",
                "offset": 8,
                "geometry": [{"circle": [62, 30, 3]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s3", "diameter": 6, "through_all": True},
            {
                "op": "circular_pattern",
                "id": "p1",
                "features": ["h1"],
                "axis": {"face": {"type": "cylinder", "radius": 10, "count": 1}},
                "quantity": 5,
            },
        ],
    },
    "bench_turned_bracket": {
        "title": "The bracket with holes, turned 30 degrees about X and 20 about Z (a STEP part "
        "placed in an assembly)",
        "steps": [],  # (the steps of bench_bracket_holes, then the turn: see _load)
    },
    "bench_part_300": {
        "title": "Speed part: plate 330 x 220 x 8 with a 21 x 14 grid of d6 holes (300 faces)",
        "steps": [
            {
                "op": "sketch",
                "id": "s1",
                "plane": "XY",
                "geometry": [{"rect": [0, 0, 330, 220]}],
            },
            {"op": "extrude", "id": "e1", "profile": "s1", "distance": 8},
            {
                "op": "sketch",
                "id": "s2",
                "plane": "XY",
                "offset": 8,
                "geometry": [{"circle": [15, 12, 3]}],
            },
            {"op": "hole", "id": "h1", "sketch": "s2", "diameter": 6, "through_all": True},
            {
                "op": "rectangular_pattern",
                "id": "p1",
                "features": ["h1"],
                "direction": "X",
                "quantity": 21,
                "distance": 15,
                "distribution": "spacing",
                "direction2": "Y",
                "quantity2": 14,
                "distance2": 15,
            },
        ],
    },
}

# What each model's steps made, for the "found" check. base: the kind describe() should
# answer; holes: every hole's diameter; fillets / chamfers: the sizes; patterns: how many
# pattern features; mesh: also run as an STL through recognize_mesh.
BENCH = [
    ("box_basic", {"base": "extrude", "holes": [], "fillets": [], "chamfers": []}),
    ("cylinder_extrude", {"base": "extrude", "holes": [], "fillets": []}),
    ("hex_prism", {"base": "extrude", "holes": []}),
    ("l_bracket_profile", {"base": "extrude", "holes": []}),
    ("slot_extrude", {"base": "extrude", "holes": [], "fillets": []}),
    ("bracket_inner_fillet", {"base": "extrude", "fillets": [3]}),
    ("fillet_top_edges", {"base": "extrude", "fillets": [2]}),
    ("fillet_one_vertical_edge", {"base": "extrude", "fillets": [5]}),
    ("fillet_all_edges", {"base": "extrude", "fillets": [2]}),
    ("chamfer_top_edges", {"base": "extrude", "chamfers": [2]}),
    ("chamfer_one_edge", {"base": "extrude", "chamfers": [3]}),
    ("blend_chamfer_top_face", {"base": "extrude"}),
    ("plate_through_hole_cut", {"base": "extrude", "holes": [10]}),
    ("pattern_rect_hole_grid_fusion", {"base": "extrude", "holes": [6] * 6, "patterns": 1}),
    ("flange_polar_holes", {"base": "extrude", "holes": [8] * 6, "patterns": 1}),
    ("hole_blind", {"base": "extrude", "holes": [6]}),
    ("hole_counterbore", {"base": "extrude", "holes": [6.6]}),
    ("hole_countersink", {"base": "extrude", "holes": [6]}),
    ("hole_single_angled", {"base": "extrude", "holes": [5]}),
    ("pocket_depth", {"base": "extrude", "holes": []}),
    ("symmetric_cut_slot", {"base": "extrude", "holes": []}),
    ("sf_cylinder_boss", {"base": "extrude", "holes": []}),
    ("mirror_boss", {"base": "extrude", "holes": []}),
    ("pattern_rect_symmetric_bosses", {"base": "extrude", "holes": []}),
    ("shell_open_box", {"base": "extrude", "holes": [], "shells": 1}),
    ("shell_filleted_box", {"base": "extrude", "fillets": [], "shells": 1}),
    ("revolve_washer", {"holes": [20]}),
    ("groove_ring", {"holes": []}),
    ("sf_revolve_cone", {"base": "revolve", "holes": []}),
    ("bench_stepped_shaft", {"base": "revolve", "holes": []}),
    ("bench_knob", {"base": "revolve", "holes": [6]}),
    ("bench_bracket_holes", {"base": "extrude", "holes": [5, 5, 6], "fillets": [3]}),
    ("bench_mount_plate", {"base": "extrude", "holes": [5] * 4, "fillets": [6]}),
    ("extrude_taper_cut", {"base": "extrude", "holes": []}),
    ("extrude_taper_join_all", {"base": "extrude", "holes": []}),
    ("sf_draft_four_sides", {"base": "extrude", "holes": []}),
    ("bench_turned_bracket", {"base": "extrude", "holes": [5, 5, 6], "fillets": [3]}),
    ("bench_shaft_cross_hole", {"base": "extrude", "holes": [4]}),
    ("bench_offset_flange", {"base": "extrude", "holes": [6, 6, 6, 6, 6, 20], "patterns": 1}),
    ("bench_part_300", {"base": "extrude", "holes": [6] * 294, "patterns": 1, "speed": True}),
]
MESH_BENCH = [
    "plate_through_hole_cut",
    "flange_polar_holes",
    "l_bracket_profile",
    "bench_knob",
    "bench_mount_plate",
]


def _load(model_id):
    if model_id == "bench_turned_bracket":
        model = copy.deepcopy(EXTRA_MODELS["bench_bracket_holes"])
        model["steps"].append(
            {
                "op": "move_bodies",
                "id": "m1",
                "bodies": ["e1"],
                "move_type": "free",
                "rx": 30,
                "rz": 20,
                "pivot": [0, 0, 0],
            }
        )
        model["id"] = model_id
        model["title"] = EXTRA_MODELS[model_id]["title"]
        return model
    if model_id in EXTRA_MODELS:
        model = copy.deepcopy(EXTRA_MODELS[model_id])
        model["id"] = model_id
        return model
    with open(os.path.join(GOLDEN, model_id + ".json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


def build(model):
    """The model's solid (built in a throw-away document)."""
    import FreeCAD as App

    from SciForgeTests.golden.builder import Builder

    doc = App.newDocument("rb_" + re.sub(r"\W", "_", model["id"]))
    try:
        builder = Builder(doc)
        for step in model["steps"]:
            if step["op"] in ("check", "reopen", "age"):
                continue
            builder.run(step)
        return builder.shape().copy()
    finally:
        App.closeDocument(doc.Name)


def step_round_trip(shape, folder, name):
    """Export to STEP and import back as SciForge does with File > Open: the featureless
    body's solid."""
    import FreeCAD as App

    from sciforge import step_import

    path = os.path.join(folder, name + ".step")
    shape.exportStep(path)
    doc = App.newDocument("rb_import")
    try:
        made = step_import.import_file(doc, path)
        bodies = made.bodies
        if not bodies:
            raise RuntimeError("the STEP file gave no body")
        return bodies[0].Shape.copy()
    finally:
        App.closeDocument(doc.Name)


def _ids_in(text):
    match = re.search(r"Its id is '([^']+)'", text)
    return match.group(1) if match else None


def _set_path(args, path, value):
    """args with the argument at `path` ("profile", "features[0]") set to value."""
    match = re.match(r"^([A-Za-z_]+)(?:\[(\d+)\])?$", path)
    if not match:
        return
    key, index = match.group(1), match.group(2)
    if index is None:
        args[key] = value
    elif isinstance(args.get(key), list) and int(index) < len(args[key]):
        args[key][int(index)] = value


def run_plan(plan, name):
    """Run the plan's steps through the headless executor in a new design. Returns (rebuilt
    solid or None, [(step, error text)], ids made)."""
    import FreeCAD as App

    from sciforge.ai import headless

    host = headless.HeadlessHost()
    answer = headless.call("new_design", {"name": name}, host)
    if answer["is_error"]:
        return None, [(0, answer["text"])], {}
    made = {}
    errors = []
    for step in plan:
        args = copy.deepcopy(step["args"])
        for path, number in (step.get("uses") or {}).items():
            if number in made:
                _set_path(args, path, made[number])
        answer = headless.call(step["tool"], args, host)
        if answer["is_error"]:
            errors.append((step["step"], answer["text"][:500]))
            break
        got = _ids_in(answer["text"])
        if got:
            made[step["step"]] = got
    doc = App.ActiveDocument
    shape = None
    try:
        from sciforge import bodies

        found = [b for b in bodies.solid_bodies(doc)] if doc is not None else []
        if len(found) > 1:
            errors.append((-1, "the plan made %d bodies, not one" % len(found)))
        if found:
            shape = found[0].Shape.copy()
    except Exception as exc:
        errors.append((-1, "no rebuilt body: %s" % exc))
    if doc is not None:
        App.closeDocument(doc.Name)
    return shape, errors, made


def match_faces(reference, rebuilt):
    """How many faces of the reference have a face of the rebuild of the same kind, area and
    place (and the other way round)."""
    from sciforge import recognize
    from sciforge.ai.ops import selectors

    def facts(shape):
        out = []
        for f in shape.Faces:
            c = f.CenterOfMass
            kind = selectors.face_type(f)
            if kind == "bspline" and recognize._flat_normal(f) is not None:
                kind = "plane"  # (a flat face SciForge's tapered extrude makes as a spline)
            out.append((kind, f.Area, (c.x, c.y, c.z)))
        return out

    a, b = facts(reference), facts(rebuilt)
    size = max(1.0, reference.BoundBox.DiagonalLength)

    def matched(src, dst):
        used = set()
        count = 0
        for kind, area, c in src:
            for j, (k2, a2, c2) in enumerate(dst):
                if j in used or k2 != kind:
                    continue
                if abs(a2 - area) > 1e-4 * max(area, 1.0):
                    continue
                if math.dist(c, c2) > 1e-4 * size:
                    continue
                used.add(j)
                count += 1
                break
        return count

    return matched(a, b), matched(b, a)


def _found(result):
    holes = sorted(
        f["diameter"]
        for f in result["features"]
        if f["kind"] in ("hole", "counterbore", "countersink")
    )
    fillets = sorted({f["radius"] for f in result["features"] if f["kind"] == "fillet"})
    chamfers = sorted({f["distance"] for f in result["features"] if f["kind"] == "chamfer"})
    patterns = len([f for f in result["features"] if f["kind"] == "pattern"])
    shells = len([f for f in result["features"] if f["kind"] == "shell"])
    return {
        "base": result["base"].get("kind"),
        "holes": holes,
        "fillets": fillets,
        "chamfers": chamfers,
        "patterns": patterns,
        "shells": shells,
    }


def _check_found(expect, found):
    problems = []
    if "base" in expect and found["base"] != expect["base"]:
        problems.append("base %s, expected %s" % (found["base"], expect["base"]))
    for key in ("holes",):
        if key in expect and sorted(expect[key]) != found[key]:
            problems.append("%s %s, expected %s" % (key, found[key], sorted(expect[key])))
    for key in ("fillets", "chamfers"):
        if key in expect and sorted(set(expect[key])) != found[key]:
            problems.append("%s %s, expected %s" % (key, found[key], sorted(set(expect[key]))))
    for key in ("patterns", "shells"):
        if key in expect and found[key] != expect[key]:
            problems.append("%s %d, expected %d" % (key, found[key], expect[key]))
    return problems


def bench_model(model_id, expect, folder):
    from sciforge import recognize
    from sciforge.ai import catalog

    row = {"id": model_id, "status": "fail", "problems": []}
    start = time.time()
    try:
        model = _load(model_id)
        row["title"] = model.get("title", "")
        original = build(model)
        reference = step_round_trip(original, folder, model_id)
        row["faces"] = len(reference.Faces)
        t0 = time.time()
        result = recognize.describe(reference)
        row["describe_s"] = round(time.time() - t0, 3)
        row["base"] = result["base"].get("kind")
        row["found"] = _found(result)
        row["plan_length"] = len(result["plan"])
        row["confidence"] = result["confidence"]
        row["notes"] = result["notes"]
        row["unrecognized"] = [u["why"] for u in result["unrecognized"]]
        row["plan"] = [{"tool": s["tool"], "args": s["args"]} for s in result["plan"]]
        row["problems"] += _check_found(expect, row["found"])
        for step in result["plan"]:
            for sentence in catalog.validate(step["tool"], step["args"]):
                row["problems"].append("step %d %s: %s" % (step["step"], step["tool"], sentence))
        if expect.get("speed") and row["describe_s"] > SPEED_LIMIT:
            row["problems"].append(
                "describe() took %.2f s on %d faces (limit %.0f s)"
                % (row["describe_s"], row["faces"], SPEED_LIMIT)
            )
        rebuilt, errors, _made = run_plan(result["plan"], "rb_" + re.sub(r"\W", "_", model_id))
        for number, text in errors:
            row["problems"].append("plan step %d failed: %s" % (number, text))
        if rebuilt is None:
            row["problems"].append("nothing was rebuilt")
            row["volume_diff"] = None
        else:
            v0, v1 = reference.Volume, rebuilt.Volume
            row["volume_diff"] = (v1 - v0) / v0
            common = rebuilt.common(reference).Volume
            row["match"] = common / (v0 + v1 - common)
            faces_ok, faces_back = match_faces(reference, rebuilt)
            row["faces_matched"] = faces_ok
            row["rebuilt_faces"] = len(rebuilt.Faces)
            row["rebuilt_matched"] = faces_back
            if abs(row["volume_diff"]) > VOLUME_TOL:
                row["problems"].append(
                    "rebuilt volume %.6g vs %.6g (%+.4f %%)" % (v1, v0, 100 * row["volume_diff"])
                )
            if faces_ok != len(reference.Faces):
                row["problems"].append("%d of %d faces matched" % (faces_ok, len(reference.Faces)))
    except Exception as exc:
        row["problems"].append("%s: %s" % (type(exc).__name__, exc))
        row["traceback"] = traceback.format_exc()
    row["seconds"] = round(time.time() - start, 3)
    row["status"] = "pass" if not row["problems"] else "fail"
    return row


def bench_mesh(model_id, folder):
    """An STL of a golden model through recognize_mesh: the same dict, the plan rebuilt."""
    import Mesh
    import MeshPart

    from sciforge import recognize_mesh

    row = {"id": model_id + " (mesh)", "status": "fail", "problems": []}
    start = time.time()
    try:
        model = _load(model_id)
        original = build(model)
        mesh = MeshPart.meshFromShape(
            Shape=original, LinearDeflection=0.01, AngularDeflection=math.radians(10)
        )
        path = os.path.join(folder, model_id + ".stl")
        mesh.write(path)
        mesh = Mesh.Mesh(path)
        row["triangles"] = mesh.CountFacets
        t0 = time.time()
        result = recognize_mesh.describe_mesh(mesh)
        row["describe_s"] = round(time.time() - t0, 3)
        row["base"] = result["base"].get("kind")
        row["found"] = _found(result)
        row["plan_length"] = len(result["plan"])
        row["confidence"] = result["confidence"]
        row["notes"] = result["notes"]
        row["plan"] = [{"tool": s["tool"], "args": s["args"]} for s in result["plan"]]
        expect = dict(BENCH)[model_id]
        row["problems"] += _check_found(
            {k: v for k, v in expect.items() if k in ("base", "holes")}, row["found"]
        )
        rebuilt, errors, _made = run_plan(result["plan"], "rbm_" + re.sub(r"\W", "_", model_id))
        for number, text in errors:
            row["problems"].append("plan step %d failed: %s" % (number, text))
        if rebuilt is None:
            row["problems"].append("nothing was rebuilt")
        else:
            v0, v1 = original.Volume, rebuilt.Volume
            row["volume_diff"] = (v1 - v0) / v0
            common = rebuilt.common(original).Volume
            row["match"] = common / (v0 + v1 - common)
            faces_ok, faces_back = match_faces(original, rebuilt)
            row["faces_matched"] = faces_ok
            row["faces"] = len(original.Faces)
            if abs(row["volume_diff"]) > VOLUME_TOL:
                row["problems"].append(
                    "rebuilt volume %.6g vs the model's %.6g (%+.4f %%)"
                    % (v1, v0, 100 * row["volume_diff"])
                )
            if faces_ok != len(original.Faces):
                row["problems"].append("%d of %d faces matched" % (faces_ok, len(original.Faces)))
    except Exception as exc:
        row["problems"].append("%s: %s" % (type(exc).__name__, exc))
        row["traceback"] = traceback.format_exc()
    row["seconds"] = round(time.time() - start, 3)
    row["status"] = "pass" if not row["problems"] else "fail"
    return row


def markdown(report):
    lines = [
        "# Auto Timeline recognition benchmark",
        "",
        "FreeCAD %s, %s. %d parts: %d pass, %d fail. Each part: built, exported to STEP, "
        "imported as a body without a timeline, described, rebuilt from the plan through the "
        "headless AI executor, compared (volume within 0.1 %%, every face matched)."
        % (
            report["freecad"],
            report["platform"],
            len(report["results"]),
            len([r for r in report["results"] if r["status"] == "pass"]),
            len([r for r in report["results"] if r["status"] != "pass"]),
        ),
        "",
        "| Part | Faces | Found | Plan steps | Volume | Faces matched | describe (s) | Total (s) "
        "| Result |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["results"]:
        found = r.get("found") or {}
        words = [str(found.get("base"))]
        if found.get("holes"):
            words.append(
                "%d hole%s" % (len(found["holes"]), "" if len(found["holes"]) == 1 else "s")
            )
        if found.get("patterns"):
            words.append(
                "%d pattern%s" % (found["patterns"], "" if found["patterns"] == 1 else "s")
            )
        if found.get("fillets"):
            words.append("fillet r%s" % "/".join("%g" % v for v in found["fillets"]))
        if found.get("chamfers"):
            words.append("chamfer %s" % "/".join("%g" % v for v in found["chamfers"]))
        vol = r.get("volume_diff")
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["id"],
                r.get("faces", r.get("triangles", "")),
                ", ".join(words),
                r.get("plan_length", ""),
                "" if vol is None else "%+.4f %%" % (100 * vol),
                (
                    ""
                    if "faces_matched" not in r
                    else "%d / %d" % (r["faces_matched"], r.get("faces", 0))
                ),
                r.get("describe_s", ""),
                r.get("seconds", ""),
                "PASS" if r["status"] == "pass" else "**FAIL**",
            )
        )
    failures = [r for r in report["results"] if r["status"] != "pass"]
    if failures:
        lines += ["", "## Problems", ""]
        for r in failures:
            lines.append("- **%s**: %s" % (r["id"], "; ".join(r["problems"])[:1500]))
    return "\n".join(lines) + "\n"


def _write(report, out_dir):
    report["passed"] = bool(report["results"]) and all(
        r["status"] == "pass" for r in report["results"]
    )
    with open(os.path.join(out_dir, "recognize-report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
    with open(os.path.join(out_dir, "recognize-report.md"), "w", encoding="utf-8") as handle:
        handle.write(markdown(report))


def main():
    import FreeCAD as App

    out_dir = (
        os.environ.get("SCIFORGE_RECOGNIZE_OUT")
        or os.environ.get("SCIFORGE_HEADLESS_OUT")
        or App.getUserAppDataDir()
    )
    os.makedirs(out_dir, exist_ok=True)
    text_filter = os.environ.get("SCIFORGE_RECOGNIZE_FILTER", "")
    folder = tempfile.mkdtemp(prefix="sciforge-recognize-")
    report = {
        "freecad": ".".join(App.Version()[:3]),
        "platform": platform.platform(),
        "folder": folder,
        "results": [],
    }
    for model_id, expect in BENCH:
        if text_filter and text_filter not in model_id:
            continue
        row = bench_model(model_id, expect, folder)
        report["results"].append(row)
        _write(report, out_dir)
        App.Console.PrintMessage(
            "[SciForge] recognize %s %s %s\n"
            % (row["status"].upper(), model_id, "; ".join(row["problems"])[:600])
        )
    for model_id in MESH_BENCH:
        if text_filter and text_filter not in model_id and text_filter != "mesh":
            continue
        row = bench_mesh(model_id, folder)
        report["results"].append(row)
        _write(report, out_dir)
        App.Console.PrintMessage(
            "[SciForge] recognize %s %s %s\n"
            % (row["status"].upper(), row["id"], "; ".join(row["problems"])[:600])
        )
    _write(report, out_dir)
    App.Console.PrintMessage(
        "[SciForge] recognize summary: %d parts, %d failed\n"
        % (
            len(report["results"]),
            len([r for r in report["results"] if r["status"] != "pass"]),
        )
    )
    return report

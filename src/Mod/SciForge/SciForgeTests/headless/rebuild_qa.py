# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline QA checks (beta 3 QA): the cases the builders' end-to-end test did not try,
each a bug found (and fixed) by the QA pass. Run by rebuild_e2e.main() (so by
tools/sciforge/run_tests.sh --only headless / base), after the six parts:

* jointed: two imported STEP parts in components, a revolute joint between them; the arm is
  rebuilt and finished: the joint must survive and sit on the rebuilt body (it was deleted
  with the original: joints.remove_joints_of), the arm must not move, the joint must still
  drive; no stray imported shape of the original is left (it stayed in its component as a
  timeline step); the rebuild takes the original's place in the timeline (before the joint);
  undo / redo of Finish.
* dependents: a body at the design's root, grounded, with a pattern of bodies of it and a
  sketch of another body on its top face; all three follow the rebuild.
* kept: a link that cannot follow (to the original's own sketch): the original is kept,
  hidden, instead of deleted, and the answer says why.
* reopened: a design saved half way through a rebuild and opened again: the next plan step
  goes into the rebuilt body (it went into the design's first body).
* deleted reference: the reference deleted with delete_step: the original is shown again.
* driven: the jointed arm turned while it is rebuilt: the reference turns with it (compare
  said match 0.16 and the plan came out turned).
* vex channel: a VEX C-channel (50 + 50 square holes, 410 faces) was also read along its
  length (51 levels: a section and booleans each): describe took 37 s.
* chamfered rim: compare called holes with a chamfered rim "a round hole ... with a pointed
  (drilled) end".
* midway: check_design while a rebuild goes on took the hidden original under its rebuild for
  an overlap (NOT OK).
* follower: a body whose extrude also cuts another body: Finish deleted it and the other
  body lost the cut; now the original is kept (hidden) for it.
* component id: start_rebuild given the component's id (what import_file answers) rebuilds
  its one body (it refused: "pick the body").
* vex plate: a VEX-like plate with 125 square holes (506 faces): describe_reference took 56 s
  (a section and a boolean per level along X, two booleans on 506 coincident faces).
* bossed plate: a plate with a boss and 60 holes in the face the boss stands on: no hole was
  closed by its rim (Face.cutHoles answers None), all went to defeaturing (12.7 s).
* text: a plate with a hole and raised (or engraved) text: the free-form letters made the whole
  part unreadable (base 'none', a plan of a sketch and a hole that failed); now the plate and
  the hole are read and the letters are said, with what to do.
* stopped: a rebuild given up in a design opened again: there was no way but Undo (none
  there); Stop Rebuild shows the original again and deletes (or keeps) the rebuilt body.
* big mesh: a 37,740-triangle STL took 160 s in start_rebuild and as long again in
  describe_reference (FreeCAD frozen); now a mesh over 10,000 triangles is refused at once
  with what to do, and describe reads the reference's solid instead of making it again.
* threaded: a plate with a modeled M6 thread: describe_reference took 210 s (OpenCASCADE's
  defeaturing on the thread's faces) and read no base; now the plate and the hole are read in
  seconds and the thread is listed as not read.

Each check takes `agent` (rebuild_e2e.Agent: call / check) and runs in-process.
"""

import json
import os
import tempfile
import traceback


def _json(text):
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def _golden(agent, name, calls, folder):
    agent.call("new_design", {"name": name})
    for tool, args in calls:
        text, error = agent.call(tool, args)
        if error:
            raise RuntimeError("%s: %s" % (tool, text))
    path = os.path.join(folder, name + ".step")
    text, error = agent.call("export", {"format": "step", "path": path})
    if error:
        raise RuntimeError(text)
    return path


ARM = [
    ("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 80, 20]}]}),
    ("extrude", {"profile": "Sketch1", "distance": 5}),
    (
        "create_sketch",
        {
            "plane": "XY",
            "offset": 5,
            "geometry": [{"circle": [10, 10, 2.5]}, {"circle": [70, 10, 2.5]}],
        },
    ),
    ("hole", {"sketch": "Sketch2", "diameter": 5, "through_all": True}),
]
BASE = [
    ("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 40]}]}),
    ("extrude", {"profile": "Sketch1", "distance": 10}),
    ("create_sketch", {"plane": "XY", "offset": 10, "geometry": [{"circle": [20, 20, 2.5]}]}),
    ("hole", {"sketch": "Sketch2", "diameter": 5, "through_all": True}),
]


def rebuild_through_tools(agent, body, plan=None):
    """start_rebuild, describe_reference, the plan, compare (with its fixes): the compare
    answer at the end. body None and a plan: a rebuild already started, its plan given."""
    from . import rebuild_e2e as e2e

    if plan is None:
        agent.call("start_rebuild", {"body": body})
        text, error = agent.call("describe_reference", {})
        data = _json(text) or {}
        plan = data.get("plan") or []
    made = {}
    for step in plan:
        args = agent._with_ids(step, made, plan)
        text, error = agent.call(step["tool"], args)
        ident = e2e.made_id(text) if not error else None
        if ident:
            made[step.get("step")] = ident
    result = None
    for _round in range(4):
        text, error = agent.call("compare_to_reference", {})
        result = _json(text) or {}
        if result.get("done"):
            break
        fixes = agent._fixes(result)
        if not fixes:
            break
        for fix in fixes:
            agent.call(fix["tool"], fix["args"])
    return result or {}


# -- jointed parts (the VEX case) ----------------------------------------------------------------
def jointed(agent, folder):
    import FreeCAD as App

    from sciforge import joints, timeline_ops

    arm = _golden(agent, "QaArm", ARM, folder)
    base = _golden(agent, "QaBase", BASE, folder)
    agent.call("new_design", {"name": "QaJointed"})
    agent.call("import_file", {"path": arm})
    agent.call("import_file", {"path": base})
    doc = App.ActiveDocument
    agent.call("ground", {"component": "Component001"})
    text, error = agent.call(
        "joint",
        {
            "type": "revolute",
            "first": {
                "component": "Component",
                "face": {"type": "cylinder", "count": 1, "at": {"axis": "x", "value": "min"}},
                "snap": "circle",
            },
            "second": {
                "component": "Component001",
                "face": {"type": "cylinder", "count": 1},
                "snap": "circle",
            },
        },
    )
    if not agent.check("jointed: the revolute joint is made", not error, text):
        return
    arm_part = doc.getObject("Component")
    agent.call("drive_joint", {"joint": "Joint", "angle": 60})
    at_60 = App.Placement(arm_part.Placement)
    agent.call("drive_joint", {"joint": "Joint", "angle": 30})
    at_30 = App.Placement(arm_part.Placement)
    result = rebuild_through_tools(agent, "Body001")
    if not agent.check("jointed: the arm is rebuilt (done)", result.get("done"), result):
        return
    text, error = agent.call("finish_rebuild", {})
    agent.check("jointed: finish_rebuild", not error, text)
    found = joints.joints(doc)
    rebuilt = doc.getObject("Body003")
    ok = (
        len(found) == 1
        and rebuilt is not None
        and rebuilt.Label == "Body001"
        and all("Body003." in s for s in found[0].Reference1[1])
    )
    agent.check(
        "jointed: the joint survives Finish, on the rebuilt body (it was deleted with the "
        "original)",
        ok,
        [(j.Name, j.Reference1) for j in found],
    )
    agent.check(
        "jointed: the answer says the joint now uses the rebuild",
        "Revolute 1" in text and "instead of the original" in text,
        text,
    )
    agent.check(
        "jointed: the arm did not move",
        arm_part.Placement.isSame(at_30, 1e-7),
        (arm_part.Placement, at_30),
    )
    text, error = agent.call("drive_joint", {"joint": "Joint", "angle": 60})
    agent.check(
        "jointed: the joint still drives the arm (to where the original went)",
        not error and arm_part.Placement.isSame(at_60, 1e-6),
        (text, arm_part.Placement, at_60),
    )
    stray = [o.Label for o in doc.Objects if o.Label == "Body001 (imported)"]
    agent.check("jointed: no stray imported shape of the original is left", not stray, stray)
    order = timeline_ops.step_order(doc)
    first = [n for n in order if doc.getObject(n) in rebuilt.Group]
    agent.check(
        "jointed: the rebuild takes the original's place in the timeline (before the joint)",
        first and order.index(first[-1]) < order.index("Joint"),
        order,
    )
    agent.call("undo", {})  # the drive
    agent.call("undo", {})  # finish
    found = joints.joints(doc)
    agent.check(
        "jointed: undo of Finish puts the joint back on the original",
        len(found) == 1 and all("Body001." in s for s in found[0].Reference1[1]),
        [(j.Name, j.Reference1) for j in found],
    )
    agent.call("redo", {})
    found = joints.joints(doc)
    agent.check(
        "jointed: redo moves it onto the rebuild again",
        len(found) == 1 and all("Body003." in s for s in found[0].Reference1[1]),
        [(j.Name, j.Reference1) for j in found],
    )


# -- a root body with a ground, a pattern of bodies and a sketch on its face ----------------------
def _featureless(doc, name, shape):
    from sciforge import bodies

    doc.openTransaction("QA setup")
    body = bodies.new_body(doc, name)
    base = doc.addObject("Part::Feature", "Imported")
    base.Shape = shape
    body.BaseFeature = base
    doc.commitTransaction()
    doc.recompute()
    return body


def _plate():
    import FreeCAD as App
    import Part

    plate = Part.makeBox(60, 40, 8)
    for x, y in ((15, 20), (45, 20)):
        plate = plate.cut(Part.makeCylinder(3, 8, App.Vector(x, y, 0)))
    return plate


def dependents(agent, folder):
    import FreeCAD as App
    import Part

    from sciforge import bodies, joints, pattern

    agent.call("new_design", {"name": "QaDependents"})
    doc = App.ActiveDocument
    plate = _featureless(doc, "Plate", _plate())
    top = [
        i + 1
        for i, f in enumerate(plate.Shape.Faces)
        if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - 8) < 1e-6
    ][0]
    doc.openTransaction("QA riser")
    riser = bodies.new_body(doc, "Riser")
    sketch = riser.newObject("Sketcher::SketchObject", "RiserSketch")
    sketch.AttachmentSupport = [(plate, "Face%d" % top)]
    sketch.MapMode = "FlatFace"
    sketch.addGeometry(Part.Circle(App.Vector(30, 32, 0), App.Vector(0, 0, 1), 4))
    pad = riser.newObject("PartDesign::Pad", "RiserPad")
    pad.Profile = sketch
    pad.Length = 6
    doc.commitTransaction()
    doc.recompute()
    riser_box = App.BoundBox(riser.Shape.BoundBox)
    agent.call("activate", {"target": plate.Name})
    agent.call(
        "rectangular_pattern",
        {"body": True, "direction": "Y", "quantity": 2, "distance": 50, "distribution": "spacing"},
    )
    agent.call("ground", {"component": plate.Name})
    patterns = [o for o in doc.Objects if pattern.is_body_pattern(o)]
    copies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body" and o.Label == "Body4"]
    result = rebuild_through_tools(agent, plate.Name)
    if not agent.check("dependents: the plate is rebuilt (done)", result.get("done"), result):
        return
    text, error = agent.call("finish_rebuild", {})
    agent.check("dependents: finish_rebuild", not error, text)
    rebuilt = [o for o in doc.Objects if o.TypeId == "PartDesign::Body" and o.Label == "Plate"]
    rebuilt = rebuilt[0] if rebuilt else None
    grounds = [g.ObjectToGround for g in joints.grounds(doc)]
    agent.check(
        "dependents: the ground follows the rebuild",
        rebuilt is not None and grounds and grounds[0] is rebuilt,
        [getattr(g, "Name", None) for g in grounds],
    )
    agent.check(
        "dependents: the pattern of bodies copies the rebuild",
        patterns
        and bodies.alive(patterns[0])
        and rebuilt is not None
        and patterns[0].SourceBody == rebuilt.Name
        and bodies.body_of(patterns[0].Source) is rebuilt,
        [(p.Name, getattr(p.Source, "Name", None), p.SourceBody) for p in patterns],
    )
    support = sketch.AttachmentSupport
    face = None
    try:
        face = rebuilt.Shape.getElement(support[0][1][0])
    except Exception:
        pass
    agent.check(
        "dependents: the other body's sketch stays on the top face (now the rebuild's)",
        support
        and support[0][0] is rebuilt
        and face is not None
        and abs(face.CenterOfMass.z - 8) < 1e-6
        and sketch.MapMode == "FlatFace",
        support,
    )
    doc.recompute()
    agent.check(
        "dependents: the other body and the pattern's copy are unchanged",
        riser.Shape.BoundBox.isInside(riser_box.Center)
        and abs(riser.Shape.BoundBox.ZMax - riser_box.ZMax) < 1e-6
        and copies
        and abs(copies[0].Shape.Volume - result["volume"]["reference"]) < 1e-3,
        (riser.Shape.BoundBox, riser_box, [c.Shape.Volume for c in copies]),
    )
    text, error = agent.call("check_design", {"interference": False})
    report = _json(text) or {}
    agent.check(
        "dependents: check_design finds no failed step", not report.get("failed_steps"), text
    )


# -- a link that cannot follow: the original is kept --------------------------------------------
def kept(agent, folder):
    import FreeCAD as App

    agent.call("new_design", {"name": "QaKept"})
    doc = App.ActiveDocument
    plate = _featureless(doc, "Plate", _plate())
    result = rebuild_through_tools(agent, plate.Name)
    if not agent.check("kept: the plate is rebuilt (done)", result.get("done"), result):
        return
    # something that uses a sketch of the original's own (no counterpart in the rebuild)
    doc.openTransaction("QA link")
    own = plate.newObject("Sketcher::SketchObject", "OwnSketch")
    holder = doc.addObject("App::FeaturePython", "QaHolder")
    holder.addProperty("App::PropertyLink", "Uses", "QA")
    holder.Uses = own
    doc.commitTransaction()
    text, error = agent.call("finish_rebuild", {})
    labels = sorted(o.Label for o in doc.Objects if o.TypeId == "PartDesign::Body")
    agent.check(
        "kept: what cannot follow keeps the original (hidden, renamed) and the answer says so",
        not error
        and "Plate (original)" in labels
        and "kept hidden" in text
        and "QaHolder" in text
        and holder.Uses is own
        and not plate.Visibility,
        (text, labels),
    )


# -- saved half way, opened again ---------------------------------------------------------------
def reopened(agent, folder):
    import FreeCAD as App

    plate = _golden(
        agent,
        "QaReopen",
        [
            ("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40]}]}),
            ("extrude", {"profile": "Sketch1", "distance": 8}),
            (
                "create_sketch",
                {"plane": "XY", "offset": 8, "geometry": [{"circle": [15, 20, 3]}]},
            ),
            ("hole", {"sketch": "Sketch2", "diameter": 6, "through_all": True}),
        ],
        folder,
    )
    agent.call("new_design", {"name": "QaMid"})
    agent.call("import_file", {"path": plate})
    text, error = agent.call("start_rebuild", {"body": "Body001"})
    from . import rebuild_e2e as e2e

    rebuilt_id = e2e.made_id(text) if not error else None
    text, error = agent.call("describe_reference", {})
    plan = (_json(text) or {}).get("plan") or []
    for step in plan[:2]:
        agent.call(step["tool"], step["args"])
    path = os.path.join(folder, "qa_mid.FCStd")
    agent.call("save_as", {"path": path})
    agent.call("close_design", {})
    agent.call("open_design", {"path": path})
    doc = App.ActiveDocument
    made = {}
    for step in plan[2:]:
        args = agent._with_ids(step, made, plan)
        text, error = agent.call(step["tool"], args)
        if not error and e2e.made_id(text):
            made[step.get("step")] = e2e.made_id(text)
    body = doc.getObject(rebuilt_id) if rebuilt_id else None
    text, error = agent.call("compare_to_reference", {})
    result = _json(text) or {}
    agent.check(
        "reopened: the plan carries on in the rebuilt body after the design is opened again",
        body is not None and result.get("done") and len(body.Group) >= 4,
        (text[:400], [o.Name for o in body.Group] if body is not None else None),
    )


# -- the reference deleted some other way than Finish ---------------------------------------------
def deleted_reference(agent, folder):
    import FreeCAD as App

    from sciforge import rebuild

    agent.call("new_design", {"name": "QaDeleted"})
    doc = App.ActiveDocument
    plate = _featureless(doc, "Plate", _plate())
    agent.call("start_rebuild", {"body": plate.Name})
    refs = rebuild.references(doc)
    if not agent.check("deleted reference: a rebuild started", refs, refs):
        return
    text, error = agent.call("delete_step", {"steps": [refs[0].Name]})
    agent.check(
        "deleted reference: the original is shown again (it stayed hidden)",
        not error and bool(plate.Visibility) and not rebuild.references(doc),
        (text, plate.Visibility),
    )
    agent.call("undo", {})
    agent.check(
        "deleted reference: undo brings the rebuild back, the original hidden",
        rebuild.references(doc) and not plate.Visibility,
        plate.Visibility,
    )
    # the same in a design opened again (what start remembered is gone then)
    path = os.path.join(folder, "qa_deleted.FCStd")
    agent.call("save_as", {"path": path})
    agent.call("close_design", {})
    agent.call("open_design", {"path": path})
    doc = App.ActiveDocument
    refs = rebuild.references(doc)
    original = doc.getObject(refs[0].SourceName) if refs else None
    text, error = agent.call("delete_step", {"steps": [refs[0].Name]} if refs else {})
    agent.check(
        "deleted reference: in a design opened again the original is shown again too",
        not error and original is not None and bool(original.Visibility),
        (text, getattr(original, "Visibility", None)),
    )


# -- a threaded hole (recognition cannot read a thread: it must say so, quickly) ---------------
def threaded(agent, folder):
    import time

    path = _golden(
        agent,
        "QaThread",
        [
            ("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]}),
            ("extrude", {"profile": "Sketch1", "distance": 10}),
            ("create_sketch", {"plane": "XY", "offset": 10, "geometry": [{"circle": [20, 15, 3]}]}),
            ("hole", {"sketch": "Sketch2", "diameter": 6, "through_all": True}),
            (
                "thread",
                {"faces": {"type": "cylinder", "count": 1}, "designation": "M6x1", "modeled": True},
            ),
        ],
        folder,
    )
    agent.call("new_design", {"name": "QaThreaded"})
    agent.call("import_file", {"path": path})
    agent.call("start_rebuild", {"body": "Body001"})
    began = time.time()
    text, error = agent.call("describe_reference", {})
    took = time.time() - began
    data = _json(text) or {}
    plan = data.get("plan") or []
    tools = [s["tool"] for s in plan]
    why = " ".join(u.get("why", "") for u in data.get("unrecognized") or [])
    agent.check(
        "threaded: describe_reference reads the plate and the hole in seconds (it took 210 s "
        "in OpenCASCADE's defeaturing, then read nothing) (%.1f s)" % took,
        not error and took < 20 and "extrude" in tools and "hole" in tools,
        (took, tools, data.get("notes")),
    )
    agent.check(
        "threaded: the thread is said, not guessed (unrecognized, with what to do)",
        "thread" in why and "not read" in why and "thread tool" in why,
        why,
    )
    made, failed = {}, []
    from . import rebuild_e2e as e2e

    for step in plan:
        args = agent._with_ids(step, made, plan)
        text, error = agent.call(step["tool"], args)
        if error:
            failed.append((step["tool"], text[:200]))
        elif e2e.made_id(text):
            made[step.get("step")] = e2e.made_id(text)
    text, error = agent.call("compare_to_reference", {})
    result = _json(text) or {}
    agent.check(
        "threaded: every plan step runs and the plain plate matches but for the thread",
        not failed and result.get("match", 0) > 0.999 and not result.get("done"),
        (failed, result.get("verdict")),
    )


# -- a jointed part driven while it is rebuilt ---------------------------------------------------
def driven(agent, folder):
    import FreeCAD as App

    from sciforge import rebuild

    arm = _golden(agent, "QaArm2", ARM, folder)
    base = _golden(agent, "QaBase2", BASE, folder)
    agent.call("new_design", {"name": "QaDriven"})
    agent.call("import_file", {"path": arm})
    agent.call("import_file", {"path": base})
    doc = App.ActiveDocument
    agent.call("ground", {"component": "Component001"})
    agent.call(
        "joint",
        {
            "type": "revolute",
            "first": {
                "component": "Component",
                "face": {"type": "cylinder", "count": 1, "at": {"axis": "x", "value": "min"}},
                "snap": "circle",
            },
            "second": {
                "component": "Component001",
                "face": {"type": "cylinder", "count": 1},
                "snap": "circle",
            },
        },
    )
    agent.call("drive_joint", {"joint": "Joint", "angle": 30})
    from sciforge import bodies

    at_30 = App.BoundBox(bodies.global_shape(doc.getObject("Body001")).BoundBox)
    agent.call("start_rebuild", {"body": "Body001"})
    text, error = agent.call("describe_reference", {})
    plan = (_json(text) or {}).get("plan") or []
    first = json.dumps(plan[0]["args"], sort_keys=True) if plan else ""
    # the person turns the arm while the AI works: the reference turns with it
    text, error = agent.call("drive_joint", {"joint": "Joint", "angle": 75})
    agent.check("driven: the arm turns during the rebuild", not error, text)
    ref = rebuild.references(doc)[0]
    target = rebuild.target_of(ref)
    text, error = agent.call("describe_reference", {})
    again = (_json(text) or {}).get("plan") or []
    agent.check(
        "driven: the plan is the same after the arm turned (it was read turned away)",
        again and json.dumps(again[0]["args"], sort_keys=True) == first,
        (first, again[0]["args"] if again else None),
    )
    result = rebuild_through_tools(agent, None, plan=again)
    agent.check(
        "driven: the rebuild matches although the arm turned (match was 0.16)",
        result.get("done"),
        result.get("verdict"),
    )
    gap = rebuild.reference_shape(ref).BoundBox.Center - bodies.global_shape(target).BoundBox.Center
    agent.check("driven: the reference stands where the arm is now", gap.Length < 1e-6, gap)
    agent.call("finish_rebuild", {})
    agent.call("drive_joint", {"joint": "Joint", "angle": 30})
    box = bodies.global_shape(target).BoundBox
    off = max(
        abs(a - b)
        for a, b in zip(
            (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax),
            (at_30.XMin, at_30.YMin, at_30.ZMin, at_30.XMax, at_30.YMax, at_30.ZMax),
        )
    )
    agent.check(
        "driven: turned back to 30 degrees the rebuilt arm is where the original was (it was "
        "built turned inside its component)",
        off < 1e-6,
        (box, at_30),
    )


# -- a VEX plate: 125 square holes (506 faces) -------------------------------------------------
def vex_plate(agent, folder):
    import time

    import FreeCAD as App
    import Part

    inch = 25.4
    plate = Part.makeBox(25 * 0.5 * inch, 5 * 0.5 * inch, 0.0625 * inch)
    side = 0.182 * inch
    cutters = [
        Part.makeBox(
            side,
            side,
            inch,
            App.Vector((0.25 + 0.5 * i) * inch - side / 2, (0.25 + 0.5 * j) * inch - side / 2, -9),
        )
        for i in range(25)
        for j in range(5)
    ]
    plate = plate.cut(Part.makeCompound(cutters)).removeSplitter()
    path = os.path.join(folder, "qa_vex_plate.step")
    plate.exportStep(path)
    agent.call("new_design", {"name": "QaVexPlate"})
    agent.call("import_file", {"path": path})
    agent.call("start_rebuild", {"body": "Body001"})
    began = time.time()
    text, error = agent.call("describe_reference", {})
    took = time.time() - began
    data = _json(text) or {}
    plan = data.get("plan") or []
    agent.check(
        "vex plate: describe_reference reads the 506 faces in seconds (56 s before: a section "
        "and a boolean for each of the 50 levels along X) (%.1f s)" % took,
        not error and took < 25 and len(plan) <= 6,
        (took, [st["tool"] for st in plan]),
    )
    result = rebuild_through_tools(agent, None, plan=plan)
    agent.check("vex plate: the plan rebuilds it (done)", result.get("done"), result.get("verdict"))


# -- the id import_file answers with is the component's ------------------------------------------
def component_id(agent, folder):
    import FreeCAD as App

    from sciforge import rebuild

    path = _golden(agent, "QaArm3", ARM, folder)
    agent.call("new_design", {"name": "QaComponentId"})
    text, error = agent.call("import_file", {"path": path})
    from . import rebuild_e2e as e2e

    ident = e2e.made_id(text)  # ("Its id is 'Component'": the component)
    text, error = agent.call("start_rebuild", {"body": ident or "Component"})
    refs = rebuild.references(App.ActiveDocument)
    agent.check(
        "component id: start_rebuild takes the component import_file named (its one body; it "
        "said to pick a body)",
        not error and refs and refs[0].SourceName == "Body001",
        (ident, text[:300]),
    )


# -- a body whose extrude also cuts another body --------------------------------------------------
def follower(agent, folder):
    import FreeCAD as App

    agent.call("new_design", {"name": "QaFollower"})
    doc = App.ActiveDocument
    agent.call("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]})
    agent.call("extrude", {"profile": "Sketch1", "distance": 10})
    text, error = agent.call("new_body", {})
    agent.call("create_sketch", {"plane": "XY", "geometry": [{"rect": [40, 0, 80, 30]}]})
    agent.call("extrude", {"profile": "Sketch2", "distance": 10})
    agent.call("activate", {"target": "Body"})
    # a slot cut through both blocks by the first body's extrude
    agent.call(
        "create_sketch", {"plane": "XY", "offset": 10, "geometry": [{"rect": [30, 10, 50, 20]}]}
    )
    text, error = agent.call(
        "extrude",
        {
            "profile": "Sketch3",
            "distance": 5,
            "operation": "cut",
            "flip": True,
            "bodies": ["Body", "Body001"],
        },
    )
    other = doc.getObject("Body001")
    before = other.Shape.Volume if other is not None and not other.Shape.isNull() else None
    if not agent.check(
        "follower: the first body's cut goes into the other body too",
        not error and before is not None and abs(before - (12000 - 10 * 10 * 5)) < 1e-3,
        (text[:300], before),
    ):
        return
    result = rebuild_through_tools(agent, "Body")
    if not agent.check("follower: the first body is rebuilt (done)", result.get("done"), result):
        return
    text, error = agent.call("finish_rebuild", {})
    doc.recompute()
    agent.check(
        "follower: the other body keeps the cut the original's extrude made in it (the "
        "original is kept for it; deleting it took the cut away)",
        not error
        and abs(other.Shape.Volume - before) < 1e-3
        and "kept hidden" in text
        and doc.getObject("Body") is not None,
        (text[:400], other.Shape.Volume, before),
    )


# -- check_design while a rebuild goes on ----------------------------------------------------------
def checked_midway(agent, folder):
    path = _golden(agent, "QaArm4", ARM, folder)
    agent.call("new_design", {"name": "QaMidway"})
    agent.call("import_file", {"path": path})
    rebuild_through_tools(agent, "Body001")
    text, error = agent.call("check_design", {})
    report = _json(text) or {}
    agent.check(
        "midway: check_design does not take the original under its rebuild for an overlap (it "
        "said NOT OK: 'Bodies Body001 and Body001 (rebuilt) overlap')",
        not error and report.get("ok") is True and "being rebuilt" in text,
        text[:500],
    )


# -- holes with a chamfered rim, the base built only ---------------------------------------------
def chamfered_rim(agent, folder):
    path = _golden(
        agent,
        "QaRim",
        [
            ("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]}),
            ("extrude", {"profile": "Sketch1", "distance": 10}),
            (
                "create_sketch",
                {
                    "plane": "XY",
                    "offset": 10,
                    "geometry": [{"circle": [10, 15, 2.5]}, {"circle": [30, 15, 2.5]}],
                },
            ),
            ("hole", {"sketch": "Sketch2", "diameter": 5, "through_all": True}),
            (
                "chamfer",
                {"edges": {"type": "circle", "at": {"axis": "z", "value": "max"}}, "distance": 0.5},
            ),
        ],
        folder,
    )
    agent.call("new_design", {"name": "QaRimRebuild"})
    agent.call("import_file", {"path": path})
    agent.call("start_rebuild", {"body": "Body001"})
    agent.call("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 40, 30]}]})
    agent.call("extrude", {"profile": "Sketch1", "distance": 10})
    text, error = agent.call("compare_to_reference", {})
    agent.check(
        "chamfered rim: compare calls the holes' chamfered rims what they are (it said 'with a "
        "pointed (drilled) end')",
        not error and "widened rim" in text and "pointed" not in text,
        text[:400],
    )


# -- a VEX C-channel: square holes in the web and both flanges ---------------------------------
def vex_channel(agent, folder):
    import time

    import FreeCAD as App
    import Part

    from sciforge import recognize

    inch, V = 25.4, App.Vector
    length, width, height, wall = 12.5 * inch, 1.0 * inch, 0.5 * inch, 0.046 * inch
    channel = Part.makeBox(length, width, height).cut(
        Part.makeBox(length, width - 2 * wall, height, V(0, wall, wall))
    )
    side = 0.182 * inch
    cutters = []
    for i in range(25):
        x = (0.25 + 0.5 * i) * inch - side / 2
        for j in range(2):  # the web: two rows
            cutters.append(
                Part.makeBox(side, side, 3 * wall, V(x, (0.25 + 0.5 * j) * inch - side / 2, -wall))
            )
        for y0 in (-wall, width - 2 * wall):  # the flanges: one row each
            z = 0.25 * inch + wall / 2 - side / 2
            cutters.append(Part.makeBox(side, 3 * wall, side, V(x, y0, z)))
    channel = channel.cut(Part.makeCompound(cutters)).removeSplitter()
    read = []
    kept = recognize._prismatic

    def counting(solid, axis_name, lenient=False):
        read.append(axis_name)
        return kept(solid, axis_name, lenient)

    recognize._prismatic = counting
    try:
        began = time.time()
        out = recognize.describe(channel, {})
        took = time.time() - began
    finally:
        recognize._prismatic = kept
    agent.check(
        "vex channel: the 410-face C-channel is read along two axes, not the one with its 51 "
        "levels of square holes (describe took 37 s) (%.1f s, read %s)" % (took, read),
        "X" not in read and out["base"].get("kind") == "extrude" and out["confidence"] >= 0.99,
        (read, out["base"].get("kind"), out["confidence"]),
    )


# -- a plate with a boss and holes on the same face ----------------------------------------------
def bossed_plate(agent, folder):
    import time

    import FreeCAD as App
    import Part

    from sciforge import recognize

    V = App.Vector
    plate = Part.makeBox(200, 120, 6).fuse(Part.makeCylinder(12, 8, V(100, 60, 6)))
    cutters = []
    for i in range(60):
        x, y = 10 + (i % 18) * 10.5, 10 + (i // 18) * 10.0
        if abs(x - 100) >= 20 or abs(y - 60) >= 20:
            cutters.append(Part.makeCylinder(2, 6, V(x, y, 0)))
    plate = plate.removeSplitter().cut(Part.makeCompound(cutters)).removeSplitter()
    reader = recognize._Reader(plate, {})
    holes = reader.find_holes()
    _solid, closed, _left = reader._drop_holes(holes)
    began = time.time()
    out = recognize.describe(plate, {})
    took = time.time() - began
    agent.check(
        "bossed plate: the %d holes in the face the boss stands on are closed by their rims "
        "(none were: the face keeps the boss's loop, Face.cutHoles answers None; all went to "
        "OpenCASCADE's defeaturing, 12.7 s) (%d closed, describe %.1f s)"
        % (len(holes), len(closed), took),
        len(holes) == len(cutters)
        and len(closed) == len(holes)
        and out["base"].get("kind") == "extrude"
        and out["confidence"] >= 0.99,
        (len(holes), len(closed), out["base"].get("kind"), out["confidence"]),
    )
    path = os.path.join(folder, "qa_bossed_plate.step")
    plate.exportStep(path)
    agent.call("new_design", {"name": "QaBossedPlate"})
    agent.call("import_file", {"path": path})
    result = rebuild_through_tools(agent, "Body001")
    agent.check("bossed plate: the plan rebuilds it (done)", result.get("done"), result)


# -- raised and engraved text on a plate -----------------------------------------------------------
def _font():
    """A font FreeCAD itself ships (DejaVu Sans Bold when there), None when none is found."""
    from sciforge import text

    files = text.freecad_font_files()
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        for path in files:
            if os.path.basename(path) == name:
                return path
    return files[0] if files else None


def text_plate(agent, folder):
    import FreeCAD as App
    import Part

    from . import rebuild_e2e as e2e

    font = _font()
    agent.check("text: a font FreeCAD ships is found", font is not None, font)
    if font is None:
        return
    V = App.Vector
    for mode in ("raised", "engraved"):
        plate = Part.makeBox(80, 30, 5).cut(Part.makeCylinder(3, 5, V(70, 15, 0)))
        letters = []
        for char in Part.makeWireString("VEX OK", font, 10, 0):
            if char:
                face = Part.makeFace(list(char), "Part::FaceMakerBullseye")
                face.translate(V(6, 10, 5))
                letters.append(face.extrude(V(0, 0, 1 if mode == "raised" else -1)))
        text = Part.makeCompound(letters)
        part = (plate.fuse(text) if mode == "raised" else plate.cut(text)).removeSplitter()
        path = os.path.join(folder, "qa_text_%s.step" % mode)
        part.exportStep(path)
        agent.call("new_design", {"name": "QaText_" + mode})
        agent.call("import_file", {"path": path})
        agent.call("start_rebuild", {"body": "Body001"})
        answer, error = agent.call("describe_reference", {})
        data = _json(answer) or {}
        plan = data.get("plan") or []
        tools = [s["tool"] for s in plan]
        why = " ".join(u.get("why", "") for u in data.get("unrecognized") or [])
        agent.check(
            "%s text: the plate and its hole are read, the free-form letters said (not read) "
            "with what to do (the base was 'none': every face unrecognized, a plan of a sketch "
            "and a hole that failed)" % mode,
            not error
            and (data.get("base") or {}).get("kind") == "extrude"
            and "hole" in tools
            and ("%s free-form shape" % mode) in why
            and "sketch_text" in why,
            (tools, data.get("base"), why[:300], data.get("notes")),
        )
        made, failed = {}, []
        for step in plan:
            args = agent._with_ids(step, made, plan)
            answer, error = agent.call(step["tool"], args)
            if error:
                failed.append((step["tool"], answer[:200]))
            elif e2e.made_id(answer):
                made[step.get("step")] = e2e.made_id(answer)
        answer, error = agent.call("compare_to_reference", {})
        result = _json(answer) or {}
        agent.check(
            "%s text: every plan step runs; the rebuild matches but for the letters" % mode,
            not failed and result.get("match", 0) > 0.98,
            (failed, result.get("verdict")),
        )


# -- Stop Rebuild: a rebuild given up in a design opened again (no undo history) -----------------
def stopped(agent, folder):
    import FreeCAD as App

    from sciforge import bodies, rebuild

    agent.call("new_design", {"name": "QaStop"})
    doc = App.ActiveDocument
    plate = _featureless(doc, "Plate", _plate())
    agent.call("start_rebuild", {"body": plate.Name})
    agent.call("create_sketch", {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40]}]})
    agent.call("extrude", {"profile": "Sketch1", "distance": 8})
    path = os.path.join(folder, "qa_stop.FCStd")
    agent.call("save_as", {"path": path})
    agent.call("close_design", {})
    agent.call("open_design", {"path": path})
    doc = App.ActiveDocument
    refs = rebuild.active_references(doc)
    has_stop = hasattr(rebuild, "stop")
    if not agent.check(
        "stopped: a rebuild going on in a design opened again can be stopped (there was no "
        "way back but Undo, and no undo history there)",
        len(refs) == 1 and has_stop,
        (refs, has_stop),
    ):
        return
    ref = refs[0]
    ref_name = ref.Name  # (a removed object has no name any more)
    target_name = rebuild.target_of(ref).Name
    original = rebuild.source_of(ref)
    steps = [o.Name for o in rebuild.target_of(ref).Group]
    doc.openTransaction("Stop Rebuild")
    rebuild.stop(ref)
    doc.commitTransaction()
    doc.recompute()
    agent.check(
        "stopped: the original is shown again, the reference and the rebuilt body (with its "
        "steps) are gone",
        not rebuild.references(doc)
        and bool(original.Visibility)
        and doc.getObject(target_name) is None
        and not any(doc.getObject(n) is not None for n in steps),
        (
            [r.Name for r in rebuild.references(doc)],
            original.Visibility,
            doc.getObject(target_name),
            [n for n in steps if doc.getObject(n) is not None],
        ),
    )
    doc.undo()
    ref = doc.getObject(ref_name)
    agent.check(
        "stopped: Undo brings the rebuild back (the original hidden again)",
        ref is not None
        and rebuild.target_of(ref) is not None
        and not original.Visibility
        and len(rebuild.target_of(ref).Group) == len(steps),
        (ref, original.Visibility),
    )
    doc.openTransaction("Stop Rebuild")
    rebuild.stop(ref, keep_rebuilt=True)
    doc.commitTransaction()
    doc.recompute()
    kept = doc.getObject(target_name)
    agent.check(
        "stopped: keeping the rebuilt body leaves it as a body of its own, its steps kept",
        not rebuild.references(doc)
        and bool(original.Visibility)
        and kept is not None
        and len(kept.Group) == len(steps)
        and bodies.has_solid(kept),
        (kept, original.Visibility),
    )
    text, error = agent.call("start_rebuild", {"body": original.Name})
    agent.check(
        "stopped: the original can be rebuilt again afterwards",
        not error and len(rebuild.active_references(doc)) == 1,
        text[:300],
    )
    # the original deleted by hand meanwhile: stopping keeps what was rebuilt
    live = rebuild.active_references(doc)
    again = rebuild.target_of(live[0]).Name if live else None
    agent.call("delete_bodies", {"bodies": [original.Name]})
    try:
        doc.openTransaction("Stop Rebuild")
        rebuild.stop(live[0], keep_rebuilt=True)
        doc.commitTransaction()
        stopped_ok = True
    except Exception as exc:
        doc.abortTransaction()
        stopped_ok = exc
    agent.check(
        "stopped: with the original deleted meanwhile, Stop keeps the rebuilt body",
        stopped_ok is True and not rebuild.references(doc) and doc.getObject(again) is not None,
        (stopped_ok, again),
    )


# -- meshes: a big one refused at once, a small one made into a solid once ----------------------
def _plate_mesh(folder, name, angular):
    import MeshPart

    path = os.path.join(folder, name)
    mesh = MeshPart.meshFromShape(
        Shape=_plate(), LinearDeflection=0.001, AngularDeflection=angular, Relative=False
    )
    mesh.write(path)
    return path, mesh.CountFacets


def big_mesh(agent, folder):
    import time

    from sciforge import insert
    from . import rebuild_e2e as e2e

    path, count = _plate_mesh(folder, "qa_big_mesh.stl", 0.006)
    agent.call("new_design", {"name": "QaBigMesh"})
    text, error = agent.call("import_file", {"path": path})
    began = time.time()
    text, error = agent.call("start_rebuild", {"body": e2e.made_id(text)})
    took = time.time() - began
    agent.check(
        "big mesh: a mesh of %d triangles is refused at once, with the reason and what to do "
        "(it took minutes: 160 s for 37,740, then describe as long again) (%.1f s)" % (count, took),
        count > 10000 and error and "Reduce" in text and took < 10,
        (count, took, text[:300]),
    )
    path, count = _plate_mesh(folder, "qa_small_mesh.stl", 0.2)
    agent.call("new_design", {"name": "QaSmallMesh"})
    text, error = agent.call("import_file", {"path": path})
    agent.call("start_rebuild", {"body": e2e.made_id(text)})
    made = []
    kept = insert.solid_from_mesh

    def counting(*args, **kwargs):
        made.append(1)
        return kept(*args, **kwargs)

    insert.solid_from_mesh = counting
    try:
        text, error = agent.call("describe_reference", {})
    finally:
        insert.solid_from_mesh = kept
    data = _json(text) or {}
    agent.check(
        "small mesh: describe_reference reads the reference's solid, not the triangles made "
        "into a solid again (%d made)" % len(made),
        not error and not made and (data.get("base") or {}).get("kind") == "extrude",
        (len(made), (data.get("base") or {}).get("kind"), text[:200]),
    )


CHECKS = (
    jointed,
    dependents,
    kept,
    reopened,
    deleted_reference,
    threaded,
    driven,
    vex_plate,
    component_id,
    follower,
    checked_midway,
    chamfered_rim,
    vex_channel,
    bossed_plate,
    text_plate,
    stopped,
    big_mesh,
)


def run(agent):
    """Every QA check (each in designs of its own; closed after)."""
    from .rebuild_e2e import _close_all

    folder = tempfile.mkdtemp(prefix="sciforge-rebuild-qa-")
    for check in CHECKS:
        try:
            check(agent, folder)
        except Exception:
            agent.check("%s: the run" % check.__name__, False, traceback.format_exc())
        _close_all()

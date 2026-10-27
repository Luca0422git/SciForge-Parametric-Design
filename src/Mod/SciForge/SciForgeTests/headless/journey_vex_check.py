# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless checks of the bugs the VEX journey found (scenarios/journey_vex*.py), in real
FreeCAD without a window (run by SciForgeTests/unit/test_journey_vex_freecad.py). Each check
prints one line:

    journeyvex OK <name>
    journeyvex FAIL <name>: <what was found>

and the run ends with "journeyvex done <count>". SciForge's own VEX-like parts
(SciForgeTests/fixtures/vex), never VEX's files.
"""

import os
import tempfile
import traceback

import FreeCAD as App

V = App.Vector
RESULTS = []


def _out(name, ok, detail=""):
    RESULTS.append((name, ok))
    if ok:
        print("journeyvex OK %s" % name, flush=True)
    else:
        print("journeyvex FAIL %s: %s" % (name, detail), flush=True)


def _folder():
    path = os.path.join(tempfile.gettempdir(), "sciforge-journeyvex-%d" % os.getpid())
    os.makedirs(path, exist_ok=True)
    return path


def _files(names):
    from SciForgeTests.fixtures.vex import vex_parts as vp

    return vp.write_all(os.path.join(_folder(), "parts"), names)


def _insert(doc, path, placement=None):
    from sciforge import exchange_core, step_import

    doc.openTransaction("Insert STEP")
    made = step_import.import_file(doc, path, exchange_core.INSERT)
    doc.commitTransaction()
    if placement is not None:
        made.top.Placement = placement
    doc.recompute()
    return made.top


def _body(doc, comp):
    from sciforge import components

    return components.bodies_in(doc, comp, recursive=True)[0]


def _face(doc, comp, test):
    for i, face in enumerate(_body(doc, comp).Shape.Faces):
        if test(face):
            return "Face%d" % (i + 1)
    return None


def _close(doc):
    try:
        App.closeDocument(doc.Name)
    except Exception:
        pass


def _jointed_design(name):
    """Two short C-channels (A at the origin, B in front of it) and a standoff jointed onto A's
    hole (1, 1) the way the Joint dialog leaves it (the baseline saved on OK)."""
    from sciforge import joints
    from SciForgeTests.fixtures.vex import vex_parts as vp

    files = _files(["c_channel_1x2x1x5", "c_channel_1x2x1x5_round", "standoff_1in"])
    doc = App.newDocument(name)
    doc.UndoMode = 1
    a = _insert(doc, files["c_channel_1x2x1x5"])
    b = _insert(doc, files["c_channel_1x2x1x5_round"], App.Placement(V(0, -45, 0), App.Rotation()))
    c = _insert(doc, files["standoff_1in"], App.Placement(V(80, 0, 0), App.Rotation()))
    t = vp.AL
    web = _face(
        doc,
        a,
        lambda f: f.Surface.TypeId == "Part::GeomPlane"
        and abs(f.BoundBox.ZMin - t) < 1e-9
        and f.BoundBox.ZLength < 1e-9
        and f.BoundBox.YLength > 20,
    )
    end = _face(
        doc,
        c,
        lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax) < 1e-9,
    )
    hole = V(vp.PITCH * 1.5, vp.PITCH * 1.5, t)
    doc.openTransaction("Joint")
    p1 = joints.Pick(c, _body(doc, c), end)
    p2 = joints.Pick(a, _body(doc, a), web, hole)
    s1 = [x for x in joints.snap_candidates(p1) if x["kind"] in ("centre", "loop")][0]
    s2 = joints.nearest_snap([x for x in joints.snap_candidates(p2) if x["kind"] == "loop"], hole)
    joint = joints.create_joint(doc, "rigid", p1, s1, p2, s2)
    joints.align(joint, first=True)
    joints.save_baseline(doc)
    doc.commitTransaction()
    doc.recompute()
    return doc, a, b, c, hole


def _align_b_onto_a(doc, a, b, hole):
    """MODIFY > Align (Components) of B's web hole (1, 1) onto A's hole (3, 1), as the dialog
    builds it, then OK (align.settle, inside the dialog's undo step)."""
    from sciforge import align, align_core
    from SciForgeTests.fixtures.vex import vex_parts as vp

    t = vp.AL
    src = b.Placement.multVec(V(vp.PITCH * 1.5, vp.PITCH * 1.5, t))
    dst = V(vp.PITCH * 3.5, vp.PITCH * 1.5, t)
    options = {
        "objects": "components",
        "from_frame": align_core.frame(src, V(0, 0, 1), True),
        "to_frame": align_core.frame(dst, V(0, 0, 1), True),
    }
    doc.openTransaction("Align")
    steps = align.build(options, target=b)
    doc.recompute()
    settle = getattr(align, "settle", None)
    if settle is not None:
        settle(steps)
    doc.commitTransaction()
    return steps, dst


# -- an Align of components in a jointed design is not a pending move ---------------------------
def check_align_is_not_a_pending_move():
    """Before: after an Align of a component in a design with joints, the next Joint asked to
    Capture Position or Revert (the Align counted as a drag), and Revert put the component
    back where it was while the Align step stayed in the timeline."""
    from sciforge import joints

    doc, a, b, c, hole = _jointed_design("JourneyVexAlignCapture")
    try:
        _out("align_capture: not dirty before", not joints.positions_dirty(doc))
        before = App.Placement(b.Placement)
        steps, dst = _align_b_onto_a(doc, a, b, hole)
        moved = not b.Placement.isSame(before, 1e-9)
        _out("align_capture: B moved by the Align", moved and len(steps) == 1, b.Placement)
        _out(
            "align_capture: the Align is not a pending move (no Capture Position question)",
            not joints.positions_dirty(doc),
            "dirty after the Align",
        )
        aligned = App.Placement(b.Placement)
        # Undo takes the Align and its acceptance back together; Redo brings both
        doc.undo()
        doc.recompute()
        _out(
            "align_capture: Undo of the Align: B back, nothing pending",
            b.Placement.isSame(before, 1e-9) and not joints.positions_dirty(doc),
            (b.Placement, joints.positions_dirty(doc)),
        )
        doc.redo()
        doc.recompute()
        _out(
            "align_capture: Redo: B aligned again, nothing pending",
            b.Placement.isSame(aligned, 1e-9) and not joints.positions_dirty(doc),
            (b.Placement, joints.positions_dirty(doc)),
        )
        joints.revert_position(doc)
        doc.recompute()
        _out(
            "align_capture: Revert keeps B where the Align put it",
            b.Placement.isSame(aligned, 1e-9),
            (b.Placement, aligned),
        )
        # a part moved by hand afterwards is still pending (only the Align's part accepted)
        b.Placement = App.Placement(V(0, 0, 30), App.Rotation()).multiply(b.Placement)
        _out("align_capture: a later drag is still pending", joints.positions_dirty(doc))
        joints.revert_position(doc)
        _out(
            "align_capture: ... and Revert takes the drag back to the Align's place",
            b.Placement.isSame(aligned, 1e-9),
            b.Placement,
        )
    finally:
        _close(doc)


def check_align_after_a_captured_position():
    """The same with a captured Position step in the timeline (its placements say where the
    parts it knows belong)."""
    from sciforge import joints

    doc, a, b, c, hole = _jointed_design("JourneyVexAlignPosition")
    try:
        doc.openTransaction("Capture Position")
        joints.capture_position(doc)
        doc.commitTransaction()
        _out("align_position: a Position step", len(joints.positions(doc)) == 1)
        _align_b_onto_a(doc, a, b, hole)
        _out(
            "align_position: the Align is not a pending move",
            not joints.positions_dirty(doc),
            "dirty after the Align",
        )
    finally:
        _close(doc)


# -- a drawing's balloons on parts inside moved components ---------------------------------------
def check_balloons_on_moved_components():
    """Before: the balloons of a parts list looked for each part along sight lines in design
    coordinates but tested the bodies where they sit inside their components: in a design of
    inserted parts (every component moved: the VEX robot) no line ever hit, so each row walked
    every visible edge of the view (TABLES > Table took over 10 minutes on the 22-part VEX
    piece, the window frozen) and the balloons pointed at the wrong part or nowhere."""
    import time

    from sciforge import drawing

    files = _files(["c_channel_1x2x1x5", "keps_nut"])
    doc = App.newDocument("JourneyVexBalloons")
    try:
        a = _insert(doc, files["c_channel_1x2x1x5"], App.Placement(V(40, 30, 0), App.Rotation()))
        b = _insert(doc, files["keps_nut"], App.Placement(V(150, 30, 0), App.Rotation()))
        ba, bb = _body(doc, a), _body(doc, b)
        page = drawing.create_drawing(doc, [ba, bb])
        view = drawing.add_base_view(page, [ba, bb], 150.0, 150.0, "Top", scale=1.0)
        doc.recompute()
        # a point of the view on the nut (its washer, 4 mm right of its axis) and on the channel
        from sciforge import drawing_core as core

        axes = drawing.axes_of(view)
        centre = drawing.centre_of(view)

        def local_of(p):
            d = (p.x - centre[0], p.y - centre[1], p.z - centre[2])
            return (core.v_dot(d, axes[0]), core.v_dot(d, axes[1]))

        on_nut = local_of(V(150 + 4.0, 30, 0))
        on_channel = local_of(V(40 + 30.0, 30 + 6.35 + 3.6, 1.0))
        found = drawing.component_at(view, on_nut)
        _out(
            "balloons: a point of the view on the nut (in a moved component) is the nut's",
            found is bb,
            found and found.Label,
        )
        found = drawing.component_at(view, on_channel)
        _out(
            "balloons: a point on the channel's web is the channel's",
            found is ba,
            found and found.Label,
        )
        t0 = time.time()
        table, made = drawing.add_parts_list(page, view, (300.0, 120.0))
        seconds = time.time() - t0
        _out("balloons: a balloon per row", len(made) == 2, len(made))
        _out("balloons: the parts list and its balloons in under 5 s", seconds < 5.0, seconds)
        owners = []
        for balloon in made:
            origin, _spot = drawing.balloon_page_points(balloon)
            body = drawing.component_at(view, drawing.page_to_local(view, origin))
            owners.append(body.Label if body is not None else None)
        _out(
            "balloons: each balloon's arrow on its own part",
            sorted(owners) == sorted([ba.Label, bb.Label]) and len(set(owners)) == 2,
            owners,
        )
    finally:
        _close(doc)


def check_balloons_quick_on_a_big_part():
    """Before: every edge tried for a balloon measured every part of the view again (the
    view's centre), so the parts list of the VEX piece took 140 s headless (more in the
    window, frozen): now the centre is measured once per parts list (8 s)."""
    import time

    from sciforge import drawing

    files = _files(["c_channel_1x2x1x25", "keps_nut", "standoff_1in", "screw_8_32_x_0_5"])
    doc = App.newDocument("JourneyVexBalloonsBig")
    try:
        found = []
        for k, (name, at) in enumerate(
            (
                ("c_channel_1x2x1x25", V(10, 20, 0)),
                ("keps_nut", V(60, -20, 0)),
                ("standoff_1in", V(120, -20, 0)),
                ("screw_8_32_x_0_5", V(180, -20, 0)),
            )
        ):
            found.append(_body(doc, _insert(doc, files[name], App.Placement(at, App.Rotation()))))
        page = drawing.create_drawing(doc, found)
        view = drawing.add_base_view(page, found, 200.0, 150.0, "Top", scale=0.5)
        doc.recompute()
        calls = {"n": 0}
        measure = drawing.centre_of

        def counted(*args, **kwargs):
            calls["n"] += 1
            return measure(*args, **kwargs)

        drawing.centre_of = counted
        try:
            t0 = time.time()
            _table, made = drawing.add_parts_list(page, view, (300.0, 250.0))
            seconds = time.time() - t0
        finally:
            drawing.centre_of = measure
        _out("balloons big: a balloon per part", len(made) == 4, len(made))
        _out(
            "balloons big: the parts (the view's centre) measured once, not once per edge tried",
            calls["n"] <= 2,
            calls["n"],
        )
        _out(
            "balloons big: the parts list of a 1x2x1x25 channel and three parts in under 10 s",
            seconds < 10.0,
            "%.1f s" % seconds,
        )
    finally:
        _close(doc)


CHECKS = [
    check_align_is_not_a_pending_move,
    check_align_after_a_captured_position,
    check_balloons_on_moved_components,
    check_balloons_quick_on_a_big_part,
]


def main():
    for check in CHECKS:
        try:
            check()
        except Exception:
            _out(check.__name__, False, traceback.format_exc().replace("\n", " | "))
    print("journeyvex done %d" % len(CHECKS), flush=True)
    import shutil

    shutil.rmtree(_folder(), ignore_errors=True)

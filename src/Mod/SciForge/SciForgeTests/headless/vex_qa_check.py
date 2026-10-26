# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless checks of beta 3's VEX work found by its QA (run in real FreeCAD without a window
by SciForgeTests/unit/test_vex_qa_freecad.py). Each check prints one line:

    vexqa OK <name>
    vexqa FAIL <name>: <what was found>

and the run ends with "vexqa done <count>". SciForge's own VEX-like parts
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
        print("vexqa OK %s" % name, flush=True)
    else:
        print("vexqa FAIL %s: %s" % (name, detail), flush=True)


def _folder():
    path = os.path.join(tempfile.gettempdir(), "sciforge-vexqa-%d" % os.getpid())
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
    return made


def _body(doc, comp):
    from sciforge import components

    return components.bodies_in(doc, comp, recursive=True)[0]


def _gbox(doc, comp):
    from sciforge import bodies

    return bodies.global_shape(_body(doc, comp)).BoundBox


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


# -- Duplicate With Joints: a screw and its nut held by a Rigid Group ---------------------------
def check_duplicate_rigid_group():
    """The copies of a screw and its nut that a Rigid Group holds together are held together
    too: a later move of the screw's copy takes the nut's copy along (as the original nut
    goes with the original screw)."""
    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import duplicate_joints as dj
    from sciforge import joints

    files = _files(["c_channel_1x2x1x5", "screw_8_32_x_0_5", "keps_nut"])
    doc = App.newDocument("VexQaRigid")
    try:
        channel = _insert(doc, files["c_channel_1x2x1x5"]).top
        screw = _insert(
            doc, files["screw_8_32_x_0_5"], App.Placement(V(-20, 19.05, 20), App.Rotation())
        ).top
        nut = _insert(
            doc, files["keps_nut"], App.Placement(V(-20, 19.05, 20 - 12.7 - 0.2), App.Rotation())
        ).top
        t, p = vp.AL, vp.PITCH

        def hole(i, j):
            return V(p / 2 + i * p, p / 2 + j * p, t)

        web = _face(
            doc,
            channel,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMin - t) < 1e-9
            and f.BoundBox.ZLength < 1e-9
            and f.BoundBox.YLength > 20,
        )
        under = _face(
            doc,
            screw,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMax) < 1e-9
            and len(f.Wires) == 2,
        )
        doc.openTransaction("Rigid Group")
        joints.create_rigid_group(doc, [screw, nut])
        doc.commitTransaction()
        p1 = joints.Pick(screw, _body(doc, screw), under)
        p2 = joints.Pick(channel, _body(doc, channel), web, hole(1, 1))
        s1 = [c for c in joints.snap_candidates(p1) if c["kind"] == "centre"][0]
        s2 = joints.nearest_snap(
            [c for c in joints.snap_candidates(p2) if c["kind"] == "loop"], hole(1, 1)
        )
        doc.openTransaction("Joint")
        joint = joints.create_joint(doc, "rigid", p1, s1, p2, s2)
        joints.align(joint, first=True)
        doc.commitTransaction()
        doc.recompute()
        pick = joints.Pick(channel, _body(doc, channel), web, hole(3, 1))
        snap = joints.nearest_snap(
            [c for c in joints.snap_candidates(pick) if c["kind"] == "loop"], hole(3, 1)
        )
        doc.openTransaction("Duplicate With Joints")
        copies, made = dj.duplicate(doc, [screw, nut], joint, 0, pick, snap)
        doc.commitTransaction()
        doc.recompute()
        by = {c.Label.split(":")[0]: c for c in copies}
        screw2, nut2 = by.get(screw.Label), by.get(nut.Label)
        gap = _gbox(doc, screw2).ZMin - _gbox(doc, nut2).ZMin
        # the copy's joint 5 mm further out: the screw's copy moves up, its nut with it
        doc.openTransaction("Offset")
        joints.set_offset(made[0], z=5.0)
        joints.align(made[0])
        doc.commitTransaction()
        doc.recompute()
        moved = _gbox(doc, screw2).ZMin - _gbox(doc, nut2).ZMin
        groups = [
            sorted(m.Label for m in g.Members)
            for g in joints.rigid_groups(doc)
            if all(m in copies for m in g.Members)
        ]
        _out(
            "duplicate_rigid_group",
            abs(moved - gap) < 1e-4 and groups == [sorted([screw2.Label, nut2.Label])],
            "the nut's copy stayed behind its screw's copy (gap %.4f -> %.4f), groups of the "
            "copies %s" % (gap, moved, groups),
        )
    finally:
        _close(doc)


def check_duplicate_limits():
    """Duplicate With Joints of a shaft on a revolute joint with limits (-30 .. 60 degrees,
    rest 10) and Offset Z: the copy's joint is a revolute with the same limits and offsets,
    and the copy goes through its new hole."""
    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import duplicate_joints as dj
    from sciforge import joints

    files = _files(["c_channel_1x2x1x5", "shaft_3in"])
    doc = App.newDocument("VexQaLimits")
    try:
        channel = _insert(doc, files["c_channel_1x2x1x5"]).top
        shaft = _insert(doc, files["shaft_3in"], App.Placement(V(-20, 60, 0), App.Rotation())).top
        t, p = vp.AL, vp.PITCH

        def hole(i, j):
            return V(p / 2 + i * p, p / 2 + j * p, t)

        web = _face(
            doc,
            channel,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMin - t) < 1e-9
            and f.BoundBox.ZLength < 1e-9
            and f.BoundBox.YLength > 20,
        )
        top = _face(
            doc,
            shaft,
            lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMin - 76.2) < 1e-6,
        )
        p1 = joints.Pick(shaft, _body(doc, shaft), top)
        p2 = joints.Pick(channel, _body(doc, channel), web, hole(1, 1))
        s1 = [c for c in joints.snap_candidates(p1) if c["kind"] == "centre"][0]
        s2 = joints.nearest_snap(
            [c for c in joints.snap_candidates(p2) if c["kind"] == "loop"], hole(1, 1)
        )
        doc.openTransaction("Joint")
        joint = joints.create_joint(doc, "revolute", p1, s1, p2, s2)
        joints.set_offset(joint, z=-38.1)
        joints.set_limits(joint, angle={"min": -30.0, "max": 60.0, "rest": 10.0})
        joints.align(joint, first=True)
        doc.commitTransaction()
        doc.recompute()
        pick = joints.Pick(channel, _body(doc, channel), web, hole(3, 1))
        snap = joints.nearest_snap(
            [c for c in joints.snap_candidates(pick) if c["kind"] == "loop"], hole(3, 1)
        )
        doc.openTransaction("Duplicate With Joints")
        copies, made = dj.duplicate(doc, [shaft], joint, 0, pick, snap)
        doc.commitTransaction()
        doc.recompute()
        box = _gbox(doc, copies[0])
        centre = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        want = hole(3, 1)
        _out(
            "duplicate_limits",
            joints.fusion_type(made[0]) == "revolute"
            and joints.limits(made[0]) == joints.limits(joint)
            and joints.offsets(made[0]) == joints.offsets(joint)
            and abs(centre.x - want.x) < 1e-4
            and abs(centre.y - want.y) < 1e-4
            and abs(box.ZMin - (t - 38.1)) < 1e-3,
            "type %s, limits %s (want %s), offsets %s, the copy %s"
            % (
                joints.fusion_type(made[0]),
                joints.limits(made[0]),
                joints.limits(joint),
                joints.offsets(made[0]),
                box,
            ),
        )
    finally:
        _close(doc)


def check_duplicate_in_place():
    """Duplicate With Joints of a screw's occurrence that sits in a sub-assembly ("Frame"):
    the copy goes into that sub-assembly, beside the screw picked (it went beside the
    original, at the root of the design)."""
    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import components
    from sciforge import duplicate_joints as dj
    from sciforge import exchange_core, joints, step_import

    files = _files(["c_channel_1x2x1x5", "screw_8_32_x_0_5"])
    doc = App.newDocument("VexQaInPlace")
    try:
        frame = components.new_component(doc, "Frame", None)
        channel = _insert(doc, files["c_channel_1x2x1x5"]).top
        _insert(doc, files["screw_8_32_x_0_5"], App.Placement(V(-20, 19.05, 20), App.Rotation()))
        doc.openTransaction("Insert STEP")
        made = step_import.import_file(doc, files["screw_8_32_x_0_5"], exchange_core.INSERT, frame)
        doc.commitTransaction()
        screw = made.top  # an occurrence of the first screw, in Frame
        screw.Placement = App.Placement(V(-40, 19.05, 20), App.Rotation())
        doc.recompute()
        t, p = vp.AL, vp.PITCH

        def hole(i, j):
            return V(p / 2 + i * p, p / 2 + j * p, t)

        web = _face(
            doc,
            channel,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMin - t) < 1e-9
            and f.BoundBox.ZLength < 1e-9
            and f.BoundBox.YLength > 20,
        )
        under = _face(
            doc,
            screw,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMax) < 1e-9
            and len(f.Wires) == 2,
        )
        p1 = joints.Pick(screw, _body(doc, screw), under)
        p2 = joints.Pick(channel, _body(doc, channel), web, hole(1, 1))
        s1 = [c for c in joints.snap_candidates(p1) if c["kind"] == "centre"][0]
        s2 = joints.nearest_snap(
            [c for c in joints.snap_candidates(p2) if c["kind"] == "loop"], hole(1, 1)
        )
        doc.openTransaction("Joint")
        joint = joints.create_joint(doc, "rigid", p1, s1, p2, s2)
        joints.align(joint, first=True)
        doc.commitTransaction()
        doc.recompute()
        pick = joints.Pick(channel, _body(doc, channel), web, hole(3, 1))
        snap = joints.nearest_snap(
            [c for c in joints.snap_candidates(pick) if c["kind"] == "loop"], hole(3, 1)
        )
        doc.openTransaction("Duplicate With Joints")
        copies, _made = dj.duplicate(doc, [screw], joint, 0, pick, snap)
        doc.commitTransaction()
        doc.recompute()
        holder = components.container_of(copies[0])
        box = _gbox(doc, copies[0])
        centre = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)
        _out(
            "duplicate_in_place",
            holder is frame
            and abs(centre.x - hole(3, 1).x) < 1e-4
            and abs(centre.y - hole(3, 1).y) < 1e-4,
            "the copy %s went into %s (the picked screw is in %s), at %s"
            % (copies[0].Label, holder.Label if holder else "the root", frame.Label, centre),
        )
    finally:
        _close(doc)


def check_delete_hole_joint():
    """A screw jointed into a square hole (its record holds the hole), the channel then
    edited (a new hole cut: faces and edges numbered anew, the joint finds its hole again),
    then the joint deleted the way the browser does (timeline_ops.delete): both bodies keep
    their solids, nothing is left in error, the screw stays where it was (patch 0.1.0-beta.2.2:
    deleting a joint must never break a body)."""
    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import joints
    from sciforge import timeline_ops as ops

    files = _files(["c_channel_1x2x1x5", "screw_8_32_x_0_5"])
    doc = App.newDocument("VexQaDelete")
    try:
        channel = _insert(doc, files["c_channel_1x2x1x5"]).top
        screw = _insert(
            doc, files["screw_8_32_x_0_5"], App.Placement(V(-20, 19.05, 20), App.Rotation())
        ).top
        t, p = vp.AL, vp.PITCH

        def hole(i, j):
            return V(p / 2 + i * p, p / 2 + j * p, t)

        web = _face(
            doc,
            channel,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMin - t) < 1e-9
            and f.BoundBox.ZLength < 1e-9
            and f.BoundBox.YLength > 20,
        )
        under = _face(
            doc,
            screw,
            lambda f: f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMax) < 1e-9
            and len(f.Wires) == 2,
        )
        p1 = joints.Pick(screw, _body(doc, screw), under)
        p2 = joints.Pick(channel, _body(doc, channel), web, hole(2, 1))
        s1 = [c for c in joints.snap_candidates(p1) if c["kind"] == "centre"][0]
        s2 = joints.nearest_snap(
            [c for c in joints.snap_candidates(p2) if c["kind"] == "loop"], hole(2, 1)
        )
        doc.openTransaction("Joint")
        joint = joints.create_joint(doc, "rigid", p1, s1, p2, s2)
        joints.align(joint, first=True)
        doc.commitTransaction()
        doc.recompute()
        # the channel edited: a round hole cut through its web (a Pocket would do the same)
        body = _body(doc, channel)
        base = body.BaseFeature
        doc.openTransaction("Edit")
        cut = base.Shape.cut(_cylinder(1.5, V(p * 4, p / 2, -1), 5))
        base.Shape = cut
        doc.commitTransaction()
        doc.recompute()
        joints.repair_references(doc)
        joints.solve(doc)
        doc.recompute()
        where = _gbox(doc, screw)
        centred = abs((where.XMin + where.XMax) / 2 - hole(2, 1).x) < 1e-4
        ops.delete(doc, [joint.Name])
        doc.recompute()
        after = _gbox(doc, screw)
        broken = [o.Label for o in doc.Objects if "Invalid" in o.State or "Error" in o.State]
        solids = all(_body(doc, c).Shape.Volume > 1.0 for c in (channel, screw))
        _out(
            "delete_hole_joint",
            centred
            and solids
            and not broken
            and not joints.joints(doc)
            and abs(after.XMin - where.XMin) < 1e-6
            and abs(after.ZMin - where.ZMin) < 1e-6,
            "on its hole after the edit %s, solids %s, in error %s, the screw %s -> %s"
            % (centred, solids, broken, where, after),
        )
    finally:
        _close(doc)


def _cylinder(r, at, h):
    import Part

    return Part.makeCylinder(r, h, at)


# -- the first occurrence deleted ----------------------------------------------------------------
def _parts_list(doc):
    from sciforge import drawing, drawing_core

    found = [b for b in doc.Objects if b.TypeId == "PartDesign::Body"]
    return {
        r["PartNumber"]: r["Qty"] for r in drawing_core.parts_rows(drawing.components_of(found))
    }


def check_parts_list_original_deleted():
    """The same screw file inserted three times ("screw", "screw:2", "screw:3"); the first one
    deleted: the other two stay (frozen as they were), and a drawing's parts list still counts
    them as one part (Fusion: the component lives on in its other occurrences, one row, Qty
    2), also after a save and reopen."""
    from sciforge import components

    path = _files(["screw_8_32_x_0_5"])["screw_8_32_x_0_5"]
    doc = App.newDocument("VexQaQty")
    saved = os.path.join(_folder(), "qty.FCStd")
    try:
        tops = [
            _insert(doc, path, App.Placement(V(15 * k, 0, 0), App.Rotation())).top for k in range(3)
        ]
        base = tops[0].Label
        before = _parts_list(doc)
        names = [t.Name for t in tops]
        components.remove(doc, tops[0])
        doc.recompute()
        left = [doc.getObject(n) for n in names[1:]]
        solid = all(o is not None and _body(doc, o).Shape.Volume > 1.0 for o in left)
        after = _parts_list(doc)
        doc.saveAs(saved)
        _close(doc)
        doc = App.openDocument(saved)
        doc.recompute()
        reopened = _parts_list(doc)
        _out(
            "parts_list_original_deleted",
            before == {base: 3} and solid and after == {base: 2} and reopened == {base: 2},
            "before %s, the others solid %s, after the delete %s, reopened %s"
            % (before, solid, after, reopened),
        )
    finally:
        _close(doc)


def check_occurrence_names_after_delete():
    """The screw file inserted three times, the first one deleted (screw:2 and screw:3 stay),
    then the file inserted twice more: a part of its own named after the file, then an
    occurrence of it numbered after the ones still there ("screw:4"), not a name FreeCAD
    makes unique by itself ("screw:001", read as the first occurrence)."""
    from sciforge import components, instances

    path = _files(["screw_8_32_x_0_5"])["screw_8_32_x_0_5"]
    doc = App.newDocument("VexQaNames")
    try:
        tops = [_insert(doc, path).top for _k in range(3)]
        base = tops[0].Label
        components.remove(doc, tops[0])
        doc.recompute()
        fresh = _insert(doc, path).top
        again = _insert(doc, path).top
        instances.sync(doc)
        labels = sorted(c.Label for c in components.list_components(doc))
        want = sorted([base, base + ":2", base + ":3", base + ":4"])
        _out(
            "occurrence_names_after_delete",
            fresh.Label == base
            and not instances.is_instance(fresh)
            and instances.source_of(again) is fresh
            and again.Label == base + ":4"
            and labels == want,
            "the part again %r, its occurrence %r, all %s" % (fresh.Label, again.Label, labels),
        )
    finally:
        _close(doc)


def check_same_file_again():
    """Insert STEP of the same file again: the same bytes are another occurrence even when
    the file's date changed (a teammate copied the parts folder again, a git checkout);
    a file that really changed comes in as a part of its own (its new shape), and inserting
    that one again is an occurrence of it."""
    import shutil
    import time

    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import instances

    src = _files(["screw_8_32_x_0_5"])["screw_8_32_x_0_5"]
    work = os.path.join(_folder(), "again")
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "screw.step")
    shutil.copyfile(src, path)
    doc = App.newDocument("VexQaAgain")
    try:
        first = _insert(doc, path).top
        later = time.time() + 120.0
        os.utime(path, (later, later))  # the same bytes, a new date
        copy = _insert(doc, path)
        same = copy.occurrence and instances.source_of(copy.top) is first
        longer = os.path.join(work, "longer.step")
        vp.write_step(vp.screw(0.75), "screw", longer)
        shutil.copyfile(longer, path)  # the file really changed
        later += 120.0
        os.utime(path, (later, later))
        changed = _insert(doc, path)
        length = _gbox(doc, changed.top).ZLength
        again = _insert(doc, path)
        _out(
            "same_file_again",
            same
            and not changed.occurrence
            and abs(length - (0.75 + 0.08) * vp.IN) < 1e-3
            and again.occurrence
            and instances.source_of(again.top) is changed.top,
            "a new date: occurrence %s; a changed file: occurrence %s, length %.3f; that one "
            "again: occurrence %s"
            % (copy.occurrence, changed.occurrence, length, again.occurrence),
        )
    finally:
        _close(doc)


def check_real_parts_snaps():
    """Hole centres on parts with real VEX files' traits (vex_real.py: inch STEP files,
    holes with tiny rounded corners, holes cut in halves, a motor assembly with a blind square
    socket): every hole's centre is offered on the face, on each piece of a split outline and
    (start, half-way, end) on its walls, at the true centre."""
    from SciForgeTests.fixtures.vex import vex_parts as vp
    from SciForgeTests.fixtures.vex import vex_real as vr
    from sciforge import hole_snaps

    files = vr.write_all(os.path.join(_folder(), "real"))
    doc = App.newDocument("VexQaReal")
    bad = []
    try:
        t, p, half = vp.AL, vp.PITCH, vp.HOLE / 2.0
        for name in ("real_channel_fillet", "real_channel_split"):
            made = _insert(doc, files[name])
            shape = _body(doc, made.top).Shape
            centres = [V(p / 2 + i * p, p / 2 + j * p, t) for i in range(5) for j in range(2)]
            top = max(
                (
                    (i, f)
                    for i, f in enumerate(shape.Faces)
                    if f.Surface.TypeId == "Part::GeomPlane"
                    and abs(f.BoundBox.ZMin - t) < 1e-6
                    and abs(f.BoundBox.ZMax - t) < 1e-6
                ),
                key=lambda pair: len(pair[1].Wires),
            )
            found = [
                s["point"]
                for s in hole_snaps.snaps(shape, "Face%d" % (top[0] + 1))
                if s["kind"] == "loop"
            ]
            for c in centres:
                if not any((q - c).Length < 1e-6 for q in found):
                    bad.append("%s: no centre at %s on the web" % (name, c))
            c = centres[3]
            for i, e in enumerate(shape.Edges):
                box = e.BoundBox
                on = (
                    abs(box.ZMin - t) < 1e-6
                    and abs(box.ZMax - t) < 1e-6
                    and box.XMin > c.x - half - 1e-6
                    and box.XMax < c.x + half + 1e-6
                    and box.YMin > c.y - half - 1e-6
                    and box.YMax < c.y + half + 1e-6
                )
                if on:
                    snaps = hole_snaps.snaps(shape, "Edge%d" % (i + 1))
                    if not any(
                        s["kind"] == "loop" and (s["point"] - c).Length < 1e-6 for s in snaps
                    ):
                        bad.append("%s: Edge%d of a hole does not offer its centre" % (name, i + 1))
            for i, f in enumerate(shape.Faces):
                box = f.BoundBox
                wall = (
                    f.Surface.TypeId == "Part::GeomPlane"
                    and box.ZLength > t - 1e-6
                    and box.XMin > c.x - half - 1e-6
                    and box.XMax < c.x + half + 1e-6
                    and box.YMin > c.y - half - 1e-6
                    and box.YMax < c.y + half + 1e-6
                )
                if wall:
                    got = sorted(
                        round(s["point"].z, 6)
                        for s in hole_snaps.snaps(shape, "Face%d" % (i + 1))
                        if s["kind"].startswith("hole_")
                        and (s["point"] - V(c.x, c.y, s["point"].z)).Length < 1e-6
                    )
                    if got != [0.0, round(t / 2.0, 6), round(t, 6)]:
                        bad.append("%s: wall Face%d gives %s" % (name, i + 1, got))
        made = _insert(doc, files["real_motor"])
        x, y, z = vr.socket_top()
        found = False
        from sciforge import components

        for body in components.bodies_in(doc, made.top, recursive=True):
            shape = body.Shape
            for i, f in enumerate(shape.Faces):
                if f.Surface.TypeId != "Part::GeomPlane" or len(f.Wires) < 2:
                    continue
                for s in hole_snaps.snaps(shape, "Face%d" % (i + 1)):
                    if s["kind"] in ("loop", "centre") and (s["point"] - V(x, y, z)).Length < 1e-6:
                        found = True
        if not found:
            bad.append("the motor's socket: no centre on the boss's top")
        _out("real_parts_snaps", not bad, "; ".join(bad[:6]))
    finally:
        _close(doc)


def check_big_channel_snaps():
    """A part with a huge face count (the steel 1x5x1x35 C-channel with rounded hole corners:
    about 2000 faces and 6000 edges): every one of its web's 175 square holes offers its centre,
    at the true centre, and the web's dots come in a few seconds at most the first time."""
    import time

    from SciForgeTests.fixtures.vex import vex_parts as vp
    from sciforge import hole_snaps

    shape = vp.make("c_channel_1x5x1x35")
    t = vp.STEEL
    web = max(
        (
            (i, f)
            for i, f in enumerate(shape.Faces)
            if f.Surface.TypeId == "Part::GeomPlane"
            and abs(f.BoundBox.ZMin - t) < 1e-6
            and abs(f.BoundBox.ZMax - t) < 1e-6
        ),
        key=lambda pair: len(pair[1].Wires),
    )
    hole_snaps.forget()
    t0 = time.perf_counter()
    found = [
        s["point"] for s in hole_snaps.snaps(shape, "Face%d" % (web[0] + 1)) if s["kind"] == "loop"
    ]
    took = time.perf_counter() - t0
    missing = [
        c
        for c in (
            V(vp.PITCH / 2 + i * vp.PITCH, vp.PITCH / 2 + j * vp.PITCH, t)
            for i in range(35)
            for j in range(5)
        )
        if not any((q - c).Length < 1e-6 for q in found)
    ]
    _out(
        "big_channel_snaps",
        len(shape.Faces) > 1500 and len(found) == 175 and not missing and took < 10.0,
        "faces %d, centres %d, missing %s, first time %.2f s"
        % (len(shape.Faces), len(found), missing[:3], took),
    )


# -- the run -------------------------------------------------------------------------------------
CHECKS = [
    check_duplicate_rigid_group,
    check_duplicate_limits,
    check_duplicate_in_place,
    check_delete_hole_joint,
    check_parts_list_original_deleted,
    check_occurrence_names_after_delete,
    check_same_file_again,
    check_real_parts_snaps,
    check_big_channel_snaps,
]


def main():
    for check in CHECKS:
        try:
            check()
        except Exception:
            _out(check.__name__, False, traceback.format_exc().replace("\n", " | "))
    print("vexqa done %d" % len(RESULTS), flush=True)
    import shutil

    shutil.rmtree(_folder(), ignore_errors=True)

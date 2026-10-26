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


# -- the run -------------------------------------------------------------------------------------
CHECKS = [
    check_duplicate_rigid_group,
]


def main():
    for check in CHECKS:
        try:
            check()
        except Exception:
            _out(check.__name__, False, traceback.format_exc().replace("\n", " | "))
    print("vexqa done %d" % len(RESULTS), flush=True)

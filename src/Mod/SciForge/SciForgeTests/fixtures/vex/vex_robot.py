# SPDX-License-Identifier: LGPL-2.1-or-later
"""A VEX-like drivetrain of about 300 parts for SciForge's speed tests, made from SciForge's own
test parts (vex_parts.py: never VEX's files). Needs SciForge (step_import, instances, joints).

    two steel 1x5x1x35 C-channel rails, three 1x2x1x25 cross members on them, four 2x2x25
    angles standing at the corners, a 5x25 plate on the cross members, four 3 in shafts
    through the rails (each turning in a revolute joint), eight bearing flats, sixteen 1 in
    standoffs on the plate, 130 #8-32 screws at hole centres and 130 Keps nuts under them.

Every part file is inserted once (Insert STEP); the repeats are occurrences of it (what a
second Insert STEP of the same file makes, or Copy / Paste): 9 parts read from files, 289
occurrences. build() returns the counts and how long each phase took.
"""

import time

import FreeCAD as App

from . import vex_parts as vp

V = App.Vector
IN = vp.IN
P = vp.PITCH
RAIL = "c_channel_1x5x1x35"
CROSS = "c_channel_1x2x1x25"
SCREWS = 130


def _rot(axis, deg):
    return App.Rotation(V(*axis), deg)


def _plc(x, y, z, rot=None):
    return App.Placement(V(x, y, z), rot or App.Rotation())


def layout():
    """[(part name, placement)] of every part of the robot, in mm."""
    out = []
    rail_len = 35 * P
    gap = 12.5 * IN  # between the two rails (outer faces)
    rail_w = 5 * P
    # the rails along X, webs on Z = 0, flanges up
    out.append((RAIL, _plc(0, 0, 0)))
    out.append((RAIL, _plc(0, gap - rail_w, 0)))
    top = 0.5 * IN  # the cross members lie on the rails' flanges
    cross_x = [1.0 * IN, 8.0 * IN, 15.0 * IN]
    # a cross member's length along X turned to run along Y (its web 1 in wide along X)
    for x in cross_x:
        out.append((CROSS, _plc(x + 2 * P, 0, top, _rot((0, 0, 1), 90))))
    # angles standing at the four corners (their standing leg along Z)
    for x, y in ((0, -2 * P), (rail_len - 25 * P, -2 * P), (0, gap), (rail_len - 25 * P, gap)):
        out.append(("angle_2x2x25", _plc(x, y, 0)))
    # the plate on the cross members
    out.append(("plate_5x25", _plc(1.0 * IN, 2.0 * IN, top + vp.AL)))
    # four shafts along Y through the rails' flanges (wheel axles), two bearings each
    shaft_x = [2.25 * IN, 6.25 * IN, 10.25 * IN, 14.25 * IN]
    for x in shaft_x:
        out.append(("shaft_3in", _plc(x, -0.5 * IN, P / 2.0, _rot((1, 0, 0), -90))))
    for x in shaft_x:
        for y in (0.0, gap):
            out.append(("bearing_flat", _plc(x, y, P / 2.0, _rot((1, 0, 0), 90))))
    # standoffs on the plate (a 4 x 4 grid)
    for i in range(4):
        for j in range(4):
            x = 1.0 * IN + P / 2.0 + (3 + 6 * i) * P
            y = 2.0 * IN + P / 2.0 + j * P
            out.append(("standoff_1in", _plc(x, y, top + 2 * vp.AL)))
    # screws at the cross members' hole centres (over the rails), then the plate's edge
    # holes, each with a Keps nut under the metal
    spots = []
    for x in cross_x:
        for k in range(2):
            for yh in range(25):
                cx = x + P / 2.0 + k * P
                cy = P / 2.0 + yh * P
                spots.append((cx, cy, top + vp.AL, top))
    for i in range(25):
        for j in (0, 4):
            spots.append(
                (1.0 * IN + P / 2.0 + i * P, 2.0 * IN + P / 2.0 + j * P, top + 2 * vp.AL, top)
            )
    for cx, cy, z_top, z_bottom in spots[:SCREWS]:
        out.append(("screw_8_32_x_0_5", _plc(cx, cy, z_top)))
        out.append(("keps_nut", _plc(cx, cy, z_bottom, _rot((1, 0, 0), 180))))
    return out


def build(doc, folder=None, joint_count=1):
    """The robot in `doc` (each part file inserted once, the repeats occurrences of it),
    with `joint_count` revolute shaft joints. Returns {"parts", "objects", "seconds": {...},
    "joints": [...], "rails": [...], "shafts": [...]}."""
    from sciforge import exchange_core, instances, step_import

    folder = folder or vp.default_folder()
    t0 = time.perf_counter()
    plan = layout()
    files = vp.write_all(folder, sorted({name for name, _p in plan}))
    t_files = time.perf_counter() - t0
    firsts = {}
    parts = []
    t1 = time.perf_counter()
    doc.openTransaction("Robot")
    for name, plc in plan:
        if name not in firsts:
            made = step_import.import_file(doc, files[name], exchange_core.INSERT)
            comp = made.top
            firsts[name] = comp
        else:
            comp = instances.make_instance(firsts[name], None, placement=plc)
        comp.Placement = plc
        parts.append((name, comp))
    doc.commitTransaction()
    t_insert = time.perf_counter() - t1
    t2 = time.perf_counter()
    doc.recompute()
    t_recompute = time.perf_counter() - t2
    out = {
        "parts": len(parts),
        "objects": len(doc.Objects),
        "seconds": {"files": t_files, "insert": t_insert, "recompute": t_recompute},
        "rails": [c for n, c in parts if n == RAIL],
        "shafts": [c for n, c in parts if n == "shaft_3in"],
        "joints": [],
    }
    if joint_count:
        t3 = time.perf_counter()
        out["joints"] = shaft_joints(doc, out["shafts"][:joint_count], out["rails"][0])
        out["seconds"]["joints"] = time.perf_counter() - t3
    return out


def shaft_joints(doc, shafts, rail):
    """A revolute joint per shaft: the shaft's end face centre onto the centre of the rail's
    flange hole it goes through (the shaft turns there)."""
    from sciforge import components, joints

    made = []
    doc.openTransaction("Robot joints")
    try:
        rail_body = components.bodies_in(doc, rail, recursive=True)[0]
        for shaft in shafts:
            body = components.bodies_in(doc, shaft, recursive=True)[0]
            shape = body.Shape
            # the shaft's end face nearest the rail (its global Y is the smallest)
            ends = [
                (i, f)
                for i, f in enumerate(shape.Faces)
                if f.Surface.TypeId == "Part::GeomPlane" and f.Area < 11.0
            ]
            gp = shaft.getGlobalPlacement()
            ends.sort(key=lambda e: gp.multVec(e[1].CenterOfMass).y)
            pick1 = joints.Pick(shaft, body, "Face%d" % (ends[0][0] + 1))
            snap1 = joints.nearest_snap(joints.snap_candidates(pick1), None)
            # the rail's outer flange face (Y = 0 side) and its hole nearest the shaft
            centre = gp.multVec(ends[0][1].CenterOfMass)
            rshape = rail_body.Shape
            rg = rail.getGlobalPlacement()
            flange = None
            for i, f in enumerate(rshape.Faces):
                if f.Surface.TypeId != "Part::GeomPlane" or len(f.Wires) < 2:
                    continue
                n = rg.Rotation.multVec(f.normalAt(0, 0))
                if n.y < -0.99 and abs(rg.multVec(f.CenterOfMass).y) < 1e-6:
                    flange = i
                    break
            pick2 = joints.Pick(rail, rail_body, "Face%d" % (flange + 1), centre)
            cands = [c for c in joints.snap_candidates(pick2) if c["kind"] == "loop"]
            snap2 = joints.nearest_snap(cands, centre)
            joint = joints.create_joint(doc, "revolute", pick1, snap1, pick2, snap2)
            joints.align(joint, first=True)
            made.append(joint)
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    return made

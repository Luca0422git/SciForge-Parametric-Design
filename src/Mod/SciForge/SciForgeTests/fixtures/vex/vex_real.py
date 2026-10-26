# SPDX-License-Identifier: LGPL-2.1-or-later
"""Test parts with the traits of real VEX STEP files that vex_parts.py's clean parts lack
(QA of beta 3's VEX work; still SciForge's own shapes from VEX's published numbers, never
VEX's files):

  real_channel_fillet  a 1x2x1x5 aluminium C-channel whose square holes have tiny rounded
                       corners (r 0.005 in: arcs of 0.13 mm in every hole's outline)
  real_channel_split   the same channel whose holes are each cut by two half-tools: every
                       hole's outline has split sides and its walls are split into more faces
  real_motor           a motor-like ASSEMBLY of three solids (a case with a round boss and a
                       blind 0.13 in square socket for a 1/8 in shaft, a cartridge, a cap)
  real_screw           the #8-32 x 0.5 in screw of vex_parts
  real_shaft           the 1/8 in x 3 in square shaft of vex_parts

Every file is written in INCH units (VEX's own STEP files are in inches; FreeCAD reads them
into millimetres). Needs FreeCAD's Part module (works headless).

    python: import vex_real; vex_real.write_all(folder) -> {name: path of its STEP file}
"""

import json
import os

from SciForgeTests.fixtures.vex import vex_parts as vp

IN = vp.IN
VERSION = 3  # bump when a shape changes: the cached STEP files are made again
TINY = 0.005 * IN  # the tiny hole corner radius
SOCKET = 0.13 * IN  # the motor's square socket (a 1/8 in shaft with a little play)
SOCKET_DEPTH = 0.25 * IN
BOSS_R = 0.3 * IN
BOSS_H = 0.1 * IN
CASE = (2.2 * IN, 1.6 * IN, 0.9 * IN)  # the motor case's box (x, y, z) from the origin
SOCKET_AT = (1.1 * IN, 0.8 * IN)  # the socket's axis (x, y)

NAMES = ("real_channel_fillet", "real_channel_split", "real_motor", "real_screw", "real_shaft")


def _vec(x, y, z):
    import FreeCAD as App

    return App.Vector(x, y, z)


def channel_split(web=2, flange=1, length=5, t=vp.AL):
    """vex_parts.c_channel, but every web hole cut by two half-tools (left and right half of
    the square): the hole's outline has split sides and more wall faces (no removeSplitter,
    as a real exporter leaves it)."""
    Part = vp._part()
    L, W, H = length * vp.PITCH, web * vp.PITCH, flange * vp.PITCH
    body = vp.box(0, 0, 0, L, W, t)
    body = body.fuse([vp.box(0, 0, 0, L, t, H), vp.box(0, W - t, 0, L, t, H)]).removeSplitter()
    h = vp.HOLE / 2.0
    for i in range(length):
        for j in range(web):
            cx = vp.PITCH / 2.0 + i * vp.PITCH
            cy = vp.PITCH / 2.0 + j * vp.PITCH
            body = body.cut(vp.box(cx - h, cy - h, -1.0, h, vp.HOLE, t + 2.0))
            body = body.cut(vp.box(cx, cy - h, -1.0, h, vp.HOLE, t + 2.0))
    solids = body.Solids
    return solids[0] if len(solids) == 1 else Part.makeCompound(solids)


def motor_solids():
    """(case, cartridge, cap) of the motor-like assembly: the case's top at z = 0.9 in, its
    boss up to 1.0 in with the square socket going 0.25 in down from the boss's top."""
    Part = vp._part()
    cx, cy = SOCKET_AT
    case = vp.box(0, 0, 0, *CASE)
    boss = Part.makeCylinder(BOSS_R, BOSS_H, _vec(cx, cy, CASE[2]))
    case = case.fuse(boss).removeSplitter()
    top = CASE[2] + BOSS_H
    socket = vp.box(
        cx - SOCKET / 2.0, cy - SOCKET / 2.0, top - SOCKET_DEPTH, SOCKET, SOCKET, SOCKET_DEPTH + 1.0
    )
    case = case.cut(socket)
    cartridge = Part.makeCylinder(0.5 * IN, 0.5 * IN, _vec(cx, cy, 0.2 * IN))
    cap = vp.box(0, 0, -0.1 * IN, CASE[0], CASE[1], 0.1 * IN)
    return case, cartridge, cap


def socket_top():
    """The centre of the socket's mouth (the boss's top face), part coordinates (mm)."""
    return (SOCKET_AT[0], SOCKET_AT[1], CASE[2] + BOSS_H)


def _write_inch(objects, path):
    """`objects` [(label, shape)] as one STEP file in inches: one product, or an assembly of
    products when there are several."""
    import FreeCAD as App
    import Import
    import Part

    doc = App.newDocument("VexRealFixture")
    before = Part.exportUnits()
    try:
        made = []
        for label, shape in objects:
            small = shape.copy()
            small.scale(1.0 / IN)  # inch numbers in the file...
            obj = doc.addObject("Part::Feature", "Part")
            obj.Label = label
            obj.Shape = small
            made.append(obj)
        top = made
        if len(made) > 1:
            part = doc.addObject("App::Part", "Assembly")
            part.Label = os.path.splitext(os.path.basename(path))[0]
            for obj in made:
                part.addObject(obj)
            top = [part]
        doc.recompute()
        Part.exportUnits("INCH")  # ... declared as inches
        Import.export(top, path)
    finally:
        try:
            Part.exportUnits(before.get("write.step.unit", "MM"))
        except Exception:
            Part.exportUnits("MM")
        App.closeDocument(doc.Name)
    return path


def make(name):
    """[(label, shape)] of one test file (millimetres)."""
    if name == "real_channel_fillet":
        return [
            ("real_channel_fillet", vp.c_channel(web=2, flange=1, length=5, t=vp.AL, corner=TINY))
        ]
    if name == "real_channel_split":
        return [("real_channel_split", channel_split())]
    if name == "real_motor":
        case, cartridge, cap = motor_solids()
        return [("Case", case), ("Cartridge", cartridge), ("Cap", cap)]
    if name == "real_screw":
        return [("real_screw", vp.screw(0.5))]
    if name == "real_shaft":
        return [("real_shaft", vp.shaft(3.0))]
    raise KeyError(name)


def write_all(folder, names=None):
    """Every file (or `names`) as <folder>/<name>.step, kept between runs of one VERSION.
    Returns {name: path}."""
    os.makedirs(folder, exist_ok=True)
    stamp = os.path.join(folder, "vex_real.json")
    try:
        with open(stamp, encoding="utf-8") as handle:
            known = json.load(handle)
    except (OSError, ValueError):
        known = {}
    if known.get("version") != VERSION:
        known = {"version": VERSION, "files": {}}
    out = {}
    for name in names or NAMES:
        path = os.path.join(folder, name + ".step")
        if not (known["files"].get(name) and os.path.isfile(path)):
            _write_inch(make(name), path)
            known["files"][name] = True
        out[name] = path
    with open(stamp, "w", encoding="utf-8") as handle:
        json.dump(known, handle)
    return out

# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX V5-like test parts, made by SciForge from VEX's published numbers (never VEX's own
files: those are for personal and educational use only, so SciForge does not ship them;
research docs/sciforge/dev/research/fusion-vex-assembly.md, section 5).

Needs FreeCAD's Part module only (works headless). Inches as VEX gives them (1 in = 25.4 mm);
the shapes are in millimetres.

  square holes      0.182 in square, on a 0.500 in grid, the first one 0.25 in from an end
  c_channel_1x2x1x25        aluminium (0.064 in), web 2 holes wide, flanges 1 hole, 25 long
  c_channel_1x2x1x25_round  the same with slightly rounded hole corners (r 0.02 in)
  c_channel_1x5x1x35        steel (0.046 in), web 5 holes, 35 long, rounded hole corners
  angle_2x2x25      aluminium angle, two legs 2 holes wide, 25 long
  plate_5x25        aluminium plate, 5 x 25 holes
  standoff_1in      a 1 in standoff: 0.25 in across the hex flats, a #8 hole through
  screw_8_32_x_0_5  a #8-32 x 0.5 in screw: round head, 0.164 in shank, a hex socket
  keps_nut          a #8-32 Keps nut: 11/32 in hex with its toothed washer (a thin disc)
  shaft_3in         a 1/8 in square shaft, 3 in long
  bearing_flat      a bearing flat: a round bore between two mounting holes 0.5 in apart (G)

Where things are (part coordinates, mm): a C-channel's length runs along X from 0, its web
lies on Z = 0 (0 .. t) across Y = 0 .. web width, its flanges stand up to the flange height
at both Y edges. Angles and plates lie the same way (a plate is a web without flanges; an
angle has one flange on Y = 0). Screws stand along Z: the underside of the head on Z = 0, the
shank down to -0.5 in. Nuts, standoffs and the bearing flat sit on Z = 0, their holes along
Z through the origin; the shaft stands on Z = 0 along Z.

    python: import vex_parts; vex_parts.write_all(folder) -> {name: path of its STEP file}
"""

import json
import math
import os

IN = 25.4
HOLE = 0.182 * IN  # square hole side
PITCH = 0.5 * IN  # hole grid
ROUND = 0.02 * IN  # the corner radius of the "rounded" square holes
AL = 0.064 * IN  # aluminium thickness
STEEL = 0.046 * IN  # steel thickness
VERSION = 3  # bump when a shape changes: the cached STEP files are made again

# name -> (builder name, keyword arguments, what it is)
PARTS = {
    "c_channel_1x2x1x25": (
        "c_channel",
        {"web": 2, "flange": 1, "length": 25, "t": AL},
        "Aluminium C-channel 1x2x1x25",
    ),
    "c_channel_1x2x1x25_round": (
        "c_channel",
        {"web": 2, "flange": 1, "length": 25, "t": AL, "corner": ROUND},
        "Aluminium C-channel 1x2x1x25, rounded hole corners",
    ),
    "c_channel_1x5x1x35": (
        "c_channel",
        {"web": 5, "flange": 1, "length": 35, "t": STEEL, "corner": ROUND},
        "Steel C-channel 1x5x1x35",
    ),
    "angle_2x2x25": ("angle", {"leg": 2, "length": 25, "t": AL}, "Aluminium angle 2x2x25"),
    "plate_5x25": ("plate", {"width": 5, "length": 25, "t": AL}, "Aluminium plate 5x25"),
    "standoff_1in": ("standoff", {"length": 1.0}, "Standoff 1 in"),
    "screw_8_32_x_0_5": ("screw", {"length": 0.5}, "Screw #8-32 x 0.5 in"),
    "keps_nut": ("keps_nut", {}, "Keps nut #8-32"),
    "shaft_3in": ("shaft", {"length": 3.0}, "Square shaft 1/8 in x 3 in"),
    "bearing_flat": ("bearing_flat", {}, "Bearing flat"),
}


def _part():
    import Part

    return Part


def _vec(x, y, z):
    import FreeCAD as App

    return App.Vector(x, y, z)


# -- building blocks ---------------------------------------------------------------------------
def box(x0, y0, z0, dx, dy, dz):
    return _part().makeBox(dx, dy, dz, _vec(x0, y0, z0))


def hole_tool(cx, cy, depth, corner=0.0, side=HOLE):
    """A square prism along Z (from z = -1 to depth + 1) that cuts one square hole centred on
    (cx, cy); `corner` > 0 rounds its four corners with that radius."""
    h = side / 2.0
    tool = box(cx - h, cy - h, -1.0, side, side, depth + 2.0)
    if corner > 1e-9:
        upright = [e for e in tool.Edges if abs(e.BoundBox.ZLength - (depth + 2.0)) < 1e-6]
        tool = tool.makeFillet(min(corner, h * 0.9), upright)
    return tool


def _cut_holes(solid, tools):
    if not tools:
        return solid
    Part = _part()
    out = solid.cut(Part.makeCompound(tools))
    solids = out.Solids
    return solids[0] if len(solids) == 1 else out


def _placed(shape, placement):
    out = shape.copy()
    out.Placement = placement.multiply(out.Placement)
    return out


def _rot(axis, degrees):
    import FreeCAD as App

    return App.Placement(App.Vector(), App.Rotation(App.Vector(*axis), degrees))


def _move(x, y, z):
    import FreeCAD as App

    return App.Placement(App.Vector(x, y, z), App.Rotation())


def _grid_tools(nx, ny, depth, corner, x0=0.0, y0=0.0):
    tools = []
    for i in range(nx):
        for j in range(ny):
            cx = x0 + PITCH / 2.0 + i * PITCH
            cy = y0 + PITCH / 2.0 + j * PITCH
            tools.append(hole_tool(cx, cy, depth, corner))
    return tools


# -- the parts ---------------------------------------------------------------------------------
def c_channel(web, flange, length, t, corner=0.0):
    """Length along X, web on Z = 0 .. t across Y = 0 .. web * pitch, flanges up to
    flange * pitch at both Y edges; square holes in the web and in both flanges."""
    L = length * PITCH
    W = web * PITCH
    H = flange * PITCH
    body = box(0, 0, 0, L, W, t)
    body = body.fuse([box(0, 0, 0, L, t, H), box(0, W - t, 0, L, t, H)]).removeSplitter()
    tools = _grid_tools(length, web, t, corner)
    # flange holes: made along Z, turned to run along Y through each flange
    for y in (0.0, W - t):
        for i in range(length):
            cx = PITCH / 2.0 + i * PITCH
            tool = hole_tool(0.0, 0.0, t, corner)
            # the prism's Z (-1 .. t+1) becomes Y (y-1 .. y+t+1); its Y becomes Z
            tool = _placed(tool, _rot((1, 0, 0), -90))  # Z -> Y, Y -> -Z
            tool = _placed(tool, _move(cx, y, PITCH / 2.0))
            tools.append(tool)
    return _cut_holes(body, tools)


def angle(leg, length, t, corner=0.0):
    """Two legs of `leg` holes: one on Z = 0 across Y = 0 .. leg * pitch, one standing up on
    Y = 0 to Z = leg * pitch."""
    L = length * PITCH
    W = leg * PITCH
    body = box(0, 0, 0, L, W, t).fuse(box(0, 0, 0, L, t, W)).removeSplitter()
    tools = []
    for i in range(length):
        for j in range(leg):
            cx = PITCH / 2.0 + i * PITCH
            c = PITCH / 2.0 + j * PITCH
            if c - HOLE / 2.0 > t:  # the flat leg's holes (clear of the standing leg)
                tools.append(hole_tool(cx, c, t, corner))
            tool = _placed(hole_tool(0.0, 0.0, t, corner), _rot((1, 0, 0), -90))
            if c - HOLE / 2.0 > t:
                tools.append(_placed(tool, _move(cx, 0.0, c)))
    return _cut_holes(body, tools)


def plate(width, length, t, corner=0.0):
    return _cut_holes(
        box(0, 0, 0, length * PITCH, width * PITCH, t), _grid_tools(length, width, t, corner)
    )


def _hex_prism(across_flats, height, z0=0.0):
    Part = _part()
    r = across_flats / math.sqrt(3.0)  # the corners' radius
    pts = [
        _vec(r * math.cos(math.radians(30 + 60 * k)), r * math.sin(math.radians(30 + 60 * k)), z0)
        for k in range(6)
    ]
    return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(_vec(0, 0, height))


def _round_hole(diameter, z0, height):
    Part = _part()
    return Part.makeCylinder(diameter / 2.0, height + 2.0, _vec(0, 0, z0 - 1.0))


def standoff(length):
    h = length * IN
    return _hex_prism(0.25 * IN, h).cut(_round_hole(0.164 * IN, 0.0, h))


def screw(length):
    """A button-head #8-32 screw: the head's underside on Z = 0, the head up to 0.08 in with
    a 3/32 in hex socket, the 0.164 in shank down to -length."""
    Part = _part()
    head = Part.makeCylinder(0.135 * IN, 0.08 * IN)
    try:
        head = head.makeFillet(0.03 * IN, [e for e in head.Edges if e.BoundBox.ZMin > 0.07 * IN])
    except Exception:
        pass
    shank = Part.makeCylinder(0.082 * IN, length * IN, _vec(0, 0, -length * IN))
    solid = head.fuse(shank).removeSplitter()
    socket = _hex_prism(0.09375 * IN, 0.05 * IN + 1.0, 0.03 * IN)
    return solid.cut(socket)


def keps_nut():
    """A Keps nut: an 11/32 in hex 0.12 in high on a thin toothed washer (a disc 0.4 in
    across, 0.03 in thick) on Z = 0, the #8 hole along Z."""
    Part = _part()
    washer = Part.makeCylinder(0.2 * IN, 0.03 * IN)
    nut = _hex_prism(11.0 / 32.0 * IN, 0.12 * IN, 0.03 * IN)
    solid = washer.fuse(nut).removeSplitter()
    return solid.cut(_round_hole(0.164 * IN, 0.0, 0.15 * IN))


def shaft(length):
    s = 0.125 * IN
    return box(-s / 2.0, -s / 2.0, 0, s, s, length * IN)


def bearing_flat():
    """(G: VEX gives no drawing) a 1.5 x 0.5 x 0.1 in Delrin flat, a 0.19 in round bore at its
    middle (the origin) and two 0.18 in mounting holes 0.5 in to each side."""
    Part = _part()
    t = 0.1 * IN
    solid = box(-0.75 * IN, -0.25 * IN, 0, 1.5 * IN, 0.5 * IN, t)
    tools = [_round_hole(0.19 * IN, 0.0, t)]
    for x in (-0.5 * IN, 0.5 * IN):
        hole = Part.makeCylinder(0.09 * IN, t + 2.0, _vec(x, 0, -1.0))
        tools.append(hole)
    return solid.cut(Part.makeCompound(tools))


def make(name):
    """The shape of one part (a Part.Solid in mm)."""
    builder, kwargs, _title = PARTS[name]
    return globals()[builder](**kwargs)


# -- facts the tests check ---------------------------------------------------------------------
def square_hole_count(name):
    builder, kw, _t = PARTS[name]
    if builder == "c_channel":
        return kw["length"] * (kw["web"] + 2)
    if builder == "angle":
        legs = len([j for j in range(kw["leg"]) if PITCH / 2.0 + j * PITCH - HOLE / 2.0 > kw["t"]])
        return kw["length"] * legs * 2
    if builder == "plate":
        return kw["length"] * kw["width"]
    return 0


def web_hole_centres(name, top=True):
    """The centres of a channel's / plate's web holes on its top (Z = t) or bottom (Z = 0)
    face, part coordinates (mm), row by row along X."""
    builder, kw, _t = PARTS[name]
    across = kw.get("web") or kw.get("width") or kw.get("leg")
    z = kw["t"] if top else 0.0
    out = []
    for j in range(across):
        for i in range(kw["length"]):
            out.append((PITCH / 2.0 + i * PITCH, PITCH / 2.0 + j * PITCH, z))
    return out


# -- STEP files ---------------------------------------------------------------------------------
def write_step(shape, label, path):
    """One part as a STEP file (FreeCAD's writer; the product is named `label`)."""
    import FreeCAD as App

    doc = App.newDocument("VexFixture")
    try:
        obj = doc.addObject("Part::Feature", "Part")
        obj.Label = label
        obj.Shape = shape
        doc.recompute()
        import Import

        Import.export([obj], path)
    finally:
        App.closeDocument(doc.Name)
    return path


def write_all(folder, names=None):
    """Every part (or `names`) as <folder>/<name>.step; files made earlier by the same
    VERSION are kept (a stamp file says which). Returns {name: path}."""
    os.makedirs(folder, exist_ok=True)
    stamp = os.path.join(folder, "vex_parts.json")
    try:
        with open(stamp, encoding="utf-8") as handle:
            known = json.load(handle)
    except (OSError, ValueError):
        known = {}
    if known.get("version") != VERSION:
        known = {"version": VERSION, "files": {}}
    out = {}
    for name in names or list(PARTS):
        path = os.path.join(folder, name + ".step")
        if known["files"].get(name) and os.path.isfile(path):
            out[name] = path
            continue
        write_step(make(name), name, path)
        known["files"][name] = True
        out[name] = path
    with open(stamp, "w", encoding="utf-8") as handle:
        json.dump(known, handle)
    return out


def default_folder():
    """Where the tests keep the STEP files: the test output folder (or a temp folder)."""
    import tempfile

    base = os.environ.get("SCIFORGE_SMOKE_OUT") or tempfile.gettempdir()
    return os.path.join(base, "vex_parts")

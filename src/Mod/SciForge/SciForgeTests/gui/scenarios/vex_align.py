# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: Align a standoff onto a square hole's centre, only real input
(docs/sciforge/parity/vex-assembly.md; Luca: "when i say align, i mean align. the align
command. so yes we will need center points on squares and such."). SciForge's own VEX-like
parts from their STEP files: a 1x2x1x5 aluminium C-channel at the origin (the web's top at
z = 0.064 in, square holes 0.182 in on a 0.5 in grid) and a 1 in standoff standing beside it.

  A  MODIFY > Align, Objects: Components. The mouse on the standoff's top face beside its
     round hole: the top's centre is lit; click: From = that centre, facing up.
  B  The mouse on the channel's web next to a square hole: the square hole's centre is lit
     (SciForge: Fusion has no such snap), only the dots near the mouse are drawn; click:
     To = the hole's centre. The standoff stands upside down on the web, its axis on the
     hole's centre.
  C  OK: one Align step; the component moved (no new step in its body). Undo: back beside
     the channel; Redo: on the hole again.
  D  Shift (Fusion: snapping off): Align, Components, From = the standoff's top. Shift held,
     the mouse next to another hole: no dots; Shift+click: To = the web's centre of area
     (the plain pick). Shift let go: the hole's centre is lit again. Esc: nothing moved.
  E  A hole's edge: Align, Components, From = the standoff's top; the mouse on the edge of
     another square hole: its centre is lit, with the hole's direction (up, out of the
     web); click: the standoff stands on that hole. OK.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import direct_steps as d
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
STANDOFF_AT = V(-20, 19.05, 0)  # the standoff's axis on the design's floor (1 in high)
LENGTH = 25.4  # the standoff's length
FIRST = (2, 1)  # the hole of B (row 1: not hidden by the front flange)
SECOND = (0, 1)  # the hole of D and E
TOP_KINDS = ("centre", "circle", "loop")  # the top's centre: face centre = round hole's centre


def standoff():
    return S["standoff"]


def snaps():
    p = vx.panel()
    return getattr(p, "snaps", None) if p is not None else None


def frame_point(name):
    p = vx.panel()
    frame = p.options.get(name + "_frame") if p is not None else None
    return (V(*frame["point"]) if frame else None), frame


def aligns():
    from sciforge import align

    return [o for o in App.ActiveDocument.Objects if align.is_align(o)]


def top():
    """The centre of the standoff's upper end, and a point of that face on the metal beside
    its round hole (radius 2.08 mm; the hex's flats 3.18 mm out), on the viewer's side."""
    box = vx.bbox(standoff())
    centre = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)
    return centre, vx.toward_viewer(centre, 2.6)


def on_hole(hole):
    """The standoff stands on the web over `hole`: its axis on the hole's centre, from the
    web's top up one standoff length."""
    box = vx.bbox(standoff())
    ok = (
        vx.near_xy(vx.axis_xy(standoff()), vx.hole_centre(*hole), 1e-4)
        and abs(box.ZMin - vx.T) < 1e-4
        and abs(box.ZMax - (vx.T + LENGTH)) < 1e-4
    )
    return ok, box


def beside():
    box = vx.bbox(standoff())
    return vx.near_xy(vx.axis_xy(standoff()), STANDOFF_AT, 1e-4) and abs(box.ZMax - LENGTH) < 1e-4


def web_centre():
    """The centre of area of the web's top face (the holes are spread evenly over it)."""
    from sciforge import bodies

    shape = bodies.global_shape(vx.body_of(S["channel"]))
    flat = [
        f
        for f in shape.Faces
        if abs(f.BoundBox.ZMin - vx.T) < 1e-6 and abs(f.BoundBox.ZMax - vx.T) < 1e-6
    ]
    return max(flat, key=lambda f: f.Area).CenterOfMass


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexAlign")
    S["channel"] = vx.insert("c_channel_1x2x1x5")
    S["standoff"] = vx.insert("standoff_1in", App.Placement(STANDOFF_AT, App.Rotation()))
    vx.fit()
    h.check("the standoff stands beside the channel", beside(), vx.bbox(standoff()))
    S["steps"] = [o.Name for o in vx.body_of(standoff()).Group]


def open_align():
    h.click_empty()
    vx.fit()
    vx.menu("MODIFY", "Align")


def components():
    p = vx.panel()
    if h.check("Align dialog", p is not None and p.title == "Align", p):
        d.choose("objects", "Components")


def hover_top():
    p = vx.panel()
    h.check(
        "Objects: Components",
        p is not None and p.objects.currentData() == "components",
        p and p.objects.currentText(),
    )
    centre, _point = top()
    vx.look_at(centre, 20.0)
    S["top"], S["hover"] = top()
    vx.hover(S["hover"])


def click_top():
    sn = snaps()
    vx.lit(sn, "the standoff's top", TOP_KINDS, S["top"])
    h.click(S["hover"])


def top_taken():
    point, frame = frame_point("from")
    h.check(
        "From = the centre of the standoff's top",
        point is not None and (point - S["top"]).Length < 1e-5,
        frame,
    )
    h.check(
        "facing up (out of the top)",
        frame is not None and frame["oriented"] and frame["axis"][2] > 0.999,
        frame,
    )
    p = vx.panel()
    h.check(
        "the standoff's component moves", p is not None and p.moving is standoff(), p and p.moving
    )


# -- A: From = the standoff's top ------------------------------------------------------------------
def a_open():
    open_align()


def a_components():
    components()


def a_hover_top():
    hover_top()


def a_click_top():
    click_top()


def a_taken():
    top_taken()
    h.shot("A-from")


# -- B: To = a square hole's centre ----------------------------------------------------------------
def b_hover_web():
    c = vx.hole_centre(*FIRST)
    vx.look_at(c, 40.0)
    S["hover"] = V(c.x + 3.6, c.y, vx.T)  # on the metal, 1.3 mm from the hole's edge
    vx.hover(S["hover"])


def b_lit():
    from sciforge import components as comps

    sn = snaps()
    h.check(
        "the dots are the channel's",
        sn is not None and sn.pick is not None and comps.component_of(sn.pick.obj) is S["channel"],
        sn and sn.pick and (sn.pick.obj.Name, sn.pick.element),
    )
    vx.lit(sn, "next to a square hole", "loop", vx.hole_centre(*FIRST))
    n = vx.drawn(sn)
    h.check("only the dots near the mouse are drawn (not the web's hundreds)", 0 < n <= 30, n)
    h.shot("B-hole-lit")
    h.click(S["hover"])


def b_preview():
    point, frame = frame_point("to")
    h.check(
        "To = the square hole's centre",
        point is not None and (point - vx.hole_centre(*FIRST)).Length < 1e-5,
        frame,
    )
    ok, box = on_hole(FIRST)
    h.check("the standoff stands upside down on the web, its axis on the hole's centre", ok, box)
    h.shot("B-preview")


# -- C: OK, Undo, Redo -----------------------------------------------------------------------------
def c_ok():
    vx.ok()


def c_done():
    h.check("dialog closed", vx.panel() is None)
    h.check("one Align step", len(aligns()) == 1, aligns())
    ok, box = on_hole(FIRST)
    h.check("kept: on the hole", ok, box)
    names = [o.Name for o in vx.body_of(standoff()).Group]
    h.check("no new step in the standoff's body", names == S["steps"], names)
    vx.undo()


def c_undone():
    h.check("Undo: back beside the channel", beside(), vx.bbox(standoff()))
    vx.redo()


def c_redone():
    ok, box = on_hole(FIRST)
    h.check("Redo: on the hole again", ok, box)


# -- D: Shift turns the dots off -------------------------------------------------------------------
def d_open():
    open_align()


def d_components():
    components()


def d_hover_top():
    hover_top()


def d_click_top():
    click_top()


def d_shift_hover():
    top_taken()
    c = vx.hole_centre(*SECOND)
    vx.look_at(c, 40.0)
    S["hover"] = V(c.x + 3.6, c.y, vx.T)
    vx.shift(True)
    vx.hover(S["hover"], QtCore.Qt.ShiftModifier)


def d_no_dots():
    sn = snaps()
    h.check(
        "Shift held: no dots (snapping off)",
        sn is not None and sn.off and sn.hot is None and vx.drawn(sn) == 0,
        sn and (sn.off, sn.hot, vx.drawn(sn)),
    )
    h.shot("D-shift")
    h.click(S["hover"], modifiers=QtCore.Qt.ShiftModifier)


def d_plain_pick():
    point, frame = frame_point("to")
    centre = web_centre()
    h.check(
        "Shift+click: To = the web's centre of area (the plain pick, not the hole)",
        point is not None and (point - centre).Length < 1e-4,
        (frame, centre),
    )
    vx.shift(False)
    vx.hover(S["hover"])


def d_dots_back():
    vx.lit(snaps(), "Shift let go", "loop", vx.hole_centre(*SECOND))
    h.press(QtCore.Qt.Key_Escape)


def d_cancelled():
    h.check("Esc: no dialog", vx.panel() is None)
    ok, box = on_hole(FIRST)
    h.check("Esc: the standoff stays on its hole", ok, box)
    h.check("still one Align step", len(aligns()) == 1, aligns())


# -- E: a hole's edge ------------------------------------------------------------------------------
def e_open():
    open_align()


def e_components():
    components()


def e_hover_top():
    hover_top()


def e_click_top():
    click_top()


def e_hover_edge():
    top_taken()
    c = vx.hole_centre(*SECOND)
    vx.look_at(c, 40.0)
    # the hole's edge facing +X, part-way along it (1 mm from its middle)
    S["hover"] = V(c.x + vx.vp.HOLE / 2.0, c.y - 1.0, vx.T)
    vx.hover_pixel(h.screen_point(S["hover"]))


def e_lit():
    sn = snaps()
    hot = sn.hot if sn is not None else None
    vx.lit(sn, "the hole's edge", "loop", vx.hole_centre(*SECOND))
    h.check(
        "with the hole's direction (up, out of the web)",
        hot is not None and hot.get("axis") is not None and hot["axis"].z > 0.999,
        hot and hot.get("axis"),
    )
    h.shot("E-edge")
    h.click(S["hover"])


def e_preview():
    ok, box = on_hole(SECOND)
    h.check("the standoff stands on that hole, along the hole", ok, box)
    vx.ok()


def e_done():
    h.check("dialog closed", vx.panel() is None)
    h.check("two Align steps", len(aligns()) == 2, aligns())
    ok, box = on_hole(SECOND)
    h.check("kept: on the second hole", ok, box)
    vx.no_popups("Align")


h.run(
    "vex_align",
    t.watched(
        [
            setup,
            a_open,
            a_components,
            a_hover_top,
            a_click_top,
            a_taken,
            b_hover_web,
            b_lit,
            b_preview,
            c_ok,
            c_done,
            c_undone,
            c_redone,
            d_open,
            d_components,
            d_hover_top,
            d_click_top,
            d_shift_hover,
            d_no_dots,
            d_plain_pick,
            d_dots_back,
            d_cancelled,
            e_open,
            e_components,
            e_hover_top,
            e_click_top,
            e_hover_edge,
            e_lit,
            e_preview,
            e_done,
        ]
    ),
    paced_by="state",
)

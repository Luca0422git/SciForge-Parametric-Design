# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: a square shaft through a square hole of a C-channel on a revolute joint, then
driven, only real input (docs/sciforge/parity/vex-assembly.md). SciForge's own VEX-like
parts from their STEP files: a 1x2x1x5 aluminium C-channel at the origin (the web's top at
z = 0.064 in, square holes 0.182 in on a 0.5 in grid) and a 1/8 in square shaft 3 in long
standing beside it.

  A  J; the mouse on the shaft's top end: its centre (on the shaft's axis) is lit; click. The
     mouse next to a square hole of the web: the hole's centre is lit (SciForge); click: the
     shaft stands on the web over the hole. Offset Z -1.5 in: the shaft goes down through
     the hole (half of it below the web), its axis on the hole's centre.
  B  Motion: Revolute; OK: "Revolute 1", the shaft still through the hole.
  C  Drive Joints (right-click the joint in the browser): 45 degrees: the shaft turns about
     the hole's axis (its corners swing out to the square's diagonal) and stays on the
     hole's centre; the channel does not move. OK; Undo: back square to the channel.
  D  The shaft's row in the browser, right-click > Hide: the shaft is hidden; right-click >
     Show: shown again.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
SHAFT_AT = V(-20, 19.05, 0)  # the shaft's axis on the design's floor
LENGTH = 3.0 * vx.IN
SIDE = 0.125 * vx.IN
HOLE = (2, 1)  # the web hole the shaft goes through (row 1: not hidden by the front flange)
DOWN = -LENGTH / 2.0  # Offset Z: half the shaft below the web


def shaft():
    return S["shaft"]


def channel():
    return S["channel"]


def hover():
    p = vx.panel()
    return getattr(p, "hover", None) if p is not None else None


def top():
    """The centre of the shaft's top end, and a point of that face 0.6 mm from it toward
    the viewer (the end is 3.2 mm square)."""
    box = vx.bbox(shaft())
    centre = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)
    return centre, vx.toward_viewer(centre, 0.6)


def width():
    box = vx.bbox(shaft())
    return box.XLength, box.YLength


def through(where, low):
    """The shaft's axis on the hole's centre, from `low` up one shaft length."""
    box = vx.bbox(shaft())
    c = vx.hole_centre(*HOLE)
    h.check(
        "%s: the shaft's axis on the hole's centre" % where,
        vx.near_xy(vx.axis_xy(shaft()), c, 1e-4),
        (box, c),
    )
    h.check(
        "%s: the shaft from z %.3f up %.1f mm" % (where, low, LENGTH),
        abs(box.ZMin - low) < 1e-4 and abs(box.ZMax - (low + LENGTH)) < 1e-4,
        box,
    )


def revolute():
    found = [o for o in vx.joints_list() if o.Label == "Revolute 1"]
    return found[0] if found else None


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexShaft")
    S["channel"] = vx.insert("c_channel_1x2x1x5")
    S["shaft"] = vx.insert("shaft_3in", App.Placement(SHAFT_AT, App.Rotation()))
    vx.fit()
    box = vx.bbox(shaft())
    h.check("the shaft stands beside the channel", abs(box.ZMax - LENGTH) < 1e-6, box)
    S["channel_box"] = vx.bbox(channel())


# -- A: the shaft's end onto the hole's centre, then down through it -------------------------------
def a_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def a_hover_top():
    p = vx.joint_panel()
    h.check("Joint dialog open", p is not None and p.active == "comp1", p and p.active)
    centre, _point = top()
    vx.look_at(centre, 15.0)
    S["top"], S["hover"] = top()
    vx.hover(S["hover"])


def a_top_lit():
    hov = hover()
    h.check(
        "the hover is on the shaft",
        hov is not None and hov.pick is not None and hov.pick.part is shaft(),
        hov and hov.pick,
    )
    vx.lit(hov, "the shaft's top end", "centre", S["top"])
    h.click(S["hover"])


def a_hover_hole():
    p = vx.joint_panel()
    h.check("component 1 taken", p is not None and p.picks["comp1"] is not None, p and p.picks)
    c = vx.hole_centre(*HOLE)
    vx.look_at(c, 40.0)
    S["hover"] = V(c.x + 3.6, c.y, vx.T)  # on the metal, 1.3 mm from the hole's edge
    vx.hover(S["hover"])


def a_hole_lit():
    vx.lit(hover(), "component 2: next to the hole", "loop", vx.hole_centre(*HOLE))
    h.click(S["hover"])


def a_on_web():
    through("joined", vx.T)
    h.shot("A-on-web")
    p = vx.joint_panel()
    if h.check("the Joint dialog stays open", p is not None, p):
        s.type_value(p.offset_fields["z"].widget, "%.2f" % DOWN)


def a_through():
    through("Offset Z -1.5 in", vx.T + DOWN)
    h.shot("A-through")


# -- B: Revolute, OK -------------------------------------------------------------------------------
def b_revolute():
    p = vx.joint_panel()
    j.click_tab(p, "Motion")
    j.choose_type(p, "Revolute")


def b_ok():
    vx.ok()


def b_made():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    h.check("Revolute 1 made", revolute() is not None, [o.Label for o in vx.joints_list()])
    through("after OK", vx.T + DOWN)
    S["width"] = width()
    h.check(
        "the shaft square to the channel (3.2 mm across)",
        all(abs(w - SIDE) < 1e-4 for w in S["width"]),
        S["width"],
    )


# -- C: drive it -----------------------------------------------------------------------------------
def c_drive():
    h.click_empty()
    j.browser_menu("Revolute 1", "Drive Joints")


def c_type():
    p = j.panel()
    h.check(
        "Drive Joints on Revolute 1",
        p is not None and getattr(p, "joint", None) is revolute(),
        p and getattr(p, "joint", None),
    )
    if p is not None:
        s.type_value(p.angle.widget, "45")


def c_turned():
    diagonal = SIDE * math.sqrt(2.0)
    w = width()
    h.check(
        "45 degrees: the shaft turned about the hole's axis (its corners out to the diagonal)",
        all(abs(x - diagonal) < 1e-3 for x in w),
        (w, diagonal),
    )
    through("turned", vx.T + DOWN)
    box, was = vx.bbox(channel()), S["channel_box"]
    h.check(
        "the channel did not move",
        all(
            abs(getattr(box, k) - getattr(was, k)) < 1e-6
            for k in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")
        ),
        (box, was),
    )
    h.shot("C-turned")
    j.ok()


def c_undo():
    j.no_dialog("Drive OK")
    s.undo()


def c_undone():
    w = width()
    h.check("Undo: the shaft square again", all(abs(x - SIDE) < 1e-4 for x in w), w)
    through("undone", vx.T + DOWN)
    vx.no_popups("Drive Joints")


# -- D: Show/Hide from the browser ----------------------------------------------------------------
def d_hide():
    from SciForgeTests.gui import timeline_input as t

    h.click_empty()
    t.row_menu(shaft().Label, "Hide")  # (Show/Hide reads Hide on a shown row)


def d_hidden():
    from SciForgeTests.gui import timeline_input as t

    h.check("Hide: the shaft is hidden", not shaft().ViewObject.Visibility)
    t.row_menu(shaft().Label, "Show")


def d_shown():
    h.check("Show: the shaft is shown again", shaft().ViewObject.Visibility)


h.run(
    "vex_shaft",
    [
        setup,
        a_press_j,
        a_hover_top,
        a_top_lit,
        a_hover_hole,
        a_hole_lit,
        a_on_web,
        a_through,
        b_revolute,
        b_ok,
        b_made,
        c_drive,
        c_type,
        c_turned,
        c_undo,
        c_undone,
        d_hide,
        d_hidden,
        d_shown,
    ],
    paced_by="state",
)

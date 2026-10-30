# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): a 1/8 in square shaft through square holes of TWO C-channels on a
revolute joint, driven, the way a VEX team builds a gearbox side; only real input in the
dialogs. SciForge's own VEX-like parts (SciForgeTests/fixtures/vex): two 1x2x1x5 aluminium
C-channels (A at the origin, B beside it) and a 3 in square shaft standing apart.

  A  J: B's web next to its hole (2, 1), then A's web next to its hole (2, 1): B comes onto A
     face to face, the two holes on one axis; Offset Z 1 in: B 1 in above A. OK (Rigid).
  B  J: the shaft's top end, then B's (outer, upward) web next to its hole (2, 1): the shaft
     stands on B over the hole; Offset Z -2 in: down through B's hole and A's hole; Motion:
     Revolute; OK.
  C  Drive Joints 45 degrees: the shaft turns about the holes' common axis and stays on both
     holes' centres; neither channel moves. OK; Undo: square again.
  D  Save, close, reopen: the channels and the shaft are where they were; Drive Joints
     30 degrees after reopening turns the shaft about the same axis.
"""

import math
import os

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
B_AT = V(-90, 0, 0)  # channel B before it is jointed
SHAFT_AT = V(-30, 60, 0)
HOLE = (2, 1)
UP = 1.0 * vx.IN  # B above A
DOWN = -2.0 * vx.IN  # the shaft pushed down from B's outer face
LENGTH = 3.0 * vx.IN
SIDE = 0.125 * vx.IN
EPS = 1e-4


def hover():
    p = vx.panel()
    return getattr(p, "hover", None) if p is not None else None


def axis_xy(comp):
    return vx.axis_xy(comp)


def hole_axis():
    """Both holes' common axis (x, y): A's hole (2, 1)."""
    return vx.hole_centre(*HOLE)


def b_outer_z():
    """The height of B's outer web face once B lies face down 1 in above A."""
    return vx.T + UP + vx.T


def channel_still(name):
    box, was = vx.bbox(S[name]), S[name + "_box"]
    return h.check(
        "channel %s did not move" % name.upper(),
        all(
            abs(getattr(box, k) - getattr(was, k)) < 1e-5
            for k in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")
        ),
        (box, was),
    )


def shaft_through(where, turned=0.0):
    box = vx.bbox(S["shaft"])
    c = hole_axis()
    h.check(
        "%s: the shaft's axis on both holes' axis" % where,
        vx.near_xy(vx.axis_xy(S["shaft"]), c, EPS),
        (box, c),
    )
    low = b_outer_z() + DOWN
    h.check(
        "%s: the shaft from z %.2f up 3 in (through A's web and B's)" % (where, low),
        abs(box.ZMin - low) < 1e-3 and abs(box.ZMax - (low + LENGTH)) < 1e-3,
        box,
    )
    h.check(
        "%s: the shaft passes A's web and B's web" % where,
        box.ZMin < 0.0 and box.ZMax > b_outer_z(),
        box,
    )
    a = math.radians(turned)
    wide = SIDE * (abs(math.cos(a)) + abs(math.sin(a)))
    h.check(
        "%s: the shaft's width %.3f (turned %g degrees)" % (where, wide, turned),
        abs(box.XLength - wide) < 1e-3 and abs(box.YLength - wide) < 1e-3,
        (box.XLength, box.YLength),
    )


def b_on_a(where):
    """B lies face down 1 in above A, its hole (2, 1) on A's hole (2, 1) axis."""
    plc = S["b"].Placement
    c = vx.hole_centre(*HOLE, top=True, origin=plc)
    h.check(
        "%s: B's hole (2, 1) on A's hole's axis" % where,
        vx.near_xy(c, hole_axis(), EPS),
        (c, hole_axis()),
    )
    h.check(
        "%s: B's web face down, 1 in above A's web" % where,
        abs(c.z - (vx.T + UP)) < 1e-3 and plc.Rotation.multVec(V(0, 0, 1)).z < -0.999,
        (c, plc),
    )


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexShaft2")
    S["a"] = vx.insert("c_channel_1x2x1x5")
    S["b"] = vx.insert("c_channel_1x2x1x5", App.Placement(B_AT, App.Rotation()))
    S["shaft"] = vx.insert("shaft_3in", App.Placement(SHAFT_AT, App.Rotation()))
    vx.fit()
    from sciforge import instances

    h.check(
        "the second channel is an occurrence of the first (the same file again)",
        instances.is_instance(S["b"]),
        S["b"].Label,
    )


def web_point(origin, i, j, top=True, dx=3.6):
    c = vx.hole_centre(i, j, top=top, origin=origin)
    return V(c.x + dx, c.y, c.z)


# -- A: B onto A ---------------------------------------------------------------------------------
def a_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def a_hover_b():
    p = vx.joint_panel()
    h.check("Joint dialog open", p is not None and p.active == "comp1", p and p.active)
    S["pt"] = web_point(S["b"].Placement, *HOLE)
    vx.look_at(vx.hole_centre(*HOLE, origin=S["b"].Placement), 40.0)
    vx.hover(S["pt"])


def a_click_b():
    vx.lit(hover(), "B next to its hole", "loop", vx.hole_centre(*HOLE, origin=S["b"].Placement))
    h.click(S["pt"])


def a_hover_a():
    S["pt"] = web_point(App.Placement(), *HOLE)
    vx.look_at(hole_axis(), 40.0)
    vx.hover(S["pt"])


def a_click_a():
    vx.lit(hover(), "A next to its hole", "loop", vx.hole_centre(*HOLE))
    h.click(S["pt"])


def a_offset():
    p = vx.joint_panel()
    if h.check("the Joint dialog stays open", p is not None, p):
        s.type_value(p.offset_fields["z"].widget, "1 in")


def a_ok():
    b_on_a("joined, Offset Z 1 in")
    vx.ok()


def a_made():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    h.check("one joint", len(vx.joints_list()) == 1, [o.Label for o in vx.joints_list()])
    b_on_a("after OK")
    S["a_box"] = vx.bbox(S["a"])
    S["b_box"] = vx.bbox(S["b"])


# -- B: the shaft through both -------------------------------------------------------------------
def b_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def b_hover_top():
    box = vx.bbox(S["shaft"])
    S["top"] = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)
    vx.look_at(S["top"], 15.0)
    S["pt"] = vx.toward_viewer(S["top"], 0.6)
    vx.hover(S["pt"])


def b_click_top():
    hov = hover()
    h.check(
        "the hover is on the shaft",
        hov is not None and hov.pick is not None and hov.pick.part is S["shaft"],
        hov and hov.pick,
    )
    vx.lit(hov, "the shaft's top end", "centre", S["top"])
    h.click(S["pt"])


def b_hover_b():
    c = V(hole_axis().x, hole_axis().y, b_outer_z())
    S["b_hole"] = c
    vx.look_at(c, 40.0)
    S["pt"] = V(c.x + 3.6, c.y, c.z)
    vx.hover(S["pt"])


def b_click_b():
    hov = hover()
    h.check(
        "the hover is on B's outer web face",
        hov is not None and hov.pick is not None and hov.pick.part is S["b"],
        hov and hov.pick,
    )
    vx.lit(hov, "B's outer face next to its hole", "loop", S["b_hole"])
    hot = hov.hot if hov is not None else None
    h.check(
        "the hole's joint origin points up (out of B's outer face)",
        hot is not None and hot["frame"].Rotation.multVec(V(0, 0, 1)).z > 0.999,
        hot and hot["frame"],
    )
    h.click(S["pt"])


def b_offset():
    box = vx.bbox(S["shaft"])
    h.check(
        "joined: the shaft's end on B's outer face over the hole",
        vx.near_xy(vx.axis_xy(S["shaft"]), hole_axis(), EPS) and abs(box.ZMin - b_outer_z()) < 1e-3,
        box,
    )
    p = vx.joint_panel()
    if h.check("the Joint dialog stays open", p is not None, p):
        s.type_value(p.offset_fields["z"].widget, "-2 in")


def b_revolute():
    shaft_through("Offset Z -2 in")
    p = vx.joint_panel()
    j.click_tab(p, "Motion")
    j.choose_type(p, "Revolute")


def b_ok():
    vx.ok()


def b_made():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    found = [o for o in vx.joints_list() if o.Label.startswith("Revolute")]
    h.check("a revolute joint", len(found) == 1, [o.Label for o in vx.joints_list()])
    S["revolute"] = found[0] if found else None
    shaft_through("after OK")
    channel_still("a")
    channel_still("b")


# -- C: drive --------------------------------------------------------------------------------------
def drive_steps(prefix, degrees):
    def drive():
        h.click_empty()
        if S.get("revolute") is not None:
            j.browser_menu(S["revolute"].Label, "Drive Joints")

    def type_angle():
        p = j.panel()
        h.check(
            "%s: Drive Joints on the revolute" % prefix,
            p is not None and getattr(p, "joint", None) is S.get("revolute"),
            p and getattr(p, "joint", None),
        )
        if p is not None:
            s.type_value(p.angle.widget, "%g" % degrees)

    def turned():
        shaft_through("%s: driven %g degrees" % (prefix, degrees), degrees)
        channel_still("a")
        channel_still("b")
        h.shot("%s-driven" % prefix)
        j.ok()

    drive.__name__ = "%s_drive" % prefix
    type_angle.__name__ = "%s_type" % prefix
    turned.__name__ = "%s_turned" % prefix
    return [drive, type_angle, turned]


def c_undo():
    j.no_dialog("Drive OK")
    s.undo()


def c_undone():
    shaft_through("Undo")
    channel_still("a")
    channel_still("b")


# -- D: save, reopen, drive again ------------------------------------------------------------------
def d_save():
    S["path"] = vx.save_as("vex_qa_shaft2")
    S["labels"] = {k: S[k].Label for k in ("a", "b", "shaft")}
    S["joint_label"] = S["revolute"].Label if S.get("revolute") is not None else None
    App.closeDocument(App.ActiveDocument.Name)


def d_open():
    App.openDocument(S["path"])
    Gui.activateWorkbench("SciForgeWorkbench")


def d_reopened():
    from sciforge import components

    by = {c.Label: c for c in components.list_components(App.ActiveDocument)}
    for k, label in S["labels"].items():
        S[k] = by.get(label)
    if not h.check("the parts are back", all(S[k] is not None for k in S["labels"]), sorted(by)):
        return
    found = [o for o in vx.joints_list() if o.Label == S["joint_label"]]
    S["revolute"] = found[0] if found else None
    h.check("the revolute is back", S["revolute"] is not None, [o.Label for o in vx.joints_list()])
    b_on_a("reopened")
    shaft_through("reopened")
    S["a_box"] = vx.bbox(S["a"])
    S["b_box"] = vx.bbox(S["b"])
    vx.fit()


def d_cleanup():
    try:
        os.remove(S["path"])
    except OSError:
        pass


h.run(
    "vex_qa_shaft2",
    [
        setup,
        a_press_j,
        a_hover_b,
        a_click_b,
        a_hover_a,
        a_click_a,
        a_offset,
        a_ok,
        a_made,
        b_press_j,
        b_hover_top,
        b_click_top,
        b_hover_b,
        b_click_b,
        b_offset,
        b_revolute,
        b_ok,
        b_made,
    ]
    + drive_steps("c", 45.0)
    + [c_undo, c_undone, d_save, d_open, d_reopened]
    + drive_steps("d", 30.0)
    + [d_cleanup],
    paced_by="state",
)

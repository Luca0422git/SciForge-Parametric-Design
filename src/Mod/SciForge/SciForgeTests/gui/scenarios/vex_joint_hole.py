# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: a screw jointed into a square hole of a C-channel, only real input
(docs/sciforge/parity/vex-assembly.md). The parts are SciForge's own VEX-like parts
(SciForgeTests/fixtures/vex), inserted from their STEP files: a 1x2x1x5 aluminium
C-channel (square holes 0.182 in on a 0.5 in grid, the web's top at z = 0.064 in) at the
origin and a #8-32 x 0.5 in screw standing upside down beside it (its head's underside faces
up).

  A  J; the mouse on the web next to a square hole: the hole's centre is lit (SciForge: Fusion
     has no such snap), only a few dots are drawn (not the face's hundreds); the mouse into
     the hole: the hole's centre stays lit (on the hole's axis); onto the hole's edge: the
     edge offers the hole's centre too.
  B  Ctrl: the mouse on the screw head's underside, Ctrl held, the mouse onto the head's
     round edge: the face's dots stay (Fusion's Ctrl lock); Ctrl+click takes the face. Esc.
  C  Refusal: J, the screw, the screw again: "Both picks are on ..." Esc.
  D  Esc after two picks: the screw goes back.
  E  The joint: J, the screw's underside, the hole's centre: the screw stands in the hole
     (its axis on the hole's centre, the head on the web); OK: one joint. Ctrl+Z / Ctrl+Y.
  F  The channel edited after jointing (a new hole cut elsewhere in its web, so its faces and
     edges are numbered anew): the screw stays in its hole.
  G  Save, close, reopen: the screw is still in its hole; a recompute keeps it there.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
SCREW_AT = V(-20, 19.05, 0)  # the upside-down screw's axis, on the design's floor
HOLE = (2, 1)  # the web hole the screw goes into (row 1: not hidden by the front flange)


def screw():
    return S["screw"]


def channel():
    return S["channel"]


def hover():
    p = vx.panel()
    return getattr(p, "hover", None) if p is not None else None


def web_point(i, j, dx=3.6, dy=0.0):
    """A point on the web's top face next to hole (i, j) (on the metal)."""
    c = vx.hole_centre(i, j)
    return V(c.x + dx, c.y + dy, vx.T)


def underside_point(r=2.75):
    # the head's underside ring (radius 2.08 .. 3.43 mm), on the viewer's side of the shank
    return vx.toward_viewer(SCREW_AT, r)


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexJoint")
    S["channel"] = vx.insert("c_channel_1x2x1x5")
    S["screw"] = vx.insert("screw_8_32_x_0_5", vx.flipped(SCREW_AT.x, SCREW_AT.y, 0))
    vx.fit()
    h.check("two components", channel() is not None and screw() is not None)
    box = vx.bbox(screw())
    h.check("the screw stands upside down", abs(box.ZMax - 12.7) < 1e-3, box)


setup.wait_ms = 1500


# -- A: the hover ----------------------------------------------------------------------------------
def a_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def a_hover_web():
    p = vx.joint_panel()
    h.check("Joint dialog open", p is not None and p.active == "comp1", p and p.active)
    vx.look_at(vx.hole_centre(*HOLE), 40.0)
    vx.hover(web_point(*HOLE))


def a_hole_lit():
    hov = hover()
    h.check(
        "the hover is on the channel's web",
        hov is not None and hov.pick is not None and hov.pick.part is channel(),
        hov and hov.pick,
    )
    vx.lit(hov, "next to the hole", "loop", vx.hole_centre(*HOLE))
    n = vx.drawn(hov)
    h.check("only the dots near the mouse are drawn (not hundreds)", 0 < n <= 30, n)
    h.check(
        "the hole's centre comes with a triad (joint origin Z up)",
        hov.hot is not None and hov.hot["frame"].Rotation.multVec(V(0, 0, 1)).z > 0.999,
        hov.hot and hov.hot["frame"],
    )
    h.shot("A-hole-lit")


def a_into_hole():
    vx.hover(vx.hole_centre(*HOLE) + V(0.4, 0.3, 0))


def a_still_lit():
    hov = hover()
    c = vx.hole_centre(*HOLE)
    hot = hov.hot if hov is not None else None
    h.check(
        "inside the hole its centre stays lit (on the hole's axis)",
        hot is not None
        and hot["kind"] in ("loop", "hole_top", "hole_mid", "hole_bottom")
        and vx.near_xy(hot["point"], c),
        hot and (hot["kind"], hot["point"]),
    )


def a_hover_edge():
    c = vx.hole_centre(*HOLE)
    # the hole's edge facing +X (x = c + half the hole), part-way along it
    S["edge_point"] = V(c.x + vx.vp.HOLE / 2.0, c.y - 1.0, vx.T)
    from SciForgeTests.gui import harness

    pixel = harness.screen_point(S["edge_point"])
    vx.hover_pixel(pixel)


def a_edge_offers_centre():
    hov = hover()
    c = vx.hole_centre(*HOLE)
    loops = [x for x in (hov.candidates if hov is not None else []) if x["kind"] == "loop"]
    h.check(
        "on the hole's edge the hole's centre is offered",
        any((x["point"] - c).Length < 1e-5 for x in loops),
        [(x["kind"], x["point"]) for x in (hov.candidates if hov else [])][:8],
    )
    # right on the edge its own middle / corners are nearer than the centre (Fusion's dots)
    vx.lit(hov, "on the hole's edge", ("loop", "midpoint", "vertex"))
    print("[SciForge] vex view direction %s" % vx.view_direction(), flush=True)


# -- B: Ctrl keeps the face ------------------------------------------------------------------------
def b_hover_underside():
    vx.look_at(SCREW_AT, 25.0)
    vx.hover(underside_point())


def b_underside_lit():
    hov = hover()
    h.check(
        "the hover is on the screw",
        hov is not None and hov.pick is not None and hov.pick.part is screw(),
        hov and hov.pick,
    )
    vx.lit(hov, "the head's underside", "centre", SCREW_AT)
    S["face"] = hov.pick.element if hov and hov.pick else ""
    vx.ctrl(True)
    # onto the head's round outer edge (radius 3.43), Ctrl held
    vx.hover(underside_point(3.43), QtCore.Qt.ControlModifier)


def b_locked():
    hov = hover()
    h.check(
        "Ctrl keeps the face",
        hov is not None and hov.locked and hov.pick.element == S["face"],
        hov and (hov.locked, hov.pick and hov.pick.element),
    )
    h.click(underside_point(3.43), modifiers=QtCore.Qt.ControlModifier)


b_locked.wait_ms = 500


def b_taken():
    vx.ctrl(False)
    p = vx.joint_panel()
    pick = p.picks["comp1"] if p is not None else None
    h.check(
        "component 1 = the screw's face (not its edge)",
        pick is not None and pick.part is screw() and pick.element == S["face"],
        pick,
    )
    h.press(QtCore.Qt.Key_Escape)


def b_closed():
    h.check("Esc closed the dialog", vx.joint_panel() is None)
    h.check("no joint", not vx.joints_list(), vx.joints_list())


# -- C: refusal ------------------------------------------------------------------------------------
def c_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def c_screw():
    vx.look_at(SCREW_AT, 25.0)
    vx.hover(underside_point())
    h.click(underside_point())


def c_screw_again():
    side = underside_point(2.08) + V(0, 0, 8.0)  # the shank's side
    vx.hover(side)
    h.click(side)


def c_refused():
    p = vx.joint_panel()
    text = p.message.text() if p is not None else ""
    h.check("refused: both picks on the screw", "Both picks are on" in text, text)
    h.check("still waiting for component 2", p is not None and p.active == "comp2", p and p.active)
    h.check("no joint", not vx.joints_list())


# -- D: Esc after two picks ------------------------------------------------------------------------
def d_hole():
    vx.look_at(vx.hole_centre(3, 1), 40.0)
    vx.hover(web_point(3, 1))
    h.click(web_point(3, 1))


d_hole.wait_ms = 1200


def d_moved():
    box = vx.bbox(screw())
    c = vx.hole_centre(3, 1)
    h.check(
        "the screw went into hole (3, 1)",
        abs((box.XMin + box.XMax) / 2 - c.x) < 1e-3 and abs((box.YMin + box.YMax) / 2 - c.y) < 1e-3,
        box,
    )
    h.press(QtCore.Qt.Key_Escape)


def d_back():
    h.check("Esc: no dialog", vx.joint_panel() is None)
    box = vx.bbox(screw())
    h.check(
        "the screw is back where it stood",
        abs((box.XMin + box.XMax) / 2 - SCREW_AT.x) < 1e-3 and abs(box.ZMax - 12.7) < 1e-3,
        box,
    )
    h.check("no joint", not vx.joints_list())


# -- E: the joint ----------------------------------------------------------------------------------
def e_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def e_screw():
    vx.look_at(SCREW_AT, 25.0)
    vx.hover(underside_point())
    h.click(underside_point())


def e_hole():
    p = vx.joint_panel()
    h.check("component 1 taken", p is not None and p.picks["comp1"] is not None, p and p.picks)
    vx.look_at(vx.hole_centre(*HOLE), 40.0)
    vx.hover(web_point(*HOLE))
    vx.lit(hover(), "component 2: next to the hole", "loop", vx.hole_centre(*HOLE))
    h.click(web_point(*HOLE))


e_hole.wait_ms = 1500


def in_hole(where):
    box = vx.bbox(screw())
    c = vx.hole_centre(*HOLE)
    head = 0.08 * vx.IN
    h.check(
        "%s: the screw's axis on the hole's centre" % where,
        abs((box.XMin + box.XMax) / 2 - c.x) < 1e-3 and abs((box.YMin + box.YMax) / 2 - c.y) < 1e-3,
        (box, c),
    )
    h.check(
        "%s: the head on the web, the shank down through the hole" % where,
        abs(box.ZMin - (vx.T - 12.7)) < 1e-3 and abs(box.ZMax - (vx.T + head)) < 1e-3,
        box,
    )


def e_joined():
    in_hole("joined")
    h.check("one joint", len(vx.joints_list()) == 1, vx.joints_list())
    vx.ok()


def e_ok():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    joints = vx.joints_list()
    h.check("one joint kept", len(joints) == 1, joints)
    if joints:
        import json

        record = json.loads(joints[0].SciForgeSnap2 or "{}")
        S["record"] = record
        h.check(
            "the joint remembers the hole (its centre, size, direction)",
            record.get("kind") == "loop" and record.get("loop", {}).get("a", 0) > 20.0,
            record,
        )
    in_hole("after OK")
    vx.undo()


def e_undone():
    h.check("Ctrl+Z: no joint", not vx.joints_list())
    box = vx.bbox(screw())
    h.check("the screw is back", abs(box.ZMax - 12.7) < 1e-3, box)
    vx.redo()


def e_redone():
    h.check("Ctrl+Y: the joint", len(vx.joints_list()) == 1)
    in_hole("after Ctrl+Y")


# -- F: the channel edited -------------------------------------------------------------------------
def f_edit_channel():
    """A round hole cut through the web between the holes (an Extrude cut in the channel's
    body): the web's faces and edges are numbered anew."""
    from sciforge import extrude, sketch_ui

    doc = App.ActiveDocument
    body = vx.body_of(channel())
    before = len(body.Shape.Edges)
    S["edges_before"] = before
    planes = sketch_ui.origin_planes(body)
    sk = sketch_ui.create_sketch(body, (planes["XY_Plane"], ""))
    h.draw_circle(sk, 0.5 * vx.PITCH * 3, vx.PITCH, 1.5)  # x 19.05, y 12.7: between the rows
    doc.openTransaction("Cut")
    extrude.make(body, sk, {"operation": "cut", "distance": 5.0, "direction": "symmetric"})
    doc.commitTransaction()
    doc.recompute()


f_edit_channel.wait_ms = 2000


def f_still_in_hole():
    body = vx.body_of(channel())
    h.check(
        "the channel was changed (more edges)",
        len(body.Shape.Edges) > S["edges_before"],
        (len(body.Shape.Edges), S["edges_before"]),
    )
    App.ActiveDocument.recompute()
    from sciforge import joints

    joints.solve(App.ActiveDocument)
    in_hole("after the edit")


f_still_in_hole.wait_ms = 1000


# -- G: save, reopen -------------------------------------------------------------------------------
def g_save():
    S["path"] = vx.save_as("vex_joint_hole")
    h.check("saved", os.path.isfile(S["path"]), S["path"])
    S["doc"] = App.ActiveDocument.Name
    App.closeDocument(S["doc"])


def g_reopen():
    App.openDocument(S["path"])
    vx.fit()


g_reopen.wait_ms = 2500


def g_reopened():
    doc = App.ActiveDocument
    comps = {c.Label: c for c in doc.Objects if c.TypeId == "App::Part"}
    S["channel"] = comps.get("c_channel_1x2x1x5")
    S["screw"] = comps.get("screw_8_32_x_0_5")
    h.check("both components back", S["channel"] is not None and S["screw"] is not None, comps)
    h.check("the joint is back", len(vx.joints_list()) == 1, vx.joints_list())
    in_hole("reopened")
    doc.recompute()
    from sciforge import joints

    joints.solve(doc)
    in_hole("reopened, recomputed and solved")


h.run(
    "vex_joint_hole",
    [
        setup,
        a_press_j,
        a_hover_web,
        a_hole_lit,
        a_into_hole,
        a_still_lit,
        a_hover_edge,
        a_edge_offers_centre,
        b_hover_underside,
        b_underside_lit,
        b_locked,
        b_taken,
        b_closed,
        c_press_j,
        c_screw,
        c_screw_again,
        c_refused,
        d_hole,
        d_moved,
        d_back,
        e_press_j,
        e_screw,
        e_hole,
        e_joined,
        e_ok,
        e_undone,
        e_redone,
        f_edit_channel,
        f_still_in_hole,
        g_save,
        g_reopen,
        g_reopened,
    ],
)

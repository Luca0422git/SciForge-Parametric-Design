# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX QA (beta 3): the team's workflow on parts with the traits of real VEX STEP files that
the builder's clean test parts lack (SciForgeTests/fixtures/vex/vex_real.py: every file in
INCH units; square holes with tiny rounded corners; holes cut in two halves, so their outlines
have split sides and their walls more faces; a motor that comes in as an ASSEMBLY of three
solids with a blind square socket). Only real input in the dialogs.

  A  J; the mouse next to a hole with tiny rounded corners: the hole's centre is lit, on the
     true centre; into the hole: still lit; next to a hole of the split channel: its true
     centre is lit; on a split side of that hole: the edge offers the hole's centre. Esc.
  B  J: the screw's head underside, then the dot of a tiny-rounded hole: the screw stands in
     the hole (axis on the true centre, the head on the web). OK.
  C  The screw picked, ASSEMBLE > Duplicate With Joints, a click next to a split hole: a copy
     of the screw stands in that hole (axis on its true centre, head on the web). OK.
  D  J: the square shaft's end, then the dot of the motor's square socket (inside the round
     boss of the motor assembly); Offset Z -0.2 in: the shaft goes 0.2 in into the socket;
     Motion: Revolute; OK.
  E  Drive Joints 30 degrees: the shaft turns about the socket's axis and stays on it; the
     motor does not move. Undo.
  F  Save, close, reopen: the screws and the shaft are where they were; a recompute keeps
     them there.
"""

import math
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.fixtures.vex import vex_real as vr
from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
SPLIT_AT = V(0, 40, 0)  # the split channel stands beside the rounded one
SCREW_AT = V(-20, 19.05, 0)  # the upside-down screw's axis on the floor
SHAFT_AT = V(-20, 70, 0)  # the shaft standing on the floor
MOTOR_AT = V(90, 0, 0)  # the motor case's corner
HOLE = (2, 1)  # the rounded channel's hole the screw goes into
SPLIT_HOLE = (1, 1)  # the split channel's hole the copy goes into
HEAD = 0.08 * vx.IN
SHANK = 0.5 * vx.IN
LENGTH = 3.0 * vx.IN
SIDE = 0.125 * vx.IN


# -- parts ---------------------------------------------------------------------------------------
def insert_real(name, placement=None):
    """Insert one of the real-looking STEP files (inches) as a component, placed."""
    from sciforge import exchange_core, step_import

    doc = App.ActiveDocument
    path = vr.write_all(vx.folder(), [name])[name]
    doc.openTransaction("Insert STEP")
    made = step_import.import_file(doc, path, exchange_core.INSERT)
    doc.commitTransaction()
    if placement is not None:
        made.top.Placement = placement
    doc.recompute()
    step_import.apply_looks(made)
    return made.top


def comp_body(comp, label=None):
    from sciforge import components

    found = components.bodies_in(comp.Document, comp, recursive=True)
    if label is not None:
        found = [b for b in found if components.container_of(b).Label == label]
    return found[0] if found else None


def gbox(comp):
    from sciforge import bodies

    return bodies.global_shape(comp_body(comp)).BoundBox


def axis_xy(box):
    return V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)


def split_centre(i, j):
    return vx.hole_centre(i, j) + SPLIT_AT


def socket_top():
    x, y, z = vr.socket_top()
    return V(x, y, z) + MOTOR_AT


def hover():
    p = vx.panel()
    return getattr(p, "hover", None) if p is not None else None


def web_point(c, dx=3.6, dy=0.0):
    return V(c.x + dx, c.y + dy, vx.T)


def in_hole(where, comp, centre):
    """`comp` (a screw) stands in the hole at `centre`: its axis there, the head on the web."""
    box = gbox(comp)
    h.check(
        "%s: the screw's axis on the hole's true centre" % where,
        vx.near_xy(axis_xy(box), centre, 1e-4),
        (box, centre),
    )
    h.check(
        "%s: the head on the web, the shank down through it" % where,
        abs(box.ZMax - (vx.T + HEAD)) < 1e-3 and abs(box.ZMin - (vx.T - SHANK)) < 1e-3,
        box,
    )


def shaft_in_socket(where, turned=0.0):
    box = gbox(S["shaft"])
    c = socket_top()
    h.check(
        "%s: the shaft's axis on the socket's axis" % where,
        vx.near_xy(axis_xy(box), c, 1e-4),
        (box, c),
    )
    low = c.z - 0.2 * vx.IN
    h.check(
        "%s: the shaft 0.2 in into the socket, up from there" % where,
        abs(box.ZMin - low) < 1e-3 and abs(box.ZMax - (low + LENGTH)) < 1e-3,
        box,
    )
    a = math.radians(turned)
    wide = SIDE * (abs(math.cos(a)) + abs(math.sin(a)))
    h.check(
        "%s: the shaft %s"
        % (where, "square to the socket" if not turned else "turned %g deg" % turned),
        abs(box.XLength - wide) < 1e-3 and abs(box.YLength - wide) < 1e-3,
        (box.XLength, box.YLength, wide),
    )


def motor_still():
    box = gbox(S["motor"])
    h.check(
        "the motor did not move",
        (box.XMin - S["motor_box"].XMin) ** 2 + (box.YMin - S["motor_box"].YMin) ** 2 < 1e-8
        and abs(box.ZMin - S["motor_box"].ZMin) < 1e-6,
        (box, S["motor_box"]),
    )


# -- setup -----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("VexReal")
    S["round"] = insert_real("real_channel_fillet")
    S["split"] = insert_real("real_channel_split", App.Placement(SPLIT_AT, App.Rotation()))
    S["screw"] = insert_real("real_screw", vx.flipped(SCREW_AT.x, SCREW_AT.y, 0))
    S["shaft"] = insert_real("real_shaft", App.Placement(SHAFT_AT, App.Rotation()))
    S["motor"] = insert_real("real_motor", App.Placement(MOTOR_AT, App.Rotation()))
    vx.fit()
    box = vx.bbox(S["round"])
    h.check(
        "the inch file comes in at its size (63.5 mm long)", abs(box.XLength - 63.5) < 1e-6, box
    )
    from sciforge import components

    kids = [c.Label for c in components.components_in(App.ActiveDocument, S["motor"])]
    h.check("the motor comes in as an assembly", sorted(kids) == ["Cap", "Cartridge", "Case"], kids)
    S["motor_box"] = gbox(S["motor"])


setup.wait_ms = 2000


# -- A: the hover on real-looking holes ----------------------------------------------------------
def a_press_j():
    h.click_empty()
    vx.fit()
    h.press("j")


def a_hover_round():
    p = vx.joint_panel()
    h.check("Joint dialog open", p is not None and p.active == "comp1", p and p.active)
    vx.look_at(vx.hole_centre(*HOLE), 40.0)
    vx.hover(web_point(vx.hole_centre(*HOLE)))


def a_round_lit():
    hov = hover()
    h.check(
        "the hover is on the rounded channel",
        hov is not None and hov.pick is not None and hov.pick.part is S["round"],
        hov and hov.pick,
    )
    vx.lit(hov, "next to a tiny-rounded hole", "loop", vx.hole_centre(*HOLE))
    vx.hover(vx.hole_centre(*HOLE) + V(0.5, 0.4, 0))


def a_round_inside():
    hot = hover().hot if hover() is not None else None
    h.check(
        "inside the tiny-rounded hole its centre stays lit",
        hot is not None and hot.get("radius") and vx.near_xy(hot["point"], vx.hole_centre(*HOLE)),
        hot and (hot["kind"], hot["point"]),
    )
    c = split_centre(*SPLIT_HOLE)
    vx.look_at(c, 40.0)
    vx.hover(web_point(c))


def a_split_lit():
    hov = hover()
    h.check(
        "the hover is on the split channel",
        hov is not None and hov.pick is not None and hov.pick.part is S["split"],
        hov and hov.pick,
    )
    vx.lit(hov, "next to a split hole", "loop", split_centre(*SPLIT_HOLE))
    c = split_centre(*SPLIT_HOLE)
    # on the hole's side facing -Y (y = c - half the hole), split in two at x = c: its left half
    S["split_edge"] = V(c.x - 1.2, c.y - vx.vp.HOLE / 2.0, vx.T)
    vx.hover_pixel(h.screen_point(S["split_edge"]))


def a_split_edge():
    hov = hover()
    loops = [x for x in (hov.candidates if hov is not None else []) if x["kind"] == "loop"]
    h.check(
        "on a split side of the hole the hole's centre is offered",
        any((x["point"] - split_centre(*SPLIT_HOLE)).Length < 1e-5 for x in loops),
        hov and [(x["kind"], x["point"]) for x in hov.candidates][:8],
    )
    h.press(QtCore.Qt.Key_Escape)


# -- B: the screw into a tiny-rounded hole -------------------------------------------------------
def b_press_j():
    h.check("Esc closed the dialog", vx.joint_panel() is None)
    h.click_empty()
    vx.fit()
    h.press("j")


def b_hover_underside():
    vx.look_at(SCREW_AT, 25.0)
    S["under"] = vx.toward_viewer(SCREW_AT, 2.75)
    vx.hover(S["under"])


def b_click_underside():
    hov = hover()
    h.check(
        "the hover is on the screw",
        hov is not None and hov.pick is not None and hov.pick.part is S["screw"],
        hov and hov.pick,
    )
    vx.lit(hov, "the head's underside", "centre", SCREW_AT)
    h.click(S["under"])


b_click_underside.wait_ms = 400


def b_hover_hole():
    p = vx.joint_panel()
    h.check("component 1 taken", p is not None and p.picks["comp1"] is not None, p and p.picks)
    vx.look_at(vx.hole_centre(*HOLE), 40.0)
    vx.hover(web_point(vx.hole_centre(*HOLE)))


def b_click_hole():
    vx.lit(hover(), "component 2: next to the tiny-rounded hole", "loop", vx.hole_centre(*HOLE))
    h.click(web_point(vx.hole_centre(*HOLE)))


b_click_hole.wait_ms = 1500


def b_ok():
    in_hole("joined", S["screw"], vx.hole_centre(*HOLE))
    vx.ok()


b_ok.wait_ms = 1200


def b_made():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    h.check("one joint", len(vx.joints_list()) == 1, [o.Label for o in vx.joints_list()])
    in_hole("after OK", S["screw"], vx.hole_centre(*HOLE))


# -- C: Duplicate With Joints into a split hole ----------------------------------------------------
def dup_panel():
    from sciforge import duplicate_joints_ui

    p = duplicate_joints_ui.DuplicatePanel.last
    return None if p is None or p._closed else p


def c_pick():
    Gui.Selection.clearSelection()
    s.click_browser_row(S["screw"].Label)


def c_open():
    vx.menu("ASSEMBLE", "Duplicate With Joints")


c_open.wait_ms = 1200


def c_hover():
    p = dup_panel()
    if not h.check("Duplicate With Joints open", p is not None):
        return
    h.check("the position box waits", p.active == "position", p.active)
    c = split_centre(*SPLIT_HOLE)
    vx.look_at(c, 40.0)
    vx.hover(web_point(c))


def c_click():
    p = dup_panel()
    vx.lit(
        getattr(p, "hover", None),
        "a copy: next to the split hole",
        "loop",
        split_centre(*SPLIT_HOLE),
    )
    h.click(web_point(split_centre(*SPLIT_HOLE)))


c_click.wait_ms = 2000


def c_copy():
    from sciforge import instances

    copies = instances.instances_of(S["screw"])
    if h.check("one copy of the screw", len(copies) == 1, [c.Label for c in copies]):
        S["copy"] = copies[0]
        box = vx.bbox(copies[0])
        c = split_centre(*SPLIT_HOLE)
        h.check(
            "the copy's axis on the split hole's true centre",
            vx.near_xy(axis_xy(box), c, 1e-4),
            (box, c),
        )
        h.check(
            "the copy's head on the split channel's web", abs(box.ZMax - (vx.T + HEAD)) < 1e-3, box
        )
    vx.ok()


c_copy.wait_ms = 1200


# -- D: the shaft into the motor's socket, revolute ------------------------------------------------
def d_press_j():
    h.check("Duplicate With Joints closed", dup_panel() is None)
    h.click_empty()
    vx.fit()
    h.press("j")


def d_hover_top():
    box = gbox(S["shaft"])
    S["shaft_top"] = V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, box.ZMax)
    vx.look_at(S["shaft_top"], 15.0)
    S["shaft_hover"] = vx.toward_viewer(S["shaft_top"], 0.6)
    vx.hover(S["shaft_hover"])


def d_click_top():
    hov = hover()
    h.check(
        "the hover is on the shaft",
        hov is not None and hov.pick is not None and hov.pick.part is S["shaft"],
        hov and hov.pick,
    )
    vx.lit(hov, "the shaft's end", "centre", S["shaft_top"])
    h.click(S["shaft_hover"])


d_click_top.wait_ms = 400


def d_hover_socket():
    c = socket_top()
    vx.look_at(c, 30.0)
    # on the boss's top 3 mm from the socket's axis (its corners are 2.33 mm out): on the
    # metal, nearer to the middle of the socket's side than to its centre, inside the
    # socket's reach (1.6 x its corner radius)
    S["boss_point"] = V(c.x + 3.0, c.y, c.z)
    vx.hover(S["boss_point"])


def d_click_socket():
    hov = hover()
    h.check(
        "the hover is on the motor's case",
        hov is not None and hov.pick is not None and hov.pick.part.Label == "Case",
        hov and hov.pick,
    )
    hot = hov.hot if hov is not None else None
    h.check(
        "the socket's centre is lit (on the socket's axis, on the boss's top)",
        hot is not None and (hot["point"] - socket_top()).Length < 1e-4,
        hot and (hot["kind"], hot["point"], socket_top()),
    )
    h.click(S["boss_point"])


d_click_socket.wait_ms = 1500


def d_offset():
    box = gbox(S["shaft"])
    c = socket_top()
    h.check(
        "joined: the shaft's end on the socket's mouth, its axis on the socket's",
        vx.near_xy(axis_xy(box), c, 1e-4) and abs(box.ZMin - c.z) < 1e-3,
        (box, c),
    )
    p = vx.joint_panel()
    if h.check("the Joint dialog stays open", p is not None, p):
        s.type_value(p.offset_fields["z"].widget, "-0.2 in")


d_offset.wait_ms = 1500


def d_revolute():
    shaft_in_socket("Offset Z -0.2 in")
    p = vx.joint_panel()
    j.click_tab(p, "Motion")
    j.choose_type(p, "Revolute")


d_revolute.wait_ms = 2600


def d_ok():
    vx.ok()


d_ok.wait_ms = 1200


def d_made():
    h.check("OK closed the dialog", vx.joint_panel() is None)
    found = [o for o in vx.joints_list() if o.Label.startswith("Revolute")]
    h.check("a revolute joint made", len(found) == 1, [o.Label for o in vx.joints_list()])
    S["revolute"] = found[0] if found else None
    shaft_in_socket("after OK")
    motor_still()


# -- E: drive it -----------------------------------------------------------------------------------
def e_drive():
    h.click_empty()
    if S.get("revolute") is not None:
        j.browser_menu(S["revolute"].Label, "Drive Joints")


e_drive.wait_ms = 1500


def e_type():
    p = j.panel()
    h.check(
        "Drive Joints on the revolute",
        p is not None and getattr(p, "joint", None) is S.get("revolute"),
        p and getattr(p, "joint", None),
    )
    if p is not None:
        s.type_value(p.angle.widget, "30")


e_type.wait_ms = 2500


def e_turned():
    shaft_in_socket("driven 30 degrees", 30.0)
    motor_still()
    j.ok()


e_turned.wait_ms = 1200


def e_undo():
    j.no_dialog("Drive OK")
    s.undo()


e_undo.wait_ms = 1500


def e_undone():
    shaft_in_socket("Undo")
    motor_still()


# -- F: save, reopen -------------------------------------------------------------------------------
def f_save():
    S["path"] = vx.save_as("vex_qa_real")
    S["copy_label"] = S["copy"].Label if S.get("copy") is not None else None
    App.closeDocument(App.ActiveDocument.Name)


f_save.wait_ms = 1000


def f_open():
    App.openDocument(S["path"])
    Gui.activateWorkbench("SciForgeWorkbench")


f_open.wait_ms = 2500


def f_reopened():
    from sciforge import components

    doc = App.ActiveDocument
    by = {c.Label: c for c in components.list_components(doc)}
    S["screw"], S["shaft"], S["motor"] = (
        by.get("real_screw"),
        by.get("real_shaft"),
        by.get("real_motor"),
    )
    if not h.check(
        "the parts are back", None not in (S["screw"], S["shaft"], S["motor"]), sorted(by)
    ):
        return
    in_hole("reopened", S["screw"], vx.hole_centre(*HOLE))
    copy = by.get(S.get("copy_label"))
    if h.check("the copy is back", copy is not None, sorted(by)):
        h.check(
            "reopened: the copy in its split hole",
            vx.near_xy(axis_xy(vx.bbox(copy)), split_centre(*SPLIT_HOLE), 1e-4),
            vx.bbox(copy),
        )
    shaft_in_socket("reopened")
    doc.recompute()


f_reopened.wait_ms = 2000


def f_recomputed():
    if S.get("screw") is None:
        return
    in_hole("a recompute after reopening", S["screw"], vx.hole_centre(*HOLE))
    shaft_in_socket("a recompute after reopening")
    try:
        os.remove(S["path"])
    except OSError:
        pass


h.run(
    "vex_qa_real",
    [
        setup,
        a_press_j,
        a_hover_round,
        a_round_lit,
        a_round_inside,
        a_split_lit,
        a_split_edge,
        b_press_j,
        b_hover_underside,
        b_click_underside,
        b_hover_hole,
        b_click_hole,
        b_ok,
        b_made,
        c_pick,
        c_open,
        c_hover,
        c_click,
        c_copy,
        d_press_j,
        d_hover_top,
        d_click_top,
        d_hover_socket,
        d_click_socket,
        d_offset,
        d_revolute,
        d_ok,
        d_made,
        e_drive,
        e_type,
        e_turned,
        e_undo,
        e_undone,
        f_save,
        f_open,
        f_reopened,
        f_recomputed,
    ],
)

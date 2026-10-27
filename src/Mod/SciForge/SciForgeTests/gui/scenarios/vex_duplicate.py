# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX: Duplicate With Joints (ASSEMBLE), only real input in the dialog
(docs/sciforge/parity/vex-assembly.md). SciForge's own VEX-like parts: a 1x2x1x5 aluminium
C-channel, a #8-32 screw jointed (rigid) into its web hole (1, 1), a Keps nut jointed to the
screw (an enclosed joint).

  A  The screw and the nut picked, ASSEMBLE > Duplicate With Joints: the open joint (screw to
     channel) is taken by itself; six clicks next to six square holes: six screws and six
     nuts, occurrences of the originals ("screw_8_32_x_0_5:2" ...), each screw in its hole
     (axis on the hole's centre, head on the web), each nut on its screw; 12 new joints. OK.
  B  One Ctrl+Z takes all the copies and their joints away; Ctrl+Y brings them back.
  C  Cancel: the dialog again, one copy, Esc: the copy goes, nothing else changes.
  D  Refusal: a component with no joint picked: the dialog says it has no joint to copy.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import vex_steps as vx

V = App.Vector
S = {}
HOLES = [(0, 1), (2, 1), (3, 1), (4, 1), (0, 0), (2, 0)]
HEAD = 0.08 * vx.IN


def comps():
    from sciforge import components

    return components.list_components(App.ActiveDocument)


def by_label(label):
    for c in comps():
        if c.Label == label:
            return c
    return None


def copies_of(source):
    from sciforge import instances

    return instances.instances_of(source)


def panel():
    from sciforge import duplicate_joints_ui

    p = duplicate_joints_ui.DuplicatePanel.last
    return None if p is None or p._closed else p


def web_point(i, j):
    c = vx.hole_centre(i, j)
    return V(c.x + 3.6, c.y, vx.T)


def make_joint(part1, element1, kind1, part2, element2, kind2, near=None):
    """A rigid joint between two parts by their snaps (set-up only: the J dialog is tested in
    vex_joint_hole)."""
    from sciforge import joints

    b1, b2 = vx.body_of(part1), vx.body_of(part2)
    p1 = joints.Pick(part1, b1, element1)
    p2 = joints.Pick(part2, b2, element2, near)
    s1 = [c for c in joints.snap_candidates(p1) if c["kind"] == kind1][0]
    found = [c for c in joints.snap_candidates(p2) if c["kind"] == kind2]
    s2 = joints.nearest_snap(found, near)
    joint = joints.create_joint(App.ActiveDocument, "rigid", p1, s1, p2, s2)
    joints.align(joint, first=True)
    return joint


def face_named(part, test):
    body = vx.body_of(part)
    for i, f in enumerate(body.Shape.Faces):
        if test(f):
            return "Face%d" % (i + 1)
    return None


# -- setup ----------------------------------------------------------------------------------------
def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("VexDuplicate")
    S["channel"] = vx.insert("c_channel_1x2x1x5")
    S["screw"] = vx.insert("screw_8_32_x_0_5", App.Placement(V(-20, 19.05, 20), App.Rotation()))
    S["nut"] = vx.insert("keps_nut", App.Placement(V(-40, 19.05, 0), App.Rotation()))
    doc.openTransaction("Set-up joints")
    # the screw's head underside (an annulus on Z = 0) onto the web's top at hole (1, 1)
    under = face_named(
        S["screw"],
        lambda f: f.Surface.TypeId == "Part::GeomPlane"
        and abs(f.BoundBox.ZMax) < 1e-9
        and len(f.Wires) == 2,
    )
    web = face_named(
        S["channel"],
        lambda f: f.Surface.TypeId == "Part::GeomPlane"
        and abs(f.BoundBox.ZMin - vx.T) < 1e-9
        and f.BoundBox.ZLength < 1e-9
        and f.BoundBox.YLength > 20,
    )
    S["j1"] = make_joint(
        S["screw"], under, "centre", S["channel"], web, "loop", vx.hole_centre(1, 1)
    )
    # the nut's washer (its face on Z = 0) onto the screw's shank end (an enclosed joint)
    washer = face_named(
        S["nut"],
        lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax) < 1e-9,
    )
    tip = face_named(
        S["screw"],
        lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMin + 12.7) < 1e-9,
    )
    S["j2"] = make_joint(S["nut"], washer, "centre", S["screw"], tip, "centre")
    doc.commitTransaction()
    doc.recompute()
    h.view().viewTop()
    h.view().fitAll()
    box = vx.bbox(S["screw"])
    c = vx.hole_centre(1, 1)
    h.check(
        "the screw is in hole (1, 1)",
        vx.near_xy(V((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2, 0), c, 1e-3),
        box,
    )
    nut = vx.bbox(S["nut"])
    h.check(
        "the nut is on the screw's end",
        abs(nut.ZMax - (vx.T - 12.7)) < 0.2 or abs(nut.ZMin - (vx.T - 12.7)) < 0.2,
        nut,
    )


setup.wait_ms = 1500


# -- A ---------------------------------------------------------------------------------------------
def a_pick():
    from SciForgeTests.gui import bodies_steps as bs

    Gui.Selection.clearSelection()
    bs.click_browser_row(S["screw"].Label)
    bs.click_browser_row(S["nut"].Label, QtCore.Qt.ControlModifier)


def a_open():
    vx.menu("ASSEMBLE", "Duplicate With Joints")


a_open.wait_ms = 1200


def a_ready():
    p = panel()
    if not h.check("Duplicate With Joints open", p is not None):
        return
    h.check(
        "Components: the screw and the nut",
        sorted(m.Label for m in p.members) == sorted([S["screw"].Label, S["nut"].Label]),
        [m.Label for m in p.members],
    )
    joint, side = p.chosen()
    h.check(
        "the open joint taken by itself (screw to channel)", joint is S["j1"], joint and joint.Label
    )
    h.check("the position box waits", p.active == "position", p.active)


def make_hole_steps():
    steps = []
    for n, (i, j) in enumerate(HOLES):

        def hover(i=i, j=j):
            vx.look_at(vx.hole_centre(i, j), 40.0)
            vx.hover(web_point(i, j))

        def click(i=i, j=j, n=n):
            p = panel()
            hov = getattr(p, "hover", None)
            vx.lit(
                hov, "copy %d: next to hole (%d, %d)" % (n + 1, i, j), "loop", vx.hole_centre(i, j)
            )
            h.click(web_point(i, j))

        click.wait_ms = 1500
        hover.__name__ = "a_hover_%d_%d" % (i, j)
        click.__name__ = "a_click_%d_%d" % (i, j)
        steps += [hover, click]
    return steps


def a_copies():
    p = panel()
    screws = copies_of(S["screw"])
    nuts = copies_of(S["nut"])
    h.check(
        "six screws made (occurrences of the first)", len(screws) == 6, [c.Label for c in screws]
    )
    h.check("six nuts made", len(nuts) == 6, [c.Label for c in nuts])
    from sciforge import joints

    h.check(
        "twelve new joints",
        len(joints.joints(App.ActiveDocument)) == 14,
        len(joints.joints(App.ActiveDocument)),
    )
    for screw in screws:
        box = vx.bbox(screw)
        mid = V((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2, 0)
        ok = any(vx.near_xy(mid, vx.hole_centre(i, j), 1e-3) for i, j in HOLES)
        ok = ok and abs(box.ZMax - (vx.T + HEAD)) < 1e-3
        h.check("%s stands in its hole, head on the web" % screw.Label, ok, box)
    for nut in nuts:
        box = vx.bbox(nut)
        h.check("%s is under the web, on its screw" % nut.Label, box.ZMax < vx.T - 5.0, box)
    if p is not None:
        h.check("the dialog counts six copies", "6 copies" in p.count.text(), p.count.text())
    h.shot("A-six")
    vx.ok()


a_copies.wait_ms = 800


def a_ok():
    h.check("OK closed the dialog", panel() is None)
    h.check("the copies stay", len(copies_of(S["screw"])) == 6)
    # a drawing's parts list counts the occurrences as the same part (Fusion: Qty)
    from sciforge import drawing, drawing_core

    doc = App.ActiveDocument
    found = [b for b in doc.Objects if b.TypeId == "PartDesign::Body"]
    rows = drawing_core.parts_rows(drawing.components_of(found))
    qty = {r["PartNumber"]: r["Qty"] for r in rows}
    h.check(
        "the parts list: 7 screws and 7 nuts, one row each",
        qty.get(S["screw"].Label) == 7 and qty.get(S["nut"].Label) == 7 and len(rows) == 3,
        qty,
    )


# -- B ---------------------------------------------------------------------------------------------
def b_undo():
    h.click_empty()
    vx.undo()


b_undo.wait_ms = 1500


def b_undone():
    from sciforge import joints

    h.check(
        "one Ctrl+Z: no copies",
        not copies_of(S["screw"]) and not copies_of(S["nut"]),
        [c.Label for c in comps()],
    )
    h.check("one Ctrl+Z: the copies' joints gone", len(joints.joints(App.ActiveDocument)) == 2)
    vx.redo()


b_undone.wait_ms = 1500


def b_redone():
    from sciforge import joints

    h.check(
        "Ctrl+Y: the copies back", len(copies_of(S["screw"])) == 6 and len(copies_of(S["nut"])) == 6
    )
    h.check("Ctrl+Y: their joints back", len(joints.joints(App.ActiveDocument)) == 14)


# -- C ---------------------------------------------------------------------------------------------
def c_open():
    from SciForgeTests.gui import bodies_steps as bs

    S["count"] = len(comps())
    Gui.Selection.clearSelection()
    bs.click_browser_row(S["screw"].Label)
    vx.menu("ASSEMBLE", "Duplicate With Joints")


c_open.wait_ms = 1200


def c_position_box():
    from SciForgeTests.gui import widget_input as wi

    p = panel()
    if not h.check("the dialog again", p is not None):
        return
    # the screw alone has two joints out of it (to the channel, and the nut's): the Joint list
    # shows both, the first (to the channel) taken; the Position box is clicked to go on
    h.check("two joints to choose from", p.joint_box.count() == 2, p.joint_box.count())
    h.check("the components box still waits", p.active == "components", p.active)
    wi.click(p.fields["position"].button)


def c_hover():
    p = panel()
    h.check(
        "only the screw this time",
        p is not None and [m.Label for m in p.members] == [S["screw"].Label],
        p and p.members,
    )
    vx.look_at(vx.hole_centre(4, 0), 40.0)
    vx.hover(web_point(4, 0))


def c_click():
    h.click(web_point(4, 0))


c_click.wait_ms = 1500


def c_one():
    h.check("one more screw", len(comps()) == S["count"] + 1, len(comps()))
    h.press(QtCore.Qt.Key_Escape)


def c_cancelled():
    h.check("Esc: no dialog", panel() is None)
    h.check("Esc: the copy went", len(comps()) == S["count"], len(comps()))


# -- D ---------------------------------------------------------------------------------------------
def d_open():
    S["lone"] = vx.insert("standoff_1in", App.Placement(V(-60, 0, 0), App.Rotation()))
    h.click_empty()
    vx.menu("ASSEMBLE", "Duplicate With Joints")


d_open.wait_ms = 1200


def d_pick_lone():
    # the standoff's top (its hex end, z = 1 in), clicked in the view
    top = V(-60 + 2.8, 0, vx.IN)
    vx.look_at(top, 30.0)
    vx.hover(top)
    h.click(top)


def d_refused():
    p = panel()
    text = (p.info.text() + " " + p.message.text()) if p is not None else ""
    h.check("a component with no joint: said so", "no joint" in text, text)
    h.press(QtCore.Qt.Key_Escape)


h.run(
    "vex_duplicate",
    [setup, a_pick, a_open, a_ready]
    + make_hole_steps()
    + [a_copies, a_ok, b_undo, b_undone, b_redone, c_open, c_position_box, c_hover]
    + [c_click, c_one, c_cancelled]
    + [d_open, d_pick_lone, d_refused],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Deleting a joint leaves both bodies as they are (Luca, 2026-10-26, for 0.1.0-beta.2.2: "When
deleting a joint, it also deletes the body. its still in the browser, but there is no body ...
or the joint gets deleted, the body stays, but cant be edited (tested with fillet)"). Two bodies
on their own (no components), a Revolute joint, deleted from the browser row. Only real input
(docs/sciforge/parity/joints.md, "Delete, Suppress, Undo, save": Fusion leaves the components
where they are).

Plate = 0..40 x 0..30 x 10, Block = 50..70 x 0..10 x 20 (joints_steps).

  A  The block's top front edge filleted (r 2). J: the block's top onto the plate's top,
     Revolute, OK; the joint edited to Angle 90 (the block turns).
  B  Right-click the joint's row in the browser > Delete: the joint is gone; both bodies are
     there with their solids (same volumes), where they were (the block stays turned on the
     plate), each body's Tip is its last step, nothing in error.
  C  The fillet still edits: double-click it in the timeline, r 3, OK: the block's volume
     follows; Ctrl+Z: r 2 again.
  D  Ctrl+Z: the joint is back, the bodies as before the delete; Ctrl+Y: deleted again,
     bodies unchanged.
  E  The same from the timeline: a new design, J, Revolute, OK (Angle 0), the joint's
     timeline button > Delete: the same checks.
  F  A new design, J, Revolute, OK, then a fillet on the jointed block: the joint keeps
     working (it finds its face again after the fillet numbered the faces anew: it went
     red, "?Face6", before) and the block stays where it is. Click the joint's row (only
     it is selected), Delete key: the joint goes, the bodies stay. Ctrl+Z.
  G  Click the row again, Del in the 3D view: the same.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import blend_steps as b
from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import timeline_input as t

V = App.Vector
state = {}
R1, R2 = 2.0, 3.0
BLOCK_VOLUME = 20 * 10 * 20


def fillet_cut(r):
    """What a round of radius r takes off a 20 mm edge."""
    return 20 * r * r * (1 - math.pi / 4)


def doc():
    return App.ActiveDocument


def body_record():
    """{body name: (volume, placement, tip name, shape null?)} of every body."""
    out = {}
    for body in s.bodies():
        shape = body.Shape
        out[body.Name] = (
            None if shape.isNull() else shape.Volume,
            body.Placement,
            body.Tip.Name if body.Tip is not None else None,
            shape.isNull(),
        )
    return out


def broken():
    return [
        o.Label
        for o in doc().Objects
        if "Invalid" in list(getattr(o, "State", [])) or "Error" in list(getattr(o, "State", []))
    ]


def same_bodies(label, before):
    now = body_record()
    h.check(
        "%s: the same bodies" % label,
        sorted(now) == sorted(before),
        (sorted(now), sorted(before)),
    )
    for name, (volume, plc, tip, null) in before.items():
        got = now.get(name)
        if got is None:
            continue
        h.check("%s: %s has its solid" % (label, name), not got[3] and got[0] is not None)
        h.check(
            "%s: %s same volume" % (label, name),
            got[0] is not None and volume is not None and abs(got[0] - volume) < 1e-6,
            (got[0], volume),
        )
        h.check(
            "%s: %s stays where it was" % (label, name),
            got[1].isSame(plc, 1e-7),
            (got[1], plc),
        )
        h.check("%s: %s Tip unchanged" % (label, name), got[2] == tip, (got[2], tip))
    h.check("%s: nothing in error" % label, not broken(), broken())


# -- A ---------------------------------------------------------------------------------------------
def a_fillet():
    Gui.Selection.clearSelection()
    h.click_empty()
    h.fit()
    h.press("f")


def a_fillet_edge():
    h.click_edge(V(60, 0, 20))  # the block's top front edge


def a_fillet_value():
    p = b.blend_panel()
    h.check("A: one edge picked", p is not None and len(p.refs) == 1)
    if p is not None:
        s.type_value(p.radius.widget, str(R1))


def a_fillet_ok():
    h.task_button("OK")


def a_filleted():
    v = j.block().Shape.Volume
    want = BLOCK_VOLUME - fillet_cut(R1)
    h.check("A: the block filleted", abs(v - want) < 1e-4, (v, want))
    state["fillet"] = j.block().Tip.Name


def a_revolute():
    p = j.panel()
    if h.check("A: joint dialog", p is not None):
        j.click_tab(p, "Motion")
        j.choose_type(p, "Revolute")


def a_ok():
    j.ok()


def a_joined():
    h.check("A: one joint", len(j.joint_list()) == 1, j.row_labels())
    j.no_dialog("A: OK")


def a_edit():
    h.fit()
    t.double_click("Revolute 1")


def a_angle():
    p = j.panel()
    if h.check("A: editing the joint", p is not None and p.editing):
        s.type_value(p.angle.widget, "90")


def a_angle_ok():
    j.ok()


def a_turned():
    box = j.block().Shape.BoundBox
    h.check("A: the block turned (its footprint is 10 x 20 now)", abs(box.XLength - 10) < 1e-3, box)
    state["before"] = body_record()
    state["volumes"] = {b.Name: b.Shape.Volume for b in s.bodies()}
    h.shot("A-joined")


# -- B ---------------------------------------------------------------------------------------------
def b_delete():
    t.row_menu("Revolute 1", "Delete")


def b_deleted():
    h.check("B: the joint is gone", not j.joint_list(), j.row_labels())
    same_bodies("B", state["before"])
    s.no_popups("B")
    h.shot("B-deleted")


# -- C ---------------------------------------------------------------------------------------------
def fillet_title():
    from sciforge import timeline_ui

    tl = timeline_ui.widget()
    tl.refresh(force=True)
    return next((x for x in tl.titles() if x.startswith("Fillet")), None)


def c_edit_fillet():
    h.fit()
    name = state.get("fillet")
    obj = doc().getObject(name) if name else None
    title = fillet_title()
    if h.check("C: the fillet is still there", obj is not None and title is not None, title):
        t.double_click(title)


def c_radius():
    p = b.blend_panel()
    if h.check("C: Edit Fillet opens", p is not None):
        s.type_value(p.radius.widget, str(R2))


def c_ok():
    h.task_button("OK")


def c_edited():
    v = j.block().Shape.Volume
    want = BLOCK_VOLUME - fillet_cut(R2)
    h.check("C: the fillet edited (r 3)", abs(v - want) < 1e-4, (v, want))
    h.check("C: nothing in error", not broken(), broken())


def c_undo():
    s.undo()


def c_undone():
    v = j.block().Shape.Volume
    want = BLOCK_VOLUME - fillet_cut(R1)
    h.check("C: Ctrl+Z: r 2 again", abs(v - want) < 1e-4, (v, want))


# -- D ---------------------------------------------------------------------------------------------
def d_undo():
    s.undo()


def d_back():
    h.check("D: Ctrl+Z brings the joint back", len(j.joint_list()) == 1, j.row_labels())
    same_bodies("D, joint back", state["before"])


def d_redo():
    s.redo()


def d_again():
    h.check("D: Ctrl+Y deletes it again", not j.joint_list(), j.row_labels())
    same_bodies("D, deleted again", state["before"])


# -- E ---------------------------------------------------------------------------------------------
def e_ok():
    j.ok()


def e_joined():
    h.check("E: one joint", len(j.joint_list()) == 1, j.row_labels())
    state["before"] = body_record()


def e_delete():
    t.menu("Revolute 1", "Delete")


def e_deleted():
    h.check("E: the joint is gone (timeline)", not j.joint_list(), j.row_labels())
    same_bodies("E", state["before"])
    s.no_popups("E")


def e_revolute():
    a_revolute()


# -- F ---------------------------------------------------------------------------------------------
def f_fillet():
    a_fillet()


def f_fillet_edge():
    # the block stands upside down on the plate after the joint: its old top front edge
    # (y 0, z 20) is now at the bottom; a vertical edge of the block is at the plate's top
    box = j.block().Shape.BoundBox
    h.click_edge(V(box.XMax, box.YMin, (box.ZMin + box.ZMax) / 2))


def f_fillet_ok():
    p = b.blend_panel()
    if h.check("F: fillet dialog", p is not None and len(p.refs) == 1):
        s.type_value(p.radius.widget, str(R1))
    h.task_button("OK")


def f_before_fillet():
    state["block_at"] = App.Placement(j.block().Placement)


def f_record():
    # the joint origin is the centre of the block's face, which the fillet trimmed at one
    # corner: it moves a few hundredths of a millimetre with the face (as Fusion's would)
    now, was = j.block().Placement, state["block_at"]
    turn = math.degrees(now.Rotation.multiply(was.Rotation.inverted()).Angle)
    h.check(
        "F: the block stays where the joint put it after the fillet",
        (now.Base - was.Base).Length < 0.1 and turn < 0.1,
        (now, was),
    )
    state["before"] = body_record()
    state["fillet"] = j.block().Tip.Name
    joint = j.joint_list()[0] if j.joint_list() else None
    h.check(
        "F: the joint still works after the fillet",
        joint is not None and not ({"Invalid", "Error"} & set(joint.State)),
        joint and (list(joint.State), joint.Reference1, joint.Reference2),
    )
    h.shot("F-filleted")


def f_click_row():
    t.click_row("Revolute 1")


def f_selection():
    sel = [(x.ObjectName, list(x.SubElementNames)) for x in Gui.Selection.getSelectionEx("", 0)]
    from sciforge import bodies_gui

    entries = [(o.Name, short) for o, short, _p in bodies_gui.selection_entries()]
    joint = j.joint_list()[0].Name if j.joint_list() else None
    rows = t.selected_rows()
    h.check("F: only the joint is selected", [n for n, _s in entries] == [joint], (sel, entries))
    h.check("F: only the joint's row is selected", rows == ["Revolute 1"], rows)
    state["sel"] = (sel, entries)


def f_delete_key():
    from PySide import QtCore

    from SciForgeTests.gui import widget_input as w

    tree = t.tree()
    tree.setFocus()
    w.key(tree, QtCore.Qt.Key_Delete)


def f_deleted():
    h.check("F: the joint is gone (Delete key)", not j.joint_list(), j.row_labels())
    same_bodies("F", state["before"])


def f_undo():
    s.undo()


def g_click_row():
    t.click_row("Revolute 1")


def g_delete_in_view():
    h.press(__import__("PySide").QtCore.Qt.Key_Delete)


def g_deleted():
    h.check("G: the joint is gone (Del in the 3D view)", not j.joint_list(), j.row_labels())
    same_bodies("G", state["before"])


h.run(
    "joints_delete",
    [s.new_design("JointsDelete")]
    + j.two_boxes()
    + [a_fillet, a_fillet_edge, a_fillet_value, a_fillet_ok, a_filleted]
    + j.pick_pair("a")
    + [a_revolute, a_ok, a_joined, a_edit, a_angle, a_angle_ok, a_turned]
    + [b_delete, b_deleted]
    + [c_edit_fillet, c_radius, c_ok, c_edited, c_undo, c_undone]
    + [d_undo, d_back, d_redo, d_again]
    + [s.new_design("JointsDelete2")]
    + j.two_boxes("e")
    + j.pick_pair("e")
    + [e_revolute, e_ok, e_joined, e_delete, e_deleted]
    + [s.new_design("JointsDelete3")]
    + j.two_boxes("f")
    + j.pick_pair("f")
    + [e_revolute, e_ok, e_joined, f_before_fillet, f_fillet, f_fillet_edge, f_fillet_ok]
    + [h.idle_step("f_settle"), f_record]
    + [f_click_row, f_selection, f_delete_key, f_deleted, f_undo, g_click_row, f_selection]
    + [g_delete_in_view, g_deleted],
    paced_by="state",
)

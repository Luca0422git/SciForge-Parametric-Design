# SPDX-License-Identifier: LGPL-2.1-or-later
"""More options of the SETUP dialogs with real clicks (builder sim-ui). The bracket's study is
made by script.

A  Structural Constraints > Frictionless on a side face of the bracket: rollers previewed; OK:
   "Frictionless 1", its glyphs drawn.
B  Structural Loads > Force on two faces (the arm's top and the plate's top) with Force Per
   Entity ticked (it is no longer greyed with two picks), 50 N; OK: each face gets the whole
   50 N.
C  Structural Loads > Moment, Direction Type Vector, the axis (0, 1, 0) typed; OK: a moment
   about Y.
D  Gravity on, Edit Gravity: Vector (1, 0, 0) typed, OK: gravity along +X.
E  MANAGE > Local Mesh Control on the arm's top face, 2 mm; OK. A double-click on its row in
   the browser opens it again (its face picked, 2 mm): 1.5 mm typed, OK: 1.5 mm kept; Undo:
   2 mm again.
"""

import FreeCAD as App
from PySide import QtCore

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    s.new_bracket("SimMore")()
    s.sim().create_study(App.ActiveDocument)
    App.ActiveDocument.recompute()


def enter():
    s.workspace("Simulation")


def data(item):
    return s.sim().item_data(item)


def of_kind(kind):
    return [i for i in s.sim().items(s.active_study()) if data(i)["kind"] == kind]


# -- A ------------------------------------------------------------------------------------------
def a_open():
    h.fit()
    h.ribbon("Structural Constraints")


def a_choose():
    s.choose("SciForgeSimItemType", "Frictionless")


def a_pick():
    p = s.item_panel()
    if not h.check("Frictionless chosen", p is not None and p.kind == "frictionless"):
        return
    body = s.body()
    face = s.visible_face(body, [f for f in s.side_faces(body) if f != s.plate_top(body)])
    state["side"] = face
    if h.check("a side face can be clicked", face is not None):
        s.click_face(body, face)


def a_ok():
    h.check("rollers previewed", s.preview_count() > 0, s.preview_count())
    s.ok()


def a_check():
    found = of_kind("frictionless")
    h.check("Frictionless 1 made", [i.Label for i in found] == ["Frictionless 1"])
    if found:
        h.check("its glyphs drawn", s.glyph_counts().get(found[0].Name, 0) >= 1)
        refs = [sub for _o, sub in s.sim()._picks(found[0].References)]
        h.check("on the side face", refs == [state.get("side")], refs)


# -- B ------------------------------------------------------------------------------------------
def b_open():
    h.ribbon("Structural Loads")


def b_pick():
    p = s.item_panel()
    if not h.check("Structural Loads opened (Force)", p is not None and p.kind == "force"):
        return
    body = s.body()
    s.click_face(body, s.arm_top(body))
    s.click_face(body, s.plate_top(body))


def b_values():
    p = s.item_panel()
    if p is None:
        return
    h.check("two faces picked", len(p.picks) == 2, p.picks)
    per = s.panel_field("SciForgeSim_per_entity")
    h.check("Force Per Entity can be ticked with two picks", per is not None and per.isEnabled())
    if per is not None and not per.isChecked():
        # on its box, as a person clicks it (the row is wider than the box and its words)
        w.click(per, QtCore.QPoint(8, per.height() // 2))
    h.check("Force Per Entity ticked", per is not None and per.isChecked())
    s.type_in("SciForgeSim_magnitude", "50")
    s.ok()


def b_check():
    found = of_kind("force")
    if not h.check("Force 1 made", [i.Label for i in found] == ["Force 1"]):
        return
    opts = data(found[0])["options"]
    h.check("50 N on each face (per entity)", opts["per_entity"] is True, opts)
    h.check("50 N", abs(opts["magnitude"] - 50.0) < 1e-9, opts)
    h.check("on two faces", len(s.sim()._picks(found[0].References)) == 2)


# -- C ------------------------------------------------------------------------------------------
def c_open():
    h.ribbon("Structural Loads")


def c_choose():
    s.choose("SciForgeSimItemType", "Moment")


def c_vector():
    p = s.item_panel()
    if not h.check("Moment chosen", p is not None and p.kind == "moment"):
        return
    s.click_face(s.body(), s.arm_top(s.body()))
    s.choose("SciForgeSim_direction", "Vector")


def c_values():
    for name, value in (("vx", "0"), ("vy", "1"), ("vz", "0")):
        h.check("axis field %s shown" % name, s.panel_field("SciForgeSim_" + name) is not None)
        s.type_in("SciForgeSim_" + name, value)
    s.ok()


def c_check():
    found = of_kind("moment")
    if not h.check("Moment 1 made", [i.Label for i in found] == ["Moment 1"]):
        return
    opts = data(found[0])["options"]
    h.check("about Y (Vector)", opts["direction"] == "vector", opts)
    v = opts["vector"]
    h.check("the axis (0, 1, 0)", abs(v[0]) < 1e-9 and abs(v[1] - 1) < 1e-9 and abs(v[2]) < 1e-9, v)


# -- D ------------------------------------------------------------------------------------------
def d_gravity():
    s.menu_item("LOADS", "Toggle Gravity On/Off")


def d_edit():
    h.check("gravity on", s.sim().settings(s.active_study())["gravity"]["on"])
    s.right_click_row("Gravity", "Edit Gravity")


def d_values():
    from sciforge import simulation_panels

    p = simulation_panels.GravityPanel.last
    if not h.check("Edit Gravity opened", p is not None and not p._closed):
        return
    for name, value in (("gx", "1"), ("gy", "0"), ("gz", "0")):
        s.type_in("SciForgeSim_" + name, value)
    s.ok()


def d_check():
    d = s.sim().settings(s.active_study())["gravity"]["direction"]
    h.check("gravity along +X", abs(d[0] - 1) < 1e-9 and abs(d[1]) < 1e-9 and abs(d[2]) < 1e-9, d)
    h.check("its arrow drawn", s.glyph_counts().get("gravity") == 1, s.glyph_counts())


# -- E ------------------------------------------------------------------------------------------
def e_local():
    s.menu_item("MANAGE", "Local Mesh Control")


def e_pick():
    p = s.item_panel()
    if not h.check("Local Mesh Control opened", p is not None and p.category == "mesh"):
        return
    s.click_face(s.body(), s.arm_top(s.body()))
    s.type_in("SciForgeSim_size", "2")
    s.ok()


def e_edit():
    found = s.items("mesh")
    if not h.check(
        "Local Mesh Control 1 made", [i.Label for i in found] == ["Local Mesh Control 1"]
    ):
        return
    h.check("2 mm", abs(data(found[0])["options"]["size"] - 2.0) < 1e-9)
    s.double_click_row("Local Mesh Control 1")


def e_change():
    p = s.item_panel()
    if not h.check("its dialog opened from the browser", p is not None and p.editing):
        return
    h.check("its face picked", len(p.picks) == 1, p.picks)
    field = s.panel_field("SciForgeSim_size")
    h.check("2 mm shown", field is not None and field.text() == "2 mm", field.text())
    s.type_in("SciForgeSim_size", "1.5")
    s.ok()


def e_check():
    found = s.items("mesh")
    h.check("1.5 mm kept", found and abs(data(found[0])["options"]["size"] - 1.5) < 1e-9)
    s.undo()


def e_undone():
    found = s.items("mesh")
    h.check("Undo: 2 mm again", found and abs(data(found[0])["options"]["size"] - 2.0) < 1e-9)


h.run(
    "sim_setup_more",
    [
        setup,
        enter,
        a_open,
        a_choose,
        a_pick,
        a_ok,
        a_check,
        b_open,
        b_pick,
        b_values,
        b_check,
        c_open,
        c_choose,
        c_vector,
        c_values,
        c_check,
        d_gravity,
        d_edit,
        d_values,
        d_check,
        e_local,
        e_pick,
        e_edit,
        e_change,
        e_check,
        e_undone,
    ],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every constraint and load type of the SETUP dialogs, Local Mesh Control, Generate Mesh and a
cancelled solve, with real clicks (builder sim-ui). The bracket's study is made by script.

A  Structural Constraints lists Fixed, Pin, Frictionless and Prescribed Displacement (Remote
   greyed, not in SciForge yet). Pin: only
   round faces can be picked (a click on the flat plate picks nothing, a hole wall is picked);
   Fusion's default holds Radial and Axial and leaves Tangential free; OK keeps "Pin 1".
B  Structural Loads lists Force, Pressure, Moment, Bearing Load and Remote Force (Remote Moment
   and Hydrostatic Pressure greyed). Moment,
   Normal, on the arm's top face, "2 N m" typed (a unit override: 2000 N mm); OK; its curved
   arrow is drawn.
C  Force with Direction Type Vector: Fx 0, Fy 100, Fz 0 typed: a force of 100 N along +Y; Force
   Per Entity is greyed with one pick.
D  Pressure on the arm's top face, 0.5 MPa, Flip Direction: it pulls; OK.
E  Prescribed Displacement: Ux ticked, 0.2 mm typed, on the arm's top face; OK.
E2 Bearing Load on the second hole's wall (a click on the flat plate is not taken: round faces
   only): its direction turns across the hole (the default -Z runs along the hole's axis),
   200 N typed; OK. Remote Force on the arm's top face acting from the point (120, 15,
   60); OK. Their glyphs are drawn.
F  MANAGE > Local Mesh Control: Body Selection, a click on the bracket picks the whole body,
   Length 3 mm typed; OK; "Local Mesh Control 1" under the Mesh row, green dots drawn.
G  SOLVE > Generate Mesh: the progress shows the two mesh stages; the mesh is shown on the
   model; the Mesh row gives its node and element counts; DISPLAY > Show Mesh hides it and
   shows it again; Workspace > Design: the mesh is not drawn over the design; back to
   Simulation.
H  Solve, then Cancel in the progress window: the solve stops (cancelled), the study keeps no
   results, nothing is left running.
"""

import FreeCAD as App
from PySide import QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


def setup():
    s.new_bracket("SimKinds")()
    s.sim().create_study(App.ActiveDocument)
    App.ActiveDocument.recompute()


def enter():
    s.workspace("Simulation")


def types(panel):
    from PySide import QtCore

    box = panel.type_box
    model = box.model()
    return [
        (box.itemText(i), bool(model.item(i).flags() & QtCore.Qt.ItemIsEnabled))
        for i in range(box.count())
    ]


# -- A ------------------------------------------------------------------------------------------
def a_constraints():
    h.ribbon("Structural Constraints")


def a_pin():
    p = s.item_panel()
    if not h.check("Structural Constraints opened", p is not None):
        return
    listed = types(p)
    h.check(
        "the four constraint types built, Remote listed greyed",
        listed
        == [
            ("Fixed", True),
            ("Pin", True),
            ("Frictionless", True),
            ("Prescribed Displacement", True),
            ("Remote", False),
        ],
        listed,
    )
    s.choose("SciForgeSimItemType", "Pin")


def a_pick():
    p = s.item_panel()
    if p is None:
        return
    h.check("Pin chosen", p.kind == "pin", p.kind)
    for key, on in (("radial", True), ("axial", True), ("tangential", False)):
        button = s.panel_field("SciForgeSim_" + key, QtWidgets.QPushButton)
        h.check(
            "%s %s by default" % (key, "on" if on else "off"),
            button is not None and button.isChecked() == on,
        )
    bracket = s.body()
    point = s.aim(bracket, s.plate_top(bracket))
    if point is not None:
        h.click(point)
    state["after_flat"] = list(p.picks)
    s.click_face(bracket, s.hole_faces(bracket)[0])


def a_ok():
    p = s.item_panel()
    if p is None:
        return
    h.check("a flat face is not picked by Pin", state.get("after_flat") == [], state)
    h.check("the hole wall is picked", len(p.picks) == 1, p.picks)
    s.ok()


def a_check():
    found = [i.Label for i in s.items("constraint")]
    h.check("Pin 1 made", found == ["Pin 1"], found)


# -- B ------------------------------------------------------------------------------------------
def b_loads():
    h.ribbon("Structural Loads")


def b_moment():
    p = s.item_panel()
    if not h.check("Structural Loads opened", p is not None):
        return
    listed = types(p)
    h.check(
        "the five load types built, Remote Moment and Hydrostatic Pressure greyed",
        listed
        == [
            ("Force", True),
            ("Pressure", True),
            ("Moment", True),
            ("Bearing Load", True),
            ("Remote Force", True),
            ("Remote Moment", False),
            ("Hydrostatic Pressure", False),
        ],
        listed,
    )
    s.choose("SciForgeSimItemType", "Moment")


def b_pick():
    p = s.item_panel()
    if p is None or p.kind != "moment":
        h.check("Moment chosen", False, p.kind if p else None)
        return
    s.click_face(s.body(), s.arm_top(s.body()))
    s.type_in("SciForgeSim_magnitude", "2 N m")


def b_ok():
    h.check("its curved arrow previewed", s.preview_count() > 0, s.preview_count())
    s.ok()


def b_check():
    found = [i for i in s.items("load") if s.sim().item_data(i)["kind"] == "moment"]
    h.check("Moment 1 made", [i.Label for i in found] == ["Moment 1"], [i.Label for i in found])
    if found:
        opts = s.sim().item_data(found[0])["options"]
        h.check("2 N m = 2000 N mm", abs(opts["magnitude"] - 2000.0) < 1e-6, opts)
        h.check("its glyph is drawn", s.glyph_counts().get(found[0].Name, 0) >= 1)


# -- C ------------------------------------------------------------------------------------------
def c_force():
    h.ribbon("Structural Loads")


def c_vector():
    s.choose("SciForgeSim_direction", "Vector")


def c_values():
    for name in ("SciForgeSim_fx", "SciForgeSim_fy", "SciForgeSim_fz"):
        h.check("field %s shown for Vector" % name, s.panel_field(name) is not None)
    s.click_face(s.body(), s.arm_top(s.body()))
    s.type_in("SciForgeSim_fx", "0")
    s.type_in("SciForgeSim_fy", "100")
    s.type_in("SciForgeSim_fz", "0")
    per = s.panel_field("SciForgeSim_per_entity")
    h.check("Force Per Entity greyed with one pick", per is not None and not per.isEnabled())
    s.ok()


def c_check():
    found = [i for i in s.items("load") if s.sim().item_data(i)["kind"] == "force"]
    if not h.check("a force made", len(found) == 1, [i.Label for i in found]):
        return
    opts = s.sim().item_data(found[0])["options"]
    h.check("100 N", abs(opts["magnitude"] - 100.0) < 1e-6, opts)
    h.check("along +Y", abs(opts["vector"][1] - 1.0) < 1e-6, opts)
    h.check("direction type vector", opts["direction"] == "vector", opts)


# -- D ------------------------------------------------------------------------------------------
def d_pressure():
    h.ribbon("Structural Loads")


def d_choose():
    s.choose("SciForgeSimItemType", "Pressure")


def d_values():
    s.click_face(s.body(), s.arm_top(s.body()))
    s.type_in("SciForgeSim_magnitude", "0.5 MPa")
    s.click_widget(s.panel_field("SciForgeSim_flip"))
    s.ok()


def d_check():
    found = [i for i in s.items("load") if s.sim().item_data(i)["kind"] == "pressure"]
    if not h.check("a pressure made", len(found) == 1):
        return
    opts = s.sim().item_data(found[0])["options"]
    h.check("0.5 MPa", abs(opts["magnitude"] - 0.5) < 1e-9, opts)
    h.check("flipped (pulls)", opts["flip"] is True, opts)


# -- E ------------------------------------------------------------------------------------------
def e_displacement():
    h.ribbon("Structural Constraints")


def e_choose():
    s.choose("SciForgeSimItemType", "Prescribed Displacement")


def e_values():
    from SciForgeTests.gui import widget_input as w

    s.click_face(s.body(), s.arm_top(s.body()))
    tick = s.panel_field("SciForgeSim_x_on")
    if h.check("Ux tick", tick is not None):
        if not tick.isChecked():
            w.click(tick)
    s.type_in("SciForgeSim_x", "0.2")
    s.ok()


def e_check():
    found = [i for i in s.items("constraint") if s.sim().item_data(i)["kind"] == "displacement"]
    if not h.check("a prescribed displacement made", len(found) == 1):
        return
    opts = s.sim().item_data(found[0])["options"]
    h.check("Ux 0.2 mm", abs(opts["x"] - 0.2) < 1e-9, opts)


# -- E2 -----------------------------------------------------------------------------------------
def e2_bearing():
    h.ribbon("Structural Loads")


def e2_choose():
    s.choose("SciForgeSimItemType", "Bearing Load")


def e2_pick():
    p = s.item_panel()
    if not h.check("Bearing Load chosen", p is not None and p.kind == "bearing"):
        return
    bracket = s.body()
    point = s.aim(bracket, s.plate_top(bracket))
    if point is not None:
        h.click(point)
    QtTest.QTest.qWait(120)  # (a pick is handled a moment after the click)
    state["bearing_after_flat"] = list(p.picks)
    s.click_face(bracket, s.hole_faces(bracket)[1])
    s.type_in("SciForgeSim_magnitude", "200")


def e2_ok():
    p = s.item_panel()
    if p is not None:
        h.check(
            "the flat plate is not taken (round faces only)",
            state.get("bearing_after_flat") == [],
            state.get("bearing_after_flat"),
        )
        h.check("the hole's wall picked", len(p.picks) == 1, p.picks)
        direction = [s.panel_field("SciForgeSim_v" + a).text() for a in "xyz"]
        h.check(
            "its direction turned across the hole (the hole runs along Z)",
            direction[2] in ("0", "-0") and direction != ["0", "0", "0"],
            direction,
        )
        h.check("its arrows previewed", s.preview_count() > 0, s.preview_count())
    s.ok()


def e2_check():
    found = [i for i in s.items("load") if s.sim().item_data(i)["kind"] == "bearing"]
    h.check("Bearing Load 1 made", [i.Label for i in found] == ["Bearing Load 1"])
    if found:
        opts = s.sim().item_data(found[0])["options"]
        h.check("200 N", abs(opts["magnitude"] - 200.0) < 1e-9, opts)
        h.check("its glyphs are drawn", s.glyph_counts().get(found[0].Name, 0) >= 1)
    h.ribbon("Structural Loads")


def e2_remote():
    s.choose("SciForgeSimItemType", "Remote Force")


def e2_remote_pick():
    p = s.item_panel()
    if not h.check("Remote Force chosen", p is not None and p.kind == "remote_force"):
        return
    s.click_face(s.body(), s.arm_top(s.body()))
    for name, value in (("px", "120"), ("py", "15"), ("pz", "60")):
        s.type_in("SciForgeSim_" + name, value)


def e2_remote_ok():
    s.ok()


def e2_remote_check():
    found = [i for i in s.items("load") if s.sim().item_data(i)["kind"] == "remote_force"]
    h.check("Remote Force 1 made", [i.Label for i in found] == ["Remote Force 1"])
    if found:
        opts = s.sim().item_data(found[0])["options"]
        point = [float(c) for c in opts.get("point") or []]
        h.check("from the point (120, 15, 60)", point == [120.0, 15.0, 60.0], opts)
        h.check("its glyphs are drawn", s.glyph_counts().get(found[0].Name, 0) >= 1)


# -- F ------------------------------------------------------------------------------------------
def f_local():
    s.menu_item("MANAGE", "Local Mesh Control")


def f_body():
    p = s.item_panel()
    if not h.check("Local Mesh Control opened", p is not None and p.category == "mesh"):
        return
    s.click_widget(s.panel_field("SciForgeSim_body_selection"))
    s.click_face(s.body(), s.arm_top(s.body()))
    s.type_in("SciForgeSim_size", "3 mm")


def f_ok():
    p = s.item_panel()
    if p is not None:
        h.check("the whole body picked", p.picks == [(s.body(), "")], p.picks)
    s.ok()


def f_check():
    found = s.items("mesh")
    h.check(
        "Local Mesh Control 1 made",
        [i.Label for i in found] == ["Local Mesh Control 1"],
        [i.Label for i in found],
    )
    if found:
        opts = s.sim().item_data(found[0])["options"]
        h.check("3 mm", abs(opts["size"] - 3.0) < 1e-9, opts)
    h.check("listed in the browser", "Local Mesh Control 1" in s.browser_labels())


# -- G ------------------------------------------------------------------------------------------
def g_mesh():
    s.menu_item("SOLVE", "Generate Mesh")


def g_progress():
    status = s.status_dialog()
    h.check("the progress shows", status is not None and status.isVisible())
    if status is not None:
        h.check("two mesh stages", status.stages.count() == 2, status.stages.count())


def g_check():
    from sciforge import simulation_solve_dialog as sd

    study = s.active_study()
    results = sd.last_results()
    h.check("meshed", results.get(study.Name, ("?",))[0] == "done", results)
    h.check("the mesh is shown", sd.mesh_shown())
    mesh = sd.mesh_object(study)
    h.check("its object visible", mesh is not None and mesh.ViewObject.Visibility)
    node = s.row_node("Mesh")
    h.check("the Mesh row gives its size", node is not None and "nodes" in node["tip"], node)
    s.close_popup("SciForgeSimJobStatus")
    s.menu_item("DISPLAY", "Show Mesh")


def g_hidden():
    from sciforge import simulation_solve_dialog as sd

    h.check("Show Mesh hid it", not sd.mesh_shown())
    s.menu_item("DISPLAY", "Show Mesh")


def g_again():
    from sciforge import simulation_solve_dialog as sd

    h.check("Show Mesh shows it again", sd.mesh_shown())
    s.workspace("Design")


def g_design():
    from sciforge import simulation_solve_dialog as sd

    mesh = sd.mesh_object(s.active_study())
    h.check("DESIGN shows", s.tab_visible("solid"))
    h.check(
        "the mesh is not drawn over the design",
        not sd.mesh_shown() and mesh is not None and not mesh.ViewObject.Visibility,
    )
    s.workspace("Simulation")


# -- H ------------------------------------------------------------------------------------------
def h_solve():
    h.ribbon("Solve")


def h_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def h_cancel():
    status = s.status_dialog()
    if h.check("progress window", status is not None):
        s.click_widget(status.cancel_button)


def h_check():
    from sciforge import simulation_solve_dialog as sd

    study = s.active_study()
    h.check("nothing running", not s.solving())
    state_ = sd.last_results().get(study.Name, ("?",))[0]
    h.check("the solve was cancelled", state_ == "cancelled", sd.last_results())
    h.check("no results kept", not s.sim().summary(study), s.sim().summary(study))
    status = s.status_dialog()
    h.check(
        "the progress says so",
        status is not None and "Cancelled" in status.title.text(),
        status.title.text() if status else None,
    )
    s.close_popup("SciForgeSimJobStatus")


h_check.wait_ms = 1500


h.run(
    "sim_setup_kinds",
    [
        setup,
        enter,
        a_constraints,
        a_pin,
        a_pick,
        a_ok,
        a_check,
        b_loads,
        b_moment,
        b_pick,
        b_ok,
        b_check,
        c_force,
        c_vector,
        c_values,
        c_check,
        d_pressure,
        d_choose,
        d_values,
        d_check,
        e_displacement,
        e_choose,
        e_values,
        e_check,
        e2_bearing,
        e2_choose,
        e2_pick,
        e2_ok,
        e2_check,
        e2_remote,
        e2_remote_pick,
        e2_remote_ok,
        e2_remote_check,
        f_local,
        f_body,
        f_ok,
        f_check,
        g_mesh,
        g_progress,
        s.wait_solved("wait_meshed"),
        g_check,
        g_hidden,
        g_again,
        g_design,
        h_solve,
        h_go,
        h_cancel,
        s.wait_solved("wait_cancelled", 30),
        h_check,
    ],
)

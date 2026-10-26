# SPDX-License-Identifier: LGPL-2.1-or-later
"""Mesh settings, adaptive refinement and Remove rigid body modes through the SETUP dialogs
(builder sim-ui), with real clicks. The bracket and its first study (Fixed at the holes, a
Force on the arm) are made by script.

A  SOLVE > Generate Mesh: the Mesh row gives its node count.
B  MANAGE > Settings > Mesh: Absolute value, 3 mm typed; OK: the Mesh row says the mesh is out
   of date; Generate Mesh again: a finer mesh (more nodes).
C  Settings > Adaptive Mesh Refinement: Low; OK. Solve: done after more than one pass (the
   summary keeps every pass); the SETUP tab clicked again.
D  New Simulation Study (Study 2): two equal forces pushing on the bracket's two ends (the view
   turned to reach the far one), nothing holding it: the pre-check is red; Settings > General:
   Remove rigid body modes; OK: the pre-check is no longer red; Solve: done.
"""

import FreeCAD as App
from PySide import QtCore

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


def setup():
    s.new_bracket("SimMeshing")()
    sim = s.sim()
    doc = App.ActiveDocument
    body = s.body()
    study = sim.create_study(doc)
    sim.add_item(study, "constraint", "fixed", [(body, s.hole_faces(body))])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 200.0})
    doc.recompute()


def enter():
    s.workspace("Simulation")


def nodes():
    info = s.sim().mesh_summary(s.active_study()) or {}
    return info.get("nodes") or 0


# -- A ------------------------------------------------------------------------------------------
def a_mesh():
    s.menu_item("SOLVE", "Generate Mesh")


def a_check():
    state["n1"] = nodes()
    tip = (s.row_node("Mesh") or {}).get("tip", "")
    h.check("the Mesh row gives its nodes", state["n1"] > 0 and "nodes" in tip, tip)
    s.close_popup("SciForgeSimJobStatus")
    s.menu_item("MANAGE", "Settings")


# -- B ------------------------------------------------------------------------------------------
def b_absolute():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    if not h.check("Study Settings opened", p is not None and not p._closed):
        return
    p.tabs.setCurrentIndex(1)
    ui.choose(p.tabs.size_kind, "Absolute value (mm)")
    h.check("the absolute size can be typed", p.tabs.size_mm.isEnabled())
    ui.type_into(p.tabs.size_mm, "3")
    s.ok()


def b_check():
    mesh = s.sim().settings(s.active_study())["mesh"]
    h.check("3 mm kept", abs(float(mesh.get("size_mm") or 0) - 3.0) < 1e-9, mesh)
    tip = (s.row_node("Mesh") or {}).get("tip", "")
    h.check("the Mesh row says it is out of date", "out of date" in tip, tip)
    s.menu_item("SOLVE", "Generate Mesh")


def b_finer():
    state["n2"] = nodes()
    h.check("a finer mesh", state["n2"] > state["n1"], (state["n1"], state["n2"]))
    s.close_popup("SciForgeSimJobStatus")
    s.menu_item("MANAGE", "Settings")


# -- C ------------------------------------------------------------------------------------------
def c_adaptive():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    if not h.check("Study Settings opened again", p is not None and not p._closed):
        return
    p.tabs.setCurrentIndex(2)
    ui.choose(p.tabs.adaptive, "Low")
    s.ok()


def c_solve():
    level = s.sim().settings(s.active_study())["adaptive"]["level"]
    h.check("Low refinement kept", level == "low", level)
    h.ribbon("Solve")


def c_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def c_check():
    summary = s.sim().summary(s.studies()[0]) or {}
    h.check("solved", bool(summary))
    passes = (summary.get("adaptive") or {}).get("passes") or []
    h.check("more than one pass kept", len(passes) >= 2, summary.get("adaptive"))
    s.close_popup("SciForgeSimJobStatus")
    s.click_tab("sim_setup")  # (the results took the RESULTS tab)


def c_setup():
    h.check("SETUP in front", s.current_tab() == "sim_setup", s.current_tab())
    h.ribbon("New Simulation Study")


# -- D ------------------------------------------------------------------------------------------
def d_create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


def d_loads():
    from sciforge import bodies

    h.check(
        "Study 2 active",
        s.active_study() is not None and s.active_study().Label.startswith("Study 2"),
    )
    body = s.body()
    shape = bodies.global_shape(body)
    ends = []
    for i, face in enumerate(shape.Faces, 1):
        box = face.BoundBox
        if abs(box.XMin - box.XMax) < 1e-6 and abs(box.XMin) < 1e-6:
            ends.insert(0, "Face%d" % i)  # x = 0
        elif abs(box.XMin - box.XMax) < 1e-6 and abs(box.XMin - 80.0) < 1e-6:
            ends.append("Face%d" % i)  # x = 80
    state["ends"] = ends
    h.check("the bracket's two ends", len(ends) == 2, ends)
    h.ribbon("Structural Loads")


def d_first():
    face = s.visible_face(s.body(), state["ends"])
    other = [f for f in state["ends"] if f != face]
    state["other"] = other[0] if other else None
    if not h.check("an end face can be clicked", face is not None):
        return
    s.click_face(s.body(), face)
    s.type_in("SciForgeSim_magnitude", "100")
    s.ok()


def d_turn():
    # the other end faces away: the view turned to it, as a person orbits
    import FreeCADGui as Gui

    view = Gui.ActiveDocument.ActiveView
    view.viewLeft() if s.visible_face(s.body(), state["ends"][:1]) is None else view.viewRight()
    h.fit(iso=False)
    h.ribbon("Structural Loads")


d_turn.wait_ms = 1500  # (the view turns with an animation)


def d_second():
    other = state.get("other")
    if not h.check("the other end can be clicked now", other is not None):
        return
    s.click_face(s.body(), other)
    s.type_in("SciForgeSim_magnitude", "100")
    s.ok()


def d_red():
    h.check("two forces", len(s.items("load")) == 2, [i.Label for i in s.items("load")])
    h.check("pre-check red: nothing holds it", s.light() == "red", s.light())
    s.menu_item("MANAGE", "Settings")


def d_rigid():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    if not h.check("Study Settings opened (Study 2)", p is not None and not p._closed):
        return
    p.tabs.setCurrentIndex(0)
    if not p.tabs.rigid.isChecked():
        s.click_widget(p.tabs.rigid)
    h.check("Remove rigid body modes ticked", p.tabs.rigid.isChecked())
    s.ok()


def d_solve():
    h.check(
        "kept",
        s.sim().settings(s.active_study()).get("remove_rigid") is True,
        s.sim().settings(s.active_study()),
    )
    h.check("pre-check no longer red", s.light() in ("green", "yellow"), s.light())
    h.ribbon("Solve")


def d_go():
    dialog = s.solve_dialog()
    if not h.check("Solve dialog", dialog is not None):
        return
    for row in range(dialog.table.rowCount()):
        item = dialog.table.item(row, 0)
        h.check(
            "only the active study ticked (%s)" % item.text(),
            (item.checkState() == QtCore.Qt.Checked) == item.text().startswith("Study 2"),
        )
    s.click_widget(dialog.go)


def d_check():
    summary = s.sim().summary(s.active_study()) or {}
    h.check("Study 2 solved without constraints", bool(summary), summary.get("notes"))
    s.close_popup("SciForgeSimJobStatus")


h.run(
    "sim_setup_mesh",
    [
        setup,
        enter,
        a_mesh,
        s.wait_solved("wait_meshed"),
        a_check,
        b_absolute,
        b_check,
        s.wait_solved("wait_meshed_again"),
        b_finer,
        c_adaptive,
        c_solve,
        c_go,
        s.wait_solved("wait_adaptive", 400),
        c_check,
        c_setup,
        d_create,
        d_loads,
        d_first,
        d_turn,
        d_second,
        d_red,
        d_rigid,
        d_solve,
        d_go,
        s.wait_solved("wait_rigid"),
        d_check,
    ],
)

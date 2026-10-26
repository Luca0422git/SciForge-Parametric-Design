# SPDX-License-Identifier: LGPL-2.1-or-later
"""Odd things a person may do in the SIMULATION workspace (builder sim-ui), with real clicks
and keys: nothing may break, nothing may be lost. The bracket's study (Fixed at the holes, a
Force on the arm) is made by script.

A  Structural Loads open, then the study's row selected and Delete: the dialog ends first, the
   study goes (no New Study dialog: deleting is not entering); Undo brings it back.
B  Study Materials open, Workspace > Design: the dialog ends, DESIGN shows; back to Simulation.
C  Generate Mesh, then the study deleted while its mesh shows: gone with it (Show Mesh off);
   Undo: the study back, its mesh not drawn.
D  F2 on the study and an empty name: the name is kept.
E  Solve, and Delete on Force 1 while it solves: refused (told why), the force stays.
F  Structural Loads: it does not start on the face Force 1's row lit up (E clicked it); a face
   picked, Ctrl+Z: the dialog ends and nothing else is undone.
G  DOF View on and off, gravity on, Edit Gravity, Esc: nothing changed.
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    s.new_bracket("SimOdd")()
    sim = s.sim()
    doc = App.ActiveDocument
    study = sim.create_study(doc)
    body = s.body()
    sim.add_item(study, "constraint", "fixed", [(body, s.hole_faces(body))])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 100.0})
    doc.recompute()


def enter():
    s.workspace("Simulation")


def delete_row(label):
    s.click_row(label)
    w.key(s.browser(), QtCore.Qt.Key_Delete)


# -- A ------------------------------------------------------------------------------------------
def a_loads():
    h.ribbon("Structural Loads")


def a_delete():
    h.check("Structural Loads open", s.item_panel() is not None)
    delete_row("Study 1 - Static Stress")


def a_check():
    h.check("the dialog ended first", s.item_panel() is None)
    h.check("the study deleted", not s.studies(), [x.Label for x in s.studies()])
    h.check("no New Study dialog", s.new_study_dialog() is None)
    h.check("no items left", not s.items())
    s.undo()


# -- B ------------------------------------------------------------------------------------------
def b_materials():
    h.check("Undo: the study back", len(s.studies()) == 1)
    h.check("with its items", len(s.items()) == 2, [i.Label for i in s.items()])
    h.ribbon("Study Materials")


def b_leave():
    h.check("Study Materials open", s.task_panel() is not None)
    s.workspace("Design")


def b_back():
    h.check("DESIGN shows", s.tab_visible("solid"))
    h.check("the dialog ended", s.task_panel() is None)
    s.workspace("Simulation")


# -- C ------------------------------------------------------------------------------------------
def c_mesh():
    h.check("SIMULATION again", s.tab_visible("sim_setup"))
    s.menu_item("SOLVE", "Generate Mesh")


def c_delete():
    from sciforge import simulation_solve_dialog

    h.check("the mesh shows", simulation_solve_dialog.mesh_shown())
    s.close_popup("SciForgeSimJobStatus")
    delete_row("Study 1 - Static Stress")


def c_check():
    from sciforge import simulation_solve_dialog

    h.check("deleted", not s.studies())
    h.check("its mesh no longer shown", not simulation_solve_dialog.mesh_shown())
    s.undo()


# -- D ------------------------------------------------------------------------------------------
def d_rename():
    from sciforge import simulation_solve_dialog

    h.check("Undo: back", len(s.studies()) == 1)
    mesh = simulation_solve_dialog.mesh_object(s.active_study())
    h.check(
        "its mesh not drawn",
        not simulation_solve_dialog.mesh_shown()
        and (mesh is None or not mesh.ViewObject.Visibility),
    )
    s.click_row("Study 1 - Static Stress")
    w.key(s.browser(), QtCore.Qt.Key_F2)


def d_empty():
    field = s.browser().findChild(QtWidgets.QLineEdit)
    if not h.check("rename field open", field is not None):
        return
    field.selectAll()
    w.key(field, QtCore.Qt.Key_Delete)
    w.key(field, QtCore.Qt.Key_Return)


def d_check():
    labels = [x.Label for x in s.studies()]
    h.check("the name kept", labels == ["Study 1 - Static Stress"], labels)
    h.ribbon("Solve")


# -- E ------------------------------------------------------------------------------------------
def e_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def e_delete():
    h.check("solving", s.solving())
    s.close_popup("SciForgeSimJobStatus")
    delete_row("Force 1")


def e_check():
    h.check("refused while it solves", len(s.items("load")) == 1)
    h.check("told why", "being solved" in s.told(), s.told())


# -- F ------------------------------------------------------------------------------------------
def f_loads():
    s.close_popup("SciForgeSimJobStatus")
    s.click_tab("sim_setup")
    h.ribbon("Structural Loads")


def f_pick():
    p = s.item_panel()
    h.check(
        "it does not start on Force 1's face (lit up by the click on its row)",
        p is not None and p.picks == [],
        p.picks if p is not None else None,
    )
    s.click_face(s.body(), s.plate_top(s.body()))


def f_undo_key():
    p = s.item_panel()
    h.check("a face picked", p is not None and len(p.picks) == 1)
    state["undo"] = list(App.ActiveDocument.UndoNames)
    s.undo_key()


def f_check():
    h.check("Ctrl+Z ended the dialog", s.item_panel() is None)
    names = list(App.ActiveDocument.UndoNames)
    h.check("nothing else undone", names == state["undo"], (state["undo"], names))
    h.check("still one force", len(s.items("load")) == 1)
    s.menu_item("DISPLAY", "DOF View")


# -- G ------------------------------------------------------------------------------------------
def g_dof_off():
    from sciforge import simulation_ui

    h.check("DOF View on", simulation_ui.dof_on())
    s.menu_item("DISPLAY", "DOF View")


def g_gravity():
    from sciforge import simulation_ui

    h.check("DOF View off", not simulation_ui.dof_on())
    s.menu_item("LOADS", "Toggle Gravity On/Off")


def g_edit():
    h.check("gravity on", s.sim().settings(s.active_study())["gravity"]["on"])
    state["gravity"] = s.sim().settings(s.active_study())["gravity"]
    s.right_click_row("Gravity", "Edit Gravity")


def g_escape():
    h.check("Edit Gravity open", s.task_panel() is not None)
    s.esc()


def g_check():
    h.check("Esc closed it", s.task_panel() is None)
    gravity = s.sim().settings(s.active_study())["gravity"]
    h.check("nothing changed", gravity == state["gravity"], gravity)


h.run(
    "sim_setup_odd",
    [
        setup,
        enter,
        a_loads,
        a_delete,
        a_check,
        b_materials,
        b_leave,
        b_back,
        c_mesh,
        s.wait_solved("wait_meshed"),
        c_delete,
        c_check,
        d_rename,
        d_empty,
        d_check,
        e_go,
        e_delete,
        e_check,
        s.wait_solved(),
        f_loads,
        f_pick,
        f_undo_key,
        f_check,
        g_dof_off,
        g_gravity,
        g_edit,
        g_escape,
        g_check,
    ],
)

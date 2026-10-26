# SPDX-License-Identifier: LGPL-2.1-or-later
"""The workspace switch with something open, several studies, and undo while results show
(builder sim-ui), with real clicks.

A  A sketch is open (Create Sketch on the XY plane): Workspace > Simulation finishes it (no
   sketch in edit, no SKETCH tab), and the New Study dialog opens; Create Study.
B  Structural Loads open, Workspace > Design: the dialog ends (nothing made: OK was not
   possible), DESIGN shows. Back to Simulation.
C  Esc with nothing open: still in SIMULATION, nothing changed.
D  STUDY > New Simulation Study, Create Study: "Study 2 - Static Stress", now the active one;
   the browser lists both. Right-click Study 1 > Activate.
E  A Fixed and a Force on Study 1. Solve: both studies listed, ticking Study 2 too says
   "Solve 2 Studies"; Study 2 holds nothing, so it is refused with its sentence; Study 2
   unticked: "Solve 1 Study" solves Study 1 alone.
F  Undo while the results show (the last setup change, the Force): the results are of a setup
   that changed: out of date; no error; Redo brings the Force back.
G  Workspace > Design with the RESULTS tab in front, then Simulation again: a SIMULATION tab is
   selected, the results row is there.
H  Solve Study 1 again (a finer mesh, so it takes a few seconds) and at once Workspace >
   Design: the solve goes on; when it ends, DESIGN stays in front (a person working on the
   design is not taken away) and a message says where the results are; Workspace > Simulation:
   the results are up to date.
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import plane_input as pl
from SciForgeTests.gui import simsetup_steps as s

state = {}


def setup():
    s.new_bracket("SimWorkspace")()


# -- A ------------------------------------------------------------------------------------------
def a_sketch():
    h.ribbon("Create Sketch")


def a_plane():
    pl.click_square("XY_Plane")


def a_enter():
    h.check("a sketch is open", h.in_sketch() is not None)
    s.workspace("Simulation")


def a_check():
    h.check("the sketch was finished", h.in_sketch() is None)
    h.check("no SKETCH tab", not s.tab_visible("sketch"))
    h.check("SETUP shown", s.tab_visible("sim_setup"))
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


# -- B ------------------------------------------------------------------------------------------
def b_loads():
    h.ribbon("Structural Loads")


def b_leave():
    h.check("Structural Loads open", s.item_panel() is not None)
    s.workspace("Design")


def b_check():
    h.check("the dialog ended", s.item_panel() is None and s.task_panel() is None)
    h.check("nothing made", not s.items())
    h.check("DESIGN shows", s.tab_visible("solid") and not s.tab_visible("sim_setup"))
    s.workspace("Simulation")


# -- C ------------------------------------------------------------------------------------------
def c_escape():
    state["undo"] = list(App.ActiveDocument.UndoNames)
    s.esc()


def c_check():
    h.check("still in SIMULATION", s.tab_visible("sim_setup"))
    h.check("nothing changed", list(App.ActiveDocument.UndoNames) == state["undo"])


# -- D ------------------------------------------------------------------------------------------
def d_new():
    h.ribbon("New Simulation Study")


def d_create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened from the ribbon", dialog is not None):
        s.click_widget(dialog.create_button)


def d_check():
    labels = [x.Label for x in s.studies()]
    h.check("two studies", labels == ["Study 1 - Static Stress", "Study 2 - Static Stress"], labels)
    h.check(
        "the new one is active",
        s.active_study() is not None and s.active_study().Label == "Study 2 - Static Stress",
    )
    rows = s.browser_labels()
    h.check("both in the browser", all(x in rows for x in labels), rows)
    s.right_click_row("Study 1 - Static Stress", "Activate")


def d_activated():
    h.check(
        "Study 1 active",
        s.active_study() is not None and s.active_study().Label == "Study 1 - Static Stress",
    )


# -- E ------------------------------------------------------------------------------------------
def e_fixed():
    h.ribbon("Structural Constraints")


def e_fixed_pick():
    for face in s.hole_faces(s.body()):
        s.click_face(s.body(), face)
    s.ok()


def e_force():
    h.ribbon("Structural Loads")


def e_force_pick():
    s.click_face(s.body(), s.arm_top(s.body()))
    s.ok()


def e_solve():
    h.check("Study 1 has its Fixed and Force", len(s.items()) == 2, [i.Label for i in s.items()])
    h.ribbon("Solve")


def e_both():
    dialog = s.solve_dialog()
    if not h.check("Solve dialog", dialog is not None):
        return
    h.check("both studies listed", dialog.table.rowCount() == 2, dialog.table.rowCount())
    item = dialog.table.item(1, 0)
    rect = dialog.table.visualItemRect(item)
    # the tick box at the start of the row, clicked like a person
    QtTest.QTest.mouseClick(
        dialog.table.viewport(),
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
        QtCore.QPoint(rect.left() + 10, rect.center().y()),
    )
    QtWidgets.QApplication.processEvents()
    h.check("Solve 2 Studies", dialog.go.text() == "Solve 2 Studies", dialog.go.text())
    s.click_widget(dialog.go)
    text = dialog.message.text()
    h.check(
        "Study 2 refused with its sentence", "Study 2" in text and "Nothing holds" in text, text
    )
    h.check("nothing started", not s.solving())
    QtTest.QTest.mouseClick(
        dialog.table.viewport(),
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
        QtCore.QPoint(rect.left() + 10, rect.center().y()),
    )
    QtWidgets.QApplication.processEvents()
    h.check("Solve 1 Study", dialog.go.text() == "Solve 1 Study", dialog.go.text())
    s.click_widget(dialog.go)


def e_check():
    study = s.active_study()
    h.check("Study 1 solved", bool(s.sim().summary(study)))
    other = s.studies()[1]
    h.check("Study 2 not solved", not s.sim().summary(other))
    s.close_popup("SciForgeSimJobStatus")


# -- F ------------------------------------------------------------------------------------------
def f_undo():
    state["undo_names"] = list(App.ActiveDocument.UndoNames)
    s.undo()


def f_check():
    study = s.active_study()
    loads = [i.Label for i in s.items("load")]
    h.check("the Force undone", loads == [], loads)
    h.check("the results are out of date", s.sim().out_of_date(study))
    h.check("Results row marked", "Results (out of date)" in s.browser_labels(), s.browser_labels())
    s.redo()


def f_redo():
    loads = [i.Label for i in s.items("load")]
    h.check("Redo: the Force back", loads == ["Force 1"], loads)
    h.check("up to date again", not s.sim().out_of_date(s.active_study()))


# -- G ------------------------------------------------------------------------------------------
def g_leave():
    s.workspace("Design")


def g_back():
    h.check("DESIGN", s.tab_visible("solid"))
    s.workspace("Simulation")


def g_check():
    h.check(
        "a SIMULATION tab selected",
        s.current_tab() in ("sim_setup", "sim_results"),
        s.current_tab(),
    )
    h.check("the Results row", "Results" in s.browser_labels(), s.browser_labels())


# -- H ------------------------------------------------------------------------------------------
def h_finer():
    # (a precondition: a finer mesh, so the solve lasts long enough to leave during it)
    study = s.active_study()
    App.ActiveDocument.openTransaction("finer mesh")
    s.sim().set_settings(study, {"mesh": {"size_pct": 3.0}})
    App.ActiveDocument.commitTransaction()
    h.ribbon("Solve")


def h_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)
    s.close_popup("SciForgeSimJobStatus")


def h_leave():
    h.check("solving", s.solving())
    s.workspace("Design")


def h_left():
    h.check("DESIGN while it solves", s.tab_visible("solid"))
    h.check("still solving", s.solving())


def h_check():
    h.check("DESIGN stays in front", s.tab_visible("solid") and not s.tab_visible("sim_setup"))
    h.check("not taken to RESULTS", s.current_tab() not in ("sim_setup", "sim_results"))
    text = s.tooltip_text()
    h.check("it says where the results are", "results are in Workspace > Simulation" in text, text)
    s.workspace("Simulation")


def h_back():
    study = s.active_study()
    h.check("Study 1 has results", bool(s.sim().summary(study)))
    h.check("up to date", not s.sim().out_of_date(study))


h.run(
    "sim_setup_workspace",
    [
        setup,
        a_sketch,
        a_plane,
        a_enter,
        a_check,
        b_loads,
        b_leave,
        b_check,
        c_escape,
        c_check,
        d_new,
        d_create,
        d_check,
        d_activated,
        e_fixed,
        e_fixed_pick,
        e_force,
        e_force_pick,
        e_solve,
        e_both,
        s.wait_solved(),
        e_check,
        f_undo,
        f_check,
        f_redo,
        g_leave,
        g_back,
        g_check,
        h_finer,
        h_go,
        h_leave,
        h_left,
        s.wait_solved("wait_solved_in_design"),
        h_check,
        h_back,
    ],
)

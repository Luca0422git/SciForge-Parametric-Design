# SPDX-License-Identifier: LGPL-2.1-or-later
"""What a person may do while a study solves (builder sim-ui), with real clicks. The bracket's
study (Fixed at the holes, a Force on the arm, a fine mesh so that a solve lasts a few seconds)
is made by script.

A  Edit Load: 300 N, OK. Solve, and while it solves: Undo (the 300 N goes back to 100 N, the
   solve goes on), Edit Load refused (told why), Generate Mesh refused (told why). When it
   ends: solved, and out of date (its setup changed while it solved).
B  Solve again and Cancel in the progress window: cancelled, the stage it stopped at says so
   (none still running); Solve again at once: it starts.
C  Workspace > Design while it solves and the bracket deleted (a design change): the solve
   stops with a sentence that names the bracket (no error); Workspace > Simulation: the
   pre-check is red (no body).
"""

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


def setup():
    s.new_bracket("SimDuring")()
    sim = s.sim()
    doc = App.ActiveDocument
    study = sim.create_study(doc)
    body = s.body()
    sim.add_item(study, "constraint", "fixed", [(body, s.hole_faces(body))])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 100.0})
    sim.set_settings(study, {"mesh": {"size_pct": 3.0}})  # (a few seconds of solving)
    doc.recompute()


def enter():
    s.workspace("Simulation")


def force():
    loads = s.items("load")
    return s.sim().item_data(loads[0])["options"]["magnitude"] if loads else None


# -- A ------------------------------------------------------------------------------------------
def a_edit():
    s.right_click_row("Force 1", "Edit Load")


def a_type():
    s.type_in("SciForgeSim_magnitude", "300")
    s.ok()


def a_solve():
    h.check("300 N kept", abs((force() or 0) - 300.0) < 1e-9, force())
    h.ribbon("Solve")


def a_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def a_undo():
    h.check("solving", s.solving())
    s.close_popup("SciForgeSimJobStatus")
    s.undo()


def a_edit_refused():
    h.check("Undo: 100 N again", abs((force() or 0) - 100.0) < 1e-9, force())
    h.check("still solving", s.solving())
    s.right_click_row("Force 1", "Edit Load")


def a_mesh_refused():
    h.check("Edit Load refused while it solves", s.item_panel() is None)
    h.check("told why", "being solved" in s.told(), s.told())
    s.menu_item("SOLVE", "Generate Mesh")


def a_told():
    text = s.told()
    h.check("Generate Mesh refused: a solve runs", "A solve is running" in text, text)


def a_check():
    study = s.active_study()
    h.check("solved", bool(s.sim().summary(study)))
    h.check("out of date (its setup changed while it solved)", s.sim().out_of_date(study))
    s.close_popup("SciForgeSimJobStatus")
    s.click_tab("sim_setup")
    h.ribbon("Solve")


# -- B ------------------------------------------------------------------------------------------
def b_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog (B)", dialog is not None):
        s.click_widget(dialog.go)


def b_cancel():
    status = s.status_dialog()
    if h.check("progress window", status is not None and status.cancel_button.isVisible()):
        s.click_widget(status.cancel_button)


def b_check():
    from sciforge import simulation_solve_dialog as sd

    states = [r[0] for r in sd.last_results().values()]
    h.check("cancelled", states == ["cancelled"], sd.last_results())
    stages = [state_ for _text, state_ in sd.stage_states()]
    h.check("no stage still running", "running" not in stages, stages)
    h.check("the stage it stopped at says cancelled", "cancelled" in stages, stages)
    s.close_popup("SciForgeSimJobStatus")
    h.ribbon("Solve")


def b_again():
    dialog = s.solve_dialog()
    if h.check("Solve dialog (again)", dialog is not None):
        s.click_widget(dialog.go)


# -- C ------------------------------------------------------------------------------------------
def c_design():
    h.check("solving again at once", s.solving())
    s.workspace("Design")


def c_delete():
    h.check("DESIGN while it solves", s.tab_visible("solid"))
    doc = App.ActiveDocument
    body = s.body()
    body.removeObjectsFromDocument()  # (a design change: the bracket deleted)
    doc.removeObject(body.Name)
    doc.recompute()


def c_check():
    from sciforge import simulation_solve_dialog as sd

    h.check("the solve stopped", not s.solving(), sd.last_results())
    status = s.status_dialog()
    text = status.message.text() if status is not None else ""
    h.check("it says the bracket was deleted", "Bracket was deleted" in text, text)
    stages = [state_ for _text, state_ in sd.stage_states()]
    h.check("no stage still running", "running" not in stages, stages)
    s.close_popup("SciForgeSimJobStatus")
    s.workspace("Simulation")


def c_red():
    h.check("pre-check red: no body", s.light() == "red", s.light())


h.run(
    "sim_setup_during",
    [
        setup,
        enter,
        a_edit,
        a_type,
        a_solve,
        a_go,
        a_undo,
        a_edit_refused,
        a_mesh_refused,
        a_told,
        s.wait_solved("wait_a", 240),
        a_check,
        b_go,
        b_cancel,
        s.wait_solved("wait_b", 60),
        b_check,
        b_again,
        c_design,
        c_delete,
        s.wait_solved("wait_c", 240),
        c_check,
        c_red,
    ],
)

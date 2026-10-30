# SPDX-License-Identifier: LGPL-2.1-or-later
"""A design closed while one of its dialogs is open (sim QA): FreeCAD keeps that dialog's
undo step open application-wide after its document went; the next design's changes went into
a step of that name, and a solve there waited for it forever. hole_common.abandon (the shared
"the document is closing" of the dialogs) now closes it once the dialog is gone.

B  The real path: two designs (a solved beam in front, a bracket behind); in the bracket's
   SIMULATION workspace Structural Loads is open; its tab closed with the dialog open: the
   dialog ends, no undo step is left open, the beam's next change (New Study, with real
   clicks) is an undo step of its own, and a solve of the beam ends (it waited forever).
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as rs
from SciForgeTests.gui import simsetup_steps as s

state = {}


# -- B ------------------------------------------------------------------------------------------
def b_bracket():
    s.new_bracket("SimQAClose")()
    s.sim().create_study(App.ActiveDocument)
    App.ActiveDocument.recompute()
    state["bracket"] = App.ActiveDocument.Name


def b_enter():
    s.workspace("Simulation")


def b_loads():
    h.ribbon("Structural Loads")


def b_close():
    h.check("B Structural Loads open", s.item_panel() is not None)
    h.check("B its undo step is open", bool(App.getActiveTransaction()), App.getActiveTransaction())
    App.closeDocument(state["bracket"])  # (a person: the tab's close button, Don't Save)


def b_closed():
    h.check("B the bracket closed", state["bracket"] not in App.listDocuments())
    h.check("B no dialog left", not Gui.Control.activeDialog())
    h.check("B no undo step left open", not App.getActiveTransaction(), App.getActiveTransaction())


def b_beam_new_study():
    h.check(
        "B the beam is in front",
        App.ActiveDocument is not None and App.ActiveDocument.Name == state["beam"],
    )
    s.workspace("Simulation")


def b_create():
    dialog = s.new_study_dialog()
    if dialog is None:  # (the beam has a study: New Simulation Study from the ribbon)
        h.ribbon("New Simulation Study")


def b_create_click():
    dialog = s.new_study_dialog()
    if h.check("B New Study", dialog is not None):
        s.click_widget(dialog.create_button)


def b_undo_names():
    names = App.ActiveDocument.UndoNames
    h.check(
        "B the new study is its own undo step", names and names[0] == "New Simulation Study", names
    )
    h.check("B nothing went into the closed dialog's step", "Structural Loads" not in names, names)
    s.right_click_row(s.studies()[0].Label, "Activate")


def b_activate_first():
    h.check("B the beam's first study active again", s.active_study() == s.studies()[0])
    h.ribbon("Solve")


def b_solve():
    dialog = s.solve_dialog()
    if h.check("B the Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def b_solved():
    from sciforge import simulation_solve_dialog

    results = simulation_solve_dialog.last_results()
    h.check(
        "B the beam's solve ended (it waited forever)",
        any(r[0] == "done" for r in results.values()),
        results,
    )


def b_beam():
    rs.new_solved_beam("SimQACloseBeam")()
    state["beam"] = App.ActiveDocument.Name


h.run(
    "sim_qa_close",
    [
        b_beam,
        b_bracket,
        b_enter,
        b_loads,
        b_close,
        b_closed,
        b_beam_new_study,
        b_create,
        b_create_click,
        b_undo_names,
        b_activate_first,
        b_solve,
        s.wait_solved(),
        b_solved,
    ],
    paced_by="state",
)

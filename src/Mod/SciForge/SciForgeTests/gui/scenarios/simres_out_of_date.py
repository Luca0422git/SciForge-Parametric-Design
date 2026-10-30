# SPDX-License-Identifier: LGPL-2.1-or-later
"""Results of a design changed after the solve (builder sim-results), on a solved steel
cantilever 100 mm long.

A  The results show with no warning.
B  In DESIGN the beam is made 120 mm long; back on RESULTS the legend warns that the results are
   out of date and offers Solve Again (Results Details says it too); the old results still show.
C  Ctrl+Z in DESIGN puts the 100 mm back: no warning; Ctrl+Y: the warning again.
D  Solve Again: sim-ui's Solve dialog solves the study; the new results show, not out of date,
   with the longer beam's larger bend (about 1.7 times: L cubed).
"""

from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def a_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    if sess is None:
        return
    h.check("not out of date", not sess.out_of_date)
    h.check("no warning", not sess.legend.warning.isVisible())
    h.check("no Solve Again", not sess.legend.solve_button.isVisible())
    state["disp"] = s.stats("displacement")["max"]


def b_design():
    s.workspace("Design")


def b_longer():
    doc = s.doc()
    box = doc.getObject("Box")
    doc.openTransaction("Change the length")
    box.Length = 120.0
    doc.commitTransaction()
    doc.recompute()


def b_back():
    s.workspace("Simulation")


def b_results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def b_check():
    sess = s.session()
    h.check("results still shown", sess is not None)
    if sess is None:
        return
    h.check("out of date", sess.out_of_date)
    h.check("the legend warns", sess.legend.warning.isVisible(), sess.legend.warning.text())
    h.check("out of date in words", "out of date" in sess.legend.warning.text())
    h.check("Solve Again offered", sess.legend.solve_button.isVisible())
    h.check(
        "the old results still show",
        abs(sess.data.max_displacement - state["disp"]) < 1e-9,
    )


def b_details():
    s.click_widget(s.legend_widget("SciForgeSimDetailsButton"))


def b_details_check():
    dialog = s.dialog("SciForgeSimDetails")
    h.check("Results Details open", dialog is not None)
    if dialog is not None:
        label = dialog.findChild(QtWidgets.QLabel, "SciForgeSimDetailsOutOfDate")
        h.check("Results Details says out of date", label is not None and label.isVisible())
        dialog.close()


def c_design():
    s.workspace("Design")


def c_undo():
    h.press("z", QtCore.Qt.ControlModifier)


def c_undone():
    h.check("100 mm again", abs(s.doc().getObject("Box").Length.Value - 100.0) < 1e-9)
    s.workspace("Simulation")


def c_results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def c_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    if sess is not None:
        h.check("up to date again after Undo", not sess.out_of_date)
        h.check("no warning", not sess.legend.warning.isVisible())


def c_redo_design():
    s.workspace("Design")


def c_redo():
    h.press("y", QtCore.Qt.ControlModifier)


def c_redone():
    h.check("120 mm again", abs(s.doc().getObject("Box").Length.Value - 120.0) < 1e-9)
    s.workspace("Simulation")


def c_redo_results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def c_redo_check():
    sess = s.session()
    h.check("out of date after Redo", sess is not None and sess.out_of_date)


def d_solve_again():
    s.click_widget(s.legend_widget("SciForgeSimSolveAgain", QtWidgets.QPushButton))


def d_solve_dialog():
    dialog = s.dialog("SciForgeSimSolve")
    h.check("sim-ui's Solve dialog opens", dialog is not None)
    if dialog is not None:
        s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimSolveGo"))


def _solved():
    sess = s.session()
    return (
        sess is not None
        and not sess.out_of_date
        and sess.data is not None
        and (sess.data.max_displacement > state["disp"] * 1.2)
    )


def d_check():
    sess = s.session()
    h.check("the new results show", sess is not None)
    if sess is None:
        return
    h.check("not out of date", not sess.out_of_date)
    h.check("no warning", not sess.legend.warning.isVisible())
    ratio = s.stats("displacement")["max"] / state["disp"]
    h.check("the longer beam bends about 1.73 times as much", 1.55 < ratio < 1.9, ratio)
    h.check("on the RESULTS tab", s.current_tab() == "sim_results", s.current_tab())


h.run(
    "simres_out_of_date",
    [
        s.new_solved_beam("SimResStale"),
        enter,
        results,
        a_check,
        b_design,
        b_longer,
        b_back,
        b_results,
        b_check,
        b_details,
        b_details_check,
        c_design,
        c_undo,
        h.idle_step(),
        c_undone,
        c_results,
        c_check,
        c_redo_design,
        c_redo,
        h.idle_step(),
        c_redone,
        c_redo_results,
        c_redo_check,
        d_solve_again,
        d_solve_dialog,
        s.wait_until(_solved, "wait_solved", 180),
        d_check,
    ],
    paced_by="state",
)

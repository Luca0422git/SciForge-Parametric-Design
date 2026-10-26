# SPDX-License-Identifier: LGPL-2.1-or-later
"""Save and reopen a design whose results show (builder sim-results), on a solved steel
cantilever.

A  Results on the screen (Stress chosen): Save As writes the design with the beam visible (the
   results hide it on the view only); Ctrl+S with its version description; nothing unsaved.
B  Close the design while its results show: no error; reopen it: the beam shows (DESIGN).
C  Workspace > Simulation: the RESULTS tab is offered (the results came back with the file);
   a click shows them, on the safety factor, with the same numbers as before the save, from the
   same mesh, and not out of date.
"""

import os
import tempfile

import FreeCAD as App
from PySide import QtCore

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s
from SciForgeTests.gui import versions_input as vi

state = {}


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def results_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    s.choose_result("Stress")
    state["sf_min"] = s.stats("safety")["min"]
    state["vm_max"] = s.stats("von_mises")["max"]
    state["nodes"] = s.summary()["mesh"]["nodes"]


def a_save_as():
    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-simres-"), "simres_reopen.FCStd")
    state["path"] = path
    s.doc().saveAs(path)
    h.check("saved", os.path.isfile(path), path)
    h.check("results still shown", s.session() is not None)


def a_ctrl_s():
    h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)


def a_describe():
    h.check("the Save dialog asks for a version description", vi.version_dialog() is not None)
    vi.accept_save()


def a_check():
    # (the solve's own objects stay "touched", sim-core's: Modified is what Save clears)
    h.check("nothing unsaved", not s.modified())
    h.check("the beam stays visible in the file", s.body().ViewObject.Visibility)


def b_close():
    App.closeDocument(s.doc().Name)


def b_closed():
    h.check("no results left", s.session() is None)


def b_reopen():
    App.openDocument(state["path"])
    h.fit()


def b_check():
    h.check("the beam shows", s.design_switches() != -1)
    h.check("the study came back", s.study() is not None)


def c_enter():
    s.workspace("Simulation")


def c_tab():
    s.close_new_study_dialog()
    h.check("RESULTS offered", s.tab_visible("sim_results"))
    s.click_tab("sim_results")


def c_check():
    sess = s.session()
    h.check("results shown after reopening", sess is not None)
    if sess is None:
        return
    h.check("on the safety factor", sess.result == "safety", sess.result)
    h.check(
        "the same lowest safety factor",
        abs(sess.legend_info["min"] - state["sf_min"]) < 1e-9,
        (sess.legend_info["min"], state["sf_min"]),
    )
    h.check("the same mesh", len(sess.data.points) == state["nodes"], len(sess.data.points))
    h.check("not out of date", not sess.out_of_date)
    h.check("no out-of-date warning", not sess.legend.warning.isVisible())
    s.choose_result("Stress")
    h.check(
        "the same highest stress",
        abs(sess.legend_info["max"] - state["vm_max"]) < 1e-9,
        (sess.legend_info["max"], state["vm_max"]),
    )
    h.check("the beam hidden on the view", s.design_switches() == -1)


h.run(
    "simres_reopen",
    [
        s.new_solved_beam("SimResReopen"),
        enter,
        results,
        results_check,
        a_save_as,
        a_ctrl_s,
        a_describe,
        a_check,
        b_close,
        b_closed,
        b_reopen,
        h.idle_step(),
        b_check,
        c_enter,
        c_tab,
        c_check,
    ],
)

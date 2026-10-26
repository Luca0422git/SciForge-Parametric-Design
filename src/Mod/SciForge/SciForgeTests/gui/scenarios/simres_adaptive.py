# SPDX-License-Identifier: LGPL-2.1-or-later
"""Results of a study solved with adaptive mesh refinement (builder sim-results), on a steel
cantilever 100 x 10 x 10 mm with 300 N down at the tip, refinement Low (two solves: the second
on a mesh made finer where the stress changes the most).

A  The RESULTS tab draws the last solve's results: the mesh drawn is the refined one (the
   solve's node count), the legend's max is the solve's.
B  INSPECT > Solver Data: the Adaptive mesh refinement section lists both solves, the second on
   more nodes than the first, with the von Mises stress each found; the mesh section has the
   refined mesh's nodes.
C  Legend > Stress: the max tag sits where the solve put the highest stress.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def setup():
    from sciforge import simulation

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimResAdaptive")
    body = s.beam(doc)
    study = s.cantilever_study(doc, body, 300.0)
    simulation.set_settings(study, {"adaptive": {"level": "low", "result": "von_mises"}})
    s.solve(study)
    h.fit()


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
    summary = s.summary()
    passes = (summary.get("adaptive") or {}).get("passes") or []
    state["passes"] = passes
    h.check("two solves made", len(passes) == 2, passes)
    h.check(
        "the refined mesh drawn (the solve's nodes)",
        len(sess.data.points) == int(summary["mesh"]["nodes"]),
        (len(sess.data.points), summary["mesh"]["nodes"]),
    )
    sf = s.stats("safety")
    h.check(
        "the legend's min is the last solve's",
        abs(sess.legend_info["min"] - sf["min"]) < 1e-9,
        (sess.legend_info["min"], sf["min"]),
    )


def b_solver():
    s.menu("INSPECT", "Solver Data")


def b_check():
    dialog = s.dialog("SciForgeSimSolverData")
    h.check("Solver Data open", dialog is not None)
    if dialog is None:
        return
    rows = s.tree_rows(dialog.findChild(QtWidgets.QTreeWidget, "SciForgeSimSolverTree"))
    adaptive = rows.get("Adaptive mesh refinement", {})
    passes = state.get("passes") or []
    h.check("both solves listed", sorted(adaptive) == ["Solve 1", "Solve 2"], adaptive)
    if len(passes) == 2 and len(adaptive) == 2:
        first, second = passes
        h.check(
            "the second on more nodes",
            second["nodes"] > first["nodes"]
            and "{:,} nodes".format(second["nodes"]) in adaptive["Solve 2"],
            adaptive,
        )
        h.check(
            "with the stress each found",
            s.results_core().fmt(second["value"]) in adaptive["Solve 2"]
            and adaptive["Solve 2"].endswith("MPa"),
            adaptive["Solve 2"],
        )
    nodes = int(s.summary()["mesh"]["nodes"])
    h.check(
        "the refined mesh's nodes",
        rows.get("Mesh", {}).get("Nodes") == "{:,}".format(nodes),
        rows.get("Mesh"),
    )
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimSolverClose"))


def c_stress():
    s.choose_result("Stress")


def c_check():
    sess = s.session()
    vm = s.stats("von_mises")
    tags = s.tags("max")
    h.check("a max tag", len(tags) == 1, tags)
    if tags:
        h.check("at the solve's highest stress", tags[0]["node"] == vm["max_index"], tags[0])
        h.check("its value", abs(tags[0]["value"] - vm["max"]) < 1e-9)
    h.check("the legend's max", abs(sess.legend_info["max"] - vm["max"]) < 1e-9)


h.run(
    "simres_adaptive",
    [setup, enter, results, a_check, b_solver, b_check, c_stress, c_check],
)

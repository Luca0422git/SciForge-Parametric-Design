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
D  RESULT TOOLS > Convergence Plot: a row per solve with its nodes and stress, the change
   between the two solves, the verdict the engine reached with the Low level's tolerance
   (converged or not, and what to do), a dot per solve on the chart (left to right, the higher
   stress higher); Close.
E  Report (no pictures): the mesh section has the adaptive refinement's solves (nodes, stress,
   change) and the verdict; with pictures the convergence chart is one of them.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}
OUT = os.environ.get("SCIFORGE_SMOKE_OUT", "")


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


def d_convergence():
    s.menu("RESULT TOOLS", "Convergence Plot")


def d_check():
    from sciforge import simulation_core as sim

    dialog = s.dialog("SciForgeSimConvergence")
    h.check("Convergence Plot open", dialog is not None)
    if dialog is None:
        return
    core = s.results_core()
    passes = state.get("passes") or []
    table = dialog.findChild(QtWidgets.QTableWidget, "SciForgeSimConvergenceTable")
    h.check(
        "a row per solve",
        table is not None and table.rowCount() == len(passes) == 2,
        table.rowCount() if table is not None else None,
    )
    if table is None or len(passes) != 2 or table.rowCount() != 2:
        return
    for row, step in enumerate(passes):
        got = (table.item(row, 1).text(), table.item(row, 3).text())
        h.check(
            "solve %d: its nodes and stress (MPa)" % (row + 1),
            got == ("{:,}".format(step["nodes"]), core.fmt(step["value"])),
            (got, step),
        )
    first, second = passes[0]["value"], passes[1]["value"]
    change = core.change_pct(first, second)
    h.check(
        "the change between the solves",
        table.item(0, 4).text() == "-" and table.item(1, 4).text() == "%s %%" % core.fmt(change, 3),
        (table.item(1, 4).text(), change),
    )
    tolerance = sim.ADAPTIVE_LEVELS["low"][1]
    converged = sim.converged(first, second, tolerance)
    sentence = dialog.findChild(QtWidgets.QLabel, "SciForgeSimConvergenceSentence").text()
    h.check(
        "the engine's verdict (%s within %s %%)" % ("converged" if converged else "not", tolerance),
        sentence.startswith("Converged" if converged else "Not converged")
        and ("%s %% tolerance" % core.fmt(tolerance)) in sentence,
        sentence,
    )
    chart = dialog.findChild(QtWidgets.QWidget, "SciForgeSimConvergenceChart")
    dots = chart.points() if chart is not None else []
    h.check("a dot per solve on the chart", len(dots) == 2 and all(dots), dots)
    if len(dots) == 2 and all(dots):
        h.check("left to right", dots[0][0] < dots[1][0], dots)
        h.check(
            "the higher stress higher",
            (dots[1][1] < dots[0][1]) == (second > first) or first == second,
            (dots, first, second),
        )
    if OUT:
        try:
            dialog.grab().save(os.path.join(OUT, "simres_adaptive_convergence.png"))
        except Exception:
            pass
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimConvergenceClose"))


def d_closed():
    h.check("closed", s.dialog("SciForgeSimConvergence") is None)


def e_report():
    s.big("Report")
    dialog = s.dialog("SciForgeSimReport")
    h.check("Report dialog open", dialog is not None)
    if dialog is None:
        return
    state["report"] = os.path.join(s.OUT, "simres_adaptive_report.html")
    s.click_widget(dialog.findChild(QtWidgets.QCheckBox, "SciForgeSimReportPictures"))
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), state["report"])
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


def e_check():
    path = state.get("report") or ""
    h.check("report written", os.path.isfile(path), path)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    passes = state.get("passes") or []
    h.check("its adaptive refinement section", "<h3>Adaptive mesh refinement</h3>" in text)
    h.check(
        "both solves' nodes",
        all("<td>{:,}</td>".format(p["nodes"]) in text for p in passes) and len(passes) == 2,
    )
    h.check(
        "both solves' stress",
        all("<td>%s</td>" % s.results_core().fmt(p["value"]) in text for p in passes),
    )
    h.check("the verdict", "onverged" in text)


def e_pictures():
    s.big("Report")
    dialog = s.dialog("SciForgeSimReport")
    h.check("Report dialog open again", dialog is not None)
    if dialog is None:
        return
    state["report2"] = os.path.join(s.OUT, "simres_adaptive_report_pictures.html")
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), state["report2"])
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))


def e_pictures_check():
    path = state.get("report2") or ""
    h.check("report with pictures written", os.path.isfile(path), path)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    h.check("the convergence chart among the pictures", "Convergence: Stress: Von Mises" in text)
    h.check("five pictures (setup, three results, convergence)", text.count("<img ") == 5)


h.run(
    "simres_adaptive",
    [
        setup,
        enter,
        results,
        a_check,
        b_solver,
        b_check,
        c_stress,
        c_check,
        d_convergence,
        d_check,
        d_closed,
        e_report,
        e_check,
        e_pictures,
        e_pictures_check,
    ],
    paced_by="state",
)

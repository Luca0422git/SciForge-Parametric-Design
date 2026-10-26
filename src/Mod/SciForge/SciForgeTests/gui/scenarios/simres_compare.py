# SPDX-License-Identifier: LGPL-2.1-or-later
"""RESULT TOOLS > Compare with real clicks (builder sim-results): one steel cantilever, two
studies (100 N and 200 N at the tip), both solved.

A  Compare: the dialog lists both studies ticked; Compare 2 Studies puts the two results side by
   side (the second beam beside the first, along Y: the beams are long in X), each with a tag
   naming its study with its min and max, on one colour scale.
B  Legend > Stress: one scale for both, so the 100 N beam's highest stress sits half way up the
   200 N one's; DEFORMATION > Actual applies to both; Surface Probes rests meanwhile.
C  Finish Compare (under the legend): back to the active study's results.
D  Compare again, then SETUP: Compare ends and the beam shows again.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimResCompare")
    body = s.beam(doc)
    first = s.cantilever_study(doc, body, 100.0, label="Light Load")
    s.solve(first)
    second = s.cantilever_study(doc, body, 200.0, label="Heavy Load")
    s.solve(second)
    state["first"], state["second"] = first.Name, second.Name
    h.fit()


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def a_compare():
    h.check("results shown", s.session() is not None)
    s.menu("RESULT TOOLS", "Compare")


def a_dialog():
    dialog = s.dialog("SciForgeSimCompare")
    h.check("Compare dialog open", dialog is not None)
    if dialog is None:
        return
    h.check("both studies listed and ticked", len(dialog.chosen()) == 2, dialog.chosen())
    go = dialog.findChild(QtWidgets.QPushButton, "SciForgeSimCompareGo")
    h.check("Compare 2 Studies", go.text() == "Compare 2 Studies", go.text())
    s.click_widget(go)


def _compare():
    from sciforge import simulation_results_ui as ui

    return ui.COMPARE["session"] if ui.compare_on() else None


def a_check():
    cmp = _compare()
    h.check("comparing", cmp is not None)
    if cmp is None:
        return
    h.check("two results drawn", len(cmp.items) == 2)
    shifts = [tuple(float(c) for c in i["display"].offset) for i in cmp.items]
    # the beams are long in X: they lie side by side along Y, 10 mm apart
    h.check(
        "side by side (the second 20 mm along Y)",
        shifts == [(0.0, 0.0, 0.0), (0.0, 20.0, 0.0)],
        shifts,
    )
    texts = [t["text"] for t in cmp.tag_list]
    h.check(
        "a tag per study with its name",
        len(texts) == 2
        and any("Light Load" in t for t in texts)
        and any("Heavy Load" in t for t in texts),
        texts,
    )
    h.check("the normal results put away", s.session() is None)
    h.check("the beam hidden on the view", s.design_switches() == -1)
    h.check("the legend says so", "Compare" in cmp.legend.study_label.text())
    h.check("Finish Compare offered", cmp.legend.compare_button.isVisible())


def b_stress():
    cmp = _compare()
    box = cmp.legend.findChild(QtWidgets.QComboBox, "SciForgeSimResultGroup")
    from SciForgeTests.gui import dialog_input as ui

    ui.choose(box, "Stress")


def b_check():
    from sciforge import simulation

    cmp = _compare()
    heavy = simulation.summary(s.doc().getObject(state["second"]))["stats"]["von_mises"]["max"]
    h.check("one scale: up to the heavy load's stress", abs(cmp.legend_info["max"] - heavy) < 1e-9)
    light = [i for i in cmp.items if i["study"].Name == state["first"]][0]["display"]
    top = max(p for p in light.node_positions().values() if p is not None)
    h.check("the light load's highest stress half way up", 0.45 < top < 0.55, top)
    s.menu("DEFORMATION", "Actual")


def b_actual_check():
    cmp = _compare()
    h.check("Actual for both", all(abs(i["display"].factor - 1.0) < 1e-12 for i in cmp.items))
    from sciforge import simulation_results_ui as ui

    h.check("Surface Probes rests meanwhile", not ui.ProbesCommand().IsActive())


def c_finish():
    s.click_widget(_compare().legend.compare_button)


def c_check():
    h.check("Compare finished", _compare() is None)
    sess = s.session()
    h.check("the active study's results again", sess is not None)
    h.check(
        "one result drawn, where it is", sess is not None and float(sess.display.offset[0]) == 0
    )


def d_again():
    s.menu("RESULT TOOLS", "Compare")


def d_go():
    dialog = s.dialog("SciForgeSimCompare")
    if dialog is not None:
        s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimCompareGo"))


def d_setup():
    h.check("comparing again", _compare() is not None)
    s.click_tab("sim_setup")


def d_check():
    h.check("SETUP ends Compare", _compare() is None)
    h.check("no results left on the view", not s.result_root_in_view())
    h.check("the beam shows", s.design_switches() != -1)


h.run(
    "simres_compare",
    [
        setup,
        enter,
        results,
        a_compare,
        a_dialog,
        a_check,
        b_stress,
        b_check,
        b_actual_check,
        c_finish,
        c_check,
        d_again,
        d_go,
        d_setup,
        d_check,
    ],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""RESULT TOOLS > Compare with real clicks (builder sim-results): one steel cantilever, two
studies (100 N and 200 N at the tip), both solved.

A  Compare: the dialog lists both studies ticked; Compare 2 Studies splits the 3D view in two
   panes side by side (Navigation bar > Viewports' Two Views Horizontal), each study's result in
   its own pane (nothing moved), each with a tag naming its study with its min and max, on one
   colour scale; turning one pane's camera turns the other with it (both ways).
B  Legend > Stress: one scale for both, so the 100 N beam's highest stress sits half way up the
   200 N one's; DEFORMATION > Actual applies to both; Surface Probes rests meanwhile.
C  Finish Compare (under the legend): back to one view with the active study's results.
D  A third study (300 N) solved; Compare: three listed, the shown one ticked; ticking the other
   two (clicks on their tick boxes): Compare 3 Studies splits the view in four panes, a study in
   each of the first three, the fourth says it stays empty; SETUP ends Compare: one view again,
   the beam shown.
E  RESULTS, Compare again (the shown study and one more): Navigation bar > Viewports > Single
   View ends Compare (one view, the shown study's results).
F  When the view cannot be split (Viewports refuses), Compare puts the studies side by side in
   the one view instead (the second beam beside the first, along Y: the beams are long in X),
   each tag at its own beam; Finish Compare.
G  Compare again; a solve ends meanwhile (sim-ui's Solve dialog shows its study's results):
   Compare ends, one view with that study's results.
H  The beam made 120 mm long and only the 300 N study solved again: Compare of all three says
   which ones are out of date on their tags; the beam back to 100 mm while comparing: the marks
   follow (the 300 N study out of date now, the others not).
I  FINISH RESULTS during Compare: SETUP, one view, the beam shown.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

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


def _layout():
    from sciforge import viewports_ui

    return viewports_ui.current()


def _in_own_pane(cmp):
    """Each study's result is drawn in its own pane's view and in no other."""
    ok = []
    for item in cmp.items:
        own = item["pane"]["view"].getSceneGraph().findChild(item["display"].root) >= 0
        others = [
            p["view"].getSceneGraph().findChild(item["display"].root) >= 0
            for p in cmp.panes
            if p is not item["pane"]
        ]
        ok.append(own and not any(others))
    return ok


def a_check():
    cmp = _compare()
    h.check("comparing", cmp is not None)
    if cmp is None:
        return
    h.check("two results drawn", len(cmp.items) == 2)
    h.check(
        "the view split in two panes side by side",
        cmp.split and len(cmp.panes) == 2 and _layout() == "Two Views Horizontal",
        (cmp.split, len(cmp.panes), _layout()),
    )
    h.check("each study in its own pane", _in_own_pane(cmp) == [True, True], _in_own_pane(cmp))
    shifts = [tuple(float(c) for c in i["display"].offset) for i in cmp.items]
    h.check("nothing moved", shifts == [(0.0, 0.0, 0.0)] * 2, shifts)
    texts = [[t["text"] for t in p["tags"].tags] for p in cmp.panes]
    h.check(
        "a tag per pane naming its study",
        len(texts) == 2
        and len(texts[0]) == 1
        and len(texts[1]) == 1
        and "Light Load" in texts[0][0]
        and "Heavy Load" in texts[1][0],
        texts,
    )
    h.check("the normal results put away", s.session() is None)
    h.check("the beam hidden on the view", s.design_switches() == -1)
    h.check("the legend says so", "Compare" in cmp.legend.study_label.text())
    h.check("Finish Compare offered", cmp.legend.compare_button.isVisible())
    h.shot("simres_compare_split")


def _orientation(view):
    return [round(c, 5) for c in view.getCameraNode().orientation.getValue().getValue()]


def a_turn():
    cmp = _compare()
    state["before"] = _orientation(cmp.panes[1]["view"])
    cmp.panes[0]["view"].viewTop()


a_turn.wait_ms = 600


def a_turn_check():
    cmp = _compare()
    first, second = _orientation(cmp.panes[0]["view"]), _orientation(cmp.panes[1]["view"])
    h.check("the second pane turned with the first", first == second and second != state["before"])
    cmp.panes[1]["view"].viewRight()


a_turn_check.wait_ms = 600


def a_turn_back_check():
    cmp = _compare()
    first, second = _orientation(cmp.panes[0]["view"]), _orientation(cmp.panes[1]["view"])
    h.check("and the first with the second", first == second, (first, second))
    cmp.panes[0]["view"].viewIsometric()
    cmp.panes[0]["view"].fitAll()


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
    h.check("one view again", _layout() == "Single View", _layout())
    sess = s.session()
    h.check("the active study's results again", sess is not None)
    h.check(
        "one result drawn, where it is", sess is not None and float(sess.display.offset[0]) == 0
    )


def d_third():
    doc = s.doc()
    third = s.cantilever_study(doc, s.body(), 300.0, label="Big Load")
    s.solve(third)
    state["third"] = third.Name


d_third.wait_ms = 1000


def d_again():
    s.menu("RESULT TOOLS", "Compare")


def d_tick():
    from PySide6 import QtTest

    dialog = s.dialog("SciForgeSimCompare")
    h.check("Compare dialog open", dialog is not None)
    if dialog is None:
        return
    listing = dialog.findChild(QtWidgets.QListWidget, "SciForgeSimCompareStudies")
    names = [listing.item(i).text() for i in range(listing.count())]
    h.check("three studies listed", len(names) == 3, names)
    ticked = [
        listing.item(i).text()
        for i in range(listing.count())
        if listing.item(i).checkState() == QtCore.Qt.Checked
    ]
    h.check("the shown one ticked", len(ticked) == 1, ticked)
    for i in range(listing.count()):
        item = listing.item(i)
        if item.checkState() != QtCore.Qt.Checked:
            rect = listing.visualItemRect(item)
            QtTest.QTest.mouseClick(
                listing.viewport(),
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                QtCore.QPoint(rect.left() + 10, rect.center().y()),
            )
    go = dialog.findChild(QtWidgets.QPushButton, "SciForgeSimCompareGo")
    h.check("Compare 3 Studies", go.text() == "Compare 3 Studies", go.text())
    s.click_widget(go)


d_tick.wait_ms = 1500


def d_check_three():
    cmp = _compare()
    h.check("comparing three", cmp is not None and len(cmp.items) == 3)
    if cmp is None:
        return
    h.check(
        "the view split in four panes",
        cmp.split and len(cmp.panes) == 4 and _layout() == "Multiple Views",
        (cmp.split, len(cmp.panes), _layout()),
    )
    h.check("each in its own pane", _in_own_pane(cmp) == [True] * 3, _in_own_pane(cmp))
    notes = [p.get("note") is not None for p in cmp.panes]
    h.check("the fourth pane says it stays empty", notes == [False, False, False, True], notes)
    if notes[-1]:
        h.check("its words", "3 studies" in cmp.panes[3]["note"].text())
    h.shot("simres_compare_three")


def d_setup():
    h.check("comparing again", _compare() is not None)
    s.click_tab("sim_setup")


d_setup.wait_ms = 1000


def d_check():
    h.check("SETUP ends Compare", _compare() is None)
    h.check("one view again", _layout() == "Single View", _layout())
    h.check("no results left on the view", not s.result_root_in_view())
    h.check("the beam shows", s.design_switches() != -1)


def e_results():
    s.click_tab("sim_results")


def e_compare():
    s.menu("RESULT TOOLS", "Compare")


def e_tick():
    from PySide6 import QtTest

    dialog = s.dialog("SciForgeSimCompare")
    h.check("Compare dialog open again", dialog is not None)
    if dialog is None:
        return
    listing = dialog.findChild(QtWidgets.QListWidget, "SciForgeSimCompareStudies")
    for i in range(listing.count()):
        item = listing.item(i)
        if item.checkState() != QtCore.Qt.Checked:
            rect = listing.visualItemRect(item)
            QtTest.QTest.mouseClick(
                listing.viewport(),
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                QtCore.QPoint(rect.left() + 10, rect.center().y()),
            )
            break
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimCompareGo"))


e_tick.wait_ms = 1500


def e_single():
    cmp = _compare()
    h.check("comparing two in two panes", cmp is not None and len(cmp.panes) == 2, cmp)
    Gui.runCommand("SciForge_ViewportSingle", 0)  # (Navigation bar > Viewports > Single View)


e_single.wait_ms = 1500


def e_check():
    h.check("Single View ends Compare", _compare() is None)
    h.check("one view", _layout() == "Single View", _layout())
    h.check("the shown study's results", s.session() is not None)


def f_no_split():
    from sciforge import viewports_ui

    state["set_layout"] = viewports_ui.set_layout
    viewports_ui.set_layout = lambda *_a, **_k: False  # (the view cannot be split)
    s.menu("RESULT TOOLS", "Compare")


def f_go():
    dialog = s.dialog("SciForgeSimCompare")
    h.check("Compare dialog open", dialog is not None)
    if dialog is not None:
        e_tick()


f_go.wait_ms = 1500


def f_check():
    from sciforge import viewports_ui

    viewports_ui.set_layout = state.pop("set_layout")
    cmp = _compare()
    h.check("comparing in one view", cmp is not None and not cmp.split and len(cmp.panes) == 1)
    if cmp is None:
        return
    shifts = [tuple(float(c) for c in i["display"].offset) for i in cmp.items]
    h.check(
        "side by side (the second 20 mm along Y)",
        shifts == [(0.0, 0.0, 0.0), (0.0, 20.0, 0.0)],
        shifts,
    )
    ys = [round(t["point"][1], 6) for t in cmp.tag_list]
    h.check("each tag over its own beam", len(ys) == 2 and abs(ys[1] - ys[0] - 20.0) < 1e-6, ys)
    h.check("one view", _layout() == "Single View", _layout())
    s.click_widget(cmp.legend.compare_button)


def f_finished():
    h.check("Compare finished", _compare() is None)
    h.check("the shown study's results", s.session() is not None)


def g_compare():
    s.menu("RESULT TOOLS", "Compare")


def g_go():
    e_tick()


g_go.wait_ms = 1500


def g_solved():
    from sciforge import simulation_results_ui as ui

    h.check("comparing in split views", _compare() is not None and _compare().split)
    ui.show(s.doc().getObject(state["second"]))  # (what sim-ui's Solve dialog does at the end)


g_solved.wait_ms = 1500


def g_check():
    h.check("the solve's results end Compare", _compare() is None)
    h.check("one view", _layout() == "Single View", _layout())
    sess = s.session()
    h.check(
        "the solved study's results shown",
        sess is not None and sess.study_name == state["second"],
        sess.study_name if sess else None,
    )


def h_change():
    doc = s.doc()
    box = [o for o in doc.Objects if o.TypeId == "PartDesign::AdditiveBox"][0]
    box.Length = 120.0
    doc.recompute()
    s.solve(doc.getObject(state["third"]))


h_change.wait_ms = 1500


def h_compare():
    s.menu("RESULT TOOLS", "Compare")


def h_tick_all():
    from PySide6 import QtTest

    dialog = s.dialog("SciForgeSimCompare")
    h.check("Compare dialog open", dialog is not None)
    if dialog is None:
        return
    listing = dialog.findChild(QtWidgets.QListWidget, "SciForgeSimCompareStudies")
    for i in range(listing.count()):
        item = listing.item(i)
        if item.checkState() != QtCore.Qt.Checked:
            rect = listing.visualItemRect(item)
            QtTest.QTest.mouseClick(
                listing.viewport(),
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                QtCore.QPoint(rect.left() + 10, rect.center().y()),
            )
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimCompareGo"))


h_tick_all.wait_ms = 1500


def h_check():
    cmp = _compare()
    h.check("comparing three", cmp is not None and len(cmp.items) == 3)
    if cmp is None:
        return
    texts = {t["study"]: t["text"] for t in cmp.tag_list}
    third = texts.get(state["third"], "")
    h.check("the study solved again: no warning", "out of date" not in third, third)
    others = [texts.get(state[k], "") for k in ("first", "second")]
    h.check(
        "the two others say they are out of date",
        all("(out of date)" in t for t in others),
        others,
    )


def h_back():
    doc = s.doc()
    box = [o for o in doc.Objects if o.TypeId == "PartDesign::AdditiveBox"][0]
    box.Length = 100.0  # (while comparing: the two first studies' design again)
    doc.recompute()


h_back.wait_ms = 1500


def h_back_check():
    cmp = _compare()
    h.check("still comparing", cmp is not None)
    if cmp is None:
        return
    texts = {t["study"]: t["text"] for t in cmp.tag_list}
    h.check(
        "the marks follow the change: the 300 N study out of date now, the others not",
        "(out of date)" in texts.get(state["third"], "")
        and all("out of date" not in texts.get(state[k], "") for k in ("first", "second")),
        texts,
    )


def i_finish():
    s.big("Finish Results")


i_finish.wait_ms = 1000


def i_check():
    h.check("Finish Results ends Compare", _compare() is None)
    h.check("SETUP again", s.current_tab() == "sim_setup", s.current_tab())
    h.check("one view", _layout() == "Single View", _layout())
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
        a_turn,
        a_turn_check,
        a_turn_back_check,
        b_stress,
        b_check,
        b_actual_check,
        c_finish,
        c_check,
        d_third,
        d_again,
        d_tick,
        d_check_three,
        d_setup,
        d_check,
        e_results,
        e_compare,
        e_tick,
        e_single,
        e_check,
        f_no_split,
        f_go,
        f_check,
        f_finished,
        g_compare,
        g_go,
        g_solved,
        g_check,
        h_change,
        h_compare,
        h_tick_all,
        h_check,
        h_back,
        h_back_check,
        i_finish,
        i_check,
    ],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab with components, two materials, two designs and an empty one (builder
sim-results).

A  A component moved 20 mm up holds two bodies glued end to end (steel 0..50, aluminium 50..100),
   fixed at the steel end, 100 N down at the aluminium end. Its results are drawn where the
   component is (design coordinates); both bodies and the component are hidden on the view
   only while they show.
B  Results Details: one row per body, each with its own material and strength.
C  INSPECT > Reaction Force: the fixed end takes the whole 100 N.
D  DISPLAY > Loads and Constraints shows the setup's glyphs on the results, and hides them again.
E  INSPECT's Point Probes, Iso-surface and Solver Data are greyed with their reason.
F  Another design in front: the first one's results are put away (its bodies shown); its own
   results show on its RESULTS tab; back to the first design, its RESULTS tab shows its own.
G  An empty design in the SIMULATION workspace: no RESULTS tab, the results commands rest.
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s
from SciForgeTests.gui import widget_input as w

V = App.Vector
state = {}


def setup():
    from sciforge import components, material, simulation

    Gui.activateWorkbench("SciForgeWorkbench")
    other = App.newDocument("SimResOther")
    beam = s.beam(other)
    s.solve(s.cantilever_study(other, beam, 100.0))
    doc = App.newDocument("SimResParts")
    part = components.new_component(doc, "Arm")
    part.Placement = App.Placement(V(0, 0, 20), App.Rotation())
    steel = components.new_body_in(doc, part, "Steel")
    box = steel.newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 50.0, 10.0, 10.0
    alu = components.new_body_in(doc, part, "Alu")
    box2 = alu.newObject("PartDesign::AdditiveBox", "Box")
    box2.Length, box2.Width, box2.Height = 50.0, 10.0, 10.0
    box2.Placement = App.Placement(V(50, 0, 0), App.Rotation())
    doc.recompute()
    material.assign(steel, "steel")
    material.assign(alu, "aluminium")
    doc.recompute()
    study = simulation.create_study(doc)
    simulation.add_item(study, "constraint", "fixed", [(steel, s.face_at_x(steel, 0.0))])
    simulation.add_item(
        study,
        "load",
        "force",
        [(alu, s.face_at_x(alu, 100.0))],
        {"magnitude": 100.0, "direction": "vector", "vector": [0.0, 0.0, -1.0]},
    )
    s.solve(study)
    state.update(doc=doc.Name, other=other.Name, part=part.Name, steel=steel.Name, alu=alu.Name)
    h.fit()


def a_enter():
    s.workspace("Simulation")


def a_results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def a_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    if sess is None:
        return
    pts = sess.data.points
    zmin, zmax = float(pts[:, 2].min()), float(pts[:, 2].max())
    h.check(
        "drawn where the component is (z 20..30)",
        abs(zmin - 20) < 1e-6 and abs(zmax - 30) < 1e-6,
        (zmin, zmax),
    )
    doc = s.doc()
    for name in (state["steel"], state["alu"], state["part"]):
        vo = doc.getObject(name).ViewObject
        h.check(
            "%s hidden on the view only" % name,
            vo.SwitchNode.whichChild.getValue() == -1 and vo.Visibility,
        )


def b_details():
    s.big("Results Details")


def b_check():
    dialog = s.dialog("SciForgeSimDetails")
    h.check("Results Details open", dialog is not None)
    if dialog is None:
        return
    rows = {dialog.bodies.item(r, 0).text(): r for r in range(dialog.bodies.rowCount())}
    h.check("one row per body", sorted(rows) == ["Alu", "Steel"], sorted(rows))
    if "Alu" in rows and "Steel" in rows:
        h.check("steel's material", "Steel" in dialog.bodies.item(rows["Steel"], 1).text())
        h.check("aluminium's material", "Alumin" in dialog.bodies.item(rows["Alu"], 1).text())
        h.check(
            "steel's yield strength", dialog.bodies.item(rows["Steel"], 2).text().startswith("207")
        )
        h.check(
            "aluminium's yield strength",
            dialog.bodies.item(rows["Alu"], 2).text().startswith("95"),
            dialog.bodies.item(rows["Alu"], 2).text(),
        )
    dialog.close()


def c_reactions():
    s.menu("INSPECT", "Reaction Force")


def c_check():
    from PySide import QtWidgets

    dialog = s.dialog("SciForgeSimReactions")
    h.check("Reaction Force opens", dialog is not None)
    if dialog is None:
        return
    table = dialog.findChild(QtWidgets.QTableWidget, "SciForgeSimReactionTable")
    h.check("one constraint", table.rowCount() == 1, table.rowCount())
    if table.rowCount():
        h.check("Fixed 1", table.item(0, 0).text() == "Fixed 1", table.item(0, 0).text())
        total = float(table.item(0, 4).text())
        h.check("it takes the whole 100 N", abs(total - 100.0) < 1.0, total)
        fz = float(table.item(0, 3).text())
        h.check("upwards (against the load)", fz > 99.0, fz)
    dialog.close()


def d_loads():
    s.menu("DISPLAY", "Loads and Constraints")


def d_check():
    from sciforge import simulation_glyphs

    h.check("the setup's glyphs shown on the results", simulation_glyphs.visible())
    h.check("the menu ticks it", s.results_ui().loads_on())


def d_off():
    from PySide import QtCore

    h.move(QtCore.QPoint(60, 60))  # the pointer leaves the menu's place before it opens again
    s.menu("DISPLAY", "Loads and Constraints")


def d_off_check():
    from sciforge import simulation_glyphs

    h.check("the glyphs hidden again", not simulation_glyphs.visible())


def e_greyed():
    from SciForgeTests.gui import sketch_input

    group = sketch_input._group_widget("INSPECT")
    h.check("INSPECT group shown", group is not None)
    if group is None:
        return
    for label in ("Point Probes", "Iso-surface", "Solver Data"):
        path = sketch_input._find(group.menu, label)
        action = path[-1][1] if path else None
        h.check("%s greyed" % label, action is not None and not action.isEnabled())
        h.check(
            "%s says why" % label,
            action is not None and "Not in SciForge yet" in action.toolTip(),
            action.toolTip() if action is not None else None,
        )


def _tab_of(doc_name):
    tabs = h.document_tabs()
    label = App.getDocument(doc_name).Label
    for i in range(tabs.count()):
        if tabs.tabText(i).strip().startswith(label):
            return tabs, i
    return tabs, -1


def f_switch():
    tabs, i = _tab_of(state["other"])
    h.check("the other design's tab", i >= 0)
    if i >= 0:
        w.click(tabs, tabs.tabRect(i).center())


f_switch.wait_ms = 1200


def f_switch_check():
    h.check(
        "the other design in front",
        App.ActiveDocument.Name == state["other"],
        App.ActiveDocument.Name,
    )
    doc = App.getDocument(state["doc"])
    vo = doc.getObject(state["steel"]).ViewObject
    h.check("the first design's bodies shown again", vo.SwitchNode.whichChild.getValue() != -1)
    h.check("no results on the screen", s.session() is None)


def f_other_results():
    s.workspace("Simulation")


def f_other_tab():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def f_other_check():
    sess = s.session()
    h.check("the other design's results", sess is not None and sess.doc_name == state["other"])
    h.check("its beam hidden on the view", s.design_switches("Beam") == -1)


def f_back():
    tabs, i = _tab_of(state["doc"])
    if i >= 0:
        w.click(tabs, tabs.tabRect(i).center())


f_back.wait_ms = 1200


def f_back_results():
    other = App.getDocument(state["other"])
    beam = [o for o in other.Objects if o.TypeId == "PartDesign::Body"][0]
    h.check(
        "the other design's beam shown again",
        beam.ViewObject.SwitchNode.whichChild.getValue() != -1,
    )
    s.close_new_study_dialog()
    if s.current_tab() != "sim_results":
        s.click_tab("sim_results")


def f_back_check():
    sess = s.session()
    h.check(
        "the first design's own results again", sess is not None and sess.doc_name == state["doc"]
    )


def g_empty():
    App.newDocument("SimResEmpty")
    s.workspace("Simulation")


g_empty.wait_ms = 1200


def g_check():
    s.close_new_study_dialog()
    h.check("no RESULTS tab without results", not s.tab_visible("sim_results"))
    h.check("no results on the screen", s.session() is None)
    from sciforge import simulation_results_ui as ui

    h.check("the results commands rest", not ui.AnimateCommand().IsActive())


h.run(
    "simres_workspace",
    [
        setup,
        a_enter,
        a_results,
        a_check,
        b_details,
        b_check,
        c_reactions,
        c_check,
        d_loads,
        d_check,
        d_off,
        d_off_check,
        e_greyed,
        f_switch,
        f_switch_check,
        f_other_results,
        f_other_tab,
        f_other_check,
        f_back,
        f_back_results,
        f_back_check,
        g_empty,
        g_check,
    ],
)

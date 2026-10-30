# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab with components, two materials, two designs and an empty one (builder
sim-results).

A  A component moved 20 mm up holds two bodies glued end to end (steel 0..50, aluminium 50..100),
   fixed at the steel end, 100 N down at the aluminium end. Its results are drawn where the
   component is (design coordinates); both bodies, the component and the mesh SETUP's Show
   Mesh drew are hidden on the view only while they show.
A2 The browser's eye of the aluminium body off: its results go (only the steel half drawn, its
   end face at x = 50 now outside, the min and max tags on the steel), the same colour scale;
   on again: the whole arm.
B  Results Details: one row per body, each with its own material and strength; the sentence
   names the body with the lowest safety factor.
C  INSPECT > Reaction Force: the fixed end takes the whole 100 N; while it is open a tag on the
   fixed face (x = 0) says so; Close takes the tag away.
D  DISPLAY > Loads and Constraints shows the setup's glyphs on the results, and hides them again.
E  INSPECT > Point Probes in design coordinates: a click on the steel's top face puts a probe
   at z = 30 (the component is 20 mm up); its Z typed as 5 (the body's own height) is outside
   the part; 25 (the middle of the height, the neutral axis) is inside, where the bending
   stress is far below the top face's. INSPECT > Solver Data lists the mesh of both bodies.
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


def a_mesh():
    s.close_new_study_dialog()
    # SETUP > DISPLAY > Show Mesh (sim-ui): the solve's mesh drawn on the model
    s.menu("DISPLAY", "Show Mesh")


def a_results():
    from sciforge import simulation_solve_dialog as solve_dialog

    h.check("the mesh shows on SETUP", solve_dialog.mesh_shown())
    mesh = solve_dialog.mesh_object(s.study())
    state["mesh"] = mesh.Name if mesh is not None else None
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
    if state.get("mesh"):
        vo = doc.getObject(state["mesh"]).ViewObject
        h.check("the SETUP mesh hidden on the view too", vo.SwitchNode.whichChild.getValue() == -1)
    for name in (state["steel"], state["alu"], state["part"]):
        vo = doc.getObject(name).ViewObject
        h.check(
            "%s hidden on the view only" % name,
            vo.SwitchNode.whichChild.getValue() == -1 and vo.Visibility,
        )


def _click_eye(label):
    from SciForgeTests.gui import timeline_input as ti

    tree = ti.tree()
    item = tree.row(label)
    h.check("browser row %s" % label, item is not None, tree.labels())
    if item is None:
        return
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    tree.scrollToItem(item)
    w.click(tree.viewport(), tree.eye_point(item))


def a2_hide():
    state["legend_hi"] = s.session().legend_info["hi"]
    _click_eye("Alu")


def a2_hide_check():
    sess = s.session()
    xs = sess.data.points[sess.display.nodes][:, 0]
    h.check(
        "the aluminium body's eye off", not s.doc().getObject(state["alu"]).ViewObject.Visibility
    )
    h.check(
        "only the steel half drawn",
        len(xs) and float(xs.max()) <= 50.0 + 1e-6,
        float(xs.max()) if len(xs) else None,
    )
    h.check("the steel's end face at x = 50 drawn", len(xs) and (abs(xs - 50.0) < 1e-6).any())
    h.check("the same colour scale", sess.legend_info["hi"] == state["legend_hi"])
    ends = [t for t in s.tags() if t["kind"] in ("min", "max")]
    h.check(
        "the min and max tags on the steel (none where the hidden body is)",
        len(ends) == 2 and all(float(sess.data.points[t["node"]][0]) <= 50.0 + 1e-6 for t in ends),
        [(t["kind"], float(sess.data.points[t["node"]][0])) for t in ends],
    )
    _click_eye("Alu")


def a2_show_check():
    sess = s.session()
    xs = sess.data.points[sess.display.nodes][:, 0]
    h.check("the eye on again: the whole arm", len(xs) and abs(float(xs.max()) - 100.0) < 1e-6)
    h.check(
        "the aluminium body still hidden on the view",
        s.doc().getObject(state["alu"]).ViewObject.SwitchNode.whichChild.getValue() == -1,
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
        core = s.results_core()
        lower, upper = s.session().targets
        for name in ("Steel", "Alu"):
            cell = dialog.bodies.item(rows[name], 4)
            band = core.target_band(float(cell.text()), lower, upper)
            want = tuple(round(c, 2) for c in core.BAND_COLOURS[band])
            got = cell.background().color()
            h.check(
                "%s's lowest safety factor in its band's colour (%s)" % (name, band),
                tuple(round(c, 2) for c in (got.redF(), got.greenF(), got.blueF())) == want,
                (got.name(), band),
            )
        values = {n: float(dialog.bodies.item(rows[n], 4).text()) for n in ("Steel", "Alu")}
        head = dialog.headline.text()
        named = [n for n in values if (", in %s " % n) in head]
        h.check(
            "the sentence names the weakest body",
            len(named) == 1 and values[named[0]] == min(values.values()),
            (head, values),
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
    tags = s.tags("reaction")
    h.check(
        "a tag on the fixed face",
        len(tags) == 1
        and tags[0]["text"].startswith("Fixed 1: ")
        and tags[0]["text"].endswith(" N"),
        tags,
    )
    if tags:
        h.check(
            "at x = 0, where the component is", abs(tags[0]["point"][0]) < 1e-6, tags[0]["point"]
        )
        h.check("z: the component's middle height", abs(tags[0]["point"][2] - 25.0) < 1e-6)
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReactionsClose"))


def c_closed_check():
    h.check("Close: the tag gone", not s.tags("reaction"))
    h.check("the window closed", s.dialog("SciForgeSimReactions") is None)


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


def e_points():
    s.menu("INSPECT", "Point Probes")


def _point_table():
    from PySide import QtWidgets

    return s.panel_field("SciForgeSimPointTable", QtWidgets.QTableWidget)


def e_click_top():
    sess = s.session()
    h.click(V(*sess.point_place({"at": (25.0, 5.0, 30.0)})))


def e_click_check():
    sess = s.session()
    h.check("a probe on the steel's top face", len(sess.points) == 1, sess.points)
    if not sess.points:
        return
    at = sess.points[0]["at"]
    h.check("at z = 30 (design coordinates)", abs(at[2] - 30.0) < 1e-4, at)
    state["vm_top"] = sess.point_value(sess.points[0], "von_mises")
    s.edit_cell(_point_table(), 0, 3, "5")


def e_outside_check():
    sess = s.session()
    h.check("z = 5 is outside the part", sess.point_value(sess.points[0]) is None)
    s.edit_cell(_point_table(), 0, 3, "25")


def e_inside_check():
    sess = s.session()
    mid = sess.point_value(sess.points[0], "von_mises")
    h.check(
        "z = 25 inside: the neutral axis, far below the top face's stress",
        mid is not None and state.get("vm_top") and mid < 0.3 * state["vm_top"],
        (mid, state.get("vm_top")),
    )
    h.task_button("Close")


def e_solver():
    s.menu("INSPECT", "Solver Data")


def e_solver_check():
    from PySide import QtWidgets

    dialog = s.dialog("SciForgeSimSolverData")
    h.check("Solver Data open", dialog is not None)
    if dialog is None:
        return
    rows = s.tree_rows(dialog.findChild(QtWidgets.QTreeWidget, "SciForgeSimSolverTree"))
    nodes = int(s.summary().get("mesh", {}).get("nodes", 0))
    h.check(
        "the mesh of both bodies",
        rows.get("Mesh", {}).get("Nodes") == "{:,}".format(nodes),
        rows.get("Mesh"),
    )
    dialog.close()


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
        a_mesh,
        a_results,
        a_check,
        a2_hide,
        a2_hide_check,
        a2_show_check,
        b_details,
        b_check,
        c_reactions,
        c_check,
        c_closed_check,
        d_loads,
        d_check,
        d_off,
        d_off_check,
        e_points,
        e_click_top,
        e_click_check,
        e_outside_check,
        e_inside_check,
        e_solver,
        e_solver_check,
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
    paced_by="state",
)

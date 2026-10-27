# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION workspace's main path with real clicks (builder sim-ui): an L bracket fixed at
its two holes with a force on its arm, solved on this computer.

A  Workspace > Simulation on a design without a study: the SETUP / RESULTS tabs replace the
   design's, the workspace button says SIMULATION, the timeline steps aside, and Fusion's New
   Study dialog opens by itself: every study type listed, Static Stress available, the others
   greyed with "Not in SciForge yet".
B  Create Study: "Study 1 - Static Stress" is the active study; the browser shows Fusion's study
   tree (Study Materials, Load Case 1 with Constraints and Loads, Contacts, Mesh); the
   Pre-check light is red (nothing holds the model). The Pre-check list says so and offers
   Repair (Solve greyed).
C  Repair: Structural Constraints opens (told why): Fixed by default; a click on each hole
   wall picks it (the preview draws its glyphs); OK keeps "Fixed 1" on the two hole faces; its
   glyphs are drawn.
D  Structural Loads: Force (Normal) by default; a click on the arm's top face; 250 N typed; OK
   keeps "Force 1".
E  Pre-check: the light turns green; its list says nothing is missing.
F  Solve: the Solve dialog ticks the study ("Solve 1 Study") and says it solves on this
   computer; the progress shows the stages; the solve ends with results (displacement and
   stress), handed over to the RESULTS tab; the Results row shows in the browser.
G  Workspace > Design: the design's tabs, the timeline and the design browser come back; no
   study, constraint, load or run is listed there or in the timeline.
H  Workspace > Simulation again: no New Study dialog (the study is there), the same active
   study, its tree in the browser, the glyphs drawn again.
"""

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


# -- A ------------------------------------------------------------------------------------------
def a_enter():
    state["timeline_before"] = s.timeline_visible()
    s.workspace("Simulation")


def a_check():
    h.check("SETUP tab shown", s.tab_visible("sim_setup"))
    h.check("SETUP tab selected", s.current_tab() == "sim_setup", s.current_tab())
    h.check("SOLID tab hidden", not s.tab_visible("solid"))
    h.check(
        "workspace button says SIMULATION", "SIMULATION" in s.workspace_text(), s.workspace_text()
    )
    h.check("the timeline was shown in DESIGN", state["timeline_before"])
    h.check("no timeline in SIMULATION", not s.timeline_visible())
    dialog = s.new_study_dialog()
    h.check("New Study opens by itself", dialog is not None)
    if dialog is None:
        return
    types = dialog.types
    names = [types.item(i).text() for i in range(types.count())]
    h.check("every Fusion study type listed", len(names) >= 10, names)
    from PySide import QtCore

    enabled = [
        types.item(i).text()
        for i in range(types.count())
        if types.item(i).flags() & QtCore.Qt.ItemIsEnabled
    ]
    h.check("only Static Stress available", enabled == ["Static Stress"], enabled)
    tip = types.item(1).toolTip()
    h.check("a greyed type says it is not in SciForge yet", "Not in SciForge yet" in tip, tip)
    h.check("Create Study is enabled for Static Stress", dialog.create_button.isEnabled())


# -- B ------------------------------------------------------------------------------------------
def b_create():
    dialog = s.new_study_dialog()
    s.click_widget(dialog.create_button if dialog is not None else None)


def b_check():
    h.check("the dialog closed", s.new_study_dialog() is None)
    studies = s.studies()
    h.check("one study made", len(studies) == 1, [x.Label for x in studies])
    study = s.active_study()
    h.check(
        "it is the active study, named like Fusion's",
        study is not None and study.Label == "Study 1 - Static Stress",
        study.Label if study else None,
    )
    labels = s.browser_labels()
    for row in (
        "Simulation Model",
        "Study 1 - Static Stress",
        "Study Materials",
        "Load Case 1",
        "Constraints",
        "Loads",
        "Contacts",
        "Mesh",
    ):
        h.check("browser row %s" % row, row in labels, labels)
    h.check("no design folders in the SIMULATION browser", "Sketches" not in labels, labels)
    h.check("Pre-check light red (nothing holds it)", s.light() == "red", s.light())
    button = s.precheck_button()
    h.check(
        "the Pre-check button shows it",
        button is not None and button.property("simLight") == "red",
        button.property("simLight") if button is not None else None,
    )


def b_precheck():
    h.ribbon("Pre-check")


def b_repair():
    dialog = s.popup_named("SciForgeSimPrecheck")
    if not h.check("the Pre-check list opened", dialog is not None):
        return
    texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
    h.check("it says nothing holds the model", any("Nothing holds" in x for x in texts), texts)
    h.check("Solve greyed", not dialog.solve.isEnabled())
    h.check("Repair offered", dialog.repair is not None and dialog.repair.isVisible())
    s.click_widget(dialog.repair)


# -- C ------------------------------------------------------------------------------------------
def c_pick_holes():
    h.check("the Pre-check list closed", s.popup_named("SciForgeSimPrecheck") is None)
    p = s.item_panel()
    h.check("Repair opened Structural Constraints", p is not None and p.category == "constraint")
    if p is None:
        return
    h.check("told why", "Nothing holds the model" in s.told(), s.told())
    h.check("Fixed by default", p.type_box.currentText() == "Fixed", p.type_box.currentText())
    bracket = s.body()
    holes = s.hole_faces(bracket)
    h.check("the bracket has two hole walls", len(holes) == 2, holes)
    state["holes"] = holes
    for face in holes:
        s.click_face(bracket, face)


def c_check_picks():
    p = s.item_panel()
    if p is None:
        h.check("dialog still open", False)
        return
    picked = sorted(sub for _b, sub in p.picks)
    h.check("both hole walls picked", picked == sorted(state.get("holes", [])), picked)
    h.check("the preview draws glyphs", s.preview_count() > 0, s.preview_count())
    s.ok()


def c_check():
    found = s.items("constraint")
    h.check("Fixed 1 made", [i.Label for i in found] == ["Fixed 1"], [i.Label for i in found])
    if found:
        subs = sorted(sub for _o, sub in s.sim()._picks(found[0].References))
        h.check("on the two hole walls", subs == sorted(state.get("holes", [])), subs)
        h.check(
            "its glyphs are drawn", s.glyph_counts().get(found[0].Name, 0) > 0, s.glyph_counts()
        )
    h.check("the dialog closed", s.item_panel() is None)
    h.check("Fixed 1 in the browser", "Fixed 1" in s.browser_labels())


# -- D ------------------------------------------------------------------------------------------
def d_loads():
    h.ribbon("Structural Loads")


def d_pick():
    p = s.item_panel()
    h.check("Structural Loads opened", p is not None)
    if p is None:
        return
    h.check("Force by default", p.type_box.currentText() == "Force", p.type_box.currentText())
    direction = s.panel_field("SciForgeSim_direction")
    h.check(
        "Direction Type Normal by default",
        direction is not None and direction.currentText() == "Normal",
    )
    bracket = s.body()
    state["arm_top"] = s.arm_top(bracket)
    s.click_face(bracket, state["arm_top"])
    s.type_in("SciForgeSim_magnitude", "250 N")


def d_ok():
    p = s.item_panel()
    if p is not None:
        h.check("arm top picked", [sub for _b, sub in p.picks] == [state.get("arm_top")], p.picks)
    s.ok()


def d_check():
    found = s.items("load")
    h.check("Force 1 made", [i.Label for i in found] == ["Force 1"], [i.Label for i in found])
    if found:
        data = s.sim().item_data(found[0])
        h.check("250 N", abs(data["options"]["magnitude"] - 250.0) < 1e-9, data)
        h.check("along the normal", data["options"]["direction"] == "normal", data)
    h.check("Force 1 in the browser", "Force 1" in s.browser_labels())


# -- E ------------------------------------------------------------------------------------------
def e_precheck():
    h.ribbon("Pre-check")


def e_check():
    h.check("Pre-check light green", s.light() == "green", s.light())
    dialog = s.popup_named("SciForgeSimPrecheck")
    h.check("the Pre-check list opened", dialog is not None)
    if dialog is not None:
        h.check("ready to solve", dialog.state == "green", dialog.checks)
        s.close_popup("SciForgeSimPrecheck")


# -- F ------------------------------------------------------------------------------------------
def f_solve():
    h.ribbon("Solve")


def f_dialog():
    dialog = s.solve_dialog()
    h.check("the Solve dialog opened", dialog is not None)
    if dialog is None:
        return
    h.check("its button names the count", dialog.go.text() == "Solve 1 Study", dialog.go.text())
    where = dialog.findChild(type(dialog.message), "SciForgeSimSolveWhere")
    h.check(
        "it says it solves on this computer", where is not None and "this computer" in where.text()
    )
    s.click_widget(dialog.go)


def f_progress():
    status = s.status_dialog()
    h.check("the progress window shows", status is not None and status.isVisible())
    if status is not None:
        h.check("it lists the stages", status.stages.count() == 5, status.stages.count())


def f_check():
    study = s.active_study()
    from sciforge import simulation_solve_dialog

    results = simulation_solve_dialog.last_results()
    h.check("the solve ended done", results.get(study.Name, ("?",))[0] == "done", results)
    summary = s.sim().summary(study)
    stats = summary.get("stats", {})
    h.check("results: the arm moves", stats.get("displacement", {}).get("max", 0) > 0, stats)
    h.check("results: stress", stats.get("von_mises", {}).get("max", 0) > 0, stats)
    h.check("not out of date", not s.sim().out_of_date(study))
    h.check("the RESULTS tab shows", s.current_tab() == "sim_results", s.current_tab())
    h.check("Results row in the browser", "Results" in s.browser_labels(), s.browser_labels())
    h.check(
        "nothing of the solve in the undo history",
        "Solve" not in " ".join(App.ActiveDocument.UndoNames),
        App.ActiveDocument.UndoNames,
    )


# -- G ------------------------------------------------------------------------------------------
def g_leave():
    s.close_popup("SciForgeSimJobStatus")
    s.workspace("Design")


def g_check():
    h.check(
        "SOLID tab back", s.tab_visible("solid") and s.current_tab() == "solid", s.current_tab()
    )
    h.check("SETUP tab hidden", not s.tab_visible("sim_setup"))
    h.check("workspace button says DESIGN", "DESIGN" in s.workspace_text(), s.workspace_text())
    h.check("the timeline is back", s.timeline_visible())
    labels = s.browser_labels()
    h.check("the design browser is back", "Bodies" in labels, labels)
    sim_rows = (
        "Study 1 - Static Stress",
        "Fixed 1",
        "Force 1",
        "Study 1 - Static Stress run",
        "Simulation Model",
        "Load Case 1",
        "Study Materials",
    )
    leaked = [x for x in labels if x in sim_rows or x.startswith(("SimRun", "SimModel", "SimMesh"))]
    h.check("no study, item or run in the design browser", not leaked, leaked)
    from SciForgeTests.gui import dialog_input as ui

    titles = ui.timeline_titles()
    leaked = [t for t in titles if "Sim" in t or "Study" in t or "Fixed" in t or "Force" in t]
    h.check("no study, item or run in the timeline", not leaked, titles)


# -- H ------------------------------------------------------------------------------------------
def h_enter_again():
    state["active"] = s.active_study().Name if s.active_study() else None
    s.workspace("Simulation")


def h_check():
    h.check("no New Study dialog this time", s.new_study_dialog() is None)
    study = s.active_study()
    h.check("the same active study", study is not None and study.Name == state["active"])
    h.check("SETUP shown again", s.tab_visible("sim_setup"))
    labels = s.browser_labels()
    h.check("the study tree is back", "Fixed 1" in labels and "Force 1" in labels, labels)
    h.check("glyphs drawn again", len(s.glyph_counts()) == 2, s.glyph_counts())


h.run(
    "sim_setup_bracket",
    [
        s.new_bracket("SimBracket"),
        a_enter,
        a_check,
        b_create,
        b_check,
        b_precheck,
        b_repair,
        c_pick_holes,
        c_check_picks,
        c_check,
        d_loads,
        d_pick,
        d_ok,
        d_check,
        e_precheck,
        e_check,
        f_solve,
        f_dialog,
        f_progress,
        s.wait_solved(),
        f_check,
        g_leave,
        g_check,
        h_enter_again,
        h_check,
    ],
)

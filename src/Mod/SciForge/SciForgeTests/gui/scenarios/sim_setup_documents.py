# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two bodies glued, and the workspace across designs (builder sim-ui), with real clicks.

A  A base block with a smaller block standing on it (two bodies that touch). Workspace >
   Simulation, Create Study.
B  CONTACTS > Automatic Contacts > Generate: one bonded pair (Base and Top, gap 0); OK.
   Contact Manager lists it.
C  DISPLAY > DOF View (on) with nothing held: both bodies free (selected, named), arrows on
   them (glued, they move as one: three slides and three turns). A Fixed on a face of the base:
   the arrows go (the top is held through the base). DOF View again: off.
D  Right-click Top in the browser > Exclude from Study: greyed, out of the study; Include in
   Study brings it back.
E  A force on the top block's top face; Solve: done, with a result for each body (glued).
F  A second design in DESIGN: its tab shows SOLID and the timeline; back to the first
   design's tab: SIMULATION again (each design keeps its workspace), its study tree back.
G  The first design saved and closed: the second one shows DESIGN; reopened: it opens in
   DESIGN; Workspace > Simulation: no New Study (the study is in the file), its constraint,
   load and results are back.
H  Settings > General: "Keep the results in the design file" unticked; saved, closed and
   reopened: the summary is there, the coloured results are not, and the Results row says
   only the summary is kept.
"""

import os
import tempfile

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

state = {}


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimGlued")
    s.block(doc, "Base", (40, 20, 10), (0, 0, 0))
    s.block(doc, "Top", (20, 20, 10), (10, 0, 10))
    h.fit()
    state["doc"] = doc.Name


def a_enter():
    s.workspace("Simulation")


def a_create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


# -- B ------------------------------------------------------------------------------------------
def b_contacts():
    h.check("study made", len(s.studies()) == 1)
    h.ribbon("Automatic Contacts")


def b_generate():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.ContactsPanel.last
    if not h.check("Automatic Contacts opened", p is not None and not p._closed):
        return
    s.click_widget(p.generate)
    rows = [
        [p.table.item(r, c).text() for c in range(p.table.columnCount())]
        for r in range(p.table.rowCount())
    ]
    h.check("one bonded pair", len(rows) == 1, rows)
    h.check("Base with Top", rows and sorted(rows[0][:2]) == ["Base", "Top"], rows)
    h.check("touching (gap 0)", rows and rows[0][2].startswith("0"), rows)
    s.ok()


def b_manager():
    s.menu_item("CONTACTS", "Contact Manager")


def b_check():
    from PySide import QtWidgets

    dialog = s.popup_named("SciForgeSimContactManager")
    if h.check("Contact Manager", dialog is not None):
        table = dialog.findChild(QtWidgets.QTableWidget)
        h.check("one bonded pair listed", table.rowCount() == 1, table.rowCount())
        h.check("bonded", "Bonded" in table.item(0, 2).text(), table.item(0, 2).text())
        s.close_popup("SciForgeSimContactManager")


# -- C ------------------------------------------------------------------------------------------
def c_dof():
    s.menu_item("DISPLAY", "DOF View")


def c_dof_check():
    import FreeCADGui as Gui
    from sciforge import simulation_ui

    names = sorted(x.Object.Label for x in Gui.Selection.getSelectionEx())
    h.check("both bodies free and selected", names == ["Base", "Top"], names)
    h.check("DOF View says which", "not held yet" in s.tooltip_text(), s.tooltip_text())
    h.check("DOF View is on", simulation_ui.dof_on())
    h.check(
        "arrows for three slides and three turns",
        s.glyph_counts().get("dof") == 6,
        s.glyph_counts(),
    )
    Gui.Selection.clearSelection()
    h.ribbon("Structural Constraints")


def c_fix_base():
    base = s.body("Base")
    face = s.visible_face(base, s.side_faces(base))
    state["base_face"] = face
    h.check("a face of the base can be clicked", face is not None)
    if face:
        s.click_face(base, face)
    s.ok()


def c_dof_again():
    h.check("Fixed 1 on the base", [i.Label for i in s.items()] == ["Fixed 1"])
    h.check(
        "nothing free now: the arrows went",
        s.glyph_counts().get("dof", 0) == 0,
        s.glyph_counts(),
    )
    s.menu_item("DISPLAY", "DOF View")


def c_check():
    from sciforge import simulation_ui

    h.check("DOF View off", not simulation_ui.dof_on())
    h.check("it says so", "DOF View off" in s.tooltip_text(), s.tooltip_text())
    h.check("no arrows", "dof" not in s.glyph_counts(), s.glyph_counts())


# -- D ------------------------------------------------------------------------------------------
def d_exclude():
    s.right_click_row("Top", "Exclude from Study")


def d_check():
    bodies = [b.Label for b in s.sim().study_bodies(s.active_study())]
    h.check("Top out of the study", bodies == ["Base"], bodies)
    node = s.row_node("Top")
    h.check("its row greyed", node is not None and node["status"] == "suppressed", node)
    s.right_click_row("Top", "Include in Study")


def d_back():
    bodies = sorted(b.Label for b in s.sim().study_bodies(s.active_study()))
    h.check("Top back in the study", bodies == ["Base", "Top"], bodies)


# -- E ------------------------------------------------------------------------------------------
def e_load():
    h.ribbon("Structural Loads")


def e_pick():
    top = s.body("Top")
    s.click_face(top, s.top_face(top))
    s.type_in("SciForgeSim_magnitude", "500 N")
    s.ok()


def e_solve():
    h.check("Force 1 made", [i.Label for i in s.items("load")] == ["Force 1"])
    h.ribbon("Solve")


def e_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def e_check():
    summary = s.sim().summary(s.active_study())
    h.check("solved", bool(summary))
    h.check(
        "a result for each glued body",
        sorted(summary.get("bodies", {})) == ["Base", "Top"],
        summary.get("bodies"),
    )
    s.close_popup("SciForgeSimJobStatus")


# -- F ------------------------------------------------------------------------------------------
def f_second_design():
    App.newDocument("SimOther")
    h.fit()


def f_check_second():
    h.check(
        "the new design shows DESIGN", s.tab_visible("solid") and not s.tab_visible("sim_setup")
    )
    h.check("its timeline", s.timeline_visible())
    s.click_doc_tab("SimGlued")


def f_check_first():
    h.check(
        "the first design is in front",
        App.ActiveDocument.Name == state["doc"],
        App.ActiveDocument.Name,
    )
    h.check("SIMULATION again", s.tab_visible("sim_setup") and not s.tab_visible("solid"))
    h.check("no timeline", not s.timeline_visible())
    h.check("its study tree", "Fixed 1" in s.browser_labels(), s.browser_labels())


# -- G ------------------------------------------------------------------------------------------
def g_save_close():
    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-sim-"), "sim_glued.FCStd")
    state["path"] = path
    App.ActiveDocument.saveAs(path)
    h.check("saved", os.path.isfile(path), path)
    App.closeDocument(App.ActiveDocument.Name)


def g_after_close():
    h.check(
        "the other design is in front",
        App.ActiveDocument is not None and App.ActiveDocument.Label.startswith("SimOther"),
    )
    h.check("it shows DESIGN", s.tab_visible("solid") and not s.tab_visible("sim_setup"))
    App.openDocument(state["path"])
    h.fit()


def g_reopened():
    from SciForgeTests.gui import dialog_input as ui

    h.check("reopened in DESIGN", s.tab_visible("solid") and not s.tab_visible("sim_setup"))
    labels = s.browser_labels()
    leaked = [
        x
        for x in labels
        if x.startswith(("Study 1", "Fixed 1", "Force 1", "SimRun", "SimModel", "SimMesh"))
        or x in ("Simulation Model", "Load Case 1", "Study Materials")
    ]
    h.check("reopened: no study, item or run in the design browser", not leaked, leaked)
    titles = ui.timeline_titles()
    leaked = [x for x in titles if "Sim" in x or "Study" in x or "Fixed" in x or "Force" in x]
    h.check("reopened: none in the timeline", not leaked, titles)
    s.workspace("Simulation")


def g_check():
    h.check("no New Study (the study is in the file)", s.new_study_dialog() is None)
    study = s.active_study()
    h.check("the study is back", study is not None and study.Label == "Study 1 - Static Stress")
    labels = sorted(i.Label for i in s.items())
    h.check("its constraint and load", labels == ["Fixed 1", "Force 1"], labels)
    h.check("its results", bool(s.sim().summary(study)) and s.sim().results(study) is not None)
    h.check("Results in the browser", "Results" in s.browser_labels(), s.browser_labels())
    s.menu_item("MANAGE", "Settings")


# -- H ------------------------------------------------------------------------------------------
def h_keep_off():
    from sciforge import simulation_dialogs

    p = simulation_dialogs.SettingsPanel.last
    if not h.check("Study Settings opened", p is not None and not p._closed):
        return
    p.tabs.setCurrentIndex(0)
    if p.tabs.keep.isChecked():
        s.click_widget(p.tabs.keep)
    h.check("Keep the results in the design file unticked", not p.tabs.keep.isChecked())
    s.ok()


def h_save_close():
    h.check(
        "kept off",
        s.sim().settings(s.active_study()).get("keep_results") is False,
        s.sim().settings(s.active_study()),
    )
    App.ActiveDocument.save()
    App.closeDocument(App.ActiveDocument.Name)


def h_reopen():
    App.openDocument(state["path"])
    h.fit()


def h_enter():
    s.workspace("Simulation")


def h_check():
    study = s.active_study()
    h.check("the summary kept", bool(s.sim().summary(study)))
    h.check("the coloured results not kept in the file", s.sim().results(study) is None)
    labels = s.browser_labels()
    h.check("the results are up to date", "Results" in labels, labels)
    h.check("not out of date", not s.sim().out_of_date(study))
    tip = (s.row_node("Results") or {}).get("tip", "")
    h.check("the Results row says only the summary is kept", "Only the summary" in tip, tip)


h.run(
    "sim_setup_documents",
    [
        setup,
        a_enter,
        a_create,
        b_contacts,
        b_generate,
        b_manager,
        b_check,
        c_dof,
        c_dof_check,
        c_fix_base,
        c_dof_again,
        c_check,
        d_exclude,
        d_check,
        d_back,
        e_load,
        e_pick,
        e_solve,
        e_go,
        s.wait_solved(),
        e_check,
        f_second_design,
        f_check_second,
        f_check_first,
        g_save_close,
        g_after_close,
        g_reopened,
        g_check,
        h_keep_off,
        h_save_close,
        h_reopen,
        h_enter,
        h_check,
    ],
)

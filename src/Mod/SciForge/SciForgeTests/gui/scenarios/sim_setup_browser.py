# SPDX-License-Identifier: LGPL-2.1-or-later
"""The study tree in the SIMULATION browser with real clicks (builder sim-ui): edit a load from
the browser and solve again, the out-of-date mark, suppress, rename, delete, Clone Study,
activate a study, delete a study. The bracket's study (Fixed at the holes, Force on the arm) is
made by script; everything after that is clicks and keys.

A  The study solved (SOLVE > Solve); the Results row shows.
B  Right-click Force 1 > Edit Load: its dialog opens with its face picked and 250 N; 500 N
   typed, OK. The results are now out of date: the row says so (yellow).
C  Right-click Results > Solve: solved again, the Results row is up to date; the progress
   window lists the earlier solve too.
D  Double-click Fixed 1: Edit Constraint opens on its two holes; Cancel changes nothing.
E  Right-click Force 1 > Suppress: greyed, its glyphs gone, the pre-check turns yellow (nothing
   pushes); Unsuppress brings it back.
F  F2 on Force 1: renamed "Arm Push"; Undo: "Force 1" again.
G  Delete on Fixed 1: gone (the pre-check turns red); Undo: back.
H  Right-click the study > Clone Study: "Study 2 - Static Stress", active, with its own copies
   of the constraint and the load and no results; double-click Study 1: active again; right-
   click Study 2 > Delete: gone.
I  The design changes (the plate made thicker): the Results row of Study 1 says out of date.
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    s.new_bracket("SimBrowser")()
    sim = s.sim()
    doc = App.ActiveDocument
    body = s.body()
    study = sim.create_study(doc)
    holes = s.hole_faces(body)
    sim.add_item(study, "constraint", "fixed", [(body, holes)])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 250.0})
    doc.recompute()
    state["study"] = study.Name


def enter():
    s.workspace("Simulation")


def study():
    return App.ActiveDocument.getObject(state["study"])


def item(label):
    for obj in s.sim().items(study()):
        if obj.Label == label:
            return obj
    return None


# -- A ------------------------------------------------------------------------------------------
def a_solve():
    h.check("no New Study dialog (a study exists)", s.new_study_dialog() is None)
    h.ribbon("Solve")


def a_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def a_check():
    h.check("solved", bool(s.sim().summary(study())), s.sim().summary(study()))
    labels = s.browser_labels()
    h.check("Results row", "Results" in labels, labels)
    s.close_popup("SciForgeSimJobStatus")


# -- B ------------------------------------------------------------------------------------------
def b_edit():
    s.right_click_row("Force 1", "Edit Load")


def b_type():
    p = s.item_panel()
    h.check("Edit Load opened", p is not None)
    if p is None:
        return
    h.check("its face is picked", len(p.picks) == 1, p.picks)
    field = s.panel_field("SciForgeSim_magnitude", QtWidgets.QLineEdit)
    h.check(
        "250 N shown",
        field is not None and field.text() == "250 N",
        field.text() if field else None,
    )
    h.check("the type cannot change while editing", not p.type_box.isEnabled())
    s.type_in("SciForgeSim_magnitude", "500")
    s.ok()


def b_check():
    data = s.sim().item_data(item("Force 1"))
    h.check("500 N kept", abs(data["options"]["magnitude"] - 500.0) < 1e-9, data)
    h.check("results out of date", s.sim().out_of_date(study()))
    labels = s.browser_labels()
    h.check("the Results row says out of date", "Results (out of date)" in labels, labels)
    node = s.row_node("Results (out of date)")
    h.check("marked yellow", node is not None and node["status"] == "warning", node)


# -- C ------------------------------------------------------------------------------------------
def c_solve_again():
    s.right_click_row("Results (out of date)", "Solve")


def c_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog again", dialog is not None):
        s.click_widget(dialog.go)


def c_check():
    h.check("up to date again", not s.sim().out_of_date(study()))
    h.check("Results row plain again", "Results" in s.browser_labels(), s.browser_labels())
    status = s.status_dialog()
    rows = [status.studies.item(i).text() for i in range(status.studies.count())] if status else []
    h.check(
        "the progress lists the earlier solve too (Job Status)",
        any(
            r.startswith("Earlier, ") and r.endswith("Study 1 - Static Stress: Done") for r in rows
        ),
        rows,
    )
    s.close_popup("SciForgeSimJobStatus")


# -- D ------------------------------------------------------------------------------------------
def d_double_click():
    s.double_click_row("Fixed 1")


def d_cancel():
    p = s.item_panel()
    h.check("Edit Constraint opened by a double-click", p is not None)
    if p is None:
        return
    h.check("its two holes picked", len(p.picks) == 2, p.picks)
    h.check("Fixed shown", p.type_box.currentText() == "Fixed")
    state["undo"] = list(App.ActiveDocument.UndoNames)
    s.cancel()


def d_check():
    h.check("closed", s.item_panel() is None)
    h.check("nothing changed", list(App.ActiveDocument.UndoNames) == state["undo"])


# -- E ------------------------------------------------------------------------------------------
def e_suppress():
    s.right_click_row("Force 1", "Suppress")


def e_check():
    force = item("Force 1")
    h.check("suppressed", force is not None and force.Suppressed)
    node = s.row_node("Force 1")
    h.check("its row greyed", node is not None and node["status"] == "suppressed", node)
    h.check("its glyphs gone", force.Name not in s.glyph_counts(), s.glyph_counts())
    h.check("pre-check yellow: nothing pushes", s.light() == "yellow", s.light())
    entries = s.menu_entries("Force 1")
    h.check("its menu offers Unsuppress", "Unsuppress" in entries, entries)
    s.right_click_row("Force 1", "Unsuppress")


def e_back():
    force = item("Force 1")
    h.check("unsuppressed", force is not None and not force.Suppressed)
    h.check("its glyphs back", force.Name in s.glyph_counts(), s.glyph_counts())


# -- F ------------------------------------------------------------------------------------------
def f_rename():
    s.click_row("Force 1")
    w.key(s.browser(), QtCore.Qt.Key_F2)


def f_type():
    field = s.browser().findChild(QtWidgets.QLineEdit)
    if not h.check("rename field open", field is not None):
        return
    field.selectAll()
    w.type_text(field, "Arm Push")
    w.key(field, QtCore.Qt.Key_Return)


def f_check():
    h.check("renamed", item("Arm Push") is not None, [i.Label for i in s.items()])
    h.check("the browser shows it", "Arm Push" in s.browser_labels())
    s.undo()


def f_undone():
    h.check("Undo: Force 1 again", item("Force 1") is not None, [i.Label for i in s.items()])


# -- G ------------------------------------------------------------------------------------------
def g_delete():
    s.click_row("Fixed 1")
    w.key(s.browser(), QtCore.Qt.Key_Delete)


def g_check():
    h.check("Fixed 1 deleted", item("Fixed 1") is None, [i.Label for i in s.items()])
    h.check("not in the browser", "Fixed 1" not in s.browser_labels())
    h.check("pre-check red", s.light() == "red", s.light())
    s.undo()


def g_undone():
    h.check("Undo: Fixed 1 back", item("Fixed 1") is not None)
    h.check("pre-check green again", s.light() == "green", s.light())


# -- H ------------------------------------------------------------------------------------------
def h_clone():
    s.right_click_row("Study 1 - Static Stress", "Clone Study")


def h_check_clone():
    studies = s.studies()
    h.check(
        "two studies",
        [x.Label for x in studies] == ["Study 1 - Static Stress", "Study 2 - Static Stress"],
        [x.Label for x in studies],
    )
    clone = s.active_study()
    h.check("the clone is active", clone is not None and clone.Label == "Study 2 - Static Stress")
    if clone is not None:
        kinds = sorted(s.sim().item_data(i)["kind"] for i in s.sim().items(clone))
        h.check("with copies of the items", kinds == ["fixed", "force"], kinds)
        h.check(
            "its own objects",
            not set(i.Name for i in s.sim().items(clone))
            & set(i.Name for i in s.sim().items(study())),
        )
        h.check("no results", not s.sim().summary(clone))
        h.check("the same mesh settings", s.sim().settings(clone) == s.sim().settings(study()))
    s.double_click_row("Study 1 - Static Stress")


def h_activated():
    h.check(
        "Study 1 active again",
        s.active_study() is not None and s.active_study().Name == state["study"],
    )
    node = s.row_node("Study 1 - Static Stress")
    h.check("shown bold (active)", node is not None and node["active"])
    s.right_click_row("Study 2 - Static Stress", "Delete")


def h_deleted():
    studies = s.studies()
    h.check(
        "Study 2 deleted",
        [x.Label for x in studies] == ["Study 1 - Static Stress"],
        [x.Label for x in studies],
    )
    leftovers = [
        o.Label
        for o in App.ActiveDocument.Objects
        if getattr(o, "SimStudy", None) is None and o.Name.startswith("SimItem")
    ]
    h.check("its items went with it", not leftovers, leftovers)


# -- I ------------------------------------------------------------------------------------------
def i_change_design():
    plate = App.ActiveDocument.getObject("Plate")
    plate.Height = 8
    App.ActiveDocument.recompute()


def i_check():
    h.check("out of date after the design changed", s.sim().out_of_date(study()))
    labels = s.browser_labels()
    h.check("the Results row says so", "Results (out of date)" in labels, labels)


h.run(
    "sim_setup_browser",
    [
        setup,
        enter,
        a_solve,
        a_go,
        s.wait_solved(),
        a_check,
        b_edit,
        b_type,
        b_check,
        c_solve_again,
        c_go,
        s.wait_solved("wait_solved_again"),
        c_check,
        d_double_click,
        d_cancel,
        d_check,
        e_suppress,
        e_check,
        e_back,
        f_rename,
        f_type,
        f_check,
        f_undone,
        g_delete,
        g_check,
        g_undone,
        h_clone,
        h_check_clone,
        h_activated,
        h_deleted,
        i_change_design,
        i_check,
    ],
)

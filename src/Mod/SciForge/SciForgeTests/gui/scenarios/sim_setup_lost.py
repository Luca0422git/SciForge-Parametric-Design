# SPDX-License-Identifier: LGPL-2.1-or-later
"""A load whose face is gone after a design change (builder sim-ui), with real clicks.

A  The bracket's study made by script: Fixed at the holes, a Force on the arm's top face.
   Workspace > Simulation: the pre-check is green.
B  Workspace > Design; the arm is suppressed (a design change: its top face is gone);
   Workspace > Simulation: Force 1's row is marked and says it lost what it was on, the
   pre-check is red, Load Case Attributes says "Lost its faces". SOLVE > Solve: the study
   "Cannot solve", with Repair next to it; Solve is refused with the sentence.
C  Repair: the Solve dialog closes and Edit Load opens on Force 1 (told why): it says its face
   is gone and has no pick left; a click on the plate's top face, OK: Force 1 is fine again
   (row, pre-check green, Load Case Attributes "OK").
D  Fixed 1 deleted (Delete on its row): red. Solve > Repair: Structural Constraints opens,
   told that nothing holds the model; a hole clicked, OK: the pre-check is not red.
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    s.new_bracket("SimLost")()
    sim = s.sim()
    doc = App.ActiveDocument
    body = s.body()
    study = sim.create_study(doc)
    sim.add_item(study, "constraint", "fixed", [(body, s.hole_faces(body))])
    sim.add_item(study, "load", "force", [(body, s.arm_top(body))], {"magnitude": 100.0})
    doc.recompute()


def enter():
    s.workspace("Simulation")


def attributes(name):
    s.menu_item("MANAGE", "Load Case Attributes")
    dialog = s.popup_named("SciForgeSimAttributes")
    rows = []
    if dialog is not None:
        table = dialog.findChild(QtWidgets.QTableWidget)
        rows = [
            [table.item(r, c).text() for c in range(table.columnCount())]
            for r in range(table.rowCount())
        ]
        s.close_popup("SciForgeSimAttributes")
    return [r for r in rows if r and r[0] == name]


# -- A ------------------------------------------------------------------------------------------
def a_check():
    h.check("pre-check green", s.light() == "green", s.light())
    s.workspace("Design")


# -- B ------------------------------------------------------------------------------------------
def b_change():
    h.check("DESIGN shows", s.tab_visible("solid"))
    doc = App.ActiveDocument
    arm = doc.getObject("Arm")
    arm.Suppressed = True  # (the design change: the arm and its top face are gone)
    doc.recompute()
    h.fit()
    s.workspace("Simulation")


def b_check():
    node = s.row_node("Force 1")
    h.check("Force 1's row is marked", node is not None and node["status"] == "error", node)
    tip = (node or {}).get("tip", "")
    h.check("it says it lost what it was on", "Lost what it was on" in tip, tip)
    h.check("pre-check red", s.light() == "red", s.light())
    row = attributes("Force 1")
    h.check("Load Case Attributes: lost", row and row[0][5] == "Lost its faces", row)
    h.ribbon("Solve")


def repair_button(dialog):
    return dialog.table.cellWidget(0, 3) if dialog is not None else None


def b_solve():
    dialog = s.solve_dialog()
    if not h.check("Solve dialog", dialog is not None):
        return
    light = dialog.table.item(0, 1)
    h.check("the study cannot solve", light is not None and light.text() == "Cannot solve")
    button = repair_button(dialog)
    h.check("Repair next to it", button is not None and button.text() == "Repair")
    s.click_widget(dialog.go)
    text = dialog.message.text()
    h.check("Solve refused: lost", "lost what it was on" in text, text)
    h.check("it points at Repair", "Repair" in text, text)
    h.check("the Solve dialog stays open", s.solve_dialog() is dialog)


def b_repair():
    s.click_widget(repair_button(s.solve_dialog()))


# -- C ------------------------------------------------------------------------------------------
def c_edit():
    h.check("the Solve dialog closed", s.solve_dialog() is None)
    p = s.item_panel()
    if not h.check("Repair opened Edit Load on Force 1", p is not None and p.editing):
        return
    h.check("on Force 1", p.item.Label == "Force 1", p.item.Label)
    h.check("told why", "Force 1 lost what it was on" in s.told(), s.told())
    h.check("no pick left (its face is gone)", p.picks == [], p.picks)
    h.check("it says so", "gone" in s.message(), s.message())
    s.click_face(s.body(), s.plate_top(s.body()))


def c_ok():
    p = s.item_panel()
    if p is not None:
        h.check("the plate's top picked", len(p.picks) == 1, p.picks)
    s.ok()


def c_check():
    node = s.row_node("Force 1")
    h.check("Force 1 is fine again", node is not None and node["status"] != "error", node)
    h.check("pre-check green again", s.light() == "green", s.light())
    row = attributes("Force 1")
    h.check("Load Case Attributes: OK", row and row[0][5] == "OK", row)
    s.click_row("Fixed 1")
    w.key(s.browser(), QtCore.Qt.Key_Delete)


# -- D ------------------------------------------------------------------------------------------
def d_deleted():
    h.check("Fixed 1 deleted", "Fixed 1" not in s.browser_labels(), s.browser_labels())
    h.check("pre-check red: nothing holds it", s.light() == "red", s.light())
    h.ribbon("Solve")


def d_repair():
    button = repair_button(s.solve_dialog())
    if h.check("Repair offered", button is not None):
        s.click_widget(button)


def d_constraints():
    p = s.item_panel()
    if not h.check(
        "Repair opened Structural Constraints",
        p is not None and p.category == "constraint" and not p.editing,
    ):
        return
    h.check("told why", "Nothing holds the model" in s.told(), s.told())
    body = s.body()
    face = s.visible_face(body, s.hole_faces(body))
    if h.check("a hole can be clicked", face is not None):
        s.click_face(body, face)


def d_ok():
    p = s.item_panel()
    if p is not None:
        h.check("the hole picked", len(p.picks) == 1, p.picks)
    s.ok()


def d_check():
    found = [s.sim().item_data(i)["kind"] for i in s.items("constraint")]
    h.check("a Fixed again", found == ["fixed"], found)
    h.check("pre-check not red", s.light() in ("green", "yellow"), s.light())


h.run(
    "sim_setup_lost",
    [
        setup,
        enter,
        a_check,
        b_change,
        b_check,
        b_solve,
        b_repair,
        c_edit,
        c_ok,
        c_check,
        d_deleted,
        d_repair,
        d_constraints,
        d_ok,
        d_check,
    ],
)

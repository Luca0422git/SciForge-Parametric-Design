# SPDX-License-Identifier: LGPL-2.1-or-later
"""A load whose face is gone after a design change (builder sim-ui), with real clicks.

A  The bracket's study made by script: Fixed at the holes, a Force on the arm's top face.
   Workspace > Simulation: the pre-check is green.
B  Workspace > Design; the arm is suppressed (a design change: its top face is gone);
   Workspace > Simulation: Force 1's row is marked and says it lost what it was on, the
   pre-check is red, Load Case Attributes says "Lost its faces".
C  Right-click Force 1 > Edit Load: the dialog says its face is gone and has no pick left; a
   click on the plate's top face, OK: Force 1 is fine again (row, pre-check green, Load Case
   Attributes "OK").
"""

import FreeCAD as App
from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

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
    s.right_click_row("Force 1", "Edit Load")


# -- C ------------------------------------------------------------------------------------------
def c_edit():
    p = s.item_panel()
    if not h.check("Edit Load opened", p is not None and p.editing):
        return
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


h.run(
    "sim_setup_lost",
    [setup, enter, a_check, b_change, b_check, c_edit, c_ok, c_check],
)

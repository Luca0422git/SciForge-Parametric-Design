# SPDX-License-Identifier: LGPL-2.1-or-later
"""The 3D view in the SIMULATION workspace (builder sim-ui), with real clicks and keys: the
right-click marking menu offers the setup's commands, and the Delete key does not change the
design (Fusion does not change the design from Simulation).

A  A bracket with a study made by script; Workspace > Simulation. A right click in the view:
   the marking menu offers Structural Loads, Structural Constraints, Pre-check, Solve, Study
   Materials and Settings, not the design's Extrude, Hole or Create Sketch. Structural Loads
   in the ring opens its dialog; Esc.
B  A right click again: the ring repeats the last setup command ("Repeat Structural Loads").
C  A click on a face of the bracket selects it; Delete: nothing is deleted (no new step, no
   undo step) and the face stays; E (Extrude's key in the design) and A (Appearance) open
   nothing either.
D  Workspace > Design: a right click shows the design's ring again (Extrude), and the Delete
   and E keys work again there.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s
from SciForgeTests.gui import widget_input as w

state = {}


def setup():
    s.new_bracket("SimCanvas")()
    s.sim().create_study(App.ActiveDocument)
    App.ActiveDocument.recompute()


def enter():
    s.workspace("Simulation")


def _open_menu():
    from sciforge import marking_menu

    marking_menu._last_menu["widget"] = None
    gl = h.gl_widget()
    w.click(gl, QtCore.QPoint(gl.width() - 140, 140), button=QtCore.Qt.RightButton)
    menu = marking_menu._last_menu["widget"]
    h.check("a right click opens the marking menu", menu is not None and menu.isVisible())
    return menu


def _labels(menu):
    from PySide import QtWidgets

    if menu is None:
        return []
    ring = [b.text() for b in menu.findChildren(QtWidgets.QToolButton)]
    listing = menu.findChild(QtWidgets.QListWidget, "SciForgeMarkingList")
    rows = [listing.item(i).text() for i in range(listing.count())] if listing else []
    return ring + rows


# -- A ------------------------------------------------------------------------------------------
def a_menu():
    h.fit()
    menu = _open_menu()
    labels = _labels(menu)
    for name in (
        "Structural Loads",
        "Structural Constraints",
        "Pre-check",
        "Solve",
        "Study Materials",
        "Settings",
    ):
        h.check("the ring offers %s" % name, name in labels, labels)
    for name in ("Extrude", "Hole", "Create Sketch", "Press Pull", "Delete"):
        h.check("no design command %s" % name, name not in labels, labels)
    if menu is not None:
        from SciForgeTests.gui import sketch_input

        sketch_input.marking_slot("Structural Loads")


def a_dialog():
    h.check("Structural Loads opened from the ring", s.item_panel() is not None)
    s.esc()


# -- B ------------------------------------------------------------------------------------------
def b_menu():
    h.check("Esc closed it", s.item_panel() is None)
    menu = _open_menu()
    labels = _labels(menu)
    h.check("Repeat Structural Loads", "Repeat Structural Loads" in labels, labels)
    if menu is not None:
        menu.close()


# -- C ------------------------------------------------------------------------------------------
def c_pick():
    doc = App.ActiveDocument
    state["objects"] = sorted(o.Name for o in doc.Objects)
    state["undo"] = list(doc.UndoNames)
    Gui.Selection.clearSelection()
    s.click_face(s.body(), s.plate_top(s.body()))


def c_delete():
    h.check("the face is selected", bool(Gui.Selection.getSelectionEx()))
    QtTest.QTest.keyClick(h.gl_widget(), QtCore.Qt.Key_Delete)


def c_check():
    doc = App.ActiveDocument
    h.check(
        "nothing deleted or added",
        sorted(o.Name for o in doc.Objects) == state["objects"],
        sorted(set(o.Name for o in doc.Objects) ^ set(state["objects"])),
    )
    h.check("no undo step", list(doc.UndoNames) == state["undo"], list(doc.UndoNames))
    QtTest.QTest.keyClick(h.gl_widget(), QtCore.Qt.Key_E)


def c_e_check():
    h.check("E opened nothing", s.task_panel() is None and not Gui.Control.activeDialog())
    QtTest.QTest.keyClick(h.gl_widget(), QtCore.Qt.Key_A)


def c_a_check():
    h.check("A (Appearance) opened nothing", not Gui.Control.activeDialog(), h.popups())
    h.close_popups()
    Gui.Selection.clearSelection()


# -- D ------------------------------------------------------------------------------------------
def d_leave():
    s.workspace("Design")


def d_menu():
    h.check("DESIGN shows", s.tab_visible("solid"))
    menu = _open_menu()
    labels = _labels(menu)
    h.check("the design's ring is back (Extrude)", "Extrude" in labels, labels)
    if menu is not None:
        menu.close()
    from sciforge import shortcuts

    for key in ("Del", "E"):
        entry = shortcuts._bound.get(shortcuts.normalise(key))
        h.check("the %s key works again" % key, entry is not None and entry[1].isEnabled())


h.run(
    "sim_setup_canvas",
    [
        setup,
        enter,
        a_menu,
        a_dialog,
        b_menu,
        c_pick,
        c_delete,
        c_check,
        c_e_check,
        c_a_check,
        d_leave,
        d_menu,
    ],
    paced_by="state",
)

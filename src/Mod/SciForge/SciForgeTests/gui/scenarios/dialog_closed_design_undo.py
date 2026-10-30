# SPDX-License-Identifier: LGPL-2.1-or-later
"""A design closed while one of its dialogs is open leaves no undo step open behind it.

FreeCAD's undo step is application-wide: `doc.openTransaction(name)` names the step that the
next change in ANY design goes into, and a design joins it only with its first change. A
design closed while its dialog had changed nothing yet (waiting for a pick) left that step
open: App.getActiveTransaction() still named it, and the next design's changes went into a
step named after the closed design's dialog (B's block and its two edits came out as three
undo steps, the first one called "Extrude"; a simulation solve waited for it forever). A
design that had changes in the step closed it as it went (FreeCAD commits it into it).

For each dialog below, real input:
1. Design A, a 40 x 30 x 10 block (made by script: the feature under test is not the block).
   The dialog opened (Extrude: E; Hole; Fillet; Measure: I; SURFACE > Offset), waiting for
   its pick: its undo step is named, nothing changed yet (Measure: no step). Then again with
   a change: Extrude (top face, 5), Hole (top face), Fillet (front top edge, 3), Offset (top
   face, 3).
2. A's tab x (Don't Save when asked): A is gone, the dialog with it, no undo step left open.
3. Design B, the same block (by script: in no undo step), then Fillet (an edge, 2, OK) and Hole
   (the top face, OK): two undo steps, Hole and Fillet, nothing else; Ctrl+Z takes the hole
   away (only it), Ctrl+Z again the fillet; no undo step open at any point. B closed.
4. A dialog of another design keeps its step: design D in the back, design C in front with
   Hole open and waiting; D's tab x: C's Hole still open, its step still open; the top face,
   OK: one undo step, Hole; Ctrl+Z: the block again.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import blend_steps as b
from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import polish2_steps as p2
from SciForgeTests.gui import surface_steps as st
from SciForgeTests.gui import widget_input as wi

V = App.Vector
BLOCK = 40.0 * 30.0 * 10.0
TOP = V(30, 20, 10)  # a point of the block's top face
FRONT_TOP = V(20, 0, 10)  # a point of its front top edge
s = {}
FOUND = {}  # dialog -> the undo step left open after its design closed (None: none)


def step(fn, name, wait_ms=None):
    fn.__name__ = name
    return fn


def open_step():
    """App.getActiveTransaction(): (name, id) of the application-wide undo step, or None."""
    try:
        return App.getActiveTransaction()
    except Exception as exc:
        return "error: %s" % exc


def dialog():
    from sciforge import taskui

    return taskui.current()


def block_design(name):
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument(name)
    p2.make_box(doc, "Block", 40, 30, 10)
    h.fit()
    return doc


def tab_x(doc):
    """Click the x of the design's tab (SciForge's document tabs at the top)."""
    bar = h.document_tabs()
    index = -1
    if bar is not None:
        for i in range(bar.count()):
            if bar.tabText(i).replace("*", "").strip().startswith(doc.Label):
                index = i
    if not h.check("%s has a tab" % doc.Label, index >= 0):
        return False
    button = bar.tabButton(index, QtWidgets.QTabBar.RightSide) or bar.tabButton(
        index, QtWidgets.QTabBar.LeftSide
    )
    if not h.check("%s's tab has an x" % doc.Label, button is not None):
        return False
    QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
    QtWidgets.QApplication.processEvents()
    return True


def solid_tab():
    st.tab("SOLID")


# -- 1. design A and the dialog ---------------------------------------------------------------
def a_steps(kind, changed):
    tag = "%s%s" % (kind, "" if changed else " (waiting)")
    key = "%s_%s" % (kind, "changed" if changed else "waiting")

    def new_a():
        doc = block_design("A_%s%s" % (kind, "" if changed else "_waiting"))
        s["a"] = doc.Name
        h.check("%s: no undo step open before the dialog" % tag, open_step() is None, open_step())

    def start():
        Gui.Selection.clearSelection()
        if kind == "extrude":
            h.click_empty()
            h.press("e")
        elif kind == "hole":
            h.ribbon("Hole")
        elif kind == "fillet":
            h.ribbon("Fillet")
        elif kind == "measure":
            h.click_empty()
            h.press("i")
        elif kind == "offset":
            h.click_empty()
            st.tab("SURFACE")
            st.menu("CREATE", "Offset")

    def pick():
        if not h.check("%s: the dialog is open" % tag, dialog() is not None, kind):
            return
        h.fit()
        if kind == "fillet":
            h.click_edge(FRONT_TOP)
        else:
            h.click(TOP)

    def change():
        p = dialog()
        if not h.check("%s: still open" % tag, p is not None):
            return
        if kind == "extrude":
            ui.type_into(p.distance.widget, "5")
        elif kind == "fillet":
            b.type_into(p.radius.widget, "3")
        elif kind == "offset":
            st.settle()
            st.type_field("distance", "3")

    def pending():
        if kind == "offset":
            st.settle()
        doc = App.getDocument(s["a"])
        h.check("%s: the dialog is open" % tag, dialog() is not None)
        current = open_step()
        if kind == "measure":
            h.check(
                "%s: no undo step (Measure changes nothing)" % tag,
                not doc.UndoNames,
                list(doc.UndoNames),
            )
        elif changed:
            h.check("%s: the dialog's undo step is open" % tag, current is not None, current)
            h.check("%s: design A changed" % tag, Gui.getDocument(doc.Name).Modified)
        else:
            h.check("%s: the dialog's undo step is named" % tag, current is not None, current)
            h.check("%s: nothing changed yet" % tag, not doc.UndoNames, list(doc.UndoNames))
        print("[SciForge] %s: open step with the dialog: %r" % (tag, current), flush=True)

    steps = [
        step(new_a, "%s_new_a" % key),
        step(start, "%s_start" % key),
    ]
    if changed:
        steps += [step(pick, "%s_pick" % key), step(change, "%s_change" % key)]
    return steps + [step(pending, "%s_pending" % key)]


# -- 2. A closed (tab x; Don't Save when it asks) ---------------------------------------------
def close_steps(kind, changed):
    tag = "%s%s" % (kind, "" if changed else " (waiting)")
    key = "%s_%s" % (kind, "changed" if changed else "waiting")

    def close_a():
        tab_x(App.getDocument(s["a"]))

    def dont_save():
        asked = p2.dialog("SciForgeCloseDialog")
        if asked is not None:
            wi.click(p2.child(asked, "SciForgeCloseDiscard"))
        elif changed and kind != "measure":
            h.check("%s: asked to save the changed design" % tag, False, h.popups())

    def closed():
        h.check(
            "%s: design A closed" % tag,
            s["a"] not in App.listDocuments(),
            list(App.listDocuments()),
        )
        h.check("%s: the dialog went with it" % tag, not Gui.Control.activeDialog())
        left = open_step()
        FOUND[tag] = left
        print("[SciForge] %s: open step after its design closed: %r" % (tag, left), flush=True)
        h.check("%s: no undo step left open by the closed design" % tag, left is None, left)

    return [
        step(close_a, "%s_close_a" % key),
        step(dont_save, "%s_dont_save" % key),
        step(closed, "%s_closed" % key),
    ]


# -- 3. design B: two edits, two undo steps ---------------------------------------------------
def b_steps(kind, changed):
    tag = "%s%s" % (kind, "" if changed else " (waiting)")
    key = "%s_%s" % (kind, "changed" if changed else "waiting")

    def new_b():
        Gui.activateWorkbench("SciForgeWorkbench")
        doc = App.newDocument("B_%s%s" % (kind, "" if changed else "_waiting"))
        s["b"] = doc.Name
        h.check("%s: B: no undo step after New" % tag, not doc.UndoNames, list(doc.UndoNames))
        p2.make_box(doc, "Block", 40, 30, 10)
        h.fit()
        solid_tab()
        print(
            "[SciForge] %s: B's undo steps after its block: %r, open step %r"
            % (tag, list(doc.UndoNames), open_step()),
            flush=True,
        )
        h.check("%s: B: no undo step open" % tag, open_step() is None, open_step())
        h.check("%s: B: its block is in no undo step" % tag, not doc.UndoNames, list(doc.UndoNames))

    def fillet():
        Gui.Selection.clearSelection()
        h.ribbon("Fillet")

    def fillet_edge():
        h.fit()
        h.click_edge(FRONT_TOP)

    def fillet_ok():
        p = b.blend_panel()
        if h.check("%s: B: Fillet open" % tag, p is not None):
            b.type_into(p.radius.widget, "2")
            h.task_button("OK")

    def hole():
        doc = App.getDocument(s["b"])
        s["filleted"] = h.solid_volume()
        h.check(
            "%s: B: the fillet made" % tag,
            s["filleted"] < BLOCK - 1.0,
            (s["filleted"], list(doc.UndoNames)),
        )
        Gui.Selection.clearSelection()
        h.ribbon("Hole")

    def hole_face():
        h.fit()
        h.click(TOP)

    def hole_ok():
        h.task_button("OK")

    def two_steps():
        doc = App.getDocument(s["b"])
        names = list(doc.UndoNames)
        print("[SciForge] %s: B's undo steps: %r" % (tag, names), flush=True)
        s["drilled"] = h.solid_volume()
        h.check("%s: B: the hole made" % tag, s["drilled"] < s["filleted"] - 1.0, s["drilled"])
        h.check("%s: B: two undo steps, Hole and Fillet" % tag, names == ["Hole", "Fillet"], names)
        h.check("%s: B: no undo step left open" % tag, open_step() is None, open_step())
        h.press(QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)

    def undone_once():
        doc = App.getDocument(s["b"])
        names = list(doc.UndoNames)
        h.check(
            "%s: B: Ctrl+Z took the hole away" % tag,
            b.close(h.solid_volume(), s["filleted"]),
            (h.solid_volume(), s["filleted"]),
        )
        h.check("%s: B: only the hole" % tag, names == ["Fillet"], names)
        h.check(
            "%s: B: Redo offers the hole" % tag,
            list(doc.RedoNames) == ["Hole"],
            list(doc.RedoNames),
        )
        h.press(QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)

    def undone_twice():
        doc = App.getDocument(s["b"])
        h.check(
            "%s: B: Ctrl+Z again took the fillet away" % tag,
            b.close(h.solid_volume(), BLOCK),
            h.solid_volume(),
        )
        h.check("%s: B: nothing more to undo" % tag, not doc.UndoNames, list(doc.UndoNames))
        h.check("%s: B: no undo step open" % tag, open_step() is None, open_step())
        Gui.getDocument(doc.Name).Modified = False  # (nothing to save: no question)
        App.closeDocument(doc.Name)

    return [
        step(new_b, "%s_new_b" % key),
        step(fillet, "%s_b_fillet" % key),
        step(fillet_edge, "%s_b_fillet_edge" % key),
        step(fillet_ok, "%s_b_fillet_ok" % key),
        step(hole, "%s_b_hole" % key),
        step(hole_face, "%s_b_hole_face" % key),
        step(hole_ok, "%s_b_hole_ok" % key),
        step(two_steps, "%s_b_two_steps" % key),
        step(undone_once, "%s_b_undone_once" % key),
        step(undone_twice, "%s_b_undone_twice" % key),
    ]


def summary():
    print("[SciForge] undo steps left open by a closed design's dialog: %r" % FOUND, flush=True)


# -- 4. another design's dialog keeps its step ----------------------------------------------
def other_steps():
    def new_d_and_c():
        s["d"] = block_design("Back_D").Name
        s["c"] = block_design("Front_C").Name
        solid_tab()
        Gui.Selection.clearSelection()
        h.ribbon("Hole")

    def close_d():
        s["c_step"] = open_step()
        h.check("other: C's Hole open", dialog() is not None and dialog().doc.Name == s["c"])
        h.check("other: its step named", s["c_step"] is not None, s["c_step"])
        tab_x(App.getDocument(s["d"]))

    def dont_save():
        asked = p2.dialog("SciForgeCloseDialog")
        if asked is not None:
            wi.click(p2.child(asked, "SciForgeCloseDiscard"))

    def c_still_open():
        h.check("other: D closed", s["d"] not in App.listDocuments(), list(App.listDocuments()))
        p = dialog()
        h.check("other: C's Hole still open", p is not None and p.doc.Name == s["c"])
        h.check(
            "other: C's step still open", open_step() == s["c_step"], (open_step(), s["c_step"])
        )
        h.fit()
        h.click(TOP)

    def c_ok():
        h.task_button("OK")

    def c_one_step():
        doc = App.getDocument(s["c"])
        h.check(
            "other: C: one undo step, Hole", list(doc.UndoNames) == ["Hole"], list(doc.UndoNames)
        )
        h.check("other: the hole made", h.solid_volume() < BLOCK - 1.0, h.solid_volume())
        h.check("other: no undo step open", open_step() is None, open_step())
        h.press(QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)

    def c_undone():
        doc = App.getDocument(s["c"])
        h.check(
            "other: Ctrl+Z: the block again", b.close(h.solid_volume(), BLOCK), h.solid_volume()
        )
        h.check("other: nothing more to undo", not doc.UndoNames, list(doc.UndoNames))

    return [
        step(new_d_and_c, "other_new_d_and_c"),
        step(close_d, "other_close_d"),
        step(dont_save, "other_dont_save"),
        step(c_still_open, "other_c_still_open"),
        step(c_ok, "other_c_ok"),
        step(c_one_step, "other_c_one_step"),
        step(c_undone, "other_c_undone"),
    ]


ROUNDS = [(k, False) for k in ("extrude", "hole", "fillet", "measure", "offset")] + [
    (k, True) for k in ("extrude", "hole", "fillet", "offset")
]
STEPS = []
for _kind, _changed in ROUNDS:
    STEPS += a_steps(_kind, _changed) + close_steps(_kind, _changed) + b_steps(_kind, _changed)
STEPS += other_steps() + [summary]

h.run("dialog_closed_design_undo", STEPS, paced_by="state")

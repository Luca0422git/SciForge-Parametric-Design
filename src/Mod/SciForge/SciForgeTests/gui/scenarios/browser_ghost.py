# SPDX-License-Identifier: LGPL-2.1-or-later
"""Hovering a hidden body's browser row shows a faint ghost of it (Luca, 2026-10-26, for
0.1.0-beta.2.2: "If i hover over a body in the browser that is hidden, I should get a preview
of that body in the workspace. A ghost body if you will."). Only real input.

Plate (Body) and block (Body2) as in the joint scenarios.

  A  The block's eye off in the browser: it is hidden. The mouse over its row: a see-through
     ghost of the block is in the 3D view (an unclickable Coin node), the block is still
     hidden (its Visibility untouched) and nothing went into the undo history.
  B  The mouse over the plate's row (shown): no ghost; the plate lights up as before. Back
     over the block's row: the same ghost again (kept, not built anew). The mouse into the
     3D view: the ghost goes.
  C  Over the block's row, then a click on its eye: the block shows, the ghost goes.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import widget_input as w

state = {}


def ghost():
    from sciforge import hover_ghost

    return hover_ghost


def in_scene(node):
    if node is None:
        return False
    root = Gui.ActiveDocument.ActiveView.getSceneGraph()
    return root.findChild(node) >= 0


def hover_row(label):
    tree, pos = t.row_point(label)
    if pos is not None:
        w.move(tree.viewport(), pos + QtCore.QPoint(5, 0))
        w.move(tree.viewport(), pos)


def a_hide_block():
    t.click_eye("Body2")


def a_hidden():
    block = j.block()
    h.check("A: the block is hidden", not block.ViewObject.Visibility)
    doc = App.ActiveDocument
    state["undo"] = doc.UndoCount
    state["names"] = doc.UndoNames


def a_hover():
    hover_row("Body2")


def a_ghost():
    g = ghost()
    h.check("A: the hidden block shows as a ghost", g.current() is j.block(), g.current())
    h.check("A: the ghost is in the 3D view", in_scene(g.node()))
    h.check("A: the block is still hidden", not j.block().ViewObject.Visibility)
    doc = App.ActiveDocument
    h.check(
        "A: nothing went into the undo history",
        doc.UndoCount == state["undo"] and doc.UndoNames == state["names"],
        (doc.UndoNames, state["names"]),
    )
    state["node"] = g.node()
    h.shot("A-ghost")


def b_plate():
    hover_row("Body")


def b_no_ghost():
    g = ghost()
    h.check("B: no ghost over a shown body", g.current() is None and g.node() is None)
    h.check("B: the old ghost left the view", not in_scene(state["node"]))
    pre = Gui.Selection.getPreselection()
    h.check("B: the plate lights up", pre is not None and pre.ObjectName == j.plate().Name)


def b_back():
    hover_row("Body2")


def b_same_ghost():
    g = ghost()
    h.check("B: the ghost again", g.current() is j.block() and in_scene(g.node()))
    h.check("B: the same ghost (kept)", g.node() is state["node"])


def b_leave():
    w.move(h.gl_widget(), QtCore.QPoint(30, 30))


def b_gone():
    g = ghost()
    h.check("B: leaving the browser takes the ghost away", g.node() is None)
    h.check("B: nothing of it is left in the view", not in_scene(state["node"]))


def c_hover():
    hover_row("Body2")


def c_eye():
    t.click_eye("Body2")


def c_shown():
    g = ghost()
    h.check("C: the block shows", j.block().ViewObject.Visibility)
    h.check("C: the ghost went", g.node() is None and not in_scene(state["node"]))
    s.no_popups("C")


h.run(
    "browser_ghost",
    [s.new_design("BrowserGhost")]
    + j.two_boxes()
    + [a_hide_block, a_hidden, a_hover, a_ghost]
    + [b_plate, b_no_ghost, b_back, b_same_ghost, b_leave, b_gone]
    + [c_hover, c_eye, c_shown],
    paced_by="state",
)

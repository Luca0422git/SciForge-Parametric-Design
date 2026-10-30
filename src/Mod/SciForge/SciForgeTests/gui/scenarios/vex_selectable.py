# SPDX-License-Identifier: LGPL-2.1-or-later
"""Selectable/Unselectable (Fusion's browser right-click; docs/sciforge/parity/vex-assembly.md):
a VEX robot's frame made unselectable, so the parts on it are easy to click.

A design with a root body "Screw" (a 10 mm box) and a component "Frame" holding a body
"Rail" (a 6 mm box at x = 40).
Path 1, right-click Frame: Selectable/Unselectable sits right after Hide; chosen, Frame's row
  carries the no-entry mark, a click on Rail in the 3D view picks nothing and the mouse over
  it lights nothing, a click on Screw still picks Screw.
Path 2, Ctrl+Z: Rail can be picked again; Ctrl+Y: not again.
Path 3, a new step in Rail is unpickable at once.
Path 4, right-click Screw (a body at the root) > Selectable/Unselectable: Screw cannot be
  picked in the 3D view either; a click on its browser row still selects it.
Path 5, Frame made selectable again from its menu: Rail is picked by a click.
Path 6, saved and opened again: Screw is still unselectable, Rail still selectable.
"""

import os
import shutil
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from SciForgeTests.gui import component_steps as cs
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import widget_input as w

V = App.Vector
s = {}
RAIL = V(43, 3, 6)  # the middle of Rail's top face
RAIL_STEP = V(43, 3, 8)  # the middle of the new step's top face (path 3)
RAIL_FREE = V(41, 1, 6)  # Rail's top face beside the new step
SCREW = V(5, 5, 10)  # the middle of Screw's top face
ENTRY = "Selectable/Unselectable"


def doc():
    return App.getDocument(s["doc"])


def obj(name):
    return doc().getObject(s[name])


def switches(name):
    """(the body's own Selectable, its steps') as FreeCAD has them."""
    body = obj(name)
    steps = [
        bool(f.ViewObject.Selectable)
        for f in body.Group
        if f.isDerivedFrom("PartDesign::Feature") and f.ViewObject is not None
    ]
    return bool(body.ViewObject.Selectable), steps


def browser():
    from sciforge import browser_ui

    tree = browser_ui.widget()
    if tree is not None:
        tree.refresh(force=True)
    return tree


def marked(label):
    node = cs.node_of(label)
    return bool(node and node.get("unselectable"))


def add_box(document, body, size, name, at=None):
    box = document.addObject("PartDesign::AdditiveBox", name)
    body.addObject(box)
    box.Length = box.Width = box.Height = size
    if at is not None:
        box.Placement = App.Placement(at, App.Rotation())
    return box


def picked(point):
    """Click on the 3D point: (what was under the mouse, the objects selected after)."""
    Gui.Selection.clearSelection()
    hit = h.click(point)
    names = [x.ObjectName for x in Gui.Selection.getSelectionEx()]
    Gui.Selection.clearSelection()
    return hit, names


def lit(point):
    """What the mouse over the 3D point preselects (FreeCAD's hover highlight)."""
    Gui.Selection.clearSelection()
    h.move(h.screen_point(point + V(0.5, 0.5, 0)))
    h.move(h.screen_point(point))
    pre = Gui.Selection.getPreselection()
    return pre.ObjectName if pre is not None and pre.ObjectName else None


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    from sciforge import components

    document = App.newDocument("Selectable")
    s["doc"] = document.Name
    screw = document.addObject("PartDesign::Body", "Body")
    screw.Label = "Screw"
    add_box(document, screw, 10, "ScrewBox")
    frame = components.new_component(document, "Frame", None)
    rail = components.new_body_in(document, frame, label="Rail")
    rail_box = add_box(document, rail, 6, "RailBox")
    rail.Placement = App.Placement(V(40, 0, 0), App.Rotation())
    document.recompute()
    s.update(screw=screw.Name, frame=frame.Name, rail=rail.Name, rail_box=rail_box.Name)
    h.fit()
    browser()


# -- Path 1 -------------------------------------------------------------------------------------
def p1_before():
    hit, names = picked(RAIL)
    h.check("P1 before: a click on Rail picks Rail's step", names == [s["rail_box"]], (hit, names))
    tree, pos = t.row_point("Frame")
    texts = [x for x, _on in w.menu_texts(tree.viewport(), pos)] if pos else []
    h.check(
        "P1 Frame's menu: Selectable/Unselectable right after Hide",
        ENTRY in texts and "Hide" in texts and texts.index(ENTRY) == texts.index("Hide") + 1,
        texts,
    )
    h.check("P1 no mark on Frame yet", not marked("Frame"))
    t.row_menu("Frame", ENTRY)


def p1_unselectable():
    from sciforge import selectable

    h.check("P1 Frame is unselectable", selectable.get(obj("frame")) is False)
    h.check(
        "P1 Rail's switches are off (its view and its step's)",
        switches("rail") == (False, [False]),
        switches("rail"),
    )
    browser()
    h.check("P1 Frame's row carries the no-entry mark", marked("Frame"), cs.node_of("Frame"))
    h.check("P1 Rail's row keeps its own (no mark)", not marked("Rail"))
    hit, names = picked(RAIL)
    h.check("P1 a click on Rail picks nothing", hit is None and names == [], (hit, names))
    h.check("P1 the mouse over Rail lights nothing", lit(RAIL) is None, lit(RAIL))
    hit, names = picked(SCREW)
    h.check("P1 a click on Screw still picks Screw", names == ["ScrewBox"], (hit, names))
    h.shot("P1-frame-unselectable")
    h.press(QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)


# -- Path 2 -------------------------------------------------------------------------------------
def p2_undone():
    from sciforge import selectable

    h.check("P2 Ctrl+Z: Frame selectable again", selectable.get(obj("frame")) is True)
    hit, names = picked(RAIL)
    h.check("P2 Ctrl+Z: a click picks Rail again", names == [s["rail_box"]], (hit, names))
    h.press(QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)


def p2_redone():
    hit, names = picked(RAIL)
    h.check("P2 Ctrl+Y: Rail cannot be picked again", names == [], (hit, names))


# -- Path 3 -------------------------------------------------------------------------------------
def p3_new_step():
    box = add_box(doc(), obj("rail"), 2, "RailBox2", at=V(2, 2, 6))
    s["rail_box2"] = box.Name
    doc().recompute()


def p3_unpickable():
    h.check("P3 the new step's switch is off", switches("rail") == (False, [False, False]))
    hit, names = picked(RAIL_STEP)
    h.check("P3 a click on the new step picks nothing", names == [], (hit, names))


# -- Path 4 -------------------------------------------------------------------------------------
def p4_screw():
    t.row_menu("Screw", ENTRY)


def p4_unselectable():
    browser()
    h.check("P4 Screw's row carries the mark", marked("Screw"), cs.node_of("Screw"))
    hit, names = picked(SCREW)
    h.check("P4 a click on Screw picks nothing", hit is None and names == [], (hit, names))
    Gui.Selection.clearSelection()
    t.click_row("Screw")
    names = [x.ObjectName for x in Gui.Selection.getSelectionEx()]
    h.check("P4 its browser row still selects it", s["screw"] in names, names)
    Gui.Selection.clearSelection()


# -- Path 5 -------------------------------------------------------------------------------------
def p5_frame_back():
    t.row_menu("Frame", ENTRY)


def p5_selectable():
    from sciforge import selectable

    h.check("P5 Frame selectable again", selectable.get(obj("frame")) is True)
    h.check("P5 Rail's switches are on", switches("rail") == (True, [True, True]), switches("rail"))
    browser()
    h.check("P5 Frame's mark is gone", not marked("Frame"))
    hit, names = picked(RAIL_FREE)
    tip = obj("rail").Tip.Name  # (FreeCAD shows a body through its last step)
    h.check("P5 a click on Rail picks it", names == [tip], (hit, names, tip))


# -- Path 6 -------------------------------------------------------------------------------------
def p6_save():
    s["dir"] = tempfile.mkdtemp(prefix="sciforge-selectable-")
    s["file"] = os.path.join(s["dir"], "Selectable.FCStd")
    doc().saveAs(s["file"])
    Gui.getDocument(s["doc"]).Modified = False
    App.closeDocument(s["doc"])
    reopened = App.openDocument(s["file"])
    s["doc"] = reopened.Name


def p6_reopened():
    from sciforge import selectable

    h.fit()
    browser()
    h.check("P6 Screw still unselectable", selectable.get(obj("screw")) is False)
    h.check("P6 Frame still selectable", selectable.get(obj("frame")) is True)
    h.check("P6 Screw's row carries the mark", marked("Screw"))
    hit, names = picked(SCREW)
    h.check("P6 a click on Screw picks nothing", names == [], (hit, names))
    hit, names = picked(RAIL_FREE)
    tip = obj("rail").Tip.Name
    h.check("P6 a click on Rail picks it", names == [tip], (hit, names, tip))


def cleanup():
    for name in list(App.listDocuments()):
        Gui.getDocument(name).Modified = False
        App.closeDocument(name)
    shutil.rmtree(s.get("dir", ""), ignore_errors=True)


h.run(
    "vex_selectable",
    [
        setup,
        p1_before,
        p1_unselectable,
        p2_undone,
        p2_redone,
        p3_new_step,
        p3_unpickable,
        p4_screw,
        p4_unselectable,
        p5_frame_back,
        p5_selectable,
        p6_save,
        p6_reopened,
        cleanup,
    ],
    paced_by="state",
)

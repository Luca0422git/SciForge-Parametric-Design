# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panning and orbiting keep working after a drag that SciForge takes over, and the ViewCube
never keeps turning once the button is up (Luca, 2026-10-29: "Sometimes the view cube gets
stuck on the mouse even when im not clicking. and freemoving components makes panning and
rotating not work until you click an empty part of the build area").

Why they broke: FreeCAD's navigation sees the left-button press of every drag (it cannot be
known yet whether it becomes a click, a box or a Component Drag), and SciForge's view filter
then keeps the moves and the release to itself. FreeCAD's navigation went on thinking the left
button was held: in its Fusion-like (Revit) style a middle-drag pans and Shift + middle-drag
orbits only with no other button down, so neither did anything until the next real left
click. The ViewCube followed the mouse after a press whose release went to another widget.

A component "Part" holding a 20 mm box, top view, Real input only (QTest presses, moves and
releases on the 3D view and the cube).
  N1 Before anything: a middle-drag pans the view, a Shift + middle-drag orbits it.
  N2 A left-drag on the component moves it (Component Drag, the free kind), then a
     middle-drag still pans and a Shift + middle-drag still orbits; nothing got selected.
  N3 A selection box (a left-drag on empty space), then a middle-drag still pans.
  N4 The ViewCube: a press on it and a drag turn the view; the release goes to another
     widget (as when the window loses it); then the mouse moves over the cube with no button
     held: the view does not turn any more; a click on the cube's FRONT still turns to FRONT.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import viewcube_input as vc

V = App.Vector
MIDDLE = QtCore.Qt.MiddleButton
LEFT = QtCore.Qt.LeftButton
SHIFT = QtCore.Qt.ShiftModifier
st = {}


def camera():
    cam = h.view().getCameraNode()
    position = App.Vector(*cam.position.getValue().getValue())
    return position, tuple(cam.orientation.getValue().getValue())


def moved_by():
    """How far the camera moved and how much it turned since remember() (mm, quaternion
    difference)."""
    pos, rot = camera()
    p0, r0 = st["camera"]
    turn = sum(abs(a - b) for a, b in zip(rot, r0))
    return (pos - p0).Length, turn


def remember():
    st["camera"] = camera()


def empty_pixel():
    """A pixel of the view with no model under it (the box sits in the middle)."""
    widget = h.gl_widget()
    return QtCore.QPoint(int(widget.width() * 0.85), int(widget.height() * 0.8))


def middle_drag(modifiers=QtCore.Qt.NoModifier, dx=80, dy=0):
    start = QtCore.QPoint(int(h.gl_widget().width() * 0.3), int(h.gl_widget().height() * 0.3))
    end = QtCore.QPoint(start.x() + dx, start.y() + dy)
    h.drag(start, end, steps=10, button=MIDDLE, modifiers=modifiers)


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    from sciforge import components

    document = App.newDocument("StuckButtons")
    part = components.new_component(document, "Part", None)
    body = components.new_body_in(document, part, label="Block")
    box = document.addObject("PartDesign::AdditiveBox", "Box")
    body.addObject(box)
    box.Length = box.Width = box.Height = 20
    document.recompute()
    st["part"] = part.Name
    h.view().viewTop()
    h.fit()
    Gui.Selection.clearSelection()


# -- N1 -----------------------------------------------------------------------------------------
def n1_pan():
    remember()
    middle_drag()


def n1_orbit():
    shift, turn = moved_by()
    h.check("N1 a middle-drag pans the view", shift > 1.0 and turn < 1e-6, (shift, turn))
    remember()
    middle_drag(SHIFT, 60, 40)


def n1_orbited():
    _shift, turn = moved_by()
    h.check("N1 a Shift + middle-drag orbits the view", turn > 1e-3, turn)
    h.view().viewTop()
    h.fit()


# -- N2 -----------------------------------------------------------------------------------------
def n2_drag():
    st["place"] = App.Placement(App.ActiveDocument.getObject(st["part"]).Placement)
    a = h.screen_point(V(10, 10, 20))
    h.drag(a, QtCore.QPoint(a.x() + 60, a.y()), steps=14)


def n2_pan():
    from sciforge import joints_drag

    part = App.ActiveDocument.getObject(st["part"])
    last = joints_drag.last() or {}
    h.check(
        "N2 the left-drag moved the component (Component Drag)",
        not part.Placement.isSame(st["place"], 1e-6) and last.get("moved") is True,
        (part.Placement, last),
    )
    h.check("N2 no drag left running", joints_drag.active() is None)
    remember()
    middle_drag()


def n2_orbit():
    shift, turn = moved_by()
    h.check(
        "N2 after the component drag a middle-drag still pans",
        shift > 1.0 and turn < 1e-6,
        (shift, turn),
    )
    remember()
    middle_drag(SHIFT, 60, 40)


def n2_orbited():
    _shift, turn = moved_by()
    h.check("N2 after the component drag a Shift + middle-drag still orbits", turn > 1e-3, turn)
    names = [x.ObjectName for x in Gui.Selection.getSelectionEx()]
    h.check("N2 nothing got selected by it all", not names, names)
    h.view().viewTop()
    h.fit()


# -- N3 -----------------------------------------------------------------------------------------
def n3_box():
    a = empty_pixel()
    h.drag(a, QtCore.QPoint(a.x() - 60, a.y() - 40), steps=10)


def n3_pan():
    remember()
    middle_drag()


def n3_panned():
    shift, turn = moved_by()
    h.check(
        "N3 after a selection box a middle-drag still pans",
        shift > 1.0 and turn < 1e-6,
        (shift, turn),
    )
    h.view().viewTop()
    h.fit()


# -- N4 -----------------------------------------------------------------------------------------
def n4_cube():
    cube = vc.cube()
    start = vc.hover("top")
    if not h.check("N4 the ViewCube is there", cube is not None and start is not None):
        return
    st["before_cube"] = vc.orientation()
    QtTest.QTest.mousePress(cube, LEFT, QtCore.Qt.NoModifier, start)
    for i in range(1, 9):
        pos = QtCore.QPointF(start.x() + 5 * i, start.y())
        vc._send_move(cube, pos, LEFT)
    # the release reaches another widget (the 3D view), never the cube
    QtTest.QTest.mouseRelease(h.gl_widget(), LEFT, QtCore.Qt.NoModifier, empty_pixel())
    QtWidgets.QApplication.processEvents()
    st["after_drag"] = vc.orientation()
    for i in range(1, 9):  # the mouse moves on over the cube, no button held
        pos = QtCore.QPointF(start.x() + 40 - 5 * i, start.y() + 3 * i)
        vc._send_move(cube, pos, QtCore.Qt.NoButton)
    QtWidgets.QApplication.processEvents()


def n4_still():
    if "after_drag" not in st:
        return
    turned = vc.turned(st["before_cube"], st["after_drag"])
    h.check("N4 the drag on the cube turned the view", turned > 5, turned)
    turned = vc.turned(st["after_drag"])
    h.check("N4 with no button held the cube no longer turns the view", turned < 1e-6, turned)
    vc.click("front")


def n4_front():
    h.check(
        "N4 a click on the cube's FRONT still turns to FRONT",
        vc.looks_along((0, 1, 0), 1e-3),
        vc.describe(),
    )


def cleanup():
    for name in list(App.listDocuments()):
        Gui.getDocument(name).Modified = False
        App.closeDocument(name)


h.run(
    "navigation_stuck_buttons",
    [
        setup,
        n1_pan,
        n1_orbit,
        n1_orbited,
        n2_drag,
        n2_pan,
        n2_orbit,
        n2_orbited,
        n3_box,
        n3_pan,
        n3_panned,
        n4_cube,
        n4_still,
        n4_front,
        cleanup,
    ],
    paced_by="state",
)

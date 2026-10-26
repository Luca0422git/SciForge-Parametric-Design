# SPDX-License-Identifier: LGPL-2.1-or-later
"""Drag a joint to set its limits (Luca, 2026-10-26, for 0.1.0-beta.2.2: "I should be able to
drag it where i want it to max and min. simple as that."). Only real input; the parity
note is in docs/sciforge/parity/joints.md.

Plate and block (joints_steps), J: the block onto the plate, Revolute, OK.

  A  Right-click the joint's row > Edit Joint Limits: the dialog opens on its limits and an
     angle handle (Fusion's disc) stands round the joint's axis. Tick Maximum: it becomes
     the row the drag sets. Drag the disc round to about 90: the block turns with it and
     Maximum follows (about 90); a faint ghost of the block shows at the maximum.
  B  Tick Minimum, drag the disc to about -45: Minimum follows, the block turns; two ghosts.
  C  OK: the joint keeps Minimum about -45 and Maximum about 90; no ghost or handle is
     left in the view. Ctrl+Z: no limits again.
  D  Edit Joint Limits again, tick Maximum, drag the block itself (not the handle) round
     its axis to about 60: it turns with the pointer, Maximum follows, the handle goes round
     with it, the joint was not picked anew. Cancel: the joint has no limits and the block is
     where it was before the dialog.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import widget_input as w

state = {}


def joint():
    found = j.joint_list()
    return found[0] if found else None


def drag():
    p = j.panel()
    return getattr(p, "limit_drag", None) if p is not None else None


def turn_to(end, step=5.0):
    """Drag the angle disc round its arc to `end` degrees, the way a hand follows it."""
    d = drag()
    handle = d.handle_now() if d is not None else None
    if not h.check("the angle handle is there", handle is not None):
        return
    widget = h.gl_widget()
    start = handle.angle()
    count = max(1, int(abs(end - start) / step))
    pixels = [
        h.screen_point(handle.point_at(start + (end - start) * i / count)) for i in range(count + 1)
    ]
    h.move(pixels[0])
    QtTest.QTest.mousePress(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pixels[0])
    for pixel in pixels[1:]:
        pos = QtCore.QPointF(pixel)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            pos,
            QtCore.QPointF(widget.mapToGlobal(pixel)),
            QtCore.Qt.NoButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(widget, event)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(30)
    QtTest.QTest.mouseRelease(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pixels[-1])
    QtWidgets.QApplication.processEvents()


def drag_block(end, step=6.0):
    """Press on the block's top face (away from the handle) and drag it round the joint's
    axis by `end` degrees, the way a hand would."""
    from sciforge import joints

    jt = joint()
    jcs2 = joints.jcs_global(jt, 1)
    center = jcs2.Base
    axis = jcs2.Rotation.multVec(App.Vector(0, 0, 1))
    top = max(j.block().Shape.Faces, key=lambda f: f.CenterOfMass.dot(axis))
    grab = top.CenterOfMass
    lever = grab - center
    lever = lever - axis * lever.dot(axis)
    if lever.Length < 3.0:  # the top's centre is on the axis: grab nearer a corner
        corner = max(top.Vertexes, key=lambda v: (v.Point - grab).Length).Point
        grab = grab + (corner - grab) * 0.6
    state["grab"] = grab
    widget = h.gl_widget()
    count = max(1, int(abs(end) / step))
    pixels = []
    for i in range(count + 1):
        turn = App.Rotation(axis, end * i / count)
        pixels.append(h.screen_point(center + turn.multVec(grab - center)))
    h.move(pixels[0])
    QtTest.QTest.mousePress(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pixels[0])
    for pixel in pixels[1:]:
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            QtCore.QPointF(pixel),
            QtCore.QPointF(widget.mapToGlobal(pixel)),
            QtCore.Qt.NoButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(widget, event)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(30)
    QtTest.QTest.mouseRelease(widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pixels[-1])
    QtWidgets.QApplication.processEvents()


def tick(key):
    p = j.panel()
    if h.check("joint dialog open", p is not None):
        w.click(p.angle_limits.rows[key][0])


def angle_now():
    from sciforge import joints

    return joints.value(joint())[0]


def ghost_count():
    d = drag()
    return d.ghost_count() if d is not None else 0


def in_view_names():
    root = Gui.ActiveDocument.ActiveView.getSceneGraph()
    return [root.getChild(i).getName().getString() for i in range(root.getNumChildren())]


# -- setup -----------------------------------------------------------------------------------------
def revolute():
    p = j.panel()
    if h.check("joint dialog", p is not None):
        j.click_tab(p, "Motion")
        j.choose_type(p, "Revolute")


def ok():
    j.ok()


def made():
    h.check("one joint", joint() is not None, j.row_labels())
    state["start"] = App.Placement(j.block().Placement)


# -- A ---------------------------------------------------------------------------------------------
def a_open():
    t.row_menu(joint().Label, "Edit Joint Limits")


def a_handle():
    p = j.panel()
    h.check("A: Edit Joint Limits opens", p is not None and p.tabs.currentIndex() == 1)
    d = drag()
    handle = d.handle_now() if d is not None else None
    h.check(
        "A: an angle handle round the joint's axis",
        handle is not None and hasattr(handle, "angle"),
    )
    h.shot("A-handle")


def a_tick_max():
    tick("max")


def a_max_current():
    d = drag()
    h.check(
        "A: Maximum is the row the drag sets",
        d is not None and d.focus_row() == ("deg", "max"),
        d and d.focus_row(),
    )


def a_drag():
    turn_to(90.0)


def a_dragged():
    p = j.panel()
    value = p.angle_limits.rows["max"][1].value()
    h.check("A: Maximum follows the drag (about 90)", abs(value - 90.0) < 4.0, value)
    a = angle_now()
    d = drag()
    h.check("A: the block turned with it", abs(a - value) < 1.0, (a, value, d and d.trace[-6:]))
    h.check("A: a ghost at the maximum", ghost_count() == 1, ghost_count())
    h.shot("A-max")


# -- B ---------------------------------------------------------------------------------------------
def b_tick_min():
    tick("min")


def b_drag():
    turn_to(-45.0)


def b_dragged():
    p = j.panel()
    value = p.angle_limits.rows["min"][1].value()
    h.check("B: Minimum follows the drag (about -45)", abs(value + 45.0) < 4.0, value)
    h.check("B: two ghosts", ghost_count() == 2, ghost_count())
    state["min"], state["max"] = value, p.angle_limits.rows["max"][1].value()
    h.shot("B-min")


# -- C ---------------------------------------------------------------------------------------------
def c_ok():
    j.ok()


def c_done():
    jt = joint()
    h.check("C: the dialog closed", j.panel() is None)
    h.check(
        "C: Minimum kept",
        jt.EnableAngleMin and abs(jt.AngleMin.Value - state["min"]) < 1e-6,
        jt.AngleMin,
    )
    h.check(
        "C: Maximum kept",
        jt.EnableAngleMax and abs(jt.AngleMax.Value - state["max"]) < 1e-6,
        jt.AngleMax,
    )
    names = in_view_names()
    h.check("C: no ghost left in the view", "SciForgeHoverGhost" not in names, names)
    s.no_popups("C")


def c_undo():
    s.undo()


def c_undone():
    jt = joint()
    h.check("C: Ctrl+Z: no limits", not jt.EnableAngleMin and not jt.EnableAngleMax)


# -- D ---------------------------------------------------------------------------------------------
def d_open():
    state["before"] = App.Placement(j.block().Placement)
    state["refs"] = (str(joint().Reference1), str(joint().Reference2))
    t.row_menu(joint().Label, "Edit Joint Limits")


def d_tick():
    tick("max")
    state["d_start"] = angle_now()


def d_drag():
    drag_block(60.0)


def d_dragged():
    p = j.panel()
    value = p.angle_limits.rows["max"][1].value()
    want = state["d_start"] + 60.0
    h.check(
        "D: dragging the block turns it (about 60)",
        abs(angle_now() - want) < 4.0,
        (angle_now(), want),
    )
    h.check("D: Maximum follows the block", abs(value - angle_now()) < 1.0, (value, angle_now()))
    d = drag()
    handle = d.handle_now() if d is not None else None
    h.check(
        "D: the handle went round with it",
        handle is not None and abs(handle.angle() - angle_now()) < 1.0,
        handle and handle.angle(),
    )
    h.check(
        "D: the press on the block was not a new pick",
        (str(joint().Reference1), str(joint().Reference2)) == state["refs"],
        (joint().Reference1, joint().Reference2),
    )
    h.shot("D-block")


def d_cancel():
    j.cancel()


def d_cancelled():
    jt = joint()
    h.check("D: Cancel: still no limits", not jt.EnableAngleMax and not jt.EnableAngleMin)
    h.check(
        "D: the block is back where it was",
        j.block().Placement.isSame(state["before"], 1e-6),
        (j.block().Placement, state["before"]),
    )
    names = in_view_names()
    h.check("D: no ghost left in the view", "SciForgeHoverGhost" not in names, names)


h.run(
    "joints_limits_drag",
    [s.new_design("JointLimitsDrag")]
    + j.two_boxes()
    + j.pick_pair("p")
    + [revolute, ok, made]
    + [a_open, a_handle, a_tick_max, a_max_current, a_drag, a_dragged]
    + [b_tick_min, b_drag, b_dragged]
    + [c_ok, c_done, c_undo, c_undone]
    + [d_open, d_tick, d_drag, d_dragged, d_cancel, d_cancelled],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real mouse input on SciForge's ViewCube, for the viewcube_*.py scenarios.

The cube is a small widget over the top-right of the 3D view. These helpers aim where a
person aims (the middle of the part or button they see: `cube().targets()`) and send Qt
test events to the cube widget, so its own hit-testing, click/drag logic and menu run
exactly as for a person.

    vc.click("front")              # the FRONT face
    vc.click("top-front")          # the edge between TOP and FRONT
    vc.drag("top", 60, 0)          # drag the cube 60 px to the right
    vc.choose(["Set Current View as Home", "Fit to View"])   # right-click menu
"""
import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h

V = App.Vector
LEFT = QtCore.Qt.LeftButton
NONE = QtCore.Qt.NoModifier
SQ2 = math.sqrt(2.0)
SQ3 = math.sqrt(3.0)


def _process():
    QtWidgets.QApplication.processEvents()


def cube():
    """The ViewCube widget of the active 3D view (None when there is none)."""
    from sciforge import viewcube_ui

    return viewcube_ui.cube_of(h.view())


def point(name):
    """Widget pixel a person aims at to click `name` (a cube part or a button)."""
    widget = cube()
    if widget is None:
        h.check("the ViewCube is there", False)
        return None
    widget.sync(h.view())
    targets = widget.targets()
    if name not in targets:
        h.check("%s can be clicked on the cube" % name, False, sorted(targets))
        return None
    x, y = targets[name]
    return QtCore.QPoint(int(round(x)), int(round(y)))


def hover(name):
    """The mouse moves onto the part or button `name` (through the window system, which
    also tells the cube the mouse came in), and Qt has been told before anything else
    happens. Should the cube still not have taken it (seen under xvfb when the next input
    came before the window system's move), the move is given to the cube directly, and the
    run log says so."""
    pos = point(name)
    if pos is None:
        return None
    widget = cube()
    h.pointer_to(widget, pos)  # (Qt has been told of the move when this returns)
    if widget.hover != name:
        top = QtWidgets.QApplication.widgetAt(widget.mapToGlobal(pos))
        print(
            "[SciForge] %s: the mouse move onto %s did not reach the cube (on top there: %s,"
            " cube hover %s, mouse grabber %s, buttons %s, popup %s); moved again directly"
            % (
                h.state.get("name"),
                name,
                top.objectName() or top.metaObject().className() if top else None,
                widget.hover,
                QtWidgets.QWidget.mouseGrabber(),
                QtWidgets.QApplication.mouseButtons(),
                QtWidgets.QApplication.activePopupWidget(),
            ),
            flush=True,
        )
        if not widget.inside:
            enter = QtGui.QEnterEvent(
                QtCore.QPointF(pos), QtCore.QPointF(pos), QtCore.QPointF(widget.mapToGlobal(pos))
            )
            QtWidgets.QApplication.sendEvent(widget, enter)
        _send_move(widget, pos, QtCore.Qt.NoButton)
    return pos


def move_away():
    """The mouse goes back to the middle of the 3D view."""
    widget = h.gl_widget()
    h.pointer_to(widget, QtCore.QPoint(widget.width() // 2, widget.height() // 2))


def _send_move(widget, pos, buttons):
    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove,
        QtCore.QPointF(pos),
        QtCore.QPointF(widget.mapToGlobal(QtCore.QPointF(pos).toPoint())),
        QtCore.Qt.NoButton,
        buttons,
        NONE,
    )
    QtWidgets.QApplication.sendEvent(widget, event)
    _process()


def click(name, wiggle=0):
    """Click a part or button of the cube. `wiggle`: the mouse moves that many pixels
    between press and release (a shaky hand), which must still count as a click."""
    pos = hover(name)
    if pos is None:
        return False
    widget = cube()
    QtTest.QTest.mousePress(widget, LEFT, NONE, pos)
    end = pos
    if wiggle:
        end = QtCore.QPoint(pos.x() + wiggle, pos.y() + wiggle // 2)
        _send_move(widget, end, LEFT)
    QtTest.QTest.mouseRelease(widget, LEFT, NONE, end)
    _process()
    return True


def drag(name, dx, dy, steps=12):
    """Press on the cube part `name` and drag the mouse (dx, dy) pixels, then let go."""
    start = hover(name)
    if start is None:
        return False
    widget = cube()
    QtTest.QTest.mousePress(widget, LEFT, NONE, start)
    for i in range(1, steps + 1):
        pos = QtCore.QPointF(start.x() + dx * i / steps, start.y() + dy * i / steps)
        _send_move(widget, pos, LEFT)
    QtTest.QTest.mouseRelease(widget, LEFT, NONE, QtCore.QPoint(start.x() + dx, start.y() + dy))
    _process()
    return True


def _open_menu(widget, pos):
    """A right click: press/release, then the context-menu event the window system sends
    (unless the release already opened a menu)."""
    h.pointer_to(widget, pos)
    shown = h.menus_shown()
    QtTest.QTest.mousePress(widget, QtCore.Qt.RightButton, NONE, pos)
    QtTest.QTest.mouseRelease(widget, QtCore.Qt.RightButton, NONE, pos)
    _process()
    if h.menus_shown() > shown:
        return
    event = QtGui.QContextMenuEvent(
        QtGui.QContextMenuEvent.Mouse, pos, widget.mapToGlobal(pos), NONE
    )
    QtWidgets.QApplication.sendEvent(widget, event)


def choose(path, on="front"):
    """Right-click the cube (on the part `on`) and click through the menu: path is the
    list of entries, e.g. ["Go Home"] or ["Set Current View as Home", "Fixed Distance"].
    Returns {'ok': clicked, 'texts': entries of the first menu, 'checked': ticked ones}."""
    widget = cube()
    pos = point(on)
    result = {"ok": False, "texts": [], "checked": []}
    if widget is None or pos is None:
        return result

    def read(menu):
        result["texts"] = [
            (a.text().replace("&", "").strip(), a.isEnabled()) for a in menu.actions() if not a.isSeparator()
        ]
        result["checked"] = [a.text().replace("&", "").strip() for a in menu.actions() if a.isChecked()]

    result["ok"] = h.choose_from(
        lambda: _open_menu(widget, pos), list(path), "the ViewCube's menu", report=False, read=read
    )
    return result


def menu_texts(on="front"):
    return choose([], on)


# -- the camera ---------------------------------------------------------------------------


def orientation():
    return h.view().getCameraOrientation()


def axes():
    """(right, up, view direction) of the camera, as world vectors."""
    r = orientation()
    return r.multVec(V(1, 0, 0)), r.multVec(V(0, 1, 0)), r.multVec(V(0, 0, -1))


def looks_along(direction, tol=1e-4):
    want = V(direction)
    want.normalize()
    return (axes()[2] - want).Length < tol


def up_is(direction, tol=1e-4):
    want = V(direction)
    want.normalize()
    return (axes()[1] - want).Length < tol


def roll():
    """0 when the camera's sideways axis is level (no roll)."""
    return abs(axes()[0].z)


def z_up():
    """The camera is level and Z points up the screen."""
    right, up, _ = axes()
    return abs(right.z) < 1e-6 and up.z > 1e-6


def describe():
    right, up, view = axes()
    return "looking along %s, up %s, right %s" % (
        tuple(round(c, 4) for c in view),
        tuple(round(c, 4) for c in up),
        tuple(round(c, 4) for c in right),
    )


def turned(before, after=None):
    """Degrees between two camera orientations."""
    after = after or orientation()
    return math.degrees(before.inverted().multiply(after).Angle)


def animations(on):
    App.ParamGet("User parameter:BaseApp/Preferences/View").SetBool(
        "UseNavigationAnimations", bool(on)
    )
    _process()


# -- what the cube shows ------------------------------------------------------------------


def pixel(pos):
    """Colour (QColor, with alpha) the cube draws at widget pixel pos."""
    widget = cube()
    widget.repaint()
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(pos.x() * ratio), int(pos.y() * ratio))


def sample_point(name):
    """A pixel inside the cube part `name` but away from its label (the text is drawn
    across the middle of a face): 70% of the way from its middle to one of its corners."""
    widget = cube()
    for part in widget.parts:
        if part["name"] == name:
            cx = sum(p[0] for p in part["points"]) / len(part["points"])
            cy = sum(p[1] for p in part["points"]) / len(part["points"])
            vx, vy = part["points"][0]
            return QtCore.QPoint(int(round(cx + 0.7 * (vx - cx))), int(round(cy + 0.7 * (vy - cy))))
    h.check("%s is drawn on the cube" % name, False, [p["name"] for p in widget.parts])
    return QtCore.QPoint(0, 0)


def is_blue(colour):
    """SciForge's hover blue (#6fb7f0), possibly seen through (idle) - not the grey cube."""
    return colour.blue() > colour.red() + 40 and colour.blue() > 150


def setup(doc_name):
    """SciForge on, a new design with a 40 x 30 x 10 block, the isometric view, fitted."""
    from sciforge import commands, extrude, sketch_ui

    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument(doc_name)
    body = commands.ensure_body()
    sk = sketch_ui.create_sketch(body, (sketch_ui.origin_planes(body)["XY_Plane"], ""))
    h.draw_rectangle(sk, 0, 0, 40, 30)
    extrude.make(body, sk, {"distance": 10.0})
    App.ActiveDocument.recompute()
    h.fit()

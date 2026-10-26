# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared steps and helpers for the VEX scenarios (scenarios/vex_*.py): SciForge's own VEX-like
parts (SciForgeTests/fixtures/vex/vex_parts.py, made from VEX's published numbers, never
VEX's files) inserted from STEP files, the hover over square holes, real clicks.

Kept outside scenarios/ because every file there is run as a scenario.
"""

import os
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.fixtures.vex import vex_parts as vp
from SciForgeTests.gui import harness as h

V = App.Vector
IN = vp.IN
T = vp.AL  # aluminium thickness (the web's top face is at z = T)
PITCH = vp.PITCH


# -- the parts -------------------------------------------------------------------------------------
def folder():
    return vp.default_folder()


def step_file(name):
    """The STEP file of one of SciForge's VEX-like test parts (made once per test folder)."""
    return vp.write_all(folder(), [name])[name]


def step_files(names):
    return vp.write_all(folder(), list(names))


def insert(name, placement=None, doc=None):
    """Insert a part's STEP file as a component (what Insert STEP does, without its Move
    dialog), placed at `placement`. Returns the component."""
    from sciforge import exchange_core, step_import

    doc = doc or App.ActiveDocument
    doc.openTransaction("Insert STEP")
    made = step_import.import_file(doc, step_file(name), exchange_core.INSERT)
    doc.commitTransaction()
    comp = made.top
    if placement is not None:
        comp.Placement = placement
    doc.recompute()
    step_import.apply_looks(made)
    return comp


def flipped(x, y, z):
    """Upside down (turned half a turn about X), standing at (x, y, z)."""
    return App.Placement(V(x, y, z), App.Rotation(V(1, 0, 0), 180))


def body_of(comp):
    from sciforge import components

    found = components.bodies_in(comp.Document, comp, recursive=True)
    return found[0] if found else None


def bbox(comp):
    """A component's box in design coordinates."""
    from sciforge import bodies

    body = body_of(comp)
    return bodies.global_shape(body).BoundBox


def axis_xy(comp):
    box = bbox(comp)
    return V((box.XMin + box.XMax) / 2.0, (box.YMin + box.YMax) / 2.0, 0)


def hole_centre(i, j=0, top=True, origin=None):
    """The centre of a channel's web hole (i along X, j across), in design coordinates
    (the channel at `origin`, default the design's origin)."""
    p = V(PITCH / 2.0 + i * PITCH, PITCH / 2.0 + j * PITCH, T if top else 0.0)
    return origin.multVec(p) if origin is not None else p


# -- the view and the mouse ------------------------------------------------------------------------
def fit():
    h.fit()
    wait(150)


def wait(ms):
    QtTest.QTest.qWait(ms)
    QtWidgets.QApplication.processEvents()


def look_at(point, size):
    """Zoom the view onto `point` so about `size` mm show across its height (a person
    zooming onto a small part before clicking it); the camera keeps its direction."""
    import math

    from pivy import coin

    view = h.view()
    cam = view.getCameraNode()
    d = view_direction()
    if cam.isOfType(coin.SoOrthographicCamera.getClassTypeId()):
        dist = max(float(cam.focalDistance.getValue()), size * 4.0)
        cam.height.setValue(size)
    else:
        angle = float(cam.heightAngle.getValue())
        dist = size / (2.0 * math.tan(angle / 2.0))
    pos = point - d * dist
    cam.position.setValue(pos.x, pos.y, pos.z)
    cam.focalDistance.setValue(dist)
    wait(150)


def view_direction():
    """The direction the camera looks (from the camera into the design)."""
    return V(h.view().getViewDirection())


def toward_viewer(centre, distance):
    """A point `distance` from `centre` on the floor plane, on the camera's side (in front of
    whatever stands at `centre`)."""
    d = view_direction()
    flat = V(d.x, d.y, 0)
    if flat.Length < 1e-9:
        flat = V(0, 1, 0)
    flat.normalize()
    return centre - flat * distance


def hover(point, modifiers=QtCore.Qt.NoModifier):
    """The mouse to `point` with `modifiers` held (a move carries the keys held, as a real
    one does), then time for the hover to look."""
    from PySide import QtGui

    h.uncover(point)
    widget = h.gl_widget()
    pixel = h.screen_point(point)
    if modifiers == QtCore.Qt.NoModifier:
        h.move(pixel)
    else:
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            QtCore.QPointF(pixel),
            QtCore.QPointF(widget.mapToGlobal(pixel)),
            QtCore.Qt.NoButton,
            QtCore.Qt.NoButton,
            modifiers,
        )
        QtWidgets.QApplication.sendEvent(widget, event)
    for _ in range(6):
        QtTest.QTest.qWait(40)
        QtWidgets.QApplication.processEvents()


def hover_pixel(pixel):
    h.move(pixel)
    for _ in range(6):
        QtTest.QTest.qWait(40)
        QtWidgets.QApplication.processEvents()


def ctrl(down):
    key = QtTest.QTest.keyPress if down else QtTest.QTest.keyRelease
    key(
        h.gl_widget(),
        QtCore.Qt.Key_Control,
        QtCore.Qt.ControlModifier if down else QtCore.Qt.NoModifier,
    )
    QtWidgets.QApplication.processEvents()


def shift(down):
    key = QtTest.QTest.keyPress if down else QtTest.QTest.keyRelease
    key(
        h.gl_widget(),
        QtCore.Qt.Key_Shift,
        QtCore.Qt.ShiftModifier if down else QtCore.Qt.NoModifier,
    )
    QtWidgets.QApplication.processEvents()


def click_pixel(pixel, modifiers=QtCore.Qt.NoModifier):
    h.move(pixel)
    QtTest.QTest.mouseClick(h.gl_widget(), QtCore.Qt.LeftButton, modifiers, pixel)
    QtWidgets.QApplication.processEvents()


def lit(hover_obj, where, kinds, point=None, tol=1e-5):
    """Check the dot the click would take: its kind (one of `kinds`) and place."""
    if isinstance(kinds, str):
        kinds = (kinds,)
    hot = getattr(hover_obj, "hot", None) if hover_obj is not None else None
    ok = hot is not None and hot["kind"] in kinds
    if ok and point is not None:
        ok = (hot["point"] - point).Length < tol
    return h.check(
        "%s: %s lit%s" % (where, "/".join(kinds), "" if point is None else " at %s" % _fmt(point)),
        ok,
        hot and (hot["kind"], _fmt(hot["point"])),
    )


def _fmt(v):
    return "(%.3f, %.3f, %.3f)" % (v.x, v.y, v.z)


def drawn(hover_obj):
    """How many dots the hover draws now."""
    try:
        return len(hover_obj._drawn or ())
    except Exception:
        return -1


# -- dialogs ---------------------------------------------------------------------------------------
def panel():
    from sciforge import taskui

    return taskui.current()


def joint_panel():
    from sciforge import joints_ui

    p = joints_ui.JointPanel.last
    return None if p is None or p._closed else p


def joints_list():
    from sciforge import joints

    return joints.joints(App.ActiveDocument)


def ok():
    h.task_button("OK")


def cancel():
    h.task_button("Cancel")


def undo():
    from SciForgeTests.gui import dialog_input

    h.check("Undo button", dialog_input.quick_access("Undo"))


def redo():
    from SciForgeTests.gui import dialog_input

    h.check("Redo button", dialog_input.quick_access("Redo"))


def menu(group, label):
    from SciForgeTests.gui import sketch_input

    return sketch_input.menu_item(group, label)


def no_popups(where):
    h.check("no pop-up after %s" % where, not h.popups(), h.popups())


def near_xy(a, b, tol=1e-4):
    return abs(a.x - b.x) <= tol and abs(a.y - b.y) <= tol


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, time.perf_counter() - t0


def save_as(name):
    import tempfile

    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-vex-"), name + ".FCStd")
    App.ActiveDocument.saveAs(path)
    return path


def new_design(name):
    def step():
        Gui.activateWorkbench("SciForgeWorkbench")
        App.newDocument(name)
        h.fit()

    step.__name__ = "new_design_" + name
    return step

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real-input helpers for the SIMULATION workspace's SETUP scenarios (scenarios/sim_*.py, builder
sim-ui). Kept outside scenarios/ because every file there runs as a scenario.

Everything acts like a person: the workspace button's menu, the ribbon's SETUP buttons, clicks
on faces in the 3D view (aimed until the face is under the mouse, as a person moves the mouse
until the face lights up), typing in the dialogs' fields, the browser's rows (right-click
menus, double-clicks), Esc / Enter / Ctrl+Z on the keyboard. The parts are built by script."""

import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import widget_input as w

V = App.Vector


def _process():
    QtWidgets.QApplication.processEvents()


# -- parts ----------------------------------------------------------------------------------------
def _box(body, kind, name, size, at):
    obj = body.newObject("PartDesign::%sBox" % kind, name)
    obj.Length, obj.Width, obj.Height = size
    obj.Placement = App.Placement(V(*at), App.Rotation())
    body.Tip = obj
    return obj


def _hole(body, name, at, radius, height):
    obj = body.newObject("PartDesign::SubtractiveCylinder", name)
    obj.Radius = radius
    obj.Height = height
    obj.Placement = App.Placement(V(*at), App.Rotation())
    body.Tip = obj
    return obj


def bracket(doc, label="Bracket"):
    """An L bracket: a plate 80 x 30 x 6 with two holes (diameter 8 at x 10, y 8 and 22) and
    an arm 6 x 30 x 30 standing at its far end (x 74..80). Fixed at its holes, pushed on the
    arm's top face (z 36)."""
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = label
    _box(body, "Additive", "Plate", (80, 30, 6), (0, 0, 0))
    _box(body, "Additive", "Arm", (6, 30, 30), (74, 0, 6))
    _hole(body, "HoleA", (10, 8, 0), 4.0, 6.0)
    _hole(body, "HoleB", (10, 22, 0), 4.0, 6.0)
    doc.recompute()
    return body


def block(doc, label, size, at):
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = label
    _box(body, "Additive", "Box", size, at)
    doc.recompute()
    return body


def new_bracket(name="SimBracket"):
    def new_bracket():
        Gui.activateWorkbench("SciForgeWorkbench")
        doc = App.newDocument(name)
        bracket(doc)
        h.fit()

    new_bracket.__name__ = "new_bracket_" + name
    return new_bracket


def doc():
    return App.ActiveDocument


def body(label="Bracket"):
    for obj in doc().Objects:
        if obj.TypeId == "PartDesign::Body" and obj.Label == label:
            return obj
    return None


def face_named(body_obj, test):
    """The name of the first face of the body for which test(face) is true."""
    for i, face in enumerate(body_obj.Shape.Faces, 1):
        try:
            if test(face):
                return "Face%d" % i
        except Exception:
            continue
    return None


def hole_faces(body_obj):
    """The two hole walls of the bracket."""
    out = []
    for i, face in enumerate(body_obj.Shape.Faces, 1):
        if "Cylinder" in face.Surface.TypeId:
            out.append("Face%d" % i)
    return out


def arm_top(body_obj):
    return face_named(
        body_obj,
        lambda f: "Plane" in f.Surface.TypeId
        and abs(f.CenterOfMass.z - 36.0) < 1e-6
        and abs(f.Area - 180.0) < 1e-3,
    )


def plate_top(body_obj):
    """The plate's top face (z 6), seen from the default view."""
    return face_named(
        body_obj,
        lambda f: "Plane" in f.Surface.TypeId
        and abs(f.BoundBox.ZMax - 6.0) < 1e-6
        and abs(f.BoundBox.ZMin - 6.0) < 1e-6,
    )


def plate_bottom(body_obj):
    return face_named(
        body_obj, lambda f: "Plane" in f.Surface.TypeId and abs(f.BoundBox.ZMax) < 1e-6
    )


# -- clicking a face like a person ----------------------------------------------------------------
def _face_points(face, count=7):
    """Points on the face, the ones farthest from its edges first (a click near an edge picks
    the edge: FreeCAD picks edges within a few pixels)."""
    import Part

    pts = []
    u0, u1, v0, v1 = face.ParameterRange
    for i in range(count):
        for j in range(count):
            u = u0 + (u1 - u0) * (i + 0.5) / count
            v = v0 + (v1 - v0) * (j + 0.5) / count
            if face.isPartOfDomain(u, v):
                pts.append(face.valueAt(u, v))
    try:
        wires = Part.Compound(face.Edges)
        pts.sort(key=lambda p: -wires.distToShape(Part.Vertex(p))[0])
    except Exception:
        pass
    return pts


def aim(body_obj, face_name):
    """A 3D point on the face where the face itself is under the mouse, or None."""
    face = body_obj.Shape.getElement(face_name)
    tip = body_obj.Tip
    for point in _face_points(face):
        hit = h.under_mouse(point)
        if not hit:
            continue
        obj, comp = hit
        if comp == face_name and obj in (tip.Name, body_obj.Name):
            return point
    return None


def click_face(body_obj, face_name):
    """Click the face (aimed until it is under the mouse). True when it was clickable."""
    point = aim(body_obj, face_name)
    if point is None:
        h.check("face %s of %s can be clicked" % (face_name, body_obj.Label), False)
        return False
    h.click(point)
    return True


# -- workspace, ribbon, dialogs -------------------------------------------------------------------
def workspace(label):
    """The workspace button's menu > label (drawing_input.workspace: the entry lit under the
    pointer, then clicked). Simulation and Design: the workspace has switched before this
    returns. (It once fell back to the keys when the click did not take under xvfb: the
    pointer moves Qt had not seen yet, fixed in the harness; a lost click now fails here.)"""
    from SciForgeTests.gui import drawing_input as d
    from sciforge import simulation_ui

    ok = d.workspace(label)
    _process()
    if ok and label in ("Simulation", "Design"):
        want = label == "Simulation"
        h.wait_for(lambda: simulation_ui.in_workspace() == want, "the %s workspace to show" % label)
    return ok


def ribbon_ui():
    from sciforge import shell

    return shell.ribbon()


def tab_visible(tab_id):
    button = ribbon_ui().tab_buttons.get(tab_id)
    return button is not None and button.isVisible()


def current_tab():
    return ribbon_ui().current_tab()


def tick_row(table, row):
    """Click the tick box at the start of a table row, as a person would (the Solve dialog's
    studies); the Space key on the row when the click did not take (a table laid out late)."""
    item = table.item(row, 0)
    if item is None:
        return False
    before = item.checkState()
    _process()
    table.scrollToItem(item)
    rect = table.visualItemRect(item)
    QtTest.QTest.mouseClick(
        table.viewport(),
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
        QtCore.QPoint(rect.left() + 10, rect.center().y()),
    )
    _process()
    if item.checkState() == before:
        table.setFocus()
        table.setCurrentCell(row, 0)
        QtTest.QTest.keyClick(table, QtCore.Qt.Key_Space)
        _process()
    return item.checkState() != before


def click_tab(tab_id):
    """Click a ribbon tab (SETUP: "sim_setup", RESULTS: "sim_results") with the mouse."""
    button = ribbon_ui().tab_buttons.get(tab_id)
    if button is None or not button.isVisible():
        h.check("tab %s shown" % tab_id, False)
        return False
    w.click(button)
    return True


def workspace_text():
    return ribbon_ui().workspace.text()


def timeline_visible():
    dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "SciForgeTimelineDock")
    return dock is not None and dock.isVisible()


def item_panel():
    from sciforge import simulation_panels

    p = simulation_panels.ItemPanel.last
    return p if p is not None and not p._closed else None


def task_panel():
    from sciforge import taskui

    return taskui.current()


def new_study_dialog():
    from sciforge import simulation_dialogs

    return simulation_dialogs.new_study_dialog()


def child(widget, name, kind=QtWidgets.QWidget):
    return widget.findChild(kind, name) if widget is not None else None


def panel_field(name, kind=QtWidgets.QWidget):
    """A widget of the open task dialog by object name."""
    current = task_panel()
    form = getattr(current, "form", None)
    return child(form, name, kind)


def type_in(name, text):
    field = panel_field(name, QtWidgets.QLineEdit)
    if field is None:
        h.check("field %s in the dialog" % name, False)
        return False
    ui.type_into(field, text)
    return True


def choose(name, text):
    box = panel_field(name, QtWidgets.QComboBox)
    if box is None:
        h.check("drop-down %s in the dialog" % name, False)
        return False
    return ui.choose(box, text)


def click_widget(widget):
    if widget is None:
        return False
    w.click(widget)
    return True


def menu_item(group, label):
    """GROUP > label in the ribbon (the group's name opens its menu), with the mouse. The
    pointer first goes over the 3D view, as a person's does: QMenu ignores a click on an
    entry when the pointer has not moved since the menu opened (it rested on that very
    entry after the same click a moment before: DISPLAY > Show Mesh twice)."""
    from SciForgeTests.gui import sketch_input

    try:
        gl = h.gl_widget()
        QtGui.QCursor.setPos(gl.mapToGlobal(QtCore.QPoint(gl.width() // 2, gl.height() // 2)))
        QtTest.QTest.mouseMove(gl, QtCore.QPoint(gl.width() // 2, gl.height() // 2))
        _process()
    except Exception:
        pass
    return sketch_input.menu_item(group, label)


def ok():
    return h.task_button("OK")


def cancel():
    return h.task_button("Cancel")


def esc():
    h.press(QtCore.Qt.Key_Escape)


def undo():
    """The application bar's Undo (as a person clicks it)."""
    h.check("Undo button", ui.quick_access("Undo"))


def redo():
    h.check("Redo button", ui.quick_access("Redo"))


def undo_key():
    """Ctrl+Z over the 3D view."""
    h.press(QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)


def message():
    """The open task dialog's message line."""
    current = task_panel()
    try:
        return current.message.text() if current is not None else ""
    except RuntimeError:
        return ""


def tooltip_text():
    return QtWidgets.QToolTip.text() if QtWidgets.QToolTip.isVisible() else ""


def told():
    """The last sentence a command told next to the pointer (commands.tell), even once its
    tip has gone."""
    from sciforge import commands

    return (getattr(commands, "_TOLD", None) or {}).get("msg") or ""


# -- the study ------------------------------------------------------------------------------------
def sim():
    from sciforge import simulation

    return simulation


def studies():
    return sim().studies(doc()) if doc() is not None else []


def active_study():
    from sciforge import simulation_ui

    return simulation_ui.active_study(doc())


def items(category=None):
    study = active_study()
    return sim().items(study, category) if study is not None else []


def light():
    from sciforge import simulation_ui

    return simulation_ui.light()


def precheck_button():
    for button in ribbon_ui().findChildren(QtWidgets.QToolButton):
        if button.objectName() == "SciForgeBig_Pre-check" and button.isVisible():
            return button
    return None


# -- the browser ----------------------------------------------------------------------------------
def browser():
    from sciforge import browser_ui

    return browser_ui.widget()


def browser_labels():
    tree = browser()
    tree.refresh(force=True)
    return tree.labels()


def browser_row(label):
    tree = browser()
    tree.refresh(force=True)
    _process()
    item = tree.row(label)
    if item is not None:
        tree.scrollToItem(item)
        _process()
        # (the browser may have been rebuilt while events ran: its row of now)
        item = tree.row(label)
    return item


def row_node(label):
    item = browser_row(label)
    from sciforge.browser_ui import ROLE_NODE

    return item.data(1, ROLE_NODE) if item is not None else None


def _row_pos(label):
    """(tree, position of the row `label`) or (tree, None); the row is found again when the
    browser was rebuilt in between (it refreshes itself after a change)."""
    tree = browser()
    for _try in range(3):
        item = browser_row(label)
        if item is None:
            return tree, None
        try:
            return tree, w.tree_row_pos(tree, item)
        except RuntimeError:  # (rebuilt while the row was being found)
            continue
    return tree, None


def right_click_row(label, entry):
    tree, pos = _row_pos(label)
    if pos is None:
        h.check("browser row %s" % label, False, browser_labels())
        return False
    ok = w.right_click(tree.viewport(), pos, entry)
    h.check("right-click %s > %s" % (label, entry), ok)
    return ok


def menu_entries(label):
    tree, pos = _row_pos(label)
    if pos is None:
        return []
    return [t for t, _enabled in w.menu_texts(tree.viewport(), pos)]


def double_click_row(label):
    tree, pos = _row_pos(label)
    if pos is None:
        h.check("browser row %s" % label, False, browser_labels())
        return False
    w.double_click(tree.viewport(), pos)
    return True


def click_row(label):
    tree, pos = _row_pos(label)
    if pos is None:
        h.check("browser row %s" % label, False, browser_labels())
        return False
    w.click(tree.viewport(), pos)
    return True


# -- solving --------------------------------------------------------------------------------------
def solve_dialog():
    from sciforge import simulation_solve_dialog

    return simulation_solve_dialog.solve_dialog()


def status_dialog():
    from sciforge import simulation_solve_dialog

    return simulation_solve_dialog.status_dialog()


def solving():
    from sciforge import simulation_solve_dialog

    return simulation_solve_dialog.solving()


def solve_took_setup():
    """The running solve has taken the study as it solves it (its first stage, a moment after
    Go): a change made after this leaves the results out of date."""
    from sciforge import simulation_solve_dialog

    job = simulation_solve_dialog.RUN["job"]
    return job is not None and getattr(job, "_fingerprints", None) is not None


def wait_solved(name="wait_solved", seconds=180):
    """A step that waits until no solve (or mesh) runs (at most `seconds`)."""

    def step():
        pass

    step.__name__ = name
    step.done = lambda: not solving()
    step.done_what = "the solve (or mesh) to end"
    step.timeout_s = seconds
    return step


def popup_named(name):
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.isVisible() and widget.objectName() == name:
            return widget
    return None


def close_popup(name):
    widget = popup_named(name)
    if widget is not None:
        QtTest.QTest.keyClick(widget, QtCore.Qt.Key_Escape)
        _process()
        return True
    return False


def glyph_counts():
    from sciforge import simulation_glyphs

    return simulation_glyphs.counts()


def preview_count():
    from sciforge import simulation_glyphs

    return simulation_glyphs.preview_count()


# -- designs and their tabs ------------------------------------------------------------------------
def click_doc_tab(label):
    """Click the design's tab at the top (as a person switches designs)."""
    bar = h.document_tabs()
    if bar is None:
        h.check("document tabs", False)
        return False
    for index in range(bar.count()):
        if bar.tabText(index).replace("[*]", "").strip().startswith(label):
            w.click(bar, bar.tabRect(index).center())
            _process()
            return True
    h.check("a tab for %s" % label, False, [bar.tabText(i) for i in range(bar.count())])
    return False


def visible_face(body_obj, names):
    """The first of `names` (face names) that can be clicked from the view now."""
    for name in names:
        if name and aim(body_obj, name) is not None:
            return name
    return None


def side_faces(body_obj):
    """The body's flat faces, the largest first."""
    found = []
    for i, face in enumerate(body_obj.Shape.Faces, 1):
        if "Plane" in face.Surface.TypeId:
            found.append((face.Area, "Face%d" % i))
    return [n for _a, n in sorted(found, reverse=True)]


def top_face(body_obj):
    z = body_obj.Shape.BoundBox.ZMax
    return face_named(
        body_obj,
        lambda f: "Plane" in f.Surface.TypeId
        and abs(f.BoundBox.ZMin - z) < 1e-6
        and abs(f.BoundBox.ZMax - z) < 1e-6,
    )

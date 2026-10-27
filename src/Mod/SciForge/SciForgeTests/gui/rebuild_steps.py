# SPDX-License-Identifier: LGPL-2.1-or-later
"""Helpers of the Auto Timeline scenarios (scenarios/rebuild_*.py, builder at-tools, beta 3):
an imported STEP part (the plate below, made with OpenCASCADE and written to a STEP file,
then brought in with SciForge's own Insert STEP code: a body without a timeline), the tool
calls an AI makes (through the same executor the AI bridge uses), and what the window
shows (the reference's ghost and red / green overlay, the dialogs).

The plate: 60 x 40 x 10, four 6 mm holes at (10, 10), (50, 10), (10, 30), (50, 30) and its
four vertical corners rounded 3 mm. Volume 60*40*10 - 4*pi*9*10 - 4*(9 - 9*pi/4)*10 =
24000 - 1130.973 - 77.257 = 22791.770 mm3.
"""

import math
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import widget_input as w

V = App.Vector
PLATE_VOLUME = 24000 - 4 * math.pi * 9 * 10 - 4 * (9 - 9 * math.pi / 4) * 10
HOLES = ((10, 10), (50, 10), (10, 30), (50, 30))


def plate_shape():
    import Part

    box = Part.makeBox(60, 40, 10)
    holes = [Part.makeCylinder(3, 10, V(x, y, 0)) for x, y in HOLES]
    shape = box.cut(Part.makeCompound(holes)).removeSplitter()
    corners = [
        e
        for e in shape.Edges
        if e.Curve.TypeId == "Part::GeomLine"
        and abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1
        and (e.Vertexes[0].Point.x in (0, 60) and e.Vertexes[0].Point.y in (0, 40))
    ]
    return shape.makeFillet(3, corners)


def folder():
    path = os.path.join(h.OUT_DIR, "rebuild")
    os.makedirs(path, exist_ok=True)
    return path


def write_step(name="plate", shape=None):
    path = os.path.join(folder(), name + ".step")
    (shape or plate_shape()).exportStep(path)
    return path


def insert_step(doc, path):
    """Insert STEP's own code (step_import): a component with a body without timeline."""
    from sciforge import exchange_core, step_import

    made = step_import.import_file(doc, path, exchange_core.INSERT)
    doc.recompute()
    step_import.apply_looks(made)
    return made.bodies[0]


def new_design(name):
    from sciforge import commands

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument(name)
    commands.ensure_body()
    return doc


# -- the AI's tool calls (as through the AI bridge) ------------------------------------------------
_HOST = {"host": None}


def tool(name, **args):
    """One AI tool call in the window, like the AI bridge makes it; returns the answer."""
    from sciforge.ai import bridge, executor

    if _HOST["host"] is None:
        _HOST["host"] = bridge.GuiHost()
    return executor.run(name, args, _HOST["host"])


def tool_json(name, **args):
    import json

    answer = tool(name, **args)
    text = answer["text"]
    start = text.find("{")
    try:
        return answer, (json.loads(text[start:]) if start >= 0 else None)
    except ValueError:
        return answer, None


# -- what the window shows -------------------------------------------------------------------------
def references(doc=None):
    from sciforge import rebuild

    return rebuild.references(doc or App.ActiveDocument)


def view_of(ref):
    from sciforge import rebuild_ui

    return rebuild_ui.view_of(ref)


def ghost_drawn(ref):
    view = view_of(ref)
    return view is not None and view.ghost_shown()


def overlay_count(ref):
    view = view_of(ref)
    if view is None:
        return None
    try:
        return view.overlay.getNumChildren()
    except Exception:
        return None


def shown(obj):
    try:
        return bool(obj.ViewObject.Visibility)
    except Exception:
        return False


def timeline_names():
    from sciforge import timeline_ops

    return [i.name for i in timeline_ops.timeline(App.ActiveDocument).items]


def browser_labels():
    """Every row label of the browser."""
    from SciForgeTests.gui import timeline_input as t

    tree = t.tree()
    found = []

    def walk(item):
        for i in range(item.childCount()):
            child = item.child(i)
            found.append(child.text(1))
            walk(child)

    root = tree.invisibleRootItem()
    walk(root)
    return found


def browser_menu(label, entry):
    from SciForgeTests.gui import timeline_input as t

    return t.row_menu(label, entry)


def browser_entries(label):
    from SciForgeTests.gui import timeline_input as t

    return [text for text, _enabled in t.row_menu_entries(label)]


def dialog(name):
    """The visible top-level dialog with this object name, or None."""
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == name and widget.isVisible():
            return widget
    return None


def utilities_menu(label):
    """UTILITIES > AI > label, with the mouse (the group's menu)."""
    from SciForgeTests.gui import sketch_input as si

    tab("utilities")
    return si.menu_item("AI", label)


def tab(tab_id):
    from sciforge import shell

    w.click(shell.ribbon().tab_buttons[tab_id])


def select_body(body):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(body.Document.Name, body.Name)


def store_fake_key():
    """A configured chat AI (a key kept for Claude), as a person who set up the chat has."""
    from sciforge import secrets_store
    from sciforge.ai import chat_ui

    secrets_store.store(
        chat_ui.key_name("anthropic"), "sk-ant-TEST-rebuild", chat_ui.secrets_folder()
    )


def drop_fake_key():
    from sciforge import secrets_store
    from sciforge.ai import chat_ui

    secrets_store.delete(chat_ui.key_name("anthropic"), chat_ui.secrets_folder())
    for name in ("openai", "gemini"):
        secrets_store.delete(chat_ui.key_name(name), chat_ui.secrets_folder())
    App.ParamGet(chat_ui.PREFS).RemString("ChatAddress")


def close_dialogs():
    for name in (
        "SciForgeRebuildNoAI",
        "SciForgeRebuildCompare",
        "SciForgeRebuildFinish",
        "SciForgeRebuildRefused",
    ):
        found = dialog(name)
        if found is not None:
            found.reject()
    QtWidgets.QApplication.processEvents()


def click_button(widget, name):
    button = widget.findChild(QtWidgets.QAbstractButton, name) if widget is not None else None
    h.check("button %s is there" % name, button is not None and button.isVisible())
    if button is not None:
        w.click(button)
    return button


def esc(widget):
    from PySide6 import QtTest

    if widget is not None:
        QtTest.QTest.keyClick(widget, QtCore.Qt.Key_Escape)
        QtWidgets.QApplication.processEvents()


def open_marking_menu(point):
    """A right click on the 3D view at a design point; returns the marking menu."""
    from sciforge import marking_menu

    marking_menu._last_menu["widget"] = None
    gl = h.gl_widget()
    pos = h.screen_point(point)
    w.click(gl, pos, button=QtCore.Qt.RightButton)
    menu = marking_menu._last_menu["widget"]
    h.check("right click opens the marking menu", menu is not None and menu.isVisible())
    return menu


def marking_rows(menu):
    return [menu.list.item(i).text().split("    ")[0] for i in range(menu.list.count())]


def click_marking_row(menu, text):
    for i in range(menu.list.count()):
        row = menu.list.item(i)
        if row.text().split("    ")[0] == text:
            w.click(menu.list.viewport(), menu.list.visualItemRect(row).center())
            return True
    h.check("marking menu row %r exists" % text, False, marking_rows(menu))
    return False

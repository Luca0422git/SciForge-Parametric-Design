# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real mouse and keyboard input on Qt widgets (the timeline, the browser, menus),
for scenario tests. Same mechanism as harness.click() on the 3D view: Qt test
events delivered to the widget, so the widget's own event handlers run exactly as
for a person's click, drag or key press.

    right_click(widget, pos, "Suppress Features")   # opens the menu, clicks the entry
"""

from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h

LEFT = QtCore.Qt.LeftButton
NONE = QtCore.Qt.NoModifier


def _process():
    QtWidgets.QApplication.processEvents()


def center(widget):
    return widget.rect().center()


def move(widget, pos):
    """The pointer to `pos` of the widget, seen by Qt before the next input."""
    h.pointer_to(widget, pos)


def click(widget, pos=None, modifiers=NONE, button=LEFT):
    pos = center(widget) if pos is None else pos
    move(widget, pos)
    QtTest.QTest.mouseClick(widget, button, modifiers, pos)
    _process()


def double_click(widget, pos=None):
    """The events of a real double-click: press, release, double-click, release."""
    pos = center(widget) if pos is None else pos
    move(widget, pos)
    QtTest.QTest.mousePress(widget, LEFT, NONE, pos)
    QtTest.QTest.mouseRelease(widget, LEFT, NONE, pos)
    QtTest.QTest.mouseDClick(widget, LEFT, NONE, pos)
    QtTest.QTest.mouseRelease(widget, LEFT, NONE, pos)
    _process()


def _menu_action(menu, text):
    for action in menu.actions():
        if action.text().replace("&", "").strip() == text:
            return action
    return None


def _texts(menu):
    return [(a.text().replace("&", "").strip(), a.isEnabled()) for a in menu.actions() if not a.isSeparator()]


def menu_texts(widget, pos):
    """The entries of the right-click menu at pos (the menu is closed again with Esc)."""
    found = {}

    def read(menu):
        found["texts"] = _texts(menu)

    h.choose_from(lambda: _open_menu(widget, pos), [], "the right-click menu", report=False, read=read)
    return found.get("texts", [])


def right_click(widget, pos, choose):
    """Right-click at pos, then click the menu entry `choose` (like a person). Returns
    True if the entry was there and enabled. Esc closes the menu when choose is None."""
    return h.choose_from(
        lambda: _open_menu(widget, pos),
        [choose] if choose else [],
        "the right-click menu",
        report=False,
    )


def right_click_sub(widget, pos, top, choose):
    """Right-click at pos, open the submenu `top` (a person points at it) and click its entry
    `choose`. Returns True if both were there and enabled; result["texts"] lists the
    submenu's entries [(text, checked)] when it opened."""
    result = {"ok": False}

    def read(menu):
        result["seen"] = True
        result["top"] = menu
        action = h.find_entry(menu, top)
        if action is None or not action.isEnabled():
            result["texts"] = [a.text() for a in menu.actions()]
            return
        sub = h.submenu(menu, action)
        result["sub"] = sub
        h.light_entry(menu, action)
        h.wait_for(lambda: sub is not None and sub.isVisible(), "the submenu %s to open" % top)
        result["texts"] = [
            (a.text().replace("&", "").strip(), a.isChecked()) for a in sub.actions() if not a.isSeparator()
        ]

    result["ok"] = h.choose_from(
        lambda: _open_menu(widget, pos),
        [top, choose] if choose else [],
        "the right-click menu",
        report=False,
        read=read,
    )
    return result


def click_menu(button, choose):
    """Click a button that opens a menu (Home's ... of a place), then the entry `choose`.
    Returns True if the entry was there and enabled."""
    return h.choose_from(lambda: click(button), [choose], "the menu of %s" % h.describe(button), report=False)


def _open_menu(widget, pos):
    """A right button press/release, then the context-menu event the window system
    sends for it, unless the release already opened the menu."""
    move(widget, pos)
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


def drag(widget, start, end_global, steps=10):
    """Press on widget at start, move to end_global (screen coordinates), release."""
    move(widget, start)
    QtTest.QTest.mousePress(widget, LEFT, NONE, start)
    begin = widget.mapToGlobal(start)
    for i in range(1, steps + 1):
        g = QtCore.QPointF(
            begin.x() + (end_global.x() - begin.x()) * i / steps,
            begin.y() + (end_global.y() - begin.y()) * i / steps,
        )
        local = widget.mapFromGlobal(g.toPoint())
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove, QtCore.QPointF(local), g, QtCore.Qt.NoButton, LEFT, NONE
        )
        QtWidgets.QApplication.sendEvent(widget, event)
        _process()
    # The release goes through the window like the press did: a release sent straight to
    # the widget left Qt thinking the button was still down, and the next click anywhere
    # (a browser eye, a row) went to the dragged widget instead.
    local = widget.mapFromGlobal(end_global)
    QtTest.QTest.mouseRelease(widget, LEFT, NONE, local)
    _process()


def key(widget, k, modifiers=NONE):
    widget.setFocus()
    QtTest.QTest.keyClick(widget, k, modifiers)
    _process()


def type_text(widget, text):
    QtTest.QTest.keyClicks(widget, text)
    _process()


def tree_row_pos(tree, item, x=None):
    """Point inside a tree row (x from the row's left edge, default: the label)."""
    rect = tree.visualItemRect(item)
    return QtCore.QPoint(rect.left() + (x if x is not None else 40), rect.center().y())


def quick_access(tooltip_start):
    """The quick-access button (Undo, Redo...) whose tooltip starts with the text."""
    import FreeCADGui as Gui

    main = Gui.getMainWindow()
    for button in main.findChildren(QtWidgets.QToolButton):
        if button.isVisible() and button.toolTip().startswith(tooltip_start):
            return button
    return None

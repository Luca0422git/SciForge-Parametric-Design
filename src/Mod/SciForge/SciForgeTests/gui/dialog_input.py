# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real keyboard/mouse input on dialog widgets for scenario tests (Extrude, Press Pull).

harness.py drives the 3D view, the ribbon and the OK/Cancel buttons. Fusion's dialogs
also have drop-downs, number fields, selection boxes and the timeline; these helpers
operate them the way a person does (clicks and key presses through Qt), never by
setting values in code. Not a scenario itself (it lives outside scenarios/).
"""

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h


def _process():
    QtWidgets.QApplication.processEvents()


def choose(combo, text):
    """Pick `text` in a drop-down with the keyboard (Up/Down, like a person who clicked it).
    The keys wait until the list shows (it may open late on a slow machine: CI #110's
    fillet_qa_more P17 lost its keys once). (The pointer stays where it is: a list that
    opens under the pointer follows it, and Down would start from the hovered row.)"""
    target = combo.findText(text)
    if target < 0:
        raise ValueError("%r is not in the drop-down %s" % (text, combo.objectName()))
    if not combo.isEnabled():
        h.check("the drop-down %s takes a choice (%s)" % (combo.objectName(), text), False, "greyed out")
        return False
    # No shortcut when it already shows `text`: choosing it again is a real choice (Extrude,
    # Revolve, Sweep, Loft, Pipe and the primitives lock a picked Operation on `activated`).
    combo.setFocus()
    QtTest.QTest.mouseClick(combo, QtCore.Qt.LeftButton)  # opens the list
    view = combo.view()
    h.wait_for(view.isVisible, "the list of %s to open" % (combo.objectName() or "a drop-down"))
    _step(view, target - combo.currentIndex())
    QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return)
    _process()
    if combo.currentText() != text:
        if view.isVisible():
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Escape)
            _process()
        combo.setFocus()
        _step(combo, target - combo.currentIndex())
    return combo.currentText() == text


def _step(widget, delta):
    key = QtCore.Qt.Key_Down if delta > 0 else QtCore.Qt.Key_Up
    for _ in range(abs(delta)):
        QtTest.QTest.keyClick(widget, key)
        _process()


def type_into(widget, text):
    """Click into a number field, select what is there and type `text`, then Tab away."""
    QtTest.QTest.mouseClick(
        widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(10, widget.height() // 2)
    )
    _process()
    widget.setFocus()
    QtTest.QTest.keyClick(widget, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
    QtTest.QTest.keyClicks(widget, text)
    _process()
    QtTest.QTest.keyClick(widget, QtCore.Qt.Key_Tab)
    _process()


def click(widget):
    QtTest.QTest.mouseClick(widget, QtCore.Qt.LeftButton)
    _process()


def timeline_button(title):
    """The timeline icon with this title ("Extrude 1"), or None."""
    for button in Gui.getMainWindow().findChildren(QtWidgets.QToolButton):
        if button.isVisible() and button.accessibleName() == title:
            return button
    return None


def timeline_titles():
    """Titles of the timeline icons (they carry a "state" property), left to right as they
    stand: the timeline keeps the button of a step whose look did not change, so the order
    Qt made the buttons in is not the order on the screen (journey_surface3 after an edit
    and Ctrl+Z)."""
    window = Gui.getMainWindow()
    buttons = [
        b
        for b in window.findChildren(QtWidgets.QToolButton)
        if b.isVisible() and b.property("state") is not None
    ]
    buttons.sort(key=lambda b: b.mapTo(window, QtCore.QPoint(0, 0)).x())
    return [b.accessibleName() for b in buttons]


def double_click_timeline(title):
    """Double-click a timeline item, as a person edits a feature in Fusion."""
    button = timeline_button(title)
    if button is None:
        return False
    QtTest.QTest.mouseDClick(button, QtCore.Qt.LeftButton)
    _process()
    return True


def quick_access(tooltip_word):
    """Click the application-bar button whose tooltip starts with the word (Undo, Redo)."""
    for button in Gui.getMainWindow().findChildren(QtWidgets.QToolButton):
        if button.isVisible() and button.toolTip().split("\n")[0].startswith(tooltip_word):
            button.click()
            _process()
            return True
    return False

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The navigation bar at the bottom of the 3D view, used like a person: click a button, or
open its drop-down and click an entry (through submenus such as Display Settings > Visual
Style). For the navbar_*.py scenarios."""

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import widget_input as w


def bar():
    return Gui.getMainWindow().findChild(QtWidgets.QWidget, "SciForgeNavBar")


def button(label):
    found = bar()
    if found is None:
        return None
    for b in found.findChildren(QtWidgets.QToolButton):
        if b.toolTip().split("\n")[0].split("  (")[0].strip() == label:
            return b
    return None


def click(label):
    """Click a plain button of the bar (Pan, Fit...)."""
    b = button(label)
    h.check("the navigation bar has %s" % label, b is not None)
    if b is not None:
        w.click(b)
    return b is not None


def _find(menu, label):
    for action in menu.actions():
        text = action.text().split("\t")[0].replace("&", "").strip()
        if text == label:
            return [(menu, action)]
        if action.menu() is not None:
            deeper = _find(action.menu(), label)
            if deeper:
                return [(menu, action)] + deeper
    return []


def entry_state(button_label, label):
    """(enabled, checked) of a drop-down entry, read when its menu would open."""
    b = button(button_label)
    if b is None or b.menu() is None:
        return None
    b.menu().aboutToShow.emit()
    path = _find(b.menu(), label)
    if not path:
        return None
    for menu, _action in path:
        menu.aboutToShow.emit()
    action = path[-1][1]
    return action.isEnabled(), action.isChecked()


def choose(button_label, label):
    """Open the button's drop-down and click `label` in it with the mouse (submenus open
    on the way by hovering). True if it was clicked."""
    b = button(button_label)
    if b is None or b.menu() is None:
        h.check("the navigation bar has a %s drop-down" % button_label, False)
        return False
    path = _find(b.menu(), label)
    if not path:
        h.check("%s > %s exists" % (button_label, label), False)
        return False
    # the drop-down runs its own loop until it closes; its entries are clicked inside it
    clicked = h.choose_from(
        lambda: w.click(b), [action for _menu, action in path], "the %s drop-down" % button_label
    )
    h.check("clicked %s > %s" % (button_label, label), clicked)
    return clicked

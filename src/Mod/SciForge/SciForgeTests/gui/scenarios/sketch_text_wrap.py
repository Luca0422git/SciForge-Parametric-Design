# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sketch Text in a box that is too narrow for the words, and the Text box itself (Luca,
2026-10-27: "the text just goes past the box i make. and the text box on the side where
the tool info is is just non existent. so if i try to click on it, it clicks past the side
tool box and typing no longer works"). Real input only.

W1  SKETCH > CREATE > Text, two clicks: a 30 x 30 mm frame.
W2  The mouse goes to the TEXT panel's Text box and clicks (the real pointer: FreeCAD's
    floating Tasks panel passes a click on a see-through spot to the 3D view): the Text
    box has the keyboard; the TEXT panel paints its own background (no see-through spot
    behind the Text box). Typing a long sentence goes into the Text box.
W3  The preview wraps: the words stay inside the frame's width, on several lines.
W4  OK: the text keeps wrapping (WrapLines on); its letters stay inside the frame's width.
W5  A text made before wrapping existed (WrapLines off, as such a design opens) still runs
    past its frame: opening a design changes nothing. Double-click it: the Text dialog
    wraps it (the preview), OK keeps that.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from PySide6 import QtTest

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import plane_input as pl
from SciForgeTests.gui import text_input as ti

SENTENCE = "hello world this is a test why is my text not wrapping"
s = {}


def new_design():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("TextWrap")
    h.fit()
    h.ribbon("Create Sketch")


def pick_xy():
    pl.click_square("XY_Plane")


def sketch_open():
    sk = h.in_sketch()
    h.check("sketch open on XY", sk is not None)
    s["sketch"] = sk
    h.view().viewTop()
    cam = h.view().getCameraNode()
    try:
        cam.height.setValue(140.0)
    except Exception:
        pass
    cam.position.setValue(30.0, 10.0, 100.0)
    QtWidgets.QApplication.processEvents()


# -- W1 ----------------------------------------------------------------------------------------
def w1_open():
    ti.open_text_tool()


def w1_first():
    h.check("W1 the Text dialog opened", ti.dialog() is not None)
    ti.click_sketch(s["sketch"], 5, 5)


def w1_second():
    ti.click_sketch(s["sketch"], 35, 35)


def w1_placed():
    d = ti.dialog()
    h.check("W1 the frame is placed", d is not None and d.frame_placed)
    if d is not None:
        s["frame"] = d.frame()


# -- W2 ----------------------------------------------------------------------------------------
def real_click(widget):
    """Put the real pointer on `widget`'s middle and click what is there, as a hand does
    (FreeCAD's overlay looks at the pointer, not at the event, to decide whether a click
    on its panel goes through to the 3D view)."""
    local = widget.rect().center()
    spot = widget.mapToGlobal(local)
    QtGui.QCursor.setPos(spot)
    QtWidgets.QApplication.processEvents()
    target = QtWidgets.QApplication.widgetAt(spot) or widget
    QtTest.QTest.mouseMove(target, target.mapFromGlobal(spot))
    QtTest.QTest.mouseClick(target, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            target.mapFromGlobal(spot))
    QtWidgets.QApplication.processEvents()
    return target


def w2_click_text_box():
    d = ti.dialog()
    if h.check("W2 Text dialog open", d is not None):
        s["clicked"] = real_click(d.text_box.viewport())


def w2_focus():
    d = ti.dialog()
    focus = QtWidgets.QApplication.focusWidget()
    h.check(
        "W2 the click went into the Text box (not through to the sketch)",
        focus is d.text_box or focus is d.text_box.viewport(),
        (focus and focus.metaObject().className(), s.get("clicked")),
    )
    from sciforge import theme

    h.check(
        "W2 the TEXT panel paints its own background",
        theme.own_background(d) is not None and getattr(d, "_sf_opaque", None) is not None,
        (theme.own_background(d), getattr(d, "_sf_opaque", None)),
    )
    if theme.in_overlay(d):
        clear = [
            (w.metaObject().className(), w.objectName(), w.isWindow())
            for w in [d] + d.findChildren(QtWidgets.QWidget)
            if w.testAttribute(QtCore.Qt.WA_TranslucentBackground)
        ]
        h.check(
            "W2 nothing in the TEXT panel is see-through (in FreeCAD's floating panel)",
            not clear,
            (getattr(d, "_sf_opaque", None), clear[:3]),
        )
    h.shot("w2-text-box")


def w2_type():
    focus = QtWidgets.QApplication.focusWidget()
    if h.check("W2 a widget has the keyboard", focus is not None):
        QtTest.QTest.keyClicks(focus, SENTENCE)
        QtWidgets.QApplication.processEvents()


def w2_typed():
    d = ti.dialog()
    h.check(
        "W2 the typing went into the Text box",
        d is not None and d.text_box.toPlainText() == SENTENCE,
        d and d.text_box.toPlainText(),
    )


# -- W3 ----------------------------------------------------------------------------------------
def w3_preview():
    d = ti.dialog()
    QtCore.QThread.msleep(100)
    QtWidgets.QApplication.processEvents()
    if not h.check("W3 the letters show", d is not None and d.plan is not None, d and d.message.text()):
        return
    x0, y0, x1, y1 = d.plan.bounds()
    (cx, cy), _angle, width, _height = s["frame"]
    h.check(
        "W3 the words stay inside the frame's width",
        x0 >= cx - 0.5 and x1 <= cx + width + 0.5,
        ((x0, x1), (cx, cx + width)),
    )
    h.check("W3 on several lines", (y1 - y0) > 2.5 * d.spec["height"], (y0, y1))
    h.shot("w3-wrapped")


# -- W4 ----------------------------------------------------------------------------------------
def w4_ok():
    ti.ok()


def w4_made():
    texts = ti.texts(s["sketch"])
    if not h.check("W4 one text made", len(texts) == 1, len(texts)):
        return
    obj = texts[0]
    s["text"] = obj.Name
    h.check("W4 it wraps (WrapLines)", bool(getattr(obj, "WrapLines", False)))
    x0, _y0, x1, _y1 = ti.letters_box(obj)
    (cx, _cy), _angle, width, _height = s["frame"]
    h.check("W4 its letters stay in the frame's width", x1 <= cx + width + 0.5, (x0, x1))


# -- W5 ----------------------------------------------------------------------------------------
def w5_old_text():
    """A text as a design from before wrapping has it (WrapLines added off on opening)."""
    from sciforge import text

    sk = s["sketch"]
    doc = sk.Document
    spec = text.default_spec()
    spec.update(text=SENTENCE, corner=(5.0, -40.0), width=30.0, frame_height=10.0, wrap=False)
    spec["font"] = text.spec_of(doc.getObject(s["text"]))["font"]
    doc.openTransaction("old text")
    obj = text.make(sk, spec, "OldText")
    doc.commitTransaction()
    doc.recompute()
    s["old"] = obj.Name


def w5_old_runs_past():
    obj = App.ActiveDocument.getObject(s["old"])
    h.check("W5 an old text does not wrap", not obj.WrapLines)
    _x0, _y0, x1, _y1 = ti.letters_box(obj)
    h.check("W5 so it still runs past its frame (nothing changed)", x1 > 5.0 + 30.0 + 5.0, x1)


def w5_edit():
    pt = ti.middle_of_first_letter(App.ActiveDocument.getObject(s["old"]))
    if h.check("W5 a point on the old text", pt is not None):
        h.double_click(ti.at(s["sketch"], *pt))


def w5_preview():
    d = ti.dialog()
    QtCore.QThread.msleep(100)
    QtWidgets.QApplication.processEvents()
    if not h.check("W5 Edit Text opened", d is not None and d.target is not None):
        return
    if not h.check("W5 its preview", d.plan is not None, d.message.text()):
        return
    x0, _y0, x1, _y1 = d.plan.bounds()
    h.check("W5 the dialog wraps it", x1 <= 5.0 + 30.0 + 0.5, (x0, x1))
    h.check(
        "W5 and says the words need more room than the frame has",
        "frame taller" in d.hint.text(),
        d.hint.text(),
    )


def w5_ok():
    ti.ok()


def w5_kept():
    obj = App.ActiveDocument.getObject(s["old"])
    h.check("W5 OK: it wraps from now on", bool(obj.WrapLines))
    _x0, _y0, x1, _y1 = ti.letters_box(obj)
    h.check("W5 its letters in the frame's width", x1 <= 5.0 + 30.0 + 0.5, x1)
    h.shot("w5-old-text")


h.run(
    "sketch_text_wrap",
    [new_design, pick_xy, sketch_open]
    + [w1_open, w1_first, w1_second, w1_placed]
    + [w2_click_text_box, w2_focus, w2_type, w2_typed]
    + [w3_preview, w4_ok, w4_made]
    + [w5_old_text, w5_old_runs_past, w5_edit, w5_preview, w5_ok, w5_kept],
)

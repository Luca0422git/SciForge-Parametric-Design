# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline: Rebuild with Timeline (AI)... (beta 3, builder at-tools), with real clicks.
Spec: docs/sciforge/parity/auto-timeline.md ("The command a person uses").

The part: a plate 60 x 40 x 10 with four 6 mm holes and rounded corners, written to a STEP
file and inserted with Insert STEP's code: a body without a timeline (rebuild_steps.py).

A  The body's right-click in the browser has "Rebuild with Timeline (AI)..."; clicking it
   freezes the plate as the reference (not in the browser, not in the timeline, drawn faint
   by its own Coin picture), hides the original, makes the empty body "<name> (rebuilt)" in
   the same component, active. No chat AI is set up, so a window says how to ask an AI app,
   with the message ready and already on the clipboard; Copy Message copies it again; Close.
B  Undo takes the whole start back in one step (the original shows again); Redo brings it
   back (the original hidden again, the reference drawn).
C  The same body again: no second reference; the message is offered again.
D  With a chat AI set up (a Claude key kept): a second plate selected, UTILITIES > AI >
   Rebuild with Timeline (AI)... opens the AI panel on its Chat tab with the message in
   the box, not sent (the person presses Send).
E  The 3D view's right-click on a third plate: its list has Rebuild with Timeline (AI)...
   and it starts that plate's rebuild; on an empty spot the entry is not there; on a
   rebuilt body the list has Compare with Reference and Finish Rebuild instead.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import widget_input as w

V = App.Vector
s = {}
ENTRY = "Rebuild with Timeline (AI)..."


def setup():
    r.drop_fake_key()
    s["doc"] = r.new_design("RebuildStart")
    s["path"] = r.write_step("plate")
    s["plate"] = r.insert_step(s["doc"], s["path"])
    s["doc"].recompute()
    h.fit()
    plate = s["plate"]
    h.check(
        "the inserted plate is a body without a timeline (one Insert STEP step)",
        plate is not None and abs(plate.Shape.Volume - r.PLATE_VOLUME) < 1e-3,
        plate.Shape.Volume if plate is not None else None,
    )
    s["label"] = plate.Label
    s["steps_before"] = list(r.timeline_names())


# -- A ------------------------------------------------------------------------------------------
def a_menu_has_entry():
    entries = r.browser_entries(s["label"])
    h.check("the body's right-click has %s" % ENTRY, ENTRY in entries, entries)


def a_start():
    r.browser_menu(s["label"], ENTRY)


a_start.wait_ms = 1500


def a_started():
    from sciforge import bodies, components, rebuild

    refs = r.references()
    h.check("one reference made", len(refs) == 1, refs)
    if not refs:
        return
    ref = s["ref"] = refs[0]
    plate = s["plate"]
    h.check(
        "the reference holds the plate's solid",
        abs(ref.FrozenShape.Volume - r.PLATE_VOLUME) < 1e-3,
        ref.FrozenShape.Volume,
    )
    h.check(
        "the reference is no body",
        not bodies.is_body(ref) and ref.TypeId == "App::FeaturePython",
        ref.TypeId,
    )
    h.check("the original is hidden", not r.shown(plate))
    h.check("the reference is drawn faint (its Coin picture)", r.ghost_drawn(ref))
    target = rebuild.target_of(ref)
    s["target"] = target
    s["target_name"] = target.Name if target is not None else None
    h.check(
        "the empty body '<name> (rebuilt)' is made",
        target is not None and target.Label == "%s (rebuilt)" % s["label"],
        target.Label if target is not None else None,
    )
    h.check("... empty", target is not None and not bodies.has_solid(target))
    h.check(
        "... in the original's component",
        target is not None and components.container_of(target) is components.container_of(plate),
    )
    h.check(
        "... and active",
        bodies.active_body(App.ActiveDocument) is target,
        bodies.active_body(App.ActiveDocument),
    )
    labels = r.browser_labels()
    h.check("the reference is not in the browser", ref.Label not in labels, labels)
    h.check(
        "... the new body is",
        target is not None and any(x.startswith(target.Label) for x in labels),
        labels,
    )
    names = r.timeline_names()
    h.check("the reference is not a timeline step", ref.Name not in names, names)
    h.check("the timeline is as before", names == s["steps_before"], (names, s["steps_before"]))


def a_dialog():
    from sciforge import rebuild_ui

    box = r.dialog("SciForgeRebuildNoAI")
    h.check("no chat AI: the window for AI apps opened", box is not None, h.popups())
    if box is None:
        return
    message = box.text.toPlainText()
    s["message"] = message
    h.check("it holds the message", 'Rebuild the body "%s"' % s["label"] in message, message)
    h.check(
        "the message is on the clipboard",
        QtWidgets.QApplication.clipboard().text() == message,
        QtWidgets.QApplication.clipboard().text(),
    )
    h.check(
        "the message names the recipe and the tools",
        all(
            word in message
            for word in (
                "reverse-engineer",
                "describe_reference",
                "compare_to_reference",
                "finish_rebuild",
            )
        ),
        message,
    )
    h.check("... as rebuild_ui prepared it", rebuild_ui._LAST["message"] == message)
    QtWidgets.QApplication.clipboard().setText("something else")
    r.click_button(box, "SciForgeRebuildCopy")


def a_copied():
    box = r.dialog("SciForgeRebuildNoAI")
    h.check(
        "Copy Message copies it again",
        QtWidgets.QApplication.clipboard().text() == s.get("message"),
    )
    r.click_button(box, "SciForgeRebuildClose")


def a_closed():
    h.check("Close closes the window", r.dialog("SciForgeRebuildNoAI") is None, h.popups())


# -- B ------------------------------------------------------------------------------------------
def b_undo():
    t.undo()


b_undo.wait_ms = 1200


def b_undone():
    doc = App.ActiveDocument
    h.check("undo: no reference", not r.references(), r.references())
    h.check("... no rebuilt body", doc.getObject(s.get("target_name") or "-") is None)
    h.check("... the original shows again", r.shown(s["plate"]))
    t.redo()


b_undone.wait_ms = 1200


def b_redone():
    from sciforge import rebuild

    refs = r.references()
    h.check("redo: the reference is back", len(refs) == 1, refs)
    if refs:
        s["ref"] = refs[0]
        s["target"] = rebuild.target_of(refs[0])
        h.check("... drawn faint again", r.ghost_drawn(refs[0]))
    h.check("... the original hidden again", not r.shown(s["plate"]))
    h.check("... the rebuilt body back", s.get("target") is not None)


# -- C ------------------------------------------------------------------------------------------
def c_again():
    r.close_dialogs()
    s["count"] = len(App.ActiveDocument.Objects)
    r.select_body(s["plate"])
    Gui.runCommand("SciForge_RebuildWithTimeline")


c_again.wait_ms = 1200


def c_checked():
    h.check("the same body again: still one reference", len(r.references()) == 1, r.references())
    h.check("... nothing new in the design", len(App.ActiveDocument.Objects) == s["count"])
    box = r.dialog("SciForgeRebuildNoAI")
    h.check("... the message is offered again", box is not None, h.popups())
    r.close_dialogs()
    Gui.Selection.clearSelection()


# -- D ------------------------------------------------------------------------------------------
def d_second():
    r.store_fake_key()
    s["second"] = r.insert_step(App.ActiveDocument, s["path"])
    App.ActiveDocument.recompute()
    r.select_body(s["second"])
    r.utilities_menu(ENTRY)


d_second.wait_ms = 2000


def d_chat():
    from sciforge import ai_panel_ui, rebuild

    refs = [x for x in r.references() if x.SourceName == s["second"].Name]
    h.check("the second plate's rebuild started", len(refs) == 1, r.references())
    h.check("a chat AI is set up: the AI panel shows", ai_panel_ui.is_shown())
    page = ai_panel_ui.panel()
    if page is None:
        return
    h.check("... on its Chat tab", page.tabs.currentWidget() is page.chat)
    text = page.chat.input.toPlainText()
    h.check(
        "... with the message in the box",
        refs and text == rebuild_core_message(refs[0]),
        text,
    )
    h.check(
        "... not sent",
        "You:" not in page.chat.transcript.toPlainText() and not page.chat.busy(),
        page.chat.transcript.toPlainText(),
    )
    h.check("no window for AI apps this time", r.dialog("SciForgeRebuildNoAI") is None)
    h.check(
        "Claude is the chat's AI",
        page.chat.provider_name() == "anthropic",
        page.chat.provider_name(),
    )
    s["second_ref"] = refs[0] if refs else None
    s["second_target"] = rebuild.target_of(refs[0]) if refs else None


def rebuild_core_message(ref):
    from sciforge import rebuild_ui

    return rebuild_ui.message_for(ref)


def d_cleanup():
    from sciforge import ai_panel_ui

    page = ai_panel_ui.panel()
    if page is not None:
        page.chat.input.clear()
    r.drop_fake_key()
    if ai_panel_ui.is_shown():
        ai_panel_ui.toggle()


# -- E ------------------------------------------------------------------------------------------
def e_third():
    s["third"] = r.insert_step(App.ActiveDocument, s["path"])
    App.ActiveDocument.recompute()
    Gui.Selection.clearSelection()
    h.fit()


e_third.wait_ms = 1500


def e_empty_spot():
    from sciforge import marking_menu

    gl = h.gl_widget()
    marking_menu._last_menu["widget"] = None
    from PySide import QtCore

    w.click(gl, QtCore.QPoint(30, 30), button=QtCore.Qt.RightButton)
    menu = marking_menu._last_menu["widget"]
    h.check("a right click on an empty spot opens the marking menu", menu is not None)
    if menu is not None:
        rows = r.marking_rows(menu)
        h.check("... without %s" % ENTRY, ENTRY not in rows, rows)
        r.esc(menu)


def e_on_body():
    menu = r.open_marking_menu(V(30, 20, 10))
    if menu is None:
        return
    rows = r.marking_rows(menu)
    h.check("a right click on the plate lists %s" % ENTRY, ENTRY in rows, rows)
    s["before_third"] = len(r.references())
    if ENTRY in rows:
        r.click_marking_row(menu, ENTRY)
    else:
        r.esc(menu)


e_on_body.wait_ms = 1500


def e_started():
    refs = [x for x in r.references() if x.SourceName == s["third"].Name]
    h.check("the marking menu started the third plate's rebuild", len(refs) == 1, r.references())
    r.close_dialogs()
    s["third_ref"] = refs[0] if refs else None


def e_on_rebuilt():
    from sciforge import rebuild

    # the third plate's rebuild gets its base (an AI's first steps), then a right click on it
    ref = s.get("third_ref")
    target = rebuild.target_of(ref) if ref is not None else None
    if target is None:
        h.check("the third rebuild has a body", False)
        return
    r.tool("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 60, 40]}])
    r.tool("extrude", profile="Sketch1", distance=10)
    App.ActiveDocument.recompute()
    h.check(
        "the AI's base was built in the rebuilt body",
        abs(target.Shape.Volume - 24000) < 1e-3,
        target.Shape.Volume,
    )


e_on_rebuilt.wait_ms = 1500


def e_menu_rebuilt():
    menu = r.open_marking_menu(V(30, 20, 10))
    if menu is None:
        return
    rows = r.marking_rows(menu)
    h.check(
        "on a rebuilt body the list has Compare with Reference",
        "Compare with Reference" in rows,
        rows,
    )
    h.check("... and Finish Rebuild", "Finish Rebuild" in rows, rows)
    h.check("... not a second rebuild", ENTRY not in rows, rows)
    r.esc(menu)


def finish():
    r.close_dialogs()
    h.expect_no_errors("the rebuild start scenario")


h.run(
    "rebuild_start",
    [
        setup,
        a_menu_has_entry,
        a_start,
        a_started,
        a_dialog,
        a_copied,
        a_closed,
        b_undo,
        b_undone,
        b_redone,
        c_again,
        c_checked,
        d_second,
        d_chat,
        d_cleanup,
        e_third,
        e_empty_spot,
        e_on_body,
        e_started,
        e_on_rebuilt,
        e_menu_rebuilt,
        finish,
    ],
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline: Compare with Reference and Finish Rebuild (beta 3, builder at-tools), with
real clicks. Spec: docs/sciforge/parity/auto-timeline.md.

The plate of rebuild_steps.py (60 x 40 x 10, four 6 mm holes, 3 mm rounded corners) inserted
from STEP, its rebuild started; an AI's tool calls build in the rebuilt body.

A  After the base plate: UTILITIES > AI > Compare with Reference shows the match (about 95
   %), the volumes, 6 of 14 faces matched, a verdict naming the 4 holes and the 4 rounded
   edges (in a person's words: Compare Again, no tool names), one row per difference, and
   the differences in the 3D view (8 green regions of extra material, nothing red); Close
   clears them.
B  The AI's compare_to_reference (tool call) draws the differences too; after the holes and
   the fillet the comparison says done (100 %, all faces) and draws nothing; Finish
   Rebuild... in the dialog opens Finish; Esc leaves everything as it was.
C  UTILITIES > AI > Finish Rebuild, Finish: the rebuilt body takes the original's name,
   stays in the original's component and place, the original and the reference are gone,
   the timeline holds the rebuild's own steps; one Undo brings back the original (hidden),
   the reference (drawn) and the "(rebuilt)" name; Redo finishes again.
D  Undo, then Finish with "Keep the original, hidden": the original stays, hidden, renamed
   "<name> (original)"; Keep the reference keeps it, not drawn.
"""

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import timeline_input as t

V = App.Vector
s = {}


def setup():
    from sciforge import rebuild, rebuild_ui

    r.drop_fake_key()
    s["doc"] = r.new_design("RebuildFinish")
    s["plate"] = r.insert_step(s["doc"], r.write_step("plate"))
    s["label"] = s["plate"].Label
    s["plate_name"] = s["plate"].Name
    s["component"] = s["plate"].getParentGeoFeatureGroup()
    s["doc"].recompute()
    s["ref"] = rebuild_ui.start_for(s["plate"])
    r.close_dialogs()
    s["target"] = rebuild.target_of(s["ref"]) if s["ref"] is not None else None
    h.check("the rebuild started", s["target"] is not None)
    s["target_name"] = s["target"].Name if s["target"] is not None else None
    # the AI's first steps: the base plate
    r.tool("create_sketch", plane="XY", geometry=[{"rect": [0, 0, 60, 40]}])
    answer = r.tool("extrude", profile="Sketch1", distance=10)
    h.check("the AI's base plate is built", not answer["is_error"], answer["text"])
    h.fit()


# -- A ------------------------------------------------------------------------------------------
def a_compare():
    r.utilities_menu("Compare with Reference")


def a_numbers():
    box = r.dialog("SciForgeRebuildCompare")
    h.check("Compare with Reference opened its window", box is not None, h.popups())
    if box is None:
        return
    head = box.headline.text()
    h.check("it shows the match (about 95 %)", "Match 94.9" in head, head)
    numbers = box.numbers.text()
    h.check("... the faces matched: 6 of 14", "6 of 14" in numbers, numbers)
    h.check("... the volumes", "22791.77 mm3" in numbers and "24000 mm3" in numbers, numbers)
    verdict = box.verdict.text()
    h.check("the verdict names the 4 holes", "4 round holes about 6 mm across" in verdict, verdict)
    h.check("... and the 4 rounded edges", "4 rounded edges of radius about 3" in verdict, verdict)
    h.check(
        "... said for a person (Compare Again, no tool names)",
        "Compare Again" in verdict and "_" not in verdict and "groups[" not in verdict,
        verdict,
    )
    h.check(
        "one row per difference", box.table.topLevelItemCount() == 2, box.table.topLevelItemCount()
    )
    count = r.overlay_count(s["ref"])
    h.check("the 3D view shows the 8 regions of extra material", count == 8, count)
    view = r.view_of(s["ref"])
    h.check(
        "... green, none red",
        view is not None and view.shown_regions == {"missing": 0, "extra": 8},
        view.shown_regions if view else None,
    )
    h.shot("compare")
    r.click_button(box, "SciForgeRebuildCompareClose")


def a_closed():
    h.check("Close closes the window", r.dialog("SciForgeRebuildCompare") is None)
    h.check(
        "... and clears the differences", r.overlay_count(s["ref"]) == 0, r.overlay_count(s["ref"])
    )


# -- B ------------------------------------------------------------------------------------------
def b_ai_compare():
    answer, data = r.tool_json("compare_to_reference")
    h.check(
        "the AI's compare answers the same",
        data is not None and abs(data["match"] - 0.949657) < 1e-5,
        answer["text"][:300],
    )
    h.check(
        "... and draws the differences", r.overlay_count(s["ref"]) == 8, r.overlay_count(s["ref"])
    )
    holes = [g for g in (data or {}).get("groups", []) if g["kind"] == "cylinder"]
    fillets = [g for g in (data or {}).get("groups", []) if g["kind"] == "fillet"]
    h.check("a fillet call is ready for the 4 edges", fillets and fillets[0].get("fix"), fillets)
    r.tool(
        "create_sketch", plane="XY", offset=10, geometry=[{"circle": [x, y, 3]} for x, y in r.HOLES]
    )
    answer = r.tool("hole", sketch="Sketch2", diameter=6, through_all=True)
    h.check("the AI drills the holes", not answer["is_error"], answer["text"])
    if fillets and fillets[0].get("fix"):
        fix = fillets[0]["fix"]
        answer = r.tool(fix["tool"], **fix["args"])
        h.check("the AI's fillet from the ready call", not answer["is_error"], answer["text"])
    s["holes_group"] = holes


def b_done():
    answer, data = r.tool_json("compare_to_reference")
    h.check("the comparison says done", data is not None and data["done"], answer["text"][:400])
    h.check("... nothing drawn", r.overlay_count(s["ref"]) == 0, r.overlay_count(s["ref"]))
    r.utilities_menu("Compare with Reference")


def b_dialog_done():
    box = r.dialog("SciForgeRebuildCompare")
    h.check(
        "the window says done",
        box is not None and box.headline.text().startswith("Done"),
        box.headline.text() if box else h.popups(),
    )
    h.check("... 14 of 14 faces", box is not None and "14 of 14" in box.numbers.text())
    if box is not None:
        r.click_button(box, "SciForgeRebuildCompareFinish")


def b_finish_esc():
    box = r.dialog("SciForgeRebuildFinish")
    h.check("Finish Rebuild... opened Finish", box is not None, h.popups())
    if box is None:
        return
    h.check("it says the rebuild matches", "matches" in box.state.text(), box.state.text())
    h.check("deleting the original is the default", box.delete_original.isChecked())
    r.esc(box)


def b_nothing():
    h.check("Esc closed Finish", r.dialog("SciForgeRebuildFinish") is None, h.popups())
    h.check(
        "... and changed nothing",
        len(r.references()) == 1 and App.ActiveDocument.getObject(s["plate_name"]) is not None,
    )


# -- C ------------------------------------------------------------------------------------------
def c_finish():
    s["undo_before"] = len(App.ActiveDocument.UndoNames)
    r.utilities_menu("Finish Rebuild")


def c_press():
    box = r.dialog("SciForgeRebuildFinish")
    h.check("UTILITIES > AI > Finish Rebuild opened Finish", box is not None, h.popups())
    if box is not None:
        r.click_button(box, "SciForgeRebuildFinishOK")


def c_finished():
    from sciforge import bodies, components

    doc = App.ActiveDocument
    target = doc.getObject(s["target_name"])
    h.check("the rebuilt body is there", target is not None)
    if target is None:
        return
    h.check("it took the original's name", target.Label == s["label"], target.Label)
    h.check(
        "... stays in the original's component", components.container_of(target) is s["component"]
    )
    h.check("... and place", target.Placement.isIdentity())
    h.check("the original is deleted", doc.getObject(s["plate_name"]) is None)
    h.check("the reference is gone", not r.references(), r.references())
    h.check(
        "the rebuilt body is shown and active",
        r.shown(target) and bodies.active_body(doc) is target,
    )
    h.check("one undo step", len(doc.UndoNames) == s["undo_before"] + 1, doc.UndoNames[:3])
    names = r.timeline_names()
    mine = [n for n in names if bodies.body_of(doc.getObject(n)) is target]
    h.check("its timeline: sketch, extrude, sketch, hole, fillet", len(mine) == 5, mine)
    h.check(
        "the part is the plate",
        abs(target.Shape.Volume - r.PLATE_VOLUME) < 1e-3,
        target.Shape.Volume,
    )
    t.undo()


def c_undone():
    from sciforge import rebuild

    doc = App.ActiveDocument
    refs = r.references()
    h.check("one Undo: the reference is back", len(refs) == 1, refs)
    plate = doc.getObject(s["plate_name"])
    h.check("... the original is back, hidden", plate is not None and not r.shown(plate))
    target = doc.getObject(s["target_name"])
    h.check(
        "... the rebuild has its '(rebuilt)' name again",
        target is not None and target.Label == "%s (rebuilt)" % s["label"],
        target.Label if target else None,
    )
    if refs:
        s["ref"] = refs[0]
        h.check("... the reference is drawn", r.ghost_drawn(refs[0]))
        h.check("... and still points at the rebuild", rebuild.target_of(refs[0]) is target)
    t.redo()


def c_redone():
    doc = App.ActiveDocument
    target = doc.getObject(s["target_name"])
    h.check(
        "Redo finishes again",
        not r.references() and target is not None and target.Label == s["label"],
        (r.references(), target.Label if target else None),
    )
    t.undo()


# -- D ------------------------------------------------------------------------------------------
def d_keep():
    h.check("back to the rebuild", len(r.references()) == 1)
    r.utilities_menu("Finish Rebuild")


def d_choose():
    box = r.dialog("SciForgeRebuildFinish")
    h.check("Finish opened again", box is not None, h.popups())
    if box is None:
        return
    from PySide6 import QtTest
    from PySide import QtCore

    QtTest.QTest.mouseClick(box.keep_original, QtCore.Qt.LeftButton)
    QtTest.QTest.mouseClick(box.keep_reference, QtCore.Qt.LeftButton)
    h.check("Keep the original chosen", box.keep_original.isChecked())
    h.check("Keep the reference ticked", box.keep_reference.isChecked())
    r.click_button(box, "SciForgeRebuildFinishOK")


def d_kept():
    doc = App.ActiveDocument
    plate = doc.getObject(s["plate_name"])
    h.check("the original is kept", plate is not None)
    h.check("... hidden", plate is not None and not r.shown(plate))
    h.check(
        "... renamed '<name> (original)'",
        plate is not None and plate.Label == "%s (original)" % s["label"],
        plate.Label if plate else None,
    )
    target = doc.getObject(s["target_name"])
    h.check("the rebuild took the name", target is not None and target.Label == s["label"])
    refs = r.references()
    h.check("the reference is kept", len(refs) == 1, refs)
    h.check("... not drawn", refs and not r.ghost_drawn(refs[0]))
    names = r.browser_labels()
    h.check(
        "the browser lists the rebuild and the original",
        s["label"] in [n.split("  ")[0] for n in names] and "%s (original)" % s["label"] in names,
        names,
    )


def finish():
    r.close_dialogs()
    h.expect_no_errors("the compare / finish scenario")


h.run(
    "rebuild_compare_finish",
    [
        setup,
        a_compare,
        a_numbers,
        a_closed,
        b_ai_compare,
        b_done,
        b_dialog_done,
        b_finish_esc,
        b_nothing,
        c_finish,
        c_press,
        c_finished,
        c_undone,
        c_redone,
        d_keep,
        d_choose,
        d_kept,
        finish,
    ],
    paced_by="state",
)

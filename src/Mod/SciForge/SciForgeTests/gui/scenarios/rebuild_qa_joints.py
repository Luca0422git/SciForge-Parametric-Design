# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline QA (beta 3): a jointed imported part rebuilt and finished, and a rebuild
saved half way and opened again, with real clicks. Found by the QA pass: Finish deleted the
joints of a jointed part (a VEX team rebuilds imported parts that are jointed), and a design
opened again sent the next steps to another body. Spec: docs/sciforge/parity/auto-timeline.md
(Finish; QA).

A  Two STEP parts inserted (an arm: a bar 80 x 20 x 5 with two 5 mm holes; a base: a block
   40 x 40 x 10 with one), the base grounded, a revolute joint between the arm's first hole
   and the base's (the AI's joint call), the arm driven to 30 degrees. The arm's body:
   browser right-click > Rebuild with Timeline (AI)... (no AI set up: the window for AI apps,
   closed); the AI builds the plan in the rebuilt body; the arm turned to 45 degrees: the
   ghost turns with it and the comparison still says done; back to 30.
B  UTILITIES > AI > Finish Rebuild > Finish: the joint is still there, on the rebuilt body;
   the arm did not move; the AI's drive_joint still turns it; the rebuild's steps stand where
   Insert STEP stood, before the joint; no stray "(imported)" row; Undo puts the joint back on
   the original and its Insert STEP; Redo moves it onto the rebuild again.
C  The base rebuilt next: half way (its base block built), saved (Ctrl+S), closed and opened
   again: the rebuilt body is the active body again and its ghost is drawn; the AI's next
   steps go into it and the comparison says done; Finish keeps the joint (now on two rebuilt
   bodies) and the ground.
D  The base rebuilt once more (its block built), and the arm too (its rebuilt body active):
   the 3D view's right-click on the rebuilt base: Compare with Reference and Finish Rebuild
   are the base's (they took the active body's rebuild, the arm's); Stop Rebuild... (there
   was no way back but Undo) names the base > Stop Rebuild: the base is shown
   again and is the active body, its rebuilt body is gone, the joint still holds it, the arm's
   rebuild goes on; one undo step; Undo brings the base's rebuild back (hidden base, ghost),
   Redo stops it again; UTILITIES > AI > Stop Rebuild... stops the arm's.
"""

import os

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import versions_input as vi
from PySide import QtCore, QtWidgets

V = App.Vector
s = {}
ENTRY = "Rebuild with Timeline (AI)..."


def arm_shape():
    import Part

    bar = Part.makeBox(80, 20, 5)
    for x in (10, 70):
        bar = bar.cut(Part.makeCylinder(2.5, 5, V(x, 10, 0)))
    return bar.removeSplitter()


def base_shape():
    import Part

    block = Part.makeBox(40, 40, 10)
    return block.cut(Part.makeCylinder(2.5, 10, V(20, 20, 0))).removeSplitter()


def joint_names():
    from sciforge import joints

    return [j.Name for j in joints.joints(App.ActiveDocument)]


def joint_subs():
    from sciforge import joints

    found = joints.joints(App.ActiveDocument)
    return list(found[0].Reference1[1]) + list(found[0].Reference2[1]) if found else []


def build_plan(prefix):
    """The AI follows describe_reference's plan (ids as the answers give them)."""
    import re

    answer, data = r.tool_json("describe_reference")
    plan = (data or {}).get("plan") or []
    h.check("%s: describe_reference gives a plan" % prefix, len(plan) >= 2, answer["text"][:300])
    made, failed = {}, []
    planned = {st.get("step"): st.get("id") for st in plan}
    for step in plan:
        args = step.get("args") or {}
        for key, number in (step.get("uses") or {}).items():
            old, new = planned.get(number), made.get(number)
            if old and new and old != new and args.get(key) == old:
                args = dict(args, **{key: new})
        answer = r.tool(step["tool"], **args)
        if answer["is_error"]:
            failed.append(answer["text"][:200])
        found = re.search(r"Its id is '([^']+)'", answer["text"])
        if found:
            made[step.get("step")] = found.group(1)
    h.check("%s: every plan step runs" % prefix, not failed, failed)
    return plan


def setup():
    from sciforge import step_import  # noqa: F401  (Insert STEP's own code, rebuild_steps)

    r.drop_fake_key()
    s["doc"] = r.new_design("RebuildJoints")
    s["arm"] = r.insert_step(s["doc"], r.write_step("qa_arm", arm_shape()))
    s["base"] = r.insert_step(s["doc"], r.write_step("qa_base", base_shape()))
    # (Insert STEP names every body of these files "Body1": a person tells them apart by
    # their names, as here)
    s["arm"].Label, s["base"].Label = "Arm", "Base"
    s["arm_part"] = s["arm"].getParentGeoFeatureGroup()
    s["base_part"] = s["base"].getParentGeoFeatureGroup()
    s["base_part_name"] = s["base_part"].Name
    r.tool("ground", component=s["base_part"].Name)
    answer = r.tool(
        "joint",
        type="revolute",
        first={
            "component": s["arm_part"].Name,
            "face": {"type": "cylinder", "count": 1, "at": {"axis": "x", "value": "min"}},
            "snap": "circle",
        },
        second={
            "component": s["base_part"].Name,
            "face": {"type": "cylinder", "count": 1},
            "snap": "circle",
        },
    )
    h.check("the revolute joint is made", not answer["is_error"], answer["text"][:300])
    r.tool("drive_joint", joint="Joint", angle=60)
    s["at_60"] = App.Placement(s["arm_part"].Placement)
    r.tool("drive_joint", joint="Joint", angle=30)
    s["at_30"] = App.Placement(s["arm_part"].Placement)
    s["arm_name"], s["arm_label"] = s["arm"].Name, s["arm"].Label
    h.fit()


setup.wait_ms = 2000


# -- A ------------------------------------------------------------------------------------------
def a_start():
    entries = r.browser_entries(s["arm_label"])
    h.check("the arm's right-click has %s" % ENTRY, ENTRY in entries, entries)
    r.browser_menu(s["arm_label"], ENTRY)


a_start.wait_ms = 2000


def a_started():
    from sciforge import rebuild

    box = r.dialog("SciForgeRebuildNoAI")
    h.check("no AI set up: the window for AI apps opens", box is not None, h.popups())
    if box is not None:
        r.click_button(box, "SciForgeRebuildClose")
    refs = r.references()
    h.check("the arm is the reference", len(refs) == 1, refs)
    if not refs:
        return
    s["ref"] = refs[0]
    target = rebuild.target_of(refs[0])
    h.check("its rebuilt body is in the arm's component", target in s["arm_part"].Group)
    s["target_name"] = target.Name if target is not None else None
    h.check(
        "the joint still holds the original while the rebuild goes on",
        joint_names() == ["Joint"] and all(s["arm_name"] + "." in x for x in joint_subs()[:2]),
        joint_subs(),
    )
    build_plan("arm")
    answer, data = r.tool_json("compare_to_reference")
    h.check("the arm's rebuild is done", data is not None and data.get("done"), answer["text"])
    # the person turns the arm while it is rebuilt: the reference turns with it
    r.tool("drive_joint", joint="Joint", angle=45)
    view = r.view_of(s["ref"])
    moved = view.moved() if view is not None else None
    h.check(
        "the ghost turns with the arm (it stayed where it was frozen)",
        moved is not None and moved.Length > 1,
        moved,
    )
    answer, data = r.tool_json("compare_to_reference")
    h.check(
        "... and the comparison still says done (it said match 0.16)",
        data is not None and data.get("done"),
        answer["text"][:300],
    )
    r.tool("drive_joint", joint="Joint", angle=30)


a_started.wait_ms = 2000


# -- B ------------------------------------------------------------------------------------------
def b_finish():
    s["undo_before"] = len(App.ActiveDocument.UndoNames)
    r.utilities_menu("Finish Rebuild")


b_finish.wait_ms = 1500


def b_press():
    box = r.dialog("SciForgeRebuildFinish")
    h.check("Finish Rebuild opened its window", box is not None, h.popups())
    if box is not None:
        h.check("deleting the original is the default", box.delete_original.isChecked())
        r.click_button(box, "SciForgeRebuildFinishOK")


b_press.wait_ms = 2000


def b_finished():
    doc = App.ActiveDocument
    target = doc.getObject(s["target_name"])
    h.check("the rebuilt arm took the name", target is not None and target.Label == s["arm_label"])
    h.check("the original arm is deleted", doc.getObject(s["arm_name"]) is None)
    h.check(
        "the joint is still there (Finish deleted it with the original)",
        joint_names() == ["Joint"],
        joint_names(),
    )
    h.check(
        "... on the rebuilt arm",
        bool(joint_subs()) and all(s["target_name"] + "." in x for x in joint_subs()[:2]),
        joint_subs(),
    )
    h.check(
        "the arm did not move",
        s["arm_part"].Placement.isSame(s["at_30"], 1e-6),
        (s["arm_part"].Placement, s["at_30"]),
    )
    h.check("one undo step", len(doc.UndoNames) == s["undo_before"] + 1, doc.UndoNames[:3])
    names = r.timeline_names()
    mine = [n for n in names if doc.getObject(n) in target.Group] if target is not None else []
    h.check(
        "the rebuild's steps stand where Insert STEP stood, before the joint",
        mine and "Joint" in names and names.index(mine[-1]) < names.index("Joint"),
        names,
    )
    labels = r.browser_labels()
    h.check(
        "no stray imported shape of the original",
        not [x for x in labels if x.startswith(s["arm_label"] + " (imported)")],
        labels,
    )
    answer = r.tool("drive_joint", joint="Joint", angle=60)
    h.check(
        "the joint still turns the arm (to where the original went)",
        not answer["is_error"] and s["arm_part"].Placement.isSame(s["at_60"], 1e-6),
        (answer["text"][:200], s["arm_part"].Placement),
    )
    h.shot("jointed_finished")
    t.undo()  # the drive


b_finished.wait_ms = 1500


def b_undo_finish():
    t.undo()


b_undo_finish.wait_ms = 1500


def b_undone():
    doc = App.ActiveDocument
    h.check("Undo: the original is back", doc.getObject(s["arm_name"]) is not None)
    h.check(
        "... and the joint on it again",
        joint_names() == ["Joint"] and all(s["arm_name"] + "." in x for x in joint_subs()[:2]),
        joint_subs(),
    )
    t.redo()


b_undone.wait_ms = 1500


def b_redone():
    h.check(
        "Redo: the joint is on the rebuilt arm again",
        joint_names() == ["Joint"] and all(s["target_name"] + "." in x for x in joint_subs()[:2]),
        joint_subs(),
    )


# -- C ------------------------------------------------------------------------------------------
def c_start_base():
    s["base_name"], s["base_label"] = s["base"].Name, s["base"].Label
    r.browser_menu(s["base_label"], ENTRY)


c_start_base.wait_ms = 2000


def c_half_way():
    from sciforge import rebuild

    r.close_dialogs()
    live = rebuild.active_references(App.ActiveDocument)
    h.check("the base is being rebuilt", len(live) == 1, live)
    if not live:
        return
    target = rebuild.target_of(live[0])
    s["base_target"] = target.Name if target is not None else None
    answer, data = r.tool_json("describe_reference")
    s["base_plan"] = (data or {}).get("plan") or []
    for step in s["base_plan"][:2]:  # the block only
        r.tool(step["tool"], **step["args"])
    path = os.path.join(r.folder(), "rebuild_qa_half_way.FCStd")
    if os.path.exists(path):
        os.remove(path)
    App.ActiveDocument.saveAs(path)
    s["path"] = path
    h.check("saved half way", os.path.isfile(path), path)
    h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)


c_half_way.wait_ms = 1500


def c_describe():
    vi.accept_save()


def c_close():
    App.closeDocument(App.ActiveDocument.Name)


def c_reopen():
    App.openDocument(s["path"])
    h.fit()


c_reopen.wait_ms = 3000


def c_reopened():
    from sciforge import bodies, rebuild

    doc = App.ActiveDocument
    target = doc.getObject(s.get("base_target") or "")
    h.check("after opening again the base's rebuilt body is there", target is not None)
    h.check(
        "... and it is the active body (the next steps went into the design's first body)",
        target is not None and bodies.active_body(doc) is target,
        getattr(bodies.active_body(doc), "Label", None),
    )
    refs = rebuild.active_references(doc)
    h.check("... its ghost is drawn", refs and r.ghost_drawn(refs[0]))
    plan = s.get("base_plan") or []
    failed = []
    for step in plan[2:]:
        answer = r.tool(step["tool"], **step["args"])
        if answer["is_error"]:
            failed.append(answer["text"][:200])
    h.check("the AI's next steps run", not failed, failed)
    answer, data = r.tool_json("compare_to_reference")
    h.check(
        "... into the rebuilt body: the comparison says done",
        data is not None and data.get("done"),
        answer["text"][:400],
    )
    answer = r.tool("finish_rebuild")
    h.check("finish_rebuild", not answer["is_error"], answer["text"][:400])


c_reopened.wait_ms = 2500


def c_both_rebuilt():
    from sciforge import joints

    doc = App.ActiveDocument
    target = doc.getObject(s.get("base_target") or "")
    subs = joint_subs()
    h.check(
        "the joint is now between the two rebuilt bodies",
        joint_names() == ["Joint"]
        and target is not None
        and any(target.Name + "." in x for x in subs)
        and any(s["target_name"] + "." in x for x in subs),
        subs,
    )
    grounds = [g.ObjectToGround for g in joints.grounds(doc)]
    h.check(
        "the base is still grounded",
        grounds and grounds[0] is doc.getObject(s["base_part_name"]),
        [getattr(g, "Name", None) for g in grounds],
    )
    h.shot("both_rebuilt")


# -- D ------------------------------------------------------------------------------------------
def d_start_again():
    doc = App.ActiveDocument
    base = doc.getObject(s.get("base_target") or "")
    s["base_again_label"] = base.Label if base is not None else ""
    r.browser_menu(s["base_again_label"], ENTRY)


d_start_again.wait_ms = 2000


def d_two_rebuilds():
    """The base's block built in its rebuilt body, then the arm's rebuild started too (its
    rebuilt body is the active one now)."""
    from sciforge import rebuild

    r.close_dialogs()
    doc = App.ActiveDocument
    live = rebuild.active_references(doc)
    h.check("the base is being rebuilt again", len(live) == 1, live)
    target = rebuild.target_of(live[0]) if live else None
    s["stop_target"] = target.Name if target is not None else ""
    answer, data = r.tool_json("describe_reference")
    for step in ((data or {}).get("plan") or [])[:2]:  # the block only
        r.tool(step["tool"], **step["args"])
    answer = r.tool("start_rebuild", body=s["target_name"])
    live = rebuild.active_references(doc)
    h.check("the arm's rebuild started too", not answer["is_error"] and len(live) == 2, answer)
    arm_refs = [x for x in live if x.SourceName == s["target_name"]]
    arm_target = rebuild.target_of(arm_refs[0]) if arm_refs else None
    s["arm_stop_target"] = arm_target.Name if arm_target is not None else ""
    doc.recompute()
    h.fit()
    import FreeCADGui as Gui

    Gui.Selection.clearSelection()  # (what the right-click is about: the body under the mouse)
    s["undo_before_stop"] = len(doc.UndoNames)


d_two_rebuilds.wait_ms = 2000


def _base_point():
    """A point on the top of the rebuilt base's block (away from its hole), or None."""
    from sciforge import bodies

    target = App.ActiveDocument.getObject(s["stop_target"])
    shape = bodies.global_shape(target) if target is not None else None
    if shape is None or shape.isNull():
        h.check("the base's block is built", False)
        return None
    box = shape.BoundBox
    return V(box.XMin + 6, box.YMin + 6, box.ZMax)


def _about_base(box):
    base = App.ActiveDocument.getObject(s.get("base_target") or "")
    ref = getattr(box, "ref", None) if box is not None else None
    return base is not None and ref is not None and getattr(ref, "SourceName", "") == base.Name


def d_compare_click():
    point = _base_point()
    menu = r.open_marking_menu(point) if point is not None else None
    if menu is not None:
        r.click_marking_row(menu, "Compare with Reference")


d_compare_click.wait_ms = 2500


def d_compare_shown():
    box = r.dialog("SciForgeRebuildCompare")
    h.check(
        "the right-click's Compare with Reference compares the base under the mouse (it took "
        "the active body's rebuild, the arm's)",
        _about_base(box),
        getattr(getattr(box, "ref", None), "SourceName", None),
    )
    r.close_dialogs()
    point = _base_point()
    menu = r.open_marking_menu(point) if point is not None else None
    if menu is not None:
        r.click_marking_row(menu, "Finish Rebuild")


d_compare_shown.wait_ms = 2500


def d_finish_shown():
    box = r.dialog("SciForgeRebuildFinish")
    h.check(
        "... and its Finish Rebuild opens the base's Finish (not the arm's)",
        _about_base(box),
        getattr(getattr(box, "ref", None), "SourceName", None),
    )
    if box is not None:
        r.click_button(box, "SciForgeRebuildFinishCancel")


d_finish_shown.wait_ms = 1500


def d_right_click():
    point = _base_point()
    menu = r.open_marking_menu(point) if point is not None else None
    if menu is None:
        return
    rows = r.marking_rows(menu)
    h.check(
        "the rebuilt base's right-click list has Stop Rebuild...", "Stop Rebuild..." in rows, rows
    )
    r.click_marking_row(menu, "Stop Rebuild...")


d_right_click.wait_ms = 1500


def d_stop_press():
    box = r.dialog("SciForgeRebuildStop")
    h.check("the right-click's Stop Rebuild... opened its window", box is not None, h.popups())
    if box is not None:
        words = box.findChild(QtWidgets.QLabel, "SciForgeRebuildStopState")
        text = words.text() if words is not None else ""
        h.check(
            "... for the base under the mouse (not the active body's rebuild, the arm's)",
            s["base_label"] in text and s["arm_label"] not in text,
            text,
        )
        h.check("deleting the rebuilt body is the default", box.delete_rebuilt.isChecked())
        r.click_button(box, "SciForgeRebuildStopOK")


d_stop_press.wait_ms = 2000


def d_stopped():
    from sciforge import bodies, rebuild

    doc = App.ActiveDocument
    base = doc.getObject(s.get("base_target") or "")
    live = rebuild.active_references(doc)
    h.check(
        "Stop Rebuild: the base's rebuild is stopped, the arm's goes on",
        len(live) == 1 and live[0].SourceName == s["target_name"],
        [(x.Name, x.SourceName) for x in live],
    )
    h.check("... the base is shown again", base is not None and bool(base.Visibility))
    h.check(
        "... and it is the active body",
        base is not None and bodies.active_body(doc) is base,
        getattr(bodies.active_body(doc), "Label", None),
    )
    h.check("... its rebuilt body is gone", doc.getObject(s["stop_target"]) is None)
    h.check(
        "... the joint still holds the base",
        base is not None and any(base.Name + "." in x for x in joint_subs()),
        joint_subs(),
    )
    h.check("one undo step", len(doc.UndoNames) == s["undo_before_stop"] + 1, doc.UndoNames[:3])
    h.shot("stopped")
    t.undo()


d_stopped.wait_ms = 1500


def d_undone():
    from sciforge import rebuild

    doc = App.ActiveDocument
    base = doc.getObject(s.get("base_target") or "")
    refs = rebuild.active_references(doc)
    mine = [x for x in refs if x.SourceName == base.Name] if base is not None else []
    h.check(
        "Undo: the base's rebuild is back (its rebuilt body there, the base hidden)",
        len(refs) == 2
        and doc.getObject(s["stop_target"]) is not None
        and base is not None
        and not base.Visibility,
        (refs, getattr(base, "Visibility", None)),
    )
    h.check("... its ghost drawn", mine and r.ghost_drawn(mine[0]))
    t.redo()


d_undone.wait_ms = 1500


def d_redone():
    from sciforge import rebuild

    doc = App.ActiveDocument
    base = doc.getObject(s.get("base_target") or "")
    h.check(
        "Redo: stopped again (the base shown, the arm's rebuild going on)",
        len(rebuild.active_references(doc)) == 1 and base is not None and bool(base.Visibility),
    )
    r.utilities_menu("Stop Rebuild...")  # the one left: the arm's


d_redone.wait_ms = 1500


def d_stop_arm():
    box = r.dialog("SciForgeRebuildStop")
    h.check("UTILITIES > AI > Stop Rebuild... opened its window", box is not None, h.popups())
    if box is not None:
        r.click_button(box, "SciForgeRebuildStopOK")


d_stop_arm.wait_ms = 2000


def d_arm_stopped():
    from sciforge import rebuild

    doc = App.ActiveDocument
    arm = doc.getObject(s["target_name"])
    h.check("no rebuild goes on any more", not rebuild.references(doc))
    h.check("... the arm is shown again", arm is not None and bool(arm.Visibility))
    h.check("... its rebuilt body is gone", doc.getObject(s["arm_stop_target"]) is None)
    h.check("the joint still holds both", joint_names() == ["Joint"], joint_subs())


def finish():
    r.close_dialogs()
    h.expect_no_errors("the jointed rebuild QA scenario")


h.run(
    "rebuild_qa_joints",
    [
        setup,
        a_start,
        a_started,
        b_finish,
        b_press,
        b_finished,
        b_undo_finish,
        b_undone,
        b_redone,
        c_start_base,
        c_half_way,
        c_describe,
        c_close,
        c_reopen,
        c_reopened,
        c_both_rebuilt,
        d_start_again,
        d_two_rebuilds,
        d_compare_click,
        d_compare_shown,
        d_finish_shown,
        d_right_click,
        d_stop_press,
        d_stopped,
        d_undone,
        d_redone,
        d_stop_arm,
        d_arm_stopped,
        finish,
    ],
)

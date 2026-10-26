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
"""

import os

import FreeCAD as App

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import rebuild_steps as r
from SciForgeTests.gui import timeline_input as t
from SciForgeTests.gui import versions_input as vi
from PySide import QtCore

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
        finish,
    ],
)

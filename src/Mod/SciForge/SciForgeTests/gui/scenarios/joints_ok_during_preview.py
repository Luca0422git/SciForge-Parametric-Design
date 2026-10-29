# SPDX-License-Identifier: LGPL-2.1-or-later
"""OK pressed the moment a new joint type is picked: the motion preview that type asks for
must not start once the dialog is closed (CI #295, vex_qa_real: the preview of a new
Revolute started a moment after OK, outside the joint's undo step, and the shaft kept a
turned pose that Undo of the next command brought back).

The block's top joined onto the plate's top (joints_steps); Motion tab > Type: Revolute; the
dialog's own update runs (as its timer does) and OK comes before anything else, as on a busy
machine where both were due at once. Then: no dialog, no preview playing (now and a second
later), the block still where the joint put it, one Revolute; Ctrl+Z takes the joint and
the move back in one step.
"""

import gc

import FreeCAD as App

from SciForgeTests.gui import bodies_steps as s
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import joints_steps as j

state = {}


def playing():
    """The joint previews still running (any dialog's, or one left behind by a closed one)."""
    from sciforge import joints_ui

    return [o for o in gc.get_objects() if isinstance(o, joints_ui.Animator) and o.running]


def joined():
    p = j.panel()
    h.check("one joint made", len(j.joint_list()) == 1, len(j.joint_list()))
    j.block_box("the block on the plate", j.ON_PLATE)
    if h.check("the dialog stays open", p is not None):
        j.click_tab(p, "Motion")
        j.choose_type(p, "Revolute")
        # the dialog's update (its timer would run it now), then OK before anything else
        p._timer.stop()
        p._recompute()
        j.ok()


def closed():
    j.no_dialog("OK")
    h.check("no preview plays after OK", not playing(), playing())
    j.block_box("the block where the joint put it", j.ON_PLATE)
    found = j.joint_list()
    h.check(
        "one Revolute",
        len(found) == 1 and j.joints_module().fusion_type(found[0]) == "revolute",
        [(x.Label, j.joints_module().fusion_type(x)) for x in found],
    )
    state["plc"] = App.Placement(j.block().Placement)


def still():
    h.check("a second later: no preview plays", not playing(), playing())
    h.check(
        "a second later: the block has not moved",
        j.block().Placement.isSame(state["plc"], 1e-9),
        (j.block().Placement, state["plc"]),
    )
    s.undo()


def undone():
    h.check("Ctrl+Z: the joint is gone", not j.joint_list(), [x.Label for x in j.joint_list()])
    j.block_box("Ctrl+Z: the block back where it was made", j.HOME)


steps = [s.new_design("OkDuringPreview")] + j.two_boxes() + j.pick_pair("pair")
steps += [joined, closed, still, undone]
h.run("joints_ok_during_preview", steps, paced_by="state")

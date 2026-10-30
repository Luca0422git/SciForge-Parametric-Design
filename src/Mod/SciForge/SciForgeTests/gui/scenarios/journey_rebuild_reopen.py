# SPDX-License-Identifier: LGPL-2.1-or-later
"""REBUILD journey, part 4 (real clicks and keys; steps and hand numbers in
journey_rebuild_steps.py): the stranger's bracket and the clamp inserted, jointed (two
clicks), the bracket rebuilt by the AI in the chat up to "Shall I finish it?"; the design
saved half way (Ctrl+S, the Save dialog), closed and opened again: the reference, its ghost,
the AI's steps in the active rebuilt body, the joint still on the original. Finished by hand
(UTILITIES > AI > Compare with Reference: 100 % > Finish Rebuild... > Finish): the bracket's
name, the joint on the rebuilt bracket. Saved again (the version prompt), closed, opened
again: the timeline, the joint, the clamp in place; the base extrude double-clicked and made
2 mm thicker: the clamp rides up with the top face, the holes widened to 6.5."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_rebuild_steps as j

h.run(
    "journey_rebuild_reopen",
    j.insert_steps()
    + j.joint_steps()
    + j.rebuild_steps()
    + j.reopen_steps("bracket_half_way", j.bracket_reopened_half_way)
    + j.finish_by_hand_steps()
    + j.reopen_steps("bracket_finished", j.bracket_reopened_finished)
    + j.edit_steps()
    + [j.finish_scenario("the rebuild journey with save and reopen")],
    paced_by="state",
)

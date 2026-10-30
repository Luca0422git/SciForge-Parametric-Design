# SPDX-License-Identifier: LGPL-2.1-or-later
"""REBUILD journey, part 1 (real clicks and keys; steps and hand numbers in
journey_rebuild_steps.py): a mounting bracket a stranger sent as a STEP file (counterbored
holes on a 2 x 2 grid, a pocket, a chamfer and two fillets: no timeline) and a clamp come in
with INSERT > Insert STEP; the clamp is jointed (ASSEMBLE > Joint, two clicks) onto a
counterbored hole of the bracket. Right-click the bracket > Rebuild with Timeline (AI)...:
the chat opens with the ready message; Send: the AI (a fake local model that reads only
SciForge's answers) describes the part, builds the plan step by step but forgets its chamfer,
compares after every feature, makes the chamfer from the verdict's ready call and asks before
finishing. UTILITIES > AI > Compare with Reference shows 100 %. The
person tells the AI to finish: the rebuilt body takes the bracket's name, component and
place, the joint moves onto it; one Ctrl+Z undoes the finish, Ctrl+Y does it again. Then the
rebuilt part edited like a person: the base extrude double-clicked in the timeline and made
2 mm thicker (the pocket and the counterbored holes stay on the top face, the clamp rides up
with it), the hole's diameter 6 -> 6.5 (the pattern follows)."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_rebuild_steps as j

j.s["forget"] = "chamfer"  # the AI leaves the plan's chamfer out: the verdict brings it back
h.run(
    "journey_rebuild",
    j.insert_steps()
    + j.joint_steps()
    + j.rebuild_steps()
    + j.compare_steps()
    + j.finish_steps()
    + j.edit_steps()
    + [j.finish_scenario("the rebuild journey")],
    paced_by="state",
)

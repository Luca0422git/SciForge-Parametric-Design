# SPDX-License-Identifier: LGPL-2.1-or-later
"""REBUILD journey, part 2 (real clicks and keys; steps and hand numbers in
journey_rebuild_steps.py): the stranger's bracket inserted (INSERT > Insert STEP) and
rebuilt with a timeline by the AI in SciForge's chat (right-click > Rebuild with Timeline
(AI)..., Send, "finish"), then used in SIMULATION: Workspace > Simulation, New Study >
Create Study, Structural Constraints Fixed on the four counterbores' floors, Structural
Loads Force 1000 N straight down (Vector) on the far end face, Solve: the largest stress is
at least the bending stress worked out by hand at the pocket (76 MPa), the RESULTS legend
shows the safety factor. Back in DESIGN the base extrude double-clicked and made 2 mm
thicker; in SIMULATION the study is out of date; Solve again: the stress drops (by hand
0.68 at the pocket), the safety factor rises."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_rebuild_steps as j

h.run(
    "journey_rebuild_sim",
    j.insert_steps(with_clamp=False)
    + j.rebuild_steps()
    + j.finish_steps(with_joint=False, with_undo=False)
    + j.sim_steps()
    + [j.finish_scenario("the rebuild journey in SIMULATION")],
)

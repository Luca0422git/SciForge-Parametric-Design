# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION journey, part 2 (sim QA): the bracket of part 1 (journey_sim_bracket.py, built
the same way with real clicks and keys), solved; a Surface Probe on the arm; then:

19 Back to DESIGN: double-click the sketch in the timeline, double-click the arm's 5 mm
   dimension, type 7, Finish Sketch: the arm is 7 thick (21594.51 mm3), the holes stay at x 40,
   the fillet follows the corner.
20 SIMULATION: the study is out of date; Solve again: up to date; the highest stress stays in
   the base plate at the bolts (it does not depend on the arm), the arm moves less; the solve
   is not an undo step.
21 The probe at the same place on the arm: the stress dropped as (5 / 7)^2 = 0.51 and matches
   M c / I for 7 mm (hand numbers in journey_sim_steps.py).
22 Ctrl+S: SciForge's Save dialog (name, place), Save; close the design's tab.
23 Open it again: DESIGN first; Workspace > Simulation: the study, its constraint and load, not
   out of date; RESULTS: the same numbers from the same mesh.
"""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_sim_steps as j

folder = j.report_folder()
h.run(
    "journey_sim_bracket_edit",
    j.design_steps("SimJourneyEdit")
    + j.study_steps()
    + j.probe_steps("p1")
    + j.edit_steps()
    + j.probe_steps("p2")
    + [j.step(j.ratio_check, "ratio_check")]
    + j.reopen_steps(folder),
    paced_by="state",
)

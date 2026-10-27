# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION journey, part 1 (sim QA): an L-bracket for a robot designed and checked the way
Luca would, only with real clicks and keys (the hand-worked numbers are in
SciForgeTests/gui/journey_sim_steps.py).

1-5  A new design: the L drawn on the front plane with the Line tool (grid 1 mm), the arm's
     thickness dimensioned 5, Finish Sketch, Extrude 40 (19000 mm3), two Hole tool bolt holes
     (diameter 6, through all) on the base, Fillet r 3 on the inside corner, Physical Material
     PLA (18794.5 mm3, 23.31 g).
6-11 Workspace > Simulation, New Study (opens by itself), Create Study; Study Materials: PLA,
     Same as Model, yield 35.9 MPa; Fixed on the two hole walls; Force 50 N on the arm's top
     across the arm (Vector, Fx -50 N); Pre-check green; Solve; the RESULTS tab.
12-18 RESULTS: safety factor = 35.9 / the highest von Mises; the highest von Mises in the
     base plate at the bolts (12 .. 60 MPa); the largest movement at the arm's top (1.0 .. 3.2
     mm, hand estimate 2.1); Min/Max tags; Deformation Actual (x1) and Adjusted (5 % of the
     part); a Surface Probe on the arm's outer face 10 mm above the base reads M c / I (band
     0.80 .. 1.10, why in the steps file); Report saved with the numbers.
"""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_sim_steps as j

h.run(
    "journey_sim_bracket",
    j.design_steps("SimJourney") + j.study_steps() + j.results_steps(j.report_folder()),
)

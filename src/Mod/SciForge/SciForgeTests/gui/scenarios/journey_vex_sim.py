# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX journey, part 2: the same piece of robot built with real clicks and keys (as in part 1:
inches, eight STEP files at once, the rails aligned and 5 in apart, standoffs, bearing flats,
screws, Keps nuts, the shaft and the wheel), then SIMULATION on rail 1: New Study (Static
Stress), Study Materials with every other body left out (each row named with its component)
and rail 1 in aluminium, Fixed on the walls of its two end holes, a Force of 20 lbf straight
down on the walls of its middle hole, Pre-check, Solve; RESULTS: the displacement, stress and
safety factor against the numbers worked out by hand (journey_vex_steps.py, section 8), a
Surface Probe and a Report."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_vex_steps as j

h.run(
    "journey_vex_sim",
    j.start_steps("JourneyVexSim")
    + j.insert_steps()
    + j.align_steps()
    + j.standoff_steps()
    + j.bearing1_steps()
    + j.bearing2_steps()
    + j.screw_steps()
    + j.nut_steps()
    + j.shaft_steps()
    + j.wheel_steps()
    + j.sim_steps()
    + j.results_steps(),
)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""VEX journey, part 1: a piece of a VEX V5 robot built the way a team member builds it in
Fusion, only with real clicks and keys (steps and hand-worked numbers in
journey_vex_steps.py): a new design in inches (Change Active Units), INSERT > Insert STEP with
eight part files picked at once in the file dialog, rail 2 aligned onto rail 1 by the
square-hole centre dots and moved 5 in up (parallel, 5 in apart, on the 0.5 in hole grid);
5 in standoffs between the rails (J, Duplicate With Joints), a bearing flat on each rail
(Align; the second one the same file inserted again), six screws (J, Duplicate With Joints
into five more holes), four Keps nuts, the 6 in shaft through bearing, rail, rail, bearing on a
revolute joint, the wheel rigidly on it between the rails; Drive Joints (only the shaft and the
wheel turn), a Rigid Group for the frame and the drive again; the screw's file inserted again
(an occurrence: the parts list counts 7 screws); Ctrl+S, close, Open: everything where it
was, the joint drives, its Offset edited (the wheel follows); the screw's file again is still
an occurrence; File > New Drawing with a parts list (TABLES > Table): 8 screws in one row."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_vex_steps as j

h.run(
    "journey_vex",
    j.start_steps("JourneyVex")
    + j.insert_steps()
    + j.align_steps()
    + j.standoff_steps()
    + j.bearing1_steps()
    + j.bearing2_steps()
    + j.screw_steps()
    + j.nut_steps()
    + j.shaft_steps()
    + j.wheel_steps()
    + j.drive_steps("j5_drive", 45.0)
    + j.rigid_group_steps()
    + j.drive_steps("j5_drive_grouped", 90.0)
    + j.again_steps()
    + j.reopen_steps()
    + j.drawing_steps(),
    paced_by="state",
)

# Session: VEX journey (beta 3, 2026-10-27)

Branch `sf/journey-vex` from `beta3` (VEX, Static Stress simulation, Auto Timeline, patch
0.1.0-beta.2.2), with `sf/vex-qa` merged in twice (its fixes up to 1df898ca). Nobody had built
a piece of a VEX robot end to end with every beta 3 tool together; this session did, only
with real clicks and keys (code only makes the test files and reads results), the way a VEX
V5 team member would in Fusion, and fixed what broke on the way.

## The journey

Scenarios `journey_vex` (part 1: steps 1 to 7) and `journey_vex_sim` (part 2: the same build,
then step 8). Steps and hand-worked numbers: `SciForgeTests/gui/journey_vex_steps.py`.

The parts are SciForge's own VEX-like parts (`SciForgeTests/fixtures/vex/vex_parts.py`, from
VEX's published numbers) written as STEP files, plus three made in the steps file with the
generator's own builders as test data: a 5 in standoff and a 6 in square shaft (VEX sells 5 in
standoffs; teams cut 12 in shafts to length) and a plain 2.75 in wheel (a disc 0.5 in wide with
a 0.13 in square hole).

**Why 5 in standoffs and a 6 in shaft:** the brief asks for rails 5 in apart with standoffs
between them and a shaft through bearing, rail, rail, bearing; the generator's 1 in standoff
cannot bridge 5 in and its 3 in shaft cannot pass 5.3 in of stack. The rails lie one above the
other (a gearbox block), 5 in apart between the webs' inside faces.

1. **A new design in inches.** Browser > Units: mm > Change Active Units > Inch, OK.
   INSERT > Insert STEP: the real file dialog (Qt's own under xvfb), the folder typed, then
   eight file names at once in quotes, Enter: two 1x2x1x25 C-channels (sharp and rounded hole
   corners), the 5 in standoff, the #8-32 screw, the Keps nut, the 6 in shaft, the bearing
   flat and the wheel. Eight components named after the files, side by side along X, the
   Move dialog on all eight, OK. Rail 1's holes checked by hand on the 0.5 in grid.
2. **Rail 2 onto rail 1, 5 in apart.** MODIFY > Align, Objects: Components, ViewCube TOP
   (from the front the front flange hides the web's row 0), From: rail 2 next to its hole
   (0, 1) (the hole's centre dot lit), To: rail 1 next to its hole (0, 0) (lit). Align takes
   its smallest turn: rail 2 came out face down but pointing along -X, half a rail aside;
   Angle twice (half a turn about the hole's axis): face down over rail 1's footprint. OK.
   Then rail 2's browser row, M, Z Distance typed as a plain `5` (inches), OK. Checked by
   hand: rail 2's hole (i, 1 - j) over rail 1's hole (i, j) at x = 0.25 + 0.5 i in for
   i = 0, 12, 24, parallel, face down, the webs' inside faces 5.000 in apart.
3. **Standoffs, screws, nuts.** J: the standoff's top end (its centre lit), rail 1 next to
   hole (2, 1): the standoff stands on the hole from z 0.064 in up 5 in, touching rail 2.
   Its row, ASSEMBLE > Duplicate With Joints, a click next to hole (22, 1): the second one.
   (After step 4's bearings:) J: the screw head's underside (view from below), the bottom
   bearing's mounting hole: the screw goes up through bearing and rail. Duplicate With Joints
   into five more holes (the bearing's other hole and the two holes under the standoffs from
   below, the top bearing's two holes from above): every screw on its hole centre with its
   head on the face (checked by hand). J: the Keps nut's washer onto rail 1's inside face at
   hole (11, 1); Duplicate With Joints onto (13, 1) and rail 2's inside face at (11, 0) and
   (13, 0) (seen from below into the gap): four nuts on the bearing screws' ends.
4. **Bearings, shaft, wheel.** Align: the bearing's top next to its bore onto rail 1's
   underside at hole (12, 1): bore on the hole, mounting holes on (11, 1) and (13, 1). INSERT
   > Insert STEP of the bearing again: an occurrence `bearing_flat:2`; Align onto rail 2's
   outer face at (12, 0). J: the shaft's top end onto the top bearing's bore, Offset Z typed
   `-5.5` (inches), Motion > Revolute, OK: the shaft from z -0.272 to 5.728 in through
   bearing, rail, rail, bearing. J: the wheel's face next to its square hole onto the shaft's
   top end, Offset Z `-3.5`, OK (rigid): the wheel from z 2.228 to 2.728 in, between the
   webs and clear of both rails' flanges.
5. **Drive, Rigid Group.** Right-click the revolute > Drive Joints, 45: the shaft is
   0.177 in wide across (turned 45 degrees), the wheel turned 45 degrees about the shaft,
   nothing else moved; OK, Undo. Six frame rows (both rails, both standoffs, both bearings)
   picked with Ctrl in the browser, ASSEMBLE > Rigid Group, OK; Drive Joints 90: again only
   the shaft and the wheel move.
6. **The screw's file again.** INSERT > Insert STEP of the screw: `screw_8_32_x_0_5:7`, an
   occurrence of the first screw (not a second reading); Y Distance -3 in the Move dialog,
   OK. A drawing's parts list (`drawing_core.parts_rows`, what DRAWING's Parts List shows)
   counts 7 screws in one row, 4 nuts, 2 standoffs, 2 bearings and one of each other part.
   J: the new screw through rail 2 into the first standoff's top.
7. **Save, close, reopen.** Ctrl+S: SciForge's Save dialog (name, location), Save; the
   design's tab closed; the application bar's Open: the file dialog, the file typed: every
   one of the 22 components where it was, every joint back, still inches; Drive Joints 30
   drives the shaft and the wheel only.
   After the reopen: the revolute's row > Edit Joint, Offset Z -5.75: the shaft 0.25 in lower
   and the wheel with it, nothing else; Undo. The screw's file inserted again: still an
   occurrence of the first screw (`screw_8_32_x_0_5:8`), the parts list counts 8.
   File > New Drawing (Full Assembly, ASME B in inches), a Front base view at 1:4 by a click,
   TABLES > Table by a click: the drawing's parts list has 8 screws in one row, 4 nuts, 2
   standoffs, 2 bearings and one of each other part, with its balloons.
8. **SIMULATION on rail 1** (part 2). Workspace > Simulation: New Study opens by itself,
   Create Study (Static Stress). Study Materials: every row but rail 1's unticked (17 clicks),
   rail 1's study material Aluminium. Structural Constraints, Fixed: the four walls of each
   end hole (0, 1) and (24, 1) clicked, the view turned until each wall shows (8 faces).
   Structural Loads, Force: the four walls of the middle hole (12, 0), 20 lbf, Direction
   Vector, Fz -20 lbf. Pre-check, Solve. The solve warns that the default mesh (elements
   about 4 mm on 1.6 mm walls) is too coarse ("comes out too stiff"): MANAGE > Settings >
   Mesh, Absolute value 0.08 in, OK, Solve again. RESULTS: Stress, Surface Probes on the
   front flange near its top at mid-span, Report saved as HTML (study, author, lowest safety
   factor, material, constraint, load all in it).

## The numbers: hand against SciForge

Rail 1 by hand (journey_vex_steps.py section 8): a 1 x 0.5 in C-channel of 0.064 in
aluminium, A = 0.1198 in2, centroid 0.1485 in above the web's underside, I = 2.769e-3 in4
without holes (2.14e-3 through a column of holes, centroid 0.153 in). Held by the walls of
its end holes 12 in apart: square holes grip only 0.064 in of metal, so the ends turn - a beam
on two supports, not clamped. 20 lbf at the middle.

| | By hand | SciForge, default mesh (7952 nodes) | SciForge, 0.08 in mesh (91173 nodes) |
|---|---|---|---|
| Max displacement | P L^3 / 48 E I = 0.0256 in = 0.65 mm (no holes) | 0.719 mm | 0.879 mm |
| Bending stress, flange top at mid-span | M c / I = 60 x 0.3516 / 2.769e-3 = 52.5 MPa (no holes); 67 MPa through the holes | | probe 0.03 in under the top: 64.8 MPa (hand 48.0 / 61.2 there) |
| Max von Mises | | 67.5 MPa at an end hole's corner | 150.9 MPa at the same corner |
| Min safety factor (yield 95 MPa: SciForge's Aluminium) | 95 / 52.5 = 1.8 on the plain section | 1.41 | 0.63 ("below 1, the part yields"), at that corner |

Why these are sensible for 0.064 in aluminium: the displacement converges (0.866 mm at a
0.12 in mesh, 0.879 mm at 0.08 in, measured headless) about 35 % above the plain-section hand
value, which leaves out the holes (I is 23 % lower through a column of them), the twist of the
open channel (the load sits 0.25 in off the web's middle) and shear. The stress away from the
supports (the probe, 64.8 MPa) sits between the plain-section and the net-section hand values;
at the probe the safety factor is 95 / 64.8 = 1.5 with SciForge's generic aluminium, about 3
with VEX's 5052-H32 (yield 193 MPa). The peak at the corner of a held square hole is a
singularity: a sharp re-entrant corner held fixed has no finite stress in a linear model, and
it reads higher with every finer mesh (67.5 MPa, 114.3 MPa at 0.12 in, 150.9 MPa at 0.08 in).
A real screw spreads that load; the peak is not the rail yielding.

## Bugs found and fixed

- **An Align of components in a jointed design counted as a pending move**
  (`align.py`, `align_ui.py`, `joints.py`): after the bottom bearing was aligned onto rail 1
  (joints existed: the standoff's), the next J asked "Components moved: Capture Position /
  Revert" as if the bearing had been dragged, and Revert put the bearing back where it was
  while its Align step stayed in the timeline. Fusion's Align is a timeline step, not a
  pending move. On OK the Align now writes its components' places into the joints' baseline
  (and the newest captured position), inside its undo step (`joints.accept_places`,
  `align.settle`). Test: `SciForgeTests/headless/journey_vex_check.py` (run by
  `unit/test_journey_vex_freecad.py`): 5 of its checks fail on the old code (the Align is a
  pending move; Redo leaves it pending; Revert takes the Align back twice; with a captured
  Position). The journey's "J opened the Joint dialog" checks fail on the old code too.
- **Study Materials and the Simulation Model named every body "Body1"**
  (`simulation_dialogs.py`, `simulation_browser.py`): a design of inserted parts has a
  "Body1" in every component, so leaving bodies out of the study meant 18 identical rows. A
  body inside a component is now "<component> / <body>" (`c_channel_1x2x1x25 / Body1`); root
  bodies keep their own name and the browser still finds a row by the body's label. Test:
  `journey_vex_sim`'s "a row per body, each named with its component" and "the browser's
  Simulation Model names rail 1's body with its component" (both fail on the old code).
- **TABLES > Table froze for minutes on the VEX piece; balloons found no part**
  (`drawing.py` `_sight_hit`): a parts list's balloons look for each part along sight lines
  through the view, in design coordinates, but tested each body where it sits inside its
  component. Every component of an inserted assembly is moved, so no line ever hit: each row
  walked every visible edge of the view (over ten minutes, the window frozen, until the test
  timed out; a stack dump showed `add_parts_list > add_row_balloons > component_anchor >
  _sight_hit`), and a click on a part with Balloon found nothing. The line is now taken into
  each body's component before measuring, and a body whose box it misses is skipped. Test:
  `journey_vex_check.check_balloons_on_moved_components` (4 of its 5 checks fail on the old
  code) and the journey's drawing steps.
- **... and then still 140 s** (`drawing.py`): with the parts found, the Table still froze
  the window for over two minutes (six stack dumps 25 s apart, all in `_sight_line >
  centre_of`): every edge tried for an arrow measured every part of the view again (the
  view's centre copies all 19 bodies). The centre is now measured once per parts list:
  140.4 s -> 8.2 s headless on the saved VEX piece. Test:
  `journey_vex_check.check_balloons_quick_on_a_big_part` counts the measurements (31 on the
  old code, at most 2 now).

## Not bugs (worked around in the journey)

- **xvfb has no window manager**: after the file dialog closed nothing gave the main window
  the keyboard back, so J and M went nowhere (`keys_to_window` in the steps raises the
  window, as a desktop's window manager does).
- **Ctrl+O with no design open** did nothing (Home in front, the keyboard in Home's text
  box: QTest to that box or to the window), while Ctrl+O in a design opens the Open dialog;
  the only owner of the key is SciForge's window shortcut. The journey clicks the
  application bar's Open instead. Not checked on a real desktop (synthetic keys under xvfb):
  worth a try on Luca's PC (Home, Ctrl+O).
- **Align's turn**: with only a face's normal to match (a hole's X is not used, unlike a
  joint's), Align takes the smallest turn, which here pointed rail 2 the other way; Angle
  twice fixed it. Fusion's Align has the same Flip / Angle buttons for this (G).
- **Row 0 of a channel's web is hidden by the front flange** in the default view: the
  journey uses the ViewCube's TOP for the Align, row 1 for the standoffs, views from below
  for the screws and nuts (as a person turns the view).

## Seen, not fixed

- **No 5052-H32 aluminium** in the material library (VEX's aluminium): the study used
  "Aluminium" (FreeCAD's Aluminum-Generic, yield 95 MPa where its card has none), half the
  real yield strength, so safety factors read about half of what VEX parts have.
- **The lowest safety factor sits on a singularity** (a sharp corner held Fixed) and falls
  with every finer mesh (1.41, 0.83, 0.63): the legend then says "below 1, the part yields"
  for a rail that holds 20 lbf. `parity/simulation.md` lists it ("Stress at a fixed edge ...
  the same in Fusion. The recipe explains it"), but nothing on the screen does: a note when
  the lowest value sits on a constraint's edge would keep a team from reading it as a
  failure (an open question for Luca; Fusion has no such note either, G).
- Align's and Joint's selection boxes say "Face of Body1" for any part of an inserted
  assembly (the same naming as above; Fusion's boxes say "1 selected").

## Speed (this sandbox: 4 shared CPUs, software OpenGL)

| What | The VEX report (298-part robot) | This journey (22 components) |
|---|---|---|
| Insert STEP, many files at once | 20 files 21.8 s (1.1 s a file) | 8 files 6.8 - 7.3 s (0.9 s a file) |
| Open | 36 s (0.12 s a part) | 2.9 - 3.1 s for 22 components (0.13 s a part) |
| Save | 3.8 s | 0.45 - 0.54 s |
| Drive Joints, one step of the dialog | 0.70 s | 0.04 - 0.14 s |
| Hover: a hole's dot lit (from the mouse arriving to the dot lit, 25 hovers a run) | first 0.05 - 0.15 s, then 0.014 s (the computation) | median 0.052 - 0.054 s, slowest 0.135 - 0.181 s (the first hover on a rail's face: its index made) |
| Static Stress solve of rail 1 | | 6.5 s default mesh, 32 s at 0.08 in (91k nodes) |
| Drawing: a Front base view of the piece | | 4.3 s headless |
| Drawing: TABLES > Table with its 8 balloons | | over 10 min before the fixes, 140 s after the first, 8.2 s now (headless) |

The per-part costs agree with the VEX report's robot (open about 0.13 s a part, insert about
1 s a file); hovering is well inside the 0.1 s target except the first hover on a big face.

## Tests (real FreeCAD 1.1.4 under xvfb, OMP_NUM_THREADS=1)

- `journey_vex` 321 checks (about 4.5 min), `journey_vex_sim` 224 checks (about 5 min): PASS.
- `--only unit` includes `test_journey_vex_freecad` (headless `journey_vex_check.py`, 4
  checks: the Align not a pending move, the same with a captured Position, balloons on
  moved components, balloons measured once).
- After the Align and simulation fixes: `components2_move` 345, `direct_components` 220,
  `joints2_drag` 80, `joints2_motion` 101, `joints_asbuilt_group` 135, `joints_drive` 108,
  `modify_align` 232, `modify_align_points` 224, `vex_align` 145, `vex_qa_align` 99,
  `surface4_misc` 28, `sim_setup_browser` 67, `sim_setup_components` 42,
  `sim_setup_documents` 71, `sim_setup_two` 52: PASS.
- After the drawing fixes: `drawing_assembly` 62, `drawing_pdf_layers` 55,
  `flatpattern_drawing` 42, `vex_qa_occ` 43: PASS.
- `--only base` (unit 2717, golden 614 + 2 xfail, headless 339 calls, docs 157, agent 81,
  rebuild 68 + 14, recognize 71 parts, sim 138, simqa 205, smoke, journey, restart): all
  passed, and again after the drawing fixes (the same counts; the 2 xfails are the
  known `plate_hole_grid` and `sf_loft_merge_slot_volume`).

## For the next session

- The journey's step files: `SciForgeTests/gui/journey_vex_steps.py` (hand numbers in the
  section comments), scenarios `journey_vex.py`, `journey_vex_sim.py`; helpers worth reusing:
  `answer_file_dialog` (drives Qt's own file dialog with keys: several files at once in
  quotes), `keys_to_window` (xvfb), `timed_hover`, `click_wall` (turns the view until a small
  face can be clicked).
- Open questions for Luca: a note on the screen when the lowest safety factor sits on a
  singularity; a 5052-H32 aluminium in the material library for VEX teams.

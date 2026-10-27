# Session log: beta 3, QA of the whole SIMULATION workspace (sim-qa)

Branch `sf/sim-qa` (from the integration branch `beta3`: the engine and its accuracy QA, the
SETUP tab, the RESULTS tab; `beta3` merged again at 48d5500b for its later fixes), 2026-10-27.
Rules: `docs/sciforge/dev/briefs/beta3-qa.md`, `beta3-common.md`, `common.md`; the briefs
`beta3-sim-*.md`, the four reports (sim-core, sim-engine-qa, sim-ui, sim-results) and their
session logs; research `fusion-simulation.md`; parity `docs/sciforge/parity/simulation.md`.

## The bracket journey (real clicks and keys; code only reads results)

`SciForgeTests/gui/journey_sim_steps.py` (steps and every hand-worked number),
`scenarios/journey_sim_bracket.py` (design, study, results) and
`scenarios/journey_sim_bracket_edit.py` (thicker arm, solve again, save / close / reopen).

The design, as Luca would make it: Create Sketch on the front plane, the L drawn with the Line
tool (six corners, grid 1 mm), the arm's and the base's thickness dimensioned 5 (the line
tool's clicks land a few tenths off the grid: Fusion's grid snap is off by default too; the
dimensions make them exact), Finish Sketch, Extrude 40, two Hole tool bolt holes (diameter 6,
All) on the base 10 mm either side of the middle at x 40, Fillet r 3 on the inside corner,
MODIFY > Physical Material: PLA. Every volume checked by hand: 19000, 18858.63, 18717.26,
18794.51 mm3; 23.31 g.

The study: Workspace > Simulation (New Study opens by itself), Create Study, Study Materials
(PLA, Same as Model, yield 35.9 MPa, E 3640 MPa: FreeCAD's PLA-Generic card), Fixed on the two
hole walls, Force 50 N on the arm's top face across the arm (Vector, Fx -50 N), Pre-check green,
Solve.

Why across and not down: down on an upright arm only squeezes it (F / A = 0.25 MPa) and the
arm's thickness would not matter; the hand formula M c / I is for an arm loaded across, as a
shelf bracket screwed to a wall is ("down" in use).

| What | SciForge | Hand estimate | Why the band |
|---|---|---|---|
| Highest von Mises | 18.08 MPa at (37, -10, 5): the bolt hole's edge on the base | 16.1 MPa nominal across the bolt line (M = 50 x 37.5 = 1875 N mm, 28 mm of plate left) | the hole and the rigid hole wall raise it; band 12 .. 60 |
| Safety factor | 1.986 | 35.9 / 18.08 = 1.986 | exact |
| Largest movement | 2.091 mm at the arm's top | 0.47 (arm, F L^3 / 3EI) + 1.62 (base plate turning, M L / EI x 37.5) = 2.09 mm | band 1.0 .. 3.2 |
| Probe, arm's inner face, z 14.19 | 7.38 MPa | 6 M / (b t^2) = 7.74 MPa (ratio 0.95) | wide arm: plane strain lowers von Mises up to 12 %; band 0.80 .. 1.10 |
| Reaction at the holes | 50 N along +X, 0, 0 | 50 N | exact |
| After the arm 5 -> 7 mm (timeline edit) | probe 3.86 MPa at the same node; ratio of the arm's stress per N mm of moment 0.523 | (5 / 7)^2 = 0.510; 6 M / (b t^2) = 3.95 MPa | band 0.45 .. 0.58 |
| Highest von Mises after | 17.05 MPa (still at a bolt hole) | unchanged by the arm | 0.75 .. 1.25 of before |
| Largest movement after | 1.761 mm | less than before (the arm's own part drops as (5/7)^3) | |

Then: Show Min/Max tags, Deformation Actual (x 1) and Adjusted (5 % of the part's size), a
Surface Probe, Report (saved, with PLA, the safety factor, the reaction, the picks in plain
words); DESIGN, the sketch double-clicked in the timeline, the arm's dimension double-clicked,
7, Finish Sketch (the holes stay at x 40, the fillet follows the corner); SIMULATION: out of
date, Solve again, up to date, the solve no undo step, the design needs no recompute; Ctrl+S
(SciForge's Save dialog: name and place), close, open again: DESIGN first, the study, its
constraint and load, not out of date, RESULTS with the same numbers from the same mesh.

## Bugs found and fixed (each its own commit, each with a test that fails on the old code)

1. **Reading a body's material marked the design as changed** (243668ad). The study's "Same as
   Model" material was read from the body's own material object
   (`body.ShapeMaterial.getPhysicalValue`), and FreeCAD then marks the body "touched": after
   Study Materials, the pre-check light or a solve the design needed a recompute, and right
   after a Save it was still unsaved (found by the journey's save step: Body touched). The
   engine reads FreeCAD's library copy by its id now (a material only the file has: read from
   the body, the mark taken away again). Engine check "reading a body's material changes
   nothing".
2. **A RESULTS marking menu** (ad1ecfd2): a right click on RESULTS opened SETUP's ring.
   `ribbon_config.SIMR_MARKING_MENU` / `SIMR_MARKING_LIST` (Surface Probes, Show Min/Max,
   Animate, Results Details, Finish Results, Report; Slice Plane, Reaction Force, Show Mesh),
   picked by the tab; Repeat offers the last command of the tab shown. Scenario `sim_qa_menus`.
3. **Free movements printed rounding noise** (d0c8174d): "through (50, -1.1e-14, 5)",
   "(0.707, 0.707, 1e-16)" in the pre-check's "not held" sentences and DOF View.
   `describe_free_mode` cleans them. Unit test `test_words_without_rounding_noise`.
4. **DOF View used the engine's private `_held_rows` / `_pieces`** (bac9ee58): public
   `simulation.free_motions(study)`; `not_held` shares it. Engine check "free motions, public".
5. **Bearing Load's default -Z ran along a hole drilled along Z** (7f28d371): only the dialog
   turned it across; the AI's `add_load` and scripts got a solve that failed with "Flip the
   direction". The engine turns the default across the hole (`core.across_axis`) and refuses a
   direction along it in `add_item` / `update_item` (the dialog's sentence, shared). And
   (bc4aa162) a bearing direction along its hole (an old item, picks changed) is told so at the
   solve instead of "Flip the direction". Engine check "a bearing load's default direction"
   (reaction 100 N), unit test `test_bearing_along_its_hole_says_so`.
6. **The engine did not notice a body deleted mid-solve** (f2fe4dd1): a script or the AI
   polling the Job got "Cannot access attribute 'Label' of deleted object" (or FreeCAD's
   material rows); only the Solve dialog checked. The Job remembers the study's bodies and
   stops with "Beam was deleted while it solved: the solve stopped. Solve again for the design
   as it is now.", nothing left behind. Engine check "a body deleted while it solves".
7. **`hole_common.abandon` left the closed design's undo step open** (e5f017a7): it now closes
   it once no dialog is open (`hole_common.close_left_step`, also used by SIMULATION's own
   check, which did it alone before). Scenario `sim_qa_close`; `sim_setup_odd` H; every hole
   scenario and `inspect_qa` (Measure uses abandon) pass.
8. **Greyed SETUP commands said only "Not in SciForge yet"** (25e4640d): Linear / Angular
   Global Load, Point Mass, Bolt / Rigid Body Connector now say what to use meanwhile. Unit
   test `test_greyed_ribbon_commands_say_what_to_use`.
9. **Reaction forces showed the solver's rounding noise** (d44ce596): "Fixed 1 | 50 | 1.3e-7 |
   -5e-6" in the report, the Reaction Force table and its tags. Unit test
   `test_reactions_without_rounding_noise`.
10. **FreeCAD's words in the dialogs and the report** (0e36d4a8): Study Materials, its properties
   line, Results Details and the report showed FreeCAD's card names ("PLA-Generic") where the
   Physical Material dialog says "PLA", and the report's constraints said "Body: Face10,
   Face11". `simulation.material_label()`; the report says "Body: 2 faces". The journey checks
   both (93 checks).
11. **A design that is only a mesh** (5178c8e1): an imported STL got only "The study has no
   solid body to simulate."; the pre-check now names the mesh and points to MESH > Convert
   Mesh. Engine check "a design that is only a mesh".
12. **`bodies.density` marked the body changed too** (dc6684d4, shared file): the same trap for
   a material outside SciForge's list (PVC from a FreeCAD file): every mass shown left the
   design needing a recompute. Read from FreeCAD's library copy; the engine check above covers
   a PVC body. `bodies_look`, `misc_materials`, `bodies_qa`, `inspect_qa4` run again.
13. **SciForge crashed when a design was closed with Surface / Point Probes open**
   (e86782e1): closing the design destroys its 3D view, Qt then sends the view's widget a
   "mouse left" event, and the probes' hover redrew its tags at once, asking the dying view
   where each tag is: a segmentation fault (every open design lost). Found because the
   journey's FreeCAD crashed at its very end (all checks passed, the process exit failed);
   Python's `faulthandler` in a copy of the scenario named the chain (`_LeaveWatch` ->
   `_Hover.left` -> `set_hover` -> `TagLayer.relayout` -> `getPointOnViewport`), and a small
   scenario made it plain (a solved beam, Surface Probes, the mouse over the result, the design
   closed: crash, every time). The hover now clears a moment later and only while its results
   show in a live view; results that go with their design stop the hover and end their dialog
   a moment later (it stayed open on the closed design). Scenario `sim_qa_results_close`.
14. **My own regression, caught by `sim_setup_during`** (552f4e75): after fix 6 the Solve
   dialog's cancel of a job whose body was deleted became "failed" with a "simulation failed"
   line in the Report view; the engine now leaves a job someone cancelled alone.

## The Fusion parity list

`tools/sciforge/data/fusion-menus.txt` has two new areas, SIMULATION SETUP
`[in=tab:sim_setup]` and SIMULATION RESULTS `[in=tab:sim_results]`, with Fusion's command names
from the research file (3.1, 5.13, 9.2, 9.3); INSPECT and SELECT are as in DESIGN (listed once,
under SOLID) and the RESULTS tab's MANAGE repeats SETUP's. Manual Contacts is
`[out=...]` (contact types other than bonded need nonlinear analysis: outline 7.18 and 8).
`parity.py`: SETUP 16 / 24 present (greyed: Simplify, Linear / Angular Global Load, Point Mass
Auto / Manual, Bolt / Rigid Body Connector), RESULTS 20 / 21 (no Wireframe: Undeformed Model
draws a see-through ghost instead); all of Fusion 515 / 677 (76.1 %). The greyed and missing
ones are row G-93 of `remaining-gaps.md` (test_parity's work-list check). `make_ai_docs.py`
run after each doc change.

## What else I tried as a beginner would (scenarios `sim_qa_*.py`)

- `sim_qa_beginner`: a study with no load (Pre-check yellow, "Nothing pushes"; solved anyway:
  zeros, safety factor 15 everywhere, the legend without "nan", Results Details, Adjusted and
  Animate on a part that does not move, a probe reads 0); a force added with clicks, solved
  (0.2 mm = F L^3 / 3 E I); Clone Study from the right-click menu, the clone's force edited to
  200 N from the browser, "Solve 2 Studies": the clone moves exactly twice as far, the first
  study unchanged and up to date.
- `sim_qa_picks`: Fixed on two edges clicked with the mouse, a Force on a corner clicked:
  green, solved, the reaction is the 100 N.
- `sim_qa_close`: a design closed with Structural Loads open (no undo step left, the other
  design's New Study its own undo step, its solve ends).
- `sim_qa_menus`: the right-click ring on RESULTS and SETUP.
- `sim_qa_speed`: a 306-face plate (200 x 200 x 6, 100 chamfered holes), every step real input,
  on this machine (4 CPUs shared with other agents, one CalculiX thread):

  | Action | Time |
  |---|---|
  | Workspace > Simulation / Create Study (with the Pre-check light) | 0.41 s / 0.12 s |
  | Structural Constraints / Structural Loads open | 0.05 s / 0.07 s |
  | A pick and its preview: the side face / the top face with 100 holes in it | 0.79 s / 1.07 s |
  | OK (Fixed / Pressure) | 0.11 s / 0.25 s |
  | Solve: 62 677 nodes, 33 042 elements | 28.4 s |
  | The window's longest pause while it solved (a 50 ms timer's gaps) | 3.1 s |
  | RESULTS: Stress drawn / a probe click / Show Mesh on, off | 0.46 / 0.92 / 0.84, 0.87 s |
  | Slice Plane opens and cuts / Remove Slice | 0.65 / 0.46 s |
  | Animate starts / its longest pause while playing / stops | 0.04 / 0.31 / 0.40 s |
  | Report saved (pictures included) | 2.48 s |

  The window stays usable; the one 3.1 s pause is a main-thread step of the solve (writing
  or reading the solver's files for 62 677 nodes), as sim-core measured (~3-4 s on big parts).
- Already covered by the builders' scenarios, read and run: Esc / Cancel in every dialog,
  undo / redo of setup changes (never a solve), a second design, components, inch designs, a
  body deleted (before and during a solve), DOF View, Repair, leaving and coming back.

## Suites

- Every simulation scenario, the journeys and my QA scenarios, plus `ribbon_sweep` and
  `marking_menu_command` (ribbon_config and the marking menu are shared), one run
  (`.sciforge-cache/full_gui`): journey_sim_bracket 93, journey_sim_bracket_edit 108,
  marking_menu_command 31, ribbon_sweep 222, sim_core_job 29, sim_qa_beginner 37, sim_qa_close
  17, sim_qa_engine 15, sim_qa_menus 34, sim_qa_picks 15, sim_qa_speed 31, sim_setup_bracket 80,
  sim_setup_browser 67, sim_setup_canvas 29, sim_setup_components 42, sim_setup_documents 71,
  sim_setup_glyphs 20, sim_setup_kinds 72, sim_setup_lost 60, sim_setup_mesh 42, sim_setup_more
  63, sim_setup_odd 82, sim_setup_two 52, sim_setup_units 39, sim_setup_workspace 70,
  simres_adaptive 37, simres_cantilever 80, simres_compare 76, simres_deformation 70,
  simres_inspect 94, simres_linear 31, simres_out_of_date 32, simres_probes_slice 84,
  simres_reopen 21, simres_report 61, simres_workspace 65: PASS. Two failed and were fixed:
  `sim_setup_dialogs` expected FreeCAD's "Aluminum" in Study Materials (now SciForge's
  "Aluminium": the scenario updated, 0f04e5bc) and `sim_setup_during` (the Solve dialog cancels
  a job whose body was deleted, then my engine check also failed it and logged "simulation
  failed": the engine now leaves a job someone cancelled alone, 552f4e75); both re-run below.
- Hole scenarios (`hole_common` is shared): hole 99, hole_edges 36, hole_qa 494, hole_qa_more
  363, hole_qa_part 257, hole_qa_thread 379, hole_sketch 49, hole_tapped 67, hole_thread 57,
  hole_thread_inside 36, and inspect_qa 557 (Measure uses `abandon`): PASS.
- Unit (`--only unit`): 2726 tests, 2 failed: the AI docs mirror of the simulation parity doc
  was out of date (regenerated, c1afc04b); `test_ai_docs_contract` and `test_parity` OK since.
- `--only sim`: the builder's benchmarks 138 checks and the QA's hand calculations and engine
  checks 230 (205 before + my 25: free motions, bearing default, a body deleted mid-solve, the
  material read, a mesh-only design), 0 failed.
- Re-runs after the late fixes (the fixed / changed ones and what they touch):
  journey_sim_bracket 113, journey_sim_bracket_edit 112, sim_qa_beginner 46, sim_qa_speed 32, sim_setup_dialogs 92, sim_setup_during 30, sim_qa_results_close 26,
  sim_setup_odd 82, simres_adaptive 37, simres_cantilever 80, simres_compare 76,
  simres_deformation 70, simres_inspect 94, simres_linear 31, simres_out_of_date 32,
  simres_probes_slice 84, simres_reopen 21, simres_report 61, simres_workspace 65; for
  `bodies.py`: bodies_look 58, bodies_qa 317, inspect_qa4 330, misc_materials 51: PASS.
- Unit (`--only unit`) again at the end: 2726 tests OK (9 skipped).
- A test-harness trap my own scenarios fell into: `harness.task_button("Close")` clicks the
  first visible "Close" in the main window, which is the solve's progress window (Job Status)
  while it shows, not the Surface Probes dialog. The journey's new checks ("Surface Probes
  closed") caught it; the journey and my scenarios now close the progress window (Esc) after
  each solve, as a person does.

## Not fixed (with the evidence)

- **The window's longest pause while a big part solves is about 3 s** (2.98 / 3.10 s on the
  62 677-node plate): one main-thread turn of writing the solver's input or reading its results
  with FreeCAD's FEM tools; sim-core measured the same (~3-4 s on 131 000 nodes). Splitting it
  further needs FreeCAD's writer and reader in pieces.
- **FreeCAD's PLA card gives an ultimate tensile strength (26.4 MPa) below its yield strength
  (35.9 MPa)**: with the Ultimate basis PLA's safety factor is lower than with Yield. FreeCAD's
  data, not SciForge's; Study Materials shows both values.
- **"50 N down on the top of the arm"** (the brief) only squeezes an upright arm; the journey
  loads it across (the shelf-bracket case M c / I is for) and also, in a cloned study, straight
  down: 0.231 MPa in the arm (F / A = 0.25), and the base plate at the bolts about as stressed
  as across (17.09 vs 18.08 MPa), so a thicker arm helps the sideways load only.
- The RESULTS marking menu's contents are SciForge's choice (sim-results' note; Fusion's own
  results ring was not documented in the research).

## For Luca

I built an L-bracket from nothing the way you would (sketch, extrude, two bolt holes, a fillet,
PLA), studied it in SIMULATION and checked every number against hand calculations: the arm's
tip moves 2.09 mm (I worked out 2.09), the stress up the arm matches the beam formula within 5 %,
the most stressed spot is the edge of a bolt hole (18 MPa, safety factor 2.0 in PLA), and making
the arm 7 mm instead of 5 mm from the timeline halves the stress in the arm, as the formula says.
Saving, closing and opening again keeps the studies and results.

What I fixed: SciForge could crash if you closed a design while Surface Probes was open with
the mouse over the result (fixed); the design looked "unsaved" right after saving once you had
used SIMULATION (fixed); right-clicking on the results now offers the result tools; the report
and Study Materials say "PLA" and "2 faces" instead of FreeCAD's "PLA-Generic" and "Face10";
reaction forces no longer show tiny numbers like 1.3e-7; an imported STL tells you to use
MESH > Convert Mesh first; greyed commands say what to use instead; and a few engine details
(bearing loads in holes, a body deleted during a solve, DOF View's words).


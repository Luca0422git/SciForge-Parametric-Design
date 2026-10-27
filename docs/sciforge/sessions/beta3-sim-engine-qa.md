# Session log: beta 3, QA of the Static Stress engine (sim-engine-qa)

Branch `sf/sim-engine-qa` (from builder sim-core's finished `sf/sim-core`), 2026-10-26/27.
Rules: `docs/sciforge/dev/briefs/beta3-qa.md`, `beta3-common.md`; the engine's brief
`beta3-sim-core.md`, its report and session log; research `fusion-simulation.md` (3, 5.4, 8,
9); parity `docs/sciforge/parity/simulation.md` (Engine, Benchmarks).

Scope: the engine only (`sciforge/simulation.py`, `simulation_core.py`, the AI tools
`ai/catalog/simulate_tools.py`, `ai/actions/simulate_actions.py`, their tests). The dialogs and
the results display (sim-ui, sim-results) were left alone; the engine's API is unchanged
(added: `design_bodies`, `map_pick_groups`, and in `simulation_core`: `ultimate_stresses`,
`inp_loads_at`, `node_forces_from_dat`, `split_reactions`, `tet_volume_shares`,
`tet_face_shares`, `thin_wall_note`, `FORCE_ONE_KIND`, `FORCE_NORMAL_NEEDS_FACES`,
`NORMAL_NEEDS_FLAT`).

## What I checked, and how

My own hand-calculated cases (not the builder's), every formula with its source next to it,
in `SciForgeTests/headless/sim_accuracy_qa.py`, run by `run_tests.sh --only sim` (and `base`)
after the builder's `sim_benchmarks.py`. Each case runs at the study's default mesh and at a
finer one, and a "converges" row checks that the finer mesh is nearer the hand calculation
wherever the default is off by more than 1 %. Four cases go through the AI tools the way an
AI app calls them (answers only). Engine checks look for numbers that are wrong without a
word. GUI scenario `sim_qa_engine.py` for what only shows with the window up.

## Bugs found and fixed (each its own commit, each with a test that fails on the old code)

1. **The ultimate-basis safety factor read 15 for a crushed part** (cb0223df). It divided the
   ultimate strength by the 1st principal stress only, which is 0 in compression: a steel bar
   at 100 MPa of compression showed 15 ("very strong", the AI said it meets the target); past
   its strength still 15. Now max(1st, -3rd) (Rankine, on the safe side for brittle
   materials; the same in tension). Parity E3 says why it differs from the help's wording.
   Tests: unit `test_ultimate_basis_in_compression`, QA case `safety_basis` (3.45).
2. **A force's total was wrong for some picks** (324a08fb): shared over a face and a corner,
   both got the whole force (twice the total); shared over faces and edges, the edges were
   left out; along the normal, edges and corners picked with faces were left out; Force (and
   Moment) Per Entity gave the whole value to every face of the simulation model, and the
   model splits a picked face where a glued body touches it (a plate under a glued block:
   1930 N for 1000 N). Now a shared force needs one kind of pick, normal needs faces (a
   sentence in the dialog / AI check, `core.check`; an old item is refused at the solve) and
   Per Entity goes by the person's picks (`map_pick_groups`). Tests: unit `test_force_picks`,
   QA engine check "a force's picks".
3. **Reactions did not add up to the loads** (73ccb1cd). CalculiX's RF is the whole external
   force at a node (reaction plus the loads acting right there): a held face's nodes carry a
   share of the weight of the elements touching them and of a pressure on a face meeting the
   held one, so every such reaction was short: a bracket held at its 6 mm wall plate 7.4 %
   below its weight, a clamped plate 9 % below p A, 1 MPa on a cantilever 991.7 N for 1000 N,
   the builder's hanging bar 0.8 %. And a node two constraints hold had its whole force in
   both totals (a quarter ring on sliding planes: 56 N sideways where statics says 0). Now
   every held node's force is printed, the loads acting at it are worked out from the solver
   input the way CalculiX applies them (consistent nodal loads of C3D4 / C3D10: *CLOAD, face
   pressures, gravity with each element's density) and taken off, and each node's remainder
   is shared among the constraints holding it along the directions each holds. Exact now
   (weight 2.226 N = rho V g; quarter ring (-2000.1, -0.01, 0)). Tests: unit
   `HeldNodeLoads`, QA `gravity_*`, `clamped_plate`, `ai_pressure_gravity`, engine checks
   "reactions add up to the loads", "reactions on sliding planes".
4. **Hiding a body made the results out of date** (e3476907; sim-results' report): a study
   with no bodies chosen took the bodies whose eye was on when it solved, so an eye turned
   off after a solve (the RESULTS tab says to, to look inside) changed the fingerprint, and
   the next solve left the body out (or found none). Now such a study takes the design's
   bodies, shown or hidden, but not the tools a Combine used up nor bodies the history marker
   has not made yet (`design_bodies`, as the export counts them; Fusion's simulation model is
   the design's bodies). A hidden body held by nothing is named by the pre-check; Study
   Materials / the browser leave a body out by name as before. Tests: QA engine check "the
   bodies of a study of the whole design", GUI `sim_qa_engine` C and D.
5. **A study changed after a solve stayed "touched"** (9a0da460; sim-results' report): any
   engine write to a study or an item (a setting such as Keep results in the file, a study
   material, an item) left FreeCAD's recompute mark, which was saved with the design and came
   back on reopening. A solve itself already left nothing touched (checked headless and with
   the window up, also after the window drew). Studies and items have nothing to compute, so
   the engine now clears the mark after its own writes (`_clean`); the design is still marked
   modified and the results still go out of date. Tests: QA engine check "nothing asks for a
   recompute after a solve", GUI `sim_qa_engine` B.
6. **A thin wall at the default mesh was wrong without a word** (6dc9cf19): a clamped 2.5 mm
   plate bent 10.5 % too little, a 3 mm tube's twist stress read 6.3 % low, with elements 5.1
   and 3.7 times the wall and no note (the stretched-elements note needs 3 x the aspect limit).
   Now each body's wall thickness (2 V / A) is measured against the median edge of its
   elements; above 3 times a note names the body, its wall and element sizes, and says to
   make the elements about the wall's size and compare (calibrated: 4.5 % off at 3.4 times,
   2.4 % at 2.2; a solid cantilever gets no note). Tests: unit `test_thin_wall_note`, QA rows
   of `clamped_plate` / `tube_torsion` at the default mesh pass only "warned", engine check "a
   thin wall at the default mesh is not silently wrong".
7. **A Force or Moment "along the normal" of a curved face pushed in an arbitrary direction**:
   it took the normal at the middle of the face's parameters (a shaft's round side pushed
   sideways). Refused now with a sentence pointing to a vector, a Pressure or a Bearing Load.
   Tests: unit `test_normal_needs_flat_faces`, QA engine check "along the normal of a curved
   face".

8. **Results stayed "in date" after a change that keeps a body's size** (8763a5dd,
   7592e764): the fingerprint took only volume, area, face count and box, so a hole moved
   along a plate, or a square bar turned a quarter about its axis (its loaded top face then a
   side), left the old results in date. It now also takes each body's centre of mass and its
   place (and its component's); stable across save and reopen and eye changes; read once per
   solid (0.06 s for a 126-face plate). Test: QA engine check "out of date after a change that
   keeps the size" (it also caught my own first version, which read the centre of mass of the
   body's compound and so fingerprinted nothing).

9. **Bodies touching only along an edge or at a corner counted as glued, and the pre-check
   was green** (c26ba18c): the model glues them only there, like a hinge; the solve then
   failed with "not held enough", naming neither body nor the reason. The pre-check now warns
   with both names and how they touch (`slight_contacts`; from the section of the two shapes,
   confirmed on their faces, so a pin in its hole or a cube on a face is not taken for one).
   Test: QA engine check "bodies that touch only along an edge or at a corner".

## Looked at and found right

- Equivalent strain: 3 G x strain = von Mises at every node of a twisted tube (CalculiX's
  tensor shear strains read right). Gravity's weight equals Inspect's mass x 9.80665 (a body
  on FreeCAD's Default material counts as Steel in both).
- Simply supported beam (line load on an edge; uniform pressure), symmetry half against the
  full beam, cantilever on an edge / corners, stepped steel + aluminium bar (materials not
  swapped, also three glued blocks listed in another order), clamped plate (fine mesh 0.9 %),
  tube torsion through a Moment in N mm (fine mesh 0.004 %), gravity (down and sideways,
  two densities), shaft with a bearing load, inch-sized part, 1000 mm and 1 mm parts, every
  load's direction (pressure into the face, negative pulls, Flip, normal force into the face,
  moment by the right-hand rule, gravity), a component moved and turned (same numbers,
  reaction turned with it), picks through PartDesign edits (longer, a slot through the
  middle, back: the force stays on the end face), results kept in / dropped from the file,
  out of date after a change (also through the AI's study_results).
- A Gui document observer (`Gui.addDocumentObserver` with slotCreatedObject /
  slotChangedObject) that reads the view providers it is told about did not stop a solve
  (GUI `sim_qa_engine` E). sim-results' "Cannot create object 'SimMesh': (Cannot add static
  property)" did not reproduce with such an observer; their observer is not in their branch
  any more. `sciforge/doc_epoch.py` explains the trap: FreeCAD calls a Gui observer's
  slotCreatedObject with a view provider still being built, and asking for its Python object
  then fixes its type; SciForge's own Gui observers leave those two slots out. Integration:
  keep it that way (App observers are safe).

## Not fixed (for sim-ui, or larger)

- sim-ui's Solve dialog (`simulation_solve_dialog._keep_out_of_date`) writes the fingerprint
  it took before the job started into the summary when the engine's (taken after it found
  lost picks again, `repair_picks`) differs: after a solve that repaired picks, the results
  show out of date at once (and the study is touched). The engine already takes the
  fingerprint when the solve starts; the dialog's copy can go (sim-core said so too).
- A pressure on a face partly covered by a glued body acts only on the uncovered part (the
  covered part is inside the model, between two solids); a shared force on the same face is
  spread over all of it. Fusion meshes the bodies apart, so its pressure covers the whole
  face. See the table for the measured numbers.

## Log

- 22:24 read the briefs, report, session log, parity, research, all of the engine.
- 22:30-22:55 wrote 16 cases + AI cases + engine checks; first run 167 checks, 26 failed
  (some my own model mistakes: a half model's end line held along X, the moved part's
  expected reaction, a save that reopened the same document).
- 22:55-23:10 fixes 1-3; the reactions: first a correction per set, then node by node once
  the quarter ring showed shared nodes counted twice (CalculiX's RF at a free degree of
  freedom is the load there, at a held one the reaction plus the load).
- 23:05 the orchestrator's note (sim-results' engine issues): fixes 4 and 5, GUI scenario.
- 23:15 fix 6 (calibrated on the plate at 10 / 7.5 / 6 / 5 mm and the tube at 10 / 8 / 6 mm).
- 23:20 fix 7. 23:26 the container restarted; runs repeated.
- 23:40 sim-results' branch (with sim-ui's work) exported to a scratch folder with this
  engine on top: sim_setup_bracket 80, sim_setup_components 43, sim_setup_dialogs 85,
  sim_setup_kinds 70, sim_setup_more 63, sim_setup_two 40, simres_cantilever 80,
  simres_inspect 94, simres_out_of_date 32, simres_reopen 21 checks: all pass.
- 23:45 a pressure on a face partly covered by a glued block: 9600 N for 1 MPa on 10 000 mm2
  (the covered 400 mm2 is inside the model); left as is, Known gaps.
- 23:46-23:55 fix 8; a fillet on the loaded end in the picks check; timings: the thin-wall
  note 0.18 s on a 204 000-node mesh, the reactions' input reading 2.7 s for a 900 000-node
  input (background thread).
- 23:55 `--only sim` (benchmarks 138, QA 191), GUI sim_core_job 29 / sim_qa_engine 15,
  `--only headless` (306 calls, docs 152 items / 1002 calls, agent 81), unit 2513 (one stale
  generated page, regenerated): all pass.
- 23:58-00:01 fix 9 (edge / corner contacts); strain and mass cross-checks.
- 00:02 sim-results' export again with the final engine: sim_setup_components 43,
  sim_setup_documents 71, sim_setup_lost 48, sim_setup_mesh 42, sim_setup_two 40,
  simres_adaptive 37, simres_compare 76, simres_out_of_date 32, simres_reopen 21,
  simres_workspace 65: all pass.
- 00:05 a 126-face plate with 120 holes at 4 %: 198 398 nodes, 175 s (CalculiX 146 s, one
  thread); the reaction 609.968 N for 609.926 N of pressure and weight (0.007 %); results
  read (with the reactions) 3.6 s in the background.

## Final results (00:15)

- `run_tests.sh --only sim`: builder's benchmarks 138 checks, QA's `sim_accuracy_qa` 197
  checks (154 accuracy rows, 43 engine checks): 0 failed; with the pinned link case added
  after it (00:20), the QA suite alone: 205 checks, 0 failed. The QA table is in the parity doc,
  Benchmarks, "QA's own hand calculations".
- `--only unit`: 2513 tests OK (9 skipped). `--only headless`: 306 calls, docs 152 items /
  1002 calls, agent 81 checks: pass.
- GUI: sim_core_job 29, sim_qa_engine 15 checks: pass; sim-ui / sim-results scenarios on this
  engine (export): 16 scenarios, all pass (see the log above).

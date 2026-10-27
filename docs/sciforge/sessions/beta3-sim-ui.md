# Session log: beta 3, sim-ui (the SIMULATION workspace's SETUP side), branch `sf/sim-ui`

Builder sim-ui of beta 3 (2026-10-26/27). Brief: `docs/sciforge/dev/briefs/beta3-sim-ui.md`.
Spec: `docs/sciforge/parity/simulation.md` section "Setup" (behaviour table S1-S28 with sources,
scenarios, Known gaps). Engine: sim-core's `simulation.py` / `simulation_core.py`, merged into
this branch four times (`sf/sim-core` at 117f9162, 18fdf61c, fe3bf6a5 and 42dd30a6), then
`sf/sim-engine-qa` at 45c340d5 (sim-core's final engine with the engine QA's fixes).

## What was built

- **The workspace switch** (`simulation_ui.py`): Workspace > Simulation / Design per design
  (each open design remembers its workspace; closing one forgets it; a reopened design opens in
  DESIGN), the timeline hidden in SIMULATION, the study tree in the browser, the glyphs, the
  Pre-check traffic light on the ribbon; entering finishes an open command or sketch and clears
  the selection; from a drawing's tab the design's 3D view comes forward first; without a study
  the New Study dialog opens by itself. Leaving hides the SIMULATION displays (glyphs, the mesh
  Generate Mesh showed, the results).
- **Dialogs** (`simulation_dialogs.py`): New Study (11 study types as tiles, Static Stress
  available, the gear's settings before the study exists), Study Settings (General: Remove
  rigid body modes, keep results; Mesh: % or absolute size, per part, order, curved, turn
  angle, adjacent / aspect ratio, minimum; Adaptive: None / Low / Medium / High / Custom with
  the engine's numbers; Contacts: Bonded, tolerance), Study Materials (In Study, model
  material, study material, properties with "filled in by SciForge" notes, safety basis),
  gravity on / off, Automatic Contacts, Contact Manager, Load Case Attributes, Pre-check list,
  DOF View.
- **Pick dialogs** (`simulation_panels.py`, on `pickpanel.PickPanel`): Structural Constraints,
  Structural Loads and Local Mesh Control (one item dialog, category constraint / load / mesh),
  Edit Gravity. Every kind's options; values with units; the live glyph preview; Fusion's types
  SciForge does not build listed greyed with a sentence. Force and Moment have Fusion's three
  Direction Types: Normal, **Angle** (About X, Y, Z in degrees, turned from the first picked
  face's normal: `simulation_setup_core.turned`; the engine gets the vector, the turns are kept
  beside it in the item's `SimDirectionAngles` with that vector, so Edit, Load Case Attributes
  and Clone Study show Angle again, and an item whose vector changed another way shows Vector)
  and Vector.
- **Solve** (`simulation_solve_dialog.py`): the Solve dialog, the progress window (stages,
  elapsed time, Cancel; only Close once it ended), studies one after another, the hand-over to
  RESULTS, Generate Mesh with the engine's mesh-only job, Show Mesh, the "not held enough" guard.
  A study that cannot solve has Fusion's **Repair** button: it closes the dialog and goes to the
  first thing to fix, with a sentence (`simulation_setup_core.repair_step`: a lost item's Edit
  dialog, Structural Constraints, DOF View, Study Materials, else the Pre-check list: a study
  whose body was deleted has nothing to pick); a red Pre-check list has the same Repair.
  A design closed (or a study deleted) while it solves: the solver is stopped and the progress
  window says the study is gone (`simulation_solve_dialog._gone`).
- **Glyphs** (`simulation_glyphs.py`), **browser** (`simulation_browser.py` + hooks in
  `browser_ui.py`), **ribbon** (the SETUP entries in `ribbon_config.py`, DISPLAY > Show Mesh,
  a big button in every group; SOLVE > Job Status opens the progress window any time), **icons**
  (`tools/sciforge/icons_simulation.py`, 44 icons, also for the greyed commands; written one by
  one so the other builders' icons are untouched), unit tests (`test_simulation_setup_core.py`,
  37), sixteen GUI scenarios `sim_setup_*.py`.
- **The design's units** (Fusion's Simulation follows the document's units, research 6): the
  value fields, the browser's texts, Load Case Attributes, Study Materials' properties and the
  mesh / contact lengths show N, MPa, N mm, mm in a metric design and lbf, psi, lbf in, in in an
  inch design (`simulation_setup_core.unit_set`, `format_quantity(..., shown=)`); a bare number
  is in the unit shown, a typed unit wins; the engine keeps N, MPa, mm. A field (or spin box)
  left as it was shown gives back its exact value, so Edit + OK in inches changes nothing.
- **DOF View** is a toggle (Fusion's display): arrows over the model for each way a piece can
  still move (three slides and three turns when nothing holds it; the turn about a held edge
  for a model held by one edge, from the engine's not-held analysis), the bodies selected and
  named; the arrows follow the setup until it is switched off. **Job Status** also lists this
  session's earlier solves and meshes (a solved one's row shows its results on a double-click,
  its design brought to the front in SIMULATION: `simulation_ui.open_results`; the rows name
  each study from its own design, whichever is in front). **OK right after a click** keeps
  that pick (pickpanel handles a click 30 ms later; my dialogs take the queued click first: a
  busy machine once lost it in `sim_setup_dialogs`).
- **The 3D view in SIMULATION**: the right-click marking menu offers the setup's commands
  (`ribbon_config.SIM_MARKING_MENU` / `SIM_MARKING_LIST`, chosen by a hook in
  `marking_menu._open_for_state`), Repeat only repeats a setup command; the design's keys are
  off while SIMULATION shows (`simulation_ui.DESIGN_KEYS`: a face clicked in the view and Delete
  made a Delete Face step in the design; E opened Extrude).
- **Exercising every option end to end, and odd things a person may do** (scenarios
  `sim_setup_more`, `_lost`, `_two`, `_mesh`, `_odd`, `_during`, throwaway explorations) found,
  all fixed:
  - a Bearing Load's default direction ran along a hole drilled along Z (no arrow, a failed
    solve): now turned across the hole;
  - editing a load whose face a design change removed kept the gone pick: now left out with a
    sentence (the faces the engine finds again by shape come under their new names);
  - unticking "Keep the results in the design file" made up-to-date results look out of date
    (the engine's fingerprint counted it: fixed by sim-core) and the Results row then said
    they were kept;
  - with another design in front, Job Status named a study by its internal name and its
    double-click said the results were gone;
  - a design closed during its solve left the progress window saying "Solving..."; a body
    deleted while its study solved made the engine fail with "Cannot access attribute 'Label'
    of deleted object" (the UI now stops the job first, with a sentence naming the body); a
    cancelled solve's progress still showed its stage "running";
  - a new load dialog opened after a click on another load's row started on that load's face
    (the rows light them up: `simulation_browser.only_highlight` leaves out what the selected
    rows lit up);
  - a deleted study whose mesh showed left Show Mesh ticked (and Undo drew the mesh again);
  - a design closed while a SETUP dialog was open left the dialog's undo step open in FreeCAD
    (its name is application-wide): the next design's changes went into it and every solve
    there waited forever for "the open command". Now `simulation_ui._close_leftover_step` runs
    after a design closes, `_finish_sim_dialog` lets go of a closed design's Settings /
    Materials dialog without touching it, and a solve stops waiting for an undo step open with
    no dialog after 2 s;
  - two rows picked with Ctrl and Delete deleted only the last one: the browser's view-to-rows
    selection sync let go of a load's row (it selects faces, not an object); now the rows stay
    picked while the view shows just what they lit up (`simulation_browser.keep_selected`, a
    hook in `browser_ui._sync_selection`);
  - the Solve dialog, Pre-check list, Load Case Attributes and Contact Manager stayed open
    after their design closed (a click in them worked on a deleted study): they now close with
    it (`simulation_dialogs.close_for_closed_designs`); New Study reopens for the design in
    front;
  - DOF View on a study without a body said "every body is held", Generate Mesh failed with
    the pre-check's sentences: both now say there is no solid body.
- **A look at every dialog on screen**: a throwaway scenario took screenshots of each SETUP
  dialog under xvfb (`h.shot` captures the widgets and FreeCAD's 3D view). Fixed from them: the
  Ux / Uy / Uz and Flip Direction buttons looked the same on and off, Study Settings pushed the
  task panel past the window's edge (tab names now scroll, long labels put their field below),
  an unticked study in the Solve dialog showed no box, a finished progress window kept Cancel,
  the notes' grey was unreadable in the light look. The later additions (Repair in the Solve
  dialog and the Pre-check list, the Angle fields, Job Status before any solve) were looked at
  in the dark and the light looks: Job Status before any solve is now as small as its
  sentence, and Study Materials' table header has no blank end.

## Scenarios (last runs)

Final batch on the merged engine (`sf/sim-engine-qa` merged), 00:40-01:01 UTC, with
`OMP_NUM_THREADS=1`, one FreeCAD at a time:

| Scenario | Checks | Result |
|---|---|---|
| `sim_setup_bracket` | 80 | PASS |
| `sim_setup_browser` | 67 | PASS |
| `sim_setup_canvas` | 29 | PASS |
| `sim_setup_components` | 42 | PASS |
| `sim_setup_dialogs` | 92 | PASS |
| `sim_setup_documents` | 71 | PASS |
| `sim_setup_during` | 30 | PASS |
| `sim_setup_glyphs` | 20 | PASS |
| `sim_setup_kinds` | 72 | PASS |
| `sim_setup_lost` | 60 | PASS |
| `sim_setup_mesh` | 42 | PASS |
| `sim_setup_more` | 63 | PASS |
| `sim_setup_odd` | 82 | PASS |
| `sim_setup_two` | 52 | PASS |
| `sim_setup_units` | 39 | PASS |
| `sim_setup_workspace` | 70 | PASS |

The engine's own `sim_core_job` (29) and `sim_qa_engine` (15) pass on this branch too. Shared
files touched (`browser_ui.py`, `ribbon_config.py`, `marking_menu.py`): `timeline_browser` (92),
`drawing_new` (63), `browser_opacity_hover` (46), `ribbon_sweep` (221) and `hole_qa_more` (363,
the marking menu) pass. `--only base` (01:01-01:10): unit tests 2550 OK (9 skipped), golden
models 614 + 2 xfail, headless AI 306 calls 0 failed, docs examples 152 items 0 failed, agent
end to end 81 checks, simulation benchmarks 138 checks, the engine QA's accuracy cases 205
checks, GUI smoke / journey / restart: all passed. `sim_setup_browser` part J was also run
with the dialog's old fingerprint copy put back for a moment: it fails there ("up to date at
once"), so it guards the fix.

## Contract with sim-results (agreed by reading its branch)

- sim-ui calls `simulation_results_ui.show(study)` when a solve ends (else selects the RESULTS
  tab itself), and `simulation_results_ui.hide()` when the workspace is left. It calls show()
  only when the study's design is in front in SIMULATION: show() enters the workspace when it
  is not on, which took a person who went on in DESIGN (a sketch open) out of their work when a
  solve ended; now they stay and are told where the results are (`simulation_ui.show_results`).
- A person's own request to see results (a Job Status row double-clicked) brings the study's
  design to the front in SIMULATION first (`simulation_ui.open_results`), then the same
  `show_results(study)`.
- sim-results calls `simulation_ui.active()`, `active_study(doc)`, `set_active_study(study)`,
  `enter_workspace("sim_results")`, and `simulation_glyphs.set_visible(on)` / `visible()`.
- A study without results made active while RESULTS is in front shows SETUP
  (`simulation_ui._setup_tab_without_results`).

## For sim-core (engine issues met while building the UI)

1. Fixed by sim-core: `simulation._link_list` dropped a whole-body pick (`(body, [])` is stored
   as nothing in a PropertyLinkSubListGlobal; it now writes `(body, [""])`). The UI's
   `simulation_panels._keep_whole_bodies` stays as a harmless check.
2. Fixed by sim-core (merged at 42dd30a6): the result summary keyed bodies by **label**: two
   components' first bodies are both "Body1" in Fusion's numbering and shared one entry; the
   key is now unique (`simulation.body_key`). The UI does not read per-body entries.
3. Fixed by sim-core: a model held by one straight edge solved "done" with 1.4e10 mm of
   displacement (CalculiX found a mechanism); the pre-check and the job now say "not held
   enough". The UI still refuses to hand over results that moved more than half the model's
   size (`simulation_solve_dialog.loose_result`).
4. Fixed by sim-core (merged at 42dd30a6): `_finish` took `signature(study)` when the solve
   ended, so a design change made while it ran looked up to date; the engine now keeps the
   fingerprint from the start (`Job._fingerprints`). The UI's own copy
   (`simulation_solve_dialog._keep_out_of_date`) is gone: the engine takes its fingerprint
   after it finds lost picks again (`repair_picks`), and the copy taken before made such
   results look out of date at once (found by the engine QA; `sim_setup_browser` part J: the
   arm deleted and made again, solved, up to date).
5. Open (cosmetic): `simulation_core.describe_free_mode` prints the rounding noise of the axis
   point ("turn about an axis along X through (5, 8.882e-16, 8.882e-16)"), which reaches the
   pre-check's sentences. DOF View cleans it (`simulation_dialogs.describe_motion`); the engine
   could round values below 1e-9 of the model's size to 0.
6. DOF View uses the engine's `_held_rows` and `_pieces` (private) with `free_modes`; a public
   `free_motions(study)` in the engine would be safer (DOF View falls back to the bodies held
   by nothing if they change).
7. Open: the Bearing Load's default direction (-Z) runs along a hole drilled along Z: no
   side takes the load and the solve fails with "Flip the direction", which does not help.
   The UI turns a default that runs along the picked hole's axis across it and refuses a
   direction along the axis (`simulation_panels.ItemPanel._bearing_across`); the pre-check
   could say it too.
8. Fixed by sim-core (merged at 42dd30a6): `signature()` counted the `keep_results` setting,
   so unticking "Keep the results in the design file" made up-to-date results look out of
   date (found by `sim_setup_documents` part H). Also: with it off, the saved design keeps an
   emptied result object, so the browser's Results row asks `results_dropped(study)` rather
   than whether a result object exists.
9. Open: a body of the study deleted while the study solves: `Job.poll()` raised "Cannot
   access attribute 'Label' of deleted object" (a WARNING, and "The solve failed: ..." as the
   message). The UI now stops the job first (`simulation_solve_dialog._poll` checks the
   study's bodies each turn); the engine could check them too (scripts and the AI's solve).

## FreeCAD / Qt facts and traps

- `doc.openTransaction(name)` makes `name` FreeCAD's application-wide active transaction. A
  dialog abandoned because its design was closed (`hole_common.abandon`, shared code) leaves it
  active: the next change in any design opens an undo step of that name. SIMULATION closes it
  after a design closes; `hole_common.abandon` could call `App.closeActiveTransaction(False)`
  for every SciForge dialog (not changed here: not sim-ui's file).
- A PropertyLinkSubListGlobal drops an entry with an empty sub-list; `(obj, "")` keeps it.
- Without a window manager (xvfb), closing a top-level dialog leaves no active window: the main
  window's QShortcuts (Esc, Enter) stop firing. SciForge's dialogs now give the main window its
  activation back when they hide (`simulation_dialogs.FocusBack`).
- Under xvfb, once any task dialog was shown and closed in one design, a synthetic mouse click
  on the workspace menu's entry in another design is dropped by QMenu (reproduced with a bare
  FreeCAD task dialog; the keyboard works). The scenario helper falls back to Enter on the entry.
- Creating a design and clicking the workspace menu in the same scenario step races the
  document switch; a person waits, the scenarios use separate steps.
- FreeCAD picks an edge within a few pixels: a click aimed at a face is aimed far from its
  edges (`simsetup_steps._face_points`).
- The harness counts any Report-view line with "failed" as an error: the engine logs
  "simulation failed: ..." when a solve fails, so a scenario that makes a solve fail on purpose
  must not (the UI refuses red pre-checks before starting a job).
- The theme draws a checkable QPushButton alike on and off, and an item view's tick box
  (`QTableView::indicator`) unstyled: invisible when unticked on the dark panels. Give them a
  style sheet (written in the dark colours: the theme's hook swaps them for the light look).
- A QTabWidget asks for the width of all its tab names, and a QFormLayout for label + field:
  in a task panel that pushes the panel past the window. `setUsesScrollButtons(True)` and
  `QFormLayout.WrapLongRows` keep it inside.
- Under xvfb the screen shows FreeCAD's 3D view in screenshots (`QScreen.grabWindow(0)`), and
  `view.saveImage` renders it off screen: both are usable to check what a person would see.

## Gaps

See the parity doc's Known gaps (Simplify, several load cases, per-body safety basis, manual
contacts / connectors / global loads / point mass, Limit Target, the Job Status history of this
session only, the glyph look is SciForge's own; an Angle direction is worked out when OK is
pressed; what Fusion's Repair opens is not known, SciForge's goes to the first thing to fix).

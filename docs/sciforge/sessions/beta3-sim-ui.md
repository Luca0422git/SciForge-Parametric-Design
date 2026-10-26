# Session log: beta 3, sim-ui (the SIMULATION workspace's SETUP side), branch `sf/sim-ui`

Builder sim-ui of beta 3 (2026-10-26/27). Brief: `docs/sciforge/dev/briefs/beta3-sim-ui.md`.
Spec: `docs/sciforge/parity/simulation.md` section "Setup" (behaviour table S1-S25 with sources,
scenarios, Known gaps). Engine: sim-core's `simulation.py` / `simulation_core.py`, merged into
this branch three times (`sf/sim-core` at 117f9162, 18fdf61c and fe3bf6a5).

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
  SciForge does not build listed greyed with a sentence.
- **Solve** (`simulation_solve_dialog.py`): the Solve dialog, the progress window (stages,
  elapsed time, Cancel; only Close once it ended), studies one after another, the hand-over to
  RESULTS, Generate Mesh with the engine's mesh-only job, Show Mesh, the "not held enough" guard.
- **Glyphs** (`simulation_glyphs.py`), **browser** (`simulation_browser.py` + hooks in
  `browser_ui.py`), **ribbon** (the SETUP entries in `ribbon_config.py`, DISPLAY > Show Mesh,
  a big button in every group), **icons** (`tools/sciforge/icons_simulation.py`, 43 icons, also
  for the greyed commands), unit tests (`test_simulation_setup_core.py`, 35), fourteen GUI
  scenarios `sim_setup_*.py`.
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
  session's earlier solves and meshes (a solved one's row shows its results on a double-click). **OK right after a click** keeps that pick (pickpanel
  handles a click 30 ms later; my dialogs take the queued click first: a busy machine once lost
  it in `sim_setup_dialogs`).
- **The 3D view in SIMULATION**: the right-click marking menu offers the setup's commands
  (`ribbon_config.SIM_MARKING_MENU` / `SIM_MARKING_LIST`, chosen by a hook in
  `marking_menu._open_for_state`), Repeat only repeats a setup command; the design's keys are
  off while SIMULATION shows (`simulation_ui.DESIGN_KEYS`: a face clicked in the view and Delete
  made a Delete Face step in the design; E opened Extrude).
- **Exercising every option end to end** found two more: a Bearing Load's default direction
  ran along a hole drilled along Z (no arrow, a failed solve: now turned across the hole), and
  editing a load whose face a design change removed kept the gone pick (now left out with a
  sentence; the faces the engine finds again by shape come under their new names).
- **A look at every dialog on screen**: a throwaway scenario took screenshots of each SETUP
  dialog under xvfb (`h.shot` captures the widgets and FreeCAD's 3D view). Fixed from them: the
  Ux / Uy / Uz and Flip Direction buttons looked the same on and off, Study Settings pushed the
  task panel past the window's edge (tab names now scroll, long labels put their field below),
  an unticked study in the Solve dialog showed no box, a finished progress window kept Cancel,
  the notes' grey was unreadable in the light look.

## Scenarios (last runs)

| Scenario | Checks | Result |
|---|---|---|
| `sim_setup_bracket` | 74 | PASS |
| `sim_setup_dialogs` | 85 | PASS |
| `sim_setup_browser` | 61 | PASS |
| `sim_setup_documents` | 49 | PASS |
| `sim_setup_kinds` | 70 | PASS |
| `sim_setup_workspace` | 54 | PASS |
| `sim_setup_components` | 42 | PASS |
| `sim_setup_glyphs` | 20 | PASS |
| `sim_setup_units` | 39 | PASS |
| `sim_setup_canvas` | 29 | PASS |
| `sim_setup_more` | 39 | PASS |
| `sim_setup_lost` | 20 | PASS |
| `sim_setup_two` | 26 | PASS |
| `sim_setup_mesh` | 34 | PASS |

Shared files touched (`browser_ui.py`, `ribbon_config.py`, `marking_menu.py`): `timeline_browser`,
`drawing_new`, `browser_opacity_hover`, `ribbon_sweep` and `hole_qa_more` (the marking menu) pass; unit tests 2534 OK.

## Contract with sim-results (agreed by reading its branch)

- sim-ui calls `simulation_results_ui.show(study)` when a solve ends (else selects the RESULTS
  tab itself), and `simulation_results_ui.hide()` when the workspace is left. It calls show()
  only when the study's design is in front in SIMULATION: show() enters the workspace when it
  is not on, which took a person who went on in DESIGN (a sketch open) out of their work when a
  solve ended; now they stay and are told where the results are (`simulation_ui.show_results`).
- sim-results calls `simulation_ui.active()`, `active_study(doc)`, `set_active_study(study)`,
  `enter_workspace("sim_results")`, and `simulation_glyphs.set_visible(on)` / `visible()`.
- A study without results made active while RESULTS is in front shows SETUP
  (`simulation_ui._setup_tab_without_results`).

## For sim-core (engine issues met while building the UI)

1. Fixed by sim-core: `simulation._link_list` dropped a whole-body pick (`(body, [])` is stored
   as nothing in a PropertyLinkSubListGlobal; it now writes `(body, [""])`). The UI's
   `simulation_panels._keep_whole_bodies` stays as a harmless check.
2. Open: the result summary keys bodies by **label** (`summary["bodies"][body.Label]`): two
   components' first bodies are both "Body1" in Fusion's numbering and share one entry.
3. Fixed by sim-core: a model held by one straight edge solved "done" with 1.4e10 mm of
   displacement (CalculiX found a mechanism); the pre-check and the job now say "not held
   enough". The UI still refuses to hand over results that moved more than half the model's
   size (`simulation_solve_dialog.loose_result`).
4. Open: `_finish` takes `signature(study)` when the solve ends: a design change made while it
   ran looks up to date. The UI stores the fingerprint from the start
   (`simulation_solve_dialog._keep_out_of_date`); the engine could take it in `_stage_model`.
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

## FreeCAD / Qt facts and traps

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
contacts / connectors / global loads / point mass, force Angle and Limit Target, Repair and the
Job Status history, the glyph look is SciForge's own).

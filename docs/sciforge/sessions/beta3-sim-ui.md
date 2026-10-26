# Session log: beta 3, sim-ui (the SIMULATION workspace's SETUP side), branch `sf/sim-ui`

Builder sim-ui of beta 3 (2026-10-26/27). Brief: `docs/sciforge/dev/briefs/beta3-sim-ui.md`.
Spec: `docs/sciforge/parity/simulation.md` section "Setup" (behaviour table with sources,
scenarios, Known gaps). Engine: sim-core's `simulation.py` / `simulation_core.py` (merged
`sf/sim-core` 117f9162 into this branch).

## What was built

- **The workspace switch** (`simulation_ui.py`): Workspace > Simulation / Design per design
  (each open design remembers its workspace; closing one forgets it; a reopened design opens in
  DESIGN), the timeline hidden in SIMULATION, the study tree in the browser, the glyphs, the
  Pre-check traffic light on the ribbon; entering finishes an open command or sketch and clears
  the selection; from a drawing's tab the design's 3D view comes forward first; without a study
  the New Study dialog opens by itself.
- **Dialogs** (`simulation_dialogs.py`): New Study (11 study types as tiles, Static Stress
  available, the gear's settings before the study exists), Study Settings (General: Remove
  rigid body modes, keep results; Mesh: % or absolute size, per part, order, curved, turn
  angle, adjacent / aspect ratio, minimum; Adaptive: levels or custom; Contacts: Bonded, tolerance), Study
  Materials (In Study, model material, study material, properties with "filled in by SciForge"
  notes, safety basis), gravity on / off, Automatic Contacts, Contact Manager, Load Case
  Attributes, Pre-check list, DOF View.
- **Pick dialogs** (`simulation_panels.py`, on `pickpanel.PickPanel`): Structural Constraints,
  Structural Loads and Local Mesh Control (one item dialog, category constraint / load / mesh),
  Edit Gravity. Every kind's options; values with units; the live glyph preview.
- **Solve** (`simulation_solve_dialog.py`): the Solve dialog, the progress window (stages,
  elapsed time, Cancel), studies one after another, the hand-over to RESULTS, Generate Mesh with
  the engine's mesh-only job, Show Mesh, the "not held enough" guard.
- **Glyphs** (`simulation_glyphs.py`), **browser** (`simulation_browser.py` + hooks in
  `browser_ui.py`), **ribbon** (the SETUP entries in `ribbon_config.py`, plus DISPLAY > Show
  Mesh), **icons** (`tools/sciforge/icons_simulation.py`, 35 icons), unit tests
  (`test_simulation_setup_core.py`, 30), seven GUI scenarios `sim_setup_*.py`.

## Contract with sim-results (agreed by reading its branch)

- sim-ui calls `simulation_results_ui.show(study)` when a solve ends (else selects the RESULTS
  tab itself), and `simulation_results_ui.hide()` when the workspace is left.
- sim-results calls `simulation_ui.active()`, `active_study(doc)`, `set_active_study(study)`,
  `enter_workspace("sim_results")`, and `simulation_glyphs.set_visible(on)` / `visible()`.
- A study without results made active while RESULTS is in front shows SETUP
  (`simulation_ui._setup_tab_without_results`).

## For sim-core (engine issues met while building the UI)

1. `simulation._link_list` drops a whole-body pick: `(body, [])` is stored as nothing in a
   PropertyLinkSubListGlobal, so a Local Mesh Control with Body Selection "lost what it was on".
   `(body, "")` keeps it (checked in FreeCAD 1.1.4). The UI rewrites the References after
   add_item / update_item meanwhile (`simulation_panels._keep_whole_bodies`).
2. The result summary keys bodies by **label** (`summary["bodies"][body.Label]`): two
   components' first bodies are both "Body1" in Fusion's numbering and share one entry.
3. A model held by one straight edge solved "done" with 1.4e10 mm of displacement (CalculiX
   found a mechanism instead of failing). The UI refuses to hand such results over
   (`simulation_solve_dialog.loose_result`: movement > half the model's size), but the summary
   is still saved; the engine should fail it (or the pre-check warn: a single held edge).
4. `_finish` takes `signature(study)` when the solve ends: a setup change made while it ran
   looks up to date. The UI stores the fingerprint from the start
   (`simulation_solve_dialog._keep_out_of_date`); the engine could take it in `_stage_model`.

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

## Gaps

See the parity doc's Known gaps (Simplify, several load cases, per-body safety basis, adaptive
manual contacts / connectors / global loads / point mass, force Angle and Limit
Target, document units, Repair, glyph look unverified on screen).

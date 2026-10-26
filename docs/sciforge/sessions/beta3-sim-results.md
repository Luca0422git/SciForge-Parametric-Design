# Session log: beta 3, builder sim-results (the RESULTS tab)

Branch `sf/sim-results` (from `beta3`), 2026-10-26/27. Brief:
`docs/sciforge/dev/briefs/beta3-sim-results.md`. Spec: outline 7.18; Fusion's behaviour:
`docs/sciforge/dev/research/fusion-simulation.md` section 5; parity:
`docs/sciforge/parity/simulation.md` section Results (behaviour table with sources, known gaps).
Merged `sf/sim-core` and `sf/sim-ui` (twice) to work against their newer engine and SETUP tab.

## What was built

- `sciforge/simulation_results_core.py` (pure, `SciForgeTests/unit/test_simulation_results_core.py`):
  Fusion's result list (type + component), units (MPa / kPa / Pa / psi / ksi, mm / cm / m / in),
  the colour map texture and legend (the safety factor 0 .. 15, red low), the safety factor
  targets (3 / 6) and their sentence, deformation and animation steps, the outer surface of a
  tetrahedral mesh with numpy (boundary faces = faces of one element only, turned to face out,
  10-node faces split in 4, mesh edges, outline edges where faces meet at more than 30 degrees),
  a ray against triangles (probes), a plane through straight tetrahedra (a 10-node one split in
  8) for the slice, the HTML report.
- `sciforge/simulation_results.py`: `ResultData` (node places, tetrahedra, surface,
  displacements, values, stats, strain components; kept per solve, keyed by the result object's
  ID and the summary's time), Results Details' rows, the report's data and file.
- `sciforge/simulation_results_view.py`: `ResultDisplay` (SciForge's own Coin nodes: a colour
  map texture with one texture coordinate per surface node, so a coarse mesh still shows the
  map's colours between nodes; mesh and outline lines; the cut face; the undeformed ghost),
  the legend (`Legend`, `ColourBar`), the tags (`TagLayer`), the animation bar.
- `sciforge/simulation_results_ui.py`: the RESULTS tab's controller (`Session` per design),
  `show(study)`, `hide()`, `finish()`, `current()`, the 17 commands (`COMMANDS`).
- `sciforge/simulation_results_panels.py`: Surface Probes and Slice Plane (task panels with no
  undo step), Results Details, Report, Reaction Force, a fallback solve.
- Ribbon: the RESULTS tab's groups wired (`ribbon_config.py`, my lines only), 21 icons
  (`tools/sciforge/icons_simresults.py`).
- Scenarios (`SciForgeTests/gui/scenarios/simres_*.py`, helpers `SciForgeTests/gui/simres_steps.py`):
  cantilever (57 checks), deformation (59), probes_slice (44), report (34), reopen (21),
  out_of_date (32), workspace (44).

## Agreed with sim-ui and sim-core (through their logs and code)

- sim-ui's Solve dialog calls `simulation_ui.show_results(study)`, which calls
  `simulation_results_ui.show(study)` (it makes the study sim-ui's active one, opens the
  SIMULATION workspace's RESULTS tab and shows the safety factor).
- sim-ui's `leave_workspace()` calls `simulation_results_ui.hide()`.
- The RESULTS tab belongs to sim-ui's active study (`simulation_ui.active_study(doc)`); the tab
  button shows only while that study has results (`refresh_tab()`).
- The setup's glyphs: `simulation_glyphs.set_visible(False)` while results show (unless
  DISPLAY > Loads and Constraints), restored after.
- A pick dialog of sim-ui (`pickpanel.PickPanel`: a load edited from the browser, Local Mesh
  Control) opened while the results show switches to SETUP (the model is hidden on RESULTS).
- sim-core: `summary["reactions"][label] = {x, y, z, total}` (Reaction Force),
  `results_dropped(study)` (Keep results off: no RESULTS tab, `show()` says to solve again).

## FreeCAD / Qt facts learned (traps)

- **A child widget of the 3D view with `WA_TranslucentBackground` crashes FreeCAD's
  `saveImage`** ("QPaintDevice: Cannot destroy paint device that is being painted", then
  SIGSEGV). The overlays now live in the 3D view's frame (the OpenGL widget's parent) without
  that attribute.
- **`view.saveImage()` renders off screen under xvfb**: the pictures are real (the 3D view on
  the screen stays blank there). Useful to look at a display in a test.
- Hiding the design for the results through the view providers' Coin switch
  (`ViewObject.SwitchNode.whichChild = -1`) changes nothing in the document: Visibility, undo,
  the modified mark and the study's out-of-date fingerprint (which counts only shown bodies)
  stay as they were. FreeCAD may show a switch again on a display mode change: a timer hides it
  again while results show.
- FreeCAD's quadratic tetrahedra (SMDS order): corners 0-3, then the mid nodes of 01, 12, 20,
  03, 13, 23. `ViewProviderFemMesh.VisibleElementFaces` exists but was not needed.
- pivy takes numpy float32 arrays in `setValues` (100 000 points: 0.05 s; a list: 0.22 s).
- A QDialog's push buttons are auto-default: Enter in a number field closed Results Details;
  its Close button is not auto-default now.
- QMenu ignores a click that comes without a mouse movement since it opened: a scenario that
  clicks the same menu entry twice moves the mouse away in between.
- After a solve the study and result objects stay "touched" (sim-core's): `doc.isTouched()` is
  true after Save; the scenarios check the Gui document's Modified flag instead.

## Measured

- Bracket (1 400 nodes): RESULTS shown 0.2 s after the click; a result change 6 ms.
- Same bracket at 2 % mesh (30 000 nodes, 17 500 elements): arrays 0.8 s once per solve, show
  0.14 s, result change 25-50 ms, deformation change 6 ms, slice 0.11 s, probe 8 ms.

## Log

- 18:05 read the briefs, research, engine; explored the result objects in FreeCAD 1.1.4.
- 18:30 first increment: core, data, display, controller, panels, ribbon, icons (one exploration
  run did everything right first time: legend, tags, slice, report).
- 18:35-19:05 merged sim-core / sim-ui; seven scenarios; fixes from them (a 300 N load to make
  the held end red-ish; Enter in Results Details; Slice alone see-through; the menu click trap).
- 19:05 visual check with saveImage pictures (bracket, fine mesh): even cut-face shading, 11
  safety factor ticks, legend options, strain components, the saveImage crash fixed.

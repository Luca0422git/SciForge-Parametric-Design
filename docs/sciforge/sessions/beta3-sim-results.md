# Session log: beta 3, builder sim-results (the RESULTS tab)

Branch `sf/sim-results` (from `beta3`), 2026-10-26/27. Brief:
`docs/sciforge/dev/briefs/beta3-sim-results.md`. Spec: outline 7.18; Fusion's behaviour:
`docs/sciforge/dev/research/fusion-simulation.md` section 5; parity:
`docs/sciforge/parity/simulation.md` section Results (behaviour table with sources, known gaps).
Merged `sf/sim-core` and `sf/sim-ui` (four times) to work against their newer engine and SETUP
tab; the merges brought adaptive mesh refinement, the results read in the background, the
per-body keys of same-named bodies and the last engine fixes.

## What was built

- `sciforge/simulation_results_core.py` (pure, `SciForgeTests/unit/test_simulation_results_core.py`):
  Fusion's result list (type + component), units (MPa / kPa / Pa / psi / ksi, mm / cm / m / in)
  and the design's units first, the colour map texture and legend (the safety factor 0 .. 15,
  red low), the safety factor targets (3 / 6) and their sentence, deformation and animation
  steps (and the saved animation's frames), the outer surface of a tetrahedral mesh with numpy
  (boundary faces = faces of one element only, turned to face out, 10-node faces split in 4,
  mesh edges, outline edges where faces meet at more than 30 degrees), a ray against triangles
  (probes), a level set through straight tetrahedra in numpy (the slice plane and the
  iso-surface; a 10-node element split in 8), the cut's mesh lines, a point found in the mesh
  with its weights (Point Probes), the slice plane's place (axis, face clicked, construction
  plane), the legend's dragged range, Solver Data's rows, the convergence plot's data (each
  solve's value and change, the verdict, round axis ticks), the HTML report (a cover, several
  studies, the adaptive refinement's table).
- `sciforge/simulation_results.py`: `ResultData` (node places, tetrahedra, surface,
  displacements, values, stats, strain components, values and displacement anywhere inside;
  kept per solve, keyed by the result object's ID and the summary's time), Results Details'
  rows, the report's data and file, the design's length unit.
- `sciforge/simulation_results_view.py`: `ResultDisplay` (SciForge's own Coin nodes: a colour
  map texture with one texture coordinate per surface node, so a coarse mesh still shows the
  map's colours between nodes; mesh and outline lines; the cut face and its mesh lines; the
  iso-surface; the undeformed ghost), the legend (`Legend`, `ColourBar` with drag handles), the
  tags (`TagLayer`: min / max, probes, point probes, the value under the mouse), the animation
  bar.
- `sciforge/simulation_results_ui.py`: the RESULTS tab's controller (`Session` per design,
  `CompareSession`: the 3D view split in panes through Navigation bar > Viewports' layouts, one
  study per pane, the panes' cameras turning together), `show(study)`, `hide()`, `finish()`,
  `current()`, the 23 commands (`COMMANDS`).
- `sciforge/simulation_results_panels.py`: Surface Probes, Point Probes (grips), Slice Plane and
  Iso-surface (task panels with no undo step), Results Details (per-body lowest safety factor in
  its band's colour, values in the legend's units), Legend Min/Max, Compare, Report, Reaction
  Force, Solver Data, Convergence Plot (a chart drawn with QPainter in the theme's colours),
  Save Animation, a fallback solve.
- Ribbon: the RESULTS tab's groups wired (`ribbon_config.py`, my lines only), 23 icons
  (`tools/sciforge/icons_simresults.py`); Convergence Plot is greyed for a study solved without
  adaptive refinement (its tooltip says so), Reaction Force when the solve has no reactions;
  nothing else on the RESULTS tab is greyed.
- Scenarios (`SciForgeTests/gui/scenarios/simres_*.py`, helpers
  `SciForgeTests/gui/simres_steps.py`): adaptive, cantilever, compare, deformation, inspect,
  linear, out_of_date, probes_slice, reopen, report, workspace (check counts in the report).

## Agreed with sim-ui and sim-core (through their logs and code)

- sim-ui's Solve dialog calls `simulation_ui.show_results(study)`, which calls
  `simulation_results_ui.show(study)` (it makes the study sim-ui's active one, opens the
  SIMULATION workspace's RESULTS tab and shows the safety factor).
- sim-ui's `leave_workspace()` calls `simulation_results_ui.hide()`.
- The RESULTS tab belongs to sim-ui's active study (`simulation_ui.active_study(doc)`); the tab
  button shows only while that study has results (`refresh_tab()`).
- The setup's glyphs: `simulation_glyphs.set_visible(False)` while results show (unless
  DISPLAY > Loads and Constraints), restored after; the report's setup picture draws a study's
  glyphs with `simulation_glyphs.refresh(doc, study, force=True)` (the active study is left
  alone).
- A pick dialog of sim-ui (`pickpanel.PickPanel`: a load edited from the browser, Local Mesh
  Control) opened while the results show switches to SETUP (the model is hidden on RESULTS).
- sim-core: `summary["reactions"][label] = {x, y, z, total}` (Reaction Force),
  `results_dropped(study)` (Keep results off: no RESULTS tab, `show()` says to solve again),
  `summary["timings"]`, `["notes"]`, `["mesh"]`, `["adaptive"]["passes"]` and `mesh_summary()`
  (Solver Data), `["adaptive"]` with `simulation_core.adaptive_plan()`'s tolerance and
  `converged()`'s rule (Convergence Plot: the change is % of the larger of two solves, as the
  engine judges it), `body_key()` (same-named bodies' per-body rows).
- The nav bar's `viewports_ui` (not a simulation builder's): Compare calls only its public
  `set_layout(name)`, `panes()`, `current()`, `is_single()` and `area()`; Viewports > Single View
  during Compare ends Compare.

## FreeCAD / Qt facts learned (traps)

- **A child widget of the 3D view with `WA_TranslucentBackground` crashes FreeCAD's
  `saveImage`** ("QPaintDevice: Cannot destroy paint device that is being painted", then
  SIGSEGV). The overlays now live in the 3D view's frame (the OpenGL widget's parent) without
  that attribute.
- **`view.saveImage()` renders off screen under xvfb**: the pictures are real (the 3D view on
  the screen stays blank there). Useful to look at a display in a test, and the base of the
  report's pictures and the saved animation.
- **Qt 6's `QTest.mouseMove(widget, pos)` moves the real pointer (`QCursor::setPos`)**: the X
  server's motion events come later. A QMenu remembers where the pointer was when it opened and
  takes no click there unless it saw the mouse move (more than 6 motions, or more than the drag
  distance away): a scenario clicking the same menu entry twice failed every other time. The
  scenarios' menu helper puts the pointer far away and waits 150 ms before opening a menu.
- Hiding the design for the results through the view providers' Coin switch
  (`ViewObject.SwitchNode.whichChild = -1`) changes nothing in the document: Visibility, undo,
  the modified mark and the study's out-of-date fingerprint (which counts only shown bodies)
  stay as they were. FreeCAD may show a switch again on a display mode change (or Undo may
  bring a deleted body back): the App document observer's `slotCreatedObject` and
  `slotChangedObject(obj, "Visibility")` flag it and the results' timer hides it again; a full
  look at a few hidden objects in turn (60 every 0.4 s) catches the rest (a display mode change
  tells only the Gui side); a look at all of a design of 800 objects took 56 ms.
- **A Gui document observer (`Gui.addDocumentObserver`; ours had `slotCreatedObject` and
  `slotChangedObject`) breaks FEM object creation**: with it registered, `ObjectsFem.makeMeshGmsh(doc, "SimMesh")` failed
  inside `addObject` with "Cannot create object 'SimMesh': (Cannot add static property)" and
  every solve failed. The App observer's slots are harmless. (Worth knowing for any builder.)
- FreeCAD's quadratic tetrahedra (SMDS order): corners 0-3, then the mid nodes of 01, 12, 20,
  03, 13, 23.
- pivy takes numpy float32 arrays in `setValues` (100 000 points: 0.05 s; a list: 0.22 s).
- A QDialog's push buttons are auto-default: Enter in a number field closed Results Details;
  its Close button is not auto-default now. In a task panel Enter is OK (as in Fusion): the
  scenarios type a value and Tab away.
- After a solve the study and result objects stay "touched" (sim-core's): `doc.isTouched()` is
  true after Save; the scenarios check the Gui document's Modified flag instead.
- FreeCAD's AppImage bundles Pillow 12 (with GIF and WebP writers) and matplotlib, no video
  encoder: the animation is saved as an animated GIF or WebP.
- A slice exactly through a layer of nodes gave no cut face while corners at zero counted as
  below: they count as above now (the face comes once, from the element below).
- `QMdiArea.setActiveSubWindow(sub)` makes `Gui.ActiveDocument.ActiveView` that pane's view at
  once: the way Compare finds each pane's FreeCAD view (a view object gives no widget).
- Copying a camera node's position, orientation, focal distance and height (or height angle)
  from one view to another makes the other redraw by itself; a 70 ms timer that copies the
  moved pane's camera keeps the panes together without a feedback loop.
- In split views FreeCAD's overlay Tasks panel (`OverlayRight`, empty) draws a thin rectangle
  over the right-hand panes; it is there with the plain Two Views layout too (not SciForge's
  results).
- A body deleted while its results show leaves dead Python objects in cached lists: every
  `.Name` on them raises; the results keep a key for it and stay drawn.

## Measured

- Bracket (1 400 nodes): RESULTS shown 0.2 s after the click; a result change 6 ms.
- Same bracket at 2 % mesh (30 000 nodes, 17 500 elements): arrays 0.8 s once per solve, show
  0.14 s, result change 25-50 ms, deformation change 6 ms, probe 8 ms.
- The numpy level set on 135 000 straight tetrahedra (a 30 x 30 x 30 grid): a slice 40-80 ms,
  an iso-surface 40 ms (the earlier Python loop: about 1 s); a point found in 25 ms.

## Log

- 18:05 read the briefs, research, engine; explored the result objects in FreeCAD 1.1.4.
- 18:30 first increment: core, data, display, controller, panels, ribbon, icons.
- 18:35-19:05 merged sim-core / sim-ui; seven scenarios; fixes from them (a 300 N load to make
  the held end red-ish; Enter in Results Details; Slice alone see-through; the menu click trap).
- 19:05 visual check with saveImage pictures (bracket, fine mesh): even cut-face shading, 11
  safety factor ticks, legend options, strain components, the saveImage crash fixed.
- 19:15-19:45 Legend Min/Max, the slice's drag arrow, dropped results, picking dialogs, the
  legend's verdict, linear meshes and strains, Compare (2 to 4 studies side by side on one
  colour scale), Multiple Views, huge meshes.
- 19:47 merged sim-ui (with sim-core's adaptive refinement and background results reading).
- 20:00 Point Probes, Iso-surface, Solver Data (INSPECT's last greyed tools); the slice cut and
  the iso-surface one numpy level set.
- 20:10-20:55 Slice Plane parallel to a clicked face and on construction planes, mesh lines on
  the cut; the value under the mouse with probe tools; Point Probe grips; Save Animation (GIF /
  WebP); legend drag handles and Grey Outside the Range; the report's cover, several studies and
  setup picture; the design's units in the legend; results windows close with their results.
- 20:55-21:20 the browser's body eye takes a body's results away (and back); reaction tags on
  the constraints; displacement arrows on the cut; tags spread so they never overlap; 10-node
  faces drawn with their quadratic shape functions; Measure from RESULTS brings SETUP back;
  scenario simres_adaptive; merged sim-core and sim-ui (same-named bodies' keys).
- 21:20-21:45 all eleven scenarios green after the merge; Results Details colours each body's
  lowest safety factor by its band; every slot, timer and handler guarded; odd flows explored
  with real FreeCAD (a study deleted with its panel open, the 3D view closed under the results,
  a second design, a body deleted and brought back by Undo, a missing animation folder, a
  report to a folder that does not exist): fixes for the deleted body and new objects; the
  Convergence Plot and the report's adaptive table.
- 21:45-22:00 Compare in split views (two panes, or four for three or four studies; cameras
  turning together; Viewports > Single View ends it); the side-by-side fallback's tags follow a
  sideways shift; Results Details' tables fit their rows, per-body values in the legend's units
  (the report's too); merged sim-core and sim-ui again; unit tests (2 591) pass.
- 22:00-22:15 the report's Preview (the page opened in the web browser from the temporary
  folder, nothing saved) and its reaction force table; with a body's eye off the min / max tags
  mark the bodies still drawn; objects shown again under the results are found through the
  App document observer (a new object, a Visibility switched on) and a look at 60 hidden
  objects in turn every 0.4 s, instead of all of them every 0.4 s (56 ms for 800 objects). A Gui document observer,
  tried first, broke the solve (see the facts above); all fifteen results and simulation
  scenarios pass again.
- 22:15-22:30 Compare: the layout put back when a split fails half way (the side-by-side
  fallback now tested), a solve ending meanwhile ends Compare and shows its study, each tag says
  when its study is out of date; the report's pictures include the convergence chart (drawn on
  white paper whatever the look); the periodic look for shown-again objects takes 60 in turn
  (5 ms instead of 56-69 ms on a design of 800 objects).

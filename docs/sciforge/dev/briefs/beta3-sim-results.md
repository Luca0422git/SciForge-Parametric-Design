You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: Static Stress results, the RESULTS tab (builder sim-results, branch `sf/sim-results`)

Outline 7.18 is the spec; Fusion's behaviour with sources is
`docs/sciforge/dev/research/fusion-simulation.md` (read all of it, especially the results
section). The engine exists and works (read `sciforge/simulation.py` and `simulation_core.py`
completely: `results(study)` gives node coordinates, displacement vectors and every stress
array; the safety factor per node is in the result object's UserDefined list; `summary(study)`
has min / max with their places per result and per body; `simulation_core` has the result list,
units, the colour spectrum (`colour`, `scale_for`, `legend_ticks`, `SAFETY_CAP`)). sim-core
extends the engine, sim-ui builds the SETUP tab and the Solve dialog; when a solve ends sim-ui
calls your `simulation_results_ui.show(study)` (agree on it in your session logs; you own that
module): `git merge sf/sim-core` / `sf/sim-ui` whenever you need them. To work before sim-ui is
ready, solve with `simulation.solve(study)` in your scenarios' setup.

Research decisions to follow: Fusion has two result viewers (research 5.2: the RESULTS tab in
the canvas, and a newer browser-based viewer with threshold sliders and "Meets / Below Safety
Factor Target" text). Build the RESULTS tab in the canvas, and take the newer viewer's useful
pieces into it: Safety Factor Target bands and the meets / below sentence in Results Details.
The safety factor is capped at 15 (`simulation_core.SAFETY_CAP`); the deformation options and
the Adjusted rule are in `simulation_core.DEFORMATIONS` / `deformation_factor` (5 % of the model
size for the largest displacement, research 5.6).

### What to build
1. **The result display**: the study's result mesh (FreeCAD's Fem::FemMeshObject made by the
   solve; its view provider takes node colours and node displacements: `NodeColor`,
   `setNodeColorByScalars`, `setNodeDisplacementByVectors`, `applyDisplacement`; or your own Coin
   nodes if that is better) coloured by the chosen result with simulation_core's spectrum
   (safety factor red low to blue high, capped at SAFETY_CAP; the rest blue low to red high),
   smooth (no mesh lines unless Show Mesh), the design's bodies hidden meanwhile and shown again
   when you leave, all display-only (nothing that lands in the undo history or the file).
2. **The RESULTS tab** (scaffold groups in `ribbon_config.py`, `# owner: sim-results`): the
   result type picker (Fusion's list, research), the legend (Fusion's place and look, research:
   a vertical colour bar with values and unit, the result's name, min / max; your own Qt overlay
   on the 3D view, original look), Deformation Scale (Fusion's options: actual, adjusted,
   adjusted x N...) and Animate (play / stop, speed, loop), Show Min / Max (markers with value
   labels), Surface Probes (click on the result: a label with the value there; several; clear),
   Slice Plane (a plane cutting the result, coloured on the cut: FreeCAD's VTK post pipeline
   `makePostVtkFilterCutFunction` or your own cut of the mesh; if neither works well, a greyed
   entry and a Known gap), display options (show mesh, undeformed model as a see-through ghost,
   show loads and constraints), Results Details / study summary (per body: max stress, min
   safety factor, max displacement, the material and its strength), Report (an HTML file with the
   study's setup, mesh, materials, results tables and pictures of each result: Fusion's report,
   research), Finish Results (back to SETUP, the bodies shown again). Commands Fusion has that
   you cannot build: greyed with the reason.
3. **Out of date**: results of a study whose design changed since the solve show a clear
   warning (Fusion's, research) and re-solve from there.
4. Icons (`icons_simresults.py`).

Scenarios `simres_*.py` (8+ paths with real clicks): a solved cantilever shows the safety factor
coloured (check node colours at the fixed end are red-ish and at the free end blue-ish), switch
to von Mises and displacement (legend values match `summary`), deformation x10 and actual
(check node displacements applied), animate and stop, min / max markers at the summary's places,
a probe click reads the nearest node's value, slice plane, show mesh, report written (file exists,
contains the numbers), Finish Results restores the bodies, leave the workspace and come back,
save / reopen with results, a changed design shows out of date.

Spec: `docs/sciforge/parity/simulation.md` section "Results". Session log:
`docs/sciforge/sessions/beta3-sim-results.md`. Report as beta3-common says.

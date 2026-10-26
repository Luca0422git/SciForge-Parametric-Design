# Parity spec: Simulation workspace, Static Stress (beta 3, outline 7.18)

Fusion's Simulation workspace limited to its Static Stress study. Fusion's behaviour with
sources: `docs/sciforge/dev/research/fusion-simulation.md`. Plan: `docs/sciforge/plan-beta3.md`.
SciForge solves on the person's own computer (FreeCAD's FEM module: Gmsh meshes, CalculiX
solves); Fusion has solved Static Stress only in Autodesk's cloud since September 2022, so local
solving with Cancel at any time is a deliberate **(SciForge)** difference.

Each builder writes only its own section (beta3-common.md).

## Engine

(builder sim-core)

## Setup

(builder sim-ui)

## Results

(builder sim-results, branch `sf/sim-results`, 2026-10-26/27.) Fusion's RESULTS tab of a
Static Stress study. Files (`src/Mod/SciForge/sciforge/`):

| File | What it holds |
|---|---|
| `simulation_results_core.py` | the rules, no FreeCAD / Qt, unit tested: Fusion's result list (type + component), units, the colour map texture and legend, the safety factor targets and their sentence, deformation and animation, the outer surface of the tetrahedral mesh (10-node faces split in 4, facing out; mesh and outline edges), a ray against it (probes), a plane through it (slice), the HTML report |
| `simulation_results.py` | the document side, no Qt: a study's results as arrays (kept per solve), strain components, Results Details' numbers, the report's data |
| `simulation_results_view.py` | the drawing: SciForge's own Coin nodes (never document objects), the legend, the tags and the animation bar floating over the 3D view |
| `simulation_results_ui.py` | when the results show (the RESULTS tab watcher), `show(study)` for sim-ui's Solve dialog, `hide()`, the 17 commands |
| `simulation_results_panels.py` | Surface Probes, Slice Plane, Results Details, Report, Reaction Force, a solve from out-of-date results when sim-ui's Solve is missing |

Shared files: `ribbon_config.py` (the RESULTS tab's groups: commands, icons, ticks),
`tools/sciforge/icons_simresults.py` (21 icons), `docs/sciforge/parity-checklist.md`
(regenerated). No FreeCAD core change. Sources as in the research file (**A** Autodesk, **F**
forum, **T** tutorial / exported report, **G** guess); four WebSearch excerpts this session:
Autodesk's Results details help (three states against a Lower and an Upper target, "reducing the
Upper Target can ... give a false positive"), an Autodesk Learn video (default targets "three
... lower limit and six is the upper limit"), Autodesk's legend help (result drop-down, a second
drop-down for direction or type, units, legend options with colour bands), guided results
("suggestions for steps you can take").

### What shows, when

| Fusion | SciForge | Src |
|---|---|---|
| After a solve the canvas shows the results, Safety Factor first, with min / max tags | sim-ui's Solve dialog calls `simulation_results_ui.show(study)`: the SIMULATION workspace's RESULTS tab, Safety Factor, min / max tags | A[80] A[71] |
| The RESULTS tab exists once there are results | The RESULTS tab shows only while the active study (sim-ui's) has results; selecting it shows them, SETUP / DESIGN / another document puts them away | A[49], G (mem) |
| The deformed shape is Adjusted by default | Adjusted (largest movement = 5 % of the model's bounding-box diagonal) | A[51], research Q9 |
| (Fusion keeps results in its cloud) | Display only: SciForge's own Coin nodes; the design's bodies are hidden on the 3D view only (their Coin switch, never Visibility): nothing in the undo history, the file, the modified mark or the study's out-of-date fingerprint (checked in the scenarios) | SciForge |
| Results tied to a design version: "out of date" when the design changed; solve again | The legend warns "out of date" with **Solve Again** (sim-ui's Solve dialog), Results Details and the report say it too; Undo of the change clears it | F[85] A[65] |
| Finish Results returns to SETUP | Same; the bodies show again | G (mem) |
| (results not saved) | A study whose results were not kept with the design (sim-core's Keep results off) has no RESULTS tab; `show()` says to solve again | SciForge |

### The legend and the result list

| Fusion | SciForge | Src |
|---|---|---|
| Legend: result drop-down, a second drop-down for the component, a unit drop-down, legend options | Same, at the top left of the 3D view: Safety Factor / Stress / Displacement / Strain, then the component; units MPa, kPa, Pa, psi, ksi or mm, cm, m, in (none for the safety factor and strain) | A[77] A[49], Autodesk legend help; place G |
| Result types | Safety Factor; Stress: Von Mises, 1st / 3rd Principal, Normal XX / YY / ZZ, Shear XY / YZ / ZX; Displacement: Total, X, Y, Z; Strain: Equivalent, 1st / 3rd Principal, Normal XX / YY / ZZ (worked out from the solve's strain tensor) | A[48], components G (A[82] Inventor) |
| A vertical colour bar with min and max | Max above, Min below the bar, 9 values (the safety factor every 1.5); colours blue - cyan - green - yellow - red drawn with a colour map texture, so the colours between two nodes follow the map | G (mem) |
| Safety factor capped at 15; no legend min / max for it | Scale 0 .. 15, red low, blue high | F[89] F[90] T[107] |
| Legend options: colour transitions (bands) | "..." > Smooth Colours / Colour Bands (9 bands) | Autodesk legend help |
| Legend Min/Max (legacy viewer: RESULT TOOLS > Legend Min/Max; not for the safety factor) | RESULT TOOLS > Legend Min/Max and the legend's "..." menu: Min and Max in the legend's unit, Reset; values beyond take the end colours (G); the legend shows the result's own min / max and says the colours' range; refused for the safety factor | A[53] F[90], web excerpt |
| Results Details button next to the Load Case selector | The "i" button in the legend (one load case per study: no selector) | A[61] |

### RESULTS tab commands

| Group: Fusion | SciForge | Src |
|---|---|---|
| RESULT TOOLS: Animate (legacy dialog with steps; online viewer: bar at the bottom of the canvas, speed 0.25x - 2x, up to 100 frames, play once / loop / mirror loop, save .webm) | Animate: a bar at the bottom left of the 3D view: Play / Stop, 0.25x - 2x, 10 - 100 steps, Play Once / Loop / Mirror Loop, Close; undeformed to the chosen scale (Adjusted when Undeformed is chosen) | A[52] |
| RESULT TOOLS: Results Details | The lowest safety factor against the Lower / Upper targets (3 / 6) in a sentence with advice (SciForge's words), the targets editable, **Show the target bands on the model** (the newer viewer's guided bands: below / meets / above), per body: material, strength (yield or ultimate), max von Mises, min safety factor, max displacement; every result's min / max; the mesh; the limits of the study; the deformation scale at the bottom | Autodesk help (Results details), Learn video, A[54] A[71] A[51] |
| RESULT TOOLS: Report (General, Properties, Studies; Preview / Save; HTML) | Report: title, author, pictures or not, file; Save / Save and Open (the web browser). One HTML page: the sentence, the limits, settings, materials with strengths, constraints and loads with their faces, contacts, mesh, every result's min / max, per body, three pictures with their legend drawn in | A[62] T[107] |
| RESULT TOOLS: Compare (up to 4 studies) | Greyed: "Not in SciForge yet" (see gaps) | A[61] |
| DEFORMATION: Undeformed, Actual, Adjusted x 0.5, Adjusted, x 2, x 5 | Same, ticked in the menu; also in Results Details | A[51] |
| DISPLAY: Mesh, Wireframe | Show Mesh (element edges); **Undeformed Model** (the unloaded shape see-through: the web viewer's "Show Undeformed model") instead of Wireframe; **Loads and Constraints** (sim-ui's glyphs on the results, off by default) | A[49] A[68], G |
| INSPECT: Surface Probes | Click the result: a tag with the value of the node under the mouse; as many as wanted; they read the result chosen in the legend; Clear All; Esc / Close keeps them | A[55] |
| INSPECT: Show Min/Max | Toggle (on by default) | A[80] A[57] |
| INSPECT: Reaction Force | A table: the force each constraint takes (X, Y, Z, total), from the solve (sim-core's `summary["reactions"]`) | A[48] A[58] |
| INSPECT: Slice Plane (legacy: Shaded, Mesh Lines, Vectors, Clipping; online: Section, Slice) | A plane across X, Y or Z, position (field, slider, or the plane's drag arrow), Flip; **Cut the result away** (clipping, the cut face coloured with the values inside) or **Slice alone** (the cut face inside the whole result drawn see-through); a probe on the cut face reads the value inside; OK / Cancel / Remove Slice | A[56] |
| INSPECT: Point Probes, Iso-surface, Solver Data | Greyed with the reason (a Surface Probe on a slice reads inside) | A[55] A[57] |
| MANAGE | sim-ui's (shared with SETUP) | A[49] |
| FINISH RESULTS | Finish Results | G (mem) |

### Known gaps (Results)

- **Compare** (two to four studies side by side, split canvas): greyed. SciForge has one result
  display per design; showing several studies at once needs one display per viewport
  (`viewports_ui`) and synchronized cameras. Workaround: activate each study and look at its
  RESULTS tab in turn.
- **Saving the animation as a video (.webm)**: not built; the 3D view can be captured frame by
  frame (`saveImage`) but SciForge has no video encoder in the bundle.
- **Slice plane at any angle / on a picked face**, the **Vectors** and **Mesh Lines** slice
  styles: the plane is across X, Y or Z only.
- **The online viewer's threshold sliders** (a range of interest dragged on the legend): Legend
  Min/Max (typed values) covers the same need.
- **Contact pressure / force results**: bodies are bonded (glued), which has no contact pressure;
  CalculiX's contact output is not requested.
- **Shear strain components**: CalculiX's shear strains are tensor values (half the engineering
  shear strain); left out rather than shown with an uncertain meaning. Normal and principal
  strains are shown.
- **Load case selector**: one load case per study.
- **Report**: no logo, cover picture, approvers or revision fields; one study per report.
- **Iso-surface, Point Probes inside the part, Solver Data**: greyed.
- **The legend's place** (top left of the 3D view) and the safety factor's colours (0 .. 15,
  red low) are guesses (research section 10, questions 1 and 6): a screenshot of Luca's Fusion
  would settle them.

## Benchmarks

(builder sim-core)

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

(builder sim-ui, branch `sf/sim-ui`.) The SIMULATION workspace switch, the SETUP tab's
commands and dialogs, the study tree in the browser and the glyphs on the model. Code:
`simulation_ui.py` (switch, commands), `simulation_dialogs.py`, `simulation_panels.py`,
`simulation_solve_dialog.py`, `simulation_browser.py` (+ hooks marked "SIMULATION workspace" in
`browser_ui.py`), `simulation_glyphs.py`, `simulation_setup_core.py` (rules, unit tested in
`test_simulation_setup_core.py`); icons `tools/sciforge/icons_simulation.py`. Source tags as in
the research file: A = Autodesk help / Learn / AU, F = forum, T = tutorial or exported report,
G = guess (the SciForge choice when the sources are silent).

### Behaviour

| # | Fusion behaviour | SciForge | Src |
|---|---|---|---|
| S1 | Workspace drop-down lists Simulation; the same design's toolbar, browser and canvas switch | Workspace button > Simulation: SETUP / RESULTS replace the design's tabs, the button says SIMULATION | A[71] |
| S2 | No design timeline in Simulation | The timeline hides while SIMULATION shows, comes back in DESIGN | G (mem), research 1.4 |
| S3 | First visit without a study: the New Study dialog opens by itself; with studies the active one | Same (the last active study, else the newest) | T[104]; G |
| S4 | Each open document keeps its own workspace | Each design remembers it; switching design tabs shows that design's workspace; closing a design forgets it; a reopened design opens in DESIGN | G (mem) |
| S5 | Leaving: Design in the same drop-down; studies and results stay | Same; the command or sketch open is finished first (as when a command starts), the selection is cleared | A[71] A[65] |
| S6 | New Study: study types as pictures, the picked one described, Settings gear, Create Study | Tiles of all 11 types; Static Stress available; the others greyed "Not in SciForge yet"; the gear opens Study Settings for the new study; the limits sentence (linear, isotropic, a guide) | A[79] A[6]; outline 7.18 |
| S7 | Study named "Study 1 - Static Stress", renamed in the browser | Same (the engine numbers it); F2 / Rename in the browser | G (mem) |
| S8 | Study Settings: General (Remove rigid body modes, off), Mesh (Average Element Size 10 %, Parabolic, curved, turn angle, adjacent ratio, aspect ratio, minimum size, Scale Mesh Size Per Part), Adaptive Mesh Refinement (None), contacts tolerance | All of these, plus an absolute element size and "keep the results in the design file"; Adaptive Mesh Refinement greyed (engine not wired yet, see gaps) | A[6] A[37] A[39] T[107] |
| S9 | Study Materials: a row per body, "(Same as Model)" default, a material for this study only, safety factor on Yield (default) or Ultimate; double-click shows the properties | A row per body with In Study, the model's material and the study material; the properties used (E, nu, density, yield, UTS) shown, saying which value SciForge filled in where FreeCAD's card had none; the basis is per study (see gaps) | A[9] A[29] A[30] |
| S10 | Structural Constraints: one dialog, Type Fixed / Pin / Frictionless / Prescribed Displacement | Same; picks with the type's filter (Pin: round faces only); Fixed Ux Uy Uz toggles (on), Pin Radial / Axial on, Tangential off, Prescribed Displacement per-axis values | A[7] A[13] A[14] A[15] A[16] |
| S11 | Structural Loads: Force (Normal / Vector, Flip, Force Per Entity), Pressure, Moment, Bearing Load, Remote Force | Same; Vector force typed as Fx, Fy, Fz (Normal and Vector carry the values over); Moment Normal / Vector with per entity; Bearing direction; Remote Force point; every value field takes a unit (100 N, 0.5 kN, 2 MPa, 10 lbf, 2 N m) | A[18] A[19]-A[23] |
| S12 | Glyphs on the model for each load and constraint | Cones (Fixed), pins (Pin), balls (Frictionless), arrows (Force, Displacement, Bearing), short arrows (Pressure), a curved arrow (Moment), a big arrow (gravity), green dots (local mesh); same screen size at any zoom; never picked; only in SIMULATION; a lighter live preview while picking | G (mem) |
| S13 | Gravity: off in a new study; Toggle Gravity On / Off; Edit Gravity (Normal from a face or edge, or angles; Flip) | LOADS > Toggle Gravity On/Off (a tick shows the state); the browser's Gravity row: Edit Gravity (on/off, Vector or Normal from a flat face / straight edge, Flip, magnitude in m/s^2) | A[26] A[28] |
| S14 | Automatic contacts made bonded at solve time; Automatic Contacts dialog (tolerance, Generate); Contact Manager | Same (0.1 mm); Generate lists the bonded pairs with their gap; Contact Manager is a read-only list; Manual Contacts and connectors greyed | A[33] A[34] A[35]; T[106] |
| S15 | Mesh made at solve time; Generate Mesh to preview; Local Mesh Control (faces / edges / Body Selection, Fine-Coarse slider or Length) | Same; Generate Mesh shows the mesh on the model (DISPLAY > Show Mesh toggles it), its node and element counts on the Mesh row; Local Mesh Control with Body Selection, slider and Length (starts at the study's element size) | A[37] A[38] |
| S16 | Pre-check: a traffic-light icon (green / yellow / red) and a list of messages | The Pre-check button's icon follows the active study (green, yellow, red), its tooltip and the Pre-check list give the engine's sentences; Solve from the list | A[42] F[92] |
| S17 | Solve dialog: the studies, "Solve 1 Study"; Job Status with progress per phase, Cancel during some phases | The design's studies with their light, ticked, "Solve N Studies"; it says it solves on this computer; a red study is refused with its sentences; progress by stage, elapsed time, Cancel at any stage; studies solved one after another; the window stays usable | A[43] A[44]; **(SciForge)** local |
| S18 | Results open on the RESULTS tab when the solve ends | Handed over to `simulation_results_ui.show(study)` (sim-results), else the RESULTS tab | A[8]; G (mem) |
| S19 | Out of date when the design or study changed after the solve | "Results (out of date)" row, yellow; a setup change made during the solve also makes it out of date | F[85] A[65] |
| S20 | MANAGE: Settings, Local Mesh Control, Load Case Attributes | Same; Load Case Attributes lists every load and constraint with place, size, direction and status (OK / lost / suppressed) | A[28] A[49] |
| S21 | DISPLAY: DOF View | Selects the bodies nothing holds and says which | F[92] |
| S22 | Browser: Simulation Model, the study (Study Materials, Load Case with Constraints and Loads and Gravity, Contacts, Mesh, Results); Clone Study; Edit / Suppress / Delete; double-click | Same tree (bodies under the model, with Exclude from Study / Include in Study); Activate, Settings, Clone Study, Rename, Delete on a study; Edit (bold), Suppress / Unsuppress, Rename, Delete on an item; double-click: activate a study, edit an item, open Study Materials / Gravity / Contact Manager / Mesh settings / Results; Delete and F2 keys | A[28] A[46] A[45]; G (mem) |
| S23 | Undo | Adding, editing, deleting, suppressing, renaming items; settings; materials; gravity; studies (new, clone, delete): one undo step each; Esc / Cancel leave nothing; a solve or a mesh is never in the undo history | outline 2.2 |
| S24 | A model not held enough fails | CalculiX's "singular" error turns into the engine's sentence; a solve that "worked" with the model moving more than half its size (a mechanism) is not shown as results: the progress says it is not held enough | A[41]; outline 0.8 |

### Scenarios (real clicks, `SciForgeTests/gui/scenarios/sim_setup_*.py`)

| Scenario | Paths |
|---|---|
| `sim_setup_bracket` | enter, New Study, Fixed at the holes, Force on the arm, Pre-check green, Solve, results handed over, leave (tabs, timeline, browser, nothing leaked), enter again |
| `sim_setup_dialogs` | Esc on New Study, the gear's settings, a refusal (nothing holds), Esc / Cancel in the item dialogs, Study Materials + undo / redo, Settings + undo, gravity on, Edit Gravity, contacts, Load Case Attributes, undo / redo of a constraint |
| `sim_setup_browser` | solve, Edit Load from the browser, out of date, solve again from the Results row, double-click edit + Cancel, Suppress / Unsuppress, F2 rename + undo, Delete key + undo, Clone Study, Activate, delete a study, a design change makes it out of date |
| `sim_setup_documents` | two glued bodies (Automatic Contacts, Contact Manager), DOF View, Exclude / Include, solve with a result per body, design tabs keep their workspaces, save / close / reopen with the study and results |
| `sim_setup_kinds` | every constraint and load type (Pin filter and defaults, Moment with a unit, vector force components, pressure flip, prescribed displacement), Local Mesh Control with Body Selection, Generate Mesh + Show Mesh, Cancel a solve |
| `sim_setup_workspace` | entering with a sketch open, leaving with a dialog open, Esc, a second study, Solve dialog with two studies (one refused), undo while results show, leaving from RESULTS |
| `sim_setup_components` | an empty design, moved components, a model held by one edge (not held enough) |

### Known gaps

- **Simplify** (simulation models, Remove Features, Replace with Primitives) is greyed: a study
  uses the design as it is; a body is left out with Study Materials' In Study or the browser's
  Exclude from Study.
- **Several load cases** per study are not built: each study has one "Load Case 1" (clone the
  study instead). Load case clone / activate are absent.
- **Safety factor basis per body**: Fusion chooses it per row of Study Materials; the engine
  keeps one basis per study, so the dialog has one Safety Factor choice under the table.
- **Adaptive Mesh Refinement**: the engine stores its settings but does not run it yet
  (sim-core); the tab is greyed with the reason.
- **Manual contacts** (Separation, Sliding, Rough, Offset Bonded), Bolt and Rigid Body
  Connectors, Linear / Angular Global Load, Point Mass: greyed (CalculiX contact is nonlinear;
  outline 7.18 keeps Static Stress linear).
- **Force direction by Angle** and **Limit Target** are not in the Structural Loads dialog
  (Normal and Vector only); Remote Moment and Hydrostatic Pressure are not listed.
- **Units follow the engine** (N, MPa, N mm, mm): a value typed with another unit (lbf, psi,
  N m, in) is converted, but a design in inches still shows metric values.
- **Repair** (Fusion's button for a study with serious input errors) and the Job Status
  history of earlier solves are not built.
- **Glyph look**: SciForge's own (Fusion's are unknown here; research 3.12 is G); they cannot
  be checked on screen in the sandbox (xvfb draws no 3D), only counted.
- **Engine issues found while building the UI** (reported to sim-core in
  `docs/sciforge/sessions/beta3-sim-ui.md`): a whole-body pick was dropped by the engine's link
  list (the UI keeps it: `simulation_panels._keep_whole_bodies`); the result summary keys bodies
  by label, so two components' "Body1" share one entry; a model held by one edge solved with
  1e10 mm of movement instead of failing (the UI refuses to show it); the result fingerprint is
  taken when the solve ends, so the UI records the one from its start
  (`simulation_solve_dialog._keep_out_of_date`).

## Results

(builder sim-results)

## Benchmarks

(builder sim-core)

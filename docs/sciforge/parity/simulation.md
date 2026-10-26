# Parity spec: Simulation workspace, Static Stress (beta 3, outline 7.18)

Fusion's Simulation workspace limited to its Static Stress study. Fusion's behaviour with
sources: `docs/sciforge/dev/research/fusion-simulation.md`. Plan: `docs/sciforge/plan-beta3.md`.
SciForge solves on the person's own computer (FreeCAD's FEM module: Gmsh meshes, CalculiX
solves); Fusion has solved Static Stress only in Autodesk's cloud since September 2022, so local
solving with Cancel at any time is a deliberate **(SciForge)** difference.

Each builder writes only its own section (beta3-common.md).

## Engine

(builder sim-core, branch `sf/sim-core`.) The study, its items, the solve and the numbers, under
the SETUP and RESULTS tabs: `sciforge/simulation_core.py` (rules, no FreeCAD; unit tests
`SciForgeTests/unit/test_simulation_core.py`), `sciforge/simulation.py` (the document side:
studies in the design, FreeCAD's FEM objects, Gmsh / Netgen and CalculiX in a background
thread), the AI tools (`sciforge/ai/catalog/simulate_tools.py`,
`sciforge/ai/actions/simulate_actions.py`), the accuracy benchmarks and engine checks
(`SciForgeTests/headless/sim_benchmarks.py`, `run_tests.sh --only sim`, also in `base`).
Source tags as in the research file: A = Autodesk help / Learn / AU, F = forum, T = tutorial
or exported report, G = guess (SciForge's choice where the sources are silent).

### Behaviour

| # | Fusion behaviour | SciForge engine | Src |
|---|---|---|---|
| E1 | Static Stress: linear, small deflections, elastic material, loads that do not change, no inertia | CalculiX linear static (`*STATIC`, geometric nonlinearity off); the limits sentence is in the New Study description and the AI tools' text | A[1] A[2] |
| E2 | Study Materials: "(Same as Model)" = the body's physical material; another material for this study only; E, Poisson's ratio, density, yield and ultimate strength | Same; FreeCAD cards that lack a value a stress study needs (Steel-Generic's yield strength, Aluminum-Generic's, PMMA / PEEK's Poisson's ratio) are filled from handbook values and marked `filled`; a material without E or Poisson's ratio is refused; gravity on a material without density is refused | A[9] A[29] |
| E3 | Safety factor = yield / von Mises (default) or ultimate / 1st principal, shown capped at 15 | Same, per node, each body with its own material's strength (two glued materials: each its own) | A[30] F[89] |
| E4 | Fixed: Ux, Uy, Uz on by default; turning some off is a roller | Same: a `*BOUNDARY` per held direction on every node of the faces / edges / corners | A[13] A[11] |
| E5 | Pin: cylindrical faces; Radial + Axial on, Tangential off | Same; radial, axial and tangential are node equations along each node's own radial / axial / tangential direction (`*EQUATION`), so the hole keeps its size and place but may turn | A[14] F[91] |
| E6 | Frictionless: no movement normal to the face, free to slide | Same, on any face (each node's own normal): symmetry planes, smooth supports; benchmark: half model = full model within 0.2 % | A[15] |
| E7 | Prescribed Displacement: Ux / Uy / Uz values | Same (`*BOUNDARY` with the value); its reaction is the force it takes (benchmark within 0.6 %) | A[16] |
| E8 | Force: normal to a face by default, or a vector; several picks share the total by area; Force Per Entity gives each the whole force; on faces it becomes an equivalent pressure | Same; the node shares are FreeCAD's consistent ones for a uniform load (6-node triangles: corners 0, mid-sides a third), normalised so the total is exact; edges by length, corners equally | A[19] A[18] |
| E9 | Pressure: normal to the faces | Same (FreeCAD's element-face pressure, exact on curved faces); negative or Flip pulls | A[20] |
| E10 | Moment: about the face normal or a vector; several faces | Spread over the picked faces as forces growing with the distance from their middle (the faces turn as a whole but stay deformable, like a distributing coupling); several faces share it about their common middle unless per entity; benchmark: shaft torsion within 0.2 % | A[21] A[18]; how several faces share it is G (research 10 Q8) |
| E11 | Bearing Load: cylindrical faces, pushes only, parabolic | Same: on the half of the faces that looks against the load, a parabola over the angle, scaled so the total along the load is exact; benchmark: the reaction balances it within 0.05 % | A[22]; Sim Mech A[83] |
| E12 | Remote Force: a force acting from a point, carried to the faces | The force plus the moment of its lever arm, spread like E10; benchmark: cantilever tip within 0.7 % of beam theory with the lever | A[23] |
| E13 | Gravity: off by default, standard gravity, a direction | Same (9806.65 mm/s2; FreeCAD's self weight, `*DLOAD GRAV`); benchmark: a hanging bar within 0.3 % | A[26] A[24] |
| E14 | Remove rigid body modes: for a model held by nothing whose loads balance | Each piece that no constraint holds is held statically determinate at three of its nodes (the 3-2-1 rule), so balanced loads give no reaction; the pre-check warns as research 9.6 says; benchmark: a plate with a hole pulled at both ends | A[40] A[6] |
| E15 | Automatic contacts: bodies within 0.1 mm bonded at solve time | Same: the study's solids are split where they touch or come within the tolerance (FreeCAD's general fuse with that fuzzy value), so the mesh is shared and they are glued; `contacts(study)` lists the pairs; benchmark: two materials 0.05 mm apart in series within 0.3 % | A[33] A[34] T[106] T[107] |
| E16 | Manual contact types: Offset Bonded, Separation, Sliding, Rough, No Contact | Refused with a sentence (`simulation_core.CONTACT_TYPES`, `CONTACT_NOT_AVAILABLE`): they make the solve nonlinear (see Known gaps) | A[33] |
| E17 | Mesh: parabolic tetrahedra, average size 10 % of the model size, curved elements, minimum size, turn angle, adjacent size ratio, aspect ratio, Scale Mesh Size Per Part | Gmsh: second order, size = % of the bounding-box diagonal (or a length), curved mid-side nodes (Gmsh's high-order optimisation straightens any that turn inside out; if CalculiX still finds one, the mesh is made again straight-sided and a note says so), the minimum, elements per turn = 360 / turn angle, local controls grow at the adjacent ratio, the statistics count elements over the aspect ratio; per part: each body's own size (Gmsh size fields); one Gmsh thread, so the same study always gives the same mesh | A[37] T[107]; Inventor A[81] |
| E18 | Generate Mesh before solving; mesh made at solve time otherwise | `Job(study, mesh_only=True)` keeps the mesh next to the last results (`mesh_object`, `mesh_summary`: nodes, elements, smallest / largest element edge, worst aspect ratio, out of date) | A[38] |
| E19 | Local Mesh Control: faces / edges / a body, one size per control, blends into the global size | Same (a study item of category "mesh"; Gmsh Distance + Threshold fields, a Constant field for bodies) | A[38] |
| E20 | Adaptive mesh refinement: None by default; Low to High or custom (number of refinements, convergence tolerance %, portion of elements refined %, the result judged); convergence plots | Same settings (`adaptive`: level none / low (2 solves, 10 %, 10 %) / medium (4, 5 %, 10 %) / high (6, 2 %, 15 %) / custom; result von Mises, displacement, 1st or 3rd principal): solve, halve the size of the elements where the result changes the most across them (a Gmsh post-processing view as the size field), solve again, until the extreme changes by less than the tolerance or the solves are used up; every pass is kept in the summary (the convergence plot's data) and a note gives the values; engine check: the plate with a hole without a local control goes from 8.0 % off Kt to 4.1 % | A[39] A[76] A[71] |
| E21 | Pre-check: green / yellow / red with messages; rigid body motion is the classic failure | The sentences of research 9.6 and more: a piece held but not completely is named with how it could still move ("could still turn about an axis along Y through (10, 5, 5)"), found before meshing from the constraints alone; bodies that would fly away; overlapping bodies; a face constrained twice; picks that are gone; gravity without density | A[42] A[41] F[92]-F[95] |
| E22 | A load or constraint whose faces were removed is flagged | A pick FreeCAD loses after an edit ("?Face5") is found again by its shape (the same face, all its pieces, or where it moved) and the study solves; only a face that is really gone is refused | A[28] |
| E23 | Solve: Job Status with phases; Cancel during some phases | Stages model, mesh, input, solve, results; Gmsh, Netgen and CalculiX in a background thread; Cancel at any stage stops the program; a failed or cancelled solve keeps the last results and leaves no objects or temporary files; nothing a solve makes is in the undo history | A[43] A[44]; **(SciForge)** local and always cancellable |
| E24 | (Fusion meshes in the cloud) | Gmsh fails: Netgen (FreeCAD's) meshes the same model in a FreeCAD of its own, in the background, and a note says so; both fail: a sentence naming the bodies of the faces Gmsh reported | **(SciForge)** |
| E25 | Results: von Mises, principal, components, displacement, strain, reaction force | Every node's values (FreeCAD's result object), the safety factor per node, min / max with where, per body, and the reaction force of every constraint (CalculiX's `*NODE PRINT ... TOTALS=ONLY`) | A[48] A[58] |
| E26 | Results out of date when the design or study changed | A fingerprint of the bodies' shapes and places, the settings, materials and items | F[85] A[65] |
| E27 | Results kept with the design (in Fusion's cloud) | Saved in the design file and back after reopening; Keep results in the file off keeps only the numbers (about 10 MB less per 25 000 nodes) | G |
| E28 | CalculiX's own messages | Sentences: not held enough, distorted elements, constraints that cannot both hold, out of memory, a material problem; a solve that "worked" while moving the model by more than its own size is refused as not held enough | G |

### AI tools

`create_study`, `add_constraint`, `add_load`, `local_mesh_control`, `set_study_material`,
`study_settings`, `precheck_study`, `solve_study`, `study_results` (min / max / where per result
and per body, reactions, and the verdict "Lowest safety factor 1.27 at (6.121, 26.13, 10) mm on
Body1: below 2."), `delete_study`; picks by the same selectors as every other tool; the recipe
`docs/ai/recipes/static-stress.md` (a bracket held at its holes, 1 kN, solve, thicken, solve
again) runs in the docs runner.

### Known gaps (engine)

- **Contact types other than Bonded** (Offset Bonded, Separation, Sliding, Rough, No Contact):
  refused with a sentence. They are nonlinear: CalculiX solves contact as a nonlinear analysis
  with penalty stiffness and increments, which needs tuning per model to converge; a linear
  Static Stress study cannot express "may open or slide". Not attempted in beta 3 (no reliable
  default could be proven in the time).
- **Several load cases in one study**: not built (one load case per study; clone the study for
  another set of loads, as Fusion users often do). CalculiX can solve several `*STEP`s; the
  study items have no load case yet.
- **Hydrostatic pressure, Remote Moment, Linear / Angular Global Load, Point Mass, Remote
  constraint, bolt connectors**: not built (research 9.1 "Later"). A remote moment is the same
  as a Moment on the faces for a deformable link.
- **Moment on several faces**: Fusion's sources disagree (shared vs per face, research 10 Q8);
  SciForge shares it about the faces' common middle by default and offers per entity.
- **Mesh settings without a Gmsh equivalent**: the adjacent size ratio only shapes how local
  controls grow back; the aspect ratio is reported (worst element, how many over the limit),
  not enforced while meshing (Gmsh optimises quality its own way).
- **Stress at a fixed edge**: a fixed constraint is perfectly rigid, so the stress right at its
  edge grows as the mesh gets finer (a singularity, the same in Fusion). The recipe explains it.

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
| S8 | Study Settings: General (Remove rigid body modes, off), Mesh (Average Element Size 10 %, Parabolic, curved, turn angle, adjacent ratio, aspect ratio, minimum size, Scale Mesh Size Per Part), Adaptive Mesh Refinement (None), contacts tolerance | All of these, plus an absolute element size and "keep the results in the design file"; Adaptive Mesh Refinement: None / Low / Medium / High (their numbers shown) / Custom (refinements, convergence tolerance, portion refined, the result watched) | A[6] A[37] A[39] T[107] |
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
| `sim_setup_glyphs` | the glyphs rendered off screen: drawn, hidden on request, same screen size after a zoom, gone in DESIGN |

### Known gaps

- **Simplify** (simulation models, Remove Features, Replace with Primitives) is greyed: a study
  uses the design as it is; a body is left out with Study Materials' In Study or the browser's
  Exclude from Study.
- **Several load cases** per study are not built: each study has one "Load Case 1" (clone the
  study instead). Load case clone / activate are absent.
- **Safety factor basis per body**: Fusion chooses it per row of Study Materials; the engine
  keeps one basis per study, so the dialog has one Safety Factor choice under the table.
- **Manual contacts** (Separation, Sliding, Rough, Offset Bonded), Bolt and Rigid Body
  Connectors, Linear / Angular Global Load, Point Mass: greyed (CalculiX contact is nonlinear;
  outline 7.18 keeps Static Stress linear).
- **Force direction by Angle** and **Limit Target** are not in the Structural Loads dialog
  (Normal and Vector only); Remote Moment and Hydrostatic Pressure are not listed.
- **Units follow the engine** (N, MPa, N mm, mm): a value typed with another unit (lbf, psi,
  N m, in) is converted, but a design in inches still shows metric values.
- **Repair** (Fusion's button for a study with serious input errors) and the Job Status
  history of earlier solves are not built.
- **Glyph look**: SciForge's own (Fusion's are unknown here; research 3.12 is G). xvfb shows no
  3D on the screen, but FreeCAD's off-screen picture does: `sim_setup_glyphs` renders the view
  with and without them and checks their colours.
- **Engine issues found while building the UI** (reported to sim-core in
  `docs/sciforge/sessions/beta3-sim-ui.md`): a whole-body pick was dropped by the engine's link
  list (the UI keeps it: `simulation_panels._keep_whole_bodies`); the result summary keys bodies
  by label, so two components' "Body1" share one entry; a model held by one edge solved with
  1e10 mm of movement instead of failing (the UI refuses to show it); the result fingerprint is
  taken when the solve ends, so the UI records the one from its start
  (`simulation_solve_dialog._keep_out_of_date`).

## Results

(builder sim-results, branch `sf/sim-results`, 2026-10-26/27.) Fusion's RESULTS tab of a
Static Stress study. Files (`src/Mod/SciForge/sciforge/`):

| File | What it holds |
|---|---|
| `simulation_results_core.py` | the rules, no FreeCAD / Qt, unit tested: Fusion's result list (type + component), units, the colour map texture and legend, the safety factor targets and their sentence, deformation and animation, the outer surface of the tetrahedral mesh (10-node faces split in 4, facing out; mesh and outline edges), a ray against it (probes), a level set through it (the slice plane and the iso-surface, in numpy), a point found in it with its weights (Point Probes), Solver Data's rows, the HTML report |
| `simulation_results.py` | the document side, no Qt: a study's results as arrays (kept per solve), strain components, values and displacement at any point inside the part, Results Details' numbers, the report's data |
| `simulation_results_view.py` | the drawing: SciForge's own Coin nodes (never document objects), the legend, the tags and the animation bar floating over the 3D view |
| `simulation_results_ui.py` | when the results show (the RESULTS tab watcher), `show(study)` for sim-ui's Solve dialog, `hide()`, Compare, the 22 commands |
| `simulation_results_panels.py` | Surface Probes, Point Probes, Slice Plane, Iso-surface, Results Details, Legend Min/Max, Compare, Report, Reaction Force, Solver Data, a solve from out-of-date results when sim-ui's Solve is missing |

Shared files: `ribbon_config.py` (the RESULTS tab's groups: commands, icons, ticks),
`tools/sciforge/icons_simresults.py` (22 icons), `docs/sciforge/parity-checklist.md`
(regenerated). No FreeCAD core change. Sources as in the research file (**A** Autodesk, **F**
forum, **T** tutorial / exported report, **G** guess); four WebSearch excerpts this session:
Autodesk's Results details help (three states against a Lower and an Upper target, "reducing the
Upper Target can ... give a false positive"), an Autodesk Learn video (default targets "three
... lower limit and six is the upper limit"), Autodesk's legend help (result drop-down, a second
drop-down for direction or type, units, legend options with colour bands), guided results
("suggestions for steps you can take"); later: Autodesk's Point probes help (probes "can be
relocated internally", "global coordinates", the first place "picked from any visible surface
including slice planes and iso-surfaces", "fixed in the global coordinate system, however the
displacement is honored in the scene") and an AU handout (moved "using the grips or x, y and z
inputs"); no Fusion source on the iso-surface's dialog was found (Autodesk Flow Design's iso
surface: a Value slider over the result, an opacity).

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
| RESULT TOOLS: Compare (up to 4 studies; the canvas splits into views; Finish closes it; no probes in the legacy Compare) | Compare: tick 2 to 4 of the design's studies with results; they show **side by side in the one 3D view** (each moved beside the one before, across the way they are thinnest: two beams lie side by side), each with a tag (study, min, max), on **one colour scale** and one deformation scale (the same colour is the same value; a bigger bend looks bigger: SciForge's choice); the legend's result and unit, DEFORMATION and Show Mesh work on all; probes, slices and the rest rest meanwhile; **Finish Compare** under the legend, Compare again, SETUP or another design end it | A[61] F[86], G |
| DEFORMATION: Undeformed, Actual, Adjusted x 0.5, Adjusted, x 2, x 5 | Same, ticked in the menu; also in Results Details | A[51] |
| DISPLAY: Mesh, Wireframe | Show Mesh (element edges); **Undeformed Model** (the unloaded shape see-through: the web viewer's "Show Undeformed model") instead of Wireframe; **Loads and Constraints** (sim-ui's glyphs on the results, off by default) | A[49] A[68], G |
| INSPECT: Surface Probes (hovering shows the value under the mouse, a click places a tag; as many as wanted) | The value under the mouse follows it over the result (a lighter tag, gone off the model); a click: a tag with the value of the node under the mouse; as many as wanted; they read the result chosen in the legend; Remove (the one chosen in the list), Clear All; Esc / Close keeps them | A[55], web excerpt |
| INSPECT: Show Min/Max | Toggle (on by default) | A[80] A[57] |
| INSPECT: Reaction Force | A table: the force each constraint takes (X, Y, Z, total), from the solve (sim-core's `summary["reactions"]`) | A[48] A[58] |
| INSPECT: Slice Plane (legacy: Shaded, Mesh Lines, Vectors, Clipping; online: Section, Slice) | A plane across X, Y or Z, or **parallel to a face clicked on the result** (any direction; half way across the part, the half away from the face kept so the cut looks at you), position (field, slider, or the plane's drag arrow), Flip; **Cut the result away** (clipping, the cut face coloured with the values inside) or **Slice alone** (the cut face inside the whole result drawn see-through); a probe on the cut face reads the value inside; OK / Cancel / Remove Slice | A[56] |
| INSPECT: Point Probes (values inside the part; first placed on any visible surface, slice planes and iso-surfaces included; moved by grips or X, Y, Z; global coordinates, drawn with the displacement) | Point Probes: a click on the result, a slice's cut face or the iso-surface puts a probe there (inside surfaces first when the result is see-through); the value under the mouse while it moves; a table P1, P2... with X, Y, Z on the unloaded part (typed to move it, a unit allowed: "0.5 in") and the value of the result in the legend; outside the part it says so; the tag (a diamond) moves with the part as drawn (Deformation, Animate); Remove, Clear All; Close keeps them; the value is interpolated in the mesh (a node's own value at a node) | A[55], web excerpts |
| INSPECT: Iso-surface | Iso-surface: the surface inside the part where the result shown has one value, in the legend's colour of that value, the result see-through around it (cut by a clipping slice too); value field (legend unit) and slider between the result's lowest and highest (half way to start); the legend's result moves it to that result; a value nothing reaches says so; OK / Cancel (puts back what was there) / Remove Iso-surface | G (Flow Design's iso surface as the model) |
| INSPECT: Solver Data | Solver Data: when the study was solved and how long each step took (model, mesh, solver input, CalculiX, reading the results), the safety factor's basis; the mesh: nodes, degrees of freedom (3 per node), elements, order, element size, smallest / largest element edge, worst aspect ratio, elements over the limit, mesher; the adaptive refinement's solves; the solve's messages; Copy (as text) | A[57]; contents G |
| MANAGE | sim-ui's (shared with SETUP) | A[49] |
| FINISH RESULTS | Finish Results | G (mem) |

### Known gaps (Results)

- **Compare in split views** (Fusion splits the canvas, one view and legend per study): SciForge
  puts the studies side by side in one view on one shared colour scale instead (one camera, so
  they turn together; the same colour is the same value).
- **Saving the animation as a video (.webm)**: not built; the 3D view can be captured frame by
  frame (`saveImage`) but SciForge has no video encoder in the bundle.
- **Slice plane on a construction plane** (a document plane), the **Vectors** and **Mesh Lines**
  slice styles: the plane is across X, Y or Z or parallel to a face of the result.
- **The online viewer's threshold sliders** (a range of interest dragged on the legend): Legend
  Min/Max (typed values) covers the same need.
- **Contact pressure / force results**: bodies are bonded (glued), which has no contact pressure;
  CalculiX's contact output is not requested.
- **Shear strain components**: CalculiX's shear strains are tensor values (half the engineering
  shear strain); left out rather than shown with an uncertain meaning. Normal and principal
  strains are shown.
- **Load case selector**: one load case per study.
- **Report**: no logo, cover picture, approvers or revision fields; one study per report.
- **Point Probes' grips**: a probe is moved by typing its X, Y, Z, not by dragging handles in the
  3D view.
- **Iso-surface**: one at a time, of the result shown in the legend, in one colour (Fusion's
  own colouring of iso-surfaces was not found); several values at once are not offered.
- **Solver Data**: CalculiX's own output (its log) is not kept by the engine, so it is not shown;
  the timings, mesh statistics and the engine's messages are.
- **The legend's place** (top left of the 3D view) and the safety factor's colours (0 .. 15,
  red low) are guesses (research section 10, questions 1 and 6): a screenshot of Luca's Fusion
  would settle them.

## Benchmarks

(builder sim-core)

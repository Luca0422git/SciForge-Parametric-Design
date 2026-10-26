<!-- A copy of docs/sciforge/parity/simulation.md for AI models, made by tools/sciforge/make_ai_docs.py: edit the original, then run the script. -->

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
| S11 | Structural Loads: Force (Normal / Vector, Flip, Force Per Entity), Pressure, Moment, Bearing Load, Remote Force | Same; Vector force typed as Fx, Fy, Fz (Normal and Vector carry the values over); Moment Normal / Vector with per entity; Bearing direction (a default that runs along the picked hole's axis is turned across it, and a direction along the axis is refused with a sentence); Remote Force point; every value field takes a unit (100 N, 0.5 kN, 2 MPa, 10 lbf, 2 N m) | A[18] A[19]-A[23] |
| S12 | Glyphs on the model for each load and constraint | Cones (Fixed), pins (Pin), balls (Frictionless), arrows (Force, Displacement, Bearing), short arrows (Pressure), a curved arrow (Moment), a big arrow (gravity), green dots (local mesh); same screen size at any zoom; never picked; only in SIMULATION; a lighter live preview while picking | G (mem) |
| S13 | Gravity: off in a new study; Toggle Gravity On / Off; Edit Gravity (Normal from a face or edge, or angles; Flip) | LOADS > Toggle Gravity On/Off (a tick shows the state); the browser's Gravity row: Edit Gravity (on/off, Vector or Normal from a flat face / straight edge, Flip, magnitude in m/s^2) | A[26] A[28] |
| S14 | Automatic contacts made bonded at solve time; Automatic Contacts dialog (tolerance, Generate); Contact Manager | Same (0.1 mm); Generate lists the bonded pairs with their gap; Contact Manager is a read-only list; Manual Contacts and connectors greyed | A[33] A[34] A[35]; T[106] |
| S15 | Mesh made at solve time; Generate Mesh to preview; Local Mesh Control (faces / edges / Body Selection, Fine-Coarse slider or Length) | Same; Generate Mesh shows the mesh on the model (DISPLAY > Show Mesh toggles it; never drawn over the design in DESIGN, nor for another study), its node and element counts on the Mesh row; Local Mesh Control with Body Selection, slider and Length (starts at the study's element size) | A[37] A[38] |
| S16 | Pre-check: a traffic-light icon (green / yellow / red) and a list of messages | The Pre-check button's icon follows the active study (green, yellow, red), its tooltip and the Pre-check list give the engine's sentences; Solve from the list | A[42] F[92] |
| S17 | Solve dialog: the studies, "Solve 1 Study"; Job Status with progress per phase, Cancel during some phases; Job Status lists completed and failed solves | The design's studies with their light, ticked, "Solve N Studies"; it says it solves on this computer; a red study is refused with its sentences; progress by stage, elapsed time, Cancel at any stage (only Close once it ended); studies solved one after another; the window stays usable; the progress window also lists this session's earlier solves and meshes with their time and result, and a solved one's row shows its results on a double-click (Fusion's action per completed solve) | A[43] A[44]; **(SciForge)** local |
| S18 | Results open on the RESULTS tab when the solve ends | Handed over to `simulation_results_ui.show(study)` (sim-results), else the RESULTS tab; only when the design is in front in SIMULATION: a person who went on working in DESIGN (or another design) while it solved stays there and is told where the results are | A[8]; G (mem) |
| S19 | Out of date when the design or study changed after the solve | "Results (out of date)" row, yellow; a setup change made during the solve also makes it out of date | F[85] A[65] |
| S20 | MANAGE: Settings, Local Mesh Control, Load Case Attributes | Same; Load Case Attributes lists every load and constraint with place, size, direction and status (OK / lost / suppressed) | A[28] A[49] |
| S21 | DISPLAY: DOF View shows which bodies can still move | A toggle: arrows over the model show each way a piece can still move (three slides and three turns for a piece nothing holds; the slides and turns its constraints leave free for one held in part, e.g. a turn about a held edge, from the engine's not-held analysis); those bodies are selected and named with how they can move; the arrows follow the setup until DOF View is switched off (or the workspace left) | F[92] |
| S22 | Browser: Simulation Model, the study (Study Materials, Load Case with Constraints and Loads and Gravity, Contacts, Mesh, Results); Clone Study; Edit / Suppress / Delete; double-click | Same tree (bodies under the model, with Exclude from Study / Include in Study); Activate, Settings, Clone Study, Rename, Delete on a study; Edit (bold), Suppress / Unsuppress, Rename, Delete on an item; double-click: activate a study, edit an item, open Study Materials / Gravity / Contact Manager / Mesh settings / Results; Delete and F2 keys | A[28] A[46] A[45]; G (mem) |
| S23 | Undo | Adding, editing, deleting, suppressing, renaming items; settings; materials; gravity; studies (new, clone, delete): one undo step each; Esc / Cancel leave nothing; a solve or a mesh is never in the undo history | outline 2.2 |
| S24 | A model not held enough fails | CalculiX's "singular" error turns into the engine's sentence; a solve that "worked" with the model moving more than half its size (a mechanism) is not shown as results: the progress says it is not held enough | A[41]; outline 0.8 |
| S25 | SETUP groups in workflow order (STUDY, SIMPLIFY, MATERIALS, CONSTRAINTS, LOADS, CONTACTS, DISPLAY, MANAGE, SOLVE, INSPECT, SELECT), each with its big button | Same order and members (research 9.2); every group shows a big button; the commands not built (Simplify, Linear / Angular Global Load, Point Mass, Manual Contacts, Bolt / Rigid Body Connector) are greyed with their sentence; original icons for every entry; on / off buttons (Ux, Uy, Uz, Flip Direction, Body Selection) look on when on | A[4]; G (mem) for the order |
| S26 | Every value field takes a unit override; Simulation follows the document's units (Document Settings > Units) | Same: the fields, the browser's texts, Load Case Attributes, Study Materials' properties and the mesh / contact lengths show N, MPa, N mm and the design's length in a metric design (N m in metres), lbf, psi, lbf in and inches in an inch design (lbf ft and feet in feet); a bare number is in the unit shown, a typed unit wins; the engine keeps N, MPa, mm, and a field left unchanged keeps its exact value | A[23] A[67] F[99] |
| S27 | In Simulation the right-click marking menu offers the setup's commands; the design's keys do nothing (the design is changed in Design) | The marking menu's ring: Repeat (the last setup command only), Study Materials, Structural Loads, Undo, Structural Constraints, Pre-check, Solve, Settings (OK / Cancel while a dialog is open); its list: Redo, Generate Mesh, Local Mesh Control, DOF View, Hide / Show All / Fit / Look At, orbit centre. Delete, E, Q, F, H, M, J, A, Ctrl+C / Ctrl+V, Ctrl+B and the sketch keys are off while SIMULATION shows (Delete made a Delete Face step from a face picked in the view); the browser still deletes a study item with Delete | G (mem); outline 2.2 |

### Scenarios (real clicks, `SciForgeTests/gui/scenarios/sim_setup_*.py`)

| Scenario | Paths |
|---|---|
| `sim_setup_bracket` | enter, New Study, Fixed at the holes, Force on the arm, Pre-check green, Solve, results handed over, leave (tabs, timeline, browser, nothing leaked), enter again |
| `sim_setup_dialogs` | Esc on New Study, the gear's settings, a refusal (nothing holds), Esc / Cancel in the item dialogs, Study Materials + undo / redo, Settings + undo, gravity on, Edit Gravity (Flip; Normal from a side face), contacts, Load Case Attributes, undo / redo of a constraint |
| `sim_setup_browser` | solve, Edit Load from the browser, out of date, solve again from the Results row (the progress lists the earlier solve), double-click edit + Cancel, Suppress / Unsuppress, F2 rename + undo, Delete key + undo, Clone Study, Activate, delete a study, a design change makes it out of date |
| `sim_setup_documents` | two glued bodies (Automatic Contacts, Contact Manager), DOF View on (both free, six arrows) and off once the base is fixed, Exclude / Include, solve with a result per body, design tabs keep their workspaces, save / close / reopen with the study and results |
| `sim_setup_kinds` | every constraint and load type (Pin filter and defaults, Moment with a unit, vector force components, pressure flip, prescribed displacement), Bearing Load (round faces only, its direction turned across the hole) and Remote Force (its point), Local Mesh Control with Body Selection, Generate Mesh + Show Mesh (not drawn in DESIGN), Cancel a solve |
| `sim_setup_workspace` | entering with a sketch open, leaving with a dialog open, Esc, a second study, Solve dialog with two studies (one refused), undo while results show, leaving from RESULTS, leaving for DESIGN during a solve (not taken back when it ends) |
| `sim_setup_components` | an empty design, moved components, a model held by one edge (DOF View: it can still turn about the edge, one turning arrow; not held enough) |
| `sim_setup_glyphs` | the glyphs rendered off screen: drawn, hidden on request, same screen size after a zoom, gone in DESIGN; DOF View's arrows drawn over the model and gone when it is off |
| `sim_setup_canvas` | the right-click marking menu in SIMULATION (the setup's commands, none of the design's; Structural Loads from the ring; Repeat Structural Loads), Delete and E on a face picked in the view change nothing, the design's ring and keys back in DESIGN |
| `sim_setup_units` | Document Settings > Units: Inch from the SIMULATION browser; a force typed as 50 (lbf) kept as 222.4 N, the browser and Load Case Attributes in lbf, Edit + OK changes nothing, psi, inches for Local Mesh Control, the mesh size and the contact tolerance (0.1 mm kept exactly); back to Millimeter |

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
  (Normal and Vector only: the engine stores a direction as normal or a vector); Remote Moment,
  Hydrostatic Pressure and the Remote constraint are listed greyed with a sentence.
- **Repair** (Fusion's button for a study with serious input errors) is not built; the Job
  Status list of earlier solves covers this session only (Fusion's cloud keeps its jobs).
- **Glyph look**: SciForge's own (Fusion's are unknown here; research 3.12 is G). xvfb shows no
  3D on the screen, but FreeCAD's off-screen picture does: `sim_setup_glyphs` renders the view
  with and without them and checks their colours.
- **Engine issues found while building the UI** (reported to sim-core in
  `docs/sciforge/sessions/beta3-sim-ui.md`): fixed by sim-core since: a whole-body pick dropped by
  the engine's link list, a model held by one edge that "solved" with 1e10 mm of movement (now
  "not held enough" in the pre-check; the UI still refuses such results:
  `simulation_solve_dialog.loose_result`). Still open: the result summary keys bodies by label,
  so two components' "Body1" share one entry; the result fingerprint is taken when the solve
  ends, so the UI records the one from its start (`simulation_solve_dialog._keep_out_of_date`).

## Results

(builder sim-results)

## Benchmarks

(builder sim-core)

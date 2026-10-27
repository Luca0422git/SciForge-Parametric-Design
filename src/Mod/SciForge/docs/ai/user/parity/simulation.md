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
| E3 | Safety factor = yield / von Mises (default) or ultimate / 1st principal, shown capped at 15 | Same, per node, each body with its own material's strength (two glued materials: each its own); on the ultimate basis a node pushed together harder than it is pulled divides by the 3rd principal stress in size (**(SciForge)**: Fusion's help names only the 1st, which is 0 in compression, so a bar crushed at 100 MPa read 15, "very strong"; Rankine's maximum normal stress theory, on the safe side for brittle materials, QA case safety_basis) | A[30] F[89]; compression G |
| E4 | Fixed: Ux, Uy, Uz on by default; turning some off is a roller | Same: a `*BOUNDARY` per held direction on every node of the faces / edges / corners | A[13] A[11] |
| E5 | Pin: cylindrical faces; Radial + Axial on, Tangential off | Same; radial, axial and tangential are node equations along each node's own radial / axial / tangential direction (`*EQUATION`), so the hole keeps its size and place but may turn | A[14] F[91] |
| E6 | Frictionless: no movement normal to the face, free to slide | Same, on any face (each node's own normal): symmetry planes, smooth supports; benchmark: half model = full model within 0.2 % | A[15] |
| E7 | Prescribed Displacement: Ux / Uy / Uz values | Same (`*BOUNDARY` with the value); its reaction is the force it takes (benchmark within 0.6 %) | A[16] |
| E8 | Force: normal to a face by default, or a vector; several picks share the total by area; Force Per Entity gives each the whole force; on faces it becomes an equivalent pressure | Same; the node shares are FreeCAD's consistent ones for a uniform load (6-node triangles: corners 0, mid-sides a third), normalised so the total is exact; edges by length, corners equally. Per Entity counts the person's picks (a picked face the model splits where a glued body touches it is still one entity). **(SciForge)** refused with a sentence: a shared force over picks of different kinds (faces and corners: the total was counted twice; faces and edges: the edges were left out) and along the normal on edges, corners or a curved face (a round face's "normal" was an arbitrary direction; Fusion's help speaks of planar faces); QA engine checks "a force's picks", "along the normal of a curved face" | A[19] A[18]; the refusals G |
| E9 | Pressure: normal to the faces | Same (FreeCAD's element-face pressure, exact on curved faces); negative or Flip pulls | A[20] |
| E10 | Moment: about the face normal or a vector; several faces | About the normal of its first face (a flat one: a curved first face is refused, see E8) or a vector; spread over the picked faces as forces growing with the distance from their middle (the faces turn as a whole but stay deformable, like a distributing coupling); several faces share it about their common middle unless per entity; benchmark: shaft torsion within 1.4 % at the default mesh, 0.2 % finer | A[21] A[18]; how several faces share it is G (research 10 Q8) |
| E11 | Bearing Load: cylindrical faces, pushes only, parabolic | Same: on the half of the faces that looks against the load, a parabola over the angle, scaled so the total along the load is exact; benchmark: the reaction balances it within 0.05 % | A[22]; Sim Mech A[83] |
| E12 | Remote Force: a force acting from a point, carried to the faces | The force plus the moment of its lever arm, spread like E10; benchmark: cantilever tip within 0.7 % of beam theory with the lever | A[23] |
| E13 | Gravity: off by default, standard gravity, a direction | Same (9806.65 mm/s2; FreeCAD's self weight, `*DLOAD GRAV`); benchmark: a hanging bar within 0.3 % | A[26] A[24] |
| E14 | Remove rigid body modes: for a model held by nothing whose loads balance | Each piece that no constraint holds is held statically determinate at three of its nodes (the 3-2-1 rule), so balanced loads give no reaction; the pre-check warns as research 9.6 says; benchmark: a plate with a hole pulled at both ends | A[40] A[6] |
| E15 | Automatic contacts: bodies within 0.1 mm bonded at solve time | Same: the study's solids are split where they touch or come within the tolerance (FreeCAD's general fuse with that fuzzy value), so the mesh is shared and they are glued, each piece keeping its own body and material (the fuse's own history); `contacts(study)` lists the pairs (remembered per geometry: the pre-check runs after every command); benchmark: two materials 0.05 mm apart in series within 0.3 % | A[33] A[34] T[106] T[107] |
| E16 | Manual contact types: Offset Bonded, Separation, Sliding, Rough, No Contact | Refused with a sentence (`simulation_core.CONTACT_TYPES`, `CONTACT_NOT_AVAILABLE`): they make the solve nonlinear (see Known gaps) | A[33] |
| E17 | Mesh: parabolic tetrahedra, average size 10 % of the model size, curved elements, minimum size, turn angle, adjacent size ratio, aspect ratio, Scale Mesh Size Per Part | Gmsh: second order, size = % of the bounding-box diagonal (or a length), curved mid-side nodes (an element that turns inside out at a tight curve, which CalculiX refuses, is made straight-sided before the solve and a note says how many; Gmsh's own repair took minutes on a big part; if CalculiX still refuses one, the mesh is made again straight-sided), the minimum, elements per turn = 360 / turn angle, local controls grow at the adjacent ratio, the statistics count elements over the aspect ratio (a note when they go far past it: a thin wall met by large elements); when Gmsh's surface mesh crosses itself (a wall thinner than the elements) it meshes again with elements half as big, at most twice, with a note; per part: each body's own size (Gmsh size fields); one Gmsh thread, so the same study always gives the same mesh | A[37] T[107]; Inventor A[81] |
| E18 | Generate Mesh before solving; mesh made at solve time otherwise | `Job(study, mesh_only=True)` keeps the mesh next to the last results (`mesh_object`, `mesh_summary`: nodes, elements, smallest / largest element edge, worst aspect ratio, out of date) | A[38] |
| E19 | Local Mesh Control: faces / edges / a body, one size per control, blends into the global size | Same (a study item of category "mesh"; Gmsh Distance + Threshold fields, a Constant field for bodies) | A[38] |
| E20 | Adaptive mesh refinement: None by default; Low to High or custom (number of refinements, convergence tolerance %, portion of elements refined %, the result judged); convergence plots | Same settings (`adaptive`: level none / low (2 solves, 10 %, 10 %) / medium (4, 5 %, 10 %) / high (6, 2 %, 15 %) / custom; result von Mises, displacement, 1st or 3rd principal): solve, halve the size of the elements where the result changes the most across them (a Gmsh post-processing view as the size field), solve again, until the extreme changes by less than the tolerance or the solves are used up; every pass is kept in the summary (the convergence plot's data) and a note gives the values; engine check: the plate with a hole without a local control goes from 8.0 % off Kt to 4.1 % | A[39] A[76] A[71] |
| E21 | Pre-check: green / yellow / red with messages; rigid body motion is the classic failure | The sentences of research 9.6 and more: a piece held but not completely is named with how it could still move ("could still turn about an axis along Y through (10, 5, 5)"), found before meshing from the constraints alone; bodies that would fly away; overlapping bodies; a face constrained twice; picks that are gone; gravity without density; linear elements (much too stiff in bending: a cantilever bends 0.082 mm instead of 0.200 at the default size); a study material no longer in the materials | A[42] A[41] F[92]-F[95] |
| E22 | A load or constraint whose faces were removed is flagged | A pick FreeCAD loses after an edit ("?Face5") is found again by its shape (the same face, all its pieces, or where it moved) and the study solves; only a face that is really gone is refused | A[28] |
| E23 | Solve: Job Status with phases; Cancel during some phases | Stages model, mesh, input, solve, results; Gmsh, Netgen and CalculiX in a background thread; Cancel at any stage stops the program; a failed or cancelled solve keeps the last results and leaves no objects or temporary files; nothing a solve makes is in the undo history | A[43] A[44]; **(SciForge)** local and always cancellable |
| E24 | (Fusion meshes in the cloud) | Gmsh fails: Netgen (FreeCAD's) meshes the same model in a FreeCAD of its own, in the background, and a note says so; both fail: a sentence naming the bodies of the faces Gmsh reported | **(SciForge)** |
| E25 | Results: von Mises, principal, components, displacement, strain, reaction force | Every node's values (FreeCAD's result object), the safety factor per node, min / max with where, per body (two components' "Body1" kept apart: "Body1 (Bracket)"), and the reaction force of every constraint, node by node: CalculiX's force at each held node less the loads acting right at it (gravity of the elements touching it, a pressure or force on a face meeting the held one, worked out from the solver input as CalculiX applies them), a node two constraints hold shared along the directions each holds (CalculiX's totals over node sets left those loads out, 7.4 % of a bracket's weight held at its 6 mm wall plate, and counted a shared node in both sets); the reactions add up to the loads (QA engine checks) | A[48] A[58] |
| E26 | Results out of date when the design or study changed | A fingerprint of the bodies' shapes (size, box, centre of mass) and places (their own and their component's), the settings (not Keep results in the file), materials and items, taken when the solve starts (a change made while it runs leaves the results out of date; a hole moved along a plate or a bar turned about its axis, which keep the size and the box, also do). A study with no bodies chosen takes the design's bodies, shown or hidden (not the tools a Combine used up): turning a body's eye off no longer makes its results out of date or leaves it out of the next solve (it went by the eyes) | F[85] A[65]; research 1.6 |
| E27 | Results kept with the design (in Fusion's cloud) | Saved in the design file and back after reopening; Keep results in the file off keeps only the numbers (about 10 MB less per 25 000 nodes) | G |
| E28 | CalculiX's own messages | Sentences: not held enough, distorted elements, constraints that cannot both hold, out of memory, a material problem; a solve that "worked" while moving the model by more than its own size is refused as not held enough | G |

### AI tools

`create_study`, `add_constraint`, `add_load`, `local_mesh_control`, `set_study_material`,
`study_settings`, `precheck_study`, `solve_study` (the window keeps painting while it solves),
`study_results` (min / max / where per result
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
- **Curved elements at tight curves**: where a coarse mesh would turn a curved element inside
  out, SciForge makes that element straight-sided (Gmsh's own repair, which keeps the faces
  curved, took minutes on a big part). The face there becomes a little flat: a coarse round
  shaft in torsion is 1.2 % too soft at the default mesh (0.01 % at the finer one). A finer mesh
  or a local mesh control on the curved faces avoids it; the solve's notes say how many.
- **Thin walls at the default size**: a 1 mm wall met by 20 mm elements meshes only with
  elements made smaller (automatic, with a note) and stays coarse across the wall: a tube
  pushed along its axis came out 11 % too stiff, with the note that elements are stretched
  131:1. Fusion's mesh settings apply the same way: a smaller Average Element Size or a Local
  Mesh Control on the wall gives the accurate answer (the same tube at 3 %: 1 % off). A wall
  that is not stretched far enough for that note can still be too thin for its elements: a
  2.5 mm clamped plate at the default size bends 10.5 % too little, a 3 mm tube's twist stress
  reads 6.3 % low (QA cases clamped_plate, tube_torsion), so a note now says so whenever a
  body's elements are more than 3 times its wall thickness (2 V / A of the body; 4.5 % off at
  3.4 times, 2.4 % at 2.2 times), and the finer mesh is within 1 %.
- **Big parts**: the window still pauses up to about 3-4 s at a time on a 140 000-node part
  (FreeCAD's tables of the mesh, its result mesh, mapping 120 picked faces onto the model); the
  rest runs in the background. A 300 000-node mesh (20 stacked plates with 500 holes) needs over
  6 GB in CalculiX: the solve's message warns when a mesh is that big.
- **Stress at a fixed edge**: a fixed constraint is perfectly rigid, so the stress right at its
  edge grows as the mesh gets finer (a singularity, the same in Fusion). The recipe explains it.
- **A pressure on a face partly covered by a glued body** acts on the uncovered part only: the
  bodies share their faces in SciForge's model, and the covered part is inside it (1 MPa on a
  100 x 100 mm plate top that a glued 20 x 20 mm block covers: 9600 N; a shared Force on the
  same face spreads over all of it: 10 000 N). Fusion meshes the bodies apart, so its pressure
  would cover the whole face (G). Not changed: a pressure cannot reach a glued interface.

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
| S4 | Each open document keeps its own workspace | Each design remembers it; switching design tabs shows that design's workspace; closing a design forgets it (a SETUP dialog of it ends without touching it, and its undo step is closed: it no longer went on in the next design nor held a solve there; its Solve, Pre-check, Load Case Attributes and Contact Manager windows close with it); a reopened design opens in DESIGN | G (mem) |
| S5 | Leaving: Design in the same drop-down; studies and results stay | Same; the command or sketch open is finished first (as when a command starts), the selection is cleared | A[71] A[65] |
| S6 | New Study: study types as pictures, the picked one described, Settings gear, Create Study | Tiles of all 11 types; Static Stress available; the others greyed "Not in SciForge yet"; the gear opens Study Settings for the new study; the limits sentence (linear, isotropic, a guide) | A[79] A[6]; outline 7.18 |
| S7 | Study named "Study 1 - Static Stress", renamed in the browser | Same (the engine numbers it); F2 / Rename in the browser | G (mem) |
| S8 | Study Settings: General (Remove rigid body modes, off), Mesh (Average Element Size 10 %, Parabolic, curved, turn angle, adjacent ratio, aspect ratio, minimum size, Scale Mesh Size Per Part), Adaptive Mesh Refinement (None), contacts tolerance | All of these, plus an absolute element size and "keep the results in the design file"; Adaptive Mesh Refinement: None / Low / Medium / High (their numbers shown) / Custom (refinements, convergence tolerance, portion refined, the result watched) | A[6] A[37] A[39] T[107] |
| S9 | Study Materials: a row per body, "(Same as Model)" default, a material for this study only, safety factor on Yield (default) or Ultimate; double-click shows the properties | A row per body with In Study, the model's material and the study material; the properties used (E, nu, density, yield, UTS) shown, saying which value SciForge filled in where FreeCAD's card had none; the basis is per study (see gaps) | A[9] A[29] A[30] |
| S10 | Structural Constraints: one dialog, Type Fixed / Pin / Frictionless / Prescribed Displacement | Same; picks with the type's filter (Pin: round faces only); Fixed Ux Uy Uz toggles (on), Pin Radial / Axial on, Tangential off, Prescribed Displacement per-axis values | A[7] A[13] A[14] A[15] A[16] |
| S11 | Structural Loads: Force (Normal / Angle / Vector, Flip, Force Per Entity), Pressure, Moment (Normal / Angle / Vectors), Bearing Load, Remote Force | Same; Vector force typed as Fx, Fy, Fz (Normal, Angle and Vector carry the direction over); Angle: About X, Y, Z (degrees) from the first picked face's normal, turned about X, then Y, then Z (the engine solves the vector it gives; the turns are kept beside it so Edit, Load Case Attributes and Clone Study show Angle again); Moment Normal / Angle / Vector with per entity; Bearing direction (a default that runs along the picked hole's axis is turned across it, and a direction along the axis is refused with a sentence); Remote Force point; every value field takes a unit (100 N, 0.5 kN, 2 MPa, 10 lbf, 2 N m) | A[18] A[19]-A[23] |
| S12 | Glyphs on the model for each load and constraint | Cones (Fixed), pins (Pin), balls (Frictionless), arrows (Force, Displacement, Bearing), short arrows (Pressure), a curved arrow (Moment), a big arrow (gravity), green dots (local mesh); same screen size at any zoom; never picked; only in SIMULATION; a lighter live preview while picking | G (mem) |
| S13 | Gravity: off in a new study; Toggle Gravity On / Off; Edit Gravity (Normal from a face or edge, or angles; Flip) | LOADS > Toggle Gravity On/Off (a tick shows the state); the browser's Gravity row: Edit Gravity (on/off, Vector or Normal from a flat face / straight edge, Flip, magnitude in m/s^2) | A[26] A[28] |
| S14 | Automatic contacts made bonded at solve time; Automatic Contacts dialog (tolerance, Generate); Contact Manager | Same (0.1 mm); Generate lists the bonded pairs with their gap; Contact Manager is a read-only list; Manual Contacts and connectors greyed | A[33] A[34] A[35]; T[106] |
| S15 | Mesh made at solve time; Generate Mesh to preview; Local Mesh Control (faces / edges / Body Selection, Fine-Coarse slider or Length) | Same; Generate Mesh shows the mesh on the model (DISPLAY > Show Mesh toggles it; never drawn over the design in DESIGN, nor for another study), its node and element counts on the Mesh row; Local Mesh Control with Body Selection, slider and Length (starts at the study's element size) | A[37] A[38] |
| S16 | Pre-check: a traffic-light icon (green / yellow / red) and a list of messages | The Pre-check button's icon follows the active study (green, yellow, red), its tooltip and the Pre-check list give the engine's sentences; Solve from the list (greyed when red); a red list also has Repair (see S17) | A[42] F[92] |
| S17 | Solve dialog: the studies, "Solve 1 Study"; Job Status with progress per phase, Cancel during some phases; Job Status lists completed and failed solves | The design's studies with their light, ticked, "Solve N Studies"; it says it solves on this computer; a red study is refused with its sentences and has a **Repair** button next to it, which closes the dialog and takes the person to the first thing to fix, told why: the Edit dialog of a load or constraint that lost its faces, Structural Constraints when nothing holds the model, DOF View when a body is not held, Study Materials for a material that lacks a value or a load on a body left out of the study, else the Pre-check list; progress by stage, elapsed time, Cancel at any stage (only Close once it ended; a cancelled or failed solve shows the stage it stopped at); a body of the study deleted while it solves stops it with a sentence naming the body; setup changes are refused while it solves (told why), Undo still works (the results then come out of date); studies solved one after another; the window stays usable; the progress window (Job Status, also opened any time from SOLVE > Job Status) lists this session's earlier solves and meshes with their time and result, and a solved one's row shows its results on a double-click, its design brought to the front in SIMULATION (Fusion's action per completed solve); the rows name each study from its own design, whichever design is in front | A[42] A[43] A[44]; **(SciForge)** local; what Repair opens is G |
| S18 | Results open on the RESULTS tab when the solve ends | Handed over to `simulation_results_ui.show(study)` (sim-results), else the RESULTS tab; only when the design is in front in SIMULATION: a person who went on working in DESIGN (or another design) while it solved stays there and is told where the results are | A[8]; G (mem) |
| S19 | Out of date when the design or study changed after the solve | "Results (out of date)" row, yellow; a setup change made during the solve also makes it out of date | F[85] A[65] |
| S20 | MANAGE: Settings, Local Mesh Control, Load Case Attributes | Same; Load Case Attributes lists every load and constraint with place, size, direction and status (OK / lost / suppressed) | A[28] A[49] |
| S21 | DISPLAY: DOF View shows which bodies can still move | A toggle: arrows over the model show each way a piece can still move (three slides and three turns for a piece nothing holds; the slides and turns its constraints leave free for one held in part, e.g. a turn about a held edge, from the engine's not-held analysis); those bodies are selected and named with how they can move; the arrows follow the setup until DOF View is switched off (or the workspace left) | F[92] |
| S22 | Browser: Simulation Model, the study (Study Materials, Load Case with Constraints and Loads and Gravity, Contacts, Mesh, Results); Clone Study; Edit / Suppress / Delete; double-click | Same tree (bodies under the model, with Exclude from Study / Include in Study); Activate, Settings, Clone Study, Rename, Delete on a study; Edit (bold), Suppress / Unsuppress, Rename, Delete on an item; double-click: activate a study, edit an item, open Study Materials / Gravity / Contact Manager / Mesh settings / Results; Delete and F2 keys (several rows picked with Ctrl are deleted together, one undo step); a click on a constraint's or load's row lights up what it is on, and a new Structural Constraints / Loads dialog does not start on those faces (only on faces picked in the view); deleting a study whose mesh shows hides it first, so Undo brings it back unshown | A[28] A[46] A[45]; G (mem) |
| S23 | Undo | Adding, editing, deleting, suppressing, renaming items; settings; materials; gravity; studies (new, clone, delete): one undo step each; Esc / Cancel leave nothing; a solve or a mesh is never in the undo history | outline 2.2 |
| S24 | A model not held enough fails | CalculiX's "singular" error turns into the engine's sentence; a solve that "worked" with the model moving more than half its size (a mechanism) is not shown as results: the progress says it is not held enough | A[41]; outline 0.8 |
| S25 | SETUP groups in workflow order (STUDY, SIMPLIFY, MATERIALS, CONSTRAINTS, LOADS, CONTACTS, DISPLAY, MANAGE, SOLVE, INSPECT, SELECT), each with its big button | Same order and members (research 9.2); every group shows a big button; the commands not built (Simplify, Linear / Angular Global Load, Point Mass, Manual Contacts, Bolt / Rigid Body Connector) are greyed with their sentence; original icons for every entry; on / off buttons (Ux, Uy, Uz, Flip Direction, Body Selection) look on when on | A[4]; G (mem) for the order |
| S26 | Every value field takes a unit override; Simulation follows the document's units (Document Settings > Units) | Same: the fields, the browser's texts, Load Case Attributes, Study Materials' properties and the mesh / contact lengths show N, MPa, N mm and the design's length in a metric design (N m in metres), lbf, psi, lbf in and inches in an inch design (lbf ft and feet in feet); a bare number is in the unit shown, a typed unit wins; the engine keeps N, MPa, mm, and a field left unchanged keeps its exact value | A[23] A[67] F[99] |
| S27 | In Simulation the right-click marking menu offers the setup's commands; the design's keys do nothing (the design is changed in Design) | The marking menu's ring: Repeat (the last setup command only), Study Materials, Structural Loads, Undo, Structural Constraints, Pre-check, Solve, Settings (OK / Cancel while a dialog is open); its list: Redo, Generate Mesh, Local Mesh Control, DOF View, Hide / Show All / Fit / Look At, orbit centre. Delete, E, Q, F, H, M, J, A, Ctrl+C / Ctrl+V, Ctrl+B and the sketch keys are off while SIMULATION shows (Delete made a Delete Face step from a face picked in the view); the browser still deletes a study item with Delete | G (mem); outline 2.2 |
| S28 | A load or constraint whose faces were removed is flagged (Load Case Attributes' status icon) | The browser row is marked with "Lost what it was on: edit it and pick again", the pre-check is red, Load Case Attributes says "Lost its faces"; Edit shows the picks as the design is now (a face the engine found again by its shape, under its new name), leaves out the gone ones and says how many to pick again | A[28] |

### Scenarios (real clicks, `SciForgeTests/gui/scenarios/sim_setup_*.py`)

| Scenario | Paths |
|---|---|
| `sim_setup_bracket` | enter, New Study, the Pre-check list red with Repair, which opens Structural Constraints: Fixed at the holes, Force on the arm, Pre-check green, Solve, results handed over, leave (tabs, timeline, browser, nothing leaked), enter again |
| `sim_setup_dialogs` | Esc on New Study, the gear's settings, a refusal (nothing holds), Esc / Cancel in the item dialogs, Study Materials + undo / redo, Settings + undo, gravity on, Edit Gravity (Flip; Normal from a side face; Normal from a straight edge), contacts, Load Case Attributes, undo / redo of a constraint |
| `sim_setup_browser` | solve, Edit Load from the browser, out of date, solve again from the Results row (the progress lists the earlier solve), double-click edit + Cancel, Suppress / Unsuppress, F2 rename + undo, Delete key + undo, Clone Study, Activate, delete a study, a design change makes it out of date; the arm deleted and made again (Force 1's face found again by its shape), solved: up to date at once |
| `sim_setup_documents` | two glued bodies (Automatic Contacts, Contact Manager), DOF View on (both free, six arrows) and off once the base is fixed, Exclude / Include, solve with a result per body, design tabs keep their workspaces, save / close / reopen with the study and results (none of it in DESIGN's browser or timeline after reopening); "Keep the results in the design file" off: reopened with the summary only, still up to date; another design's tab clicked during a solve: it stays in front, the progress names the study, a double-click on its row brings its design forward on RESULTS |
| `sim_setup_kinds` | every constraint and load type (Pin filter and defaults, Moment with a unit, vector force components, pressure flip, prescribed displacement), Bearing Load (round faces only, its direction turned across the hole) and Remote Force (its point), Local Mesh Control with Body Selection, Generate Mesh + Show Mesh (not drawn in DESIGN), Cancel a solve |
| `sim_setup_workspace` | entering with a sketch open, leaving with a dialog open, Esc, a second study (undo / redo of it), Solve dialog with two studies (one refused), undo while results show, leaving from RESULTS, leaving for DESIGN during a solve (not taken back when it ends), the design closed during a solve (the solver stops, the progress window says the study is gone, a new design opens in DESIGN) |
| `sim_setup_components` | an empty design, moved components, a model held by one edge (DOF View: it can still turn about the edge, one turning arrow; not held enough) |
| `sim_setup_glyphs` | the glyphs rendered off screen: drawn, hidden on request, same screen size after a zoom, gone in DESIGN; DOF View's arrows drawn over the model and gone when it is off |
| `sim_setup_canvas` | the right-click marking menu in SIMULATION (the setup's commands, none of the design's; Structural Loads from the ring; Repeat Structural Loads), Delete and E on a face picked in the view change nothing, the design's ring and keys back in DESIGN |
| `sim_setup_lost` | a design change takes a load's face away: its row marked with the reason, pre-check red, Load Case Attributes "Lost its faces"; Solve: "Cannot solve" with Repair, Solve refused; Repair opens Edit Load (told why), which says the face is gone; a new pick, OK: fine again; the Fixed deleted: Repair opens Structural Constraints, a hole picked: not red; the body deleted: the study stays, red, Repair opens the Pre-check list (no solid body); SOLVE > Job Status with nothing solved says so; DOF View and Generate Mesh say there is no solid body |
| `sim_setup_mesh` | Generate Mesh, an absolute 3 mm size (the Mesh row out of date, a finer mesh), Adaptive Mesh Refinement Low solved in several passes, a second study held by nothing with two balanced forces (the view turned to reach the far end): red, then Remove rigid body modes: solved; SOLVE > Job Status lists the session's meshes and solves, a double-click shows Study 1's results |
| `sim_setup_more` | Frictionless on a side face, Force Per Entity on two faces, Moment by Angle (its axis out of the face) then Vector (carried over) about a typed axis, gravity along a typed vector, Local Mesh Control edited from the browser + undo, a Force by Angle (About X 30: turned, kept, shown again by Edit and Load Case Attributes, carried to Vector, kept by Clone Study) |
| `sim_setup_two` | two bodies 0.5 mm apart: red (the top held by nothing), Solve > Repair switches DOF View on with the top named; no contact at 0.1 mm, bonded with the tolerance typed as 1 mm (kept), DOF View: held through the contact, Clone Study with Aluminium for one body, In Study unticked + undo, "Solve 2 Studies": both solved, each body in its study's material; Top excluded with a force on it: red, Repair opens Study Materials (told why), Top ticked In Study: not red |
| `sim_setup_during` | while a study solves: Undo (the solve goes on; the results come out of date), Edit Load and Generate Mesh refused with a sentence, Cancel (the stage it stopped at says cancelled) and Solve again at once, the bracket deleted in DESIGN (the solve stops with a sentence naming it; red afterwards) |
| `sim_setup_odd` | odd actions: Delete on the study with Structural Loads open (the dialog ends first, no New Study dialog, Undo), leaving for DESIGN with Study Materials open, deleting a meshed study (Show Mesh off, Undo brings it back unshown), an empty name refused, Delete refused while it solves (told why), a new load dialog not starting on the faces a row lit up, Ctrl+Z in a pick dialog, DOF View on / off, Edit Gravity + Esc, designs closed with Structural Loads or Settings open (no undo step left open, no error, the next design's Generate Mesh runs), two rows Ctrl-picked and deleted in one undo step, the only constraint suppressed: Repair says so, the Solve dialog and Load Case Attributes closing with their design |
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
- **Limit Target** (a force on a circle inside the face) is not in the Structural Loads dialog
  (the engine loads whole faces); Remote Moment, Hydrostatic Pressure and the Remote constraint
  are listed greyed with a sentence. An Angle direction is worked out from the face's normal
  when OK is pressed: a later design change that turns the face does not turn the load (Normal
  does follow the face).
- The Job Status list of earlier solves covers this session only (Fusion's cloud keeps its
  jobs). What Fusion's Repair opens is not known (research 3.10 names the button only):
  SciForge's goes to the first thing that stops the solve.
- **Glyph look**: SciForge's own (Fusion's are unknown here; research 3.12 is G). xvfb shows no
  3D on the screen, but FreeCAD's off-screen picture does: `sim_setup_glyphs` renders the view
  with and without them and checks their colours.
- **Engine issues found while building the UI** (reported to sim-core in
  `docs/sciforge/sessions/beta3-sim-ui.md`): fixed by sim-core since: a whole-body pick dropped by
  the engine's link list, a model held by one edge that "solved" with 1e10 mm of movement (now
  "not held enough" in the pre-check; the UI still refuses such results:
  `simulation_solve_dialog.loose_result`), the result summary keyed bodies by label (two
  components' "Body1" shared one entry), the result fingerprint was taken when the solve ended,
  and "Keep the results in the design file" made results look out of date. Still open: the
  Bearing Load's default direction along a hole drilled along Z (the UI turns it across), and
  a body deleted while its study solves (the engine fails on it; the UI stops the job first).

## Results

(builder sim-results, branch `sf/sim-results`, 2026-10-26/27.) Fusion's RESULTS tab of a
Static Stress study. Files (`src/Mod/SciForge/sciforge/`):

| File | What it holds |
|---|---|
| `simulation_results_core.py` | the rules, no FreeCAD / Qt, unit tested: Fusion's result list (type + component), units, the colour map texture and legend, the safety factor targets and their sentence, deformation and animation, the outer surface of the tetrahedral mesh (10-node faces split in 4, facing out; mesh and outline edges), a ray against it (probes), a level set through it (the slice plane and the iso-surface, in numpy), a point found in it with its weights (Point Probes), Solver Data's rows, the convergence plot's data, the HTML report |
| `simulation_results.py` | the document side, no Qt: a study's results as arrays (kept per solve), strain components, values and displacement at any point inside the part, Results Details' numbers, the report's data |
| `simulation_results_view.py` | the drawing: SciForge's own Coin nodes (never document objects), the legend, the tags and the animation bar floating over the 3D view |
| `simulation_results_ui.py` | when the results show (the RESULTS tab watcher), `show(study)` for sim-ui's Solve dialog, `hide()`, Compare, the 23 commands |
| `simulation_results_panels.py` | Surface Probes, Point Probes, Slice Plane, Iso-surface, Results Details, Legend Min/Max, Compare, Report, Reaction Force, Solver Data, Convergence Plot, Save Animation, a solve from out-of-date results when sim-ui's Solve is missing |

Shared files: `ribbon_config.py` (the RESULTS tab's groups: commands, icons, ticks),
`tools/sciforge/icons_simresults.py` (23 icons), `docs/sciforge/parity-checklist.md`
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
surface: a Value slider over the result, an opacity); an Autodesk blog excerpt on adaptive
mesh refinement (it "unlocks 2D convergence plots" of the von Mises stress, displacement, 1st
and 3rd principal stress; where the plot opens was not found).

### What shows, when

| Fusion | SciForge | Src |
|---|---|---|
| After a solve the canvas shows the results, Safety Factor first, with min / max tags | sim-ui's Solve dialog calls `simulation_results_ui.show(study)`: the SIMULATION workspace's RESULTS tab, Safety Factor, min / max tags | A[80] A[71] |
| The RESULTS tab exists once there are results | The RESULTS tab shows only while the active study (sim-ui's) has results; selecting it shows them, SETUP / DESIGN / another document puts them away | A[49], G (mem) |
| The deformed shape is Adjusted by default | Adjusted (largest movement = 5 % of the model's bounding-box diagonal) | A[51], research Q9 |
| (Fusion keeps results in its cloud) | Display only: SciForge's own Coin nodes; the design's bodies are hidden on the 3D view only (their Coin switch, never Visibility): nothing in the undo history, the file, the modified mark or the study's out-of-date fingerprint (checked in the scenarios) | SciForge |
| Results tied to a design version: "out of date" when the design changed; solve again | The legend warns "out of date" with **Solve Again** (sim-ui's Solve dialog), Results Details and the report say it too; Undo of the change clears it | F[85] A[65] |
| Finish Results returns to SETUP | Same; the bodies show again | G (mem) |
| A body's eye in the browser hides it on the results too (to see the results of the parts inside) | The browser's eye of a study body off: its elements are left out of the drawn result (the surfaces of the bodies left are drawn, slices and iso-surfaces too; the min / max tags mark the bodies shown), the colour scale stays the whole study's; on again: back. (sim-core counts a hidden body out of a study without its own body list, so the results say they are out of date meanwhile.) | G (mem) |
| (results not saved) | A study whose results were not kept with the design (sim-core's Keep results off) has no RESULTS tab; `show()` says to solve again | SciForge |

### The legend and the result list

| Fusion | SciForge | Src |
|---|---|---|
| Legend: result drop-down, a second drop-down for the component, a unit drop-down, legend options | Same, at the top left of the 3D view: Safety Factor / Stress / Displacement / Strain, then the component; units MPa, kPa, Pa, psi, ksi or mm, cm, m, in (none for the safety factor and strain), first in **the design's units** (Document Settings > Units: an inch or foot design shows inches and psi, a cm design cm; it follows a change at once), then the one chosen | A[77] A[49] A[67], Autodesk legend help; place G |
| Result types | Safety Factor; Stress: Von Mises, 1st / 3rd Principal, Normal XX / YY / ZZ, Shear XY / YZ / ZX; Displacement: Total, X, Y, Z; Strain: Equivalent, 1st / 3rd Principal, Normal XX / YY / ZZ (worked out from the solve's strain tensor) | A[48], components G (A[82] Inventor) |
| A vertical colour bar with min and max | Max above, Min below the bar, 9 values (the safety factor every 1.5); colours blue - cyan - green - yellow - red drawn with a colour map texture, so the colours between two nodes follow the map; a 10-node element's face is drawn with its quadratic shape functions (16 small triangles), so a coarse mesh shows its field smoothly | G (mem) |
| Safety factor capped at 15; no legend min / max for it | Scale 0 .. 15, red low, blue high | F[89] F[90] T[107] |
| Legend options: colour transitions (bands) | "..." > Smooth Colours / Colour Bands (9 bands) | Autodesk legend help |
| Legend Min/Max (legacy viewer: RESULT TOOLS > Legend Min/Max; not for the safety factor); the colour bar's sliders: drag the top or the bottom of the legend to narrow the range, hiding what is beyond | RESULT TOOLS > Legend Min/Max and the legend's "..." menu: Min and Max in the legend's unit, Reset; **the colour bar's two ends have handles**: drag one and let go to narrow the range, double-click the bar for the result's own range; values beyond take the end colours, or are **drawn grey** with "..." > Grey Outside the Range (SciForge's grey for Fusion's hiding); the legend shows the result's own min / max and says the colours' range; none of it for the safety factor | A[53] F[90], web excerpts (Fusion blog, AU handout) |
| Results Details button next to the Load Case selector | The "i" button in the legend (one load case per study: no selector) | A[61] |

### RESULTS tab commands

| Group: Fusion | SciForge | Src |
|---|---|---|
| RESULT TOOLS: Animate (legacy dialog with steps; online viewer: bar at the bottom of the canvas, speed 0.25x - 2x, up to 100 frames, play once / loop / mirror loop, save .webm) | Animate: a bar at the bottom left of the 3D view: Play / Stop, 0.25x - 2x, 10 - 100 steps, Play Once / Loop / Mirror Loop, **Save...** (an animated GIF or WebP: one picture of the 3D view per step, at the speed chosen, looping as chosen, the legend drawn in; Pillow, which FreeCAD bundles), Close; undeformed to the chosen scale (Adjusted when Undeformed is chosen) | A[52]; GIF / WebP instead of .webm: G |
| RESULT TOOLS: Results Details | The lowest safety factor against the Lower / Upper targets (3 / 6) in a sentence with advice (SciForge's words; it names the body it is in when the study has several), the targets editable, **Show the target bands on the model** (the newer viewer's guided bands: below / meets / above), per body: material, strength (yield or ultimate), max von Mises, min safety factor (in its band's colour: below / meets / above), max displacement, in the legend's units (an inch design: psi / ksi and inches); every result's min / max; the mesh; the limits of the study; the deformation scale at the bottom | Autodesk help (Results details), Learn video, A[54] A[71] A[51] |
| RESULT TOOLS: Report (General, Properties, Studies; Preview / Save; HTML) | Report: General (title, author, logo, cover picture, summary), Properties (project, approved by, revision), Studies (this design's studies with results, the one shown ticked: one report can cover several), pictures or not, file; **Preview** (the report in the web browser, nothing saved; the dialog stays open), Save / Save and Open (the web browser). One HTML page: the cover, then per study the sentence, the limits, settings, materials with strengths, constraints and loads with their faces, contacts, mesh (and the adaptive refinement's solves), every result's min / max, per body (in the legend's units), the reaction force at each constraint, a picture of the loads and constraints and three of the results with their legend drawn in (and the convergence chart of a study solved with adaptive refinement) | A[62] T[107] |
| Convergence plots after a solve with adaptive mesh refinement (2D, of the result judged: von Mises, displacement, 1st or 3rd principal) | RESULT TOOLS > **Convergence Plot** (greyed for a study solved without adaptive refinement): the judged result's highest value (the 3rd principal's lowest) at each solve on a chart, over a band showing the tolerance around the last solve; a table with each solve's nodes, elements, value and the change from the solve before (the engine's own rule: % of the larger of the two); a sentence: converged within the tolerance, or not and what to do (allow more refinements); the report's mesh section has the same table. Its place in the ribbon is SciForge's | A[71] A[76], web excerpt (Autodesk blog: "2D convergence plots"); place G |
| RESULT TOOLS: Compare (up to 4 studies; the canvas splits into views; Finish closes it; no probes in the legacy Compare) | Compare: tick 2 to 4 of the design's studies with results; **the 3D view splits in panes** (two studies: two side by side; three or four: four panes, Navigation bar > Viewports' layouts), each study's result in its own pane, starting from the view's camera, **the panes turning together** (turn, pan or zoom one, the others follow); each pane's tag names its study with its min and max (and says when the study is out of date); an empty fourth pane says so; **one colour scale** and one deformation scale (the same colour is the same value; a bigger bend looks bigger: SciForge's choice) with one legend; the legend's result and unit, DEFORMATION and Show Mesh work on all; probes, slices and the rest rest meanwhile; **Finish Compare** under the legend, Compare again, FINISH RESULTS, SETUP, another design, Viewports > Single View or a solve that ends (its study's results then show) end it and put the view back as it was (a view that cannot be split shows the studies side by side in it) | A[61] F[86], G |
| DEFORMATION: Undeformed, Actual, Adjusted x 0.5, Adjusted, x 2, x 5 | Same, ticked in the menu; also in Results Details | A[51] |
| DISPLAY: Mesh, Wireframe | Show Mesh (element edges); **Undeformed Model** (the unloaded shape see-through: the web viewer's "Show Undeformed model") instead of Wireframe; **Loads and Constraints** (sim-ui's glyphs on the results, off by default) | A[49] A[68], G |
| INSPECT: Surface Probes (hovering shows the value under the mouse, a click places a tag; as many as wanted) | The value under the mouse follows it over the result (a lighter tag, gone off the model); a click: a tag with the value of the node under the mouse; as many as wanted; they read the result chosen in the legend; Remove (the one chosen in the list), Clear All; Esc / Close keeps them | A[55], web excerpt |
| INSPECT: Show Min/Max | Toggle (on by default) | A[80] A[57] |
| INSPECT: Measure | SciForge's Measure works on the design's bodies, which the results hide: opening it from RESULTS brings SETUP back with the model shown (and says so) | G |
| INSPECT: Reaction Force | A table: the force each constraint takes (X, Y, Z, total), from the solve (sim-core's `summary["reactions"]`), and while it is open a tag on each constraint's faces with its total | A[48] A[58] |
| INSPECT: Slice Plane (legacy: Shaded, Mesh Lines, Vectors, Clipping; online: Section, Slice) | A plane across X, Y or Z, **on one of the design's construction planes** ("On Offset Plane 1"), or **parallel to a face clicked on the result** (any direction; half way across the part, the half away from the face kept so the cut looks at you), position (field, slider, or the plane's drag arrow), Flip; **Cut the result away** (clipping, the cut face coloured with the values inside) or **Slice alone** (the cut face inside the whole result drawn see-through); **Mesh lines on the cut** (the legacy Mesh Lines style: where the plane crosses the elements, to judge the mesh inside); **Displacement arrows on the cut** (the legacy Vectors style: arrows the way the material moves, longer where it moves more, coloured like the result there, evenly spread); a probe on the cut face reads the value inside; OK / Cancel / Remove Slice | A[56] |
| INSPECT: Point Probes (values inside the part; first placed on any visible surface, slice planes and iso-surfaces included; moved by grips or X, Y, Z; global coordinates, drawn with the displacement) | Point Probes: a click on the result, a slice's cut face or the iso-surface puts a probe there (inside surfaces first when the result is see-through); the value under the mouse while it moves; the chosen probe (the newest, or the one chosen in the table) has **grips**: three drag arrows along X, Y and Z; a table P1, P2... with X, Y, Z on the unloaded part (typed to move it, a unit allowed: "0.5 in") and the value of the result in the legend; outside the part it says so; the tag (a diamond) moves with the part as drawn (Deformation, Animate); Remove, Clear All; Close keeps them; the value is interpolated in the mesh (a node's own value at a node) | A[55], web excerpts |
| INSPECT: Iso-surface | Iso-surface: the surface inside the part where the result shown has one value, in the legend's colour of that value, the result see-through around it (cut by a clipping slice too); value field (legend unit) and slider between the result's lowest and highest (half way to start); the legend's result moves it to that result; a value nothing reaches says so; OK / Cancel (puts back what was there) / Remove Iso-surface | G (Flow Design's iso surface as the model) |
| INSPECT: Solver Data | Solver Data: when the study was solved and how long each step took (model, mesh, solver input, CalculiX, reading the results), the safety factor's basis; the mesh: nodes, degrees of freedom (3 per node), elements, order, element size, smallest / largest element edge, worst aspect ratio, elements over the limit, mesher; the adaptive refinement's solves; the solve's messages; Copy (as text) | A[57]; contents G |
| MANAGE | sim-ui's (shared with SETUP) | A[49] |
| FINISH RESULTS | Finish Results | G (mem) |

### Known gaps (Results)

- **Compare's legends**: Fusion shows a legend in each study's view; SciForge's panes share one
  legend and one colour scale (the same colour is the same value in every pane). With three
  studies the fourth pane stays empty (Fusion's layout for three was not found). Fusion's legacy
  Compare locks the deformation scale to Adjusted (F[86]); SciForge's DEFORMATION changes it for
  every study at once.
- **Saving the animation as a video (.webm)**: SciForge saves an animated GIF or WebP instead
  (FreeCAD's bundle has Pillow but no video encoder); browsers and chat apps play both.
- **The Vectors slice style** shows the displacement's arrows (what Fusion draws for a stress
  result there was not found: principal stress directions are not drawn).
- **The online viewer's threshold sliders**: the legend's handles narrow the range and Grey
  Outside the Range greys what is beyond; Fusion hides it (a grey part keeps the shape readable).
- **Contact pressure / force results**: bodies are bonded (glued), which has no contact pressure;
  CalculiX's contact output is not requested.
- **Shear strain components**: CalculiX's shear strains are tensor values (half the engineering
  shear strain); left out rather than shown with an uncertain meaning. Normal and principal
  strains are shown.
- **Load case selector**: one load case per study.
- **Report**: one load case per study (no load case choice), no result steps (Static Stress has
  one); the pictures use the camera as it is when Save is pressed.
- **Point Probes' grips**: three separate arrows (X, Y, Z), not Fusion's one triad
  manipulator.
- **Iso-surface**: one at a time, of the result shown in the legend, in one colour (Fusion's
  own colouring of iso-surfaces was not found); several values at once are not offered.
- **Solver Data**: CalculiX's own output (its log) is not kept by the engine, so it is not shown;
  the timings, mesh statistics and the engine's messages are.
- **Reaction Moment** (a result type in Fusion's list): the engine reports the force each
  constraint takes (Reaction Force, its tags and the report's table), not the moment.
- **Convergence Plot's place**: where Fusion opens its convergence plots was not found;
  SciForge puts it in RESULT TOOLS (greyed for a study solved without adaptive refinement).
- **The legend's place** (top left of the 3D view) and the safety factor's colours (0 .. 15,
  red low) are guesses (research section 10, questions 1 and 6): a screenshot of Luca's Fusion
  would settle them.

## Benchmarks

(builder sim-core.) `SciForgeTests/headless/sim_benchmarks.py`, run by
`tools/sciforge/run_tests.sh --only sim` (and `--only base`): every case through the same engine
as the workspace and the AI tools, in real FreeCAD 1.1.4 with Gmsh 4.15 and CalculiX 2.23, at
the study's default mesh and at a finer one, against the hand calculation, with CalculiX on one
thread (so the times compare between runs; a solve uses all cores but one otherwise). Steel is
FreeCAD's Steel-Generic (E = 200 GPa, nu = 0.3, 7900 kg/m3); every hand calculation reads E,
nu and the density from the study material, so the formulas and the solve use the same values.
The evidence outline 0.8 asks for; acceptance of outline 7.18 ("golden studies match hand
calculations within a few percent").

Run of 2026-10-26 (report `sim-benchmarks.json` in the output folder, from `--only base`):
50 accuracy checks and 88 engine checks, all PASS; the whole run takes about two minutes.

| Case | Check | Hand calculation | Default mesh: SciForge (error) | Finer mesh: SciForge (error) | Tolerance | Nodes (default / finer) | Seconds (default / finer) | Result |
|---|---|---|---|---|---|---|---|---|
| **cantilever**: Cantilever 100 x 10 x 10 mm, steel, 100 N at the tip | tip deflection (mm) | 0.2 | 0.1995 (0.27 %) | 0.2005 (0.25 %) | 3 % | 459 / 3953 | 0.71 / 1.41 | PASS |
|  | bending stress / (M c / I), top face 20-80 mm | 1 | 1 (0.01 %) | 1 (0.01 %) | 3 % | 459 / 3953 | 0.71 / 1.41 | PASS |
|  | reaction at the fixed end (N) | 100 | 100 (0.00 %) | 100 (0.00 %) | 1 % | 459 / 3953 | 0.71 / 1.41 | PASS |
| **plate_hole**: Plate 200 x 100 x 5 mm with a 20 mm hole, 10 MPa tension both ends, Remove rigid body modes | max 1st principal stress at the hole (MPa), Kt 2.506 on the net section | 31.33 | 32.04 (2.26 %) | 31.99 (2.12 %) | 5 % | 7174 / 30674 | 3.16 / 18.73 | PASS |
| **thick_cylinder**: Thick ring, inner 20 / outer 40 mm, 10 MPa inside; quarter model on Frictionless planes | hoop stress at the bore (MPa), Lame | 16.67 | 16.65 (0.10 %) | 16.67 (0.00 %) | 3 % | 800 / 7949 | 0.58 / 3.63 | PASS |
|  | bore growth (mm), Lame plane strain | 0.001907 | 0.00191 (0.18 %) | 0.001907 (0.03 %) | 3 % | 800 / 7949 | 0.58 / 3.63 | PASS |
| **symmetry_half**: Half cantilever on a Frictionless symmetry plane against the full model | half model tip deflection = full model's (mm) | 0.1995 | 0.1995 (0.02 %) | 0.2005 (0.02 %) | 2 % | 441 / 2541 | 0.27 / 0.78 | PASS |
|  | half model max von Mises = full model's (MPa) | 59.08 | 59.2 (0.20 %) | 59.91 (1.10 %) | 4 % | 441 / 2541 | 0.27 / 0.78 | PASS |
| **bonded_bars**: Steel and aluminium bars glued end to end (one 0.05 mm apart), 10 kN pull | end of the bars moves (mm), two springs in series | 0.0965 | 0.09625 (0.26 %) | 0.09631 (0.20 %) | 3 % | 459 / 4377 | 0.4 / 1.54 | PASS |
|  | stress in both bars (MPa) = F / A | 100 | 100 (0.00 %) | 100 (0.00 %) | 3 % | 459 / 4377 | 0.4 / 1.54 | PASS |
|  | the two bodies are glued (one contact found) | 1 | 1 (0.00 %) | 1 (0.00 %) | 0 % | 459 / 4377 | 0.4 / 1.54 | PASS |
| **torsion**: Round shaft 20 mm x 100 mm twisted by 10 N m at its end (a Moment) | von Mises on the surface, 30-70 mm (MPa) = sqrt(3) T r / J | 11.03 | 11.18 (1.39 %) | 11.04 (0.15 %) | 3 % | 488 / 4446 | 0.27 / 1.6 | PASS |
|  | rim turns (mm) = T L r / (G J) | 0.008276 | 0.008374 (1.18 %) | 0.008277 (0.01 %) | 3 % | 488 / 4446 | 0.27 / 1.6 | PASS |
| **hanging_bar**: Steel bar 20 x 20 x 200 mm hanging from its top, gravity only | stress at the top (MPa) = rho g L | 0.01549 | 0.01545 (0.28 %) | 0.01547 (0.17 %) | 3 % | 457 / 2385 | 0.28 / 0.81 | PASS |
|  | the bottom drops (mm) = rho g L^2 / 2E | 7.75e-06 | 7.76e-06 (0.14 %) | 7.76e-06 (0.14 %) | 3 % | 457 / 2385 | 0.28 / 0.81 | PASS |
|  | the hold carries the weight (N) = rho g V | 6.198 | 6.198 (0.00 %; 6.149 before QA's reaction fix) | 6.198 (0.00 %; 6.171 before) | 1 % | 457 / 2385 | 0.28 / 0.81 | PASS |
| **remote_force**: Cantilever with 100 N acting 50 mm beyond its tip (a Remote Force) | tip deflection (mm) = F L^3 / 3EI + F a L^2 / 2EI | 0.35 | 0.3477 (0.67 %) | 0.3491 (0.24 %) | 3 % | 459 / 3953 | 0.24 / 1.46 | PASS |
|  | reaction (N) | 100 | 100 (0.00 %) | 100 (0.00 %) | 1 % | 459 / 3953 | 0.24 / 1.46 | PASS |
| **prescribed**: Cantilever whose tip is pushed down 0.2 mm (a Prescribed Displacement) | force it takes (N) = 3 E I d / L^3 | 100 | 100.6 (0.56 %) | 100 (0.04 %) | 3 % | 459 / 3953 | 0.31 / 1.24 | PASS |
|  | the tip moved 0.2 mm | 0.2 | 0.2006 (0.28 %) | 0.2006 (0.28 %) | 1 % | 459 / 3953 | 0.31 / 1.24 | PASS |
| **pinned_beam**: Beam 420 x 20 x 10 mm on two pins 400 mm apart, 1 N/mm on top | middle of the span drops (mm), bending + shear | 0.2508 | 0.2495 (0.51 %) | 0.2504 (0.18 %) | 3 % | 701 / 2254 | 0.33 / 0.8 | PASS |
|  | the pins carry the load (N) | 420 | 420 (0.00 %) | 420 (0.00 %) | 1 % | 701 / 2254 | 0.33 / 0.8 | PASS |
| **bearing_lug**: Lug fixed at its foot, 1 kN bearing load in its 10 mm hole | the foot holds the load (N, along it) | 1000 | 1000 (0.00 %) | 1000 (0.00 %) | 1 % | 1535 / 9563 | 0.49 / 4.39 | PASS |
|  | nothing sideways (N) | 0 | 3.11e-12 (0.00 %) | 0.05364 (0.05 %) | 1 % | 1535 / 9563 | 0.49 / 4.39 | PASS |
| **hollow_sphere**: Hollow steel ball, outer 40 / inner 36 mm, 10 MPa inside, held by nothing (Remove rigid body modes) | hoop stress at the bore (MPa), Lame for a sphere | 45.35 | 45.74 (0.86 %) | 45.41 (0.12 %) | 3 % | 1881 / 10130 | 0.79 / 4.34 | PASS |

| Engine check | What is checked | Checks | Result |
|---|---|---|---|
| cancel at every stage | cancelled, temporary folder gone, last results and objects kept, before each of: model, model's second turn, mesh, input, input's second turn, solve, results, results' second turn, results' last turn | 27 | PASS |
| a failed solve keeps the last results | refused: nothing holds it; results kept; now out of date; back in date; not held enough: a sentence; results still kept | 6 | PASS |
| Generate Mesh | mesh statistics; results kept next to the new mesh; the newest mesh is shown; mesh summary not stale; mesh summary stale after a mesh setting; a solve replaces the Generate Mesh run; nothing left needing a recompute after the solve | 7 | PASS |
| save and reopen | file size: 910 kB with results, 12 kB without (3953 nodes); reopened: results back; reopened: same summary, not out of date; reopened: items and picks; without results: the numbers stay; without results: not out of date (keeping them changes nothing); without results: solve again to see them; solved again after reopening | 8 | PASS |
| a body in a moved component | same bend as unmoved; the tip is where the component put it; reaction 100 N | 3 | PASS |
| two components' bodies with the same name | both named Body1, two rows: Body1 (Bracket), Body1 (Plate); each row is its own body (bends 0.2 mm, as one cantilever) | 2 | PASS |
| a body whose middle is a hole, glued to another | each piece of the model belongs to its own plate; each plate keeps its material in the results | 2 | PASS |
| a design saved while it solves | a running job's run is not taken for left over; reopened: the half-made run is in the file; the next solve removes it and solves | 3 | PASS |
| undo steps opened while it solves | solved; every step undone: the results stay (9 turns) | 2 | PASS |
| a study material that is gone | the body's own material is used, and the pre-check warns | 1 | PASS |
| a thin plate at a fine mesh | solved; the tip bends between plate and beam theory (2.696 .. 2.963 mm): 2.843 mm | 2 | PASS |
| a thin tube at the default mesh | solved; a note: the elements were made smaller; a note: stretched elements across the wall | 3 | PASS |
| a change while it solves | solved; out of date: the load changed while it solved; solved again: up to date | 3 | PASS |
| a deleted body | a load on a body the study leaves out: refused, naming both; the pre-check names the load that lost its face; the solve refuses with that sentence | 3 | PASS |
| a solve is no undo step | the undo list did not grow with the solve; no undo step left open; undo takes the setup back; redo brings it back with its results | 4 | PASS |
| Netgen when Gmsh fails | solved with Netgen; a note says so; Netgen's mesh bends the same (3 %) | 3 | PASS |
| adaptive mesh refinement | several solves; each solve on a finer mesh; the peak stress ends nearer Kt: first 8.0 % off, last 4.1 % (within 5 %); a note says so | 4 | PASS |
| contacts and loose bodies | 0.05 mm apart is glued, 0.55 mm is not; C would fly away: an error naming it; A and D overlap: a warning; B moved 1 mm away: no longer glued; moved back: glued again; B made shorter, 1 mm off A: not glued | 5 | PASS |

How to read it: "Default" is the study's default mesh (10 % of the model size) except where the
case says otherwise; "finer" is the size in the case's own row. Stresses are read away from a
fixed constraint's edge where the formula is for the material inside (beam theory, torsion),
and at the peak where the formula is for the peak (Kt at the hole, Lame at the bore).

### QA's own hand calculations (sim-engine-qa)

The engine's QA wrote its own cases, independent of the builder's: every formula with its
source next to it in `SciForgeTests/headless/sim_accuracy_qa.py` (run by `run_tests.sh --only
sim` after the builder's benchmarks), at the default and a finer mesh, a few through the AI
tools (their answers only), and engine checks for numbers that would be wrong without a word.
Run of 2026-10-27 (`sim-accuracy-qa.json`): 205 checks (162 accuracy rows, 43 engine checks), 0 failed. A row marked "warned" is outside its
tolerance at the default mesh and the solve says why (a thin wall met by large elements); the
finer mesh is within it. Steel is Steel-Generic, aluminium Aluminum-Generic (E read from the
study material).

| Case | Check | Hand calculation | Default mesh: SciForge (error) | Finer mesh: SciForge (error) | Tolerance | Result |
|---|---|---|---|---|---|---|
| **ss_beam_centre**: Simply supported beam 200 x 10 x 20 mm (pin and roller lines under its ends), 1 kN on a line across the top at mid span (a force on an edge) | mid-span deflection (mm) = P L^3 / 48EI + P L / 4kGA | 0.1288 | 0.1289 (0.074 %) | 0.1298 (0.754 %) | 3 % | PASS |
|  | bottom bending stress / (M c / I), x 30-70 and 130-170 mm (M = P x / 2) | 1 | 1.002 (0.205 %) | 0.9999 (0.009 %) | 3 % | PASS |
|  | pin line carries half (N, z) | 500 | 500 (0 %) | 500 (0 %) | 0.5 % | PASS |
|  | roller line carries half (N, z) | 500 | 500 (0 %) | 500 (0 %) | 0.5 % | PASS |
| **ss_beam_pressure**: Simply supported beam 200 x 10 x 20 mm under 0.5 MPa on its top (5 N/mm) | mid-span deflection (mm) = 5wL^4/384EI + wL^2/8kGA | 0.08004 | 0.08045 (0.519 %) | 0.08121 (1.469 %) | 3 % | PASS |
|  | bottom bending stress / (M c / I), x 30-70 and 130-170 mm (M = w x (L - x) / 2) | 1 | 1.002 (0.192 %) | 1.003 (0.336 %) | 3 % | PASS |
|  | the supports carry the load (N) = q b L | 1000 | 1000 (0 %) | 1000 (0 %) | 0.5 % | PASS |
| **symmetry_beam**: Half of the centre-loaded beam on a Frictionless symmetry plane at mid span against the full beam (the line load on the plane's top edge, halved) | half model's mid-span deflection = the full model's (mm) | 0.1289 | 0.1294 (0.375 %) | 0.13 (0.147 %) | 1 % | PASS |
|  | half model's bending stress ratio = the full model's (x 30-70 mm) | 1.002 | 1.001 (0.171 %) | 0.9998 (0.027 %) | 1 % | PASS |
|  | half model's support carries half the load (N) = full model's pin line | 500 | 500 (0 %) | 500 (0 %) | 0.5 % | PASS |
| **cantilever_edge_vertex**: Cantilever 100 x 10 x 10 mm loaded on an edge (100 N), on two corners (shared, then per corner) | edge load: tip deflection (mm) = FL^3/3EI + FL/kGA | 0.2015 | 0.1989 (1.324 %) | 0.1999 (0.812 %) | 3 % | PASS |
|  | edge load: the fixed end holds 100 N | 100 | 100 (0 %) | 100 (0 %) | 0.5 % | PASS |
|  | two corners sharing 100 N: tip deflection (mm) | 0.2015 | 0.1989 (1.324 %) | 0.1999 (0.815 %) | 3 % | PASS |
|  | two corners sharing 100 N: the fixed end holds 100 N | 100 | 100 (0 %) | 100 (0 %) | 0.5 % | PASS |
|  | 100 N per corner (Force Per Entity): the fixed end holds 200 N | 200 | 200 (0 %) | 200 (0 %) | 0.5 % | PASS |
|  | 100 N per corner: tip deflection twice the shared one (mm) | 0.4031 | 0.3977 (1.324 %) | 0.3998 (0.814 %) | 3 % | PASS |
| **stepped_bar**: Stepped bar pulled by 5 kN: steel 20 x 20 x 100 mm glued to aluminium 10 x 10 x 100 mm | the end moves (mm) = F L1/E1A1 + F L2/E2A2 | 0.07768 | 0.07769 (0.017 %) | 0.07798 (0.389 %) | 2 % | PASS |
|  | steel bar stress (MPa) = F / A1, x 30-70 mm | 12.5 | 12.5 (0.004 %) | 12.5 (0.006 %) | 2 % | PASS |
|  | aluminium bar stress (MPa) = F / A2, x 130-170 mm | 50 | 49.99 (0.013 %) | 50 (0.001 %) | 2 % | PASS |
|  | materials not swapped: end movement far from the swapped value 0.04286 mm | 1 | 1 (0 %) | 1 (0 %) | 0 % | PASS |
|  | per-body rows name each body's material (steel part) | Steel-Generic | Steel-Generic (0 %) | Steel-Generic (0 %) | 0 % | PASS |
|  | per-body rows name each body's material (aluminium part) | Aluminum-Generic | Aluminum-Generic (0 %) | Aluminum-Generic (0 %) | 0 % | PASS |
|  | the hold takes the pull (N) | 5000 | 5000 (0 %) | 5000 (0 %) | 0.5 % | PASS |
| **clamped_plate**: Circular plate, radius 50 mm, 2.5 mm thick, clamped at its rim, 0.1 MPa on top | centre deflection (mm) = q a^4 / 64D + q a^2 / 4 kappa G t | 0.03451 | 0.03089 (10.52 %) warned | 0.03422 (0.853 %) | 5 % | PASS (default: warned) |
|  | bottom bending stress / plate theory, r < 0.4 a | 1 | 0.9382 (6.182 %) warned | 0.9959 (0.414 %) | 5 % | PASS (default: warned) |
|  | the rim holds the load (N) = q pi a^2 | 785.4 | 785.4 (0.006 %) | 785.4 (0 %) | 0.5 % | PASS |
| **tube_torsion**: Tube 30 / 24 mm across, 150 mm long, held at one end, twisted by 50 N m (a Moment, N mm) | von Mises on the outer surface (MPa) = sqrt(3) T r / J | 27.67 | 25.92 (6.319 %) warned | 27.67 (0.004 %) | 3 % | PASS (default: warned) |
|  | the free end's rim turns (mm) = T L r / (G J) | 0.03115 | 0.03027 (2.819 %) | 0.03115 (0.004 %) | 3 % | PASS |
|  | the held end takes no force (N): a moment only | 0 | 0.0001046 (0 %) | 3.13e-05 (0 %) | 0.5 % | PASS |
| **gravity_bracket**: Steel L bracket held at its wall face with an aluminium block glued on it, gravity alone | the wall holds the weight (N, z) = g sum(rho V) | 2.226 | 2.226 (0 %) | 2.226 (0 %) | 0.2 % | PASS |
|  | nothing sideways (N) | 0 | 8.748e-08 (0 %) | 1.885e-07 (0 %) | 0.2 % | PASS |
|  | the arm's tip goes down, not up (sign of its z movement) | -1 | -1 (0 %) | -1 (0 %) | 0 % | PASS |
| **gravity_sideways**: The same bracket with gravity along -Y: the wall holds the weight along +Y | the weight = Inspect's mass 0.216144 kg x 9.80665 m/s2 (N) | 2.12 | 2.12 (0 %) | 2.12 (0 %) | 0.2 % | PASS |
|  | the wall holds the weight along +Y (N) | 2.12 | 2.12 (0 %) | 2.12 (0 %) | 0.2 % | PASS |
|  | nothing along Z (N) | 0 | 8.347e-10 (0 %) | 5.418e-09 (0 %) | 0.2 % | PASS |
| **shaft_bearing**: Shaft 20 mm across, 120 mm long, held at one end, 500 N bearing load on its last 20 mm | free end deflection (mm), distributed load on the journal | 0.1631 | 0.1599 (1.967 %) | 0.1613 (1.128 %) | 3 % | PASS |
|  | the held end takes the load (N, z) | 500 | 500 (0 %) | 500 (0 %) | 0.5 % | PASS |
|  | nothing sideways (N) | 0 | 0.000316 (0 %) | 0.08346 (0.083 %) | 0.5 % | PASS |
| **pinned_link**: Link 100 x 20 x 5 mm with two 8 mm holes 80 mm apart: one on a Pin (tangential held too), a 2 kN bearing load pulling the other along the link | stress in the middle (MPa) = F / (w t) | 20 | 20 (0.019 %) | 20 (0.005 %) | 2 % | PASS |
|  | x 30..70 mm stretches (mm) = F 40 / (E w t) | 0.004 | 0.004003 (0.069 %) | 0.003991 (0.227 %) | 3 % | PASS |
|  | the pin takes the pull (N, -x) | -2000 | -2000 (0 %) | -2000 (0 %) | 0.5 % | PASS |
|  | nothing across (N) | 0 | 1.292e-05 (0 %) | 4.721e-06 (0 %) | 0.5 % | PASS |
| **inch_cantilever**: Cantilever 1 x 1 x 12 in, 100 lbf at its end (an inch-sized part; numbers in mm, N, MPa) | tip deflection (mm) = 25.4 x F L^3 / 3EI [in] | 0.6052 | 0.6023 (0.481 %) | 0.6054 (0.023 %) | 3 % | PASS |
|  | top stress / (0.00689 x M c / I [psi]), 20-80 % of the length (24.82 MPa at mid) | 1 | 1 (0.004 %) | 1 (0.001 %) | 3 % | PASS |
|  | reaction (N) = 100 lbf | 444.8 | 444.8 (0 %) | 444.8 (0 %) | 0.5 % | PASS |
| **scale_1000mm**: The 100 mm cantilever made 10 times bigger (1000 x 100 x 100 mm, 10 kN): the same stress, 10 times the deflection | tip deflection (mm) = F L^3 / 3EI | 2 | 1.995 (0.256 %) | 2.005 (0.245 %) | 3 % | PASS |
|  | bending stress / (M c / I), top face 20-80 % | 1 | 0.9996 (0.039 %) | 1 (0.001 %) | 3 % | PASS |
|  | reaction (N) | 1e+04 | 1e+04 (0 %) | 1e+04 (0 %) | 0.5 % | PASS |
| **scale_1mm**: The 100 mm cantilever made 100 times smaller (1 x 0.1 x 0.1 mm, 0.01 N): the same stress, a hundredth of the deflection | tip deflection (mm) = F L^3 / 3EI | 0.002 | 0.001995 (0.254 %) | 0.002002 (0.101 %) | 3 % | PASS |
|  | bending stress / (M c / I), top face 20-80 % | 1 | 0.9997 (0.028 %) | 0.9991 (0.091 %) | 3 % | PASS |
|  | reaction (N) | 0.01 | 0.01 (0 %) | 0.01 (0 %) | 0.5 % | PASS |
| **safety_basis**: Bar 20 x 20 x 100 mm, 100 MPa in tension and in compression: safety factor on yield (207 MPa / von Mises) and on ultimate (345 MPa / largest principal stress) | pulled 100 MPa, yield basis: lowest safety factor = 207 / 100 | 2.07 | 2.07 (0.001 %) | 2.07 (0.001 %) | 1 % | PASS |
|  | pulled 100 MPa, ultimate basis: lowest safety factor = 345 / 100 | 3.45 | 3.45 (0.001 %) | 3.45 (0.001 %) | 1 % | PASS |
|  | pushed 100 MPa, yield basis: lowest safety factor = 207 / 100 | 2.07 | 2.07 (0.001 %) | 2.07 (0.001 %) | 1 % | PASS |
|  | pushed 100 MPa, ultimate basis: lowest safety factor = 345 / 100 | 3.45 | 3.45 (0.001 %) | 3.45 (0.001 %) | 1 % | PASS |
| **shared_vs_per_entity**: Simply supported beam, 1 kN on two top faces of 60 and 140 mm: shared by area, then per face (Force Per Entity) | shared: the pin line takes 500 N | 500 | 500 (0 %) | 500 (0 %) | 0.5 % | PASS |
|  | shared: deflection at x = 60 mm = an even load's (mm) | 0.06513 | 0.06558 (0.681 %) | 0.06632 (1.826 %) | 3 % | PASS |
|  | per face: the pin line takes 1200 N | 1200 | 1200 (0 %) | 1200 (0 %) | 0.5 % | PASS |
|  | per face: the roller line takes 800 N | 800 | 800 (0 %) | 800 (0 %) | 0.5 % | PASS |
| **directions**: Which way things push: pressure into the face, a normal force into the face, Flip, a negative pressure, a moment about the face's normal (right-hand rule), gravity | pressure pushes into the face: the tip goes down | -1 | -1 (0 %) | -1 (0 %) | 0 % | PASS |
|  | a negative pressure pulls: the tip goes up | 1 | 1 (0 %) | 1 (0 %) | 0 % | PASS |
|  | Flip on a pressure pulls: the tip goes up | 1 | 1 (0 %) | 1 (0 %) | 0 % | PASS |
|  | a normal force on the top face pushes into it: down | -1 | -1 (0 %) | -1 (0 %) | 0 % | PASS |
|  | a normal force on the end face pushes into it (mm): shortens by F L / E A | -0.005 | -0.004979 (0.417 %) | -0.004982 (0.355 %) | 3 % | PASS |
|  | Flip on a force along -Z: the tip goes up | 1 | 1 (0 %) | 1 (0 %) | 0 % | PASS |
|  | a moment about the end face's normal (+X) turns the top edge to -Y | -1 | -1 (0 %) | -1 (0 %) | 0 % | PASS |
|  | gravity along -Z: the tip goes down | -1 | -1 (0 %) | -1 (0 %) | 0 % | PASS |
| **moved_component**: The cantilever inside a component moved by (120, -40, 35) mm and turned 37 degrees about (1, 1, 0.3): the same numbers as unmoved | largest displacement = unmoved (mm) | 0.09977 | 0.0997 (0.075 %) | 0.1002 (0.049 %) | 1 % | PASS |
|  | unmoved: top stress along the part / (-F/A + M c / I), x 20-80 mm | 1 | 0.9994 (0.057 %) | 1 (0.001 %) | 3 % | PASS |
|  | moved and turned: top stress along the part / (-F/A + M c / I), x 20-80 mm | 1 | 1 (0 %) | 0.9999 (0.01 %) | 3 % | PASS |
|  | reaction = unmoved (N) | 111.8 | 111.8 (0 %) | 111.8 (0 %) | 0.2 % | PASS |
|  | reaction turned with the part (N off (100, 0, 50) in its axes) | 0 | 6.782e-05 (0 %) | 6.586e-06 (0 %) | 0.5 % | PASS |

Finer mesh nearer the hand calculation (every check off by more than 1 % at the default):

| Case | Check | Error default -> finer | Result |
|---|---|---|---|
| cantilever_edge_vertex | edge load: tip deflection (mm) = FL^3/3EI + FL/kGA | 1.324 % -> 0.812 % | PASS |
| cantilever_edge_vertex | two corners sharing 100 N: tip deflection (mm) | 1.324 % -> 0.815 % | PASS |
| cantilever_edge_vertex | 100 N per corner: tip deflection twice the shared one (mm) | 1.324 % -> 0.814 % | PASS |
| clamped_plate | centre deflection (mm) = q a^4 / 64D + q a^2 / 4 kappa G t | 10.52 % -> 0.853 % | PASS |
| clamped_plate | bottom bending stress / plate theory, r < 0.4 a | 6.182 % -> 0.414 % | PASS |
| tube_torsion | von Mises on the outer surface (MPa) = sqrt(3) T r / J | 6.319 % -> 0.004 % | PASS |
| tube_torsion | the free end's rim turns (mm) = T L r / (G J) | 2.819 % -> 0.004 % | PASS |
| shaft_bearing | free end deflection (mm), distributed load on the journal | 1.967 % -> 1.128 % | PASS |

Through the AI tools (study_results' answers only):

| Case | Check | Hand calculation | SciForge (error) | Tolerance | Result |
|---|---|---|---|---|---|
| ai_cantilever | tip deflection (mm) = F L^3 / 3EI | 0.2 | 0.1995 (0.27 %) | 3 % | PASS |
| ai_cantilever | reaction (N) | 100 | 100 (0 %) | 0.5 % | PASS |
| ai_cantilever | lowest safety factor = yield / largest von Mises | 3.504 | 3.504 (0 %) | 0.5 % | PASS |
| ai_cantilever | units named mm, N, MPa | 1 | 1 (0 %) | 0 % | PASS |
| ai_pressure_gravity | 1 MPa on top: tip deflection (mm) = wL^4/8EI + wL^2/2kGA | 0.7577 | 0.747 (1.402 %) | 3 % | PASS |
| ai_pressure_gravity | 1 MPa on 1000 mm2: reaction (N) = 1000 | 1000 | 1000 (0 %) | 0.5 % | PASS |
| ai_pressure_gravity | gravity: reaction (N) = rho V g | 0.7747 | 0.7747 (0 %) | 0.2 % | PASS |
| ai_moment_units | 10000 N mm: the rim turns (mm) = T L r / GJ | 0.008276 | 0.008277 (0.013 %) | 3 % | PASS |
| ai_out_of_date | in date right after the solve | 0 | 0 (0 %) | 0 % | PASS |
| ai_out_of_date | OUT OF DATE after the box grew to 120 mm | 1 | 1 (0 %) | 0 % | PASS |

| Engine check | What is checked | Checks | Result |
|---|---|---|---|
| picks follow their faces through edits | as made: the end (x = 100) bends 0.1998 mm (beam theory 0.2; 2394 nodes); made 140 mm long: the end (x = 140) bends 0.5472 mm (beam theory 0.5488; 1238 nodes); with a slot through its middle: the end (x = 140) bends 0.593 mm (beam theory 0.5883; 1410 nodes); then 120 mm long again: the end (x = 120) bends 0.3689 mm (beam theory 0.3659; 1932 nodes); with the end's top edge rounded: the end (x = 120) bends 0.3689 mm (beam theory 0.3659; 2442 nodes) | 5 | PASS |
| materials stay with their bodies in any order | stretch 0.013379 mm = sum of F L / E A (0.013429); each body's row names its own material | 2 | PASS |
| a thin wall at the default mesh is not silently wrong | default mesh: centre deflection 0.03089 mm vs plate theory 0.03451 (10.5 % off); warned: True; a solid cantilever at the default mesh: no thin-wall note | 2 | PASS |
| reactions add up to the loads | reaction (0.0, -30.0, 194.1196) + applied (0.0, 30.0, -194.1196) = (2e-05, -0.0, -1e-05) (N) | 1 | PASS |
| a force's picks | shared over a face and a corner: refused; shared over a face and an edge: refused; along the normal on an edge: refused; per entity on a face and a corner: the hold takes 2 x 100 N (200); per entity on a plate's top that a glued block splits, and the block's roof: the hold takes 2 x 1000 N (2000) | 5 | PASS |
| reactions of two holds that share an edge, linear elements | Wall + Foot + loads = (-2e-06, 0.0, 0.0) N (loads (0.0, 30.0, -2.1196)) | 1 | PASS |
| reactions on sliding planes | Cut X holds (-2000.1, -0.01458, -4.5955e-13) N (statics (-2000, 0, 0)); Cut Y holds (-0.01458, -2000.1, -1.7967e-13) N (statics (0, -2000, 0)); Ends holds (0.23459, 0.23459, -2.5275e-05) N (statics (0, 0, 0)) | 3 | PASS |
| the bodies of a study of the whole design | eye off: the same bodies; eye off: not out of date; a new body is in the study; a new body hidden is still in it; a body a Combine used up is not | 5 | PASS |
| nothing asks for a recompute after a solve | after the solve; after Keep results in the file off and on; after a study material; after a load changed; those changes leave the results out of date | 5 | PASS |
| along the normal of a curved face | force along a round face's normal: refused; moment along a round face's normal: refused; a force along a vector on it: taken | 3 | PASS |
| out of date after a change that keeps the size | solved: in date; the hole moved from x 30 to 60: out of date; the bar solved: in date; the bar turned a quarter about its axis: out of date | 4 | PASS |
| bodies that touch only along an edge or at a corner | touching along an edge: warned; touching at a corner: warned; a cube on a cube's face: no such warning; a pin in its hole: no such warning | 4 | PASS |
| results kept in and dropped from the file | kept: reopened with its results and the same numbers, in date; dropped: reopened with the numbers only, in date, says solve again; reopened, then the part changed: out of date | 3 | PASS |

### Big parts

A 300 x 200 x 10 mm plate with 120 counterbored holes (366 faces), pressure on its top face,
fixed at one end, solved through `Job` as the Solve dialog does (CalculiX on 2 threads, the
machine shared with five other builds):

| Mesh | Nodes / elements | Gmsh | CalculiX | Whole solve | Longest pause of the window (model / mesh / input / results turn) | Notes |
|---|---|---|---|---|---|---|
| 10 % (the default) | 131 174 / 73 561 | 11 s | 84 s | 112 s | 1.3 / 3.2 / 2.6 / 3.3 s | 286 curved elements made straight-sided; max von Mises 253.4 MPa, max displacement 3.012 mm |
| 2.5 % | 142 756 / 80 047 | 9 s | 106 s | 134 s | 1.7 / 2.8 / 3.1 / 3.0 s | none made straight; 261.1 MPa, 3.031 mm |

Before this build: the same 2.5 % solve froze the window for 84 s writing the input and for
almost 10 minutes reading the results; earlier in this build, with Gmsh's own repair of curved
elements, the default mesh took 268 s in Gmsh (375 s in all) and the window paused up to 7-12 s
while the input was written and the results read (now split over two and three turns). The
times vary by about a fifth from run to run on this shared machine.

The window stays usable: Gmsh and CalculiX run in the background thread, and so do the
reading of the solver's result file and the check of the curved elements; the work on the
document is split in turns of at most about 3 s, so a timer keeps ticking. (The 84 s: FreeCAD
searched the mesh by geometry for the nodes of each picked face; SciForge reads them from Gmsh's
groups. The 10 minutes: the scaffold read the whole displacement list once per node.)

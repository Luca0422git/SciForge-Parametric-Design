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

(builder sim-ui)

## Results

(builder sim-results)

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
Run of 2026-10-27 (`sim-accuracy-qa.json`): 197 checks (154 accuracy rows, 43 engine checks), 0 failed. A row marked "warned" is outside its
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

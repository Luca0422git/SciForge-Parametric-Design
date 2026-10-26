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

<!-- BENCHMARK TABLE -->

How to read it: "Default" is the study's default mesh (10 % of the model size) except where the
case says otherwise; "finer" is the size in the case's own row. Stresses are read away from a
fixed constraint's edge where the formula is for the material inside (beam theory, torsion),
and at the peak where the formula is for the peak (Kt at the hole, Lame at the bore).

### Big parts

A 300 x 200 x 10 mm plate with 120 counterbored holes (366 faces), pressure on its top face,
fixed at one end, solved through `Job` as the Solve dialog does (CalculiX on 2 threads, the
machine shared with five other builds):

<!-- BIG PART TABLE -->

The window stays usable: Gmsh and CalculiX run in the background thread and the solver's
result file is parsed there too; the work on the document is split in turns (the longest
column), so a timer keeps ticking. Before this build the same solve froze the window for 84 s
(FreeCAD searched the mesh by geometry for the nodes of each picked face) and then for almost
10 minutes (the scaffold read the whole displacement list once per node).

You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: Static Stress simulation, the engine (builder sim-core, branch `sf/sim-core`)

Luca first asked for "simulation. stress and flow and shit", then "change the spec, stress-only
sim is fine". Outline 7.18 (read it) is the spec; Fusion's behaviour with sources is in
`docs/sciforge/dev/research/fusion-simulation.md` (read all of it). sim-ui builds the SIMULATION
workspace (dialogs, browser, glyphs, solve dialog) and sim-results the RESULTS tab (colour plot,
legend, deformation, probes); both call YOUR engine, so keep its API stable and tell them (in
your session log and commit messages) what you add.

### What exists (the orchestrator wrote and tested it; read every line)
`sciforge/simulation_core.py` (rules, no FreeCAD: study types, settings and defaults, kinds of
constraints and loads with options and checks, units, materials' gaps, safety factor, stats,
colours, legend, pre-check; unit tests `test_simulation_core.py`) and `sciforge/simulation.py`
(studies and items saved in the design, materials from each body's physical material with gaps
filled, the simulation model = the study's solids in design coordinates, split where bodies touch
so they are glued, picks found again on the model by geometry, FreeCAD's FEM objects made in a
hidden run, Gmsh in a background thread, FreeCAD's CalculiX writer, CalculiX in a background
thread, FreeCAD's .frd reader, the safety factor per node with per-body strength, the result
summary, out-of-date fingerprint, `Job` with poll / wait / cancel, `solve()`). Measured: a
100 x 10 x 10 steel cantilever with 100 N at the tip gives 0.2005 mm (beam theory 0.2000) and
58.9 MPa (60.0) at 2.5 mm elements, about 3 s; two glued bodies of different materials solve with
per-body results. Built kinds: Fixed (all or some axes), Force (normal / vector, per entity),
Pressure, gravity. Two FreeCAD quirks are already handled (see the comments): a force direction
needs a hidden line (a vector set directly is reset by recompute), and Gmsh's groups make
FreeCAD's input writer print an error unless removed.

Research decisions already in the engine: safety factor = yield / von Mises, or ultimate /
1st principal (the study's basis), capped at 15; Pin holds radial and axial by default; the
deformation options of research 5.6 (`simulation_core.DEFORMATIONS`). Research 9.4 maps Fusion's
kinds to FreeCAD FEM objects and 9.5 lists the golden studies: use both.

### What to build
1. **Every Static Stress constraint and load Fusion has** (the research file's lists; at least):
   Pin (round faces: radial / axial / tangential on or off; FreeCAD: `makeConstraintTransform`
   (Cylindrical) + displacement, or your own approach), Frictionless (flat faces: no movement
   along the normal; any orientation), Prescribed Displacement (values per axis), Moment (about an
   axis, on faces: FreeCAD 1.1 has `makeConstraintRigidBody` with moments, or forces arranged as
   a couple; prove it with a hand calculation), Bearing Load (round faces: FreeCAD has
   `makeConstraintBearing`? check; else a sine-distributed pressure written to the input), Remote
   Force (rigid body constraint), and anything else the research marks as a must. Switch
   `"built": True` in `simulation_core` as each one lands; never leave a kind half-working.
2. **Contacts**: bodies that touch are bonded (done); bodies that only nearly touch (within the
   contact tolerance) also bonded (generalFuse fuzzy value: verify); overlapping bodies warned
   (the pre-check says which); Fusion's other contact types (Separation, Sliding...) refused with a
   sentence unless CalculiX contact works reliably here (prove it with a test before offering it).
   Bodies that touch nothing and are held by nothing: the pre-check names them (the summary key
   "loose" is ready in `simulation_core.precheck`).
3. **Mesh**: Fusion's mesh settings (research), Local Mesh Control (smaller elements on picked
   faces / edges: FreeCAD `makeMeshRegion`), a mesh-only run (sim-ui's Generate Mesh shows it
   before solving: add `Job(study, mesh_only=True)` or similar), mesh statistics (nodes, elements,
   smallest / largest), a clear failure when Gmsh cannot mesh (with the faces it choked on when
   Gmsh says) and an automatic retry with Netgen (FreeCAD's `makeMeshNetgen`) before giving up.
   Adaptive mesh refinement (Fusion's study setting): build it if feasible (solve, refine where
   the stress changes fastest, solve again until the max stress changes by less than the setting),
   else document it as a gap.
4. **Robustness and speed**: big parts (200-400 faces, 100 k+ nodes: time it, keep the window
   responsive: everything heavy is in `Job`'s background thread already; meshing a big part may
   need the BREP export in the thread too), the solver's own messages turned into sentences
   (`_solver_failure`; add the cases you meet), cancel at every stage, nothing left behind
   (temporary folders, half-made runs), undo: a solve must not land in the person's undo history
   (check FreeCAD's transactions; sim-ui will call you from a command), saving a solved study and
   reopening it (the results come back: test), the size of a saved design (a fine mesh can add
   many MB: measure; offer a study setting to keep results out of the file if large, like Fusion
   keeping them in the cloud), a design changed after a solve (`out_of_date`), deleting a body that
   a study uses (items lose picks: pre-check), components (bodies inside App::Part components,
   moved components: design coordinates, test).
5. **Accuracy benchmarks** (`SciForgeTests/headless/sim_benchmarks.py`, run by
   `run_tests.sh --only base` or a new `--only sim` entry: add it): cantilever (deflection and
   stress), a plate with a central hole in tension (stress concentration, Peterson's Kt for the
   finite width), a thick-walled cylinder under internal pressure (Lame), a pinned beam or a
   frictionless symmetry plane (half model = full model), a bonded two-material bar in series, a
   moment on a shaft end (torsion: tau = T r / J), gravity on a hanging bar (sigma = rho g L at the
   top), each within a stated tolerance (3-5 %) at the default and at a finer mesh, plus timings.
   These are the evidence outline 0.8 asks for: report the table in the parity doc.
6. **AI tools** (`sciforge/ai/catalog/simulate_tools.py`, `sciforge/ai/actions/simulate_actions.py`):
   create_study, add_constraint, add_load, set_study_material, study_settings, precheck_study,
   solve_study, study_results (min / max / where per result type and per body, the safety
   verdict in a sentence: "lowest safety factor 1.4 at (x, y, z) on Body1: below 2"),
   delete_study (choose names with care: they are permanent). Picks by selectors like the other
   tools (`sciforge/ai/ops/selectors.py`). Headless runner block, docs regenerated, a recipe
   `docs/ai/recipes/static-stress.md` (a bracket: fixed holes, a force, solve, read, thicken, solve
   again) whose calls run in the docs runner.
7. `docs/sciforge/parity/simulation.md` sections "Engine" and "Benchmarks" (sim-ui and
   sim-results write "Setup" and "Results"): what is built, the benchmark table, Known gaps with
   evidence.

Tests: unit tests for everything pure; the benchmarks; one GUI scenario `sim_core_*.py` that
solves through `Job` with the window up (poll from a QTimer, cancel half way, solve again) and
checks nothing is printed as an error.

Session log: `docs/sciforge/sessions/beta3-sim-core.md`. Report as beta3-common says.

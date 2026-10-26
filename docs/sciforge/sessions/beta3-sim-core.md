# Session log: beta 3, builder sim-core (Static Stress engine)

Branch `sf/sim-core` (from `beta3`), 2026-10-26/27. Brief:
`docs/sciforge/dev/briefs/beta3-sim-core.md`. Spec: outline 7.18; Fusion's behaviour:
`docs/sciforge/dev/research/fusion-simulation.md`; parity: `docs/sciforge/parity/simulation.md`
sections Engine and Benchmarks.

## What the engine offers sim-ui and sim-results (nothing of the scaffold renamed or removed)

`sciforge/simulation.py` (document side) and `sciforge/simulation_core.py` (rules, no FreeCAD):

- **Kinds**: every kind in `simulation_core.CONSTRAINTS` / `LOADS` / `MESH_CONTROLS` is
  `"built": True`: constraints fixed (x / y / z), pin (radial / axial / tangential, round
  faces), frictionless (any face; the normal at each node), displacement (x / y / z in mm or
  None); loads force, pressure, moment (direction normal / vector, per_entity, flip), bearing
  (round faces, vector, parabolic, pushes only), remote_force (vector, point); local mesh
  control = category `"mesh"`, kind `"local"`, option `size` (mm), picks faces, edges or whole
  bodies (`(body, "")`). `core.TABLES[category]`, `core.CATEGORIES`.
- **Items**: `add_item(study, category, kind, refs, opts, label)` also for category "mesh".
  Labels are numbered across the whole design ("Fixed 1" in one study, "Fixed 2" in the next):
  FreeCAD keeps labels unique in a document. `clone_study(study)` (Fusion's Clone Study: no
  results).
- **Picks that survive edits**: every pick remembers its shape (item JSON `sigs`, in pick
  order). `resolve_picks(item)` -> `[(obj, [names], moved)]` gives the faces as the design is
  now (FreeCAD's name when it still fits, else found again by shape; FreeCAD marks a pick it
  lost "?Face5" after a Press Pull). `repair_picks(study)` rewrites the references of moved
  picks (the Job does it before a solve and adds a note); call it after an edit if the glyphs
  need the new faces. `lost_items(study)` uses the same rule.
- **Contacts**: `contacts(study)` -> `[(body, body, "bonded")]` (touching or closer than the
  study's `contact_tolerance`, glued at solve time), `overlaps(study)`, `loose_bodies(study)`.
- **Pre-check** adds: loose bodies (error unless Remove rigid body modes), overlapping bodies
  (warning), a face constrained twice (warning), gravity on a material with no density (error),
  Remove rigid body modes (warning with constraints, or that the loads must balance).
- **Settings** (`core.settings`): `remove_rigid` (3-2-1 hold of free pieces), `keep_results`,
  `mesh.size_mm` (absolute size, 0 = use %), `mesh.adjacent_ratio` (growth of local controls),
  `mesh.aspect_ratio` (the limit the statistics count against), `adaptive` (level none /
  low / medium / high / custom, passes, tolerance, portion, result).
- **Job**: `Job(study, mesh_only=False)`; `job.notes` (sentences: constraints that disagree
  on a shared edge, Netgen used, straight-sided elements, picks found again); `job.elapsed`;
  `job.progress` (mesh-only: two stages). A failed or cancelled job keeps the last results and
  removes everything it made (temporary folder too). Nothing a job makes lands in the undo
  history: it closes an undo step left open first (keeping it).
- **Generate Mesh**: `generate_mesh(study)` / `Job(study, mesh_only=True)` keeps the mesh in
  `study.SimMeshRun` next to the last results; `mesh_object(study)` (Generate Mesh's mesh,
  else the last solve's), `mesh_summary(study)` -> nodes, elements, smallest / largest
  element edge (mm), worst_aspect, over_limit, mesher (gmsh / netgen), size, order, made,
  stale. A solve replaces SimMeshRun.
- **Summary** (`summary(study)`) adds `reactions` {constraint label: {x, y, z, total}} (N, the
  force each constraint takes), `notes`, `results_kept`, `adaptive` ({result, passes: [{nodes,
  elements, value}]} when adaptive refinement ran: Fusion's convergence plot data) and mesh
  `smallest / largest / worst_aspect / over_limit / mesher`.
- **Held enough**: `not_held(study)` -> `[(bodies, [free movement in words])]` (the pre-check
  uses it: "Body1 is not held enough: it could still turn about an axis along Y through (10,
  5, 5)"); `simulation_core.free_modes(rows, centre, size)` for a DOF View.
- **Keep results in the file**: `apply_keep_results(study)` (set_settings calls it when
  keep_results changes); `results_dropped(study)`: solved, but the coloured results were not
  saved (reopened with keep_results off): `results(study)` is None then, `summary()` keeps
  the numbers; solve again to see them.
- **Contacts**: `simulation_core.CONTACT_TYPES` (key, Fusion's name, available) and
  `CONTACT_NOT_AVAILABLE` (the sentence for the greyed types).
- **Per-body results** (`summary["bodies"]`): keyed by the body's label, or "Body1 (Bracket)"
  (its component's label added) when two bodies of the study share a label; each row has
  `"name"` (the body's object name). `body_key(study, body)` gives a body's key. (sim-ui's
  report: two components' "Body1" shared one row.)
- **Out of date**: the fingerprints (results and mesh) are taken when the solve starts, so a
  design changed while it runs leaves the results out of date (sim-ui's report;
  `simulation_solve_dialog._keep_out_of_date` is no longer needed but harmless).
- **No VTK pipeline** is made with the results any more (`Pipeline_SimResults` is gone): draw
  from `results(study)` / the result object.

## Log

- 18:05 read the briefs, research, code. Baseline cantilever 0.1995 mm at the default mesh.
- SciForge now writes every constraint itself into CalculiX's input (`*BOUNDARY`,
  `*EQUATION` from `node_constraints`), so a Pin, a Frictionless plane and a Fixed face can
  share nodes; loads other than pressure and gravity are `*CLOAD` lines computed from FreeCAD's
  consistent node areas (`meshtools.get_ref_facenodes_areas`). FreeCAD's force object is no
  longer used: its face loads print "Error on: ..." when the mesh's area differs from the
  face's by 1 % (any curved face with a coarse mesh), which fails every GUI scenario.
- Benchmarks: 11 cases x 2 meshes, all within tolerance (worst: plate with a hole 2.3 % at the
  default mesh with a local control on the hole).
- AI tools (10), recipe, recorded examples; the headless block passes.
- FreeCAD facts: `(obj, [])` in a LinkSubList is dropped (use `(obj, [""])` for a whole
  object); importFrd's result mesh is not in the analysis group (remove it with the run);
  Gmsh's 2D meshing on several threads gives a different mesh each run (SciForge writes
  `General.NumThreads = 1`); FreeCAD's TNP marks a body face pick lost ("?Face1") after a
  SciForge Press Pull.
- 19:00-19:45 big parts. A 366-face plate (120 counterbored holes) at 2.5 % mesh: 142 756
  nodes. Before: the window froze 84 s writing the input (FreeCAD's `getNodesByFace` searches
  every node by geometry: 31 s per face) and 598 s reading results (the scaffold's per-body
  maximum read `result.DisplacementLengths`, a 143 000-value copy, once per node). After:
  model 1.9 s, mesh turn 3.5 s, input 5.8 s, results 7.6 s on the main thread; Gmsh 16 s,
  CalculiX 100 s (2 threads, shared machine), the result file parsed in the background (2.7 s).
  How: Gmsh's groups ("Face12", the reader adds "_Faces" / "_Nodes" suffixes) give the nodes of
  every model face / edge / solid; FreeCAD's pressure writer and Remove rigid body modes use
  them through a patched `meshtools.get_femnodes_by_refshape`; the writer's unused second
  mesh-sets getter is skipped; von Mises / principal stresses with numpy (FreeCAD loops per
  node); no VTK pipeline.
- FreeCAD facts: `obj.Shape` is read-only in 1.1 (`copy(False)` shares the geometry and can be
  re-placed); freecadcmd crashes in PySide at exit when a FreeCAD GmshTools (it owns a QProcess
  with a connected signal) is still referenced: drop it when done.
- 20:00-20:20 the default mesh of the same plate took 268 s in Gmsh (10 % size; 6 %: 334 s),
  2.5 % only 16 s: Gmsh's high-order optimisation (`HighOrderOptimize`, which SciForge had
  switched on so curved elements would not turn inside out at small holes) merged the 278 bad
  elements into patches of 15 000 elements. Without it Gmsh takes 10 s; its other modes do not
  help (elastic: 31 s and 137 elements still inside out; fast curving: none fixed; fewer
  layers / passes: 148 s). Now SciForge checks every curved element of the solver input where
  CalculiX integrates it (and at its corners and middle), in the background thread before
  CalculiX starts, and makes only the elements inside out or nearly (Jacobian below 1 % of the
  straight element's) straight-sided, with a note ("SciForge made 12 curved mesh elements
  straight-sided ..."). Straightening every element below Gmsh's own 10 % aim made a coarse
  shaft 18 % too soft in torsion (each straight element flattens a bit of the curved face);
  the 1 % rule: 1.2 % at the default mesh, 0.01 % at the finer one. The plate solves in 115 s
  instead of 375 s. The straight-sided retry stays as the fallback.
- Fixed in review: a mesh made again after a failed solve looked for Netgen's old mesh when
  Netgen had been used (Gmsh is tried first again now); switching Keep results in the file made
  the results out of date (it changes nothing they say).
- 20:35-20:50 the window's longest pause on the 131 000-node part: 2.7 s (was 6.8-11.6 s): the
  input is written over two turns (FreeCAD's mesh tables first), the results read over three
  (FreeCAD's import with the renumbering of its result mesh moved to a turn of its own, then
  the summary); displacement lengths and the result statistics with numpy. sim-ui's two open
  engine issues fixed (per-body rows of same-named bodies, fingerprints from the solve's
  start), each with an engine check.
- 20:50-21:05 the pre-check of 20 stacked plates with holes took 5.8 s (contacts 4 s, overlaps
  2 s: OpenCASCADE's distance and common of every touching pair), and sim-ui runs it after every
  SETUP command. Contacts and overlaps are now remembered per geometry (each body's shape hash,
  face / edge / corner counts, box and place, its component's place, the tolerance): 0.2 s
  after the first time; a moved or edited body is seen at once (engine check). Only checking
  the faces near the other body did not make OpenCASCADE's distance faster.

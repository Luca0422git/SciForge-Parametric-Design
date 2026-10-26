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

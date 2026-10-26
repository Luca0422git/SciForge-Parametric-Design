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
- 20:20-20:30 the window's longest pause on the 131 000-node part: 2.7 s (was 6.8-11.6 s): the
  input is written over two turns (FreeCAD's mesh tables first), the results read over three
  (FreeCAD's import with the renumbering of its result mesh moved to a turn of its own, then
  the summary); displacement lengths and the result statistics with numpy. sim-ui's two open
  engine issues fixed (per-body rows of same-named bodies, fingerprints from the solve's
  start), each with an engine check.
- 20:45-20:50 the pre-check of 20 stacked plates with holes took 5.8 s (contacts 4 s, overlaps
  2 s: OpenCASCADE's distance and common of every touching pair), and sim-ui runs it after every
  SETUP command. Contacts and overlaps are now remembered per geometry (each body's shape hash,
  face / edge / corner counts, box and place, its component's place, the tolerance): 0.2 s
  after the first time; a moved or edited body is seen at once (engine check). Only checking
  the faces near the other body did not make OpenCASCADE's distance faster; its section does
  (two bodies whose boundaries cross touch: 0.06 s instead of 0.19 s a pair), and only those
  are tested for overlap: contacts and overlaps together 3.5 s instead of 6 s the first time.
- 20:50-20:55 the pre-check of the big plate fixed at its 120 holes took 8 s: every pick made
  its own copy of the 366-face shape (27 ms each) to compare its remembered shape. The copy is
  now made once per object and call, and remembered per shape: 0.4 s.
- 20:55-21:15 a solve of 20 stacked plates with 25 holes each: the model turn took 16 s (the
  pre-check's first contacts 7 s, the general fuse 1.3 s, and 2.3 s working out which body
  each piece of the model came from). That last part was also **wrong** in a case: it went by
  each piece's centre of mass, and a plate with a hole in its middle has it in the hole, nearer
  a plate glued on it; that plate's material then went to both (engine check "a body whose
  middle is a hole, glued to another": the old rule gave both pieces to the upper plate). Now
  the general fuse's own history says which body each piece came from (exact and instant), and
  the model stage is two turns (pre-check, then the model). The same stack at the default mesh
  needs over 6 GB in CalculiX (stopped after 9 minutes): a big model is still big.
- 21:15-21:25 integration check (nothing merged): `sf/sim-results` (which holds sim-ui's work
  too) exported to a scratch folder with this branch's `simulation.py` / `simulation_core.py`
  on top: the simulation unit tests (129) and eight of their GUI scenarios pass
  (sim_setup_bracket 74, sim_setup_components 36, sim_setup_kinds 52, simres_cantilever 80,
  simres_out_of_date 32, simres_reopen 21, simres_adaptive 16, simres_inspect 93 checks).
- 21:25-21:30 a design saved while a solve ran kept that solve's half-made run (its mesh too)
  in the file for good: nothing linked it, nothing removed it. A solve now removes such left
  overs first (objects of a solve that no study links and no running job is making; engine
  check "a design saved while it solves").
- 21:30 an undo step someone opened between two turns of a solve (a command run between
  the timer's ticks) took in what the next turn made (the result objects, the mesh): undoing it
  took the results away. Every turn now closes such a step first (keeping it), except when a
  cancel removes a run (a dialog's own step must stay open for its Cancel; sim-ui does not
  poll while a dialog is open). Engine check "undo steps opened while it solves" (fails
  without the change).
- 21:33 a study material later deleted from the materials made the study fall back to the
  body's own material without a word; the pre-check now warns (engine check).
- 21:35 solve_study from the AI froze the window for the whole solve (the AI's tools run on the
  window's thread). It now lets the window repaint and run its timers while the solve's
  programs work (`Job.wait(timeout, idle=...)`; no mouse or keys meanwhile, so nothing changes
  the design under it). GUI scenario sim_core_job step F: 38 timer ticks during a 5.8 s solve.
- 21:38 the model turn of the plate fixed at its 120 holes took 7.6 s: mapping each pick onto
  the model asked every model face for its box (120 x 366 times). The model's faces and boxes
  are now listed once per solve: 3.3 s.
- 21:43 linear elements: the steel cantilever bends 0.082 mm at the default mesh (beam theory
  0.200; 0.161 at 3 %): linear tetrahedra lock in bending, as everywhere. The pre-check now
  warns when a study uses them (Fusion's help says parabolic is the accurate choice).
  Integration again with the latest engine: sim_setup_dialogs 76, sim_setup_workspace 43,
  simres_linear 27 checks pass.
- 21:45-21:50 a 3 mm plate (200 x 100 mm) at 2 % mesh failed: "distorted elements". Gmsh left
  a flat sliver element (corners nearly in one plane, 0.0002 mm3), and FreeCAD's "Coherence
  Mesh" (merge nodes closer than a millionth of the model's size, 0.0002 mm here) made its two
  diagonals' middles (0.00006 mm apart) one node: an element with a node twice, which CalculiX
  refuses. The study's bodies share their faces through the general fuse, so the mesh needs no
  merging: it is off now (every benchmark gives the same nodes and numbers; the plate solves,
  its tip between beam and plate theory: engine check "a thin plate at a fine mesh").
- 21:50-22:00 awkward shapes (scratch "torture" run: a 1 mm-wall tube, an L bracket with a
  1 mm fillet, a sphere, a box with a 0.01 mm step):
  - The tube fixed at its end ring was refused as "not held enough: it could still turn about
    an axis along X": the held-enough check sampled the ring with a grid over its parameter
    square, which missed the 1 mm ring entirely, leaving its two seam corners on one line.
    Faces are now also sampled along their edges.
  - The L bracket's L-shaped end face "lost what it was on" at the solve: every probe spot
    and the centre of mass of the L lay outside it. More spots, then points along its edges.
  - The tube at the default size (20 mm elements, 1 mm wall) failed in Gmsh ("a segment and a
    facet intersect": the two walls' coarse triangles crossed) and in Netgen. SciForge now
    meshes again with elements half as big (at most twice) when Gmsh's surface mesh crosses
    itself, with a note; the failure sentence says thin walls need smaller elements (it said
    "larger"); Gmsh's error summary lines are no longer quoted as the reason.
  - A note when many elements are stretched far past the aspect ratio limit (the tube: 789 of
    2192, the worst 131:1; its axial stiffness is then 11 % too high).
  Engine checks "a thin tube at the default mesh"; unit tests for the new rules.

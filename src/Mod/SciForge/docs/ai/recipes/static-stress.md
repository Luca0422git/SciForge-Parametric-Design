# Recipe: is this bracket strong enough? (Static Stress)

Tags: simulation, stress, study, safety factor, bracket, constraint, load, beginner

An L bracket held by the two screws in its base, with 1000 N pushing on the top of its
upright: a Static Stress study says whether it bends for good (the safety factor), how much it
moves and where the stress is highest. Then the upright is made thicker and the study is
solved again. Every call below was run by SciForge's tests; the `expect` part of each call is
what the answer must contain, not a tool argument.

This is Fusion's SIMULATION workspace: a study, its constraints (where the part is held) and
loads (what pushes on it), a solve and the results. SciForge solves on this computer
(Gmsh meshes, CalculiX solves) in seconds; the results are a guide: linear static, small
deflections, a material that stays elastic and is the same in every direction (a 3D-printed
part is not).

## 1. The bracket

The same L bracket as [the bracket recipe](sciforge://docs/recipes/bracket.md): a 60 mm wide
L of 5 mm plate, 40 mm base and 40 mm upright, with two 6.5 mm holes in the base.

```json sciforge-calls
[
  {"tool": "new_design", "args": {"name": "BracketStress"}},
  {"tool": "create_sketch", "args": {"plane": "YZ", "geometry": [
    {"polyline": [[0, 0], [40, 0], [40, 5], [5, 5], [5, 40], [0, 40]]}]},
   "expect": {"contains": ["Its id is 'Sketch1'"]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 60},
   "expect": {"contains": ["Its id is 'Extrude1'", "22500 mm3"]}},
  {"tool": "create_sketch", "args": {"plane": "XY", "offset": 5, "geometry": [
    {"circle": [15, 25, 3.25]}, {"circle": [45, 25, 3.25]}]},
   "expect": {"contains": ["Its id is 'Sketch2'"]}},
  {"tool": "hole", "args": {"sketch": "Sketch2", "diameter": 6.5, "through_all": true},
   "expect": {"contains": ["Its id is 'Hole1'"]}},
  {"tool": "physical_material", "args": {"body": "Extrude1", "material": "aluminium_6061"}},
  {"tool": "check_design", "args": {}, "expect": {"json": {"ok": true}}}
]
```

## 2. The study: held at the holes, pushed at the top

[create_study](sciforge://docs/reference/create_study.md) makes a Static Stress study of every
body. The screws hold the bracket by its two holes: a **fixed** constraint on both round faces
(the selector picks every cylinder of radius 3.25 mm, count 2). The load is a **force** of
1000 N on the upright's top face, pushing along +Y (towards the base's far edge). Before
solving, [precheck_study](sciforge://docs/reference/precheck_study.md) says whether anything
is missing, like Fusion's Pre-check light: ready, caution or cannot solve.

```json sciforge-calls
[
  {"tool": "create_study", "args": {"label": "Bracket 1 kN"},
   "expect": {"contains": ["(id 'SimStudy')"]}},
  {"tool": "precheck_study", "args": {},
   "expect": {"json": {"verdict": "cannot solve"}}},
  {"tool": "add_constraint", "args": {"kind": "fixed",
    "on": [{"face": {"type": "cylinder", "radius": 3.25, "count": 2}}]},
   "expect": {"contains": ["Fixed 'Fixed 1'"]}},
  {"tool": "add_load", "args": {"kind": "force",
    "on": [{"face": {"normal": [0, 0, 1], "at": {"axis": "z", "value": "max"}, "count": 1}}],
    "magnitude": 1000, "direction": "vector", "vector": [0, 1, 0]},
   "expect": {"contains": ["Force 1000 N"]}},
  {"tool": "precheck_study", "args": {},
   "expect": {"json": {"verdict": "ready", "constraints": ["Fixed 1"], "loads": ["Force 1"]}}}
]
```

## 3. Solve and read the results

[solve_study](sciforge://docs/reference/solve_study.md) meshes and solves (a few seconds) and
answers the main numbers. [study_results](sciforge://docs/reference/study_results.md) has all of
them: the minimum and maximum of every result with where they are, per body, the reaction
force at each constraint, and the verdict against a target safety factor (2 here). The
holes carry the whole 1000 N, so the reaction at Fixed 1 is 1000 N. The highest stress, about
267 MPa von Mises, is at the edge of a screw hole on the base's top face: the base bends
between the holes and the upright. Aluminium 6061 yields at 276 MPa, so the lowest safety
factor is about 1.03: below the target 2, and only just above 1 (below 1 it would bend for
good). The top of the upright moves about 1 mm.

A fixed constraint holds its faces perfectly rigid, which no real screw does, so the stress
right at the edge of a fixed face is higher than in reality and grows as the mesh gets finer
(Fusion's results do the same). Judge a design by the stress a little away from such edges,
or hold the part the way it really is held.

```json sciforge-calls
[
  {"tool": "solve_study", "args": {},
   "expect": {"contains": ["Bracket 1 kN solved", "Lowest safety factor"]}},
  {"tool": "study_results", "args": {"target": 2},
   "expect": {"json": {"out_of_date": false, "reactions.Fixed 1.total": [1000, 1],
     "safety.lowest": [1.03, 0.1], "results.von_mises.max": [267, 27],
     "results.displacement.max": [1.0, 0.1]}}}
]
```

## 4. Make the plate thicker and solve again

The safety factor is below the target, so the bracket gets 3 mm thicker, base and upright
(8 mm plate): [press_pull](sciforge://docs/reference/press_pull.md) moves the base's bottom
face down and the outside face of the L back. The study now shows **out of date**: the
design changed since the solve. Its fixed holes and the loaded face are still there, so
solving again needs no new picks (SciForge finds a pick again by its shape when an edit
renames the faces, and says so in the answer's notes). Bending stress falls with the square
of the thickness: the stress roughly halves, the safety factor doubles past the target and
the upright moves about a third as much.

```json sciforge-calls
[
  {"tool": "press_pull", "args": {"faces": {"normal": [0, 0, -1], "count": 1}, "distance": 3}},
  {"tool": "press_pull", "args": {"faces": {"normal": [0, -1, 0], "count": 1}, "distance": 3}},
  {"tool": "study_results", "args": {},
   "expect": {"contains": ["OUT OF DATE"], "json": {"out_of_date": true}}},
  {"tool": "solve_study", "args": {},
   "expect": {"contains": ["Lowest safety factor", "meets 2", "found again"]}},
  {"tool": "study_results", "args": {"target": 2},
   "expect": {"json": {"out_of_date": false, "reactions.Fixed 1.total": [1000, 1],
     "safety.lowest": [2.18, 0.2], "results.von_mises.max": [127, 13],
     "results.displacement.max": [0.29, 0.03]}}},
  {"tool": "check_design", "args": {}, "expect": {"json": {"ok": true}}}
]
```

## Variations

- **Gravity**: `study_settings {"gravity": true}` adds the part's own weight (off by default,
  as in Fusion); the part needs a material with a density.
- **A pin instead of screws**: `add_constraint {"kind": "pin", ...}` on a round face lets the
  part turn about it (radial and axial held, tangential free, Fusion's default).
- **A finer mesh where it matters**: `local_mesh_control` on the corner faces, or
  `study_settings {"mesh_size": 5}` for the whole part; solve again and compare the numbers:
  when they barely change, the mesh is fine enough.
- **Another material for this study only**: `set_study_material {"body": "Extrude1",
  "material": "steel"}` (the design keeps aluminium).
- **Symmetry**: half a symmetric part with a `frictionless` constraint on the cut face gives
  the same results with half the mesh.

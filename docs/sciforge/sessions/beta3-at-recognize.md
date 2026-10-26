# Session log: beta 3, Auto Timeline recognition (builder at-recognize, `sf/at-recognize`)

2026-10-26/27. Brief: `docs/sciforge/dev/briefs/beta3-at-recognize.md`. Contract:
`sciforge/recognize.py` (`describe(shape, options)`), implemented exactly; nothing renamed.

## What was built

- `sciforge/recognize.py` (FreeCAD, no Qt): `describe()`. Faces and topology (kind, plane,
  axis, radius, concave, smooth edges) -> holes (bores with their ends: open, flat bottom,
  drill point, counterbore, countersink; both-end recesses) -> fillets (tangent round faces,
  chains per radius; ribs' curved edges and two-direction sheet bends excluded) -> chamfers
  (one or two distances) -> defeaturing (holes closed by their rims, then OpenCASCADE's
  `defeaturing` by halves) -> base (prismatic along X / Y / Z with levels, bosses, cuts,
  drafts, shells; or a revolve) -> plan (Fusion's order, ids and "uses", catalogue-checked) ->
  unrecognized, confidence, notes. Parts turned away from the origin: read in their own frame,
  plan ends with a free `move_copy`.
- Later in the session: each boss / cut piece is read along the axis its open side faces (a
  VEX-like channel reads as its U profile along X with through-all square holes and two
  patterns); cuts that open onto round faces (keyways, flats) and bosses on round faces (a
  port on a pipe); holes into a hollow get a depth instead of through all; coaxial bores with
  material between them are separate holes; drafted pockets in a straight block; touching
  regions in separate sketches; the readings compared by steps, then by the volume the steps
  add or take (a round boss on a block reads as a boss along Z); axes where some faces belong
  to features along another axis are tried only when no axis fits every face.
- Then, from real files: repeated openings become one cut and a pattern (a VEX plate), moved
  copies of a piece are read once, drafted blocks with a cavity (molded boxes), chamfers on
  round edges (narrow cones), holes with a rounded rim, arcs that miss each other by noise,
  idempotent snapping, a volume check on defeaturing, free-form parts not defeatured, a time
  budget, guarded curve / surface types, each plan stage on its own.
- Last: rods and tubes that end in an eye (FreeCAD's example assembly has four, placed at
  angles): in a reading where a feature along another axis crosses the base's end levels, the
  base extrude may stop inside it, at a level or at the feature's middle, and the eye is a boss
  of its own along its axis; a bore that ends on a round face inside the part (a tube's bore
  that stops at its eye) is no hole: it stays in the base's profile. When no base is read, a
  note names the axis most of the part fits and lists the faces that do not. Turned parts about
  a line parallel to X, Y or Z away from the origin (a torus, a dome on a spot of a block) are
  revolved about a construction line drawn on the offset sketch.
- Not mine but touching my file: the QA builder (`sf/autotimeline-qa`) added modelled-thread
  handling and two speed-ups to `recognize.py` on its branch and merges mine regularly; `git
  merge-tree` of the two branches shows no conflict (checked at the end).
- `sciforge/recognize_core.py` (pure Python): snapping, "nice" rounding of measured values,
  origin planes, 2D loops (clean-up, areas, create_sketch items that close exactly), patterns
  (grid / circle / row), the plan's ids, extents, frames and Euler angles, mesh helpers
  (circle / cylinder fits, arcs fitted on a polygon, ideal pattern points).
- `sciforge/recognize_mesh.py`: `describe_mesh(mesh)`.
- `SciForgeTests/unit/test_recognize_core.py`, `SciForgeTests/headless/recognize_bench.py`,
  `run_tests.sh --only recognize` (also run at the end of `--only headless` / `base`).
- `docs/sciforge/parity/auto-timeline.md`, section "Recognition" and my lines in "Tests".

## FreeCAD / OpenCASCADE facts learned

- `shape.defeaturing(faces)` (BRepAlgoAPI_Defeaturing) works on holes, fillets and chamfers,
  but costs about 75 ms per removed face: 294 holes took minutes. Closing a hole by rebuilding
  the faces that carry its rim (`Part.Face(face.Surface, face.OuterWire).cutHoles(other
  inner wires)`) and sewing `Part.Solid(Part.Shell(faces))` takes milliseconds, and the
  untouched faces stay the same TShape (sub-shapes of the new solid: `defeaturing` can still
  take fillets off it).
- A boolean fuse of 294 exact cylinders into a plate (coincident walls) took 3.9 s.
- `Face.normalAt` on a face with hundreds of inner wires costs ~1 ms per call: use the plane's
  known normal.
- Sketch closing tolerance is 1e-7 mm: a line end written with 6 decimals misses an arc end
  computed from its angles (4e-7 seen). Lines next to arcs must take their ends from the arc's
  own `cx + r cos(a)` arithmetic.
- SciForge's extrude taper: positive widens along the extrude direction (golden
  `extrude_taper_cut` narrows a downward cut with -10).
- Stock FreeCAD's LinearPattern with two directions has the Spacings2 bug (core patch #4):
  `rectangular_pattern` (sciforge/pattern.py) works around it, the core `pattern` tool's
  second direction does not on stock FreeCAD.
- The Hole tool picks its direction by looking for material at each centre: a recess drilled
  after the through hole at the same centre finds none and drills into air; give `flip` and
  drill the recess first.
- OpenCASCADE's fillet builder (ChFi3d_Builder::Compute) segfaulted on the outer bend edges of
  golden `sheetmetal_edge_flange_adjacent_later` (bends along X and Y meeting at a relief
  corner): a plan step must not lead there (those bends now stay in the base).
- Chamfer two distances: SciForge measures distance 1 on `shape.ancestorsOfType(edge,
  Part.Face)[0]` (blend.reference_face).
- `pkill -f` with a pattern that appears in the command line kills your own shell (exit 144).
- `shape.BoundBox` is padded by the tolerances (a 10 mm part reads 10.000025 after a STEP round
  trip); `shape.optimalBoundingBox(False, False)` is the tight box.
- `solid.isInside(p, tol, True)` and `solid.isInside(p, tol, False)` together tell a point on
  the surface (True / False) from one inside (True / True) or outside (False / False): that is
  how a boss or cut piece's open side (where it meets the part, or the air) is found.
- A `create_sketch` whose loops touch at a point (two regions sharing a corner) made a cut that
  took nothing off: such regions go in sketches of their own.
- Some golden models (`sf_gear_*`, modelled `thread_*`) take minutes to build: the sweep skips
  them.
- Real STEP files from other programs (the repository's `data/tests/Step`, `Mod/Idf/Idflibs`,
  the Pi 5 case) split a full bore in two half faces: the hole reader sums the halves; the
  bench's face check (kind, area, centre) then fails although the rebuild is exact, so the
  real-file sweep also compares surface by surface.
- One FreeCAD run of the real-file sweep grew to 13.5 GB and was killed by the out-of-memory
  killer (the machine has 16 GB for every builder): my scratch runners now set `ulimit -v 7000000`.
- OpenCASCADE's defeaturing took 48 s for 26 chamfers / fillets on a 434-face connector
  (`TSM_103_01_L_DV_A.stp`): a single call cannot be interrupted, so describe() keeps a time
  budget (30 s) for what comes after, and skips defeaturing for parts with free-form faces (their
  base cannot be read anyway: the forged lever `Schenkel.stp` went from 26 s to 1.6 s).
- `core.snap` snapped an already snapped offset again (-3.459989 -> -3.45999: exactly 1e-6
  away passed the `<= 1e-6` test), so a base ended 1e-6 before the boss on it started and the
  boss became a body of its own. Snapping is now idempotent (a unit test).
- `Part.ShapeUpgrade` in FreeCAD 1.1.4 has only `UnifySameDomain` (no `ShapeDivideClosed`).
- Two tangent arcs of a part in `AssemblyExample.FCStd` missed each other by 5e-7 mm, more than
  the sketch's 1e-7 closing tolerance ("no closed area"). Arcs that meet are now moved by that
  noise onto one shared point (the centre put on the perpendicular bisector of the two ends).
- `edge.Curve` raises `TypeError: undefined curve type` for some edges of the CAM demo part
  `hole_puzzle.fcstd` (and so does `selectors.edge_type`): every curve / surface type check in
  recognize.py goes through a guarded helper, and each plan stage fails on its own.
- A "chamfer" found on the slanted side of a groove made the defeaturing fill the groove
  (+15 % volume, a wrong plan): a feature is now taken off only when the volume changes by about
  what such a feature holds. `_hole_void` counted both halves of a split bore as whole bores.
- OpenCASCADE's defeaturing of 98 fillet faces: 14.4 s at once; in chunks of 49, 11 s for the
  first chunk alone (and the faces of the rest must be found again): at once is fastest.
- `edge.discretize(n)` with two different n gives two different "tops" of a 3D curve (the rim of
  a bore that meets a round face): the hole reader found the bore's end with 24 samples and
  looked for the faces at that end with 12, found none and called the end open. Both use 24 now.
- OpenCASCADE's defeaturing crashed FreeCAD (a segfault in `BOPAlgo_PaveFiller`, out of memory
  under my 7 GB limit) on `data/tests/ModelRefineTests/refine_breaks_cylinder.brep`: the reader
  had taken the 41 pieces of its split outer wall (r 30) for a fillet. Pieces of one round wall
  that together go half way round or more are no fillet now (their arcs are joined, so a fillet
  in stacked pieces still is one). The same part's central bore, crossed by a ring of 13 slots,
  then took 181 s (266 s on the refined copy) in one defeaturing call: a hole whose faces meet
  more than 16 other faces is left in the base without trying (7 s for the whole describe()).
- The BREP files in the repository (FreeCAD's model-refine test shapes: unrefined booleans, two
  3D-printer parts) were swept too: 27 solids, 18 rebuilt exactly, no crash after the fix
  above. The Y rod mount's root fillets (r 3.997) were made before the opening in its plate cut
  them short: the plan rounds edges last, OpenCASCADE refuses the fillet there (a Known gap).
- The QA builder found that `Face.cutHoles` answers None (it changes the face in place):
  `_drop_holes` took the answer, so every face that keeps another loop failed and its holes
  went to defeaturing; I took their fix and fixed the same mistake in `_fill_copies`.
- `face.normalAt(u, v)` counts the face's orientation (the outward normal of the solid), and
  `face.Surface.parameter(point)` gives the (u, v) of the surface point nearest any point: that
  tells a floor that faces back into a bore from an opening that faces out.

## Tests

- `tools/sciforge/run_tests.sh --freecad /home/user/fc/freecad --only base` on my branch, the
  final run (23:29-23:36 UTC, the code of 6408c0c4, after the container restart): **all
  passed**. Unit tests 2524 (9 skipped), golden models 614 pass + 2 xfail (expected), headless AI
  tools 284 calls 0 failed (117 tools), documentation examples 141 items 0 failed, AI agent end
  to end (MCP) 81 checks 0 failed, **recognition benchmark 67 parts 0 failed**, GUI smoke 79
  checks, journey 25, restarts 8 + 9. (A run started just before was killed by the restart.)
- After the last change (turned parts about an offset axis line, 38089c8c): the recognition
  benchmark again, 69 parts, 0 failed (the torus and the dome added), and the sweeps below.
- Earlier, `--only base` at 21:59-22:11 UTC (the code of e59e4f28): the same stages all passed
  but the unit stage, whose two AI-docs contract tests failed on a stale generated copy of the
  parity doc (`docs/ai/user/parity/auto-timeline.md`): after every edit of the parity doc,
  `tools/sciforge/make_ai_docs.py` must be run (then `--only unit` passed: 2519 tests).
- `SciForgeTests/unit/test_recognize_core.py`: 56 tests, OK (5 new: where a base extrude may end).
- Recognition benchmark (`--only recognize`): 54 parts built from golden steps or my own (the
  VEX-like channel, plate and angle, a keyed shaft, a pipe with a port, a clevis, opposed blind
  holes, a shaft collar, chamfered round edges, a link rod, the 300-face plate...), sent through
  STEP and back, described, rebuilt by the headless AI executor: every one within 0.1 % volume
  with every face matched; 9 real solids (4 STEP files from other programs, 3 parts of FreeCAD's
  example assembly placed at angles, 2 BREP parts) face by face or surface by surface; 5 meshes;
  the contract on odd input, with the BREP part that crashed FreeCAD answered in under 30 s.
  Table: the parity doc's Benchmark section.
- Scratch sweeps (not in the suite), with the final code: 601 golden models tried, the 505 that
  build one solid described, 408 rebuilt exactly (391 earlier in the session), 422 with
  a base read, 0 crashes, no regression between runs; 71 solids of 36 real files: 23 exact
  (19 before the rods with an eye), 12 exact with faces split in the file, 4 within 1e-7 of the
  volume, 1 step stopped (a fillet selector), 31 base not read (said so); 27 BREP solids: 18
  exact, no crash.

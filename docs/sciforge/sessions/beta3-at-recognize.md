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

## Tests

(see the parity doc's Tests section for the final numbers)

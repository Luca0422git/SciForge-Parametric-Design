You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: Auto Timeline, feature recognition (builder at-recognize, branch `sf/at-recognize`)

Luca: "Using a connected AI, I want there to be the tool necessary for the AI to reverse engineer
premade models and make them parametric. That means mesh to parametric, or objects with no
timeline to have a timeline. In my testing, Claude opus 5.5 was able to reverse engineer a pretty
complicated model. So current frontier models are capable. But I want to make it easier. A tool
call and instructions on how to reverse engineer a model would be cool. or however you think is
easier/faster/efficient. ... for non complex parts, i want a nicer option to make real parametric
objects."

Fusion has no such tool (its Mesh to BRep gives a featureless body): this is **beyond Fusion**.
Your half is the engine that READS a featureless solid and writes the plan; builder at-tools
makes the AI tools, the reference / compare, the right-click command and the docs around it, and
calls your `recognize.describe(shape, options)` (contract in `sciforge/recognize.py`: implement
exactly that dict; never rename it).

### What to build
1. `sciforge/recognize_core.py` (pure Python, unit tested in `test_recognize_core.py`): grouping
   and pattern logic on plain numbers (rectangular / circular / linear patterns of equal holes or
   bosses, with count, spacing, angle; tolerant to tiny float noise), plan ordering (Fusion's order:
   base shape, cuts and bosses, holes, patterns, chamfers, fillets last; each step names the
   features it makes), 2D profile clean-up (loops of lines and arcs: merge collinear lines, snap
   near-equal values, keep loops closed), turning profiles into `create_sketch` /
   `create_curve_sketch` arguments (read those tools' schemas in `sciforge/ai/catalog/sketch_tools.py`
   and `core_tools.py`; the plan's args must pass the catalogue's own check, `kit` / `registry`).
2. `sciforge/recognize.py` (FreeCAD, no Qt), `describe()`:
   - **Summary**: volume, area, bbox, size, counts, surface census.
   - **Defeaturing**: the base shape without fillets, chamfers and holes (OpenCASCADE's
     defeaturing through FreeCAD: `shape.defeaturing(faces)`; check it on each feature, fall back
     to one feature at a time, then to leaving the feature in place), so the base profile has
     sharp corners and simple lines.
   - **Base**: prismatic (one direction such that every flat face is parallel or square to it and
     every round face runs along it): the extrude direction, the sketch plane (an origin plane
     when it is one, else a face), the profile = section of the defeatured base, the distance;
     stacked levels (a plate with a raised boss, a pocket) become further extrudes (join / cut)
     with their own profiles. Revolved (every face a surface of revolution about one axis): the
     half profile and a revolve. Plain primitives (box, cylinder) may use the `primitive` tool.
   - **Holes**: inner round faces (concave), diameter, axis, start face, depth, through or blind,
     counterbore / countersink (coaxial round + cone faces), drill point; as `hole` tool calls
     (read its schema: placements, types) or as sketch circles + cut when the hole tool cannot
     express it.
   - **Fillets and chamfers**: blend faces (round faces tangent to both neighbours; constant
     radius), chamfer faces (narrow flat faces between two faces: one or two distances, angle);
     the edges to round as selectors on the REBUILT part (its sharp edge where the two faces
     meet), grouped by radius / distance (one `fillet` call per size).
   - **Patterns**: equal holes / bosses / pockets on a grid, a circle or a line, as `pattern`
     calls when the AI tools can express it (else repeat the feature with a note).
   - **What it cannot read** (free-form faces, variable fillets, threads, text): listed in
     "unrecognized" with selectors and a sentence, never guessed.
   - **Confidence** from how much of the area and volume the plan explains.
3. **Meshes** (`sciforge/recognize_mesh.py`): Luca: "mesh to parametric ... for non complex
   parts". Turn a mesh body into something describe() can read: SciForge's own mesh-to-solid
   (`sciforge/insert.py` `solid_from_mesh(mesh, "Prismatic")` merges coplanar triangles into flat
   faces), then find the round regions (strips of thin flat faces that lie on one cylinder: fit
   the cylinder by least squares and give its radius / axis), so a meshed plate with holes gives
   "hole diameter 6 at (x, y)". FreeCAD's Mesh and ReverseEngineering modules are in the AppImage
   (segmentation by curvature, plane / cylinder / sphere fitting): use them if they help. Answer
   the same dict (with a note that the numbers come from a mesh, rounded sensibly: a 5.98 mm hole
   in a mesh is reported as 6 with the measured value beside it).
4. **Benchmark** (`SciForgeTests/headless/recognize_bench.py`, run by `run_tests.sh --only base`
   or its own `--only recognize` entry in the script: add one): take at least 20 golden models
   (`SciForgeTests/golden/models/`: brackets, plates with hole grids, flanges, enclosures, revolved
   knobs, shafts...), build each, export its solid to STEP, import it back as a featureless body
   (`step_import.import_file`), describe() it, and check: the features found match the model's
   steps (hole count and diameters, fillet radii, base kind), and **executing the plan through the
   headless AI executor rebuilds a solid within 0.1 % volume of the original with every face
   matched** (use `sciforge/ai/headless.py`'s executor the way `SciForgeTests/headless/runner.py`
   does; rebuild.compare once at-tools has it, your own volume / face check meanwhile). Report per
   model: found, plan length, rebuilt match, time. Also 3 STL meshes of simple golden models
   through recognize_mesh.
5. Speed: describe() on a 300-face part in under 5 s on this machine (measure; say what you got).

### Tests
Unit tests for every pure function; the benchmark above; a parity doc section "Recognition" in
`docs/sciforge/parity/auto-timeline.md` (what is recognized, with examples and the benchmark's
table; Known gaps). No GUI scenario is needed for your half (at-tools makes the GUI entry).

Session log: `docs/sciforge/sessions/beta3-at-recognize.md`. Report as beta3-common says.

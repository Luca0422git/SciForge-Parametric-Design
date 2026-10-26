# Parity spec: Auto Timeline, rebuilding a part with a timeline (beta 3)

Luca (2026-10-26): "Using a connected AI, I want there to be the tool necessary for the AI to
reverse engineer premade models and make them parametric." Fusion has no such tool (its Mesh to
BRep gives a body without features): this is **beyond Fusion**. Plan: `docs/sciforge/plan-beta3.md`.

Each builder writes only its own sections (beta3-common.md).

## Recognition

(builder at-recognize; code `src/Mod/SciForge/sciforge/recognize.py` (FreeCAD, no Qt),
`recognize_core.py` (pure Python: numbers, planes, loops, patterns, the plan's ids) and
`recognize_mesh.py` (meshes); tests `SciForgeTests/unit/test_recognize_core.py` and the
benchmark `SciForgeTests/headless/recognize_bench.py`, `run_tests.sh --only recognize`.)

`recognize.describe(shape, options)` reads a solid that has no timeline (an imported STEP
body, a solid made from a mesh) and answers what it is made of and a **plan**: the AI tool
calls, in Fusion's order, that build it again as real timeline steps. Each plan step's
arguments pass the AI catalogue's own check (`catalog.validate`), so an AI can send them as
they are; each step also says the id it will make (`"id": "Sketch1"`) and which arguments
name an earlier step (`"uses": {"profile": 1}`), so an AI whose step got another id puts that
one there. `recognize_mesh.describe_mesh(mesh)` answers the same dict for a mesh.

### What comparable programs do (sources)

| What | Behaviour | Source |
|---|---|---|
| Fusion, mesh to solid | MESH workspace > MODIFY > Convert Mesh: a body without features; history capture must be off; simple parts are often faster to model again over the mesh | Forum (Autodesk Community "Mesh to Brep Missing", 2018-2022) |
| Fusion, feature recognition | none: an imported STEP body stays a base feature without a timeline | Forum / G |
| SOLIDWORKS FeatureWorks | recognizes boss and cut extrudes, revolves, fillets, chamfers, holes, drafts, patterns and shells of an imported body, all at once or step by step; what it does not recognize stays an imported body | SOLIDWORKS help ("Step-by-Step Recognition", "Autodesk Inventor Files") |
| FeatureCAM | recognized holes are taken off the solid so they are not found twice | Autodesk help (FeatureCAM hole recognition) |
| Fusion's timeline order | sketch and base shape first, then cuts and bosses, holes, patterns, and fillets / chamfers last (the usual way Fusion users build a part) | G (common practice; the brief) |

SciForge goes further than Fusion: it reads the features and writes the plan; the AI (or a
person) builds it with the normal tools, so the result is an ordinary editable timeline.

### What is read

| Feature | How it is read | What the plan does |
|---|---|---|
| Summary | volume, area, box, size, counts, census of surface kinds | (always answered, also with `detail: summary`) |
| Holes | concave round faces that go all the way round, grouped by axis line; at each end what closes or opens the bore: the part's face (open), a flat disc (flat bottom), a cone to a point (drill point, its angle), a shoulder and a wider bore (counterbore), a widening cone (countersink); through or blind; depth from where it starts; rims on sloped faces measured at their true top | one `hole` step per group of equal holes on one plane (`create_sketch` with a circle at each centre on the origin plane at the face's height; `through_all` / `depth`, `counterbore`, `countersink`, `drill_point` + `drill_angle`; `flip` when drilled along the sketch's normal); a hole widened at both ends gets its far recess as a second, short hole drilled first; a hole along no origin axis: a Single Hole on its face (`face` + `at`) |
| Hole patterns | the centres of equal holes: a grid (rows and columns along the sketch's x / y, even spacing), a circle (equal angles, full or an arc), tolerant to float noise; four holes on a square read as a bolt circle when a round face of the part has that centre (a flange) | one hole and `rectangular_pattern` (quantity, spacing, second direction) or `circular_pattern` (about X / Y / Z, or about a round face of the part when the circle is elsewhere) |
| Fillets | round faces (cylinder, torus, sphere) tangent to two neighbours, of one radius, with the corner pieces between them; one chain per radius; a round face that covers only part of the edge it would round (the curved edge of a thin rib) is part of the shape, not a fillet; a sheet's bends in two directions stay in the base (OpenCASCADE's fillet builder crashed on such corners) | one `fillet` step per radius, biggest first, its edges picked on the part as it will be then (the sharp edge where the two faces the fillet joined meet), with a short selector when one fits ("the 4 top edges") else one ref per edge (`any_of`); `fillet_sets` with Tangent Chain off when the edges run smoothly on into edges that stay sharp |
| Chamfers | narrow flat faces between two faces, their normal between the two faces' normals; one or two distances measured from the sharp edge | one `chamfer` step per size; two distances written the way SciForge's Chamfer measures them (distance 1 on the edge's first face) |
| Defeaturing | holes closed by rebuilding the faces around their rims (milliseconds), then chamfers and fillets taken off with OpenCASCADE's defeaturing (`shape.defeaturing`, all at once, else by halves); a feature that cannot be taken off stays in the base and is said so | the base is read from the solid without its features: sharp corners and simple lines |
| Base, extrude | along X, Y or Z (fewest steps first): every flat face square to the axis (levels) or along it, every round face along it; the section of each level; the biggest level's region extruded over the levels whose outline it covers; what is extra are bosses, what is missing pockets / cuts (each one a band of equal sections); a cut through everything is `through_all`; walls on a draft give a `taper` (a drafted pocket or boss, a drafted block) | `create_sketch` on the origin plane at the right offset (geometry: `rect`, `circle`, `slot`, `polyline` or `segments` of lines and arcs that close exactly) + `extrude` (`flip`, `symmetric` or `two_sides` when the part straddles the plane); bosses / cuts on one level with the same height in one sketch; copies of one boss or pocket on a grid or circle as one extrude and a pattern |
| Base, revolve | every face a surface of revolution about an origin axis (flat faces square to it with round edges about it, coaxial cylinders, cones, tori, spheres): the half profile cut by a half plane | `create_sketch` on XZ (axis Z) or XY (axis X / Y) + `revolve` a full turn |
| Parts turned away from the origin | most of the area faces no origin axis: the part is read in its own frame (the closest one to the origin's) | the plan builds it lined up with the origin planes, then one `move_copy` (free: X, then Y, then Z angles about the origin) turns it into place |
| Cannot read | free-form faces, variable fillets, threads, text, coils, lofts, sweeps, tapered (pipe) threads, profiles with ellipse or spline edges, bosses / pockets on sloped faces, oblique holes | listed in `unrecognized` with selectors of their faces and a sentence; never guessed |
| Confidence | the share of the area the plan explains, times how well the base's own steps rebuild the defeatured solid (the base is checked by building it with OpenCASCADE) | halved when a plan step does not pass the catalogue's check |

### Meshes

`recognize_mesh.describe_mesh(mesh)`: the mesh becomes a solid with SciForge's Convert Mesh
(Prismatic: flat regions merged); strips of thin faces meeting at small angles along parallel
edges are round regions: a cylinder is fitted to each (its axis is the strips' direction, its
circle a least-squares fit of the corners); the strips that go all the way round on the inside
are holes: closed, then cut back as true cylinders with rounded diameters (a 5.98 mm hole is
6, `measured_diameter` 5.98 beside it); equal holes that make a pattern are put exactly where
the pattern says; the rest is rebuilt exactly level by level, the runs of corners lying on a
fitted circle turned into arcs, every number rounded the way a person reads it (to 0.01 mm and
rounder); then describe() reads that solid. Parts that are not prismatic once their holes are
closed (cones, spheres, fillets across them) are read as the faceted solid, their round regions
listed as not recognized.

### Speed

describe() of a 300-face plate (294 holes on a grid) takes about 1.3 s on the sandbox (4 CPUs
shared with five other builders); the limit was 5 s. Closing holes by their rims instead of
defeaturing them took it from minutes (OpenCASCADE's defeaturing costs about 75 ms per hole
face) to milliseconds.

### Benchmark

(filled in from the final run, see Tests)

## Reference, compare and finish

(builder at-tools)

## AI tools and documentation

(builder at-tools)

## The command a person uses

(builder at-tools)

## Tests

(builders at-recognize and at-tools, each its own lines)

- **Recognition (at-recognize)**: `SciForgeTests/unit/test_recognize_core.py` (pure Python:
  numbers and measured values, planes, loops and the create_sketch items they become, exact
  arc / line closure, patterns with noise, ideal pattern points, the plan's ids and Fusion's
  order, plan arguments checked by the catalogue, frames and Euler angles, circle / cylinder
  fits, arcs fitted on mesh sections); `SciForgeTests/headless/recognize_bench.py` (real
  FreeCAD 1.1.4: parts built, sent through STEP and back as bodies without a timeline,
  described, rebuilt from the plan by the headless AI executor, compared: volume within 0.1 %
  and every face of the original matched; meshes of golden models through recognize_mesh;
  describe() on a 300-face part under 5 s), run by `tools/sciforge/run_tests.sh --only
  recognize` and at the end of `--only headless` / `--only base`. A sweep over every golden
  model (a scratch script, not in the suite) found the bugs listed in the session log.

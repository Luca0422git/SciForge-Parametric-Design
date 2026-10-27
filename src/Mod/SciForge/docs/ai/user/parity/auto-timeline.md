<!-- A copy of docs/sciforge/parity/auto-timeline.md for AI models, made by tools/sciforge/make_ai_docs.py: edit the original, then run the script. -->

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
| Holes | concave round faces that go all the way round (one face or several: STEP files from other programs often split a bore in two halves), grouped by axis line; at each end what closes or opens the bore: the part's face (open), a flat disc (flat bottom), a cone to a point (drill point, its angle), a shoulder and a wider bore (counterbore), a widening cone (countersink); through or blind; depth from where it starts; rims on sloped faces measured at their true top; a hole open at both ends with more of the part in line beyond it (a port into a pipe) is not through: through all would drill the far wall too; a bore that ends on a round face inside the part (a tube's bore that stops at the eye it was extruded up to) is no hole: the Hole tool makes no such floor, so it stays in the base's profile | one `hole` step per group of equal holes on one plane (`create_sketch` with a circle at each centre on the origin plane at the face's height; `through_all` / `depth`, `counterbore`, `countersink`, `drill_point` + `drill_angle`; `flip` when drilled along the sketch's normal); a hole into a hollow gets a depth past its far end, rounded when the bore carried on meets nothing (15, not 13.38); a hole widened at both ends gets its far recess as a second, short hole drilled first; a hole along no origin axis: a Single Hole on its face (`face` + `at`) |
| Hole patterns | the centres of equal holes: a grid (rows and columns along the sketch's x / y, even spacing), a circle (equal angles, full or an arc), tolerant to float noise; four holes on a square read as a bolt circle when a round face of the part has that centre (a flange) | one hole and `rectangular_pattern` (quantity, spacing, second direction) or `circular_pattern` (about X / Y / Z, or about a round face of the part when the circle is elsewhere) |
| Fillets | round faces (cylinder, torus, sphere) tangent to two neighbours, of one radius, with the corner pieces between them; one chain per radius; a round face that covers only part of the edge it would round (the curved edge of a thin rib) is part of the shape, not a fillet; a sheet's bends in two directions stay in the base (OpenCASCADE's fillet builder crashed on such corners) | one `fillet` step per radius, biggest first, its edges picked on the part as it will be then (the sharp edge where the two faces the fillet joined meet), with a short selector when one fits ("the 4 top edges") else one ref per edge (`any_of`); `fillet_sets` with Tangent Chain off when the edges run smoothly on into edges that stay sharp |
| Chamfers | narrow flat faces between two faces, their normal between the two faces' normals; one or two distances measured from the sharp edge; a narrow cone between a cylinder and a flat face square to its axis (the chamfered end of a shaft, the top of a round boss) | one `chamfer` step per size; two distances written the way SciForge's Chamfer measures them (distance 1 on the edge's first face) |
| Defeaturing | holes closed by rebuilding the faces around their rims (milliseconds), then chamfers and fillets taken off with OpenCASCADE's defeaturing (`shape.defeaturing`, all at once, else by halves); a feature that cannot be taken off, or whose removal changes the volume far more than such a feature holds (a slanted face of a groove taken for a chamfer), stays in the base and is said so; raised or engraved text and logos (faces with free-form ones among them that meet the part only along inner loops of one flat face) are closed over the same way as holes (beta 3 QA); parts with other free-form faces left are not defeatured (their base cannot be read) | the base is read from the solid without its features: sharp corners and simple lines |
| Base, extrude | along X, Y or Z: every flat face square to the axis (levels) or along it, every round face along it; the section of each level; the biggest level's region extruded over the levels whose outline it covers; what is extra are bosses, what is missing pockets / cuts (each one a band of equal sections); each boss or cut is read along the axis its open side faces (the holes in a channel's flanges along Y, those in its web along Z); a cut through everything, or one that could go through without taking more (the same hole in both flanges), is `through_all`; walls on a draft give a `taper` (a drafted pocket or boss, a drafted block, a drafted hole in a straight block, a drafted block with a cavity: a molded box); a cut that opens onto a round face (a keyway, a flat on a shaft) goes from its floor out of the part, a boss standing on one (a port on a pipe) from its top into the part, from the origin plane or a round value when the part is solid there; when no axis fits every face, an axis is tried with up to a quarter of the area in such features. Of the readings, the one with the fewest steps wins, then the one whose steps add or take the least volume (a round boss on a block is a boss along Z, not the block's side outline with its corners cut off) | `create_sketch` on the origin plane at the right offset (geometry: `rect`, `circle`, `slot`, `polyline` or `segments` of lines and arcs that close exactly) + `extrude` (`flip`, `symmetric` or `two_sides` when the part straddles the plane); bosses / cuts on one level with the same height in one sketch (regions that touch go in sketches of their own: one sketch would merge them); copies of one boss, pocket or opening on a grid or circle as one extrude and a pattern (a VEX plate's square holes: one cut and a 5 x 10 pattern) |
| Base, revolve | every face a surface of revolution about an origin axis, or about a line parallel to one (a turned part away from the origin: a torus, a dome on a spot of a block): flat faces square to it with round edges about it, coaxial cylinders, cones, tori, spheres; the half profile cut by a half plane | `create_sketch` on XZ (axis Z) or XY (axis X / Y), offset to the axis line when it is away from the origin, + `revolve` a full turn (about the origin axis, or about a construction line drawn on the sketch: `axis: {"sketch": ..., "construction": [[x1, y1], [x2, y2]]}`) |
| Base with features along another axis | when no axis fits every face, an axis is tried with up to a quarter of the area in features along the others; the base extrude may then stop inside such a feature, at a level or at its middle (a rod or a tube that ends in an eye: the rod, then the eye as a boss along its own axis, in FreeCAD's example assembly placed at angles) | the base extrude, then each boss or cut along its own axis |
| Turned bosses and cuts | a boss or cut piece of an extruded part that is itself turned about a line along X, Y or Z (a dome on a block, a torus groove in its top): its round faces are passed over by the extrude reading and the piece is read as a revolve | `create_sketch` of its half profile (offset to its axis line) + `revolve` with `operation` join or cut, about the origin axis or a construction line |
| What is not taken off | pieces of one round wall cut in pieces that together go half way round or more are no fillet (taking such a "fillet" off ran out of memory and crashed FreeCAD); a hole crossed by many other faces (a bore with a ring of slots) is left in the base without trying (one such defeaturing took 3 minutes); a hole whose removal leaves most of its bore open (OpenCASCADE answered so for two bores countersunk at both ends) stays in the base too, where it is read as a turned cut that makes both ends | said in the notes; the hole is listed in `unrecognized` |
| Parts turned away from the origin | most of the area faces no origin axis: the part is read in its own frame (the closest one to the origin's) | the plan builds it lined up with the origin planes, then one `move_copy` (free: X, then Y, then Z angles about the origin) turns it into place |
| No base read | the faces fit no extrude or revolve | a note names the axis most of the part fits ("Along Y, 87 % of the part's area ... fits an extrude") and `unrecognized` lists the faces that do not; the holes, fillets and chamfers are still planned |
| Cannot read | free-form faces, variable fillets, modelled threads, text, coils, lofts, sweeps, profiles with ellipse or spline edges, bosses / pockets on sloped faces, oblique holes starting on a curved face (a tapered pipe-thread hole without thread geometry is read: a drafted cut) | listed in `unrecognized` with selectors of their faces and a sentence; never guessed |
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

describe() of a 300-face plate (294 holes on a grid) takes about 1.5 s on the sandbox (4 CPUs
shared with five other builders); the limit was 5 s. Closing holes by their rims instead of
defeaturing them took it from minutes (OpenCASCADE's defeaturing costs about 75 ms per hole
face) to milliseconds.

Other parts (describe() alone, seconds, measured on this sandbox while other builders ran):

| Part | Faces | describe (s) | Where the time goes |
|---|---|---|---|
| plate with a 21 x 14 grid of holes (`bench_part_300`) | 300 | 1.5 to 3.7 | holes closed by their rims; one section |
| VEX-like plate, 50 square cut-outs (`bench_vex_plate`) | 206 | about 5.5 | the base along Z; X and Y are skipped (many more levels than a 2-step reading) |
| VEX-like C-channel, square holes in web and flanges | 70 | about 4.4 | three axes read, 10 cut pieces |
| Raspberry Pi 5 case, base (a real STEP file) | 62 | about 3.3 | |
| 7 x 7 bosses with a fillet at foot and top | 202 | about 19 | OpenCASCADE's defeaturing of 98 fillet faces: 15 s |
| forged lever `Schenkel.stp` (free-form) | 409 | about 1.9 | not defeatured: its base cannot be read |
| connector `TSM_103_01_L_DV_A.stp` | 434 | about 42 | one defeaturing call of 26 chamfers and fillets; the base is not read |

What keeps it fast: copies of one cut-out or boss are read once (a moved copy takes the first
one's reading, moved); an axis with many more levels than a simple reading already found is not
read; parts with free-form faces are not defeatured (their base cannot be read: the forged
lever `Schenkel.stp`, 409 faces, went from 26 s to under 2 s); after 30 s (`DESCRIBE_BUDGET`)
the optional work is skipped and the notes say so. One OpenCASCADE defeaturing call cannot be
interrupted: a 434-face connector with 26 chamfers and fillets spends about 40 s in it.

### Benchmark

`SciForgeTests/headless/recognize_bench.py` (`run_tests.sh --only recognize`), the final run on this sandbox (times are wall-clock on 4 CPUs shared with five other builders). 71 parts: 71 pass, 0 fail. Each part: built, exported to STEP, imported as a body without a timeline, described, rebuilt from the plan through the headless AI executor, compared (volume within 0.1 %, every face matched; for the real files, every face or else every surface: they split faces the rebuild keeps whole).

| Part | Faces | Found | Plan steps | Volume | Faces matched | describe (s) | Total (s) | Result |
|---|---|---|---|---|---|---|---|---|
| box_basic | 6 | extrude | 2 | +0.0000 % | 6 / 6 | 0.086 | 0.359 | PASS |
| cylinder_extrude | 3 | extrude | 2 | +0.0000 % | 3 / 3 | 0.024 | 0.06 | PASS |
| hex_prism | 8 | extrude | 2 | -0.0000 % | 8 / 8 | 0.237 | 0.296 | PASS |
| l_bracket_profile | 8 | extrude | 2 | +0.0000 % | 8 / 8 | 0.155 | 0.236 | PASS |
| slot_extrude | 6 | extrude | 2 | +0.0000 % | 6 / 6 | 0.071 | 0.151 | PASS |
| bracket_inner_fillet | 9 | extrude, fillet r3 | 3 | +0.0000 % | 9 / 9 | 0.275 | 0.417 | PASS |
| fillet_top_edges | 10 | extrude, fillet r2 | 3 | +0.0000 % | 10 / 10 | 0.164 | 0.373 | PASS |
| fillet_one_vertical_edge | 7 | extrude, fillet r5 | 3 | +0.0000 % | 7 / 7 | 0.12 | 0.226 | PASS |
| fillet_all_edges | 26 | extrude, fillet r2 | 3 | +0.0000 % | 26 / 26 | 0.144 | 0.684 | PASS |
| chamfer_top_edges | 10 | extrude, chamfer 2 | 3 | +0.0000 % | 10 / 10 | 0.208 | 0.39 | PASS |
| chamfer_one_edge | 7 | extrude, chamfer 3 | 3 | +0.0000 % | 7 / 7 | 0.125 | 0.239 | PASS |
| blend_chamfer_top_face | 10 | extrude, chamfer 2 | 3 | +0.0000 % | 10 / 10 | 0.132 | 0.346 | PASS |
| plate_through_hole_cut | 7 | extrude, 1 hole | 4 | +0.0000 % | 7 / 7 | 0.13 | 0.308 | PASS |
| pattern_rect_hole_grid_fusion | 12 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 12 / 12 | 0.098 | 0.329 | PASS |
| flange_polar_holes | 9 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 9 / 9 | 0.059 | 0.246 | PASS |
| hole_blind | 8 | extrude, 1 hole | 4 | +0.0000 % | 8 / 8 | 0.088 | 0.188 | PASS |
| hole_counterbore | 9 | extrude, 1 hole | 4 | +0.0000 % | 9 / 9 | 0.1 | 0.243 | PASS |
| hole_countersink | 8 | extrude, 1 hole | 4 | +0.0000 % | 8 / 8 | 0.089 | 0.246 | PASS |
| hole_single_angled | 8 | extrude, 1 hole | 4 | -0.0000 % | 8 / 8 | 0.097 | 0.226 | PASS |
| pocket_depth | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.308 | 0.441 | PASS |
| symmetric_cut_slot | 10 | extrude | 2 | +0.0000 % | 10 / 10 | 0.236 | 0.331 | PASS |
| sf_cylinder_boss | 8 | extrude | 4 | -0.0000 % | 8 / 8 | 0.066 | 0.183 | PASS |
| mirror_boss | 10 | extrude, 1 pattern | 5 | +0.0000 % | 10 / 10 | 0.089 | 0.261 | PASS |
| pattern_rect_symmetric_bosses | 36 | extrude, 1 pattern | 5 | +0.0000 % | 36 / 36 | 0.327 | 0.732 | PASS |
| shell_open_box | 11 | extrude | 3 | +0.0000 % | 11 / 11 | 0.285 | 0.416 | PASS |
| shell_filleted_box | 19 | extrude | 3 | -0.0000 % | 19 / 19 | 0.368 | 0.625 | PASS |
| revolve_washer | 4 | extrude, 1 hole | 4 | +0.0000 % | 4 / 4 | 0.037 | 0.117 | PASS |
| groove_ring | 7 | extrude | 4 | +0.0000 % | 7 / 7 | 0.098 | 0.194 | PASS |
| sf_revolve_cone | 2 | revolve | 2 | +0.0000 % | 2 / 2 | 0.02 | 0.125 | PASS |
| sf_torus_new_body | 1 | revolve | 2 | -0.0000 % | 1 / 1 | 0.011 | 0.071 | PASS |
| sf_sphere_intersect | 2 | revolve | 2 | +0.0000 % | 2 / 2 | 0.029 | 0.097 | PASS |
| sf_torus_inside_cut | 8 | extrude | 4 | -0.0000 % | 8 / 8 | 0.304 | 0.435 | PASS |
| bench_domed_block | 7 | extrude | 4 | +0.0000 % | 7 / 7 | 0.401 | 0.581 | PASS |
| bench_stepped_shaft | 7 | revolve | 2 | -0.0000 % | 7 / 7 | 0.098 | 0.218 | PASS |
| bench_knob | 6 | revolve, 1 hole | 4 | +0.0000 % | 6 / 6 | 0.086 | 0.286 | PASS |
| bench_bracket_holes | 12 | extrude, 3 holes, 1 pattern, fillet r3 | 8 | +0.0000 % | 12 / 12 | 0.274 | 0.738 | PASS |
| bench_mount_plate | 18 | extrude, 4 holes, 1 pattern, fillet r6 | 6 | +0.0000 % | 18 / 18 | 0.962 | 1.674 | PASS |
| extrude_taper_cut | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.449 | 0.666 | PASS |
| extrude_taper_join_all | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.512 | 0.919 | PASS |
| sf_draft_four_sides | 6 | extrude | 2 | -0.0000 % | 6 / 6 | 0.09 | 0.225 | PASS |
| bench_turned_bracket | 12 | extrude, 3 holes, 1 pattern, fillet r3 | 9 | -0.0000 % | 12 / 12 | 0.291 | 0.736 | PASS |
| bench_shaft_cross_hole | 4 | extrude, 1 hole | 4 | -0.0001 % | 4 / 4 | 0.076 | 0.387 | PASS |
| bench_vex_channel | 70 | extrude, 2 patterns | 8 | -0.0000 % | 70 / 70 | 2.5 | 3.619 | PASS |
| bench_side_boss | 9 | extrude | 4 | +0.0000 % | 9 / 9 | 0.097 | 0.248 | PASS |
| bench_keyed_shaft | 10 | extrude | 6 | -0.0000 % | 10 / 10 | 0.675 | 1.05 | PASS |
| bench_pipe_port | 7 | extrude, 2 holes | 8 | +0.0005 % | 7 / 7 | 0.842 | 1.563 | PASS |
| bench_clevis | 11 | extrude, 1 hole | 4 | +0.0000 % | 11 / 11 | 0.223 | 0.384 | PASS |
| bench_opposed_holes | 10 | extrude, 2 holes | 6 | +0.0000 % | 10 / 10 | 0.116 | 0.312 | PASS |
| bench_vex_plate | 206 | extrude, 1 pattern | 5 | +0.0000 % | 206 / 206 | 3.964 | 35.118 | PASS |
| bench_vex_angle | 50 | extrude, 2 patterns | 8 | -0.0000 % | 50 / 50 | 1.124 | 2.073 | PASS |
| bench_shaft_collar | 5 | extrude, 2 holes | 6 | +0.0002 % | 5 / 5 | 0.167 | 0.712 | PASS |
| bench_chamfered_boss | 9 | extrude, chamfer 1 | 5 | +0.0000 % | 9 / 9 | 0.106 | 0.304 | PASS |
| bench_chamfered_shaft | 5 | extrude, chamfer 1.5 | 3 | +0.0000 % | 5 / 5 | 0.05 | 0.125 | PASS |
| bench_offset_flange | 9 | extrude, 6 holes, 1 pattern | 7 | +0.0000 % | 9 / 9 | 0.056 | 0.374 | PASS |
| bench_link_rod | 8 | extrude, 1 hole | 6 | -0.0002 % | 8 / 8 | 2.127 | 2.725 | PASS |
| bench_part_300 | 300 | extrude, 294 holes, 1 pattern | 5 | +0.0000 % | 300 / 300 | 1.594 | 14.167 | PASS |
| contract and odd shapes |  | None |  |  |  |  | 6.273 | PASS |
| pi5_case.step #0 | 62 | extrude, 4 holes, 1 pattern | 19 | -0.0000 % | 62 / 62 (surfaces all) | 2.264 | 6.011 | PASS |
| pi5_case.step #1 | 56 | extrude, fillet r1 | 7 | -0.0000 % | 56 / 56 (surfaces all) | 1.657 | 2.801 | PASS |
| as1-ac-214.stp #0 | 18 | extrude, 6 holes | 4 | +0.0000 % | 6 / 18 (surfaces all) | 0.132 | 0.511 | PASS |
| EPL22_6_16.stp #0 | 36 | extrude, 1 pattern, fillet r1, chamfer 0.443784/1 | 8 | -0.0000 % | 36 / 36 (surfaces all) | 1.745 | 2.76 | PASS |
| AssemblyExample.FCStd Shape016 | 6 | extrude, 1 hole | 7 | -0.0001 % | 6 / 6 | 0.936 | 1.521 | PASS |
| AssemblyExample.FCStd Shape020 | 8 | extrude, 1 hole | 7 | -0.0001 % | 8 / 8 | 1.94 | 2.167 | PASS |
| AssemblyExample.FCStd Shape022 | 10 | extrude, 1 hole | 7 | +0.0000 % | 10 / 10 | 2.192 | 2.529 | PASS |
| holesInFace2.brep #0 | 39 | extrude | 6 | +0.0000 % | 33 / 39 (surfaces all) | 2.243 | 2.543 | PASS |
| shelf.brep #0 | 70 | extrude, 2 patterns | 8 | +0.0000 % | 50 / 70 (surfaces all) | 3.623 | 4.081 | PASS |
| plate_through_hole_cut (mesh) | 7 | extrude, 1 hole | 4 | +0.0000 % | 7 / 7 | 0.348 | 0.456 | PASS |
| flange_polar_holes (mesh) | 9 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 9 / 9 | 3.678 | 3.916 | PASS |
| l_bracket_profile (mesh) | 8 | extrude | 2 | +0.0000 % | 8 / 8 | 0.197 | 0.259 | PASS |
| bench_knob (mesh) | 6 | revolve, 1 hole | 4 | +0.0000 % | 6 / 6 | 2.913 | 3.045 | PASS |
| bench_mount_plate (mesh) | 18 | extrude, 4 holes, 1 pattern, fillet r6 | 6 | +0.0000 % | 18 / 18 | 2.984 | 3.6 | PASS |

### Real files from other programs

Every solid of every STEP file in the repository (made by other programs: the AS1 test
assembly, a part library of electronic packages, a forged lever, the Pi 5 case) and of four of
FreeCAD's example documents (the CAM hole puzzle, PartDesignExample, EngineBlock,
AssemblyExample), 71 distinct solids from 36 files, each described and rebuilt from the plan
through the headless AI executor (a scratch sweep; seven of them are also in the benchmark):

| Result | Solids | Which |
|---|---|---|
| rebuilt exactly | 23 | the Pi 5 case (both parts), PartDesignExample, EngineBlock's block, six assembly parts (four of them rods and tubes that end in an eye, placed at angles), IDF bodies with chamfers and patterns |
| exactly, faces split in the file | 12 | the AS1 plates, brackets and nuts (each bore in two half faces), CAM test blocks, an assembly bracket: the same volume and surfaces, whole faces in the rebuild |
| within 1e-7 of the volume | 4 | a lead with tiny two-distance chamfers, two excavator links whose tangent arcs missed each other by 5e-7 mm |
| a step stopped | 1 | an excavator bucket (97 faces): a fillet's selector found 5 edges where it expected 1 (the step stops; nothing is rounded wrongly) |
| read, volume within 1e-5, some faces differ | 2 | two CAM test plates whose bores are countersunk at both ends: the bores read as turned cuts (both ends made); the file's cones in halves and the corner chamfers do not match face by face |
| base not read (said so) | 29 | free-form bodies (SMD chips, a capacitor, the forged lever), molded IC bodies drafted from a parting line with leads on them, CAM test parts with oblique holes, a bracket whose round ribs stay in it; their holes, fillets and chamfers are still listed, and a note names the axis most of the part fits |

The BREP files in the repository (FreeCAD's model-refine test shapes: unrefined booleans, two
3D-printer parts): 27 solids, 18 rebuilt exactly (two of them in the benchmark); the rest are
free-form, a bore crossed by a ring of slots (left in the base), a grid of 144 blocks, slanted
features, and a 3D-printer part whose root fillets the original made before the cut that trims
them (Known gaps).

Before these sweeps: a curve type FreeCAD has no Python class for stopped the whole reading, a
base ended 1e-6 mm short of the boss on it (two snaps in a row), tangent arcs did not close a
sketch, a hole whose rim is rounded started below the round, slanted groove faces read as
chamfers filled the groove (+15 % volume), three files took 26 to 169 s, and one BREP file
crashed FreeCAD (a round wall in 41 pieces read as a fillet: OpenCASCADE's defeaturing ran out
of memory); all fixed (see the session log).

### Known gaps

| Gap | Why | What describe() does |
|---|---|---|
| Free-form faces: lofts, sweeps, pipes, coils, B-spline surfaces, embossed text, variable fillets, modelled threads | no extrude or revolve of lines and arcs makes them | the base is `none` (or the faces stay in the base); they are listed in `unrecognized` with a sentence. A text or a logo standing on or cut into a flat face, and a hole's modelled thread, are taken off instead: the part under them is read and planned, they are listed (beta 3 QA) |
| Profiles with ellipse or spline edges | `create_sketch` has `ellipse` (axis along x only) and `spline_loop` (a curve through points), which do not give back the original curve exactly | not attempted: listed |
| A drafted block with bosses on it, or whose top or bottom is not one flat face | the base is read as the outline of its bottom face extruded with the walls' draft up to its top face | a drafted block, one with a cavity or pockets, and drafted pockets / bosses / holes in a straight block are read; this is listed |
| Fillets between leaning (drafted) walls | SciForge's tapered walls are flat B-spline faces: the round between them is a B-spline, not a cylinder or a torus | the round stays in the shape; the base is then not read |
| Sheet metal bent in two directions with closed corners | the bends stay in the base (OpenCASCADE's fillet builder crashed on such corners); some trays read as a floor and walls along X and Y, others not | the rest is listed |
| Oblique holes starting on a curved face, bosses / pockets on sloped faces | the Hole tool's Single Hole needs a flat face; a sloped boss is along no origin axis | listed |
| A turned cut or bump that is cut by the part's own faces (a sphere cut out of a block's corner) | the piece has flat faces along several axes: it is neither an extrude nor a revolve on its own (a dome on a face or a torus groove is read) | listed; the base is `none` |
| Several solids in one shape | the contract reads one solid | the largest is read, the note says how many others there are (describe them one by one) |
| Countersunk at both ends | the Hole tool makes one end | the plan makes the first end, a note asks for the other |
| A face split in two in the original (a split face, a face cut for a sketch region) | the plan rebuilds it as one face | volume exact; the bench's face check fails on those golden models (`direct_split_face_*`) |
| Meshes | only parts that are prismatic or turned once their holes are closed, from CAD-quality meshes (not scans); fillets across a mesh are not recovered | open meshes are refused with repair advice; the rest is read as the faceted solid and listed |
| Speed of fillet-heavy and complex parts | OpenCASCADE's defeaturing: one call for all fillets (in chunks it is slower), which cannot be interrupted | a 202-face part with 98 fillet faces takes about 19 s (15 s of it defeaturing); a 434-face connector about 45 s |
| A fillet the original made before a cut that trims it (the root fillets of a 3D-printer part's uprights, cut short by the opening in its plate) | the plan rounds edges last, as Fusion users do; the fillet then runs into the cut's edge and OpenCASCADE refuses it | the step stops with the largest radius that fits (nothing is rounded wrongly); the volume is short by the fillet's material |
| A fillet or chamfer step whose short selector ("the edge along X at the top") finds more edges on the rebuilt part | the edges are picked on the part as it will be; when an earlier step rebuilt something slightly differently, more edges can match | the step stops with a count error (never rounds the wrong edges); pick the edges with query_geometry |

## Reference, compare and finish

(builder at-tools; `sciforge/rebuild.py`, the words in `sciforge/rebuild_core.py`)

### What Fusion does, and what SciForge does instead (sources)

| Fusion | Source | SciForge |
|---|---|---|
| An imported STEP body has no design history; "an imported model can't be converted into a parametric recipe" (imported models are direct models) | Forum (Autodesk community manager and consultants, [Accessing parametric modeling from solid](https://forums.autodesk.com/t5/fusion-support-forum/accessing-parametric-modeling-from-solid-why-isn-t-my-timeline/m-p/10002539/highlight/true), [Find Features](https://forums.autodesk.com/t5/fusion-design-validate-document/find-features/m-p/6237381)) | the same body comes in without a timeline (one "Insert STEP" step), and **Rebuild with Timeline** rebuilds it as real steps |
| **Find Features** (direct modeling only) recognizes fillets, holes and chamfers of a solid in place, without changing its geometry; the found features can be edited, deleted or dissolved; no base sketch or extrude is recovered; users report holes that cannot be resized and misread chamfers | Autodesk ([Recognize features in a design](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/GUID-C651DB91-81DC-43F6-90E9-52540DCA0C40.htm)), Forum ([Find Features](https://forums.autodesk.com/t5/fusion-design-validate-document/find-features/m-p/6236249)) | not built as such (a gap below): Auto Timeline rebuilds the whole part, base shape included, as a parametric timeline, and proves it with a comparison |
| **Mesh to BRep** is direct-modeling only (a Base Feature); its result is a body without features; a faceted STL may refuse to convert | Forum ([Mesh to Brep Missing](https://forums.autodesk.com/t5/fusion-support/mesh-to-brep-missing/td-p/7770093), [Stl to Brep](https://forums.autodesk.com/t5/fusion-support-forum/stl-to-brep/td-p/10557786)) | MESH > Convert Mesh stays as it is; a mesh body can also be the reference of a rebuild: its holes come back as real holes |
| No comparison of two bodies beyond Interference and Measure | Guess (no such command in Fusion's INSPECT menu) | **Compare with Reference**: match, missing / extra material, faces, a verdict |

### Behaviour

| What | SciForge |
|---|---|
| The reference | `start(doc, source)`: a body (or a step in it), or a mesh body made into a solid first with SciForge's own mesh-to-solid (Prismatic). A mesh that is not watertight, has edges shared by more than two triangles, or whose solid does not come out the mesh's size is refused with the reason and what to do (MESH tab > Repair). The solid is frozen (design coordinates) in an `App::FeaturePython` (SciForgeType `RebuildReference`, never a `Part::Feature`, so no export, inspect, joint or body code takes it for a part), hidden from the timeline (`SciForgeTimeline` false) and not in the browser. The original is hidden; a new empty body `<name> (rebuilt)` is made in the original's component with its placement, and made active. One undo step; undo shows the original again (an undo / redo watcher, since FreeCAD does not record what is shown). The same body is not started twice (its message is offered again). A reference whose rebuilt body was deleted gets a new one when started again. |
| The picture | the reference's own view provider draws it faint blue-grey and see-through (Coin nodes only, unpickable, pushed behind faces lying on it, so the rebuild shows clean where it matches); nothing in the document changes for it. Saved with the design and drawn again on reopen. |
| Compare | `compare(ref, target=None)`: both solids in the rebuilt body's frame; the faces matched first (when every face of each part lies on a face of the other and the volumes agree, it is the same solid: no boolean, `method` "faces"); else one General Fuse splits them by each other; every piece is put inside / outside each solid from the orientation of its faces (a face of a piece lies on a face of one solid; facing the same way, it is inside), a point test only when that says nothing; slivers below 1e-7 of the volume are rounding; the pieces must add up to both volumes (else a fuzzy General Fuse, else the volumes measured along 4096 rays through both parts' triangles, about 1 % exact, said in `note` and in the verdict). `match` = common / union. |
| Regions | each region of missing / extra material (touching pieces merged) with volume, centre, box, kind and numbers: a round hole (extra material shaped like a cylinder; counterbores as stepped), a boss, a rounded edge (the corner strip of radius r: r^2 (1 - pi/4) per mm), a chamfer (a triangle strip), a block, a layer (a thin slab: "too tall"), else its size. `fix` when SciForge is sure: a Single Hole call on the flat face the hole starts on (through_all when it comes out the other side), a fillet / chamfer of exactly the rebuild's sharp edges in the strip (stable selectors); `groups` puts equal regions together in Fusion's order (big base differences first, fillets last) with one call for a group of fillets / chamfers. |
| Faces | matched by geometry: same kind and surface (plane: normal and offset; cylinder: axis line, radius, inside / outside; sphere; cone; torus) within 0.001 mm, facing the same way, and covering each other (every sample point of one lies on the other; the same face with the same area and box needs no sampling). A reference from a mesh: a facet is matched when its points lie within the mesh's tolerance (0.2 % of its size, 0.02 to 0.5 mm) of the rebuild's faces and the other way round. Unmatched faces are listed with words ("a round hole face 6 mm across along Z at (10, 30)") and a selector. |
| Deviation | sample points of the unmatched faces (at most 48 faces, spread from the biggest to the smallest, the mean scaled to all of them), their exact distance to the other solid (the faces' boxes first); matched faces count 0; max and an area-weighted mean. |
| Done and verdict | `done`: match >= 0.999, every face of the original matched and no face of the rebuild left over (an extra 1 mm hole hides inside the 0.1 % volume tolerance; the faces catch it: stricter than the contract's comment, which says the first two). The verdict: "Match 0.9497 (1 is identical); 6 of 14 faces of the original matched. Next: 4 round holes about 6 mm across, 10 deep (along Z) are not cut yet, at (10, 10), (50, 10), (10, 30), (50, 30). 4 rounded edges of radius about 3 are still sharp in the rebuild (the fillet call is ready in groups[1].fix). Fix that, then compare_to_reference again." |
| Finish | `finish(ref, target=None, keep_reference=False, keep_original=False)`: the rebuilt body takes the original's name (its name now; a name the person gave the rebuild meanwhile stays: beta 3 QA), component and place (and its material and appearance), and the original's place in the timeline (its steps go where the original's stood, before what used it); whatever used the original (joints and their snaps, grounds, rigid groups, contact sets, a pattern of bodies of it, sketches and planes on its faces, drawings: every link of every other object) moves onto the rebuild, each face / edge / corner name swapped for the rebuild's element on the same geometry (`sciforge/rebuild_links.py`, beta 3 QA); then the original is deleted (an imported body with its imported shape; a mesh body with its steps) or kept hidden as `<name> (original)`; it is kept anyway, and the answer says why, when something cannot move (a link to its own sketch, a face the rebuild does not have). The reference removed or kept hidden (not drawn). One undo step. |
| Speed | measured in this sandbox (4 CPUs shared by six builders, load about 4.5): the parts of the end-to-end test 0.01 to 0.13 s when done (the same solid: no boolean), the meshed plate (150 faces) 1.6 to 2.1 s; a 298-face plate with 96 chamfered holes: the same solid 0.3 to 0.6 s, the base plate only (96 holes left) 1.5 s, 10 holes left 2.2 s, every chamfer and 4 holes left (188 regions) 3.7 s. OpenCASCADE's General Fuse alone takes 0.5 to 2.4 s of that. What compare measures of the reference is kept between compares (the reference never changes). On a PC without other jobs it should be about half. The 2 s target is met for typical parts, and on the 300-face plate for the same solid and the base plate, not with 10 or 188 regions left at this load. |

## AI tools and documentation

(builder at-tools; `sciforge/ai/catalog/rebuild_tools.py`, `sciforge/ai/actions/rebuild_actions.py`)

Four tools in their own category "Rebuild with a timeline" (beyond Fusion), with a need of
their own ("No rebuild is going on in this design: call start_rebuild with the body to rebuild
first", listed by `list_tools` and on the reference pages):

| Tool | What it does |
|---|---|
| `start_rebuild` (`body`, `label`) | the body (or mesh body) becomes the reference; answers the reference's id and size and the new body's id ("Its id is 'Body002'"). One undo step "AI: Start rebuild of Body001". |
| `describe_reference` (`reference`, `detail` plan / summary / full, `max_features`) | recognize.describe() of the reference in the rebuilt body's frame (recognize_mesh.describe_mesh for a mesh while the mesh body is there), with the ids already taken in the design (the plan's ids are the ones SciForge will give); `plan` (default) leaves out each feature's face list, `full` keeps it, `summary` is the numbers only. Read-only. |
| `compare_to_reference` (`reference`, `body`, `detail`, `show`) | rebuild.compare as JSON after the verdict; `summary` lists 6 regions and 8 faces per side, `full` 100 / 200; `show` draws the differences in the window. Read-only. |
| `finish_rebuild` (`reference`, `keep_original`, `keep_reference`, `even_if_different`) | compares first and refuses a rebuild that is not done (the answer is the verdict) unless `even_if_different`; marked destructive (it deletes the original). One undo step. |

`reference` takes the reference's id, or the original's or the rebuilt body's; without it the
tools use the rebuild of the active body, or the only one (several: the answer lists them).

Documentation for AI models: `docs/ai/recipes/reverse-engineer.md` (when to use it, the loop,
good habits: key sizes as user parameters, Fusion's order, real features not copied faces,
what describe_reference could not read, meshes; then a tested run: an imported plate rebuilt
with parameters and made thicker, 32 calls), a handbook section "Rebuilding a part that has no
timeline", a troubleshooting section "Rebuilding a part (Auto Timeline)" (its calls run too),
the recipe index row, one reference page per tool with a recorded example (`describe_reference`'s
is compared on its first line only: its plan is at-recognize's and may change). The chat
panel's system prompt lists the recipe by itself (`docs_core.prompt_index`).

## The command a person uses

(builder at-tools; `sciforge/rebuild_ui.py`, icons in `tools/sciforge/icons_rebuild.py`)

| What | SciForge |
|---|---|
| Where | **Rebuild with Timeline (AI)...** on a body's (and a mesh body's) right-click in the browser, on the 3D view's right-click list when a body is under the mouse (a small hook in `marking_menu.py`: `CONTEXT_ITEMS`), and in UTILITIES > AI (with Compare with Reference and Finish Rebuild). On a body being rebuilt the 3D view's list and the browser's right-click offer Compare with Reference, Finish Rebuild and Stop Rebuild... instead, for that body's rebuild (beta 3 QA: the 3D view's took the active body's; the browser's offered Rebuild with Timeline (AI)..., which refused). |
| Start | one undo step "Rebuild with Timeline"; a refusal (a broken mesh, a body without a solid) is said in a small window with the reason and what to do. |
| The AI | when SciForge's own chat has an AI set up (a key kept, or a local model's address), the AI panel opens on its Chat tab with the message in the box, not sent: the person reads it, may change it, and presses Send. Otherwise a window says how to ask an AI app (Claude Desktop, Gemini CLI, Claude Code...: add it, turn AI control on, paste the message), with the message in an editable box, already on the clipboard, Copy Message, Add an AI... and Close. The message names the body, the rebuilt body, the recipe and the four tools. |
| Compare with Reference | a window with the match, the volumes (missing red, extra green), the faces matched, the largest gap, the verdict (the AI's, said with the buttons' names instead of the tools') and one row per difference; the 3D view shows the missing material red and the extra green, see-through, until the window closes (Close or Esc), the next compare, or Finish. Compare Again; Finish Rebuild... opens Finish. |
| Finish Rebuild | a window: whether the rebuild matches (match, faces), Delete the original body (the default when it matches) or Keep the original, hidden (the default when it does not match yet: journey, beta 3); Keep the reference (hidden); Finish / Cancel (Esc). One undo step "Finish Rebuild". |
| Stop Rebuild... | (beta 3 QA) UTILITIES > AI and the rebuilt body's right-click in the 3D view: a window: Delete the rebuilt body and its steps (default) or Keep it as a body of its own; Stop Rebuild / Cancel. The original is shown again as it was (and is the active body), the reference goes. One undo step "Stop Rebuild". The AI gives a rebuild up with `delete_step` on the reference. |

## Tests

(builders at-recognize and at-tools, each its own lines)

- **Recognition (at-recognize)**: `SciForgeTests/unit/test_recognize_core.py` (56 tests, pure
  Python: numbers and measured values, snapping twice is snapping once, planes, loops and the
  create_sketch items they become, exact arc / line closure and arcs that miss each other by
  noise, patterns with noise, ideal pattern points, the plan's ids and Fusion's order, plan
  arguments checked by the catalogue, frames and Euler angles, circle / cylinder fits, arcs
  fitted on mesh sections, round values beyond a value, where a base extrude may end inside a
  feature along another axis); `SciForgeTests/headless/recognize_bench.py`
  (real FreeCAD 1.1.4: 56 parts built, sent through STEP and back as bodies without a
  timeline, described, rebuilt from the plan by the headless AI executor, compared: volume
  within 0.1 % and every face of the original matched; 4 solids of STEP files made by other
  programs, 3 parts of FreeCAD's example assembly placed at angles and 2 BREP parts of its
  model-refine tests, compared face by face or surface by surface; 5 meshes of golden models
  through recognize_mesh; the contract on odd input, with the part that crashed FreeCAD once
  answered in under 30 s; describe() on a 300-face part under 5 s), run by
  `tools/sciforge/run_tests.sh --only recognize` and at the end of `--only headless` / `--only
  base`. Scratch sweeps (not in the suite) found the bugs listed in the session log: the 27
  BREP solids above, every golden model that builds one solid (505 described, 410 rebuilt
  exactly, 424 with a base read, no crash and no regression between runs;
  the rest are free-form, sheet metal bent both ways or split faces) and the 71 real solids
  above.

### Tests: the reference, compare, tools and command (at-tools)

- `SciForgeTests/headless/rebuild_e2e.py` (run by `run_tests.sh --only headless` and `base`):
  six parts built, exported (STEP; STL for the meshed plate), imported without a timeline and
  rebuilt only through the tools (start_rebuild, describe_reference, every plan step,
  compare_to_reference and its fixes, finish_rebuild), then the timeline checked, check_design,
  and one early value edited; plus compare's fallback (68 checks):

  | Part | Plan steps | Fix rounds | Match | Faces | Timeline after finish |
  |---|---|---|---|---|---|
  | bracket (L, holes in both legs, fillet, chamfer) | 10 | 0 | 1.0 | 14/14 | sketch extrude sketch hole pattern sketch hole pattern chamfer fillet |
  | plate with a 4 x 3 hole grid | 5 | 0 | 1.0 | 18/18 | sketch extrude sketch hole pattern |
  | flange with a hub and 6 bolt holes | 9 | 0 | 1.0 | 12/12 | sketch extrude sketch extrude sketch hole sketch hole pattern |
  | revolved knob with a blind bore | 4 | 0 | 1.0 | 6/6 | sketch revolve sketch hole |
  | block with a boss and a pocket | 6 | 0 | 1.0 | 13/13 | sketch extrude sketch extrude sketch extrude |
  | plate with two holes from an STL | 5 | 0 | 0.99995 | 150/150 | sketch extrude sketch hole pattern |

  Plus the same loop through the real MCP server (`--mcp`, 14 checks), and every rebuild
  tool in the headless runner (`RUNNER_SESSION`: the refusals, a ready hole call, finish
  keeping the original).
- Scenarios (real clicks): `rebuild_start` (70 checks: the browser's right-click, the
  reference and its picture, the window for AI apps and the clipboard, undo / redo, the same
  body again, the chat with a fake Claude key, the 3D view's right-click on a body, an empty
  spot and a rebuild; three rebuilds and none chosen, a rebuilt body deleted while Compare
  is open, Undo), `rebuild_compare_finish` (66: the numbers, the verdict in a person's
  words, the 8 green regions, the AI's compare drawing too, done, Finish from Compare, Esc,
  Finish with one undo and redo, keep the original and the reference), `rebuild_mesh_reopen`
  (39: a broken mesh refused in a window, a mesh rebuilt, Compare and Esc, save / close /
  reopen with the reference), `rebuild_chat` (20: SciForge's own chat with a fake local model
  that reads only SciForge's answers rebuilds the plate, from the right-click to Finish).
- Unit tests `test_rebuild_core.py` (21: regions, groups, the verdict for an AI and for a
  person, sampled volumes, faces in words, the message); the docs runner runs the recipe,
  the troubleshooting block and the tools' examples.

### Known gaps (at-tools)

- Fusion's **Find Features** (recognize fillets / holes / chamfers in place, in direct
  modeling) is not built: Auto Timeline rebuilds the part instead. Its reading is
  at-recognize's (see Recognition).
- `compare` on a 298-face plate (96 chamfered holes), in this sandbox shared by six builders
  (load about 4.5): the same solid 0.3 to 0.6 s (no boolean), the base plate only (96 holes
  left) 1.5 s, 10 holes left 2.2 s, every chamfer and 4 holes left (188 regions) 3.7 s.
  OpenCASCADE's General Fuse alone is 0.5 to 2.4 s of that (the most when the two parts
  share most of their faces); the brief's 2 s holds for the same solid and for the base
  plate, not with 10 or 188 regions left at this load (about half on a PC without other
  jobs).
- A region is said in words for holes, bosses, rounded edges, chamfers, blocks and layers;
  anything else is "a piece of material about a x b x c". Ready calls exist for holes and
  fillets / chamfers of equal distances only (a pocket or a boss is described, not built).
- The frame: comparisons are in the rebuilt body's coordinates and the selectors in its
  component's; a rebuilt body that is itself moved inside its component (never done by the
  rebuild) would make the selectors' coordinates differ.
- A reference made from a mesh: `done` comes when every facet lies within the mesh's
  tolerance of the rebuild, so a hole a hair off still counts as matched there.

## QA (beta 3)

(the independent QA pass, branch `sf/autotimeline-qa`; session log
`docs/sciforge/sessions/beta3-autotimeline-qa.md`)

What the QA pass found and fixed, each with a check in
`SciForgeTests/headless/rebuild_qa.py` (run by `rebuild_e2e.main()`, so by `run_tests.sh
--only headless / base`; `SCIFORGE_REBUILD_FILTER=qa` runs only them) or the scenario
`rebuild_qa_joints` that fails on the code before the fix:

| Found | Fixed |
|---|---|
| Finish deleted every joint of a jointed part (the VEX case), its ground, the source of a pattern of bodies of it and the face a sketch of another body sat on (that body changed shape) | what used the original moves onto the rebuild first (see Finish above); what cannot keeps the original, hidden, and the answer / window says why |
| Finish deleted an original whose extrude also cut another body: that body lost the cut | such a follower step keeps the original (hidden) |
| Finish left the original's imported shape in its component (a stray "Body001 (imported)" step) | deleted with the original |
| A jointed part driven while it was rebuilt: the reference stayed where it was frozen (compare said match 0.16, the plan came out turned, the ghost stood apart) | the reference keeps the frame it was frozen in and moves with the rebuild's component (`FrozenFrame`); the ghost follows |
| A design saved half way and opened again: the next steps went into the design's first body ("No base set" on the hole after) | the body of the rebuild going on is the active one again (window and headless) |
| The reference deleted another way than Finish (delete_step, a script) left the original hidden for good | the rebuild is given up: the original is shown again |
| start_rebuild given the id import_file answers with (the component's) refused: "pick the body" | a component with one solid body stands for it |
| describe_reference on a plate with a modeled thread: 210 s (OpenCASCADE's defeaturing on the thread's faces), then no base read | a thread round a bore is closed with its hole, never defeatured, listed as not read (1.3 s) |
| describe_reference on a VEX plate with 125 square holes (506 faces): 56 s | the base check compares faces before any boolean, planes are bucketed by offset (and at-recognize skips axes with many more levels): 9 s |
| The chat's ready message waited in the box with nothing saying so | a tip says to read it and press Send |
| check_design while a rebuild went on took the hidden original under its rebuild for an overlap (NOT OK) | the originals being rebuilt are left out of the interference check (said in the answer) |
| compare called holes with a chamfered or countersunk rim "a round hole ... with a pointed (drilled) end" | the cone's two radii tell a drill point from a widened rim |
| A VEX C-channel (410 faces) was also read along its length: 51 levels of square holes, a section and booleans each (37 s) | an axis with far more levels than another reading already found is not read (25 s; the rest is at-recognize's sections) |
| A plate with a boss and 60 holes in the face the boss stands on: no hole was closed by its rim (`Face.cutHoles` changes the face in place and answers None), every hole went to OpenCASCADE's defeaturing (12.7 s) | the face is rebuilt in place (0.3 s) |
| There was no way to give a rebuild up but Undo (none at all in a design opened again: the original stayed hidden, the ghost drawn) | Stop Rebuild... (UTILITIES > AI, the rebuilt body's right-click): the original shown again, the rebuilt body deleted or kept, one undo step |
| A name the person gave the rebuild while it was built was replaced at Finish by the original's name at start; an original renamed meanwhile was kept as "<old name> (original)" | Finish keeps the person's name for the rebuild and uses the original's name as it is now |
| check_design after a Finish that kept the original (asked, or because something still used it): "NOT OK: Body and Body (original) overlap" (an AI could move a body to fix it) | the kept original is marked (`SciForgeKeptUnder`) and left out of check_design and interference, said in a warning |
| A body of a component linked to another design (Insert of a saved design) was rebuilt in place: Finish deleted its link (0 linked copies) while the component still said linked, and Break Link then refused ("the design is not found") | refused at start, with what to do: rebuild it in its own design (every linked copy follows), or Break Link first |
| A part rebuilt in its own design while another design (a robot) links it: the robot said the part's design was not found and kept the old shape (Finish's rebuilt body is another object) | a linked copy whose body is gone finds the body of that design with the same name again when the design opens (`design_insert._relink`; a linked design FreeCAD opened only partly is loaded whole for it) |
| With the history marker rolled back, compare and Finish said the rebuild was still empty ("build the base shape first"): an AI would build the plan a second time | they say the marker leaves N steps of the rebuild out and to move it to the end |
| A part whose base cannot be read (free-form, the forged lever): its plan's holes failed with FreeCAD's "No base set, sketch support is not Part::Feature", and compare said "its step 1 is the base" (a hole) | a hole on a body without a solid says so ("there is no solid ... build its base shape first"); compare says to build the base yourself when describe could not read it; troubleshooting for the known gaps (base not read, a fillet made before a cut, a selector that picks more edges, a slow describe) |
| With two rebuilds going on, the 3D view's right-click on one rebuilt body compared, finished or stopped the other one (the active body's: the rebuild started last) | the right-click's entries act on the body under the mouse |
| A mesh of 37,740 triangles (an STL exported finely): start_rebuild took 160 s and describe_reference 250 s, FreeCAD frozen (the time grows much faster than the count; describe made the solid again) | a mesh over 10,000 triangles is refused at once with what to do (MESH tab > Reduce, or a coarser export); describe reads the reference's solid |
| Raised or engraved text on a plate made the whole part unreadable (base `none`, every face unrecognized, a plan of a sketch and a hole that failed) | the letters are closed over like holes: the plate and its hole are read and planned, each free-form group of letters is listed (raised or engraved, its size and place, `sketch_text` + extrude to make a text) |

Tried and found right: a body that already has a timeline, two rebuilds at once (each tool
takes `reference`; the dialogs ask to select the rebuilt body), undo / redo across start, the
AI's steps and finish, component instances (a pasted copy follows the rebuild), parts of
0.5 mm and 2 m, an inch STEP file (read at its size; the plan's numbers are millimetres: 12.7
for half an inch), a 294-face plate (describe 1.7 s, compare 1.6 to 2.2 s while holes are
left, 0.4 s when done, finish 2 s), a loft (said not read: the notes say to build it by
hand).

Known gaps found by the QA pass (not fixed):

- A free-form face that is not a text or a logo on a flat face (a loft, a sweep, letters on a
  round face) still leaves the whole base unread (at-recognize's free-form rule); letters made
  of straight lines and arcs only are read as a boss, those with curves are listed, not built.
- A VEX C-channel still takes about 25 s in describe_reference (its sections and the booleans
  of its through cuts: at-recognize's reading).
- Deleting the rebuilt body by hand (Delete) leaves the rebuild going on (the ghost, the
  hidden original) until it is started again (a new rebuilt body) or stopped (Stop
  Rebuild... in UTILITIES > AI: the rebuilt body's right-click is gone with it).
- A thread rebuilt with SciForge's thread tool on the planned hole matches every face but the
  bore's (its seam differs): finish with even_if_different.
- Stop Rebuild (and an undone start) shows the original again even if it was hidden before
  the rebuild started.
- Finish with keep_original: a design that links the part keeps following the hidden
  original, not the rebuild.
- UTILITIES > AI > Compare / Finish / Stop take the active body's rebuild when several go on
  (the right-clicks take the one clicked).

## Journey (beta 3)

(the journey tester, branch `sf/journey-rebuild`; session log
`docs/sciforge/sessions/journey-rebuild.md`; scenarios `SciForgeTests/gui/scenarios/
journey_rebuild*.py`, their steps and the numbers worked out by hand in
`SciForgeTests/gui/journey_rebuild_steps.py`)

Auto Timeline used the way Luca would, with real clicks and keys only: a mounting bracket a
stranger sent as a STEP file (four counterbored holes on a 2 x 2 grid, a pocket, a chamfer, two
fillets) and a meshed STL plate, rebuilt as parametric parts, then used in the rest of
SciForge. The AI is a fake local model in SciForge's own chat that reads only SciForge's answers
(as scenario `rebuild_chat`): describe_reference's plan, compare_to_reference after every
feature, the fixes the verdict offers, finish_rebuild when the person says so.

| Scenario | What a person does | Checks |
|---|---|---|
| `journey_rebuild` | Insert STEP (bracket and a clamp), a joint (J, two clicks), right-click > Rebuild with Timeline (AI)..., Send; Compare with Reference 100 %; "finish" in the chat; one Ctrl+Z / Ctrl+Y; the base extrude double-clicked 10 -> 12, the hole 6 -> 6.5 | 86 |
| `journey_rebuild_sim` | the same rebuild, then SIMULATION: Fixed on the counterbores' floors, 1000 N down on the far end, Solve; DESIGN: 2 mm thicker; out of date; Solve again | 76 |
| `journey_rebuild_mesh` | Insert Mesh, rebuilt by hand (no AI set up): typed rectangle, E 8, Compare, an early Finish (Cancel), saved and opened again half way, two circles on the top face, E -8 All, Compare done, Finish; saved, opened again, made 10 thick | 65 |
| `journey_rebuild_reopen` | the AI's rebuild saved half way, closed, opened again, finished by hand; saved, opened again; the edits | 88 |

What the journey found and fixed (each with a test that fails on the code before):

| Found | Fixed |
|---|---|
| A rebuilt part made 2 mm thicker (its base extrude double-clicked, 10 -> 12) kept its pocket and its counterbores at the old height, sealed under a 2 mm skin: two shells, 65115 mm3 instead of 64889 by hand, and check_design said OK. The plan sketched every feature that starts on the top face on an origin plane at a fixed offset | those sketches go on the top face itself, in the plane's axes (`create_sketch` takes `face` with `plane` and `offset` now: attached to the face, turned and moved on it so the plan's numbers stay the plane's; the plane at its offset when the face is not found); describe_reference adds the face when the part has exactly one flat face there. Tests: `test_ai_catalog`, `rebuild_e2e` (one shell after the early edit), `journey_rebuild` |
| The recipe's own example said "its holes still go through" at 12 mm: its hole sketch was at offset 10, so the top 2 mm stayed closed (27576.3 mm3 instead of 27350.1); the docs runner only checked the size | the recipe sketches the holes on the top face, a good habit says why, and the last call expects 27350.1 mm3 (docs runner) |
| Compare said a meshed plate's holes were at (60.003, 24) and offered the Single Hole there: a 63-facet polygon's box is off its axis | the faceted region is placed by its centroid: (60, 24) (`test_rebuild_core`) |
| Finish Rebuild in the window deleted the original by default even when the rebuild did not match yet (a meshed plate at 92 %, its holes not cut) | a rebuild that does not match keeps the original, hidden, by default; Delete stays the default for one that matches (`journey_rebuild_mesh`) |
| The same for a hole drilled in a boss's top or in a pocket's floor: the boss made taller or the pocket deeper left the hole behind, sealed inside (three shells) | the plan puts a sketch on the end face of any earlier extrude it lies on (a join's top, a cut's floor) when the part has exactly one flat face there (`rebuild_e2e` follow_checks) |
| An AI that left the plan's chamfer out got "the differences could not be listed (OpenCASCADE could not split the two parts, so the volumes were sampled)" and no ready call: the strip's end triangle was read at the middle of its parameters, on its long side, where it also lies on the original's end face, so the strip counted as common | a piece's face is read at a point off its edges: "a chamfered edge, about 2 (60 mm long)", its call ready (`rebuild_e2e` strip_checks; `journey_rebuild`, whose AI forgets the chamfer) |

Tried and found right: the chat's ready message, the AI's steps as one undo step each, the
timeline in Fusion's order (sketch, extrude, sketch, cut, sketch, hole, pattern, chamfer,
fillet), Compare 100 %, Finish (the original's name, component and place; one undo step), the
joint made before the rebuild moved onto the rebuild at Finish and back at Ctrl+Z, the clamp
riding up 2 mm with the thicker top, the pattern following the hole's new diameter, the
study out of date after the edit and the stress dropping (120 -> 87 MPa; by hand 0.68 at the
pocket), Save / close / open again half way (the ghost, the active rebuilt body, the joint
still on the original) and after Finish, both for the AI's rebuild and the one by hand.

Known gaps found by the journey (not fixed):

- A face is followed only when it is the end face of an extrude of the plan on the same
  plane and the part has exactly one flat face there; a feature that starts on a face made
  otherwise (a revolve, a side face along another axis, two faces at one height) is still
  sketched at a fixed offset.
- SciForge's own chat stops after 25 requests per Send (`chat_core.MAX_STEPS`): a model that
  makes one call per request and follows the recipe's loop (describe, every plan step, a
  compare after every feature) reaches it on a part of more than about 14 plan steps (the
  bracket took 17), and the person then says "continue" (counted, not run).
- A sketch made by hand on a face holds the face's projected outline (Fusion's auto project),
  so pressing E from it picks no profile: the person clicks the circles (as in Fusion).

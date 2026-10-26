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
| Defeaturing | holes closed by rebuilding the faces around their rims (milliseconds), then chamfers and fillets taken off with OpenCASCADE's defeaturing (`shape.defeaturing`, all at once, else by halves); a feature that cannot be taken off, or whose removal changes the volume far more than such a feature holds (a slanted face of a groove taken for a chamfer), stays in the base and is said so; parts with free-form faces left are not defeatured (their base cannot be read) | the base is read from the solid without its features: sharp corners and simple lines |
| Base, extrude | along X, Y or Z: every flat face square to the axis (levels) or along it, every round face along it; the section of each level; the biggest level's region extruded over the levels whose outline it covers; what is extra are bosses, what is missing pockets / cuts (each one a band of equal sections); each boss or cut is read along the axis its open side faces (the holes in a channel's flanges along Y, those in its web along Z); a cut through everything, or one that could go through without taking more (the same hole in both flanges), is `through_all`; walls on a draft give a `taper` (a drafted pocket or boss, a drafted block, a drafted hole in a straight block, a drafted block with a cavity: a molded box); a cut that opens onto a round face (a keyway, a flat on a shaft) goes from its floor out of the part, a boss standing on one (a port on a pipe) from its top into the part, from the origin plane or a round value when the part is solid there; when no axis fits every face, an axis is tried with up to a quarter of the area in such features. Of the readings, the one with the fewest steps wins, then the one whose steps add or take the least volume (a round boss on a block is a boss along Z, not the block's side outline with its corners cut off) | `create_sketch` on the origin plane at the right offset (geometry: `rect`, `circle`, `slot`, `polyline` or `segments` of lines and arcs that close exactly) + `extrude` (`flip`, `symmetric` or `two_sides` when the part straddles the plane); bosses / cuts on one level with the same height in one sketch (regions that touch go in sketches of their own: one sketch would merge them); copies of one boss, pocket or opening on a grid or circle as one extrude and a pattern (a VEX plate's square holes: one cut and a 5 x 10 pattern) |
| Base, revolve | every face a surface of revolution about an origin axis (flat faces square to it with round edges about it, coaxial cylinders, cones, tori, spheres): the half profile cut by a half plane | `create_sketch` on XZ (axis Z) or XY (axis X / Y) + `revolve` a full turn |
| Base with features along another axis | when no axis fits every face, an axis is tried with up to a quarter of the area in features along the others; the base extrude may then stop inside such a feature, at a level or at its middle (a rod or a tube that ends in an eye: the rod, then the eye as a boss along its own axis, in FreeCAD's example assembly placed at angles) | the base extrude, then each boss or cut along its own axis |
| What is not taken off | pieces of one round wall cut in pieces that together go half way round or more are no fillet (taking such a "fillet" off ran out of memory and crashed FreeCAD); a hole crossed by many other faces (a bore with a ring of slots) is left in the base without trying (one such defeaturing took 3 minutes) | said in the notes; the hole is listed in `unrecognized` |
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

`SciForgeTests/headless/recognize_bench.py` (`run_tests.sh --only recognize`), the final run on this sandbox (times are wall-clock on 4 CPUs shared with five other builders). 61 parts: 61 pass, 0 fail. Each part: built, exported to STEP, imported as a body without a timeline, described, rebuilt from the plan through the headless AI executor, compared (volume within 0.1 %, every face matched; for the STEP files made by other programs, every surface: they split faces the rebuild keeps whole).

| Part | Faces | Found | Plan steps | Volume | Faces matched | describe (s) | Total (s) | Result |
|---|---|---|---|---|---|---|---|---|
| box_basic | 6 | extrude | 2 | +0.0000 % | 6 / 6 | 0.126 | 0.752 | PASS |
| cylinder_extrude | 3 | extrude | 2 | +0.0000 % | 3 / 3 | 0.035 | 0.162 | PASS |
| hex_prism | 8 | extrude | 2 | -0.0000 % | 8 / 8 | 0.619 | 0.766 | PASS |
| l_bracket_profile | 8 | extrude | 2 | +0.0000 % | 8 / 8 | 0.259 | 0.403 | PASS |
| slot_extrude | 6 | extrude | 2 | +0.0000 % | 6 / 6 | 0.235 | 0.388 | PASS |
| bracket_inner_fillet | 9 | extrude, fillet r3 | 3 | +0.0000 % | 9 / 9 | 0.3 | 0.571 | PASS |
| fillet_top_edges | 10 | extrude, fillet r2 | 3 | +0.0000 % | 10 / 10 | 0.193 | 0.57 | PASS |
| fillet_one_vertical_edge | 7 | extrude, fillet r5 | 3 | +0.0000 % | 7 / 7 | 0.376 | 0.65 | PASS |
| fillet_all_edges | 26 | extrude, fillet r2 | 3 | +0.0000 % | 26 / 26 | 0.208 | 1.13 | PASS |
| chamfer_top_edges | 10 | extrude, chamfer 2 | 3 | +0.0000 % | 10 / 10 | 0.349 | 0.765 | PASS |
| chamfer_one_edge | 7 | extrude, chamfer 3 | 3 | +0.0000 % | 7 / 7 | 0.257 | 0.458 | PASS |
| blend_chamfer_top_face | 10 | extrude, chamfer 2 | 3 | +0.0000 % | 10 / 10 | 0.169 | 0.51 | PASS |
| plate_through_hole_cut | 7 | extrude, 1 hole | 4 | +0.0000 % | 7 / 7 | 0.227 | 0.509 | PASS |
| pattern_rect_hole_grid_fusion | 12 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 12 / 12 | 0.221 | 0.617 | PASS |
| flange_polar_holes | 9 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 9 / 9 | 0.055 | 0.416 | PASS |
| hole_blind | 8 | extrude, 1 hole | 4 | +0.0000 % | 8 / 8 | 0.1 | 0.422 | PASS |
| hole_counterbore | 9 | extrude, 1 hole | 4 | +0.0000 % | 9 / 9 | 0.306 | 0.715 | PASS |
| hole_countersink | 8 | extrude, 1 hole | 4 | +0.0000 % | 8 / 8 | 0.172 | 0.619 | PASS |
| hole_single_angled | 8 | extrude, 1 hole | 4 | -0.0000 % | 8 / 8 | 0.263 | 0.533 | PASS |
| pocket_depth | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.43 | 0.709 | PASS |
| symmetric_cut_slot | 10 | extrude | 2 | +0.0000 % | 10 / 10 | 0.31 | 0.643 | PASS |
| sf_cylinder_boss | 8 | extrude | 4 | -0.0000 % | 8 / 8 | 0.09 | 0.255 | PASS |
| mirror_boss | 10 | extrude, 1 pattern | 5 | +0.0000 % | 10 / 10 | 0.112 | 0.432 | PASS |
| pattern_rect_symmetric_bosses | 36 | extrude, 1 pattern | 5 | +0.0000 % | 36 / 36 | 0.796 | 1.523 | PASS |
| shell_open_box | 11 | extrude | 3 | +0.0000 % | 11 / 11 | 0.405 | 0.681 | PASS |
| shell_filleted_box | 19 | extrude | 3 | -0.0000 % | 19 / 19 | 0.755 | 1.365 | PASS |
| revolve_washer | 4 | extrude, 1 hole | 4 | +0.0000 % | 4 / 4 | 0.062 | 0.193 | PASS |
| groove_ring | 7 | extrude | 4 | +0.0000 % | 7 / 7 | 0.115 | 0.365 | PASS |
| sf_revolve_cone | 2 | revolve | 2 | +0.0000 % | 2 / 2 | 0.038 | 0.319 | PASS |
| bench_stepped_shaft | 7 | revolve | 2 | -0.0000 % | 7 / 7 | 0.292 | 0.477 | PASS |
| bench_knob | 6 | revolve, 1 hole | 4 | +0.0000 % | 6 / 6 | 0.125 | 0.361 | PASS |
| bench_bracket_holes | 12 | extrude, 3 holes, 1 pattern, fillet r3 | 8 | +0.0000 % | 12 / 12 | 0.511 | 1.334 | PASS |
| bench_mount_plate | 18 | extrude, 4 holes, 1 pattern, fillet r6 | 6 | +0.0000 % | 18 / 18 | 1.748 | 2.747 | PASS |
| extrude_taper_cut | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.816 | 1.293 | PASS |
| extrude_taper_join_all | 11 | extrude | 4 | +0.0000 % | 11 / 11 | 0.817 | 1.58 | PASS |
| sf_draft_four_sides | 6 | extrude | 2 | -0.0000 % | 6 / 6 | 0.085 | 0.374 | PASS |
| bench_turned_bracket | 12 | extrude, 3 holes, 1 pattern, fillet r3 | 9 | -0.0000 % | 12 / 12 | 0.513 | 1.4 | PASS |
| bench_shaft_cross_hole | 4 | extrude, 1 hole | 4 | -0.0001 % | 4 / 4 | 0.166 | 0.665 | PASS |
| bench_vex_channel | 70 | extrude, 2 patterns | 8 | -0.0000 % | 70 / 70 | 4.36 | 6.915 | PASS |
| bench_side_boss | 9 | extrude | 4 | +0.0000 % | 9 / 9 | 0.185 | 0.583 | PASS |
| bench_keyed_shaft | 10 | extrude | 6 | -0.0000 % | 10 / 10 | 1.104 | 1.793 | PASS |
| bench_pipe_port | 7 | extrude, 2 holes | 8 | +0.0005 % | 7 / 7 | 1.244 | 2.228 | PASS |
| bench_clevis | 11 | extrude, 1 hole | 4 | +0.0000 % | 11 / 11 | 0.384 | 0.626 | PASS |
| bench_opposed_holes | 10 | extrude, 2 holes | 6 | +0.0000 % | 10 / 10 | 0.132 | 0.358 | PASS |
| bench_vex_plate | 206 | extrude, 1 pattern | 5 | +0.0000 % | 206 / 206 | 5.466 | 53.855 | PASS |
| bench_vex_angle | 50 | extrude, 2 patterns | 8 | -0.0000 % | 50 / 50 | 1.345 | 2.692 | PASS |
| bench_shaft_collar | 5 | extrude, 2 holes | 6 | +0.0002 % | 5 / 5 | 0.202 | 0.915 | PASS |
| bench_chamfered_boss | 9 | extrude, chamfer 1 | 5 | +0.0000 % | 9 / 9 | 0.121 | 0.399 | PASS |
| bench_chamfered_shaft | 5 | extrude, chamfer 1.5 | 3 | +0.0000 % | 5 / 5 | 0.086 | 0.192 | PASS |
| bench_offset_flange | 9 | extrude, 6 holes, 1 pattern | 7 | +0.0000 % | 9 / 9 | 0.092 | 0.54 | PASS |
| bench_part_300 | 300 | extrude, 294 holes, 1 pattern | 5 | +0.0000 % | 300 / 300 | 2.062 | 19.176 | PASS |
| contract and odd shapes |  | None |  |  |  |  | 0.34 | PASS |
| pi5_case.step #0 | 62 | extrude, 4 holes, 1 pattern | 19 | -0.0000 % | 62 / 62 (surfaces all) | 3.283 | 8.025 | PASS |
| pi5_case.step #1 | 56 | extrude, fillet r1 | 5 | +0.0000 % | 56 / 56 (surfaces all) | 2.5 | 4.307 | PASS |
| as1-ac-214.stp #0 | 18 | extrude, 6 holes | 4 | +0.0000 % | 6 / 18 (surfaces all) | 0.226 | 1.003 | PASS |
| EPL22_6_16.stp #0 | 36 | extrude, 1 pattern, fillet r1, chamfer 0.443784/1 | 8 | -0.0000 % | 36 / 36 (surfaces all) | 3.11 | 4.439 | PASS |
| plate_through_hole_cut (mesh) | 7 | extrude, 1 hole | 4 | +0.0000 % | 7 / 7 | 0.435 | 0.606 | PASS |
| flange_polar_holes (mesh) | 9 | extrude, 6 holes, 1 pattern | 5 | +0.0000 % | 9 / 9 | 4.264 | 4.633 | PASS |
| l_bracket_profile (mesh) | 8 | extrude | 2 | +0.0000 % | 8 / 8 | 0.283 | 0.362 | PASS |
| bench_knob (mesh) | 6 | revolve, 1 hole | 4 | +0.0000 % | 6 / 6 | 3.567 | 3.839 | PASS |
| bench_mount_plate (mesh) | 18 | extrude, 4 holes, 1 pattern, fillet r6 | 6 | +0.0000 % | 18 / 18 | 3.763 | 4.68 | PASS |

### Real files from other programs

Every solid of every STEP file in the repository (made by other programs: the AS1 test
assembly, a part library of electronic packages, a forged lever, the Pi 5 case) and of four of
FreeCAD's example documents (the CAM hole puzzle, PartDesignExample, EngineBlock,
AssemblyExample), 71 distinct solids from 36 files, each described and rebuilt from the plan
through the headless AI executor (a scratch sweep; four of them are also in the benchmark):

| Result | Solids | Which |
|---|---|---|
| rebuilt exactly | 19 | the Pi 5 case (both parts), PartDesignExample, EngineBlock's block, two assembly parts, IDF bodies with chamfers and patterns |
| exactly, faces split in the file | 12 | the AS1 plates, brackets and nuts (each bore in two half faces), CAM test blocks, an assembly bracket: the same volume and surfaces, whole faces in the rebuild |
| within 1e-7 of the volume | 4 | a lead with tiny two-distance chamfers, two excavator links whose tangent arcs missed each other by 5e-7 mm |
| a step stopped | 1 | an excavator bucket (97 faces): a fillet's selector found 5 edges where it expected 1 (the step stops; nothing is rounded wrongly) |
| base not read (said so) | 35 | free-form bodies (SMD chips, a capacitor, the forged lever), molded IC bodies drafted both ways from a parting line, a CAM test part of turned and hexagonal features, assembly parts where a round boss crosses a rod; their holes, fillets and chamfers are still listed |

Before this sweep: a curve type FreeCAD has no Python class for stopped the whole reading, a
base ended 1e-6 mm short of the boss on it (two snaps in a row), tangent arcs did not close a
sketch, a hole whose rim is rounded started below the round, slanted groove faces read as
chamfers filled the groove (+15 % volume), and three files took 26 to 169 s; all fixed (see the
session log).

### Known gaps

| Gap | Why | What describe() does |
|---|---|---|
| Free-form faces: lofts, sweeps, pipes, coils, B-spline surfaces, embossed text, variable fillets, modelled threads | no extrude or revolve of lines and arcs makes them | the base is `none` (or the faces stay in the base); they are listed in `unrecognized` with a sentence |
| Profiles with ellipse or spline edges | `create_sketch` has `ellipse` (axis along x only) and `spline_loop` (a curve through points), which do not give back the original curve exactly | not attempted: listed |
| A drafted block with bosses on it, or whose top or bottom is not one flat face | the base is read as the outline of its bottom face extruded with the walls' draft up to its top face | a drafted block, one with a cavity or pockets, and drafted pockets / bosses / holes in a straight block are read; this is listed |
| Fillets between leaning (drafted) walls | SciForge's tapered walls are flat B-spline faces: the round between them is a B-spline, not a cylinder or a torus | the round stays in the shape; the base is then not read |
| Sheet metal bent in two directions with closed corners | the bends stay in the base (OpenCASCADE's fillet builder crashed on such corners); some trays read as a floor and walls along X and Y, others not | the rest is listed |
| Oblique holes starting on a curved face, bosses / pockets on sloped faces | the Hole tool's Single Hole needs a flat face; a sloped boss is along no origin axis | listed |
| Several solids in one shape | the contract reads one solid | the largest is read, the note says how many others there are (describe them one by one) |
| Countersunk at both ends | the Hole tool makes one end | the plan makes the first end, a note asks for the other |
| A face split in two in the original (a split face, a face cut for a sketch region) | the plan rebuilds it as one face | volume exact; the bench's face check fails on those golden models (`direct_split_face_*`) |
| Meshes | only parts that are prismatic or turned once their holes are closed, from CAD-quality meshes (not scans); fillets across a mesh are not recovered | open meshes are refused with repair advice; the rest is read as the faceted solid and listed |
| Speed of fillet-heavy and complex parts | OpenCASCADE's defeaturing: one call for all fillets (in chunks it is slower), which cannot be interrupted | a 202-face part with 98 fillet faces takes about 19 s (15 s of it defeaturing); a 434-face connector about 45 s |
| A fillet or chamfer step whose short selector ("the edge along X at the top") finds more edges on the rebuilt part | the edges are picked on the part as it will be; when an earlier step rebuilt something slightly differently, more edges can match | the step stops with a count error (never rounds the wrong edges); pick the edges with query_geometry |

## Reference, compare and finish

(builder at-tools)

## AI tools and documentation

(builder at-tools)

## The command a person uses

(builder at-tools)

## Tests

(builders at-recognize and at-tools, each its own lines)

- **Recognition (at-recognize)**: `SciForgeTests/unit/test_recognize_core.py` (56 tests, pure
  Python: numbers and measured values, snapping twice is snapping once, planes, loops and the
  create_sketch items they become, exact arc / line closure and arcs that miss each other by
  noise, patterns with noise, ideal pattern points, the plan's ids and Fusion's order, plan
  arguments checked by the catalogue, frames and Euler angles, circle / cylinder fits, arcs
  fitted on mesh sections, round values beyond a value, where a base extrude may end inside a
  feature along another axis); `SciForgeTests/headless/recognize_bench.py`
  (real FreeCAD 1.1.4: 50 parts built, sent through STEP and back as bodies without a
  timeline, described, rebuilt from the plan by the headless AI executor, compared: volume
  within 0.1 % and every face of the original matched; 4 solids of STEP files made by other
  programs and 3 parts of FreeCAD's example assembly placed at angles, compared face by face
  or surface by surface; 5 meshes of golden models through recognize_mesh;
  the contract on odd input; describe() on a 300-face part under 5 s), run by
  `tools/sciforge/run_tests.sh --only recognize` and at the end of `--only headless` / `--only
  base`. Two scratch sweeps (not in the suite) found the bugs listed in the session log: every
  golden model that builds one solid (505 described, 404 rebuilt exactly, 418 with a base read;
  the rest are free-form, sheet metal bent both ways or split faces) and the 71 real solids
  above.

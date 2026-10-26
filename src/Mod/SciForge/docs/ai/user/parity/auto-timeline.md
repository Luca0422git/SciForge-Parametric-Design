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
| Finish | `finish(ref, target=None, keep_reference=False, keep_original=False)`: the rebuilt body takes the original's name, component and place; the original is deleted (an imported body with its imported shape; a mesh body with its steps) or kept hidden as `<name> (original)`; the reference removed or kept hidden (not drawn). One undo step. |
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
| Where | **Rebuild with Timeline (AI)...** on a body's (and a mesh body's) right-click in the browser, on the 3D view's right-click list when a body is under the mouse (a small hook in `marking_menu.py`: `CONTEXT_ITEMS`), and in UTILITIES > AI (with Compare with Reference and Finish Rebuild). On a body being rebuilt the 3D view's list offers Compare with Reference and Finish Rebuild instead. |
| Start | one undo step "Rebuild with Timeline"; a refusal (a broken mesh, a body without a solid) is said in a small window with the reason and what to do. |
| The AI | when SciForge's own chat has an AI set up (a key kept, or a local model's address), the AI panel opens on its Chat tab with the message in the box, not sent: the person reads it, may change it, and presses Send. Otherwise a window says how to ask an AI app (Claude Desktop, Gemini CLI, Claude Code...: add it, turn AI control on, paste the message), with the message in an editable box, already on the clipboard, Copy Message, Add an AI... and Close. The message names the body, the rebuilt body, the recipe and the four tools. |
| Compare with Reference | a window with the match, the volumes (missing red, extra green), the faces matched, the largest gap, the verdict (the AI's, said with the buttons' names instead of the tools') and one row per difference; the 3D view shows the missing material red and the extra green, see-through, until the window closes (Close or Esc), the next compare, or Finish. Compare Again; Finish Rebuild... opens Finish. |
| Finish Rebuild | a window: whether the rebuild matches (match, faces), Delete the original body (default) or Keep the original, hidden; Keep the reference (hidden); Finish / Cancel (Esc). One undo step "Finish Rebuild". |

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

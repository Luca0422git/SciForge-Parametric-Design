# Recipe: rebuild a part that has no timeline (reverse engineering)

Tags: rebuild, reverse-engineering, auto-timeline, step, stl, mesh, parametric, start_rebuild, describe_reference, compare_to_reference, finish_rebuild

A part that came in without a timeline (an imported STEP body, an STL or 3MF mesh of a simple
part, any body whose steps are lost) rebuilt as real, editable timeline steps: sketches,
extrudes, holes, patterns, fillets, with its key sizes as parameters. Fusion has no such tool
(its Mesh to BRep gives a body without features); SciForge's Auto Timeline gives you the part
frozen as a reference, its features read as numbers with a plan of tool calls, and a
comparison that says what is still missing after every step. Every call below was run by
SciForge's tests; `expect` is what the answer must contain.

## When to use it

- The person asks to "make this part parametric", "give it a timeline", "reverse engineer
  it", or right-clicked a body and chose **Rebuild with Timeline (AI)...** (SciForge then sends
  you a message naming the body; the rebuild is already started).
- The part is a body without a timeline (an imported STEP body shows one "Insert STEP" step)
  or a mesh body. A mesh must be watertight (start_rebuild refuses one with holes and says
  so); simple parts work best: plates, brackets, blocks with holes, pockets and bosses,
  turned parts, fillets and chamfers.

## The loop

1. `start_rebuild` with the body's id (`get_design` lists the bodies). The part becomes the
   reference (frozen, drawn faint, never a body or a step) and a new empty body
   `<name> (rebuilt)` is made at its place and made active. Every step you build goes
   there.
2. `describe_reference`: the part read as numbers. `base` is the base shape (an extrude with
   its plane, profile and distance, or a revolve), `features` the holes, pockets, bosses,
   patterns, fillets and chamfers with their sizes, and `plan` a list of tool calls in
   Fusion's order (base shape, cuts and bosses, holes, patterns, chamfers, fillets last).
   Each plan step's `args` passes the tool's own check: send them as they are. A step's `id`
   is the id SciForge will give it; when an answer reports another id, use that one in the
   later steps that name it (`uses` says which arguments do).
3. Build the plan step by step, reading each answer (the volume and size it reports).
4. `compare_to_reference` after every feature (it changes nothing; about a second). `match`
   is the share of the volume that agrees (1 is identical); `missing` is material of the
   original the rebuild lacks, `extra` material the rebuild has and the original does not (a
   hole not cut yet is extra material shaped like a cylinder); each region says what it
   looks like ("a round hole about 6 mm across, 10 deep") and, when SciForge is sure, `fix`:
   the tool call that makes it (a Single Hole on the right face, a fillet of exactly those
   edges). `groups` puts equal regions together with one call for all of them. `verdict`
   says what to do next, in that order. Fix it, compare again.
5. `finish_rebuild` when compare says `done` (match at least 0.999, every face of the
   original matched, no face of the rebuild left over). The rebuilt body takes the original's
   name, component and place; the original is deleted (`keep_original: true` keeps it,
   hidden, as `<name> (original)`). Whatever used the original (joints, a ground, a pattern
   of it, a sketch on one of its faces) moves onto the rebuild face for face, so a jointed
   part stays jointed; what cannot move keeps the original (hidden: the answer names it).
   finish_rebuild compares first and refuses a rebuild that is not done
   (`even_if_different: true` finishes it anyway: a person happy with a close rebuild of a
   mesh).

## Good habits

- **Key sizes as parameters.** Before the first sketch, `set_parameter` the sizes a person
  would change (width, depth, thickness, hole diameter, spacing) and drive the steps with
  them (`set_sketch_dimension` with `expression`, `set_model_parameter`, `expressions`), as in
  [the parametric plate](sciforge://docs/recipes/parametric-plate.md). The rebuild is then a
  part a person can change, which is the point.
- **Fusion's order.** Base shape first, then cuts and bosses, holes, patterns, chamfers, and
  fillets last (a fillet made early breaks when a later cut changes its edges).
- **Real features, not copied faces.** Never rebuild by copying the reference's faces or
  outlines as geometry: a hole is a `hole`, four equal holes are one hole and a
  `rectangular_pattern` (or one sketch with four circles), a rounded edge is a `fillet`.
  The numbers come from describe_reference and compare; round them the way a person types
  them (6, not 5.99998).
- **What describe_reference could not read** is in `unrecognized` (faces with selectors and
  why) and in `notes`; `confidence` says how much of the part the plan explains. Build what
  it read, then use compare's regions and `query_geometry` on the rebuild to work out the
  rest (a free-form face may need `loft` or `sweep`; a text or a thread may stay out: say so).
- **Meshes.** A mesh becomes the reference as flat facets: sizes come out rounded (a 5.98 mm
  hole of 32 facets is "about 6"), match stays a little under 1 where round faces are
  facets, and faces are matched within the mesh's tolerance. Build round holes, not polygons.
- **When a step fails,** read the sentence (the usual causes are in
  [troubleshooting](sciforge://docs/troubleshooting.md#rebuilding-a-part-auto-timeline)),
  fix the arguments, call it again; `undo` takes back a step that came out wrong. The
  rebuild's timeline is like any other: `edit_step`, `delete_step`, `roll_timeline` work.
- **Coordinates** are the rebuilt body's own; for a part at the origin (as Insert STEP makes
  it) they are the design's. describe_reference says which in `coordinates`.

## 1. The part to rebuild

Here the part is made, exported as STEP and inserted into a new design so this recipe runs
anywhere; with a real part, the person has already inserted it. A plate 60 x 40 x 10 with
four 6 mm holes and its vertical corners rounded 3 mm: 24000 - 4 x pi x 3^2 x 10 - 4 x (9 -
9 pi / 4) x 10 = 22791.8 mm3.

```json sciforge-calls
[
  {"tool": "new_design", "args": {"name": "Original"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40]}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_sketch", "args": {"plane": "XY", "offset": 10, "geometry": [
    {"circle": [10, 10, 3]}, {"circle": [50, 10, 3]}, {"circle": [10, 30, 3]},
    {"circle": [50, 30, 3]}]}},
  {"tool": "hole", "args": {"sketch": "Sketch2", "diameter": 6, "through_all": true}},
  {"tool": "fillet", "args": {"edges": {"type": "line", "parallel": [0, 0, 1],
    "not_on_faces": {"type": "cylinder"}, "count": 4}, "radius": 3},
   "expect": {"contains": ["22791.8 mm3"]}},
  {"tool": "export", "args": {"format": "step", "path": "{tmp}/plate.step"}},
  {"tool": "new_design", "args": {"name": "Rebuilt plate"}},
  {"tool": "import_file", "args": {"path": "{tmp}/plate.step"},
   "expect": {"contains": ["1 body", "22791.8 mm3"]}},
  {"tool": "get_timeline", "args": {}, "expect": {"contains": ["insert_step"]}}
]
```

## 2. Start, and read the part

The imported body is `Body001` (the new design's empty `Body` comes first).

```json sciforge-calls
[
  {"tool": "start_rebuild", "args": {"body": "Body001"},
   "expect": {"contains": ["is the reference now", "Its id is 'Body002'", "(rebuilt)"]}},
  {"tool": "describe_reference", "args": {},
   "expect": {"contains": ["\"plan\"", "\"features\"", "\"base\""]}},
  {"tool": "compare_to_reference", "args": {},
   "expect": {"contains": ["still empty"], "json": {"match": 0, "done": false}}}
]
```

## 3. The base, with its sizes as parameters

The plan's base is a 60 x 40 rectangle extruded 10 mm. Built with named sizes:

```json sciforge-calls
[
  {"tool": "set_parameter", "args": {"name": "width", "value": 60}},
  {"tool": "set_parameter", "args": {"name": "depth", "value": 40}},
  {"tool": "set_parameter", "args": {"name": "thickness", "value": 10}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [
    {"rect": [0, 0, 60, 40], "name": "plate"}]}},
  {"tool": "set_sketch_dimension", "args": {"sketch": "Sketch1", "constraint": "plate.width",
    "expression": "width"}},
  {"tool": "set_sketch_dimension", "args": {"sketch": "Sketch1", "constraint": "plate.height",
    "expression": "depth"}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10},
   "expect": {"contains": ["Its id is 'Extrude1'"]}},
  {"tool": "set_model_parameter", "args": {"step": "Extrude1", "label": "Distance",
    "expression": "thickness"}},
  {"tool": "compare_to_reference", "args": {},
   "expect": {"contains": ["4 round holes about 6 mm across, 10 deep (along Z) are not cut yet",
     "4 rounded edges of radius about 3 are still sharp", "groups[1].fix"],
     "json": {"done": false, "volume.missing": 0, "faces.reference": 14}}}
]
```

## 4. What compare says: the holes, then the rounded edges

The verdict lists the holes first (Fusion's order), at (10, 10), (50, 10), (10, 30), (50,
30). One sketch with four circles on the top and one `hole` make them in one step; compare
then has only the rounded edges left, with the fillet call ready in `groups[0].fix` (the
same edges as below).

```json sciforge-calls
[
  {"tool": "create_sketch", "args": {"plane": "XY", "offset": 10, "geometry": [
    {"circle": [10, 10, 3]}, {"circle": [50, 10, 3]}, {"circle": [10, 30, 3]},
    {"circle": [50, 30, 3]}]}},
  {"tool": "hole", "args": {"sketch": "Sketch2", "diameter": 6, "through_all": true},
   "expect": {"contains": ["Its id is 'Hole1'"]}},
  {"tool": "compare_to_reference", "args": {},
   "expect": {"contains": ["4 rounded edges of radius about 3 are still sharp",
     "groups[0].fix"], "json": {"groups.0.fix.tool": "fillet", "groups.0.fix.args.radius": 3}}},
  {"tool": "fillet", "args": {"edges": {"type": "line", "parallel": [0, 0, 1],
    "not_on_faces": {"type": "cylinder"}, "count": 4}, "radius": 3},
   "expect": {"contains": ["Its id is 'Fillet1'", "22791.8 mm3"]}},
  {"tool": "compare_to_reference", "args": {},
   "expect": {"contains": ["Done: the rebuilt part matches the original"],
     "json": {"done": true, "match": 1, "faces.matched": 14}}}
]
```

## 5. Finish, and check it is a real parametric part

```json sciforge-calls
[
  {"tool": "finish_rebuild", "args": {},
   "expect": {"contains": ["is now the rebuilt part", "the original was deleted"]}},
  {"tool": "check_design", "args": {}, "expect": {"json": {"ok": true}}},
  {"tool": "get_timeline", "args": {},
   "expect": {"contains": ["\"kind\": \"extrude\"", "\"kind\": \"hole\"",
     "\"kind\": \"fillet\""], "not_contains": ["insert_step"]}},
  {"tool": "set_parameter", "args": {"name": "thickness", "value": 12},
   "expect": {"contains": ["60 x 40 x 12 mm"]}},
  {"tool": "check_design", "args": {}, "expect": {"json": {"ok": true}}}
]
```

The plate is now 12 mm thick, its holes still go through and its corners are still rounded:
the rebuild is a part a person can change.

## Variations

- **Keep the original** to compare by eye later: `finish_rebuild` with `keep_original: true`
  (hidden, renamed `<name> (original)`).
- **Several rebuilds in one design:** each call takes `reference` (the reference's id, or the
  original's or the rebuilt body's); without it the tools use the rebuild of the active body.
- **A mesh body** (from `import_file` of an STL): `start_rebuild` with the mesh body's id;
  the rest is the same.
- **A person rebuilding by hand** uses the same pieces in the window: UTILITIES > AI >
  Compare with Reference (the numbers, missing material red and extra green in the 3D view)
  and Finish Rebuild.

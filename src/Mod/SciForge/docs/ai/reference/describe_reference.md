# `describe_reference`: Describe reference

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: Browser: right-click a body > Rebuild with Timeline (AI)... (beyond Fusion). Category: Rebuild with a timeline. Read-only. Needs an open design, a rebuild going on (start_rebuild).

## What it does

What the reference of a rebuild is made of, read by SciForge from its faces: summary (volume, area, size, counts, the kinds of faces), base (the base shape: an extrude with its plane, profile and distance, a revolve, a box...), features (holes, counterbores, pockets, bosses, slots, fillets, chamfers, patterns, each with its numbers and the faces it explains), plan (tool calls in Fusion's order: base shape, cuts and bosses, holes, patterns, chamfers, fillets last; each step's args pass the tool's own check, so send them as they are, adjusting ids the answers give), unrecognized (faces it could not read, with selectors and why), confidence (0..1) and notes. Coordinates are the rebuilt body's (the design's for a part at the origin). detail: plan (default: the features and the plan), summary (the part's numbers only, quick) or full (also every face of every feature, as selectors).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `reference` | string |  |  |  | the rebuild's reference (its id, or the original's / the rebuilt body's id); default: the rebuild of the active body, or the only one in the design |
| `detail` | `plan` \| `summary` \| `full` |  | `"plan"` |  | plan: features and plan; summary: numbers only; full: also every face |
| `max_features` | integer |  |  | >= 1, <= 500 | at most this many features |

## Answer

A plain sentence, then JSON with: `reference`, `original`, `original_kind`, `rebuilt`, `coordinates`, `summary`, `base`, `features`, `plan`, `unrecognized`, `confidence`, `notes`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Without a rebuild going on (start_rebuild): `No rebuild is going on in this design: call start_rebuild with the body to rebuild first (an imported STEP body, any solid body or a mesh body).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: the plate's features and a plan of tool calls

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_sketch", "args": {"plane": "XY", "offset": 10, "geometry": [{"circle": [30, 20, 4]}]}},
  {"tool": "hole", "args": {"sketch": "Sketch2", "diameter": 8, "through_all": true}},
  {"tool": "export", "args": {"format": "step", "path": "/home/me/sciforge/plate.step"}},
  {"tool": "new_design", "args": {"name": "Rebuild"}},
  {"tool": "import_file", "args": {"path": "/home/me/sciforge/plate.step"}},
  {"tool": "start_rebuild", "args": {"body": "Body001"}}
]
```

The call:

```json
{"tool": "describe_reference", "args": {}}
```

The answer:

```text
Body001, read from its 7 faces: 1 feature, a plan of 4 steps. Build the plan in the active body 'Body001 (rebuilt)', compare_to_reference after each feature.
{
 "reference": "RebuildReference",
 "original": "Body001",
 "original_kind": "body",
 "rebuilt": "Body002",
 "coordinates": "design",
 "summary": {
  "volume": 23497.345175,
  "area": 6950.796447,
  "bbox": [0.0, 0.0, 0.0, 60.0, 40.0, 10.0],
  "size": [60.0, 40.0, 10.0],
  "solids": 1,
  "faces": 7,
  "edges": 15,
  "surfaces": {"plane": 6, "cylinder": 1}
 },
 "base": {
  "kind": "extrude",
  "plane": "XY",
  "direction": "Z",
  "offset": 0.0,
  "distance": 10.0,
  "from": 0.0,
  "to": 10.0,
  "profile": [
   [
    {"line": [0.0, 40.0, 0.0, 0.0]},
    {"line": [0.0, 0.0, 60.0, 0.0]},
    {"line": [60.0, 0.0, 60.0, 40.0]},
    {"line": [60.0, 40.0, 0.0, 40.0]}
   ]
  ],
  "profile_words": "rectangle 60 x 40",
  "levels": [0.0, 10.0],
  "steps": [1, 2]
 },
 "features": [
  {
   "id": "F1",
   "kind": "hole",
   "diameter": 8.0,
   "through": true,
   "axis": [0.0, 0.0, -1.0],
   "start": [30.0, 20.0, 10.0],
   "steps": [3, 4],
   "face_count": 1
  }
 ],
 "plan": [
  {
   "step": 1,
   "tool": "create_sketch",
   "args": {"plane": "XY", "geometry": [{"rect": [0.0, 0.0, 60.0, 40.0]}]},
   "why": "The base profile (rectangle 60 x 40) on the XY plane.",
   "features": [],
   "id": "Sketch1"
  },
  {
   "step": 2,
   "tool": "extrude",
   "args": {"profile": "Sketch1", "distance": 10.0},
   "why": "Extrude it 10 mm: the base shape.",
   "features": [],
   "id": "Extrude1",
   "uses": {"profile": 1}
  },
  {
   "step": 3,
   "tool": "create_sketch",
... (19 more lines)
```

## More argument examples

- the features and the plan of the rebuild going on:
  `{}`
- every face of every feature too:
  `{"detail": "full"}`
- only the part's size, volume and kinds of faces:
  `{"detail": "summary"}`

## See also

- Recipe: [rebuild a part that has no timeline (reverse engineering)](sciforge://docs/recipes/reverse-engineer.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

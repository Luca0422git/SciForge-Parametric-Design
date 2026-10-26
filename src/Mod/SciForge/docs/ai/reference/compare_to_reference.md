# `compare_to_reference`: Compare to reference

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: Rebuild > Compare with Reference (beyond Fusion). Category: Rebuild with a timeline. Read-only. Needs an open design, a rebuild going on (start_rebuild).

## What it does

How far the rebuilt body is from the reference, to call after every feature: match (common volume / union volume; 1 is identical), volume (reference, rebuilt, common, missing, extra in mm3), missing (material of the original the rebuild lacks) and extra (material the rebuild has and the original does not: a hole not cut yet is extra material shaped like a cylinder), each region with its volume, centre, box, kind, what it looks like ('a round hole about 6 mm across, 10 deep', 'a rounded edge, radius about 2', 'a block 10 x 5 x 3') and, when SciForge is sure, fix: the tool call that makes it (a Single Hole, a fillet of exactly those edges); groups (equal regions together, with one fix for all of them); faces (how many of the original's faces the rebuild matches by geometry, and the unmatched ones of each side with a description and a selector); deviation (how far the surfaces are apart, max and mean, mm); size_notes; done (match >= 0.999, every face of the original matched and none of the rebuild left over); and verdict: what to do next, in words. Changes nothing; in the window it also shows the differences (missing material red, extra green, until the next compare or finish; show false: not). body: compare another body (default the rebuilt one). detail full lists every region and face.

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `reference` | string |  |  |  | the rebuild's reference (its id, or the original's / the rebuilt body's id); default: the rebuild of the active body, or the only one in the design |
| `body` | string |  |  |  | the body to compare (default: the rebuild's own body) |
| `detail` | `summary` \| `full` |  | `"summary"` |  | full: every region and face |
| `show` | boolean |  | `true` |  | show the differences in the window's 3D view |

## Answer

A plain sentence, then JSON with: `reference`, `rebuilt`, `frame`, `tolerance`, `match`, `volume`, `missing`, `extra`, `regions`, `faces`, `deviation`, `done`, `method`, `size_notes`, `groups`, `verdict`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Without a rebuild going on (start_rebuild): `No rebuild is going on in this design: call start_rebuild with the body to rebuild first (an imported STEP body, any solid body or a mesh body).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: after the base plate: the hole is not cut yet (with the hole call to make it)

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
  {"tool": "start_rebuild", "args": {"body": "Body001"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40]}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}}
]
```

The call:

```json
{"tool": "compare_to_reference", "args": {}}
```

The answer:

```text
Match 0.9791 (1 is identical); 6 of 7 faces of the original matched. Next: A round hole about 8 mm across, 10 deep (along Z) is not cut yet, at (30, 20) (the hole call is ready in groups[0].fix). Fix that, then compare_to_reference again.
{
 "reference": "RebuildReference",
 "rebuilt": "Body002",
 "frame": "design",
 "tolerance": 0.001,
 "match": 0.979056,
 "volume": {
  "reference": 23497.345175,
  "rebuilt": 24000.0,
  "common": 23497.345175,
  "missing": 0,
  "extra": 502.654825
 },
 "missing": [],
 "extra": [
  {
   "volume": 502.654825,
   "center": [30.0, 20.0, 5.0],
   "bbox": [26.0, 16.0, 0.0, 34.0, 24.0, 10.0],
   "looks_like": "a round hole about 8 mm across, 10 deep",
   "kind": "cylinder",
   "diameter": 8.0,
   "depth": 10.0,
   "axis": [0.0, 0.0, -1.0],
   "at": [30.0, 20.0, 5.0],
   "ends": [[30.0, 20.0, 10.0], [30.0, 20.0, 0.0]],
   "fix": {
    "tool": "hole",
    "args": {
     "face": {"type": "plane", "normal": [0.0, 0.0, 1.0], "count": 1},
     "at": [30.0, 20.0, 10.0],
     "diameter": 8.0,
     "through_all": true
    }
   }
  }
 ],
 "regions": {"missing": 0, "extra": 1},
 "faces": {
  "reference": 7,
  "matched": 6,
  "rebuilt": 6,
  "rebuilt_matched": 4,
  "unmatched_reference": [
   {
    "kind": "cylinder",
    "describe": "a round hole face 8 mm across along Z at (30, 20) (251.3 mm2)",
    "selector": {"type": "cylinder", "radius": 4.0, "count": 1},
    "area": 251.327412
   }
  ],
  "unmatched_rebuilt": [
   {
    "kind": "plane",
    "describe": "a flat face 60 x 40 facing -Z at z = 0 (2400 mm2)",
    "selector": {"type": "plane", "normal": [0.0, 0.0, -1.0], "count": 1},
    "area": 2400.0
   },
   {
    "kind": "plane",
    "describe": "a flat face 60 x 40 facing +Z at z = 10 (2400 mm2)",
    "selector": {"type": "plane", "normal": [0.0, 0.0, 1.0], "count": 1},
    "area": 2400.0
   }
  ]
 },
 "deviation": {"max": 5.0, "mean": 0.05077},
 "done": false,
 "method": "exact",
... (21 more lines)
```

## More argument examples

- how far the rebuild is, and what to do next:
  `{}`
- every region and face, no picture:
  `{"detail": "full", "show": false}`

## See also

- Recipe: [rebuild a part that has no timeline (reverse engineering)](sciforge://docs/recipes/reverse-engineer.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

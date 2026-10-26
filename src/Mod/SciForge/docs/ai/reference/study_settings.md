# `study_settings`: Study settings

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > MANAGE > Settings. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Study settings". Needs an open design.

## What it does

Read or change a study's settings; with none given it answers them all. mesh_size: average element size in % of the model's size (default 10, Fusion's; smaller is finer and slower), or mesh_size_mm as a length; element_order parabolic (default, more accurate) or linear; curved_elements; gravity on / off (off by default) and gravity_direction; remove_rigid_body_modes: for a model held by nothing whose loads balance (off by default); contact_tolerance: bodies closer than this (mm, default 0.1) are glued; safety_basis yield / ultimate; keep_results: keep the mesh and results in the design file (on; off keeps only the numbers, the file stays small); adaptive_refinement (Fusion's Adaptive Mesh Refinement, none by default): solve, refine where the stress changes the most, solve again until the peak von Mises stress changes by less than 10 / 5 / 2 % (low / medium / high). study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `mesh_size` | number |  |  | >= 0.5, <= 50 | average element size, % of the model size |
| `mesh_size_mm` | number | mm |  | >= 0 | average element size in mm (0: use mesh_size) |
| `element_order` | `parabolic` \| `linear` |  |  |  | element order |
| `curved_elements` | boolean |  |  |  | parabolic elements follow curved faces |
| `gravity` | boolean |  |  |  | switch gravity on or off |
| `gravity_direction` | array of 3 numbers |  |  |  | which way gravity pulls [x, y, z] |
| `remove_rigid_body_modes` | boolean |  |  |  | hold free pieces whose loads balance |
| `contact_tolerance` | number | mm |  | >= 0, <= 10 | bodies closer than this are glued (mm) |
| `safety_basis` | `yield` \| `ultimate` |  |  |  | what the safety factor divides |
| `keep_results` | boolean |  |  |  | keep the mesh and results in the design file |
| `adaptive_refinement` | `none` \| `low` \| `medium` \| `high` |  |  |  | solve again on a mesh made finer where the stress changes the most, until the peak stress settles (low 2, medium 4, high 6 solves at most) |

## Answer

A plain sentence, then JSON with: `study`, `id`, `mesh_size`, `mesh_size_mm`, `element_order`, `curved_elements`, `gravity`, `gravity_direction`, `remove_rigid_body_modes`, `contact_tolerance`, `safety_basis`, `keep_results`, `adaptive_refinement`, `local_mesh_controls`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: a finer mesh and gravity on

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_study", "args": {}}
]
```

The call:

```json
{"tool": "study_settings", "args": {"mesh_size": 5, "gravity": true}}
```

The answer:

```text
Done: Study 1 - Static Stress's settings changed.
{
 "study": "Study 1 - Static Stress",
 "id": "SimStudy",
 "mesh_size": 5.0,
 "mesh_size_mm": 0.0,
 "element_order": "parabolic",
 "curved_elements": true,
 "gravity": true,
 "gravity_direction": [
  0.0,
  0.0,
  -1.0
 ],
 "remove_rigid_body_modes": false,
 "contact_tolerance": 0.1,
 "safety_basis": "yield",
 "keep_results": true,
 "adaptive_refinement": "none",
 "local_mesh_controls": []
}
```

## More argument examples

- the settings as they are:
  `{}`
- a finer mesh and gravity on:
  `{"mesh_size": 5, "gravity": true}`

## See also

- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

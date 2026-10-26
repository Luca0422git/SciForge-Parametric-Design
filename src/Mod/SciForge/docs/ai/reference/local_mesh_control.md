# `local_mesh_control`: Local mesh control

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > MANAGE > Local Mesh Control. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Local mesh control". Needs an open design.

## What it does

Make the mesh finer (smaller elements, size in mm) on picked faces, edges or whole bodies of a study, blending back into the study's element size: where the stress matters (a hole, a fillet in a corner). on: where it acts, a list of picks: {"face": selector}, {"edge": selector} or {"vertex": {"at": ...}} on a body, with "of": the body (or a step in it; default the active body). Every face / edge / corner a selector picks is used (give count). A whole body: {"body": id}. study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `on` (required) | array of objects |  |  | at least 1 item(s) | where the mesh is finer |
| `size` (required) | number | mm |  | > 0 | the element size there (mm) |
| `label` | string |  |  |  | its name (default: Local Mesh Control 1...) |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Called without arguments, the arguments are refused before anything runs: `Not done: on is missing; size is missing.`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: 2 mm elements on the held end

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_study", "args": {}},
  {"tool": "add_constraint", "args": {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]}}
]
```

The call:

```json
{"tool": "local_mesh_control", "args": {"on": [{"face": {"normal": [-1, 0, 0], "count": 1}}], "size": 2}}
```

The answer:

```text
Done: Local Mesh Control 2 mm 'Local Mesh Control 1' (id 'SimItem001') in Study 1 - Static Stress, on Body.Face4.
```

## More argument examples

- 0.5 mm elements in two holes:
  `{"on": [{"face": {"type": "cylinder", "count": 2}}], "size": 0.5}`

## See also

- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

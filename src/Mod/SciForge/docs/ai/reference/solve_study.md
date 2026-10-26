# `solve_study`: Solve study

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > SOLVE > Solve. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Solve study". Needs an open design.

## What it does

Solve a study on this computer (Gmsh meshes it, CalculiX solves it; Fusion solves in Autodesk's cloud): seconds for a simple part, minutes for a fine mesh; SciForge waits until it is done (timeout, seconds: then it gives up). Answers the main numbers: the lowest safety factor and where, the largest von Mises stress and displacement, the mesh size; study_results has everything. A solve is not an undo step; the last results stay when it fails. study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `timeout` | number |  | `600` | > 0, <= 7200 | give up after this many seconds |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: solve it

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_study", "args": {}},
  {"tool": "add_constraint", "args": {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]}},
  {"tool": "add_load", "args": {"kind": "force", "on": [{"face": {"normal": [1, 0, 0], "count": 1}}], "magnitude": 2000, "direction": "vector", "vector": [0, 0, -1]}}
]
```

The call:

```json
{"tool": "solve_study", "args": {}}
```

The answer:

```text
Done: Study 1 - Static Stress solved (1137 nodes, 528 elements). Lowest safety factor 1.27 at (6.121, 26.13, 10) mm on Body1: below 2. Largest von Mises stress 163.2 MPa, largest displacement 0.212 mm. study_results has every number.
```

## More argument examples

- solve the newest study:
  `{}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

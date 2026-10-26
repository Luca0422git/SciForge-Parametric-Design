# `add_constraint`: Structural constraint

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > CONSTRAINTS > Structural Constraints. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Fixed constraint". Needs an open design.

## What it does

Hold part of the model in a study (Fusion's structural constraints). kind: fixed (no movement; x / y / z false frees that design axis, a roller), pin (round faces only: radial keeps the hole's size and place, axial stops sliding along it, tangential stops turning about it; default radial and axial, so it can turn like a hinge), frictionless (faces: no movement across the face, free to slide along it: a symmetry plane or a smooth support), displacement (a prescribed displacement: x / y / z in mm, null = free). on: where it acts, a list of picks: {"face": selector}, {"edge": selector} or {"vertex": {"at": ...}} on a body, with "of": the body (or a step in it; default the active body). Every face / edge / corner a selector picks is used (give count). study: the study's id or name (create_study answers it; default the newest study). A model must be held so it cannot move or spin freely (six directions in all), or the solve fails with that reason.

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `kind` (required) | `fixed` \| `pin` \| `frictionless` \| `displacement` |  |  |  | the kind of constraint |
| `on` (required) | array of objects |  |  | at least 1 item(s) | where it holds |
| `x` | boolean or number or null |  |  |  | fixed: held along X (default true); displacement: mm or null |
| `y` | boolean or number or null |  |  |  | fixed: held along Y (default true); displacement: mm or null |
| `z` | boolean or number or null |  |  |  | fixed: held along Z (default true); displacement: mm or null |
| `radial` | boolean |  | `true` |  | pin: the hole keeps its size and place |
| `axial` | boolean |  | `true` |  | pin: no sliding along the pin |
| `tangential` | boolean |  | `false` |  | pin: no turning about the pin |
| `label` | string |  |  |  | its name (default: Fixed 1, Pin 1...) |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Called without arguments, the arguments are refused before anything runs: `Not done: kind is missing; on is missing.`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: the plate's left end held in place

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
{"tool": "add_constraint", "args": {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]}}
```

The answer:

```text
Done: Fixed 'Fixed 1' (id 'SimItem') in Study 1 - Static Stress, on Body.Face4.
```

## More argument examples

- the bottom face held in place:
  `{"kind": "fixed", "on": [{"face": {"normal": [0, 0, -1], "count": 1}}]}`
- two holes on pins that let the part turn:
  `{"kind": "pin", "on": [{"face": {"type": "cylinder", "radius": 3.25, "count": 2}}]}`
- a symmetry plane:
  `{"kind": "frictionless", "on": [{"face": {"normal": [0, -1, 0], "count": 1}, "of": "Body"}]}`
- the end face pushed 0.5 mm down:
  `{"kind": "displacement", "on": [{"face": {"normal": [1, 0, 0], "count": 1}}], "x": null, "y": null, "z": -0.5}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

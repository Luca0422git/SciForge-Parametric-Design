# `add_load`: Structural load

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > LOADS > Structural Loads. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Force load". Needs an open design.

## What it does

Push on part of the model in a study (Fusion's structural loads). kind: force (N; direction normal pushes into each picked face, Fusion's default; vector gives [x, y, z]; several picks share the force by area unless per_entity gives each one the whole force), pressure (MPa, always into the faces; negative pulls), moment (N mm about the first face's normal or about vector, spread over the faces as a twist that keeps them deformable; per_entity: each face gets the whole moment), bearing (N, round faces: a pin or shaft pressing along vector, most in the middle of the loaded half and never pulling), remote_force (N along vector acting from point [x, y, z] mm, carried to the faces with its lever arm). flip reverses it. on: where it acts, a list of picks: {"face": selector}, {"edge": selector} or {"vertex": {"at": ...}} on a body, with "of": the body (or a step in it; default the active body). Every face / edge / corner a selector picks is used (give count). study: the study's id or name (create_study answers it; default the newest study). Gravity is in study_settings.

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `kind` (required) | `force` \| `pressure` \| `moment` \| `bearing` \| `remote_force` |  |  |  | the kind of load |
| `on` (required) | array of objects |  |  | at least 1 item(s) | where it pushes |
| `magnitude` (required) | number | mm |  |  | N (force, bearing, remote_force), MPa (pressure) or N mm (moment) |
| `direction` | `normal` \| `vector` |  | `"normal"` |  | force / moment: along the face's normal or along vector |
| `vector` | array of 3 numbers |  |  |  | the direction [x, y, z] (design axes) |
| `point` | array of 3 numbers | mm |  |  | remote_force: where the force acts from (mm) |
| `per_entity` | boolean |  | `false` |  | force / moment: every pick gets the whole value |
| `flip` | boolean |  | `false` |  | reverse the direction |
| `label` | string |  |  |  | its name (default: Force 1, Pressure 1...) |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Called without arguments, the arguments are refused before anything runs: `Not done: kind is missing; on is missing; magnitude is missing.`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: 2 kN down on its right end

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
{"tool": "add_load", "args": {"kind": "force", "on": [{"face": {"normal": [1, 0, 0], "count": 1}}], "magnitude": 2000, "direction": "vector", "vector": [0, 0, -1]}}
```

The answer:

```text
Done: Force 2000 N 'Force 1' (id 'SimItem001') in Study 1 - Static Stress, on Body.Face2.
```

## More argument examples

- 200 N pressing down on the top face:
  `{"kind": "force", "on": [{"face": {"normal": [0, 0, 1], "count": 1}}], "magnitude": 200, "direction": "vector", "vector": [0, 0, -1]}`
- 2 MPa inside a bore:
  `{"kind": "pressure", "on": [{"face": {"type": "cylinder", "count": 1}}], "magnitude": 2}`
- 5 N m twisting the end of a shaft about its axis:
  `{"kind": "moment", "on": [{"face": {"normal": [0, 0, 1], "count": 1}}], "magnitude": 5000}`
- a pin pulling a lug's hole upward with 1 kN:
  `{"kind": "bearing", "on": [{"face": {"type": "cylinder", "count": 1}}], "magnitude": 1000, "vector": [0, 0, 1]}`
- 100 N hanging 50 mm beyond the end face:
  `{"kind": "remote_force", "on": [{"face": {"normal": [1, 0, 0], "count": 1}}], "magnitude": 100, "vector": [0, 0, -1], "point": [150, 5, 5]}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

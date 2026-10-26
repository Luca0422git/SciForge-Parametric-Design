# `study_results`: Study results

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > RESULTS (legend, Show Min / Max, Reaction Force, Results Details). Category: Simulation. Read-only. Needs an open design.

## What it does

The results of a study's last solve as numbers: the minimum and maximum of every result (safety factor, von Mises, 1st / 3rd principal and the stress components in MPa, displacement in mm, strain) with where they are [x, y, z] mm, per body (material, largest stress and displacement, lowest safety factor), the reaction force at every constraint (N), the mesh, and the verdict in a sentence (lowest safety factor against target: "lowest safety factor 1.4 at (x, y, z) on Body1: below 2"; below 1 the part would bend for good). out_of_date: the design or the study changed since the solve. results: only these result keys. Without a study and with several studies it lists them. study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `target` | number |  | `2.0` | > 0 | the safety factor the part should reach |
| `results` | array of strings |  |  | at least 1 item(s) | only these results (default: all) |

## Answer

A plain sentence, then JSON with: `study`, `id`, `solved`, `out_of_date`, `verdict`, `safety`, `results`, `bodies`, `reactions`, `mesh`, `safety_basis`, `notes`, `units`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: three results and the verdict

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_study", "args": {}},
  {"tool": "add_constraint", "args": {"kind": "fixed", "on": [{"face": {"normal": [-1, 0, 0], "count": 1}}]}},
  {"tool": "add_load", "args": {"kind": "force", "on": [{"face": {"normal": [1, 0, 0], "count": 1}}], "magnitude": 2000, "direction": "vector", "vector": [0, 0, -1]}},
  {"tool": "solve_study", "args": {}}
]
```

The call:

```json
{"tool": "study_results", "args": {"results": ["safety", "von_mises", "displacement"], "target": 2}}
```

The answer:

```text
Lowest safety factor 1.27 at (6.121, 26.13, 10) mm on Body1: below 2.
{
 "study": "Study 1 - Static Stress",
 "id": "SimStudy",
 "solved": true,
 "out_of_date": false,
 "verdict": "Lowest safety factor 1.27 at (6.121, 26.13, 10) mm on Body1: below 2.",
 "safety": {
  "lowest": 1.2682905880492759,
  "at": [
   6.121,
   26.1309,
   10.0
  ],
  "body": "Body1",
  "target": 2.0
 },
 "results": {
  "safety": {
   "title": "Safety Factor",
   "unit": "",
   "min": 1.2682905880492759,
   "min_at": [
    6.121,
    26.1309,
    10.0
   ],
   "max": 15.0,
   "max_at": [
    60.0,
    0.0,
    0.0
   ]
  },
  "von_mises": {
   "title": "Stress: Von Mises",
   "unit": "MPa",
   "min": 0.8704580045044562,
   "min_at": [
    0.0,
    26.5958,
    5.0118
   ],
   "max": 163.21180804343996,
   "max_at": [
    6.121,
    26.1309,
    10.0
   ]
  },
  "displacement": {
   "title": "Displacement: Total",
   "unit": "mm",
   "min": 0.0,
   "min_at": [
    0.0,
    0.0,
    0.0
   ],
   "max": 0.21201575620458465,
   "max_at": [
    60.0,
    20.0,
    0.0
   ]
  }
 },
 "bodies": {
  "Body1": {
   "displacement_max": 0.21201575620458465,
... (29 more lines)
```

## More argument examples

- every number of the newest study's results:
  `{}`
- two results, target 1.5:
  `{"results": ["safety", "von_mises"], "target": 1.5}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

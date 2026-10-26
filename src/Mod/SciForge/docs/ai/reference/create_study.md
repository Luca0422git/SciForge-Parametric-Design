# `create_study`: New simulation study

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > STUDY > New Simulation Study (Static Stress). Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: New Static Stress study". Needs a solid body.

## What it does

Make a Static Stress study, Fusion's linear stress simulation: where a part is held (add_constraint), what pushes on it (add_load, or gravity in study_settings), then solve_study and study_results. The study uses each body's physical material (change it for the study only with set_study_material) and the bodies as they are now; bodies that touch (or are closer than 0.1 mm) are glued. bodies: the bodies it simulates (default: every solid body of the design, shown or hidden; not the tools a Combine used up). Answers the study's id. Linear static only: small deflections, materials that stay elastic and isotropic (3D-printed parts are not); results are a guide.

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `label` | string |  |  |  | its name (default "Study N - Static Stress") |
| `bodies` | array of strings |  |  | at least 1 item(s) | the bodies to simulate (default: every solid body, shown or hidden) |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without a solid body: `The design has no solid body yet: make one first (create_sketch + extrude, or primitive).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: a study of the plate

Starting from this design (made by these calls):

```json
[
  {"tool": "new_design", "args": {"name": "Example"}},
  {"tool": "create_sketch", "args": {"plane": "XY", "geometry": [{"rect": [0, 0, 60, 40], "name": "base"}]}},
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}}
]
```

The call:

```json
{"tool": "create_study", "args": {}}
```

The answer:

```text
Done: new Static Stress study 'Study 1 - Static Stress' (id 'SimStudy') of Body1. Next: add_constraint (where it is held), add_load (what pushes on it), then solve_study.
```

## More argument examples

- a study of every body:
  `{}`
- a study of one body:
  `{"label": "Bracket load", "bodies": ["Body"]}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

# `precheck_study`: Pre-check study

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > SOLVE > Pre-check. Category: Simulation. Read-only. Needs an open design.

## What it does

Check a study before solving it, like Fusion's Pre-check traffic light: ready (green), caution (yellow: it solves, but read the warnings) or cannot solve (red: what to fix), with every message as a sentence: missing constraints or loads, materials without the values a stress study needs, constraints or loads whose faces are gone, bodies that would fly away, bodies that overlap. study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |

## Answer

A plain sentence, then JSON with: `study`, `id`, `verdict`, `messages`, `constraints`, `loads`, `gravity`, `bodies`, `contacts`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: ready to solve?

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
{"tool": "precheck_study", "args": {}}
```

The answer:

```text
Study 1 - Static Stress: ready to solve.
{
 "study": "Study 1 - Static Stress",
 "id": "SimStudy",
 "verdict": "ready",
 "messages": [],
 "constraints": [
  "Fixed 1"
 ],
 "loads": [
  "Force 1"
 ],
 "gravity": false,
 "bodies": [
  "Body1"
 ],
 "contacts": []
}
```

## More argument examples

- is the newest study ready to solve?:
  `{}`

## See also

- Recipe: [is this bracket strong enough? (Static Stress)](sciforge://docs/recipes/static-stress.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

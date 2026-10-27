# `set_study_material`: Study material

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: SIMULATION > SETUP > MATERIALS > Study Materials. Category: Simulation. Changes the design (one undo step). Its undo step is named like "AI: Study material". Needs an open design.

## What it does

Choose the material a body is made of in one study only (Fusion's Study Materials; the design keeps its own): material is a key of the material library (steel, stainless, iron, aluminium, aluminium_6061, copper, titanium, abs, pla, pet, nylon, polycarbonate, acetal, acrylic, polypropylene, ptfe, peek, wood, glass) or same_as_model to go back to the body's physical material. safety_basis: what the safety factor divides for the whole study (yield: yield strength / von Mises, Fusion's default; ultimate: ultimate tensile strength / 1st principal stress, or the 3rd where the part is pushed together harder than pulled). Answers the values the study uses (E, Poisson's ratio, density, yield and ultimate strength). study: the study's id or name (create_study answers it; default the newest study).

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `study` | string |  |  |  | the study's id or name (default: the newest study) |
| `body` (required) | string |  |  |  | the body (or a step in it) |
| `material` (required) | string |  |  |  | a material key, or same_as_model |
| `safety_basis` | `yield` \| `ultimate` |  |  |  | what the safety factor divides |

## Answer

A plain sentence, then JSON with: `material`, `from`, `youngs_mpa`, `poisson`, `density`, `yield_mpa`, `ultimate_mpa`, `filled_in`, `safety_basis`. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Called without arguments, the arguments are refused before anything runs: `Not done: body is missing; material is missing.`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: the study in aluminium (the design stays steel)

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
{"tool": "set_study_material", "args": {"body": "Extrude1", "material": "aluminium"}}
```

The answer:

```text
Done: Body1 is Aluminum-Generic in Study 1 - Static Stress (units MPa, kg/m3).
{
 "material": "Aluminum-Generic",
 "from": "this study",
 "youngs_mpa": 70000.0,
 "poisson": 0.3499999940395355,
 "density": 2700.0,
 "yield_mpa": 95.0,
 "ultimate_mpa": 310.0,
 "filled_in": [
  "yield_mpa"
 ],
 "safety_basis": "yield"
}
```

## More argument examples

- this study in aluminium 6061:
  `{"body": "Body", "material": "aluminium_6061"}`
- back to the body's material:
  `{"body": "Body", "material": "same_as_model"}`

## See also

- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

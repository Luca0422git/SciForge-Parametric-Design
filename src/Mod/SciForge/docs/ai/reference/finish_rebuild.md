# `finish_rebuild`: Finish rebuild

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: Rebuild > Finish Rebuild (beyond Fusion). Category: Rebuild with a timeline. Changes the design (one undo step), destructive. Its undo step is named like "AI: Finish rebuild". Needs an open design, a rebuild going on (start_rebuild).

## What it does

Finish a rebuild: the rebuilt body takes the original's name, component and place, with its timeline; the original (the featureless body or the mesh body) is deleted, or kept hidden as '<name> (original)' with keep_original: true; the reference is removed (keep_reference: true keeps it, hidden). It first compares and refuses a rebuild that is not done yet (the answer says what is left); even_if_different: true finishes it as it is (a person happy with a close rebuild of a mesh). One undo step.

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `reference` | string |  |  |  | the rebuild's reference (its id, or the original's / the rebuilt body's id); default: the rebuild of the active body, or the only one in the design |
| `keep_original` | boolean |  | `false` |  | keep the original body, hidden and renamed '<name> (original)' |
| `keep_reference` | boolean |  | `false` |  | keep the reference, hidden |
| `even_if_different` | boolean |  | `false` |  | finish even though compare_to_reference does not say done |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Without a rebuild going on (start_rebuild): `No rebuild is going on in this design: call start_rebuild with the body to rebuild first (an imported STEP body, any solid body or a mesh body).`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: the rebuild matches: it takes the original's name and place

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
  {"tool": "extrude", "args": {"profile": "Sketch1", "distance": 10}},
  {"tool": "create_sketch", "args": {"plane": "XY", "offset": 10, "geometry": [{"circle": [30, 20, 4]}]}},
  {"tool": "hole", "args": {"sketch": "Sketch2", "diameter": 8, "through_all": true}}
]
```

The call:

```json
{"tool": "finish_rebuild", "args": {}}
```

The answer:

```text
Done: AI: Finish rebuild. Body001 is now the rebuilt part (id 'Body002') with 4 timeline steps; the original was deleted, the reference removed. Bodies now: Body001: 23497.3 mm3, 60 x 40 x 10 mm.
```

## More argument examples

- the rebuild becomes the part, the original is deleted:
  `{}`
- keep the original, hidden:
  `{"keep_original": true}`

## See also

- Recipe: [rebuild a part that has no timeline (reverse engineering)](sciforge://docs/recipes/reverse-engineer.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

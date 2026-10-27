# `start_rebuild`: Start rebuild

<!-- Generated from the tool catalogue (src/Mod/SciForge/sciforge/ai/catalog) by tools/sciforge/make_ai_docs.py: do not edit by hand. The unit test test_ai_docs_contract.py fails when this file and the catalogue differ. -->

Fusion: Browser: right-click a body > Rebuild with Timeline (AI)... (beyond Fusion). Category: Rebuild with a timeline. Changes the design (one undo step). Its undo step is named like "AI: Start rebuild of Body001". Needs an open design.

## What it does

Start rebuilding a part that has no timeline as real, editable timeline steps (Auto Timeline): an imported STEP body, any solid body, or a mesh body (made into a solid first; an open or broken mesh, or one of more than 10,000 triangles, is refused). SciForge freezes the part as the reference (drawn faint and see-through; never a body or a step, so it stays the target whatever you build), hides the original and makes a new empty body '<name> (rebuilt)' at its place, active: build the rebuild there with the normal tools. Then: describe_reference (the part's features and a plan of tool calls), build the plan step by step, compare_to_reference after every feature and fix what its verdict says, finish_rebuild when it says done. The recipe: docs_read recipes/reverse-engineer.md. One undo step. body: the id of the body (or of a step in it, of the mesh body, or of the component holding one body: what import_file answers); label: the reference's name (default '<name> (reference)').

## Arguments

| Argument | Type | Unit | Default | Limits | Description |
|---|---|---|---|---|---|
| `body` (required) | string |  |  |  | the body to rebuild: its id (get_design lists them), or its component's |
| `label` | string |  |  |  | a name for the reference (default '<name> (reference)') |

## Answer

A plain sentence. The example below shows a real one.

## Errors

- Without an open design: `No design is open: call new_design or open_design first (or create_sketch, which starts a new design).`
- Called without arguments, the arguments are refused before anything runs: `Not done: body is missing.`
- Arguments of the wrong type, out of their limits or not in the table are refused the same way, each problem in a sentence ("radius must be a number above 0").
- When it cannot be done the answer says why in a sentence (isError true) and nothing changes.

## Example 1: the imported plate becomes the reference; Body002 is made for the rebuild

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
  {"tool": "import_file", "args": {"path": "/home/me/sciforge/plate.step"}}
]
```

The call:

```json
{"tool": "start_rebuild", "args": {"body": "Body001"}}
```

The answer:

```text
Done: AI: Start rebuild of Body001. Body001 is the reference now (id 'RebuildReference': frozen, drawn faint; 7 faces, 23497.35 mm3, 60 x 40 x 10 mm). The new empty body 'Body001 (rebuilt)' is active: build the rebuild there. Its id is 'Body002'. Next: describe_reference (the part's features and a plan of tool calls), build the plan step by step, compare_to_reference after every feature, finish_rebuild when it says done. Bodies now: Body001: 23497.3 mm3, 60 x 40 x 10 mm.
```

## More argument examples

- rebuild the imported body Body001 with a timeline:
  `{"body": "Body001"}`
- a body named by its label:
  `{"body": "Bracket"}`

## See also

- Recipe: [rebuild a part that has no timeline (reverse engineering)](sciforge://docs/recipes/reverse-engineer.md)
- [All tools](sciforge://docs/tools.md), [the handbook](sciforge://docs/handbook.md)

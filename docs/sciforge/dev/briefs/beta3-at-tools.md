You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: Auto Timeline, the AI tools and the rebuild (builder at-tools, branch `sf/at-tools`)

Luca: "Using a connected AI, I want there to be the tool necessary for the AI to reverse engineer
premade models and make them parametric. That means mesh to parametric, or objects with no
timeline to have a timeline. In my testing, Claude opus 5.5 was able to reverse engineer a pretty
complicated model. So current frontier models are capable. But I want to make it easier. A tool
call and instructions on how to reverse engineer a model would be cool. or however you think is
easier/faster/efficient. I know that mesh to parametric already exists in the mesh tab, but for
non complex parts, i want a nicer option to make real parametric objects."

This is **beyond Fusion**. Builder at-recognize writes the engine that reads a featureless solid
(`sciforge/recognize.py`: `describe(shape, options)` gives features and a plan of tool calls; the
contract is in that file). You build everything around it: the reference and the comparison
(`sciforge/rebuild.py`, contract in that file: implement exactly it), the AI tools, the
documentation an AI reads, the command a person clicks, and the end-to-end proof. Merge
`sf/at-recognize` into your branch whenever it has something new you need.

Read first: `docs/sciforge/parity/ai.md` (the AI connector, the tools, the documentation for
AI models), `sciforge/ai/catalog/__init__.py` and `verify_tools.py` (how a tool is defined),
`sciforge/ai/actions/verify_actions.py` (how an action answers), `sciforge/ai/executor.py`,
`SciForgeTests/headless/runner.py` and `agent_e2e.py` (how tools are tested), `docs/ai/` (the
handbook and recipes), `sciforge/insert.py` (`solid_from_mesh`, Convert Mesh) and
`sciforge/step_import.py` (STEP bodies).

### What to build
1. **`sciforge/rebuild.py`** (no Qt), per its contract:
   - `start(doc, source)`: source = a body (any solid body; typically an imported STEP body) or a
     mesh body (made into a solid first with SciForge's own mesh-to-solid; refuse an open or
     broken mesh with a sentence). Freeze its solid in a hidden reference object (SciForgeType
     "RebuildReference": never a body, never a timeline step, not in the browser's design
     folders: check `browser_core`, `timeline_ops._is_step`, `joints.is_part`, `bodies.*` and
     export / inspect code paths), hide the original, show the reference faint and see-through
     (display only, through Coin, never a document property that lands in the undo history), make
     a new empty body "<name> (rebuilt)" at the same place and make it active.
   - `compare(ref, target)`: the numbers of the contract. Volumes by booleans (common / cut,
     OpenCASCADE; guard against failures with a fallback: sampled points inside / outside),
     `match` = common / union, the missing and extra regions (each solid of the cut results:
     volume, centre, bbox, and `looks_like`: "a round hole about 6 mm across, 10 deep" / "a
     rounded edge, radius about 2" / "a block 10 x 5 x 3" by a few cheap geometric tests), faces
     matched by geometry (same surface type, same plane / axis / radius within tolerance, and
     overlapping), the unmatched ones described with stable selectors (see
     `sciforge/ai/geometry_facts.py`), deviation sampled on both surfaces, `done`, and a verdict
     sentence that tells an AI exactly what to do next ("4 holes of 6 mm are missing at
     (10, 10), (50, 10), ..." / "the rebuilt part is 2 mm too tall"). Fast enough to call after
     every step (under 2 s on a 300-face part; measure).
   - `finish(ref, target, keep_reference)`: the rebuilt body takes the original's name, component
     and place; the original (featureless) body is deleted or kept hidden as Luca chooses (the
     dialog / tool asks); the reference goes unless kept. One undo step.
   - In the window: `compare` can show the differences in the 3D view (missing material red,
     extra green, see-through, cleared by the next compare or Finish), display-only.
2. **AI tools** (`sciforge/ai/catalog/rebuild_tools.py` + `sciforge/ai/actions/rebuild_actions.py`;
   pick the names with care: they are permanent): at least `start_rebuild` (body or mesh id),
   `describe_reference` (recognize.describe of the reference: summary, features, plan, notes;
   detail summary / full), `compare_to_reference`, `finish_rebuild`. Each with its schema, examples,
   availability ("needs a reference: call start_rebuild first"), plain-sentence errors. Every tool
   call is one undo step where it changes the design. Add them to the headless runner (every
   tool once) and regenerate `docs/ai` (`tools/sciforge/make_ai_docs.py`).
3. **Instructions an AI reads**: a recipe `docs/ai/recipes/reverse-engineer.md` (when to use it,
   the loop: start_rebuild, describe_reference, follow the plan step by step, compare_to_reference
   after every feature, fix what the verdict says, finish_rebuild when done; good habits: key
   sizes as user parameters so the part stays editable, Fusion's feature order, never copy the
   reference's faces as geometry, how to handle what describe_reference could not read, meshes),
   a handbook section, troubleshooting entries; the chat panel's system prompt index picks them up
   by itself (check). Every tool call in the docs runs in the docs runner (that is how it stays
   correct).
4. **A person's way in**: right-click on a body in the browser (and the canvas marking menu if a
   body is under the mouse) **Rebuild with Timeline (AI)...**, also in UTILITIES > AI. It starts
   the rebuild (start_rebuild), then opens the AI panel's chat with a ready message ("Rebuild
   <body> with a timeline: ...", editable, not sent until the person presses Send) when the
   built-in chat has an AI set up, else a small dialog that says how to ask a connected AI app
   (Claude Desktop, Gemini CLI...) and copies the message to the clipboard. Read
   `sciforge/ai_panel_ui.py`, `ai/chat_ui.py`. Also a plain **Compare with Reference** command
   (shows the numbers and the red / green picture) and **Finish Rebuild**, so a person can rebuild
   by hand too. Icons in `icons_rebuild.py`.
5. **The proof** (`SciForgeTests/headless/rebuild_e2e.py`, run by `run_tests.sh --only base`):
   for at least 6 parts of different kinds (a bracket with holes and fillets, a plate with a hole
   grid, a flange with a bolt circle, a revolved knob, a part with a pocket and a boss, a meshed
   plate from an STL), build the golden model, export STEP (or STL), import it as a featureless
   body, then do what an AI would do ONLY through the tools (start_rebuild, describe_reference,
   each plan step as its tool call, compare_to_reference, finish_rebuild) and require match >=
   0.999 with every face matched, the timeline holding real steps, and an edit of one early value
   (the base distance) rebuilding cleanly. Where a plan step fails, the test shows what an AI would
   read from the answer. Plus one run through the real MCP server (like agent_e2e.py).
6. GUI scenarios `rebuild_*.py` (8+ paths: the right-click command on an imported STEP body, the
   ghost reference, the chat message prepared (with a fake configured AI) and the
   no-AI dialog, Compare with Reference (numbers and overlay), Finish Rebuild (name, place, one
   undo), refusal on a broken mesh, save / reopen with a reference in the design, Esc / Cancel).

Spec: `docs/sciforge/parity/auto-timeline.md` (yours, except the "Recognition" section). Session
log: `docs/sciforge/sessions/beta3-at-tools.md`. Report as beta3-common says.

# Session log: beta 3, Auto Timeline tools and rebuild (builder at-tools, `sf/at-tools`, 2026-10-26)

Luca: "Using a connected AI, I want there to be the tool necessary for the AI to reverse
engineer premade models and make them parametric ... A tool call and instructions on how to
reverse engineer a model would be cool." This builder made everything around the feature
reading (at-recognize's `recognize.describe()`): the reference and the comparison, the AI
tools, the documentation an AI reads, the command a person clicks, and the proof. Spec:
`docs/sciforge/parity/auto-timeline.md` (sections "Reference, compare and finish", "AI tools
and documentation", "The command a person uses", the at-tools tests and known gaps).

## What was built

- `sciforge/rebuild.py` (the contract, no Qt): `start` freezes a body (or a mesh body, made
  into a solid first; a mesh that is not watertight is refused with the reason) as the
  **reference**: an `App::FeaturePython` (SciForgeType `RebuildReference`, `FrozenShape` in
  design coordinates, the original's name / label / kind, the rebuilt body's name), hidden
  from the timeline and the browser; the original is hidden; a new empty body
  `<name> (rebuilt)` in the original's component, active. `compare` (described below),
  `finish` (the rebuild takes the original's name, component and place; the original deleted
  or kept hidden as `<name> (original)`; the reference removed or kept hidden), `describe`
  (recognize.describe of the reference in the rebuilt body's frame; recognize_mesh for a mesh
  reference), `find` / `reference_for`, an undo / redo watcher for the original's visibility.
- `sciforge/rebuild_core.py` (pure Python): what a region looks like (hole, stepped hole,
  boss, rounded edge, chamfer, block, layer, a mesh's faceted hole), equal regions grouped in
  Fusion's order, faces in words, size notes, the verdict (for an AI, and in a person's
  words for the dialogs), the chat message. 21 unit tests.
- Compare, in short: faces matched first, by surface + coverage (mesh references within the
  mesh's tolerance); when every face of each part lies on a face of the other and the
  volumes agree it is the same solid (no boolean); else one General Fuse, each piece put
  inside / outside each solid from the orientation of its faces (a point test only as a
  fallback), the pieces must add up to both volumes (else fuzzy, else the volumes measured
  along 4096 rays through both parts' triangles, said so); regions with
  "fix" calls (a Single Hole on the right face, a fillet / chamfer of exactly the rebuild's
  sharp edges, grouped); deviation; `done`; the verdict ("Match 0.9497 ...; Next: 4 round
  holes about 6 mm across, 10 deep (along Z) are not cut yet, at (10, 10), (50, 10), (10,
  30), (50, 30). 4 rounded edges of radius about 3 are still sharp in the rebuild (the
  fillet call is ready in groups[1].fix)."). What it measures of the reference is kept for
  the next compare (the reference never changes).
- AI tools (category "Rebuild with a timeline", need "reference"): `start_rebuild`,
  `describe_reference`, `compare_to_reference`, `finish_rebuild` (refuses a rebuild that is
  not done unless `even_if_different`); in the headless runner (`rebuild_e2e.RUNNER_SESSION`,
  33 calls), reference examples recorded, `docs/ai` regenerated; early in the chat's tool
  list (`catalog.CHAT_ORDER`) so a local model that takes 48 tools has them.
- Docs for AI models: `docs/ai/recipes/reverse-engineer.md` (32 tested calls), a handbook
  section, a troubleshooting section, the recipe index row; the chat's system prompt index
  lists the recipe by itself.
- The window (`sciforge/rebuild_ui.py`, icons `tools/sciforge/icons_rebuild.py`): the
  reference's view provider (faint see-through ghost and the red / green differences, Coin
  only); **Rebuild with Timeline (AI)...** on a body's / mesh body's right-click in the
  browser, on the 3D view's right-click list when a body is under the mouse
  (`marking_menu.CONTEXT_ITEMS`, a small hook), UTILITIES > AI; the chat with the ready
  message (not sent) or the window for AI apps (message copied); **Compare with Reference**
  and **Finish Rebuild** dialogs (the verdict and refusals in a person's words, the wait
  cursor while a mesh becomes a solid or a big part is compared; with several rebuilds going
  on and none chosen, they say to select the rebuilt body, naming them).
- The proof: `SciForgeTests/headless/rebuild_e2e.py`: six parts (bracket, hole grid, flange,
  knob, block with pocket and boss, plate from an STL) rebuilt only through the tools, then
  the timeline, check_design and an early edit checked, plus compare's fallback (68 checks),
  and the same loop through the real MCP server (14 checks); `run_tests.sh --only headless /
  base` runs both.
- Scenarios: `rebuild_start` (70 checks), `rebuild_compare_finish` (66), `rebuild_mesh_reopen`
  (39), `rebuild_chat` (20: a fake local model rebuilds the plate through SciForge's own chat,
  from the right-click to Finish).

## FreeCAD / OpenCASCADE facts learned (traps)

- `Part.Shape.generalFuse(...)` in FreeCAD 1.1.4 returns an **empty map** (`[[], []]`): the
  pieces cannot be traced back to the arguments through it. Classify them yourself.
- `Shape.isInside(point, tol, checkFace)` builds OpenCASCADE's solid classifier on every call:
  10-20 ms on a 220-face solid. For many pieces, the orientation of a piece's face lying on a
  face of the solid says inside / outside without it.
- Two solids whose faces lie on each other within a hair (a mesh's facets and their exact
  copies) give a General Fuse with dozens of slivers of 1e-6 mm3 that have no inside point:
  skip pieces below 1e-7 of the volume and allow them in the volume check.
- `insert.solid_from_mesh` on a box mesh with one triangle missing gave a **flat** "solid"
  (no error): check `mesh.isSolid()` / `hasNonManifolds()` first and that the solid has the
  mesh's box and volume.
- Visibility changes are not recorded in undo: an object shown / hidden by a step stays so
  after Undo unless something puts it back (here an `App.addDocumentObserver` with
  `slotUndoDocument` / `slotRedoDocument`).
- A reference as `App::FeaturePython` (not `Part::Feature`) with a `Part::PropertyPartShape`
  named `FrozenShape` (not `Shape`) is invisible to every geometry path of SciForge (exports,
  inspect, joints, render); `SciForgeTimeline = False` keeps it out of the timeline; the
  browser drops unknown types by itself.
- Cone faces of a revolve and of the same STEP cone can carry opposite axis directions:
  compare cones / tori by apex (centre), |axis . axis| and angle, and let the cover test
  decide; measure analytically (no `distToShape`).
- FreeCAD measures `Shape.Area`, `Volume`, `BoundBox` and `CenterOfMass` on every access
  (nothing is kept): sorting a 300-face piece's faces by area cost 0.34 s, a box test per
  pair of 96 pieces 0.25 s. Measure once and keep the number.
- `Face.isPartOfDomain`, `Face.isInside` and `distToShape` on a face with 96 holes cost 1 to 2
  ms a call (OpenCASCADE's classifier is built again on each call). A plane or cylinder face
  that is its whole parameter rectangle (area = du dv, or R du dv) needs no classifier: test
  the point on its surface and its parameters against the range.
- The harness fails a scenario on "failed" / "error" / "invalid" in any Report-view line,
  including SciForge's own log lines: log words were chosen for it.

## Numbers measured

compare in this sandbox (4 CPUs, six builders, load about 4.5), after the second round of
speed-ups: the e2e parts' last compare 13 to 130 ms (the same solid: no boolean), the meshed
plate (150 faces) 1.6 s; a 298-face plate with 96 chamfered holes: the same solid 0.3 to
0.6 s, the base plate only (96 regions) 1.5 s (was 3.5 s), 10 holes missing 2.2 s (was
3.2 s), every chamfer and 4 holes missing (188 regions) 3.7 s (was 6.5 s); the General Fuse
alone 0.5 to 2.4 s of that. The six e2e parts: 11 s in all (was 25 s). describe_reference is
at-recognize's (0.06 to 6.5 s).

## Notes for whoever merges

- Shared files touched (only these lines): `ai/catalog/__init__.py` (4 names in
  `CHAT_ORDER`), `ai/executor.py` (`state()["reference"]`), `ai/tool_docs.py`
  (`NEED_WORDS["reference"]`), `browser_core.py` (2 menu entries), `browser_ui.py` (1
  handler), `marking_menu.py` (`CONTEXT_ITEMS`), `ribbon_config.py` (UTILITIES > AI: a
  separator and 3 items), `SciForgeTests/headless/runner.py` (4 lines at the end of main),
  `SciForgeTests/docs/tool_examples.py` (2 setups, 4 examples), `tools/sciforge/run_tests.sh`
  (the rebuild e2e block; merged with at-recognize's `run_recognize`).
  `docs/sciforge/parity-checklist.md` regenerated (`tools/sciforge/parity.py`): regenerate
  again after merging the other branches.
- The category "rebuild" and the need "reference" are entered from `rebuild_tools.py` itself
  (`registry.CATEGORIES` / `NEEDS`), so `registry.py` is untouched.
- `describe_reference`'s recorded example is compared on its first line only (`volatile`):
  its plan is at-recognize's. Re-record the tool examples (`SCIFORGE_DOCS_RECORD=1`) and run
  `tools/sciforge/make_ai_docs.py` after the merge.
- Found in at-recognize's first version (they fixed it since): a rectangular pattern of holes
  was planned in one direction only; compare's hole calls repaired it in the e2e test.
- Merging `sf/at-recognize` conflicts in `docs/sciforge/parity/auto-timeline.md`'s Tests
  section only: keep both (at-recognize's bullet first, then "Tests: ... (at-tools)" and
  "Known gaps (at-tools)").

## Tests run (final code, after merging at-recognize's bc1bf483)

- `run_tests.sh --only base` (before that merge): all passed: unit 2531 (9 skipped), golden
  614 + 2 known xfails, headless runner 317 calls / 121 tools, docs runner 146 items / 1009
  calls, agent e2e (MCP) 81, rebuild e2e 68, rebuild e2e through MCP 14, recognition 37
  parts, smoke 79, journey 25, restart 8 + 9.
- After the merge: the whole unit suite 2537 OK (11 skipped without FreeCAD); rebuild e2e 68,
  through MCP 14; the runner's rebuild session 32 results; docs runner on the recipe (32
  calls), troubleshooting (59), the four tools' examples: all pass; scenarios below.
- Scenarios of the areas touched (run alone or in small groups): ai_bridge 44, ai_chat 20,
  ai_docs_gui 18, ai_panel 27, ai_tools_gui 38, browser_opacity_hover 46,
  marking_menu_command 31, timeline_browser 92: PASS; rebuild_start 70,
  rebuild_compare_finish 66, rebuild_mesh_reopen 39, rebuild_chat 20: PASS.

## Gaps

In the parity doc's "Known gaps (at-tools)": no Fusion **Find Features** (in-place recognition
in direct modeling); compare is 2 to 4 s on a 300-face part with many regions left (the
General Fuse alone is up to 2.4 s there at this load); ready calls only for holes and fillets
/ chamfers; a mesh's "done" is within the mesh's tolerance; when OpenCASCADE cannot split the
two parts, only the volumes are given (about 1 %), not the regions.

Seen, not mine: `ribbon_sweep` with `SWEEP_TABS=utilities` (not a default run) fails on the
pop-ups of Export, Export Everything, Scripts and Add-Ins, Add-on Manager and Add an AI App
(windows those commands open on purpose) and then hangs at FreeCAD Tools, whose menu
(`QMenu.exec_`) the harness's `close_popups` does not close (it closes `QDialog`s only). The
three new UTILITIES > AI items passed it (no pop-up).

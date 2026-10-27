# Session log: beta 3, the REBUILD journey (`sf/journey-rebuild`, 2026-10-27)

A journey tester's pass over Auto Timeline (rules: `docs/sciforge/dev/briefs/beta3-qa.md`,
Journey agents): turn parts that came without a timeline into real parametric parts the way
Luca would, with real clicks and keys only, then use the rebuilt part in the rest of SciForge
(edits, a joint, SIMULATION, save / reopen). Code only writes the test files, plays the AI and
reads results. Branch made from `beta3`; `sf/autotimeline-qa` merged at the start (no newer
commits after), `beta3` merged again at 02:02 (VEX QA, the rebuild helper fix).

## The journey

Steps and the numbers worked out by hand: `SciForgeTests/gui/journey_rebuild_steps.py`.

1. **The stranger's part.** `bracket.step`, written by code as another CAD program would: a
   plate 100 x 60 x 10 with four counterbored holes (d 6 through, counterbore d 10 x 4) on a
   2 x 2 grid, a pocket 30 x 30 x 5, the top edge of the mounting end chamfered 2, the two far
   corners rounded 8: 53170.089 mm3 by hand. Also `clamp.step` (a 24 x 24 x 6 block with a d 6
   hole) and `plate.stl` (80 x 48 x 8 with two d 10 holes, triangles written from the exact
   plate). INSERT > Insert STEP brings the bracket in as one body with one "Insert STEP" step.
2. **Rebuild with Timeline (AI)...** from the body's right-click: the chat opens with the ready
   message, not sent; Send. The AI is a fake local model (a small HTTP server in the test that
   answers like Ollama) that reads only SciForge's answers: describe_reference's plan, every
   plan step with the ids the answers give, compare_to_reference after every feature, the
   calls the verdict offers while it is not done (in `journey_rebuild` it forgets the plan's
   chamfer on purpose: the verdict brings it back), then it asks the person before finishing;
   "Yes, finish the rebuild." in the chat makes it call finish_rebuild.
3. **Edits like a person**: the base extrude double-clicked in the timeline, 10 -> 12; the
   hole double-clicked, d 6 -> 6.5 (the pattern follows).
4. **The joint** made before the rebuild (J, the clamp's bottom by its hole, the counterbore's
   rim until its centre lights up) is on the rebuilt bracket after Finish, back on the
   original after Ctrl+Z, and the clamp rides up 2 mm with the thicker top.
5. **SIMULATION** on the rebuilt part: New Study, Fixed on the four counterbores' floors (seen
   from the top: from the side the walls hide them), Force 1000 N straight down (Vector) on the
   far end face, Solve; DESIGN: 2 mm thicker; the study is out of date; Solve again.
6. **The mesh path by hand**: Insert Mesh, the right-click with no AI set up (the window for
   AI apps), Create Sketch on XY, a rectangle typed 80 x 48, E 8, Compare (two holes about
   10 mm across at (20, 24) and (60, 24)), an early Finish (Cancel), two circles typed d 10
   on the top face, E with the two circles picked, -8, Extent All, Compare done, Finish.
7. **Save, close, open again** half way and after Finish, for the mesh by hand and for the
   AI's bracket (finished by hand after opening again).

| Scenario | Journey steps | Checks | Result |
|---|---|---|---|
| `journey_rebuild` | 1, 2, 3, 4 | 86 | PASS |
| `journey_rebuild_sim` | 1, 2, 5 | 76 | PASS |
| `journey_rebuild_mesh` | 6, 7 | 65 | PASS |
| `journey_rebuild_reopen` | 1, 2, 4, 7, 3 | 88 | PASS |

Numbers by hand that the scenarios check: the bracket 53170.089 mm3 (60000 - 616 pi - 4500 -
120 - 2 (64 - 16 pi) 10); 2 mm thicker with everything on top following 64888.955 (and one
shell); holes d 6.5 64731.875; the clamp at x 20..44, y 33..57, z 10..16 (z 12..18 on the
thicker bracket); the plate 30720 then 29463.363, 10 thick 36829.204; the bending stress at the
pocket section (x = 55: I = 3437.5 mm4, c = 5.833) 76.4 MPa for 1000 N, 51.9 MPa at 12 mm
(0.68). The solver gave 119.8 MPa at the clamped counterbores (safety factor 1.73, shown in
the RESULTS legend), then 86.7 MPa (0.72) and 2.39.

## Bugs found and fixed

| Bug | Fix | Test (fails on the old code) | Commit |
|---|---|---|---|
| A rebuilt part made 2 mm thicker kept its pocket and counterbores at the old height, sealed under a 2 mm skin (two shells, 65115 mm3 instead of 64889; check_design OK): the plan sketched what starts on the top face on an origin plane at a fixed offset | the plan's sketches at the base's top go on that face, in the plane's axes (`create_sketch` takes `face` with `plane` and `offset`: `ai/ops/core.py` `_sketch_on_face_as_plane`; `recognize._on_top_face`; catalogue and golden schema accept the pair) | `test_ai_catalog.test_sketch_on_a_face_in_a_planes_axes`; `rebuild_e2e` "nothing is sealed inside the part (one shell)" (pocket_boss failed); `journey_rebuild` | 447231f0, aa858365 |
| Compare said a meshed plate's holes were at (60.003, 24) and gave the Single Hole there (a 63-facet polygon's box is off its axis) | the faceted region is placed by its centroid across the axis | `test_rebuild_core.test_a_mesh_hole_with_an_odd_number_of_facets_is_at_its_axis` (old: 60.0128) | 35b9beb9 |
| The recipe's example said its holes still go through at 12 mm; they did not (27576.3 mm3 instead of 27350.1) | the recipe sketches them on the top face, a good habit says why, the last call expects 27350.1 mm3 | the docs runner on the recipe | e034cd3a |
| Finish Rebuild in the window deleted the original by default even when the rebuild did not match yet (the meshed plate at 92 %, holes not cut) | a rebuild that does not match keeps the original, hidden, by default | `journey_rebuild_mesh` "keeps the original by default" | 2075b5f6 |
| A hole in a boss's top or in a pocket's floor stayed behind when the boss got taller or the pocket deeper (sealed inside: three shells) | the plan sketches on the end face of any earlier extrude (a join's top, a cut's floor) | `rebuild_e2e` follow_checks (the first version: three shells) | 015b698f |
| An AI that forgot the plan's chamfer got "the differences could not be listed ... sampled" and no call (the strip's end triangle was read on its long side, which also lies on the original's end face: the strip counted as common) | a piece's face is read at a point off its edges | `rebuild_e2e` strip_checks (old: sampled); `journey_rebuild` (the AI forgets the chamfer, the verdict's call brings it back) | 640fcd62, c935d616 (only flat faces checked: as fast as before) |
| (unit test) `test_ai_tools_core.test_sketch_rules` expected plane with face to be refused | it is accepted now (on the face, in the plane's axes); plane with on is still refused | the test itself | 55140b89 |

## Test runs (OMP_NUM_THREADS=1, FreeCAD 1.1.4, on the branch after the beta3 merge)

- `run_tests.sh --only base`: all passed: unit 2724, golden 614 + 2 xfail, headless AI tools
  339 calls (131 tools), documentation examples 157 items / 1087 calls, MCP agent 81, Auto
  Timeline end to end 6 parts / 153 checks (with the one-shell, follow and strip checks) and
  through MCP 15, recognition 71 parts, simulation 138 and the QA's 205, smoke 79, journey 25,
  restarts.
- Compare speed with the strip fix (a 198-face plate with 96 chamfered holes, load about 3):
  the same solid 0.10 to 0.27 s, the base only 0.67 to 0.87 s (before: 0.72 to 0.81), 10 holes
  left 1.63 s (1.65 to 1.82), the chamfers left 1.44 to 1.47 s (1.46 to 1.58).
- GUI scenarios: see "Final scenario run" at the end.

## Gaps (not fixed)

- A face is followed only when it is the end face of an extrude of the plan on the same plane
  and the part has exactly one flat face there (a face of a revolve, or two faces at one
  height, still get a sketch at a fixed offset).
- SciForge's own chat stops after 25 requests per Send (`chat_core.MAX_STEPS`); a model that
  makes one call per request reaches it on a part of more than about 14 plan steps (the
  bracket took 17): the person says "continue".
- Finish from the window on a rebuild that does not match is allowed (said in the window);
  the AI's finish_rebuild refuses it unless even_if_different.

## FreeCAD and SciForge facts learned (traps for the next tester)

- `body.Shape` of a body inside a component leaves the component's placement out: a box check
  of a jointed part must apply `getGlobalPlacement() * Placement^-1` (the clamp "did not move"
  until that was done).
- Joint snaps: the hot dot is the nearest on the screen; hovering 1.5 mm off a counterbore's
  rim takes the rim's seam vertex or midpoint. A person moves the mouse until the centre lights
  up: the scenario does the same (around the rim, reading the hover's hot snap).
- A counterbore floor (a ring 2 mm wide, 4 mm down) is hidden by its wall from the isometric
  view; a click 1 mm from the circle's seam corner picks the corner (Fixed then held a vertex:
  a stress singularity that made the "thicker" stress go up).
- Create Sketch on a face projects the face's outline (Fusion's auto project): E from such a
  sketch picks no profile, the regions are clicked; a click on the plate's area outside the
  sketch's regions picks the body's face as the profile (an extrude of the whole top).
- Insert STEP names the body "Body1" whatever the STEP product is called (the component
  carries the file's name), as Fusion does.
- `rebuild_steps.insert_step` on beta3 inserts its own copy of the file (VEX: the same file
  again is an occurrence of the first).

## How it went (for Luca)

The good news first: the whole story works. A part from a stranger came in with no history;
one right-click and one press of Send, and the AI rebuilt it step by step in the right order
(sketch, extrude, pocket, holes, pattern, chamfer, fillet), checked itself after every step,
and asked before finishing. Compare showed 100 %, Finish kept the part's name and place and
moved the joint onto it, and one Ctrl+Z put everything back.

The problem the journey found was the important one: the rebuilt part was not really
parametric where it matters most. Making the plate 2 mm thicker left the pocket and the
counterbores at the old height, sealed inside the part, and nothing said so. A part a
person draws in Fusion would have its pocket on the top face, and so would follow. That is
fixed: the rebuild now sketches those features on the top face, so a thicker plate keeps them
on top, and the same for a hole on a boss or in a pocket's floor; the AI's instructions were
wrong in the same way and are fixed too. When the AI (on purpose, in the test) forgot a
chamfer, Compare could not say what was missing ("the volumes were sampled"): a small
mistake in how Compare looks at the pieces, fixed, so it now says "a chamfered edge, about 2"
with the call ready, and the AI put it back by itself. Smaller fixes: the holes of a meshed
part are placed at round numbers, and Finish no longer deletes the original by default when
the rebuild does not match yet.

Simulation on the rebuilt part works the way you would expect: holding the counterbores and
pushing the far end gave a safety factor of 1.7; after making the plate thicker the study
said it was out of date and the new solve gave 2.4.

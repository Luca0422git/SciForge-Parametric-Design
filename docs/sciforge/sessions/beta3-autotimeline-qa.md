# Session log: beta 3, Auto Timeline QA (`sf/autotimeline-qa`, 2026-10-26/27)

The independent QA pass over Auto Timeline (builders at-tools and at-recognize). Rules:
`docs/sciforge/dev/briefs/beta3-qa.md`. Branch made from `sf/at-tools` (with at-recognize's work
up to bc1bf483); `sf/at-recognize` merged again as it went on (see "Merges").

## What was tried, and what came out

| Question | Result |
|---|---|
| A jointed body (a VEX part) rebuilt and finished | **Bug, fixed**: Finish deleted the original, and `joints.remove_joints_of` took every joint on it with it (the AI's answer did not even say so). Now whatever used the original moves onto the rebuild first (`sciforge/rebuild_links.py`): the joint stays, the arm does not move, the joint still drives it |
| A body with a pattern of bodies, another body's sketch on its face, a ground, a component instance | **Bug, fixed** (same fix): the ground was deleted, the pattern lost its source, the other body's sketch lost its face (that body changed shape). A pasted instance's copy follows too |
| A body whose extrude also cuts another body | **Bug, fixed**: deleting the original took the cut out of the other body (its follower step); now the original is kept, hidden, for it |
| A body that already has a timeline | works (the plan rebuilds it; what used it follows) |
| Two rebuilds at once | works (each tool takes `reference`; the active body picks one; the dialogs ask to select the rebuilt body) |
| Undo / redo across start, the AI's steps and finish | works (with the joints moved too: undo of Finish puts them back on the original) |
| Save / reopen in the middle | **Bug, fixed**: after opening again no body was active and SciForge picked the design's first body: the AI's next sketch went into the empty "Body1" and the hole after it failed ("No base set, sketch support is not Part::Feature") |
| The reference deleted by hand (the AI's delete_step, a script) | **Bug, fixed**: the original stayed hidden for good |
| A jointed part driven while it is rebuilt | **Bug, fixed**: the reference stayed where it was frozen: compare said match 0.16, the plan came out turned, the ghost stood apart |
| Finish of an imported STEP body | **Bug, fixed**: its imported shape stayed in the component as a stray "Body001 (imported)" timeline step |
| start_rebuild with the id import_file answers | **Bug, fixed**: that id is the component's; it was refused ("pick the body") |
| A mesh with holes (not watertight) | refused with the reason and "MESH tab > Repair" (start_rebuild and the window); a meshed plate with through holes rebuilds (the e2e test) |
| Threads | **Bug, fixed**: a plate with a modeled M6 thread took 210 s in describe_reference (OpenCASCADE's defeaturing on the thread's faces), then read no base at all and planned a hole that failed. Now 1.3 s: the plate and the hole are read, the thread is listed as not read with what to do |
| Text (raised or engraved letters), a loft | **Bug, fixed** for text on a flat face: its free-form letters made the whole part unreadable (base none, every face unrecognized, a plan of a sketch and a hole that failed on the empty body); now the letters are closed over like holes, the plate and its hole are read and planned, and each group of letters is said (raised or engraved, size and place, sketch_text + extrude). A loft: said, not guessed ("build it yourself") |
| A 0.5 mm part and a 2 m part | both rebuilt to done (match 0.999996 and 1) |
| An inch STEP file | read at its size (127 x 12.7 x 1.5875 mm), rebuilt to done; the plan's numbers are millimetres (12.7 for half an inch) |
| The chat message a beginner sees | right for the AI it is meant for (names the body, the rebuilt body, the recipe, the four tools); nothing said it waits for Send: a tip now says so |
| An AI following only the docs and the answers | the e2e agent (plain Python, reads only answers) gets to done on 6 parts, the recognition bench on 53; a threaded part cannot get to done (the thread is said; finish with even_if_different) |
| Speed on a 294-face part (144 chamfered holes) | start 0.4 s, describe 1.7 s, compare 1.6 to 2.2 s while holes are left and 0.4 s when done, finish 2 s (load about 5 on 4 CPUs) |
| Speed on a VEX plate (125 square holes, 506 faces) | **Bug, fixed**: describe 56 s; now about 9 s (compare 2 to 3 s, finish 5 s) |
| Speed on a VEX C-channel (410 faces) | **Bug, fixed** in part: describe 37 s, read along its length too (51 levels); now 25 s (the rest is at-recognize's sections and booleans) |
| A plate with a boss and 60 holes in the face the boss stands on | **Bug, fixed**: no hole was closed by its rim (`Face.cutHoles` answers None), all went to defeaturing: 12.7 s, now 0.3 s |
| Speed of Finish in a big design (150 components, 3009 objects, 40 joints) | start 0.55 s, describe 0.25 s, compare 0.13 s, finish 1.3 s (both joints of the part followed) |
| check_design half way through a rebuild | **Bug, fixed**: the hidden original under its rebuild was an overlap (NOT OK) |
| Holes with a chamfered rim, the base built only | **Bug, fixed**: compare called them holes "with a pointed (drilled) end" |
| Giving a rebuild up | **Bug, fixed**: there was no way but Undo (none in a design opened again: the original stayed hidden, the ghost drawn); now Stop Rebuild... (UTILITIES > AI, the rebuilt body's right-click) |
| A drawing of the original (3 views, 26 dimensions) | the views follow the rebuild; no dimension changed its value |
| A body two components deep, both turned, the body moved in its component | rebuilt to done and finished in place (the same world volume) |
| A modelled thread after at-recognize's latest merge (28b49f4d) | **Regression, fixed**: its new round-floor rule took the thread's flanks for a floor: no hole, base none |

## Fixes (each with a check that fails on the code before it)

Commits on `sf/autotimeline-qa` (oldest first):

1. Finish moves what used the original onto the rebuild (joints, grounds, rigid groups,
   contact sets, patterns of bodies, sketches / planes on its faces, drawings: every link of
   every other object, element names swapped for the rebuild's on the same geometry;
   joints' snap records too); what cannot follow keeps the original (hidden, said); the
   rebuild's steps take the original's place in the timeline; the original's material and
   appearance go to the rebuild. `sciforge/rebuild_links.py`, unit tests
   `test_rebuild_core.FollowTest`; checks `rebuild_qa.jointed / dependents / kept`, scenario
   `rebuild_qa_joints` B.
2. The original's imported shape no longer stays behind. Check `jointed` (no stray shape).
3. A design opened again carries on in the rebuilt body (`rebuild.working_body`; headless
   host and window). Checks `reopened`, scenario C.
4. A reference deleted outside Finish shows the original again. Check `deleted_reference`.
5. A threaded hole: closed with its thread, never defeatured, said in unrecognized (210 s ->
   1.3 s). Check `threaded`.
6. The reference moves with the rebuild's component (`FrozenFrame`, `moved_by`); the ghost
   follows. Check `driven`, scenario A.
7. A VEX plate: the base check compares faces before any boolean; planes bucketed by offset
   (56 s -> 9 s; at-recognize's own axis skipping, merged later, replaced mine). Check
   `vex_plate`.
8. A follower step of the original's extrude keeps the original. Check `follower`.
9. start_rebuild takes a component with one body. Check `component_id`.
10. The window: the chat's ready message is said; the ghost placed on reopening.
11. Docs: finish_rebuild's description, the recipe, troubleshooting, the parity doc.
12. check_design and interference leave an original under its rebuild alone. Check `midway`.
13. A link through the original's sketch or datum does not follow to a wrong element (unit
    test `FollowTest`); a reference deleted in a design opened again shows its original too
    (`deleted_reference`); the move watcher looks only in designs with a rebuild.
14. compare tells a drill point from a chamfered or countersunk rim. Check `chamfered_rim`,
    unit test.
15. A VEX C-channel is not read along its length too (37 s -> 25 s). Check `vex_channel`.
16. Holes in a face that keeps another loop (a boss) are closed by their rims again
    (`Face.cutHoles` works in place; 12.7 s -> 0.3 s). Check `bossed_plate`.
17. Raised or engraved text on a flat face: closed over like a hole ("islands"), the rest of
    the part read and planned, the text said. Check `text_plate` (raised and engraved).
18. Stop Rebuild... (window) / `delete_step` on the reference (AI). Checks `stopped`, scenario
    `rebuild_qa_joints` D.
19. After merging at-recognize 28b49f4d: a modelled thread is read again (its round-floor rule
    limited to analytic faces). Check `threaded` (failed on the merge).
20. Stop Rebuild keeps the rebuilt body by default when the original was deleted meanwhile.

`SciForgeTests/headless/rebuild_qa.py` is run by `rebuild_e2e.main()` (so by
`run_tests.sh --only headless / base`); `SCIFORGE_REBUILD_FILTER=qa` runs only it. On the code
before the fixes 12 of its first 24 checks failed (and the later ones: the plan turned,
component id, follower).

## Merges of sf/at-recognize

0460e98b (2543d664), 7c5a95f8 (cd7dc610), e286585b (4622f67f: its free-form rule then took a
hole's thread for free-form faces: fixed in 5bdbdd82), 8ca93fd0 (135be235: its axis skipping
conflicted with mine in `_best_prismatic`: theirs kept), a5682d67 (db65af29), 71810a78
(28b49f4d: its round-floor rule broke threads: fixed in dd8022eb; parity doc conflicts
resolved by hand, the AI docs copy regenerated). After each: recognition bench and rebuild
e2e passed (see the report for the numbers).

## FreeCAD facts learned

- A removed document object has no name any more: read `obj.Name` before `doc.removeObject`
  if you need it after (a `finally` that used it left a stale entry).
- `Shape.transformGeometry` with a scale turns planes and cylinders into B-splines; use
  `Shape.scale` to keep them analytic (an "inch STEP" made the first way read as free-form).
- FreeCAD's document observer takes the slot methods when the observer is added: patching
  the class afterwards does nothing.
- Insert STEP (`step_import`, the window's path) names the body of a STEP file without
  product names "Body1", the same label as the design's first body: a browser lookup by label
  finds the wrong one.
- `Timeline.at_end` (timeline_core) is a property, not a method.
- OpenCASCADE's defeaturing has no time limit: one call on a thread's 34 B-spline faces took
  210 s. Keep free-form faces away from it.
- Two booleans between solids whose 500 faces coincide take seconds each: compare the faces
  first.
- `Part.Face.cutHoles(wires)` changes the face in place and answers None (`f = f.cutHoles(w)`
  leaves None).
- In headless FreeCAD there is no active body after `components.activate_body` (it is the
  window's); tests of the active body belong in GUI scenarios.

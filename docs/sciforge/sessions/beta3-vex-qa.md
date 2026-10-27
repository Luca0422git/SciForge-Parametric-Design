# Session log: beta 3, QA of the VEX work (branch `sf/vex-qa`, 2026-10-26/27)

Independent QA of builder vex's work (`sf/vex`, brief `docs/sciforge/dev/briefs/beta3-vex.md`,
rules `docs/sciforge/dev/briefs/beta3-qa.md`; spec `docs/sciforge/parity/vex-assembly.md`, the
team page `docs/sciforge/vex.md`). The branch already holds develop's patch 0.1.0-beta.2.2.
The container restarted at about 23:26 UTC (the first browser batch was cut off and run again).

## What was tried

- **Parts with real VEX files' traits** (`SciForgeTests/fixtures/vex/vex_real.py`, SciForge's
  own shapes, never VEX's files): every file written in INCH units; square holes with tiny
  rounded corners (r 0.005 in: arcs of 0.13 mm in each outline); holes cut in two halves
  (split outline sides, more wall faces); a motor that comes in as an assembly of three
  solids with a blind 0.13 in square socket in a round boss; the 1x5x1x35 steel channel
  (about 2000 faces, 6000 edges). Headless (the hole index on every face, edge and wall) and
  with real clicks (`vex_qa_real`): the centre dots appear on every one, at the true centre.
- **The team's workflow with real clicks**: a screw into a tiny-rounded square hole; Duplicate
  With Joints into a split hole; a square shaft into the motor's socket on a revolute, driven,
  undone, saved and reopened (`vex_qa_real`); a 1/8 in square shaft through square holes of
  TWO channels (one jointed face to face onto the other, 1 in apart) on a revolute, driven 45
  degrees, saved, reopened, driven again (`vex_qa_shaft2`); Align of a channel onto a channel,
  hole onto hole, both ways round (from the dots next to the holes, and from a hole's edge),
  with Undo / Redo (`vex_qa_align`); a design in inches (`vex_qa_inch`).
- **Occurrences and inserting** (`vex_qa_occ` and headless checks): ten files, then twenty in
  one Insert STEP (ten of them again: occurrences), Undo / Redo of the twenty (all back with
  their solids, where they were, still linked); a file changed on disk; the first occurrence
  deleted (the others stay, frozen) with Undo / Redo and save / reopen; the parts list's Qty;
  Duplicate With Joints with limits, with a Rigid Group, from a sub-assembly.
- **The browser after the speed changes**: read `browser_ui.py`'s diff against every use of a
  row's node (eyes, Show / Hide from menus, rename, drag-organize, activate, Isolate, Opacity
  Control, the hover ghost, selection sync, folders, undo / redo); nothing else needs a row's
  children. Every browser, timeline_browser and components scenario run (all pass).
- **The patch's joint fixes**: a joint on a hole, the channel edited (faces renumbered), the
  joint deleted the way the browser deletes it: both bodies keep their solids, nothing in error
  (headless `delete_hole_joint`); `joints_delete` and `joints_limits_drag` run.

## Bugs found and fixed (each its own commit, each with a test that fails on the old code)

1. **Duplicate With Joints left a nut behind** (2c46982f). A screw and its nut held by a Rigid
   Group (Fusion's advice for parts that never move apart) were copied, but nothing held the
   nut's copy to the screw's copy: when the copy's joint moved, the nut's copy stayed where it
   was. A Rigid Group holding two or more of the picked components is now made again for
   their copies. Test: headless `duplicate_rigid_group`.
2. **The parts list split a part once its first occurrence was deleted** (514f873a): the
   screw inserted three times, the first deleted: "screw:2" and "screw:3" were listed as two
   parts (Qty 1 each). They count as the part again (Qty 2), also after a reopen. Test:
   headless `parts_list_original_deleted`.
3. **"screw:001"** (4da9f658): with the first screw deleted, the same file inserted again and
   then once more: the occurrence was numbered 2 again (clashing with the surviving
   "screw:2"), and FreeCAD renamed it "screw:001", which reads as the first occurrence. The
   numbers taken now include every component still named "<part>:<n>" ("screw:4"). Test:
   headless `occurrence_names_after_delete`.
4. **The same STEP file with a new date was a new part** (ac2266ca): a file is recognised by
   its path, size and a digest of its bytes instead of its date, so a teammate's copy of the
   parts folder, a git checkout or a fresh download over the old file still gives an
   occurrence; a file whose content changed is still a part of its own. Test: headless
   `same_file_again`.
5. **Duplicate With Joints put copies at the root** (537c063d): a screw's occurrence kept in a
   sub-assembly was copied beside its original (the root) instead of beside itself. Test:
   headless `duplicate_in_place`.
6. **Inch designs read plain numbers as millimetres** (1797eb04): the team page puts the design
   in inches, but Offset Z typed as `-1.5` moved the shaft 1.5 mm (and the box then showed
   `-0.06 in`). SciForge's value boxes read a plain number themselves (FreeCAD's box reads it
   in whatever unit it shows) and always as mm; a plain number for a length is now in the
   design's units, as in Fusion (mm, cm, m, in, ft), also in the fillet / chamfer boxes; mm
   designs read as before. Tests: scenario `vex_qa_inch` (failed on the old code), unit test
   `test_plain_number_in_design_units`.
7. **A hole centred on its face had no reach** (f160f674): a square bore at the centre of a
   face (a VEX gear's, wheel's or sprocket's bore, a motor's socket) has the same point as the
   face's centre of area, which comes first and is kept; the hole's own dot, with its reach,
   was dropped. Next to the bore its corners or side middles took the click, inside it the
   socket's floor took over: the shaft went onto a corner of the motor's socket. The face's
   centre now takes the reach of a hole centred on it (joints and Align). Tests: scenario
   `vex_qa_real` step D (failed on the old code), unit test `test_centred_hole_keeps_its_reach`.

8. **The parts list of an assembly file inserted twice** (d6d07022): a motor that comes in as
   an assembly (Case, Cartridge, Cap) inserted twice listed Case 1, Cartridge 1, Cap 1 and
   "real_motor" 1 (the occurrence holds its copies flat and counted itself as one part). A copy
   now counts as the nested component of the original it repeats: Case 2, Cartridge 2, Cap 2.
   Test: headless `parts_list_assembly_twice`.

My own slip: a first test script set FreeCAD's STEP export unit to inch in the shared FreeCAD
profile (`/root/.config/FreeCAD`) for about two minutes (23:07 - 23:09 UTC) before I reset it;
every later script ran with a profile of its own. A STEP file another agent exported with a
plain `freecadcmd` in those two minutes would have been written in inches.

## Speed (re-measured; the machine shared with the other agents, load about 2 to 5)

The 298-part robot (`vex_robot`, 5960 objects), two QA runs (best, the spread of every try
in brackets) against the builder's best:

| What | Target | Builder's best | QA (2 runs) |
|---|---|---|---|
| Open the robot | < 30 s | 36 s | 27.9 s (27.9 - 29.5) |
| Browser rows rebuilt (forced) | < 0.3 s | 0.42 s | 0.37 s (0.37 - 0.62) |
| Browser: the design read again | | 0.30 s | 0.21 s (0.21 - 0.25) |
| Timeline refresh | | 0.12 s | 0.08 s (0.08 - 0.15) |
| Hover a rail's web: first time / next times | < 0.1 s | 0.05 - 0.15 / 0.014 s | 0.04 / 0.010 s (0.010 - 0.34) |
| Drive the joint by script: one step | live | 0.05 s | 0.04 s (0.04 - 0.59; medians 0.26 - 0.28) |
| Drive Joints dialog: one slider step | | 0.70 s (median 0.96) | 0.45 s (0.45 - 1.01; medians 0.55 - 0.74) |
| Orbit: one frame | | 0.35 s | 0.25 s (0.25 - 0.78) |
| Insert twenty STEP files | < 20 s | 21.8 s | 15.0 s (15.0 - 17.7) |
| Save | < 10 s | 3.8 s | 3.0 s (3.0 - 3.7) |
| Recompute after the screw's part changed (130 occurrences) | | 14.1 s | 7.9 s (7.9 - 9.7) |
| Build the robot by script | | 83 s | 62 s (62 - 65) |

Lower numbers than the builder's mostly because the machine was less loaded; no step got
slower. Only the forced browser rebuild still misses its target.

Elsewhere (`perf_big_model`, a big ordinary design: a plate of 1716 faces, 121 timeline
steps), two runs of this branch against two runs of develop before the VEX work (fac2005e),
best of each: browser rebuilt 26.7 vs 30.4 ms, browser read 26.4 vs 24.6 ms, timeline rebuilt
31.4 vs 30.1 ms, timeline read 23.8 vs 23.4 ms, open the design 4.9 vs 4.6 s, save 1.25 vs
1.26 s, edit + recompute 13.3 vs 12.7 s and 11.7 vs 10.4 s. The recompute differences sit
entirely in FreeCAD's own recompute (OpenCASCADE) under a varying load; SciForge's own share
of each step is the same in both (profiles compared). Nothing got slower in SciForge's code.

## Scenarios and suites (all with real FreeCAD 1.1.4)

New: `vex_qa_real` 74 checks, `vex_qa_shaft2` 68, `vex_qa_align` 99, `vex_qa_occ` 38,
`vex_qa_inch` 21 (all pass; `vex_qa_inch` and `vex_qa_real` failed on the old code). Headless
`SciForgeTests/headless/vex_qa_check.py` (10 checks, run by the unit test
`test_vex_qa_freecad`): all pass.

Run after the last code change of each area, all pass: VEX `vex_align` 145, `vex_duplicate` 52,
`vex_joint_hole` 51, `vex_shaft` 39, `vex_insert_many` 37, `vex_robot` 13; browser and
components `browser_ghost` 33, `browser_opacity_hover` 46, `components2_bodies` 302,
`components2_copy` 278, `components2_marker` 209, `components2_move` 345,
`components2_pattern` 278, `components_basic` 252, `components_extrude` 171,
`components_move` 219, `timeline_browser` 92, `timeline_browser_2` 134, `timeline_browser_qa`
222, `timeline_browser_qa2` 245, `timeline_browser_qa3` 240, `timeline_browser_qa4` 280;
shared files `data_panel_fusion` 60, `drawing_assembly` 62, `exchange2_step_insert` 76,
`insert_step` 31, `fillet` 67, `joints2_modes` 71, `joints_asbuilt_group` 135, `joints_basic`
86, `joints_delete` 143, `joints_limits_drag` 48, `joints_types` 230, `modify_align` 232,
`modify_align_points` 224; speed `perf_big_model` 33 (four runs). Unit tests (plain Python):
2499 OK.

`components2_marker` failed once (the first run, cut short by the container restart, under
load: "Lid 6000 0.0", the builder's report) and passed in the full run: flaky, not from the
VEX work (the builder saw it fail on the beta 3 scaffold too).

## Gaps (not fixed; in `parity/vex-assembly.md`, Known gaps)

- Deleting the first occurrence leaves the others frozen (components.md's gap): they keep
  their solids, joints and place, the parts list counts them, but they no longer follow an edit
  and cannot be copied or duplicated; the same file inserted again is a part of its own.
  Promoting the next occurrence to the original would close it (not done: it touches
  components.remove, undo and the timeline; too risky for the time left).
- A hole whose outline is split between two faces gets no centre; flat faces that a STEP file
  stores as B-spline surfaces give no hole centres (VEX's files have neither, as far as known).
- Duplicate With Joints of an assembly picked as a whole whose joint is on a nested
  component is refused (occurrences of assemblies are flat).
- Sketching in an inch design: the sketch's own value boxes still show and read mm.
- The browser's timer read is paced on big designs (`POLL_PAUSE`): after Ctrl+Z on the robot
  the rows follow 1 - 4 s later (a deliberate trade-off of the builder for driving joints).

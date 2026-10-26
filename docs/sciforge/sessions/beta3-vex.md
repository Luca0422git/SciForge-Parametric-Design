# Session log: beta 3, builder vex (branch `sf/vex`, 2026-10-26/27)

VEX robotics assemblies (brief `docs/sciforge/dev/briefs/beta3-vex.md`, research
`docs/sciforge/dev/research/fusion-vex-assembly.md`, spec `docs/sciforge/parity/vex-assembly.md`).

## What was built

- **N9 test parts** (`SciForgeTests/fixtures/vex/vex_parts.py`): SciForge's own VEX-like parts
  from VEX's published numbers (0.182 in square holes on a 0.5 in grid; aluminium 0.064 in,
  steel 0.046 in): C-channels 1x2x1x25, 1x2x1x25 with rounded hole corners, steel 1x5x1x35
  (rounded corners), 1x2x1x5 (short, for close-up tests), angle 2x2x25, plate 5x25, standoff
  1 in, #8-32 x 0.5 in screw, Keps nut, 3 in square shaft, bearing flat; written as STEP at test
  time into the test output folder (cached by a version stamp; the files are 0.6-2.9 MB, too big
  to commit). `vex_robot.py`: a drivetrain of 298 parts (9 part files, 289 occurrences, a
  revolute shaft joint). CMake: the fixtures glob lists files only (`LIST_DIRECTORIES false`),
  the generator's `.py` files install with the tests.
- **N1 + N2 hole-centre snaps from a per-shape index** (`hole_snaps_core.py`, `hole_snaps.py`;
  `joints._shape_snaps` / `snap_candidates` / `local_placement` / `snap_record`;
  `align.snap_points`; `joints_ui.SnapHover`; `align_ui`).
- **N3** Ctrl lock in the joint dialogs; Shift turns Align's dots off.
- **N4** Insert STEP of several files; Data Panel multi Upload, STEP cards dragged in, Insert of
  every selected STEP card.
- **N5** the same STEP file again = an occurrence ("screw:2").
- **N6** Duplicate With Joints (`duplicate_joints.py`, `duplicate_joints_ui.py`, ASSEMBLE menu,
  icon `duplicate_joints` in `tools/sciforge/icons_vex.py`).
- **N7** speed of big assemblies (measured; see the numbers below).
- **N10** `docs/sciforge/vex.md` (a page for the team).
- Merged `develop` (patch 0.1.0-beta.2.2, fac2005e) into `sf/vex` on the orchestrator's request;
  one conflict (`joints_ui._JointsPanel._selection_changed`: both the limit drag's guard and the
  held snap kept).

## FreeCAD / SciForge facts found

- `TopoShape.findSubShape(list)` names many sub-shapes in one call from FreeCAD's cached indexed
  map (0.05 s for 1400 edges); the old per-corner scan of `shape.Edges` took 0.15 s per edge on a
  steel 1x5x1x35 channel (its web face: minutes).
- `Part.Shape(shape)` is a shallow copy (same TShape), and setting its Placement leaves the
  original alone: an index keyed by `isPartner` survives a part being moved.
- Sharing one solid between occurrences (no deep copy) made recomputes **slower** in a 100-screw
  test (FreeCAD re-meshes a shared shape for each holder): not kept.
- A throw-away document made and closed inside an undo step (FreeCAD's STEP reader) cuts the step
  short when the insert does not come from a FreeCAD command (the Data Panel's menu): Ctrl+Z then
  left the parts in. Files are now read before the step opens.
- `decal_ui`'s document observer scanned every object of the design on each Placement / Group /
  Visibility change: opening the 298-part robot made 3562 such calls (21 million attribute
  reads, 117 of 180 s). `decal.decals` now asks FreeCAD for App::FeaturePython objects only and
  the observer does nothing while a file loads.
- Hovering a square hole straight on: the pointer over the hole hits nothing (or a face behind);
  the hover keeps the hole's centre while the pointer is within the hole's zone, and a click on
  nothing is taken by the hover itself (a mouse-button callback).
- QTest mouse moves carry no keyboard modifiers: a test that holds Ctrl must send its moves with
  the modifier, or the lock is released by the next move.
- A mouse already on a pixel sends no move event: tests that look at the same spot of several
  holes (the camera centred on each) must come from a neighbouring pixel.

## Speed numbers

(see the report and `parity/vex-assembly.md` section 4)

## Gaps

(see `parity/vex-assembly.md`, Known gaps)

# Session log: beta 3, builder vex (branch `sf/vex`, 2026-10-26/27)

VEX robotics assemblies (brief `docs/sciforge/dev/briefs/beta3-vex.md`, research
`docs/sciforge/dev/research/fusion-vex-assembly.md`, spec `docs/sciforge/parity/vex-assembly.md`,
a page for the team `docs/sciforge/vex.md`).

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
  `align.snap_points`; `joints_ui.SnapHover`; `align_ui`): the centre of every closed inner
  outline of a flat face, lit around / on / inside the hole; three dots on a hole's flat wall;
  a joint keeps the hole (centre, size, direction) and finds it again after an edit.
- **The hover shows what a click takes** (`joints_ui.object_info`,
  `hole_snaps_core.choose_hit`): FreeCAD's selection prefers an edge or a corner right at the
  face hit first; the hover asked for the first hit only, so on a hole's edge the face's dot was
  lit while the click took the bare edge (found by `vex_align`: the standoff went along the
  edge).
- **N3** Ctrl locks the hovered face in the joint dialogs (Align had it); Shift turns Align's dots
  off.
- **N4** Insert STEP of several files (one component per file, side by side, one undo step, the
  Move dialog on all); Data Panel: Upload of several files, STEP cards dragged into the view,
  Insert into Current Design of every selected STEP card.
- **N5** the same STEP file again (path, size, date) = an occurrence ("screw:2").
- **N6** Duplicate With Joints (`duplicate_joints.py`, `duplicate_joints_ui.py`, ASSEMBLE menu,
  icon `duplicate_joints` in `tools/sciforge/icons_vex.py`).
- **N7** speed of big assemblies: measured on the robot, and made faster (section 4 of
  `parity/vex-assembly.md`; the list below).
- **N8** Selectable / Unselectable: not built (see Gaps).
- **N10** `docs/sciforge/vex.md` (a page for the team: parts in, inches, the dots, screws and
  nuts, shafts, Align, frames and speed).
- Merged `develop` (patch 0.1.0-beta.2.2, fac2005e) into `sf/vex` on the orchestrator's request
  (commit 71bf43d9); one conflict (`joints_ui._JointsPanel._selection_changed`: both the limit
  drag's guard and the held snap kept). The patch's scenarios `joints_delete`,
  `joints_limits_drag`, `browser_ghost` pass with the vex work.

## Speed work (N7)

- `decal_ui`'s observer looked at every object on each Placement / Group / Visibility change
  (3562 calls while the robot opened, 117 of 180 s): `decal.decals` asks FreeCAD for
  App::FeaturePython only, the observer waits while a file loads.
- `joints`: joints, grounds, helpers, motion links, contact sets, studies, positions, rigid
  groups from `doc.findObjects("App::FeaturePython")`; the assembly by name first.
- `components.of_type` (FreeCAD's type filter, exact type); `components.bodies_in(recursive)`
  walks the component instead of asking every body whether it is inside;
  `instances.source_bodies` / `sync` / `instances_of` use them.
- `browser_ui`: rows never listed are passed over before they are read; origin rows from one
  look per Origin (`_origin_index`); a row's item keeps its node without its subtree (Qt
  copied the whole tree in and out for the design's row on every read and paint); the timer's
  read is paced on a design whose read takes long (`POLL_PAUSE`).
- `step_import`: files read before the undo step opens; a body read from a file is not copied
  again; `export_report.shape_notes` builds no compound of every face of a solid.
- Measured, not changed (FreeCAD's own): opening is 3.7 s without the window and 36 s or more
  with it, most of it FreeCAD 1.1 making a placement indicator (axes with text labels drawn by
  Qt) for each of the 5400 origin planes, axes and bodies, and meshing the 298 bodies (11 s);
  a lazy indicator would be a core change (see the report).

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
- `view.getObjectInfo` gives the first hit under the pointer; FreeCAD's selection
  (`SoFCUnifiedSelection::getPickedList`) takes, among the hits on the first hit's object, an
  edge or a corner within 0.45 mm of it. `view.getObjectsInfo` gives all hits, nearest first.
- `ViewProviderDragger::attach` (FreeCAD 1.1) builds a `SoFCPlacementIndicatorKit` for every
  part and datum view provider, shown only with ShowPlacement: 1.6 ms each (500 made from
  Python), 8 s for the robot's 5400; a third of reading it (6 of 16 stack samples with gdb).
- FreeCAD's own tree (the hidden Model tab) costs nothing measurable when opening (deleting it
  changed 38.2 s to 37.5 s); hidden bodies are not meshed until shown (open 43 s hidden, 62 s
  shown, under the same heavy load).
- The test runner links the module folder into the throw-away profile: a file edited while a
  batch of scenarios runs is what the later scenarios of the batch load.
- Hovering a square hole straight on: the pointer over the hole hits nothing (or a face behind);
  the hover keeps the hole's centre while the pointer is within the hole's zone, and a click on
  nothing is taken by the hover itself (a mouse-button callback).
- QTest mouse moves carry no keyboard modifiers: a test that holds Ctrl must send its moves with
  the modifier, or the lock is released by the next move. A key press from QTest does set
  QApplication.keyboardModifiers (Shift held for the hover).
- A mouse already on a pixel sends no move event: tests that look at the same spot of several
  holes (the camera centred on each) must come from a neighbouring pixel.

## Scenarios

New: `vex_joint_hole`, `vex_align`, `vex_shaft`, `vex_insert_many`, `vex_duplicate`,
`vex_robot` (the speed measurements; its time targets for opening and the browser's rebuild
fail on this machine, see the speed table). Changed: `insert_step` (C: the same file again is
an occurrence), `exchange2_step_insert` (P5). Results: see the report of this session.

## Gaps

See `parity/vex-assembly.md`, Known gaps: Selectable switch (needs a FreeCAD change), opening
under 30 s and the browser's rebuild under 0.3 s on a 300-part robot (36 s and 0.42 s at best
here), occurrences that share one mesh, ellipse centres, sketch points as snaps.

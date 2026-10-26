# Parity spec: VEX robotics assemblies (beta 3, builder vex)

What a VEX V5 team does in Fusion with VEX's parts, and how SciForge does it. Research with
sources: `docs/sciforge/dev/research/fusion-vex-assembly.md` (its numbers in square brackets
below). Luca (2026-10-26): "if there is a version with step files, we should be good. as long
as the step files work and we are able to import large amounts of items into an assembly,
thats all we need", and "when i say align, i mean align. the align command. so yes we will
need center points on squares and such."

Status: **built and tested with real clicks, not yet signed off by Luca.** Marks: **Autodesk**
/ **Forum** / **VEX** = a source in the research file; **G** = a guess; **(SciForge)** = a
deliberate difference from Fusion, explained.

Code (all in `src/Mod/SciForge/`):

| File | What |
|---|---|
| `sciforge/hole_snaps_core.py` | no FreeCAD: outline centres (straight sides and arcs, exact), a hole's X, which dot the pointer takes (`choose_hot`), finding a hole again (`same_loop`, `best_loop`), fast de-duplication; unit tests `SciForgeTests/unit/test_hole_snaps_core.py` (21) |
| `sciforge/hole_snaps.py` | no Qt: the snap index of a shape (`index_for`: made once per OpenCASCADE shape, names from FreeCAD's indexed map), the snaps of a face / edge with the hole centres, `refind` / `stored_snap` |
| `sciforge/joints.py` | `_shape_snaps` on the index; `snap_candidates` (the snaps near the pointer on a face with very many, quick de-duplication); `snap_record` keeps the hole; `local_placement` / `_chosen_snap` find the hole again after an edit (`_find_snap`); `_longest_edge_direction` no longer walks every edge of a holey face |
| `sciforge/joints_ui.py` | `SnapHover`: hole centres lit around / on / inside a hole (a click into a hole where nothing is under the pointer still takes it), only the dots near the pointer drawn, Ctrl locks the face (`held()`), the joint dialogs take a held snap |
| `sciforge/align.py`, `align_ui.py` | Align's dots from the same index (no copy of the whole part per hover), a hole's centre brings the hole's direction, Shift turns the dots off |
| `sciforge/step_import.py`, `exchange_ui.py`, `insert_ui.py` | several STEP files in one Insert STEP, side by side, one undo step; the same file again = an occurrence |
| `sciforge/data_panel_ui.py`, `data_panel_core.py` | Upload of several files, STEP cards dragged into the 3D view, Insert into Current Design of every selected STEP card |
| `sciforge/instances.py` | an occurrence of an assembly keeps the copies nested in it |
| `sciforge/duplicate_joints.py`, `duplicate_joints_ui.py` | Duplicate With Joints (ASSEMBLE) |
| `sciforge/drawing.py` (`_part_name`) | a drawing's parts list counts an occurrence ("screw:2") as its original: one row, the count in Qty |
| `sciforge/browser_ui.py`, `components.py`, `export_report.py`, `decal.py`, `decal_ui.py` | speed on a 300-part robot (section 4) |
| `SciForgeTests/fixtures/vex/vex_parts.py` | SciForge's own VEX-like parts from VEX's published numbers (never VEX's files), as STEP files made at test time |
| `SciForgeTests/fixtures/vex/vex_robot.py` | a drivetrain of about 300 parts for the speed tests |
| `tools/sciforge/icons_vex.py` | the Duplicate With Joints icon |

## 1. Hole-centre snaps (Joint, Joint Origin, As-built Joint, Duplicate With Joints, Align)

| Fusion | Source | SciForge |
|---|---|---|
| Keypoints: start, middle, end of edges; centres of circles, arcs, ellipses; centre of area of a flat face and of a sketch profile | Autodesk [7]-[10] | Same as before (`joints._shape_snaps`), now from an index of the shape |
| No snap at the centre of a square (or any non-round) hole: VEX users sketch points in the holes, use Between Two Faces, or a library with points | Autodesk [7]-[10]; Forum [27][31][35][49][53][54] | **(SciForge)** every closed inner outline of a flat face (square, rectangle, hex, slot, any shape, sharp or rounded corners) offers its **centre of area** (kind "hole centre"): Z = the face's normal, X = along the outline's longest straight side (sides of one length: the one nearest the face's own longest edge, so all the holes of a part point the same way) |
| The keypoints of an edge | Autodesk [9] | Same; an edge of a hole's outline also offers the hole's centre (after a round edge's own centre, before its middle) |
| A round hole offers points along its axis | Autodesk [6] | Same (as before); **(SciForge)** a flat wall of a hole (a square hole's side) offers the hole's centre where it starts, half-way and where it comes out, Z along the hole (out of each face) |
| Hovering shows the snap points; the click takes the lit one | Autodesk [1][3] | Same. **(SciForge)** a hole's centre is lit while the pointer is around the hole (within 1.6 x its radius), unless a corner or an edge's middle is right under the pointer (8 px); inside the hole, where only the hole's far wall or nothing is under the pointer, the hole's centre stays lit and a click takes it |
| (the joint follows later edits) | Autodesk (joints.md source 8) | A joint on a hole stores the hole (centre, direction, size) besides its edge's name: after an edit renumbers the part's faces and edges it finds the same hole by where it is; a hole that moved by more than its own size or changed size counts as gone and the joint stays where the hole was (said in the Report view) |
| Align offers the same points | Autodesk [1]; G | Same dots in Align (as before); a hole's centre taken on its edge or wall points the part along the hole |

## 2. Keys in the snap hover

| Fusion | Source | SciForge |
|---|---|---|
| Ctrl (Command) held over a face keeps that face's snap points (Joint, Joint Origin, As-built Joint, Align; not Move) | Autodesk [6]; Forum [27][28][32] | Same: the joint dialogs now too (Align had it); a click (or Ctrl+click) while Ctrl is held takes the kept face at its lit dot |
| Shift turns snapping off in Align | Autodesk [1][2] (one excerpt; section 8 question 3) | Same: no dots while Shift is held, the click takes the plain pick (a face's centre of area, an edge's nearest end or middle) |
| Shift in the joint commands | No source | Not changed (G: Fusion's joints always snap) |

## 3. Many parts

| Fusion | Source | SciForge |
|---|---|---|
| Upload takes several files at once | Autodesk [18]; Tutorial [63] | Same: the Data Panel's Upload picks several files |
| Insert into Current Design: one design per insert | Autodesk [16] | **(SciForge)** INSERT > Insert STEP picks several STEP / IGES files at once: one component per file (named after it), laid side by side along X from the origin (each one's box starting 10 mm after the previous one's), one undo step, then the Move dialog (Initial Position) on all of them; a file that cannot be read is named in the message and the others come in. The Data Panel's Insert into Current Design inserts every selected STEP card the same way, and STEP cards can be dragged into the 3D view (designs could) |
| Inserting the same design again: another instance of the same component | Autodesk [16] (excerpt) | Same for a STEP / IGES file: the same path and the same bytes (size and a digest; not the date: a copy of the parts folder or a git checkout gives the same part) as one inserted before in this design = another occurrence of that component (linked, "screw:2"; the browser shows the first as "screw:1"), not a second reading of the file; a changed file (or another copy of it elsewhere) comes in as a part of its own, "screw (2)". A drawing's parts list counts the occurrences of a part in one row (Qty), also once the first one was deleted (the others stay, frozen as they were: components.md) |
| Duplicate With Joints: pick components that are already joined, the open joint, then click new places (Simple or Between Two Faces): each click a duplicate, joined there; enclosed joints duplicated with them | Autodesk [22]; Forum [48] | Same (ASSEMBLE > Duplicate With Joints, after Rigid Group (G: its place in the menu)): Components (view or browser), Joint (taken by itself when there is one open joint, else a list), Position (Simple or Between Two Faces; hole centres work); each copy is an occurrence of each picked component (in the same parent component as the one picked), placed by a new joint of the open joint's type, offsets, axes and limits, the enclosed joints made again between the copies (and a Rigid Group that holds two or more of the picked components together: a new Rigid Group of their copies, G: Fusion lists Rigid Groups with the joints); OK keeps all (one undo step), Esc / Cancel takes them back. A component with no joint, or a joint on a joint origin / as-built, is refused with the reason |
| Picking every matching hole at once | Forum [48] (asked for, not in Fusion) | Not built (one click per copy, as Fusion) |

## 4. Big assemblies: speed

Measured on the sandbox (4 CPUs shared with five other builders, a load of 6 to 9 while
measuring; software OpenGL under xvfb: slower than Luca's PC). Scenario `vex_robot` (it writes
`vex-perf.json` next to the test output): the 298-part drivetrain of
`SciForgeTests/fixtures/vex/vex_robot.py` (9 part files, 289 occurrences, 130 screws, 130 nuts,
a shaft on a revolute joint; 5960 document objects, a 5.8 MB file). Best of the tries, the
spread in brackets; "before" is the same scenario before the speed work of beta 3.

| What | Target | Before | After |
|---|---|---|---|
| Open the robot | < 30 s | 127 s (180 s under load) | 36 s (36 - 62 s with the load) |
| Browser: rows rebuilt (a forced refresh) | < 0.3 s | 0.79 s (0.79 - 2.2) | 0.42 s (0.42 - 1.34) |
| Browser: the design read again after a change | < 0.3 s | 0.35 s (0.35 - 0.78) | 0.30 s (0.30 - 0.62) |
| Timeline refresh | | 0.13 s | 0.12 s (0.12 - 0.27) |
| Hover dots on a rail's web (245 square holes) | < 0.1 s | minutes (every edge walked per corner) | first 0.05 - 0.15 s (the part's index made), then 0.014 s (0.014 - 0.36) |
| Drive the shaft's joint by script: one step | live | 1.86 s (1.86 - 2.59) | 0.05 s (0.05 - 1.45; median 0.45 - 0.68): SciForge's part 0.04 s, the rest is the redraw |
| Drive Joints dialog: one step of the slider | live | 1.09 s (median 1.40) | 0.70 s (median 0.96): the drive and recompute 0.12 s, the rest the other tools' reactions to a change (timeline, looks, display) and the redraw |
| Orbit: one frame (the redraw of 300 parts) | | 0.48 s | 0.35 s (0.35 - 1.45): software OpenGL |
| Insert twenty STEP files in one go | < 20 s | 34.0 s | 21.8 s (21.8 - 29.5) |
| Save | < 10 s | 4.3 s | 3.8 s (3.8 - 6.1) |
| Recompute after the screw's part changed (130 occurrences) | | 32.4 s | 14.1 s (14.1 - 16.6) |
| Build the robot by script (insert, occurrences, recompute, joint) | | 115 s | 83 s (83 - 92) |

What the time goes on, and what was done:

- **Opening**: FreeCAD alone (no window) opens the file in 3.7 s. The rest is FreeCAD's window
  side: FreeCAD 1.1 makes a placement indicator (three axes with text labels drawn with Qt)
  for every origin plane, axis and body when it is created, about 5400 in this robot (1.6 ms
  each here: 8 s; a third of the reading in stack samples), and it meshes the 298 bodies for
  display (11 s: each occurrence is a copy with its own mesh). SciForge's own share was a
  document observer of decals that looked at every object on each change (3562 calls while
  loading, 117 of 180 s): it now asks FreeCAD for its own objects only and waits while a file
  loads. A FreeCAD change (make the indicator when it is first shown) would save those 8 s:
  not made in this branch (a change to FreeCAD's C++ can be tried only in a full build).
- **Browser**: a row's item kept its node with the node's whole subtree (Qt copied it in and
  out on every read and every paint); the origin rows (2400 here) asked FreeCAD for their
  parents one plane at a time.
- **Hover**: the snap points come from an index made once per part (FreeCAD's own indexed map
  names the edges); only the dots near the pointer are drawn.
- **Drive, recompute**: joints, grounds, links, the joints' views and the occurrences' sync
  looked at all 6000 objects (or all bodies) many times per step; they ask FreeCAD for their
  type now. In the Drive Joints dialog each step also recomputes the design, and the other
  tools that follow a change (the timeline, the looks of the bodies, the display settings)
  each read the whole design again (0.1 - 0.2 s each here): not changed (their modules).
  The recompute's rest is FreeCAD meshing the 130 changed screws.
- **Insert**: files are read before the undo step opens (the reading is 6.3 s of the twenty
  without the window), a body read from the file is not copied again, the import notes no
  longer build a compound of every face; the rest is FreeCAD meshing the twenty parts.

## 5. The test parts (VEX's published numbers; never VEX's files)

| Part | Numbers | Source |
|---|---|---|
| Square hole 0.182 in, pitch 0.500 in, first hole 0.25 in from an end | VEX [67][75]; G (the end distance) |
| Aluminium 0.064 in, steel 0.046 in | VEX [67][75] |
| C-channel 1x2x1x25 (al.), 1x5x1x35 (steel, rounded hole corners r 0.02 in, G), 1x2x1x5 (a short piece for close-up tests) | Forum [58]; VEX\* [75] |
| Angle 2x2x25, plate 5x25 | VEX [74]; VEX\* [75] |
| Standoff 1 in, 0.25 in across the hex flats, a #8 hole | VEX [68] |
| Screw #8-32 x 0.5 in, round head 0.27 in x 0.08 in (G), 3/32 in hex socket | VEX [69]; G (head) |
| Keps nut 11/32 in hex, a 0.4 in washer (G) | VEX [70]; G |
| Shaft 1/8 in square x 3 in | VEX [71] |
| Bearing flat 1.5 x 0.5 x 0.1 in, 0.19 in bore between two holes 0.5 in apart | G (no drawing found) |

Masses with Physical Material (a check of the numbers): our 1x2x1x25 aluminium channel 0.124 lb
(VEX 0.116 lb), our 5x25 plate 0.168 lb (VEX 0.146 lb), our 2x2x25 angle 0.129 lb (VEX's 2x2x35
0.154 lb scaled: 0.110 lb): within 7-17 %, so VEX's flanges or holes differ a little from the
published numbers (G).

## Known gaps

| Fusion | Why not (yet) |
|---|---|
| Snap points on sketch points and profile centres in Align / joints | not built (direct-modify.md known gap); the hole centres cover the VEX need |
| Ellipse centres | not built (minor) |
| Duplicate With Joints into every matching hole at once | Fusion has none either (Forum [48]) |
| A STEP insert that stays linked to its file (out of date when the file changes) | the insert is a one-off (insert-export.md); the occurrence check uses the file's path, size and a digest of its bytes |
| A second occurrence of an assembly shows its nested components flat | instances flatten nested components (components.md known gap); the nested copies' solids are all there |
| Selectable / Unselectable on a component (right-click) | not built: FreeCAD's Selectable switch of a body is not asked when the body sits in a component (the component passes the click on to it), so it needs a change in FreeCAD's C++ or a selection filter that would clash with the commands' own |
| Opening a 300-part robot in under 30 s | 36 s at best here (see section 4): most of it is FreeCAD's window side (a placement indicator made for each of 5400 origin planes and bodies; a mesh per occurrence) |
| Occurrences that share one mesh (Fusion's are light) | an occurrence is a copy with its own solid and mesh (instances.py); FreeCAD's links would share the mesh but every SciForge tool works on copies |
| Rows rebuilt in the browser in under 0.3 s on a 300-part robot | 0.42 s at best here (3300 rows made again); reading the design after a change: 0.30 s |
| A live Drive Joints dialog on a 300-part robot | 0.70 s a step at best here (software OpenGL; the timeline, looks and display tools read the whole design after each step) |
| Twenty STEP files inserted in under 20 s | 21.8 s at best here: FreeCAD's STEP reader (6 - 8 s) and its meshing of the twenty parts (about 9 s) |

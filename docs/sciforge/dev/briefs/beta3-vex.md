You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: VEX robotics assemblies (builder vex, branch `sf/vex`)

Luca coached a VEX V5 robotics team that builds its robots in Fusion from VEX parts, and that
team (plus college students) is about to use SciForge. His words: "VEX V5 robotics uses Fusion
to assemble robots. There are whole packs of VEX parts that you can import into fusion and use.
... Those parts have built in attachment points for the align tool. I need to make sure that the
workflow that the team uses currently is how its built. and i need insurance that the parts that
are imported will work just as they work in fusion." Then: "if there is a version with step
files, we should be good. as long as the step files work and we are able to import large amounts
of items into an assembly, thats all we need", and "when i say align, i mean align. the align
command. so yes we will need center points on squares and such."

The research is done: `docs/sciforge/dev/research/fusion-vex-assembly.md` (read all of it; its
section 7 "What SciForge needs" is your work list, N1-N10, with file:line). Key facts: Fusion has
**no** snap at the centre of a square hole (teams add sketch points by hand), so the hole-centre
snaps are a deliberate **(SciForge)** improvement; the snap code today is slow on hole-heavy parts
and must get faster with it; VEX's own STEP files are for personal / educational use only, so
SciForge never ships them: the tests use parts SciForge makes from the published numbers.

### What to build (research section 7; in this order)
1. **N9 test parts first** (`SciForgeTests/fixtures/vex/`, a generator in the style of
   `SciForgeTests/fixtures/make_fixtures.py`, files made at test time or small committed STEP
   files if under ~200 kB each): aluminium C-channel 1x2x1x25, steel 1x5x1x35, angle 2x2x25,
   plate 5x25, 1 in standoff, #8-32 x 0.5 in screw, Keps nut, 3 in square shaft, bearing flat;
   square holes with sharp and with slightly rounded corners; each also written as STEP; and a
   test robot of about 300 parts (a drivetrain frame with its screws, nuts, standoffs, shafts).
2. **N1 hole-centre snaps** for Joint, Joint Origin, As-built Joint and Align (and anything else
   that uses `joints._shape_snaps` / `align.snap_points`): the centre of every closed inner
   outline of a flat face (square, rectangle, hex, slot, any shape), the same centre when an edge
   of that outline is hovered, and the hole's centre at both ends (and half-way) when a flat wall
   of a hole is hovered, Z along the hole; X along the outline's longest straight side; only the
   outline under or nearest the pointer shows its dot; the joint / align record finds the same
   hole after an edit (store what identifies the outline) and survives save / reopen; parity docs
   (`parity/joints.md`, `parity/direct-modify.md` or wherever Align's rows are) mark it
   (SciForge).
3. **N2 hover speed**: an index of the shape's edges / vertices built once per shape (cached by
   object and document change; `doc_epoch.py`), no whole-shape copies per hover, a limit on the
   dots drawn; a timing test on the test C-channel before / after (`perf_guard.py` if it fits).
4. **N4 many STEP files in one go** (Insert STEP multi-select, one undo step, one component per
   file named after it, laid side by side, then the Move dialog; Data Panel: multi-select Upload,
   STEP cards draggable into the 3D view, multi-select Insert into Current Design).
5. **N5 the same part again = another occurrence** of the first ("Screw:2"... Fusion's naming,
   research), linked (`instances.make_instance`), recognised by path + size + date.
6. **N6 Duplicate With Joints** (ASSEMBLE): pick a jointed component (or a screw + nut pair),
   then click hole centres: each click makes an occurrence and a joint of the same type, offsets
   and limits; one undo step.
7. **N7 cheap occurrences** (measure first: the 300-part robot open / orbit / drive / recompute
   / save; then share the source solid instead of deep copies, or another approach the
   measurements justify; keep every existing components / instances scenario passing).
8. **N3** Ctrl locks the hovered face in the joint commands; Shift turns Align's snapping off.
9. **N8 / N10**: a Selectable switch on component rows if cheap; a short "VEX in SciForge" page
   (`docs/sciforge/vex.md` or the cheat sheet: inches, square holes, Duplicate With Joints, Rigid
   Groups for frames, speed tips).

### Speed targets (measure and report; fix what misses)
On the 300-part test robot in this sandbox (slower than Luca's PC): open < 30 s, insert 20 STEP
files < 20 s, a browser refresh < 0.3 s, hovering a C-channel face shows its hole dots < 0.1 s,
driving a joint stays live, save < 10 s. Report every number before and after.

Scenarios `vex_*.py` (8+ paths with real clicks): J onto a square-hole centre (screw into a
channel), Align a standoff onto a hole centre, a shaft through square holes with a revolute joint
and driving it, insert 10 STEP parts at once (undo), insert the same file again (an occurrence),
Duplicate With Joints into 6 holes, the 300-part robot opens and a joint drives, Ctrl lock /
Shift, save / reopen, a channel edited after jointing (the joint stays on its hole). Keep every
existing joints / align / components / insert / exchange scenario passing (run them).

Spec: `docs/sciforge/parity/vex-assembly.md`. Session log: `docs/sciforge/sessions/beta3-vex.md`.
Report as beta3-common says.

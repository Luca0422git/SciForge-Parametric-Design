# SciForge changelog

What changed in each release, newest first, in plain words. Each release's page on GitHub shows
its own section of this file (the release notes are made from it), so every release gets a
section here whose heading is exactly its version number, like `## 0.1.0-beta` below. Known
problems are in [docs/sciforge/known-issues.md](docs/sciforge/known-issues.md).

## 0.1.0-beta.3.1.1

### Fixed

- **Sketch Text: the TEXT panel was see-through.** In the floating panel on the right, a click
  on the Text box went through to the sketch behind it, so typing stopped working. The panel
  (and Measure's box in a sketch) now has its own background and takes the click.
- **Sketch Text: words stay inside the box you drew.** A word that runs past the frame's right
  edge goes on the next line (a word longer than the whole frame is broken). If the lines need
  more height than the frame has, the dialog says so. Texts in designs made before this keep
  their single line until you edit them.

## 0.1.0-beta.3.1

**A full build after beta 3, for VEX robots.** The program itself was built again with one
change to FreeCAD's own code, so it comes as a new installer: SciForge's **Update now**
downloads and runs it (the AppImage: download the new one).

### Improved

- **Selectable/Unselectable** (right-click a body, mesh body or component in the browser, like
  Fusion): it stays visible but can no longer be clicked in the 3D view, so the screws and
  parts around a big frame are easy to pick. A small red mark on its icon shows it; the same
  entry turns it back. An unselectable component covers every body in it. Saved with the
  design, one Undo step; the browser still selects it.
- **Big assemblies open faster**: FreeCAD made a placement indicator (the axis cross of Show
  Placement) for every part and origin plane when a design opened, about 8 seconds of a
  300-part robot; it is now made only when someone turns Show Placement on.

## 0.1.0-beta.3

**The third beta.** Three new things: **stress simulation** (Fusion's Simulation workspace with
its Static Stress study, solved on your own computer), **Auto Timeline** (an AI turns a part
without a timeline, such as a STEP file or a simple mesh, into a real part with timeline
steps you can edit), and **VEX robotics assemblies** (snapping to the centre of square holes,
many STEP parts at once, Duplicate With Joints, and big assemblies much faster). Nothing in the
compiled program changed: if you have 0.1.0-beta.2 or later, **Update now** only replaces
SciForge's own part.

### Simulation (Static Stress)

- **Workspace > Simulation** opens Fusion's SIMULATION workspace with its **SETUP** and
  **RESULTS** tabs; your studies are saved in the design, and **Design** takes you back.
- **New Simulation Study**: Static Stress. Fusion's other study types are listed greyed (they
  are not in SciForge yet). A study can be cloned (right-click > Clone Study) for another load
  case.
- **Study Materials** (try another material in the study only; yield or ultimate strength for
  the safety factor), **Study Settings** (mesh size, element type, adaptive mesh refinement,
  keep the results in the file or not), **Structural Constraints** (Fixed, Pin, Frictionless,
  Prescribed Displacement), **Structural Loads** (Force along the face, at an angle or along a
  direction; Pressure; Moment; Bearing Load; Remote Force; gravity, with Edit Gravity),
  **Automatic Contacts** (bodies that touch are bonded), **Local Mesh Control**, **Generate
  Mesh**, **DOF View** (arrows for every way a part could still move), **Load Case
  Attributes**, and **Pre-check** with a traffic light and a **Repair** button that opens what
  to fix. Every setup change is one Undo step; the values follow the design's units (mm, in...).
- **Solve runs on your own computer** (Fusion uses Autodesk's cloud), in the background: you can
  keep working, and **Cancel** stops it at any moment. **Job Status** lists your solves.
- **RESULTS**: the part coloured by **Safety Factor** (red is weak), von Mises and principal
  stresses, displacements and strains, with a legend you can change, units, **deformation scale**
  and **Animate** (save it as a GIF), **min / max** tags, **Surface** and **Point Probes**,
  **Slice Plane**, **Iso-surface**, **Reaction Force**, **Results Details** with a plain verdict
  ("meets the safety factor target", with the weakest body named), **Compare** up to four studies
  side by side, **Convergence Plot**, and a **Report** (a web page with the setup, the numbers and
  pictures). Right-click on the results for the results tools.
- **Out of date**: change the design or the setup after solving (a hole moved, a part turned)
  and the results say so; **Solve Again** brings them up to date.
- **Checked against hand calculations** (over 300 checks, on Linux and on Windows): beams,
  plates, tubes in torsion, gravity, two glued materials, pins and bearings, inch parts, very
  small and very large parts: within a few percent at the default mesh, and the reaction
  forces add up to the loads exactly. Thin walls get a note asking for a finer mesh, which
  then lands within about 1 %.
- **The AI can run studies too**: "hold the holes, push 1000 N on the top, solve and tell me
  the safety factor".

### Auto Timeline (AI)

- **Right-click a body > Rebuild with Timeline (AI)...** (also on the 3D view's right-click and in
  UTILITIES > AI). The part becomes a faint reference; a new body takes the rebuild. If
  SciForge's chat has an AI set up, it opens with a ready message (you press Send); otherwise the
  message is copied for your AI app (Claude Desktop, Gemini CLI...).
- SciForge reads the part for the AI: its base shape and profile, holes (counterbores,
  countersinks, patterns), pockets, bosses, fillets, chamfers, revolved parts, and gives a step-by-
  step plan in Fusion's order. The AI builds it with the normal tools, so every step is a real
  timeline step, and checks itself after each one. The result really is parametric: make the
  rebuilt plate thicker and its pockets and holes move with its top face.
- **Compare with Reference** (UTILITIES > AI) shows how close the rebuild is: missing material in
  red, extra in green, and what to do next in words. **Finish Rebuild** gives the new part the
  original's name, place, material and spot in the timeline; joints, grounds and patterns that
  used the original move onto the rebuild (a VEX part keeps its joints). **Stop Rebuild...**
  gives a rebuild up. A design saved half way carries on when you open it again.
- Simple meshes (STL, OBJ, 3MF; closed, up to 10,000 triangles) work too. What SciForge cannot
  read (free-form surfaces, threads, raised or engraved text) is named, never guessed.

### VEX robotics and big assemblies

- **Square-hole centres**: in Joint, Joint Origin, As-built Joint, Align and Duplicate With
  Joints, a blue dot shows at the centre of any hole (square, hex, slot, the motor's square
  socket) under or near the mouse, and along a hole's walls. Fusion does not have this; VEX
  teams add points by hand there.
- **Ctrl** keeps the face you are on while you reach for its edge; **Shift** turns Align's dots
  off.
- **Insert STEP takes many files at once** (each becomes a part, laid out in a row, one Undo for
  all), the **Data Panel** uploads several files and drags STEP parts into the design, and
  **inserting the same file again** makes another copy of the same part ("screw:2"); a drawing's
  parts list counts the copies. Delete the first copy and the next one simply becomes the part.
- **Duplicate With Joints** (ASSEMBLE): click hole after hole to put more screws (with their nuts)
  in, each jointed like the first.
- **Big assemblies are much faster**: a 300-part robot opens in about 28 seconds (it took over
  two minutes), hovering a rail with 245 holes is instant, and driving a joint is live.
- **Aluminium AlMg3 (5754)** in the materials: the alloy next to the 5052 VEX metal is made
  of, so a stress test of a VEX part reads a realistic safety factor.
- A page for teams: [docs/sciforge/vex.md](docs/sciforge/vex.md).

### Fixed

- **Designs in inches:** a plain number typed into a dialog (Offset 1.5) or into a sketch's
  dimension or value box (a circle 1 across) was taken as millimetres. It is now in the
  design's units everywhere; type "20 mm" to give millimetres.
- **Closing a design while a tool waited for a click** (Extrude, Hole, Fillet, Offset...) left
  that tool's Undo step open: the next design's first edit went into it, and Undo then took
  back two edits at once under the other design's tool name. Fixed for every tool.

### Known problems

The list is in [docs/sciforge/known-issues.md](docs/sciforge/known-issues.md). New in this beta:
simulation does Static Stress only (one load case per study, bonded contacts only); opening a
300-part robot still takes about half a minute; Auto Timeline reads prismatic and turned parts,
not free-form ones.

## 0.1.0-beta.2.2

### Fixed

- **A joint lost its face when a later step changed the body.** A fillet (or another step)
  added after a joint renumbered the body's faces: the joint went red ("?Face6") and its part
  could jump. The joint now finds its face, edge or point again by its shape and place and
  keeps working. This is the likely cause of "deleting a joint breaks the body": deleting a
  joint itself (browser right-click, the Delete key, the timeline, Del in the 3D view) was
  tested every way and leaves both bodies exactly as they were, with their fillets still
  editable. If it still happens to you, please send the design.

### Improved

- **Drag a joint to set its limits.** In Edit Joint Limits (or the Joint dialog's Motion tab)
  a handle stands on the joint: a disc round its axis for a turn, an arrow for a slide. Drag
  it, or drag the moving part itself, and the joint moves with you. Tick Minimum, Maximum or
  Rest (or click into its box) and that value follows the drag. A faint amber ghost of the
  part shows where Minimum and Maximum are. OK keeps it as one undo step; Cancel puts
  everything back.
- **Hover a hidden body in the browser** and a faint see-through ghost of it shows in the 3D
  view (also hidden components and mesh bodies). Nothing about the body changes.
- **Fillet and Chamfer arrows are diagonal**, like Fusion's: the arrow stands on the middle of
  the round or bevel and points out of the part halfway between the two faces (Equal Distance
  chamfers, variable-radius points and Chord Length too). Two Distances keeps one arrow on
  each face.

## 0.1.0-beta.2.1

**A patch of 0.1.0-beta.2.** Only SciForge's own files changed: **Help > Check for Updates >
Update now** installs it in about a minute.

### Fixed

- **Create Sketch on a face that a later step changed** (a Draft, a fillet or chamfer round
  it, Press Pull) showed the face's outline from before that step, so the purple outline was
  too big or in the wrong place. It now shows the face as it is. Suppressing or deleting that
  step later leaves the sketch and what you built on it in place, and the outline follows.
  Sketches made before this patch keep the outline they got: make them again to get the right
  one. (In 0.1.0-beta too.)
- **Hole > From Sketch** no longer drills at the circles of the face the sketch is on (a hole
  already in the face, a boss standing on it), only at the points and circles you drew.

## 0.1.0-beta.2

**The second beta.** Two new tabs, a complete SURFACE tab, a Data Panel like Fusion's, and a big
round of work on speed and on SciForge explaining itself. If you have 0.1.0-beta, **Update now**
only has to replace SciForge's own part: the compiled program has not changed.

### New tabs and tools

- **SHEET METAL tab**: sheet metal rules (thickness, bend radius, K-factor, reliefs; a library
  and rules kept in the design), **Flange** (one command for base, contour and edge flanges),
  Bend, Hem (six kinds), Join by Bend, Corner Closure, Lofted Flange, sheet metal Fillet and
  Chamfer, Convert to Sheet Metal, Rip, Unfold and Refold, and **Create Flat Pattern** with
  **Export DXF** (bend lines on their own layers). Drawings get a Bend Table and Bend Notes.
- **PLASTIC tab**: plastic rules for each component (a library of 16, including FDM PLA and
  PETG) that Shell, Draft, Rib, Web and thin Extrude follow; Boss (with its screws), Rest, Rule
  Fillet, Snap Fit, Lip and Groove, and **Design Advice**.
- **The SURFACE tab is complete**: more of Fusion's options in Extrude, Revolve, Sweep, Loft,
  Patch, Offset, Untrim, Extend, Stitch, Trim and Ruled; SOLID's modify tools work on surface
  bodies (Fillet, Chamfer, Press Pull, Split Face, Merge, Replace Face, Move/Copy, Align, Scale,
  Pattern, Mirror); Environment Map analysis; Isoparametric Curve in sketches.
- **Draft takes curved and free-form walls** (splines, ellipses), not only flat and round ones.

### Designs, files and the browser

- **A Data Panel like Fusion's**: cards with pictures, search, sort, list or grid, and details
  with a design's versions and where it is used. **Drag a design into an open design** to
  insert a copy; drag files from your file manager onto the panel to add them.
- **Delete a design** from Home (the **...** on a tile, or the Delete key) and from the Data
  Panel. It goes to a trash folder in the same place, never deleted for good.
- **Opacity Control**: right-click a body or component in the browser.
- **Hovering over a body in the 3D view lights its row in the browser.**
- **Export and import reports**: after an export, a short card says what that file format does
  not keep; after an import, what did not come in.
- **Drawing PDFs** with layers you can switch on and off and text you can search.

### Faster, and it explains itself

- **Dragging never waits for the model**: Draft, Fillet, Chamfer, Shell, Press Pull and Extrude
  show a live picture while you drag; the exact result follows when the mouse rests.
- **Editing an earlier step rolls back the later ones while you edit**, as in Fusion.
- **Values stop at the limit**: Fillet, Chamfer, Draft, Shell, Press Pull, Thicken, a tapered or
  thin Extrude, Revolve, Coil, Pipe, Torus, Gear and sketch fillets stop at the largest value
  that works and say so, instead of failing.
- **Sketches explain themselves**: a conflict names the constraints involved and rings them in
  red; a padlock marks fully constrained sketches in the browser and the timeline, and the
  Sketch Palette says how many are left to define.
- **Big designs**: the browser and timeline re-read the design only after a change, and Undo /
  Redo on big parts take about a second instead of many.

### AI

- **117 AI tools** (there were 16), the same for the chat panel and for AI apps you connect,
  including tools the AI uses to check its own work (inspect the design, find geometry, check
  for problems, render a picture, compare two states), and a documentation library it can
  search.
- **Not yet**: the AI cannot use the new SHEET METAL and PLASTIC tabs, nor the SURFACE tab's
  Fillet, Chamfer, Press Pull, Delete and Merge on surface bodies. Its tools for them come
  next.

### Fixed

- **A crash when a design with a drawing closed** while the mouse pointer was on a view of
  the drawing sheet (closing with the keyboard, or the AI closing the design). It was in
  0.1.0-beta too.

### Known problems

The list is in [docs/sciforge/known-issues.md](docs/sciforge/known-issues.md). New in this beta:
the SHEET METAL and PLASTIC tabs are the least used parts of SciForge so far, and the AI cannot
use them yet.

## 0.1.0-beta

**The first public beta.** SciForge is parametric CAD that works the way people who know Fusion
expect it to, free and open source, built on FreeCAD 1.1.4. It is a beta: every feature is tested
by driving the real program, but it has had little use by anyone but its author, so expect rough
edges (read the known issues).

### What you can do

- **Design the Fusion way**: the ribbon (SOLID, SURFACE, MESH, UTILITIES, and SKETCH while
  sketching), the browser, the timeline with a rollback marker, the navigation bar and ViewCube,
  the `S` command search, Fusion's keys and mouse. Dark look by default, a light look in
  Preferences. Home tab with your recent designs, places and a design picture for each.
- **Sketches** with the sketch palette: lines, rectangles, circles, arcs, polygons, slots,
  splines, text; the Sketch Dimension tool; automatic constraints and snapping guides; trim,
  offset, mirror, patterns and more.
- **Solid modeling**: Extrude (all start and extent types, taper, thin), Revolve, Sweep, Loft,
  Rib, Web, Emboss, **Press Pull** (faces, edges, fillet faces, with a draggable arrow), Fillet
  and Chamfer, Shell, Draft, Scale, Combine, Split Body and Split Face, Replace Face, Move/Copy
  and Align, Hole and Thread (simple, counterbore, countersink, tapped, modeled threads),
  primitives (box, cylinder, sphere, torus, coil, pipe), gears, mirror and rectangular, circular
  and path patterns of features, faces and bodies.
- **Components and joints**: components, moving and copying them, rigid, revolute, slider,
  cylindrical, pin-slot, planar and ball joints, as-built joints, joint motion limits, joint drives.
- **Surfaces**: patch, stitch, unstitch, trim, extend, ruled, boundary fill, thicken, delete face.
- **Mesh**: insert, tessellate, repair, reduce, remesh, plane cut, separate and combine, face
  groups, direct edit.
- **Drawings**: base, projected, section, detail and broken views, dimensions with tolerances,
  balloons and parts list, export to PDF and DXF.
- **3D printing**: send to a slicer or export 3MF / STL; **hardware library** (screws, nuts, washers, heat-set inserts, magnets);
  insert STEP, DXF, SVG, canvas pictures, meshes; export everything to open formats.
- **Inspect**: measure, interference, section analysis, curvature, zebra and draft analysis,
  center of mass, construction planes, axes and points.
- **Parameters** you can use in every number field, and **version history** for each design.
- **AI features, off unless you use them**: a chat panel where you connect your own Claude,
  ChatGPT, Gemini or local (Ollama, LM Studio) key and ask it to build; and a connector so AI
  apps such as Claude Desktop can build in SciForge (off until you switch it on in Preferences,
  asks you before the first change in each session, every step is one Undo).
- **FreeCAD Tools**: FreeCAD's own workbenches one click away, with a "Back to SciForge" bar.
- **An example design**: a Raspberry Pi 5 case, built with SciForge, in
  [docs/sciforge/examples/pi5-case](docs/sciforge/examples/pi5-case/README.md).

### New in the way you get and look after SciForge

- **Windows installer and portable download, and a Linux AppImage**, from the
  [Releases page](https://github.com/Luca0422git/SciForge/releases). SciForge installs next to
  FreeCAD without touching it (its own settings folder, own installer entry).
- **Help > Report a Problem**: one dialog that gathers the useful details (versions, graphics
  card, recent SciForge messages, the last crash log) with your name and folders removed. You
  see everything first, then Save it, Copy it, or Open it on GitHub in your browser. Nothing is
  uploaded by SciForge.
- **A crash log**: if SciForge closes unexpectedly, the next start shows a one-line note on Home
  with a button to report it.
- **Help > Check for Updates**, and a quiet check when SciForge starts (at most once a day, off in
  Preferences > General). A new version shows as an **update icon in the top right** of the window
  (next to the search button; it stays until you update) and as one line on Home with **Update
  now**, **What's new** and **Later**. Nothing is installed without your click.
- **A one-line welcome** on Home the first time you start it. It can be closed for good.
- **Version 0.1.0-beta** shown quietly on Home, in SciForge > Diagnostics, on the splash and in
  Help > About.
- **Privacy**: no accounts, no telemetry; the update check and the AI features you connect are
  the only things that go online ([docs/sciforge/privacy.md](docs/sciforge/privacy.md)).

### Known problems

The list is in [docs/sciforge/known-issues.md](docs/sciforge/known-issues.md). The ones to know
before you start: Windows will show "Windows protected your PC" for the unsigned installer
(the exact clicks are in the release notes and in the README); Press Pull is still work in
progress on complex curved shapes; SciForge has no macOS version and is English only.

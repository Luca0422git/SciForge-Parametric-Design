# Fusion Align, Joint snaps and big assemblies, for a VEX V5 team: research for SciForge

Research only, done 2026-10-26, for the VEX items on Luca's beta 3 list (MEMORY.md, session log
"Beta 3 list"): (1) VEX parts come in as STEP files and work, (2) "import large amounts of items
into an assembly", (3) Fusion's **Align** and **Joint** snap to "center points on squares and
such" (VEX metal is full of square holes on a 1/2 inch grid). Black-box documentation research of
Fusion (help pages, API reference, Autodesk blog and support, forums) and of VEX's public
catalogue. Copy the behaviour, never Autodesk's or VEX's assets, wording, files or code. No code
was changed; the SciForge code was read, not run.

## How to read this file

**Tags.** Every fact carries one of these:

- **Autodesk**: help.autodesk.com (help and API reference), Autodesk support articles, Autodesk
  Learn, Autodesk University (AU), the Fusion blog, Autodesk Education.
- **Forum**: Autodesk Community, VEX Forum, Chief Delphi. (Reddit searches returned nothing.)
- **Tutorial**: third-party guides and courses (a university guide, LinkedIn Learning, the
  Onshape blog).
- **VEX**: vexrobotics.com and kb.vex.com. **VEX\*** = a reseller page that repeats VEX's own
  catalogue text (part numbers, specs), used where VEX's page did not come up.
- **G**: my guess, with what it is based on. A G row is an inference or a recommendation, not a
  verified fact.
- **SciForge**: what the code in `src/Mod/SciForge/sciforge/` does today, with file:line.

Numbers in square brackets point to the numbered source list at the end.

**Research limits.** No page could be opened: WebFetch cannot reach any host from the sandbox, so
every fact comes from search-engine excerpts of the cited pages. 50 searches were used. Where an
excerpt and a later search disagree, both are given and the point is listed in section 8.

---

## Summary

1. **Fusion has no snap at the centre of a square hole.** Its keypoints are the start, middle and
   end of edges, the centre of circles, arcs and ellipses, the centre of area of a flat face and
   the centre of area of a sketch profile [7]-[10]. No help page, API page or forum answer shows a
   centre for a non-circular hole, and VEX users are told to add sketch points or use workarounds
   [35][49][53][54]. So the "centre of a square" Luca asked for goes **beyond** Fusion: build it,
   and mark it **(SciForge)** in the parity docs.
2. **Fusion's own way to a square-hole centre** is a joint origin in **Between Two Faces** mode on
   two opposite walls of the hole, then a snap on one of those walls; Autodesk's support article
   for "a cylindrical part in a square hole" says exactly this [12][13]. SciForge already has that
   mode (`joints.py:731-787`), so the workaround works today; it takes about five clicks per hole.
3. **Ctrl lock**: in Fusion, hovering a face and holding Ctrl keeps that face's snap points; it
   works in Align and Joint, not in Move [1][6][28][32]. SciForge has it in Align only.
4. **Align** (SOLID > MODIFY): Objects Bodies / Components; From and To accept a point, line,
   plane, circle or coordinate system; Flip (180 degrees); Angle (90 degrees per click); no
   relationship is kept; Shift turns snapping off [1][2]. A point target takes all three
   coordinates [29].
5. **Many parts in Fusion**: Upload takes many files at once [18][63], but Insert into Current
   Design takes one design at a time [16]. The same part used many times is one component with
   several occurrences (Copy / Paste "Name:1", "Name:2"; a second insert of the same design is
   another instance [16][39]). **Duplicate With Joints** copies a jointed screw into more holes,
   one click per hole [22][48]: it is made for fasteners.
6. **Big assemblies**: a Fusion user with VEX STEP parts found adding, pasting and aligning choppy
   past about 75 parts and blamed the many faces (fillets, square holes) [36]. Autodesk's advice:
   Rigid Group instead of rigid joints for parts that do not move [35], linked (external)
   components [23], unselectable or hidden components [43][44]. Fusion has no "lightweight" mode
   to copy (not found).
7. **VEX parts**: VEX publishes a STEP file for each part on its product pages and keeps no parts
   library [57][66]; teams also use a community Fusion library with every structure length [52]
   and Autodesk's VEX kit (F3Z, unreadable for us) [26][63].
8. **VEX numbers** (for our own test parts): 0.182 in square holes on a 0.500 in pitch; aluminium
   5052-H32 0.064 in thick, steel 0.046 in; #8-32 hardware; standoffs 0.250 in across the hex
   flats; 1/8 in and 1/4 in square shafts (section 5).
9. **SciForge gaps, most important first**: hole-centre snaps; hover speed on hole-heavy faces
   (the snap code scans every edge of the part for every edge of the face); one STEP file per
   Insert; a second insert of the same file is an independent copy, not an occurrence; no
   Duplicate With Joints; heavy occurrences (each repeats the solid). Details in section 7.
10. **Open questions** for Luca's Fusion and the builder: section 8.

---

## 1. Fusion's Align (SOLID > MODIFY > Align)

### 1.1 The dialog

| Behaviour | Source | Notes |
|---|---|---|
| Design > Solid > Modify > Align opens the Align dialog. No shortcut key (Fusion's A is Appearance) | Autodesk [1]; [76] (direct-modify.md A6) | |
| **Objects**: Bodies or Components (what moves) | Autodesk [1]; [76] (A1) | |
| **From**: geometry on the object that moves. **To**: geometry it goes to. Both take a point, a line, a plane, a circle or a coordinate system | Autodesk [1] | "Coordinate system" probably means a joint origin or construction geometry (G) |
| **Flip** turns the result 180 degrees | Autodesk [1] | |
| **Angle**: each click turns the result a further 90 degrees | Autodesk [1] | Known Fusion defect FUS-99810: Angle sometimes flips instead [76] |
| Align moves a body or component without making a relationship: later edits do not keep things aligned | Autodesk [2]; Forum [46] (an Autodesk moderator: use joints, a joint survives geometry changes, Align does not) | |
| Align is parametric: an Align item in the timeline, editable | Autodesk [1][2] (excerpt) | For components, see the next row |
| Moving components by dragging, Align, Drive Joint or Animate makes no timeline item until **Capture Position** is chosen, which adds a Capture Position item | Forum [46] | Conflicts with the row above for components; no source shows a Capture Position field inside the Align dialog itself (section 8) |

### 1.2 Snap points while hovering

| Behaviour | Source | Notes |
|---|---|---|
| Hovering a face or an edge shows its snap points; the click takes the lit one | Autodesk [1]; [3] (Fusion's snap points: vertices, face centres, edge points, edge centres; on spheres, cylinders and tori, tangent points while hovering) | |
| A plain face pick resolves to the face's centre | Autodesk [76] (A7: support article "How to align the center of a face"); the API's flat-face centre is the **centre of area** [8] | |
| Circle centres and sphere centres are offered | Forum [30] (sphere), [31] (Align "will allow you to snap centers") | |
| Hold **Shift**: snapping off | Autodesk [1][2] (search excerpt; a later search could not find the sentence again) | |
| Hover a face, then hold **Ctrl** (Command on macOS): that face is locked for snapping, so a point on its border can be clicked without the edge taking over | Autodesk [1][2]; Forum [28] (an Autodesk community manager: Ctrl works in Align and Joint, not in Move), [27] | |
| A point target takes all three coordinates: Align cannot line things up along one or two axes only | Forum [29] | Users fall back on Move, joints or projected geometry |
| A snap at the **centre of a non-circular closed outline** (square or rectangular hole) | **Not found.** The API's keypoints have none [7]-[10]; forum users with square holes get workarounds [27][31] | G: Fusion has none. A SciForge addition (section 7, N1) |

### 1.3 How Fusion users line things up on square holes (VEX C-channel, 80/20)

| Behaviour | Source | Notes |
|---|---|---|
| For hole-to-hole placement the usual answer is a joint, not Align | Forum [46] | |
| Parts that never move relative to each other: place them with Move or Align, then make a **Rigid Group** (instead of rigid joints) | Forum [35] (Autodesk support, in a VEX EDR thread) | Also a speed tip (3.5) |
| A sketch point at the hole centre, then pick that point | Forum [27][31] | What VEX libraries do (4.2) |
| End face of an extrusion (80/20 profile, VEX square shaft): its centre of area is the profile's centre | G, from [8] | SciForge does this already (`align.py:130-133`, CenterOfMass) |
| A VEX square hole with Align today: hovering the hole's edge gives that edge's middle and ends; hovering a wall gives the wall's centre (half a hole off the axis) | G, from [3][7]-[9] | Same in SciForge (`joints.py:534-571`) |

---

## 2. Joint snap points (Joint, Joint Origin, As-built Joint)

### 2.1 The keypoints

| Behaviour | Source | Notes |
|---|---|---|
| Snap icons mark endpoints, edge and arc midpoints, the face centroid and arc centres | Autodesk [5] (as recorded in [76], joints.md source 3) | |
| Fusion calls them implicit joint origins: different faces offer different points; a centre point is drawn as a plus sign; on a round hole's edge the point offered by default is its centre | Autodesk [14] | |
| The API has four keypoint kinds: Start, Middle, End, Center (since July 2015) | Autodesk [7] | |
| Center applies to circles, ellipses, flat faces and sketch profiles | Autodesk [7] | No "centre of a loop" kind |
| Flat face with no edge given: Center = the face's centre of area; with an edge: a keypoint of that edge | Autodesk [8] | A face with 70 holes has its centre of area somewhere in the middle, not at a hole (G) |
| Open curve: Start, Middle, Center, End; circle or ellipse: Center; closed spline: Start (= End) | Autodesk [9] | The Center of an open arc is the arc's centre (G) |
| Sketch profile: Center = the profile's centre of area | Autodesk [10] | Why a square sketched over a hole gives a usable centre (G) |
| A round hole offers snap points along its axis; when other features hide them, hover the hole, hold Ctrl and click | Autodesk [6] | Start / middle / end of the axis (G, from [9]) |
| A joint origin can only sit on a snap point | Forum [33] | |
| Configurations (2025): several named snap options per joint location, flip per configuration | Autodesk [15] | Not needed for VEX |

### 2.2 Keys

| Behaviour | Source | Notes |
|---|---|---|
| Hover a face, hold **Ctrl** (Command): snap to the points of that face; the face stays locked while the key is held | Autodesk [6]; Forum [32] (Autodesk QA, workaround for FUS-16171), [27] | Joint, Joint Origin, As-built Joint and Align; not Move [28] |
| Between Two Faces: after the two faces, hold Ctrl and hover until the centre point between them appears | Autodesk [13]; Tutorial [64] (holding Ctrl over the two faces shows a projected centre point) | |
| Shift in the joint commands | No source | G: same as Align (snapping off), unconfirmed |

### 2.3 Position modes

| Behaviour | Source | Notes |
|---|---|---|
| **Simple**: one snap point | Autodesk [5][4] | |
| **Between Two Faces**: Plane 1, Plane 2, then a snap point; the origin is centred between the two planes | Autodesk [5][13]; API [11] | Works for any joint type [13] |
| **Two Edge Intersection**: where two non-parallel edges meet when extended | Autodesk [5] | |
| The mode is chosen by right-clicking inside the Joint command (or in the Position tab's Mode) | Autodesk [13][4] | |
| Offset X / Y / Z, Angle, Flip on the Position tab | Autodesk [4] (as recorded in [76]) | |

### 2.4 Square holes: how Fusion users do it

| Behaviour | Source | Notes |
|---|---|---|
| Autodesk's answer for a round part in a square hole: a Joint Origin in Between Two Faces mode on two opposite walls of the square hole, then turn the origin as needed, then the joint | Autodesk [12] | |
| Step by step (G): Joint Origin, mode Between Two Faces, click wall A and the opposite wall B; then hover wall A and click its centre: the origin lands on the hole's centre line, half-way through the metal. Clicking instead the middle of wall A's top edge puts it on the hole's centre at the surface | G, from [5][13] (the snap is brought onto the halfway plane) | Works in SciForge today (2.5) |
| VEX structural parts come with **no joint origins** in their square holes; each hole would need them on both faces | Forum [35] | |
| VEX teams sketch on one square (points or lines), then pattern the sketch over the part; or use a library whose C-channels already have sketch points in every hole, "easy to joint", no edge clicking | Forum [49][53][54] | |
| Advice in a VEX build thread: make a joint origin at the centre of a C-channel hole, then adjust its offsets | Forum [51] | |
| Screws, standoffs, gears: click the round inside edge (the origin goes to its centre); for a flat face, hold Ctrl over it and click its centre | Forum [50][54] | Round geometry is easy; square holes are the problem |
| A screw through a hole: a Cylindrical joint (shaft in the hole) plus a Planar joint between the faces, or one Rigid joint | Forum [34] | |
| Fusion has no mates or flush constraints: joints only, by design | Forum [45] (Autodesk community manager) | The Sept 2026 notes mention timings for "assembly constraints" [25]: section 8 |
| A square shaft through square holes: its end face is a square whose centre of area is the shaft axis; joint it to a bearing's round edge centre | G, from [8][9] | |

### 2.5 SciForge today (joints)

| Behaviour | Source | Notes |
|---|---|---|
| Snap list: a face's centre, corners, the middles of its straight edges and the centres of its round edges; an edge's centre (arc), middle and ends; a corner | SciForge `joints.py:534-571` | Matches 2.1 |
| Flat face centre = centre of area | SciForge `joints.py:476-483` (`face.CenterOfMass`) | Matches [8] |
| Cylinder / cone face: a point on the axis plus the centres of its two round edges (start, middle, end of the axis) | SciForge `joints.py:484-488`, `546-552` | Matches [6] |
| Ellipse centre | Missing: only `Part::GeomCircle` counts as round, `joints.py:512-513` | Minor |
| Sketch profile centre | Not offered (G: `snap_candidates` handles shape elements and datums only, `joints.py:586-617`) | Minor once N1 exists |
| Ctrl lock in the Joint / Joint Origin / As-built Joint hover | **Missing**: `joints_ui.SnapHover` (`joints_ui.py:114-193`) has none; only Align's subclass has it (`align_ui.py:62`, `113-115`) | Parity gap |
| Between Two Faces with the snap brought onto the halfway plane; Two Edge Intersection | Built, `joints.py:731-787` | The square-hole workaround of 2.4 works |
| Centre of a square hole | **Missing** (as in Fusion) | Section 7, N1 |
| Hover cost on hole-heavy faces: `_vertex_name` / `_edge_name` scan every vertex / edge of the **whole part** for each vertex / edge of the hovered face, and `shape.Edges` is rebuilt on every call | SciForge `joints.py:455-470`, called from `544-555` | G (counted, not timed): a 1x2x1x35 C-channel has 140 square holes, about 1,700 edges; its web face has about 280 edges, so about half a million look-ups each time the pointer reaches that face |
| Every dot of the face is drawn and the joint hover takes the nearest one on screen with no distance limit | SciForge `joints_ui.py:181-190` | G: a 70-hole face shows about 560 dots |

---

## 3. Inserting many parts

### 3.1 Getting files in

| Behaviour | Source | Notes |
|---|---|---|
| Data Panel **Upload**: one or several files; non-Fusion files (STEP...) are translated into Fusion designs in the cloud (needs to be online); the upload window lets you change the destination folder | Autodesk [18][19] | |
| The upload file picker takes several files from one folder, not from several folders | Tutorial [63] | |
| Files uploaded from the web site (Fusion Team) are not translated | Forum [41] | |
| Tip: keep many STEP files in one folder or name them consistently | Autodesk [19] | |
| AnyCAD: other-CAD files put in a project folder (Desktop Connector) appear in the Data Panel and can be inserted; their file type shows; an assembly shows as one composite file | Autodesk [17] | |
| **Insert into Current Design**: right-click a design in the Data Panel (or drag it into the open design) → an external component with a link icon, the **Initial Position** dialog (drag the manipulators or type Distance / Angle), an Insert item in the timeline | Autodesk [16]; Forum [42] (drag in) | |
| One design per insert: no source shows several designs inserted in one go | Autodesk [16]; G (absence) | |
| The inserted component stays linked to its design; out of date when the source changes, then updated; **Break Link** makes it local | Autodesk [16][17]; [76] | |
| A personal-hub setting ("don't show this again") can make inserts come in unlinked | Forum [40] | |

### 3.2 The same part many times

| Behaviour | Source | Notes |
|---|---|---|
| Inserting the same design again creates another instance of the same external component | Autodesk [16] (excerpt) | The browser name of the second one ("Name v1:2"?) was not found (section 8) |
| Copy, Paste: a linked duplicate, editing one changes all, named "Comp:1", "Comp:2" | Autodesk / Forum (as recorded in [76], components.md 14); Forum [38][39] | |
| Paste New: an independent component; Fusion then opens Move on it | Forum [39]; [76] | |
| Joints are not copied by Copy / Paste | Forum [39] | |
| Linked copies keep one part number in a parts list; Paste New gives each its own | Forum [39] | |
| Rectangular / circular pattern with Object Type Components | Autodesk (as recorded in [76], components.md 17) | VEX: screws along a channel every 0.5 in |
| Patterns and mirrors do not carry joints | Forum [48] | |
| **Duplicate With Joints** (ASSEMBLE): pick components that are already joined, pick an **open** joint (one that goes to a component outside the selection), then click new places with the Simple or Between Two Faces origin modes: each click adds a duplicate, joined there. **Enclosed** joints (between two selected components, such as screw and nut) are duplicated with them | Autodesk [22]; Forum [48] ("select the component and then select the holes") | Made for fasteners: the VEX screw workflow |
| Picking every matching hole at once: asked for, not available | Forum [48] | |

### 3.3 Placing and grounding

| Behaviour | Source | Notes |
|---|---|---|
| The first component at each level (internal or external) is grounded to its parent by default (anchor icon); right-click Unground From Parent / Ground To Parent | Autodesk [21] | |
| Grounding acts at the component's creation point in the timeline: grounding a child that already has a joint moves it back | Autodesk [21] | |
| After an insert: Initial Position (manipulators, Distance, Angle) | Autodesk [16] | |
| Component moves stay pending until Capture Position | Forum [46]; [76] | |
| Rigid Group for parts that never move relative to each other | Forum [35] | |

### 3.4 Insert Derive, libraries

| Behaviour | Source | Notes |
|---|---|---|
| **Insert Derive** (Solid > Insert): pick a design, then components, bodies, sketches, construction geometry, flat patterns or parameters; they stay linked and update; activate the receiving component first | Autodesk [20] | |
| Autodesk's VEX Kit of Parts: F3Z files, uploaded into a project folder, then inserted | Autodesk [26]; Tutorial [63]; Forum [47] (2021: no insert option after upload; Autodesk support: Insert into Current Design, then joints) | |
| A dedicated "library project" feature | Not found | G: teams keep the uploaded parts in their own project folder [55][63] |
| "Make Independent" on a pasted occurrence | Not found (searched) | G: unconfirmed; Break Link and Paste New are the sourced ways (section 8) |

### 3.5 Big assemblies: speed and display

| Behaviour | Source | Notes |
|---|---|---|
| Fusion's practical limit is "above 2000 parts", depending on the computer | Autodesk [24] | |
| Big data sets: linked (external) components rather than internal ones; split big designs; too many features in one timeline slows Fusion | Autodesk [23] | |
| STEP parts are no faster than Fusion designs without history; each conversion can lose information | Forum [37] | |
| Make the components you are not working on unselectable (an AU tip); grouping components just for speed is a workaround | Forum [44][43] | |
| Simplify components (delete bodies and faces), re-model imported parts, hide unimportant ones with selection sets, cut the feature count | Forum [43] | |
| Isolate / Unisolate, Show / Hide | Autodesk (as recorded in [76], components.md 6) | |
| A robot of VEX STEP parts: past about 75 parts, adding, pasting and aligning got choppy and froze for seconds; the user blamed the many faces (fillets, square holes) | Forum [36] | The same parts SciForge must handle |
| Forum view that Fusion is not built for large assemblies: hide sub-assemblies, simplify; some VEX teams gave up half-way or moved to Onshape | Forum [62][56] | |
| Autodesk's speed-ups: suppress / delete up to 85% faster in big assemblies by recomputing only the affected components, faster pattern and mirror (Apr 2026); configured assemblies up to 80% faster (Sep 2026); joint select / edit / animate up to 5x faster (Jan 2024, excerpt) | Autodesk [25] | Fusion recomputes only what changed |
| A "lightweight" or "large design" mode | Not found (searched) | G: nothing to copy. FreeCAD has `App::Link` (one shared display for many copies) |

### 3.6 SciForge today (insert, occurrences)

| Behaviour | Source | Notes |
|---|---|---|
| Insert STEP: one file per command (single-file picker) | SciForge `insert_ui.py:46-65` (`pick_file`), `insert_ui.py:1871-1891` | Gap for "large amounts" |
| STEP structure kept: a component per product, names, colours; a part used twice **inside one file** comes in once plus linked copies | SciForge `step_import.py:201-268` | Matches insert-export.md Part 2 |
| Each solid becomes a PartDesign Body whose first step is a Part::Feature holding the imported shape | SciForge `step_import.py:271-290` | |
| The same STEP file inserted a second time: an independent component "Name (2)" with its own solids, read from the file again | SciForge `step_import.py:239-245` | Fusion: another instance of the same part [16] |
| The same design inserted twice (Insert Component): an independent linked component "Name (2)" | SciForge `design_insert.py:119-139` | Same gap |
| After Insert STEP, the Move dialog places the component (Initial Position) | SciForge `exchange_ui.py:173-211` | Matches [16] |
| Data Panel Upload button: one file; dropping files from Explorer onto the panel uploads many | SciForge `data_panel_ui.py:1405-1425` vs `332-348` | |
| A STEP card in the Data Panel: right-click > Insert into Current Design runs a fresh import each time; STEP cards cannot be dragged into the 3D view (only designs) | SciForge `data_panel_ui.py:1525-1531` → `versions_ui.py:2024-2033`; `data_panel_core.py:222-224` | |
| Several designs dragged into the 3D view: each comes in as a copy, the last one is placed | SciForge `data_panel_ui.py:579-603` | |
| Copy / Paste (linked occurrences "Name:2"), Paste New, component patterns, Insert Derive, Break Link | Built: `instances.py:232-254`, `348+`; `component_pattern.py`; `derive.py`; `design_insert.py:300+` | Matches 3.2 / 3.4 |
| Ground, Rigid Group, Isolate, Opacity Control on component rows | Built: `browser_core.py:522-545`; `joints.py:2639+` | |
| "Selectable" on component rows | Missing (`browser_core.py:522-545`) | Fusion speed tip [44] |
| Duplicate With Joints | Missing (ASSEMBLE group `ribbon_config.py:294-330`) | |
| Cost of one occurrence: an App::Part, one copy Body per source body (each with its own origin and datums), a FeatureBase and an `InstanceCopy` whose recompute deep-copies and moves the source solid | SciForge `instances.py:174-195`, `257-288`; `bodies.global_shape` (copy=True) | G: about 18-20 document objects, one solid copy and one tessellation per occurrence; 300 screws = several thousand objects |
| Hardware library: ISO metric only, no #8-32 | SciForge `hardware_core.py:1-30` | Low priority: VEX STEP screws cover it |

---

## 4. The VEX + Fusion workflow

### 4.1 Where the parts come from

| Behaviour | Source | Notes |
|---|---|---|
| VEX publishes official CAD for every part on its product pages, as a STEP (.step / .stp) file; VEX keeps no "parts library", only the STEP downloads | Forum [57]; VEX [66] (same arrangement for VEX IQ and GO: a free STEP for every part, readable by most CAD programs) | MEMORY.md: Luca is fine with STEP |
| The models are free for personal and educational use; commercial use of 3D-printed VEX parts is forbidden | VEX [66] | So SciForge must not ship VEX's files: our tests use our own parts (section 5) |
| Some parts are missing from the downloads | Forum [60] | |
| Autodesk's VEX page points to a Fusion Kit of Parts (F3Z, Fusion's own format) | Autodesk [26]; Tutorial [63] | F3Z cannot be read by SciForge (MEMORY.md) |
| Community "VEX CAD Fusion 360 Parts Library" 2.0: every competition-legal part, a file for every structure length, each motion part in every insert option, spacers, screws and standoffs in every length; its add-in is no longer supported | Forum [52] | |
| The older add-in resized C-channels and axles; setting the library up (uploading every file) took 1-2 hours once | Forum [55] | |
| An Ohio State VEX-U Fusion library also exists | Forum [57] | |
| Onshape has its own VEX V5 / IQ parts libraries | Tutorial [65] | Many teams use Onshape [56] |

### 4.2 How teams assemble

| Behaviour | Source | Notes |
|---|---|---|
| Insert each part into the robot design, then position with joints | Forum [47] (Autodesk support) | |
| Square holes: Between Two Faces joint origins, sketch points in the holes (one square, then a pattern), or a library that has them | Autodesk [12]; Forum [49][51][53][54] | 2.4 |
| Round geometry (screws, gear inserts, standoffs' ends): click the round edge, its centre is the joint origin; Ctrl over a flat face for its centre | Forum [50][54] | |
| Frames that never move: Move / Align into place, then Rigid Group | Forum [35] | |
| A screw: Cylindrical joint plus Planar joint, or Rigid | Forum [34] | |
| Many identical parts: Copy / Paste and patterns; Duplicate With Joints for fasteners | Autodesk [22]; Forum [39][48] | |

### 4.3 Pain points

| Behaviour | Source | Notes |
|---|---|---|
| No joint origins in VEX square holes | Forum [35] | N1 |
| Wanted: a library where every hole already has a snap point | Forum [53][54] | N1 solves it without a library |
| Choppy past about 75 parts; picking a C-channel face makes Fusion stall | Forum [36] | N2, N7 |
| One user's Fusion stopped coping after a few C-channels and a motor (others disagreed); teams that could not get past half a robot | Forum [56] | |
| A display bug after modifying a 3-wide aluminium C-channel (fixed by unsuppressing features) | Forum [59] | |
| Setting up a library takes hours of uploading | Forum [55] | N4 |

---

## 5. VEX V5 dimensions

Public numbers, to model SciForge's **own** test parts (never VEX's files). Inches first;
1 in = 25.4 mm.

| Part | Public number | Source | Notes for our test parts |
|---|---|---|---|
| Square hole | 0.182 in square (4.62 mm), "VEX standard" | VEX [67]; VEX\* [75] (plate 15x5, hinge, aluminium kit) | Corner shape (sharp or slightly rounded) not found: make both variants (G) |
| Hole pitch | 0.500 in (12.7 mm) between hole centres | VEX [67]; VEX\* [75] | |
| Size names | Numbers count holes per face: 1x2x1x35 = a 1-hole flange, a 2-hole web, a 1-hole flange, 35 holes long | Forum [58]; VEX\* [75] | |
| Lengths | 35 holes = 17.5 in (a 1x5x1x35 is 17.5 in long and 2.5 in wide); 25 holes = 12.5 in by the same rule | VEX\* [75]; G (25 holes) | Holes start 0.25 in from each end (G) |
| C-channel profiles | 1x2x1, 1x3x1, 1x5x1 (webs 2, 3 and 5 holes wide) | Forum [58]; VEX\* [75] | Outside web width = holes x 0.5 in (G) |
| Aluminium | 5052-H32, 0.064 in (1.6 mm) thick | VEX [67]; VEX\* [75] | No source for 0.040 in |
| Steel | Cold-rolled, 0.046 in thick, zinc plated; the channels can be cut into 2.5 in pieces | VEX\* [75] | |
| Weights | Al 1x2x1x35 0.157 lb; Al 1x2x1x25 0.116 lb; steel 1x2x1x35 0.361 lb; Al 2x2x35 angle 0.154 lb; Al 5x25 plate 0.146 lb | VEX\* [75] | A check for Physical Material masses (G) |
| Angles | 2x2x25, 2x2x35 (2 holes per leg), aluminium and steel | VEX [74]; VEX\* [75] | No "1x1 angle" found |
| Plates, U-channel | 5x25 and 15x5 plates; 2x2x2x20 aluminium U-channel | VEX\* [75]; VEX [67] | |
| Standoffs | Aluminium, #8-32 thread inside, 0.250 in across the hex flats; 1/4, 1/2, 3/4, 1, 1.5, 2, 2.5, 3, 4, 5, 6 in (275-1013 to 275-1023) | VEX [68] | |
| Screws | #8-32; star drive (T15) from 1/4 in to 2 in in 13 lengths; older button heads with a hex (Allen) drive, 275-1002 to 275-1012 from 0.250 in | VEX [69]; VEX\* [75] (3/32 in hex key, per the reseller) | #8 thread outside diameter 0.164 in (G: UNC table); fits the 0.182 in hole |
| Nuts | #8-32: Keps (built-in toothed washer, removable), Nylock (nylon insert, permanent), plain hex, low profile (sized for standoffs); 11/32 in across flats, low profile 1/4 in | VEX [70] | |
| Shafts | Standard 1/8 in (0.125 in) square; High Strength 1/4 in (0.250 in) square in 2, 3, 4 and 12 in; the 2, 3, 4 in HS shafts are about 1 mm shorter than the same standoffs; HS shafts do not pass through the square holes (a 5/16 in or 8 mm hole is drilled) | VEX [71]; Forum [58] | A 1/8 in shaft in a 0.182 in hole has play: it turns in a bearing (G) |
| Bearings | Bearing Flat 276-1209 (Delrin; screws or rivets onto the metal; holds a shaft square to it); low-profile 276-8023 (fits inside a C-channel); HS shaft bearing 276-3521; HS ball bearing 276-8402: 0.302 in bore, a square insert for 1/8 in shafts | VEX [72]; VEX\* [75]; Forum [61] | Bearing Flat hole layout not found: G (a centre bore between two mounting holes on the 0.5 in grid) |
| Spacers, washers | Nylon spacers 0.125, 0.250, 0.375, 0.500 in long (pack 275-1066); washers cut friction, spacers keep gaps | VEX\* [75]; VEX [73] | Outside diameters not found |

---

## 6. What SciForge already matches (short)

- **Align** dialog (Objects, From, To, Flip, Angle), snap dots (face centre, corners, edge
  middles, circle centres), Ctrl lock, face click = centre of area, timeline step:
  `align.py:1-37`, `86-167`; `align_ui.py:25-117`, `132-380` (direct-modify.md A1-A10).
  Missing: Shift to turn snapping off; joint origins as From / To dots; the square-hole centre.
- **Joint snaps**: the full Fusion keypoint list except ellipse and profile centres
  (`joints.py:472-571`); Between Two Faces and Two Edge Intersection (`joints.py:731-787`); the
  joint re-finds its snap after edits (`joints.py:629-635`, `689-694`). Missing: Ctrl lock in the
  joint hover, the square-hole centre.
- **Insert**: STEP with its structure and copies (`step_import.py`), Initial Position
  (`exchange_ui.py:173-211`), Upload, Insert into Current Design, Insert Derive, Break Link,
  Copy / Paste / Paste New, patterns of components, Ground, Rigid Group, Isolate. Missing for
  VEX: several files at once, occurrences across inserts, Duplicate With Joints, Selectable,
  cheap occurrences.

---

## 7. What SciForge needs (ordered by importance for a VEX team)

Each item: what, why, where, how to test. "(SciForge)" = goes beyond Fusion on purpose.

**N1. Hole-centre snaps for Joint, Joint Origin, As-built Joint and Align (SciForge). [P0]**
- On a flat face, every closed inner outline (square, rectangular, hex, slot, any shape) gets a
  centre dot at the outline's centre of area (`Part.Face(wire).CenterOfMass`, G), Z = the face's
  normal, X = along the outline's longest straight side so a square shaft or nut lines up.
- On an edge that belongs to such an outline: the same dot (with the outline's face normal).
- On a flat side wall of a hole made of flat faces (a square hole's wall): the hole's centre at
  both ends and half-way, Z along the hole, like Fusion's round-hole axis points [6]. VEX holes
  go through 0.046-0.064 in of metal, so both ends matter (which side the screw sits on).
- Where: `joints._shape_snaps` (`joints.py:534-571`) with a new kind "loop"; `snap_record` and
  `_chosen_snap` (`joints.py:629-635`, `689-694`) so a joint finds the same hole after an edit
  (store the outline's edge names, or one edge plus its face). Align gets it through
  `align.snap_points` (`align.py:146-167`).
- Show only the outline under or nearest the pointer (not all 70 holes of a face).
- Parity: Fusion has none (1.2, 2.1): write it in parity/joints.md and parity/direct-modify.md
  as a deliberate **(SciForge)** difference.
- Test: a scenario on the test C-channel (N9): J, hover a square hole → its centre dot; a
  screw's round edge onto it; Align a standoff's end face onto a hole centre; add holes to the
  channel → the joint stays on its hole; undo / redo; save / reopen.

**N2. Hover speed and readable dots on hole-heavy parts. [P0, else N1 is unusable]**
- `_vertex_name` / `_edge_name` (`joints.py:455-470`) scan the whole part for every vertex and
  edge of the face (`shape.Edges` rebuilt each call); the de-duplication in `snap_candidates`
  (`joints.py:612-616`) compares every dot with every other; Align copies the whole shape on
  every hover (`align.py:155-156`). On a 1x2x1x35 C-channel this is about half a million
  look-ups per new face (G, section 2.5).
- Build an index once per shape (hash → "EdgeN" / "VertexN"), cached by object and document
  change (`doc_epoch.py` exists); limit the drawn dots to those near the pointer
  (`joints_ui.py:181-190` takes the nearest with no limit; Align uses 14 px,
  `align_ui.py:22`).
- Test: time the hover on the test C-channel with `perf_guard.py` (a baseline in ms).

**N3. Ctrl lock in the joint commands; Shift turns Align's snapping off. [P1, parity]**
- Fusion: Ctrl locks the hovered face in Joint, Joint Origin, As-built Joint and Align
  [6][28][32]; Shift turns Align's snapping off [1][2].
- Where: `joints_ui.SnapHover` (`joints_ui.py:114-193`): port the lock of `align_ui.py:62` and
  `113-115`; Align's hover: Shift = no dot, the click takes the plain pick.

**N4. Many STEP files in one go. [P0, "large amounts of items"]**
- Insert STEP takes several files (`getOpenFileNames` in `insert_ui.py:46-65`; the command at
  `insert_ui.py:1871-1891`; `exchange_ui.insert_cad_file`, `exchange_ui.py:173-211`): one undo
  step, one component per file named after it, laid side by side instead of on top of each other
  at the origin (G), then the Move dialog.
- Data Panel: Upload button with multi-select (`data_panel_ui.py:1405-1425`; dropping many files
  already works, `332-348`); STEP cards draggable into the 3D view and multi-selectable for Insert
  (`data_panel_core.py:222-224` takes designs only; `data_panel_ui.py:1525-1531`).
- Parity: Fusion uploads many files at once [18][63] but inserts one at a time [16]; inserting
  several in one go is a convenience **(SciForge)**.
- Test: insert 20 test-part STEP files in one go; time it; undo removes all of them.

**N5. The same part many times = one part, several occurrences. [P0]**
- A STEP file (or design) already inserted in this design comes in as an occurrence of the first
  one ("Screw:2", linked, `instances.make_instance`) instead of "Screw (2)" with new solids
  (`step_import.py:239-245`; `design_insert.py:125-130`). Fusion: a second insert of the same
  design is another instance of the same component [16]. Recognise the file by its path plus
  size and date (G).
- Test: insert the screw file 3 times → "Screw:1..3"; edit the source → all follow; the parts
  list counts 3 of one part.

**N6. Duplicate With Joints. [P1, the biggest time-saver for screws, standoffs and nuts]**
- New ASSEMBLE command (`ribbon_config.py:294-330`) per [22]: pick jointed components (a screw,
  or a screw + nut pair), pick the open joint, then click hole centres (needs N1): each click =
  an occurrence (`instances.make_instance`) and a joint of the same type, offsets and limits;
  enclosed joints are copied with the pair.
- Test: one screw jointed in a hole, 10 clicks → 10 screws jointed; edit the channel → they
  follow; one undo step.

**N7. Cheap occurrences for hundreds of fasteners. [P1]**
- Today each occurrence is an App::Part, a copy Body per source body (with origins), a
  FeatureBase and an `InstanceCopy` whose recompute deep-copies and moves the source solid
  (`instances.py:174-195`, `257-288`; `bodies.global_shape` copy=True). G: 300 screws = 300 solid
  copies, 300 tessellations, several thousand document objects.
- Options (G, to measure first): keep the model but share the source solid (place it with a
  Placement instead of a deep copy, so OpenCASCADE's triangulation is computed once); or draw
  occurrences with FreeCAD's `App::Link`, which shares one display node (components.md explains
  why links were not used for the model itself). Check Rigid Group speed with many members
  (`joints.py:2639+`), the Fusion advice for frames [35].
- Test: a 300-part test robot (N9): open, orbit, drive a joint, recompute, save; times recorded
  by `perf_guard.py`.

**N8. Display help for big robots. [P2]**
- "Selectable" on / off on component rows (`browser_core.py:522-545`), the Fusion speed tip
  [44]; Isolate and Show / Hide exist.

**N9. Test parts from public numbers. [P0, needed by N1-N7]**
- Made by SciForge from section 5 (never VEX's files, [66]): aluminium C-channel 1x2x1x25
  (0.064 in, 0.182 in square holes, 0.5 in pitch), steel 1x5x1x35 (0.046 in), 2x2x25 angle,
  5x25 plate, 1 in standoff (0.25 in hex), #8-32 x 0.5 in screw (round head, 0.164 in shank),
  Keps nut (11/32 in hex), 3 in square shaft (1/8 in), a bearing flat (G layout); each also
  written as STEP; a test robot of about 300 parts. Square holes with sharp and with rounded
  corners. In the style of `SciForgeTests/fixtures/make_fixtures.py`.

**N10. A short "VEX in SciForge" page for the team. [P2]**
- Units in inches (browser > Change Active Units); square holes today with Between Two Faces
  (2.4); hole-centre dots once N1 is built; Rigid Group for frames; Copy / Paste for repeated
  parts. In `docs/sciforge/cheat-sheet.md` or the user docs.

Lower priority: ellipse centres (`joints.py:512-513`); Align dots on joint origins and sketch
points (direct-modify.md known gap); #8-32 in the Hardware library (`hardware_core.py`, ISO
metric only); a STEP insert that stays linked to its file (insert-export.md known gap).

---

## 8. Open questions

For Luca's Fusion (a screenshot settles each):

1. Does today's Fusion offer a centre on a VEX square hole when hovering it in Joint or Align
   (with and without Ctrl)? Every source says no (1.2, 2.1).
2. Align on **components**: an Align item in the timeline [1][2], or a pending move that needs
   Capture Position [46]? Is there a Capture Position option in the Align dialog?
3. Does Shift turn snapping off in Align (one excerpt says so [1][2], a later search could not
   find it)? And in Joint?
4. The browser name of a design inserted twice ("Name v1:1", "Name v1:2"?), and whether a pasted
   occurrence's menu has "Make Independent".
5. The September 2026 notes time "assembly constraints" [25], while Autodesk said Fusion is
   joints only [45]: does Fusion now have a constraint command beside joints?

For the builder / Luca:

6. Do VEX's STEP square holes have sharp or slightly rounded corners? (N1 works either way; it
   changes the dots shown at the corners.)
7. How many parts has the team's robot (fasteners included)? It sets the speed target of N7.
   G: a few hundred.
8. Where the VEX items go: patch, beta 3 or later (already asked, MEMORY.md "Questions waiting
   for Luca").

---

## Sources

Autodesk

1. Autodesk help, "Align solids" (SLD-ALIGN-CMD): https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-ALIGN-CMD.htm
2. Autodesk help, "Align reference" (SLD-REF-ALIGN): https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-REF-ALIGN.htm
3. Autodesk help, "Create a point at a vertex" (snap points): https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-CONSTRUCT-POINT-AT-VERTEX.htm
4. Autodesk help, "Create a joint" (ASM-CREATE-JOINT): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-CREATE-JOINT.htm
5. Autodesk help, "Create a joint origin" (ASM-CREATE-JOINT-ORIGIN): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-CREATE-JOINT-ORIGIN.htm
6. Autodesk help, "Create an as-built joint" (ASM-CREATE-AS-BUILT-JOINT): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-CREATE-AS-BUILT-JOINT.htm
7. Autodesk API, "JointKeyPointTypes Enumerator": https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/JointKeyPointTypes.htm
8. Autodesk API, "JointGeometry.createByPlanarFace": https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/JointGeometry_createByPlanarFace.htm
9. Autodesk API, "JointGeometry.createByCurve": https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/JointGeometry_createByCurve.htm
10. Autodesk API, "JointGeometry.createByProfile": https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/JointGeometry_createByProfile.htm
11. Autodesk API, "JointGeometry.createByBetweenTwoPlanes": https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/JointGeometry_createByBetweenTwoPlanes.htm
12. Autodesk support, "How to assemble a cylindrical part into a square hole in Fusion 360": https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-assemble-a-cylindrical-part-into-a-square-hole-in-Fusion-360.html
13. Autodesk blog, "Quick Tip: Adding Joints Between Two Faces": https://www.autodesk.com/products/fusion-360/blog/quick-tip-adding-joints-between-two-faces/
14. Autodesk Learn, "Define joints for component relationships": https://www.autodesk.com/learn/ondemand/tutorial/define-joints-for-component-relationships
15. Autodesk blog, "March 2025 product update" (configured joint snaps): https://autodesk.com/products/fusion-360/blog/march-2025-product-update-whats-new ; help CFG-JOINT-SNAP-FLIP: https://help.autodesk.com/cloudhelp/ENU/Fusion-Configurations/files/CFG-JOINT-SNAP-FLIP.htm
16. Autodesk help, "Insert designs" (ASM-INSERT-FUSION-DESIGN): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-INSERT-FUSION-DESIGN.htm
17. Autodesk help, "Insert designs created in other CAD applications" (ASM-INSERT-ANYCAD): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-INSERT-ANYCAD.htm ; "Upload designs created in other CAD applications" (ASM-UPLOAD-ANYCAD): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-UPLOAD-ANYCAD.htm
18. Autodesk support, "How to import or open a file in Fusion": https://knowledge.autodesk.com/article/How-to-import-or-open-a-file-in-Autodesk-Fusion-360
19. Autodesk blog, "Import STEP file into Fusion": https://www.autodesk.com/products/fusion-360/blog/import-step-file-into-fusion-360/
20. Autodesk help, "Derive design features from one design into another" (ASM-DERIVE): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-DERIVE.htm
21. Autodesk blog, "Introducing Ground to Parent": https://autodesk.com/products/fusion-360/blog/introducing-ground-to-parent-a-new-assembly-tool-in-autodesk-fusion
22. Autodesk help, "Duplicate components with their joints" (ASM-DUPLICATE-WITH-JOINTS): https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-DUPLICATE-WITH-JOINTS.htm ; command page: https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-DUPLICATE-WITH-JOINTS-COMMAND.htm
23. Autodesk blog, "Optimizing Your Performance and Productivity With Autodesk Fusion": https://www.autodesk.com/products/fusion-360/blog/how-to-optimize-performance-productivity-autodesk-fusion/
24. Autodesk University, "Fusion 360 Large Model Management" (handout CP10167): https://static.au-uw2-stg.autodesk.com/handout_10167_CP10167_20Fusion_20360_20Large_20Model_20Management.pdf ; class page: https://www.autodesk.com/autodesk-university/class/Fusion-360-Large-Model-Management-Productivity-and-Performance-2015
25. Autodesk blog, product updates: April 2026 https://www.autodesk.com/products/fusion-360/blog/april-2026-product-update-whats-new/ ; May 2026 https://www.autodesk.com/products/fusion-360/blog/may-2026-product-update-whats-new/ ; September 2026 https://www.autodesk.com/products/fusion-360/blog/september-2026-major-product-update-whats-new/ (the January 2024 joint figure came from a search excerpt of the blog; its page was not identified)
26. Autodesk Education, "VEX: recommended software": https://www.autodesk.com/education/competitions-and-events/vex/recommended-software

Forum

27. Autodesk Community, "How to keep snap points visible for selection?": https://forums.autodesk.com/t5/fusion-design-validate-document/how-to-keep-snap-points-visible-for-selection/td-p/7313453
28. Autodesk Community, "Keep snap points visible for selection - Holding CTLR doesn't work": https://forums.autodesk.com/t5/fusion-support-forum/keep-snap-points-visible-for-selection-holding-ctlr-doesn-t-work/m-p/12687354
29. Autodesk Community, "Align components to a single axis?": https://forums.autodesk.com/t5/fusion-support-forum/align-components-to-a-single-axis/m-p/10351982
30. Autodesk Community, "How to Align a body with origin plane": https://forums.autodesk.com/t5/fusion-design-validate-document/how-to-align-a-body-with-origin-plane/m-p/6018800
31. Autodesk Community, "Snap problems": https://forums.autodesk.com/t5/fusion-design-validate-document/snap-problems/m-p/6683992
32. Autodesk Community, "Joint issues" (FUS-16171): https://forums.autodesk.com/t5/fusion-design-validate-document/joint-issues/m-p/5475032
33. Autodesk Community, "Creating a joint between two components": https://forums.autodesk.com/t5/fusion-support-forum/creating-a-joint-between-two-components/m-p/7876358
34. Autodesk Community, "How do I make this type of joint?": https://forums.autodesk.com/t5/fusion-design-validate-document/how-do-i-make-this-type-of-joint/m-p/10422752
35. Autodesk Community, "VEX EDR Robotic Assembly in Fusion 360": https://forums.autodesk.com/t5/fusion-support-forum/vex-edr-robotic-assembly-in-fusion-360/m-p/7823475
36. Autodesk Community, "Robot assembly performance using VEX Robotics STEP files": https://forums.autodesk.com/t5/fusion-design-validate-document/robot-assembly-performance-using-vex-robotics-step-files/td-p/6565750
37. Autodesk Community, "Building a parts library, STEP vs F3D file type performance": https://forums.autodesk.com/t5/fusion-design-validate-document/building-a-parts-library-step-vs-f3d-file-type-performance/td-p/9391560
38. Autodesk Community, "Break Link Between Copied and Pasted Components": https://forums.autodesk.com/t5/fusion-design-validate-document/break-link-between-copied-and-pasted-components/m-p/9808282
39. Autodesk Community, "Paste functioning but not 'Paste New'": https://forums.autodesk.com/t5/fusion-support-forum/paste-functioning-but-not-quot-paste-new-quot/m-p/8871582
40. Autodesk Community, "Insert into Current Design not linked to original external component file": https://forums.autodesk.com/t5/fusion-support-forum/insert-into-current-design-not-linked-to-original-external/td-p/9421225
41. Autodesk Community, "Can't open a .STEP file or a .SLDPRT file. Am I missing something?": https://forums.autodesk.com/t5/fusion-support-forum/can-t-open-a-step-file-or-a-sldprt-file-am-i-missing-something/td-p/11729061
42. Autodesk Community, "import a step file": https://forums.autodesk.com/t5/fusion-design-validate-document/import-a-step-file/m-p/6557361
43. Autodesk Community, "Issues with a giant assembly (Including lag and a crash)": https://forums.autodesk.com/t5/fusion-design-validate-document/issues-with-a-giant-assembly-including-lag-and-a-crash/td-p/6741454
44. Autodesk Community, "Fusion 360 is able to handle large assemblies, even complex marble machines": https://forums.autodesk.com/t5/fusion-design-validate-document/fusion-360-is-able-to-handle-large-assemblies-even-complex/m-p/8367289
45. Autodesk Community, "Where are the constraints / mates?": https://forums.autodesk.com/t5/fusion-design-validate-document/where-are-the-constraints-mates/m-p/5549328
46. Autodesk Community, "Understanding Component positions and projections (without joints)": https://forums.autodesk.com/t5/fusion-design-validate-document/understanding-component-positions-and-projections-without-joints/td-p/12554238 ; "Aligning joints to other parts workflow": https://forums.autodesk.com/t5/fusion-design-validate-document/aligning-joints-to-other-parts-workflow/td-p/9222902
47. Autodesk Community, "How to use VEX library parts in assembly": https://forums.autodesk.com/t5/fusion-design-validate-document/how-to-use-vex-library-parts-in-assembly/td-p/10740162
48. Autodesk Community (idea), "Copy components with joints": https://forums.autodesk.com/t5/fusion-360-ideastation-archived/copy-components-with-joints/idc-p/7066828
49. VEX Forum, "Assemblies/Joints in Fusion 360": https://www.vexforum.com/t/assemblies-joints-in-fusion-360/41295
50. VEX Forum, "VRC Gear Drive Fusion 360": https://www.vexforum.com/t/vrc-gear-drive-fusion-360/100416/5
51. VEX Forum, "Fusion 360 Joints": https://www.vexforum.com/t/fusion-360-joints/79476
52. VEX Forum, "VEX CAD Fusion 360 Parts Library 2.0.0 Release": https://www.vexforum.com/t/vex-cad-fusion-360-parts-library-2-0-0-release/120228
53. VEX Forum, "What Part Library is Best for Fusion 360?": https://www.vexforum.com/t/what-part-library-is-best-for-fusion-360/59691
54. VEX Forum, "RobotMesh Studio with New Chrome Versions" (the reply about sketch points in C-channel holes): https://www.vexforum.com/t/robotmesh-studio-with-new-chrome-versions/92834/5
55. VEX Forum, "New to CAD": https://www.vexforum.com/t/new-to-cad/87491/4
56. VEX Forum, "CAD Softwares": https://www.vexforum.com/t/cad-softwares/103966 ; "Fusion 360 freezing issues": https://www.vexforum.com/t/fusion-360-freezing-issues/92765
57. VEX Forum, "CAD for VEX Robotics" (PDF guide): https://www.vexforum.com/uploads/default/original/2X/d/d8874234e83e4833c96713eeeb2d2b3327233a40.pdf ; "VEX CAD Directory": https://www.vexforum.com/t/vex-cad-directory/81708
58. VEX Forum, VEX beginner guide (PDF; hole counts, shaft fit): https://www.vexforum.com/uploads/default/original/2X/a/a7d875efc87c0acdfb4c7a9cbdb02cb5f7c72e4b.pdf
59. VEX Forum, "Fusion 360 - VEX Cad - Bug when 'Modifying' 3x Alu C channel?": https://www.vexforum.com/t/fusion-360-vex-cad-bug-when-modifying-3x-alu-c-channel/108403
60. VEX Forum, "STEP files missing for certain vex iq parts": https://www.vexforum.com/t/step-files-missing-for-certain-vex-iq-parts/96938
61. VEX Forum, "New Products - July 2022 (High Strength Shaft Ball Bearings)": https://www.vexforum.com/t/new-products-july-2022-high-strength-shaft-ball-bearings/104429
62. Chief Delphi, "Fusion 360 is slow": https://www.chiefdelphi.com/t/fusion-360-is-slow/373330

Tutorial

63. NYU Tandon, "VEX CAD Assembly Guide": https://manual.eg.poly.edu/index.php/VEX_CAD_Assembly_Guide
64. LinkedIn Learning (Lynda), "Migrating from AutoCAD to Fusion 360: Joint origin": https://origin-www.lynda.com/Fusion-360-tutorials/joint-origin/667363/703417-4.html
65. Onshape blog, "VEX IQ and VEX V5 parts libraries": https://www.onshape.com/de/blog/vex-iq-vex-v5-parts-libraries

VEX

66. VEX Knowledge Base, "CAD Resources for VEX IQ": https://kb.vex.com/hc/en-us/articles/360044338912-CAD-Resources-for-VEX-IQ ; "CAD Resources for VEX GO": https://kb.vex.com/hc/en-us/articles/360057689112-CAD-Resources-for-VEX-GO
67. VEX, "2x2x2x20 Aluminum U-Channel" (276-7285): https://www.vexrobotics.com/276-7285.html
68. VEX, "#8-32 Standoffs": https://www.vexrobotics.com/standoffs-8-32.html
69. VEX, "All screws": https://www.vexrobotics.com/all-screws.html ; Knowledge Base, "Overview of VEX Screws": https://kb.vex.com/hc/en-us/articles/7107240154260-Overview-of-VEX-Screws
70. VEX, "#8-32 Nuts": https://www.vexrobotics.com/nuts-8-32.html
71. VEX Knowledge Base, "Using V5 Shafts": https://kb.vex.com/hc/en-us/articles/360035591372-Using-V5-Shafts ; VEX, "High Strength hardware": https://www.vexrobotics.com/hs-hardware.html
72. VEX, "V5 Bearings": https://www.vexrobotics.com/v5-bearings.html ; "High Strength Shaft Ball Bearing" (276-8402): https://www.vexrobotics.com/276-8402.html
73. VEX Knowledge Base, "Using V5 Washers and Spacers": https://kb.vex.com/hc/en-us/articles/360035952811-Using-V5-Washers-and-Spacers
74. VEX, "Angles": https://www.vexrobotics.com/angles.html
75. VEX\* (reseller idesignsol.com repeating VEX's catalogue text): C-Channel STEEL 1x5x1x35 (275-1139) https://www.idesignsol.com/C-Channel-STEEL-1x5x1x35-4-pack-275-1139 ; Long Aluminum Structure Kit (275-1410) https://www.idesignsol.com/vex-edr/Long-Aluminum-Structure-Kit-275-1410 ; Plate 15x5 (275-2023) https://www.idesignsol.com/vexrobotics/Plate-15x5-2-pack-275-2023?page=7 ; Hinge (275-1272) https://www.idesignsol.com/Hinge-2-pack-275-1272 ; Aluminum Chassis Kit 25x25 (276-2319) https://idesignsol.com/Aluminum-Chassis-Kit-25x25-276-2319 ; Nylon Spacer Variety Pack (275-1066) https://idesignsol.com/Nylon-Spacer-Variety-Pack-275-1066 ; High Strength Shaft Bearing (276-3521) https://idesignsol.com/High-Strength-Shaft-Bearing-10-Pack-276-3521 ; Bearing Attachment Rivet (276-2215) https://www.idesignsol.com/Bearing-Attachment-Rivet-50-pack-276-2215 ; Screw 8-32 x 0.375 (275-1003) https://idesignsol.com/Screw-8-32-x-0375-100-pack-275-1003

SciForge (internal)

76. `docs/sciforge/parity/joints.md` (its source 3: snap icons), `parity/direct-modify.md` (Align
    A1-A10 and its sources 10 and 15), `parity/components.md` (sources 6, 14, 17),
    `parity/insert-export.md` (Part 2), `MEMORY.md` (session log "Beta 3 list").

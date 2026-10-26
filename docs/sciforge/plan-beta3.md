# Plan: 0.1.0-beta.3 (2026-10-26)

Luca's beta 3 list, as he split it (2026-10-26):

- "joint bug, dragging joints, ghost bodies, and angled fillet will go into a patch" (patch
  0.1.0-beta.2.2, a separate Claude session: `docs/sciforge/dev/briefs/patch-beta2.2.md`).
- "Auto Timeline and Sim is what you will work on. timeline and sim will be beta 3."
- "put the vex stuff in beta 3. youre on max effort so make this count. one shot for beta 3."

So beta 3 is three areas: **Static Stress simulation**, **Auto Timeline** and **VEX
assemblies**. The spec was changed for simulation on 2026-10-26 (outline 7.18: Static Stress
only; flow, thermal, modal, buckling, nonlinear, event and optimization stay out of scope).

## How Fusion's behaviour was found

Two research agents searched Autodesk's help pages, Autodesk Learn and AU material, the
Autodesk and VEX forums and tutorials (the sandbox reads search excerpts only, no web pages):
`docs/sciforge/dev/research/fusion-simulation.md` (the Simulation workspace and the Static
Stress study) and `docs/sciforge/dev/research/fusion-vex-assembly.md` (Align, joint snap
points, inserting many parts, how VEX teams work in Fusion, VEX V5 dimensions). Every fact has
a source tag (Autodesk / Forum / Tutorial / VEX) or is marked G (our guess).

## 1. Static Stress simulation (SIMULATION workspace)

What a person does in Fusion, and so in SciForge: switch the workspace to **Simulation**, make a
**Static Stress** study, check the study materials, add **constraints** (where the part is held)
and **loads** (forces, pressures, gravity...), optionally adjust the **mesh**, **pre-check**,
**solve**, then read the **results**: the safety factor first, then stress and displacement, as
coloured pictures with a legend, an exaggerated bent shape, the places of the minimum and
maximum, probes.

How it works inside: FreeCAD's FEM module, already in every SciForge build (the solver
CalculiX, the mesher Gmsh, and Netgen; checked in the sandbox and in the Windows bundle recipe).
SciForge keeps its own study objects (studies, constraints and loads that point at faces of
the design's bodies) and, at solve time, makes FreeCAD's FEM objects from them in a hidden run,
meshes with Gmsh and solves with CalculiX in the background (the window stays responsive,
Cancel works), then reads the results back. Proven before the builders started: a steel beam
100 x 10 x 10 mm, fixed at one end with 100 N at the other, bends 0.2005 mm (hand calculation
0.2000) with 58.9 MPa (60.0) in about 3 seconds.

| Part | What | Builder |
|---|---|---|
| Engine | studies, constraints and loads of every Static Stress kind, contacts (bonded), mesh settings and local mesh control, solve in the background, results, safety factor, out of date, AI tools, accuracy benchmarks against hand calculations | sim-core |
| SETUP tab | the workspace switch, New Study (Static Stress; Fusion's other types shown greyed), Study Settings, Study Materials, Constraints, Loads, Gravity, Contacts, Mesh (generate, settings, local control), Pre-check, Solve dialog with progress and Cancel, the study tree in the browser, glyphs on the model | sim-ui |
| RESULTS tab | the colour plot (safety factor, stresses, displacements, strain), legend, deformation scale and animation, min / max markers, probes, slice plane, display options, report, Finish Results | sim-results |

## 2. Auto Timeline (AI rebuilds a part with a timeline)

Beyond Fusion (Fusion's Mesh to BRep gives a body without features). A part without a timeline
(an imported STEP file; a simple mesh) becomes the **reference**; SciForge reads it (the base
shape and its profile, holes, pockets, bosses, fillets, chamfers, patterns) and writes a **plan**
of tool calls in Fusion's order; the AI (the built-in chat or a connected app such as Claude
Desktop) follows the plan with SciForge's normal tools, so every step is a real timeline step,
and **compares** with the reference after each step (what material is missing or extra, which
faces are not matched yet) until it matches; then **finish** gives the new body the original's
name and place. A person starts it with a right-click on the body: **Rebuild with Timeline
(AI)...**

| Part | What | Builder |
|---|---|---|
| Recognition | `recognize.describe()`: features and plan from a solid; meshes; a benchmark over 20+ golden models (export to STEP, import, describe, rebuild from the plan, compare) | at-recognize |
| Tools and rebuild | the reference, compare (numbers, words, red / green picture), finish; AI tools start_rebuild, describe_reference, compare_to_reference, finish_rebuild; the recipe and handbook pages an AI reads; the right-click command; the end-to-end proof through the tools and through MCP | at-tools |

## 3. VEX assemblies

Luca: "if there is a version with step files, we should be good. as long as the step files work
and we are able to import large amounts of items into an assembly, thats all we need", and
Align / Joint must snap to "center points on squares and such" (VEX metal has square holes on a
1/2 inch grid).

| Part | What | Builder |
|---|---|---|
| Snaps | the centre of any closed hole outline (square, hexagonal, slot...) and of a hole's walls as a snap point for Joint, Joint Origin, As-Built Joint and Align | vex |
| Many parts | insert many STEP files at once, insert the same part again as a linked copy, the Data Panel for a folder of STEP parts | vex |
| Big assemblies | measured speed with hundreds of parts (insert, browser, timeline, selection, joints, save / open) and the slow spots fixed | vex |
| Proof | VEX-like parts made from published dimensions (our own geometry), a small drivetrain assembled with Align and joints at square holes | vex |

## Schedule

Six builders work at the same time in their own worktrees (rules:
`docs/sciforge/dev/briefs/beta3-common.md`), then an independent QA agent per area, then journey
testers who use the three areas together like a person, then integration on `develop`, all tests,
the docs, the CHANGELOG and the version 0.1.0-beta.3. A release needs Luca's green light.

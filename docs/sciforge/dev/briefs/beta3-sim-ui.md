You are building one feature area of SciForge, a FreeCAD 1.1.4 fork that must behave like
Autodesk Fusion. The owner, Luca, is a beginner who only tests; he wants the finished product.
Read `docs/sciforge/dev/briefs/beta3-common.md` first (and everything it lists).

## Your area: the SIMULATION workspace and its SETUP tab (builder sim-ui, branch `sf/sim-ui`)

Luca asked for simulation ("stress and flow ... it would be very useful"), then "stress-only sim
is fine". Outline 7.18 is the spec; Fusion's behaviour with sources is
`docs/sciforge/dev/research/fusion-simulation.md` (read all of it: it is the source of truth for
every dialog, option, default and the browser). The engine exists and works (read
`sciforge/simulation.py` and `simulation_core.py` completely: studies, items, materials,
pre-check, `Job` with poll / cancel, results summary, out of date); builder sim-core extends it
at the same time (more constraint and load kinds, mesh-only runs, local mesh control, AI tools):
`git merge sf/sim-core` whenever you need its newer engine. Builder sim-results makes the RESULTS
tab (the colour plot, legend, deformation, probes, report); you hand over to it when a solve ends
(call `simulation_results_ui.show(study)` if it exists, else switch to the RESULTS tab: agree on
this through your session logs; sim-results owns that module).

Research decisions to follow: the SETUP groups and every command's status (enabled / greyed with
its sentence) are in research 9.2 (the scaffold's ribbon follows it); Fusion solves in the cloud,
SciForge on this computer (the Solve dialog has no cloud choice and says where it solves);
Pin's default leaves tangential free; a force on several faces is shared by area unless Force
Per Entity; gravity is off by default; contacts are bonded automatically (0.1 mm); Pre-check is a
traffic light (green / yellow / red, research 3.9) with the sentences of research 9.6.

### What to build
1. **The workspace switch**: the scaffold has `simulation_ui.enter_workspace()` /
   `leave_workspace()`, `RibbonWidget.set_simulation_mode(on, tab)` and the workspace menu entry
   (Design / Simulation / Drawing). Make it Fusion's: what the research says happens to the
   design's tabs, the timeline, the browser, the selection, a sketch or dialog that is open, a
   document switch (each document remembers its workspace), closing the document, Esc. Entering
   with no study: Fusion's New Study dialog (research); with studies: the last active one.
2. **New Simulation Study**: Fusion's dialog (research: tiles or list), Static Stress available,
   every other study type shown greyed with "not in SciForge yet" (`simulation_core.STUDY_TYPES`).
   Study Settings (every setting the research lists for Static Stress: general, mesh, adaptive
   refinement if sim-core builds it, contacts, gravity...).
3. **The SETUP tab** (the scaffold put Fusion's groups in `ribbon_config.py` with every command
   `None` and an `# owner: sim-ui` comment; wire yours, keep the order): Study Materials (the
   table of bodies with their study material, "Same as Model" default, safety factor basis, the
   properties shown; sentences when FreeCAD's card lacked a value and SciForge filled it),
   Structural Constraints (one dialog, the type dropdown, picks with the selection filter of the
   type, every option of every type sim-core builds; types not built shown greyed with a
   sentence), Structural Loads (likewise: Force with Normal / Vector direction and flip,
   per-entity, Pressure, Moment, Bearing, Remote Force...; live glyph preview while picking),
   Gravity (Fusion's toggle and direction, research), Contacts (Fusion's automatic contacts
   result, bonded; the other types greyed unless sim-core builds them), Mesh (Generate Mesh shows
   the mesh on the model, Mesh Settings, Local Mesh Control), Pre-check (Fusion's icon states and
   a list of the sentences), Solve (Fusion's Solve dialog: progress by stage, elapsed time,
   Cancel; runs `simulation.Job` polled by a QTimer; the window stays usable; when done, the
   results show: hand over to sim-results), Manage / Inspect / Select as the research says.
4. **Glyphs** (`simulation_glyphs.py`): constraints and loads drawn on the model like Fusion's
   (a padlock / hatch for Fixed, arrows for Force and Pressure along their direction, an arc
   arrow for Moment, a pin for Pin...), scaled to the screen, coloured, hidden outside the
   workspace, display-only (Coin nodes, never document properties).
5. **The browser** (`simulation_browser.py` + the smallest hooks in `browser_core.py` /
   `browser_ui.py`): in the SIMULATION workspace the browser shows Fusion's study tree (study,
   materials, load case with constraints and loads, contacts, mesh, results...: research),
   with the right-click actions (Edit, Suppress, Delete, Rename, Clone Study... what the engine
   supports), double-click edits, the out-of-date mark when the design changed after a solve,
   and the design's folders back in DESIGN. Studies, items and runs never show in DESIGN's
   folders or the timeline (they are hidden from the timeline already; check every path).
6. **Undo**: adding / editing / deleting constraints, loads, settings and materials are undo
   steps; a solve is not (check FreeCAD's transactions: the run's objects must not land in an
   open transaction); undoing while results show.
7. Icons for every command (`icons_simulation.py`, original artwork, style of the others).

Scenarios `sim_*.py` (8+ paths with real clicks): enter the workspace, New Study, a bracket
fixed at its holes with a force on its arm, Study Materials changed, Pre-check, Solve (wait for
the job), results handed over; Esc / Cancel in each dialog; a refusal (no constraint: the
pre-check's sentence); edit a load from the browser and solve again; suppress / delete; two
bodies glued; save / reopen in the workspace; leave to DESIGN and come back (tabs, timeline,
browser); undo / redo of setup changes.

Spec: `docs/sciforge/parity/simulation.md` section "Setup" (behaviour table with sources, Known
gaps). Session log: `docs/sciforge/sessions/beta3-sim-ui.md`. Report as beta3-common says.

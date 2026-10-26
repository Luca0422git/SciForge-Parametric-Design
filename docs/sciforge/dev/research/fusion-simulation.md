# Fusion SIMULATION workspace, Static Stress study: behaviour spec for SciForge

Black-box documentation research, done 2026-10-26, for outline §7.18 (Simulation: Static Stress
only). It describes Fusion as documented in 2022-2026, with older behaviour marked. Copy the
behaviour, never Autodesk's icons, artwork, help text or code. Fusion's command names, dialog labels
and defaults are recorded below as facts, so builders know what a Fusion user expects. SciForge
uses its own wording and its own icons.

## How to read this file

**Source tags.** Each fact carries one of these tags. The numbers point to the reference list at
the end.

- **A[n]**: Autodesk. This covers Fusion help pages (help.autodesk.com), Autodesk Learn, Autodesk
  University (AU) handouts and the Fusion blog. A few A entries are help for other Autodesk
  products (Inventor, Simulation Mechanical). Those are marked "(Inventor)" or "(Sim Mech)" and
  are hints only.
- **F[n]**: Autodesk Community forum answers, often written by Autodesk staff.
- **T[n]**: third-party tutorials and Fusion study reports that users exported and posted online.
- **G**: my guess where the sources are silent. The Notes column says what it is based on.
  - **G (mem)** means my memory of the Fusion interface from before this session. It was not
    checked here.
  - A G row is a **recommended SciForge choice**, not a verified Fusion fact.

**Research limits.**

- WebFetch cannot reach any host from this sandbox, so every fact comes from search-engine
  excerpts of the cited pages. I used 61 searches.
- Many help pages appeared only as fragments. Because of that, these are **not confirmed**:
  - the left-to-right order of the toolbar groups;
  - most dialog defaults (default force magnitude, most mesh values);
  - the safety-factor colours.
- §10 lists what only a screenshot from Luca's Fusion can settle.

**Words used** (plain language, for Luca):

| Word | Meaning |
|---|---|
| study | One simulation setup: the materials, supports, loads, contacts and mesh, plus its results. A design can hold many studies. |
| constraint | A support. It stops part of the model moving, for example a face bolted to a wall. |
| load | A push, pull, twist or pressure on the model, or its own weight (gravity). |
| contact | How two touching bodies are joined. **Bonded** means glued. |
| mesh | The model cut into many small pyramids (tetrahedra, called "elements"). The solver computes on these. |
| load case | One set of loads and constraints. One study can hold several. |
| von Mises stress | One number per point that sums up how hard the material is being worked. |
| safety factor | Material strength ÷ von Mises stress. Below 1 means the part would bend permanently. |

**Fusion versions.** Where old and new behaviour differ, both are given:

| When | Change | Src |
|---|---|---|
| Sep 2017 | Simulation models and Simplify (first called "Edit Simulation Model"). Removing or suppressing parts for a study became timeline features of a simulation model. | F[96] A[72] |
| Sep 2022 | **Local solving was removed** for Static Stress, Modal, Thermal and Thermal Stress, so solving is cloud only. With a subscription, Linear Static Stress cloud solves are free. Other study types cost tokens. | F[84] F[103] A[43] |
| 2024-2025 | Static Stress results move to a browser-based **"online viewer"** inside the canvas. It has a result browser, a legend with range and threshold sliders, and an animation bar. It was a Preview Feature in May 2025. | A[50] A[52] F[86] |
| 2025 | "Guided" safety-factor results: *very strong / meets target / not strong enough*. Results Details shows interpretation messages. | A[71] A[54] F[88] |

---

## Summary

- **Getting in.** Simulation is its own workspace, picked from the workspace drop-down. The first
  visit opens the **New Study** dialog: study-type pictures with a description. Static Stress is
  one of about ten types (A[71] T[104] A[79]).
- **The simulation model.** A study works on a **simulation model**. This is a copy of the design
  that follows design edits, and the **Simplify** environment can slim it down without touching
  the design (A[72] F[96]).
  - If the design or simulation model changes after a solve, the results are marked
    **out of date** and must be solved again (F[85] A[65]).
- **SETUP tab.** In workflow order its groups are STUDY, SIMPLIFY, MATERIALS, CONSTRAINTS, LOADS,
  CONTACTS, DISPLAY, SOLVE (Pre-check, Solve, Generate Mesh) and MANAGE (Settings, Local Mesh
  Control, Load Case Attributes). The exact left-to-right order is G (A[4] A[38] A[49]).
- **Static Stress setup** has five parts:
  - Study Materials: default "(Same as Model)", with the safety factor based on yield strength by
    default and ultimate tensile strength as the other choice (A[9] A[30]).
  - Structural Constraints: Fixed, Pin, Frictionless and Prescribed Displacement (A[7] A[11]).
  - Structural Loads: Force, Pressure, Moment, Bearing Load, Remote Force or Moment, and
    Hydrostatic Pressure (A[18] A[3]).
  - Global loads (gravity, which is off by default) and point masses (A[24]-A[27]).
  - Contacts: automatic **Bonded** contacts are made at solve time (A[33]).
- **Key defaults.**
  - Fixed holds all three directions (A[13]).
  - Pin holds Radial and Axial and leaves Tangential free (A[14]).
  - A force on several faces is **shared by area** unless "Force Per Entity" is ticked (A[19]).
- **Mesh.** Parabolic (10-node) tetrahedra by default, with an average element size of 10 % of
  model size (exported reports, T[107]). There is also local mesh control and adaptive refinement,
  which is off by default. If no mesh was made, it is built automatically at solve time (A[37]
  A[38] A[39]).
- **Pre-check** works like a traffic light: green means ready, yellow means caution, red means it
  cannot solve (A[42] F[92]).
  - A model that is not held enough (**rigid body motion**) is the classic failure.
  - "Remove rigid body modes" is only for loads that balance each other (A[40] A[41]).
- **Solving.** Fusion **no longer solves on the user's computer** (cloud only since Sep 2022). A
  Job Status dialog shows progress and offers Cancel during some phases (A[43] A[44] F[84]).
  SciForge's local solve is a deliberate, better difference.
- **Results** open on **Safety Factor**, with min and max tags (A[80] A[71]).
  - The result types are Safety Factor, Stress (von Mises, principal and components),
    Displacement, Reaction Force or Moment, Strain and Contact Pressure (A[48] A[49]).
  - Safety factor is shown capped at **15** (F[89]).
  - The deformation is exaggerated by default ("Adjusted" draws the largest movement as 5 % of
    the model size), with ×0.5, ×2, ×5, Actual and Undeformed choices (A[51]).
  - The other tools are Animate, surface probes, slice planes, Compare (up to 4 studies) and an
    HTML Report (A[52] A[55] A[56] A[61] A[62]).
- **Fusion's own assumptions.** Small deflections, linear elastic material, loads that do not
  change, and no inertia. Safety factor = yield ÷ von Mises (A[1] A[30]).
- **Biggest open item.** Fusion is moving Static Stress results to the new online viewer, with
  threshold sliders, a bottom animation bar and guided "meets target" text. Which viewer Luca's
  Fusion shows decides how SciForge's RESULTS should look (§10, question 1).

---

## 1. Entering and leaving the Simulation workspace

| # | Behaviour | Source | Notes |
|---|---|---|---|
| 1.1 | The workspace drop-down at the left end of the toolbar (it reads DESIGN) lists **Simulation**. Choosing it switches the toolbar, browser and canvas of the **same** document. | A[71] ("switch ... using the dropdown menu") | The document tab stays. Each open document keeps its own workspace (G (mem)). |
| 1.2 | The first time a design enters Simulation with no study, the **New Study** dialog opens by itself. | T[104] | If studies exist, Fusion opens on the active study (G). |
| 1.3 | The toolbar shows the **SETUP** tab, which "holds all the commands to set up and run a study", and the **RESULTS** tab once results exist. Design's SOLID, SURFACE and other tabs are not shown. | A[4] A[49]; G (mem) for the hidden tabs | SETUP commands change with the study type (A[4]). |
| 1.4 | **Timeline.** The Simulation workspace shows no design timeline (G (mem)). The Simplify environment has its own timeline of simplify features; since Sep 2017, removing a component is recorded there. A 2024 forum post complains that the design history is not visible in Simplify. | F[96] F[102] | SciForge: no timeline in Simulation. |
| 1.5 | **Browser.** The design browser is replaced by the simulation browser: simulation models and the study tree (§4). | A[45] A[28] | |
| 1.6 | **Simulation model.** A study works on a simulation model, a copy of the design. **New Simulation Model** (in Simplify) makes a fresh copy. **Clone Simulation Model** copies the current one with its removed parts. After a new model is made, going back to Simulation prompts for a new study on it. | F[96] A[74] | Fusion's default name is "Simulation Model 1" (G (mem)). |
| 1.7 | **Simplify** changes stay inside that simulation model: "the design model and all other simulation models are undisturbed". Edits made later to the design still flow into the simulation models. | A[63] A[72] | Used for removing small fillets and holes, and for "what if" changes. |
| 1.8 | **Leaving.** Pick Design in the same drop-down. Studies and results stay in the document. | A[71] A[65] | There is no "Finish Simulation" button (G (mem)). |
| 1.9 | **Design changed after a solve.** Results belong to a design version. If the design or simulation model changed after the solve, an **out-of-date** message appears, and the fix is to solve again. | F[85] (Autodesk QA engineer) A[65] | The same happens when the configuration a study belongs to is changed in Design or Simplify (A[65]). |
| 1.10 | **Configurations.** A study and its results stay tied to the configuration they were made for. | A[65] | Later for SciForge. |
| 1.11 | **Loads or constraints whose faces were removed.** The **Load Case Attributes** dialog lists every load and constraint with its location, magnitude and direction. A status icon shows whether each one is placed correctly. | A[28] | A warning icon on the browser item is G. |

---

## 2. New Simulation Study dialog and Study Settings

### 2.1 Opening and layout

| Behaviour | Source | Notes |
|---|---|---|
| Opened with SETUP > STUDY > **New Simulation Study**. It also opens automatically on the first visit. | A[65] T[104] | |
| A list of study types, each with a picture. Clicking a type shows a short description of what it does. | A[79] (AU 2021: each type "shows a little bit about what it is about") | Tiles or list layout: §10 Q3. |
| The selected type is shown as a **large thumbnail**. A **Settings** (gear) icon in its upper-right corner opens Study Settings (§2.3) before the study exists. | A[6] | T[106] (2016) shows an expandable settings section in the same window. |
| A "Help Me Choose a Study Type" link. | A[79] (2021) | Whether it is still there now is unknown. |
| The **Create Study** button makes the study and enters its setup. | A[79] | |
| A new study gets a default name such as "Study 1 - Static Stress", which can be renamed in the browser. | G (mem) | |

### 2.2 Study types Fusion lists

The order is G. It follows the older 8-type list in T[105], with the newer types appended.

| Study type | What it is | Fusion cost | SciForge |
|---|---|---|---|
| **Static Stress** | Linear: displacement, stress, safety factor and reactions under constant loads (A[2]) | Free on the cloud with a subscription (A[43]) | **Build** |
| Modal Frequencies | Vibration modes and frequencies (A[2]) | Tokens | Greyed |
| Thermal | Temperatures | Tokens | Greyed |
| Thermal Stress | Temperatures and stress, with a stress-free reference temperature in settings | Tokens | Greyed |
| Structural Buckling | Buckling modes and load multipliers | Tokens | Greyed |
| Nonlinear Static Stress | Large deformation, changing contact, nonlinear material (A[1]) | Tokens | Greyed |
| Event Simulation (dynamic) | Impact and other time-dependent events | Tokens | Greyed |
| Quasi-static Event Simulation | Event-style solver used for slow, large-deformation loading | Tokens | Greyed |
| Shape Optimization | Removes material where it is not needed | Tokens | Greyed |
| Electronics Cooling | Board temperatures with airflow | Tokens | Greyed |
| Injection Molding Simulation | Plastic fill | Tokens | Greyed |

Sources: A[2], A[43] and A[50] (which lists the study types that use the online viewer), plus
A[73] and A[70] (the Simulation Extension).

**Old dialog** (about 2019-2021, T[105]): Static Stress, Modal Frequencies, Thermal, Thermal
Stress, Structural Buckling, Nonlinear Static Stress, Event Simulation ("in preview") and Shape
Optimization. The top four could run locally or on the cloud; the bottom four were cloud only and
cost cloud credits.

### 2.3 Study Settings (one dialog with tabs)

- **Opening it.** Use the gear icon in the New Study dialog. Later, use **MANAGE > Settings**, from
  the RESULTS tab as well (A[6]); SETUP > MANAGE > Settings is G (mem).
- **Tabs.** General opens first (A[6]). Adaptive refinement is "set in the Settings dialog"
  (A[39]), and there is a Mesh tab (A[4] A[9]). Whether a **Contacts** tab exists for Static
  Stress is **not confirmed** (§10 Q4).

| Tab | Field | Default | Source | Notes |
|---|---|---|---|---|
| General | **Remove rigid body modes** (checkbox) | Off | A[6] ("make sure Remove rigid body modes is not activated") A[40] | Valid only for a model with no constraints, or a constrained model whose loads balance exactly. Otherwise the reaction forces are wrong (A[40]). |
| Mesh | **Average Element Size (% of model size)** | **10** | T[107] (several exported reports) | "Model size": Inventor uses "fraction of longest model dimension" (A[81]). Using the bounding-box diagonal is G. |
| Mesh | **Scale Mesh Size Per Part** (checkbox) | Off | G (mem) | The older label was "Use part based measure for assembly mesh": each part is meshed relative to its own size (A[74]). |
| Mesh | Average Element Size (absolute value) | empty | G (mem) | An alternative to the % value. |
| Mesh | **Element Order**: Parabolic / Linear | **Parabolic** | A[37] T[107] | Parabolic = 10-node tetrahedra (A[37]). |
| Mesh | **Create Curved Mesh Elements** | On | A[37] (exists, parabolic only); default G (mem) | |
| Mesh | **Max. Turn Angle on Curves** (deg) | 60 | G (Inventor default 60, recommended 30-60, A[81]) | Range 1-90 (Inventor). A Fusion tutorial sets 30 for round areas (A[74]). |
| Mesh | **Max. Adjacent Mesh Size Ratio** | 1.5 | G (Inventor "grading factor" 1.5, range 1-10, A[81]) | "Transition rate" between small and large elements (A[37]). |
| Mesh | **Max. Aspect Ratio** | 10 | G (mem) | Exists: A[37] A[74]. |
| Mesh | **Minimum Element Size (% of average size)** | 20 | G (Inventor minimum element size 0.2) | Reports call it "Minimal Element Size" (G (mem)). |
| Adaptive Mesh Refinement | Level: **None** / Low / Medium / High / Custom | **None** | A[39] | Older UI: MANAGE > Adaptive Mesh Refinement, "low to high" (A[76]). |
| Adaptive Mesh Refinement | Number of refinements | unknown | A[39] | Maximum number of refine-and-solve passes. It wins over the tolerance. Good results usually come in under 8 passes. |
| Adaptive Mesh Refinement | Results convergence tolerance (%) | unknown | A[39] | Stops when the change between passes is at or below this. |
| Adaptive Mesh Refinement | Portion of elements to refine (%) | unknown | A[39] | For example, 5 % refines the worst 5 % of elements by the chosen result. |
| Adaptive Mesh Refinement | Result used to judge convergence | unknown | A[76] (convergence of von Mises, displacement, 1st and 3rd principal) | 2D convergence plots after the solve (A[71]). |
| Contacts (if it exists) | Type and tolerance of the automatic contacts made at solve time | Bonded, 0.1 mm | A[33] (Bonded at solve time); T[106] T[107] (0.1 mm) | Where this is set is G. |

---

## 3. The SETUP tab

### 3.1 Groups and their commands

A[4] lists the groups in workflow order. **The left-to-right order below is G (mem)**; the
members are sourced.

| Order (G) | Group | Commands (Static Stress) | Source |
|---|---|---|---|
| 1 | STUDY | New Simulation Study. Clone Study is on the browser (§4). | A[65] A[46] |
| 2 | SIMPLIFY | Simplify (opens the Simplify environment) | A[4] A[63] |
| 3 | MATERIALS | Study Materials; Manage Physical Materials | A[29] A[4]; the second label is G (mem) |
| 4 | CONSTRAINTS | Structural Constraints | A[7] |
| 5 | LOADS | Structural Loads; Linear Global Load; Angular Global Load; Toggle Gravity On/Off; Point Mass (Auto); Point Mass (Manual) | A[18] A[24] A[25] A[26] A[27]; Manual is G (mem) |
| 6 | CONTACTS | Automatic Contacts; Manual Contacts; Contact Manager. Bolt Connector and Rigid Body Connector: G (mem). | A[34] A[33] A[35]; A[76] advises "connectors for screws and bolts" |
| 7 | DISPLAY | DOF View (shows which bodies are still free); glyph visibility (G) | F[92] |
| 8 | SOLVE | Pre-check; Solve; Generate Mesh. Job Status: G (mem). | A[42] A[43] A[38] |
| 9 | MANAGE | Settings; Local Mesh Control; Load Case Attributes. Older UI: Adaptive Mesh Refinement. | A[6] A[38] A[49] A[76] |
| 10 | INSPECT | Measure and the rest, as in Design | G |
| 11 | SELECT | Selection tools | G |

G (mem): MANAGE sits just before SOLVE, with INSPECT and SELECT last, as in other Fusion
workspaces. §10 Q2 asks for a screenshot.

### 3.2 STUDY and SIMPLIFY

| Behaviour | Source | Notes |
|---|---|---|
| New Simulation Study opens §2. | A[65] | |
| **Simplify** opens a contextual environment with its own toolbar. Its changes are confined to the simulation model being edited. | A[4] A[63] | |
| Simplify commands: | | |
| • **Remove Features** picks small features automatically by relative size: fillets, holes, chamfers, extrudes and revolves. A count shows how many were picked by hand, to remove or to keep. Esc restores the geometry. | A[63] | |
| • **Remove Faces** also removes the neighbouring faces that must go, so the solid heals. | A[63] | |
| • **Replace with Primitives** swaps bodies for a box, cylinder or sphere. It starts sized from a bounding shape, and the original bodies are removed. | A[63] | |
| • **Remove** bodies or components, which also suppresses them for the study. | A[63] F[96] | |
| • New Simulation Model and Clone Simulation Model. | F[96] A[74] | |
| • Finish Simplify, which returns to SETUP. | G (mem) | |
| SciForge, first release: Simplify is **greyed**. The study uses the live design, and a body can be excluded from a study (§9). | G | |

### 3.3 MATERIALS

**Study Materials** (SETUP > MATERIALS > Study Materials, A[29])

| Behaviour | Source | Notes |
|---|---|---|
| A table with one row per body or component. | A[29] A[9]; T[107] | Fusion rows are per component, but exported reports list bodies (for example "Body1"). G: SciForge uses one row per body. |
| Column **Study Material**: a drop-down with the default **"(Same as Model)"**, which means the body's physical material from Design. | A[9] ("The default Study Material setting is (Same as Model)") | |
| Picking another material changes it **for this study only**. Tutorials do this to compare materials (clone the study, change the material, solve again). | A[10]; "study only" is G, consistent with A[63] | |
| Column **Safety Factor**: **Yield Strength** (default) or **Ultimate Tensile Strength**, chosen per row. | A[30] A[75] T[107] (report: "Body1 / Steel / Yield Strength") | §5.4 gives the formulas. |
| Double-clicking a row shows the properties that matter for simulation, such as Young's modulus and yield strength. | A[29] | |
| Properties Static Stress uses: | | |
| • Young's modulus. | A[29] | |
| • Poisson's ratio. | G | Any 3D elastic solve needs it. |
| • Density, for gravity and global loads. | A[24] A[26] | |
| • Yield strength. | A[29] A[30] | |
| • Ultimate tensile strength, if chosen for the safety factor. | A[30] | |
| A material marked as meant for nonlinear analysis triggers a pre-check notice. | F[95] | |
| **Manage Physical Materials** opens the material library: pick, create and edit materials. | A[4] ("select materials, create new material libraries, and modify material properties") | |

### 3.4 CONSTRAINTS

**Structural Constraints** dialog (SETUP > CONSTRAINTS > Structural Constraints, A[7])

| Behaviour | Source | Notes |
|---|---|---|
| One dialog. Its **Type** drop-down switches between **Fixed, Pin, Frictionless, Prescribed Displacement**. | A[7] A[3] | |
| A **Remote** constraint also exists in Fusion's help. | A[17] | Details were not found. Later for SciForge. |
| Purpose: stop rigid body motion. Either fix one face completely, or combine partial constraints on faces, edges and vertices. | A[11] | |
| Constraints do **not** join parts; touching parts need contacts. | A[12] | |
| Directions are the design's global X, Y and Z. | G | No custom frame was found. |

| Type | What can be picked | Options and defaults | Source |
|---|---|---|---|
| **Fixed** | Faces, edges, vertices | Three toggle buttons, **Ux, Uy, Uz**, all **on** by default. Turning some off gives a partial constraint, such as a roller. | A[13] A[11] |
| **Pin** | **Cylindrical faces only** | Toggles **Radial, Axial, Tangential**. Default: **Radial + Axial on, Tangential off**, so the part is free to turn. | A[14]. Caveat from Autodesk staff (F[91]): Radial fixed holds **every** node of the hole, so the pin also "pulls". Split the face or use a Bearing Load instead. |
| **Frictionless** | Faces | No options. Blocks movement normal to the face; the face may slide and rotate in its own plane. | A[15] |
| **Prescribed Displacement** | Faces, edges, vertices (G: as Fixed) | Choose 1 to 3 directions (X, Y, Z) and type **Ux, Uy, Uz** (lengths). Used when the deflection is known and the load is not. | A[16] |

### 3.5 LOADS

**Structural Loads** dialog (SETUP > LOADS > Structural Loads). Common fields:

| Field | Behaviour | Source |
|---|---|---|
| **Type** | Force, Pressure, Moment, Bearing Load, Remote Force, Hydrostatic Pressure. Remote Moment also exists. | A[18] A[3] A[19]-A[23] |
| **Direction Type** | Force: Normal / Angle / Vector. Moment: Normal / Angle (delta) / Vectors (x, y, z). Bearing Load: Angle (delta) / Vectors / Reference. | A[18] |
| **Flip Direction** | Reverses the load. | A[18] |
| **Magnitude** | A value with a unit override in the field. | A[23] |
| **Per Entity** | "Force Per Entity" and "Moment Per Entity" (§ per type below). | A[19] A[18] |
| **Limit Target** (Force) | Applies the force only on a circle inside the face. Needs Direction Type Angle or Vector. | A[18] A[19] |

| Load | Targets | Behaviour and options | Source |
|---|---|---|---|
| **Force** | Faces, edges, vertices | Details below this table. | A[19] A[18] |
| **Pressure** | Faces | Always normal to the faces. Positive pushes into the face (G). | A[20] |
| **Moment** | Faces | **Normal** (axis normal to the face), **Angle (delta)** or **Vectors** (Mx, My, Mz), plus Flip. With several faces the sources **conflict**: the concept page says the moment is shared ("prorated") among the faces, while a load page says "Moment Per Entity" appears, switched on and greyed, so each face gets the full value. | A[21] vs A[18]; §10 Q8 |
| **Bearing Load** | Cylindrical faces | A parabolic distribution. It always pushes into the face and never pulls (tension). Direction by Angle (delta), Vectors (Fx, Fy, Fz) or **Reference**: radial to the cylinder, refined by a flat face's normal or a straight edge. The magnitude is the total (G, as in Sim Mech A[83]). | A[22] A[18] |
| **Remote Force** | Target faces | A force acting from a point in space, not on the model, and carried to the target faces. Fields: direction, magnitude, and the point's X, Y, Z. Example: wind on a mast. | A[23] |
| **Remote Moment** | Target faces | As Remote Force but a moment: Normal / Angle / Vectors, plus the X, Y, Z of the point. | A[18] |
| **Hydrostatic Pressure** | Faces | Pressure that grows linearly with fluid depth. Its fields (fluid density, surface level, direction) are G. | A[3] |

**Force in detail** (A[19] A[18]):

- By default the force is normal to a picked planar face (A[19]).
- **Angle** gives X, Y, Z angles relative to the first picked face or another reference (A[18],
  by analogy with Moment). **Vector** gives Fx, Fy, Fz in global axes.
- On several faces or edges, the **total** is shared by face area or edge length ("prorated").
- **Force Per Entity** puts the full value on each entity. Autodesk's example: 3 faces at 100 N
  give 300 N in total.
- Vertices each get an equal share.
- On faces, the force becomes an equivalent pressure.
- **Default magnitude: not found** (§10 Q5). Autodesk's own example uses 100 N.

**Global loads, gravity and point masses**

| Command | Behaviour | Source |
|---|---|---|
| **Linear Global Load** | An acceleration of the whole model. The force is proportional to each material's mass, and a body with zero density gets none. Help: "only one global load can be applied per study". | A[24] |
| **Angular Global Load** | Rotation speed or acceleration. The axis is set by **Normal** (picked entities) or **Vectors** (x, y, z) in global axes. Listed for Static Stress, Nonlinear Static and Buckling. | A[25] |
| **Gravity** | Details below this table. | A[26] A[69] A[28] |
| **Point Mass (Auto)** | Replaces the picked bodies with a point mass at their centre of mass, attached to picked faces. It weighs something only when gravity is on. | A[27] |
| **Point Mass (Manual)** | A typed mass and location. | G (mem) |

**Gravity in detail** (A[26] A[69] A[28]):

- It is a global load on all bodies and point masses, and needs density above 0.
- It is **off** in a new structural study.
- The LOADS menu entry reads **Toggle Gravity On** or **Toggle Gravity Off**.
- In the browser it sits at Load Case > Loads > **Gravity**. Hovering shows an edit icon, which
  opens **Edit Gravity**. The direction is set by **Normal** (pick a face, edge or vertex; Flip)
  or by **Angles** (X, Y, Z).
- The default direction comes from Preferences, "Default modeling orientation" (Y-up or Z-up).
- The magnitude is standard gravity: 9.807 m/s² is G.

### 3.6 CONTACTS

| Behaviour | Source | Notes |
|---|---|---|
| **Automatic contacts are generated by default during the solve, as Bonded.** | A[33] | So a two-body study works with no contact step. |
| **Automatic Contacts** command: a dialog with **Contact Detection Tolerance** and a **Generate** button. Bodies farther apart than the tolerance get no contact. | A[34] A[33] | Detection runs at the start of the analysis, before meshing (A[34]). |
| Default tolerance **0.1 mm**. | T[106] T[107] | It appears in exported reports. The exact current value is G. |
| **Manual Contacts**: 6 types: **Bonded, Offset Bonded, Separation, Sliding, Rough, No Contact**. | A[33] | The 2016 list was Bonded, Separation (no sliding), Sliding (no separation), Separation + Sliding (T[106]). |
| Penetration Type (manual contacts): **Symmetric** (default; prevents the parts passing through each other, slowest) or **Unsymmetric**. Unsymmetric only checks nodes of the secondary body against faces of the primary body. | A[36] | |
| **Contact Manager**: a table of contact pairs, shown **by Bodies** or **by Contact Set** (the default). It opens from CONTACTS or the browser Contacts node, and the type can be changed per pair. | A[35] | |
| Bonded: the pair can neither separate nor slide relative to each other. | A[33] (Inventor Nastran wording) | |
| Separation, Sliding and Rough make the solve nonlinear. | G | CalculiX contact is a nonlinear analysis. |

### 3.7 Mesh

| Behaviour | Source | Notes |
|---|---|---|
| The model is **meshed automatically at solve time**. **Generate Mesh** (SOLVE group, or right-click the browser **Mesh** node) builds it first, to preview and adjust it. | A[38] A[37] A[28] | |
| Elements are tetrahedra: **Linear** (corner nodes only) or **Parabolic** (an extra node at each edge middle, 10 nodes). Curved elements are possible only with Parabolic. | A[37] | |
| The global settings are in §2.3 (Settings > Mesh). | A[37] T[107] | |
| Mesh quality advice: control the aspect ratio, the adjacent size ratio and the turn angle on curves; refine locally where stress matters; refine thin parts locally rather than globally. | A[37] A[38] | |
| **Local Mesh Control** (SETUP > MANAGE): details below this table. | A[38] | |
| **Adaptive Mesh Refinement**: in Settings (§2.3), **None** by default. It runs refine-and-solve passes and gives 2D convergence plots. | A[39] A[71] A[76] | |
| Forum tip: a 1 % average size with refinement off solved a thin part quickly. | F[97] | |

**Local Mesh Control in detail** (A[38]):

- Pick faces and/or edges; a **Body Selection** button picks a whole body.
- **One size per control**: for different sizes, make more controls.
- Set the size with a slider from **Fine** to **Coarse**, or a typed **Length**. The Length starts
  at the average global element size.
- Green dots on the picked edges preview where the nodes will go.
- The size blends gradually into the global size.
- After OK, the mesh must be generated again.

### 3.8 DISPLAY

| Behaviour | Source | Notes |
|---|---|---|
| **DOF View** shows which bodies can still move. Autodesk staff recommend it for checking constraints. | F[92] | A good SciForge "should". |
| Showing or hiding load and constraint glyphs, and the mesh. | G (mem) | |

### 3.9 Pre-check

| Behaviour | Source | Notes |
|---|---|---|
| SETUP > SOLVE > **Pre-check** checks the study before solving. | A[42] | |
| The toolbar icon shows the study state like a traffic light: **green check** = ready; **yellow** = possible problems ("proceed with caution"), but it can still solve; **red** = "cannot succeed". | A[42] F[92] (Autodesk staff) | |
| Clicking it lists messages saying what may be missing, usually constraints, loads or contacts. | A[42] | |
| Message examples seen on the forum: | | |
| • Unconstrained bodies. | F[94] | |
| • The same entity constrained twice ("references same entity"). | F[93] | |
| • A material intended for nonlinear analysis. | F[95] | |
| • Bolt-hole geometry shared with a contact. | F[92] | |
| Pre-check can give false alarms. | F[92] | |
| **Not held enough (rigid body motion)**: in 3D at least **six** independent degrees of freedom must be held. | A[41] | |
| The escape hatch, Remove rigid body modes, is valid only when the forces and moments sum to zero. | A[40] F[98] | |
| **Missing material property**: no message text was found. | G | SciForge: red, with the property named (§9). |

### 3.10 Solve and Job Status

| Behaviour | Source | Notes |
|---|---|---|
| SETUP > SOLVE > **Solve** opens the Solve dialog. It holds the list of studies, a **Show** list (for example "Token costs & balances", with **Required / Available / Will remain**), and a button that names the count, such as "**Solve 1 Study**". | A[43] | Per-study checkboxes: G (mem). |
| A **Repair** button appears next to a study with serious input errors. | A[42] | |
| Fusion solves only on Autodesk's cloud (since Sep 2022). Linear Static Stress is included in the subscription; other types cost tokens. | A[43] F[84] | |
| Before Sep 2022 the four basic types could be solved **locally** (on the user's computer) or on the **cloud**. | T[105] F[84] F[97] | This is what SciForge brings back. |
| **Job Status** opens automatically when a solve starts. | A[44] | |
| Job Status, **Simulation** tab: running, completed and failed solves, each with a **status** and an **action** column. Expanding a running row shows per-phase progress. | A[44] | The phase names are G. |
| **Cancel** is offered only during some phases. | A[44] | SciForge offers Cancel always (outline 7.18). |
| Fusion can be closed during a cloud solve; results download later. | A[44] | |
| When results are ready they open in the RESULTS tab (§5). | A[8]; the auto-switch is G (mem) | |

### 3.11 MANAGE

| Command | Behaviour | Source |
|---|---|---|
| **Settings** | Study Settings (§2.3); also changes study parameters. | A[6] A[49] |
| **Local Mesh Control** | §3.7. | A[38] |
| **Load Case Attributes** | A table of every load and constraint in the load case: location, magnitude, direction and a placement status icon. | A[28] A[49] |
| Adaptive Mesh Refinement (older UI) | Now inside Settings. | A[76] A[39] |

### 3.12 Rules shared by all setup commands

| Behaviour | Source | Notes |
|---|---|---|
| Each load and constraint draws **glyphs** on its targets: arrows for loads, symbols for supports. | G (mem) | SciForge draws its own (§9). |
| One command can take **many targets**, such as several faces for one force. | A[19] A[11] | |
| Each item appears in the browser under the active **Load Case**, in **Constraints** or **Loads**. | A[28] | |
| Edit later from the browser item: the hover edit icon (shown for Gravity), or double-click and Edit. | A[26]; other items G (mem) | |
| **Several load cases per study** are allowed for Static Stress. Double-click activates one; right-click clones it; rename it. | A[28] A[78] A[74] | Most other study types have one load case. |

---

## 4. The browser in Simulation

The tree below is reconstructed. Node names are G (mem); each part's existence is sourced.

```
<document name>
├─ Document Settings (units)                       G (mem)
├─ Named Views                                      G (mem)
└─ Simulation Model 1                               F[96] A[74] (name G)
   ├─ components and bodies (active / suppressed)   A[28]
   └─ Study 1 - Static Stress   (active study)      G (mem)
      ├─ Study Materials                            A[28]
      ├─ Load Case1             (active load case)  A[28]
      │  ├─ Constraints: Fixed1, Pin1 ...           A[28]
      │  └─ Loads: Force1 ... and Gravity           A[26] A[28]
      ├─ Contacts               (Contact Manager)   A[35]
      ├─ Mesh                   (Generate Mesh)     A[38]
      │  └─ Local Mesh Control1 ...                 G
      └─ Results                                    G (mem)
```

A[28]: loads (including gravity) and constraints are stored together in a load case. Components,
study materials, contacts and mesh settings sit outside the load cases.

| Node | Action | Source |
|---|---|---|
| Study | **Clone Study**: a copy with the same mesh, loads, constraints and settings but **no results**. The study need not be active. | A[46] |
| Study | Activate, Rename, Delete, Settings | G (mem) |
| Load Case | Clone, Rename; double-click activates | A[74] A[78] |
| Load Case | New Load Case | G |
| Gravity | Hover edit icon → Edit Gravity | A[26] |
| Contacts | Opens Contact Manager | A[35] |
| Mesh | Generate Mesh | A[38] |
| Any load, constraint or contact | Edit, Delete, Suppress | G (mem) |
| Component or body | Remove from the study (through Simplify) | A[63] |

---

## 5. Results

### 5.1 What appears after a solve

| Behaviour | Source | Notes |
|---|---|---|
| The results download and the canvas shows the **Safety Factor** plot first ("The default display of the results of a static stress simulation ... is Safety Factor"). | A[80] A[71] | |
| Tags show the locations of the **minimum and maximum** automatically. | A[80] | |
| The deformed shape is drawn **Adjusted** (exaggerated). **Actual** is the default only for Nonlinear Static and Event Simulation. | A[51] | |
| The toolbar switches to the **RESULTS** tab. | G (mem) | |

### 5.2 Two result viewers (legacy and online)

| | Legacy ("standard") viewer | Online viewer (newer) |
|---|---|---|
| Studies | Static Stress and Nonlinear Static (older help A[47]) | Static Stress, Thermal, Thermal Stress, Electronics Cooling, Injection Molding (A[50]) |
| Layout | Legend with result-type and unit drop-downs | "Result browser", 3D display and a legend with **sliders for range of interest and thresholds**, plus result settings (A[50]) |
| Legend min/max | Editable, except for Safety Factor (A[53] F[90]) | Threshold sliders instead (A[53]) |
| Animation | Animate dialog, Steps up to 100 (A[52]) | A bar at the **bottom of the canvas**: speed 0.25× to 2×, up to 100 frames, play once / loop / mirror loop, save as .webm (A[52]) |
| Slice | INSPECT > **Create Slice Plane**: Shaded, Mesh Lines, Vectors, Clipping (A[56]) | INSPECT > **Create Cutting Plane**: Section, Slice (A[56]) |
| Compare | Deformation fixed to "Adjusted"; no probes (F[86]) | Scale adjustable (Preview, May 2025, F[86]) |

Which viewer a 2026 Fusion shows by default for Static Stress is unknown (§10 Q1).

### 5.3 Result types

| Result | Components | Source |
|---|---|---|
| **Safety Factor** | One value per point (§5.4) | A[30] A[48] |
| **Stress** | **Von Mises** (default stress), **1st Principal**, **3rd Principal**, Normal XX / YY / ZZ, Shear XY / YZ / ZX | A[30] A[32] A[48]; the component names are G (mem), consistent with the Inventor list A[82] |
| **Displacement** | Total, X, Y, Z | A[48] A[59]; components G (mem) |
| **Reaction Force** | At the constraints: Total, X, Y, Z | A[48] A[58] A[49] |
| **Reaction Moment** | | A[49] |
| **Strain** | Equivalent, principal, normal, shear | A[48]; components G (A[82] Inventor) |
| **Contact Pressure** (and contact force) | Only with contacts | A[48] A[60] A[76] |
| Convergence plot | Only with adaptive refinement | A[71] A[76] |

### 5.4 Safety factor

| Behaviour | Source | Notes |
|---|---|---|
| **Yield basis (default)**: safety factor = yield strength ÷ **von Mises** stress. | A[30] A[9] | |
| **Ultimate basis**: safety factor = ultimate tensile strength ÷ **1st principal** stress. | A[30] | |
| A minimum above 1.0 means no permanent deformation under the assumed conditions. | A[9] | |
| Values are **capped at 15** in the display, so a part that shows 15 everywhere is carrying almost no load. | F[89]; T[107] (an exported report shows a maximum of 15) | |
| The legend min/max option is **not offered** for Safety Factor. | F[90] | |
| Results Details text: details below this table. | A[71] A[54] | |
| A study can still be marked failed when the safety factor passes, because Fusion "evaluates multiple criteria at the study level" (yield, displacement, strain and others). | F[88] (Autodesk community manager, 2025) | Where these criteria are set is unknown (§10 Q6). |
| The safety-factor legend's colours and range | **not found** | §10 Q6. |

**Guided results** (A[71] A[54]):

- The safety-factor view sorts the part into three bands: "very strong", "meets target" and "not
  strong enough", judged against the user's targets.
- The Results Details messages read "**Meets Safety Factor Target**" or "**Below Safety Factor
  Target**", each with advice: add material, choose a stronger material, stiffen the design, or
  run a generative study.
- Help warns that lowering the **Upper Target** can make the message falsely say the design is
  fine.

### 5.5 Legend

| Behaviour | Source | Notes |
|---|---|---|
| A **result-type drop-down** chooses the plot. | A[77] A[49] | |
| A **units drop-down** switches English or metric on the fly, for stress, displacement and so on. It is not shown for Safety Factor, which has no unit. | A[77] | |
| A **Load Case** selector, with the **Results Details** button next to it. | A[61] | |
| Legacy: editable min/max. Online viewer: range and threshold sliders. | A[53] A[50] | |
| A vertical colour bar on the canvas, labelled with min and max values. | G (mem) | The position needs a screenshot. |

### 5.6 Deformation scale

| Option | Meaning | Largest movement drawn as | Source |
|---|---|---|---|
| Undeformed | Original shape | 0 | A[51] |
| Actual | True displacement. Default only for Nonlinear Static and Event Simulation. | True size | A[51] |
| Adjusted x 0.5 | Half of Adjusted | 2.5 % of model size | A[51] |
| **Adjusted** (default) | Scale factor from the bounding-box diagonal and the maximum displacement | **5 %** of model size | A[51] |
| Adjusted x 2 | | 10 % | A[51] |
| Adjusted x 5 | | 25 % | A[51] |

- **The formula.** The help excerpt gives the factor as "0.5 × (bounding box diagonal) ÷ (max
  displacement)", but the listed percentages imply **0.05 ×** (§10 Q9). SciForge should use
  scale = 0.05 × diagonal ÷ max displacement (G).
- **Where it is set.** A **Deformation** panel on the RESULTS ribbon, and a drop-down at the bottom
  of **Results Details** (A[51]).

### 5.7 Animate

| Behaviour | Source | Notes |
|---|---|---|
| Any result with result steps can be animated, Static Stress included. | A[52] | Static stress plays from undeformed to deformed (G). |
| Online viewer: details below this table. | A[52] | |
| Legacy: an **Animate** dialog with **Steps** (up to 100). | A[52] | Speed choices and a Repeat option are G (mem). |

**Online viewer animation bar** (A[52]):

- It sits at the bottom of the canvas.
- The gear icon sets the **speed** (0.25× to 2×) and the **number of frames** (up to 100).
- The play menu offers **once / loop / mirror loop**.
- The animation can be saved as **.webm** video.

### 5.8 Min/max, probes, reactions and slice planes

| Behaviour | Source |
|---|---|
| Min and max tags appear automatically. "Show Min/Max" is listed with the probe tools under INSPECT. | A[80] A[57] |
| **Surface Probes**: values at picked surface points, with no limit on how many. | A[55] |
| **Point Probes**: values **inside** the part, placed on visible surfaces including slice planes and iso-surfaces. | A[55] |
| The INSPECT drop-down offers surface probes, point probes, **reaction forces** and slice planes. | A[55] |
| **Slice plane**: legacy styles Shaded, Mesh Lines (to judge whether the mesh is fine enough), Vectors and Clipping. Online: "Create Cutting Plane", with styles Section and Slice. | A[56] |
| **Solver Data**: INSPECT > Solver Data. | A[57] |

### 5.9 Display options

| Behaviour | Source | Notes |
|---|---|---|
| A DISPLAY group on RESULTS toggles **Mesh** and **Wireframe**. | A[49] | |
| An outline of the **undeformed model** can be shown ("Show Undeformed model" in the web viewer). | A[68] | In the desktop UI: G. |
| Show or hide the load and constraint glyphs on results. | G (mem) | |

### 5.10 Results Details

| Behaviour | Source |
|---|---|
| Opened from the legend, next to the Load Case selector. | A[61] |
| Shows the result interpretation ("Meets ..." / "Below Safety Factor Target"), with advice and the targets (§5.4). | A[54] |
| A **Deformation Scale** drop-down at the bottom. | A[51] |

### 5.11 Compare

| Behaviour | Source | Notes |
|---|---|---|
| RESULTS > **Compare** shows up to **4** studies side by side; the canvas splits into views. | A[61] | Synchronized views: G (mem). |
| **Finish** closes Compare. | A[61] | |
| In the legacy viewer, Compare locks the deformation scale to Adjusted and has no probes. | F[86] | |

### 5.12 Report

| Behaviour | Source |
|---|---|
| RESULTS > RESULT TOOLS > **Report** opens the report dialog. | A[62] |
| Its sections are below this table. | A[62] |
| One report can cover several studies. Nonlinear studies choose how many result steps to include. | A[62] |
| **Preview** opens the report in a web browser; **Save** writes it. | A[62] |
| The output is an **HTML** file: the exported examples online are .html, or PDFs printed from it. | T[107] |
| Contents of real exported reports are listed below. | T[107]; the exact headings are G (mem) |

**Report sections** (A[62]):

- **General**: title, author, logo, cover picture and summary.
- **Properties**: project details, approvers and revision. General and Properties together make
  the cover page.
- **Studies**: pick the studies, load cases and glyphs. This section adds images of the loads and
  constraints, and result images.

**Contents of real exported reports** (T[107]):

- study properties;
- settings, with the mesh values (average element size 10 %, parabolic elements, contact
  tolerance 0.1 mm);
- a materials table (body, material, safety-factor basis) and a material properties table;
- constraints, loads and contacts, each with its entities and values;
- a results table of the min and max of each result type;
- result pictures.

### 5.13 RESULTS tab layout

The group order is G (mem); the members are sourced.

| Group | Commands | Source |
|---|---|---|
| RESULT TOOLS | Compare, Report, Animate, Results Details | A[49] A[61] A[62]; Animate placement is G |
| DEFORMATION | Deformation scale options | A[51] |
| DISPLAY | Mesh, Wireframe toggles | A[49] |
| MANAGE | Settings (study type, parameters, mesh settings including adaptive refinement), Local Mesh Control, Load Case Attributes | A[49] |
| INSPECT | Surface Probes, Point Probes, Reaction Force, Slice or Cutting Plane, Solver Data, Show Min/Max | A[55] A[56] A[57] |
| SELECT | | G |
| **FINISH RESULTS** | Returns to the SETUP tab | G (mem) |

---

## 6. Units

| Behaviour | Source | Notes |
|---|---|---|
| Every value field takes a **unit override**, for example typing "100 lbf". | A[23] | |
| Simulation follows the document's units. Preferences > **Default Units** has a **Simulation** tab, which sets defaults for new documents only. To change an open document, use **Document Settings > Units** in the browser. | A[67] F[99] | |
| The legend's **units drop-down** switches English or metric on the fly, except for Safety Factor. | A[77] | |
| Metric reports show **mm, N, MPa**. | T[107] | Imperial: in, lbf, psi (G). |

---

## 7. Keyboard shortcuts

| Behaviour | Source | Notes |
|---|---|---|
| No shortcut specific to Simulation was found. | (searched) | |
| Fusion's general keys still work: S for the shortcut box, Esc to cancel, Enter to OK. | G (mem) | |
| SciForge: Enter = OK, Esc = Cancel, Delete removes the selected study item, double-click an item to edit it. | G | |

---

## 8. Solver assumptions and definitions Fusion documents

| Behaviour | Source | Notes |
|---|---|---|
| Static Stress is valid only for **small deflections and rotations**. The part returns to its original shape when unloaded. | A[1] A[2] | |
| Loads keep their **direction and size**. | A[1] | |
| The material stays **elastic**; stiffness and strength do not change. | A[1] | |
| **No inertia** is considered. Mass is used only for gravity and rotational loads. | A[1] | |
| For large deformation, changing contact or nonlinear materials, use Nonlinear Static Stress. | A[1] A[2] | |
| Consequence: results scale linearly with the loads. | G | Use this in tests. |
| Elements: tetrahedra, linear (4-node) or parabolic (10-node). | A[37] | |
| A force on faces is turned into an equivalent pressure. | A[19] | |
| Safety factor = yield ÷ von Mises (default), or UTS ÷ 1st principal. | A[30] | |
| Principal stresses are maximum, intermediate and minimum (σ1 ≥ σ2 ≥ σ3). | A[32] | |
| Von Mises: σvm = √(((σ1−σ2)² + (σ2−σ3)² + (σ3−σ1)²) ÷ 2). | A[31] (the page exists); the formula is the standard one, G for the form shown there | |
| **Isotropic** materials are not stated by Fusion. | G | Fusion materials carry one E and one ν. SciForge must say it plainly (outline 7.18). |
| Rigid body: hold at least 6 DOF. | A[41] | |
| Fusion's help has a page of **accuracy verification examples** (classic textbook cases). | A[64] | Reuse it for golden tests (§9.5). |

---

## 9. Recommended for SciForge

### 9.1 Scope of the first Static Stress release

**Must:** without these it does not feel like Fusion.

1. **Workspace.** Simulation in the workspace drop-down, with SETUP and RESULTS tabs, a simulation
   browser and no timeline. Going back to Design leaves the studies stored in the document.
2. **New Study dialog.** All of Fusion's study types are shown as pictures with a one-line
   description. Only **Static Stress** is enabled. The rest are greyed with "Not in SciForge
   yet". A Settings icon and a **Create Study** button.
3. **Study Settings**:
   - General: Remove rigid body modes, off.
   - Mesh: average element size 10 % of model size; Scale Mesh Size Per Part; Parabolic or
     Linear (Parabolic default); curved elements on; turn angle 60; adjacent ratio 1.5; aspect
     ratio 10; minimum size 20 %.
4. **Study Materials table**:
   - one row per body;
   - a "(Same as Model)" default, with an override for this study only;
   - a safety-factor basis of Yield Strength (default) or Ultimate Tensile Strength;
   - double-click shows the properties used (E, ν, density, yield, UTS).
5. **Structural Constraints**:
   - Fixed (Ux/Uy/Uz, all on);
   - Pin (cylindrical faces; Radial and Axial on, Tangential off);
   - Frictionless;
   - Prescribed Displacement (Ux/Uy/Uz values).
6. **Structural Loads**:
   - Force: Normal or Vector (Angle is a "should"), Flip, shared by area, with Force Per Entity;
   - Pressure (normal);
   - Moment (Normal or Vectors);
   - **Gravity**: off by default, toggled on in the LOADS menu, Edit Gravity for direction, the
     default direction from SciForge's up axis, 9.807 m/s².
7. **Automatic Bonded contacts** made at solve time between bodies within 0.1 mm, plus the
   **Automatic Contacts** dialog (tolerance, Generate).
8. **Mesh.** Generate Mesh (SOLVE group and the Mesh node), and an automatic mesh at solve time.
   The mesh can be shown on the model.
9. **Pre-check** with a green, yellow or red toolbar icon and a message list (§9.6).
10. **Solve locally.** A Solve dialog that lists the studies and has a "Solve N Studies" button. A
    progress window with phases (Checking, Meshing, Solving, Reading results), elapsed time and
    **Cancel at any time**. No tokens, no cloud, no account.
11. **Out-of-date results.** Mark results stale as soon as the design, a material, a load, a
    constraint or the mesh changes. Show a stale badge on the Results node and a prompt to solve
    again.
12. **Browser tree** as in §4:
    - Study Materials; Load Case (Constraints, Loads, Gravity); Contacts; Mesh; Results.
    - Right-click: Edit, Rename, Delete, Suppress, Clone Study.
    - Double-click an item to edit it.
13. **Results.**
    - Opens on **Safety Factor**, with min and max tags.
    - Result list: Safety Factor; Stress (von Mises, 1st and 3rd principal, Normal XX/YY/ZZ,
      Shear XY/YZ/ZX); Displacement (Total, X, Y, Z); Reaction Force (Total, X, Y, Z); Strain
      (equivalent).
    - Legend with result-type and unit drop-downs.
    - Safety factor capped at 15.
    - Deformation scale: Undeformed / Actual / Adjusted ×0.5 / **Adjusted** / ×2 / ×5, with
      Adjusted = 5 % of model size.
    - Animate (frames, speed, loop).
    - Surface probes.
    - Mesh toggle.
    - **Finish Results**.
14. **The honest banner.** State the limits plainly: linear static, small deflections, isotropic
    material (3D-printed parts are not), and that results are a guide (outline 7.18). Show it in
    the New Study description and in Results Details.

**Should:** the second step, or in the first release if time allows.

- Bearing Load.
- Remote Force.
- Force direction by Angle.
- Limit Target.
- Load Case Attributes.
- Several load cases in a study.
- Local Mesh Control.
- DOF View.
- Contact Manager. Read-only list at first, showing Bonded pairs.
- Results Details:
  - the min and max of each result;
  - the deformation scale;
  - "meets / below target" text against a minimum safety factor the user sets, default 1.0 (G);
  - advice lines in SciForge's own words.
- Slice plane, with a Shaded and a Clipping style.
- Compare, two studies side by side.
- Report as HTML, with SciForge's own layout and wording.
- Unit override in each value field.

**Later:**

- The Simplify environment and simulation models.
- Adaptive mesh refinement and convergence plots.
- Point probes and iso-surfaces.
- Hydrostatic pressure.
- Linear and angular global loads.
- Point mass.
- Remote moment and the remote constraint.
- Contact types other than Bonded (Separation, Sliding, Rough and Offset Bonded need nonlinear
  contact).
- Connectors.
- Saving the animation as video.
- Compare with 4 studies.
- Configurations.
- The guided "online viewer" style legend with threshold sliders, unless Luca's screenshot shows
  that this is what he uses (§10 Q1).

### 9.2 SETUP tab: SciForge command status

| Group | Command | SciForge first release |
|---|---|---|
| STUDY | New Simulation Study | Enabled (Static Stress only; the other types greyed inside the dialog) |
| SIMPLIFY | Simplify | **Greyed**: "Not in SciForge yet. The study uses the design as it is; exclude a body from a study in Study Materials." |
| MATERIALS | Study Materials | Enabled |
| MATERIALS | Manage Physical Materials | Enabled (opens SciForge's material library) |
| CONSTRAINTS | Structural Constraints: Fixed, Pin, Frictionless, Prescribed Displacement | Enabled |
| CONSTRAINTS | Remote constraint | Greyed in the Type list |
| LOADS | Structural Loads: Force, Pressure, Moment | Enabled |
| LOADS | Structural Loads: Bearing Load, Remote Force | Should; greyed in the Type list until built |
| LOADS | Structural Loads: Remote Moment, Hydrostatic Pressure | Greyed in the Type list |
| LOADS | Toggle Gravity On/Off | Enabled |
| LOADS | Linear Global Load, Angular Global Load, Point Mass (Auto), Point Mass (Manual) | Greyed |
| CONTACTS | Automatic Contacts | Enabled (Bonded) |
| CONTACTS | Manual Contacts | Greyed: "Not in SciForge yet: only bonded contacts, found automatically." |
| CONTACTS | Contact Manager | Should (read-only list) |
| CONTACTS | Bolt / Rigid Body Connector | Greyed |
| DISPLAY | DOF View | Should |
| SOLVE | Pre-check, Solve, Generate Mesh | Enabled (local solve) |
| MANAGE | Settings | Enabled (General and Mesh tabs; the Adaptive Mesh Refinement tab greyed) |
| MANAGE | Local Mesh Control, Load Case Attributes | Should |
| INSPECT, SELECT | As in Design | Enabled |

### 9.3 RESULTS tab: SciForge command status

| Group | Command | SciForge first release |
|---|---|---|
| RESULT TOOLS | Animate | Enabled |
| RESULT TOOLS | Results Details | Should |
| RESULT TOOLS | Compare | Greyed: "Not in SciForge yet" |
| RESULT TOOLS | Report | Greyed until built |
| DEFORMATION | Undeformed / Actual / Adjusted ×0.5, ×1, ×2, ×5 | Enabled |
| DISPLAY | Mesh, Wireframe | Enabled |
| MANAGE | Settings, Local Mesh Control, Load Case Attributes | As on SETUP |
| INSPECT | Surface Probes, Show Min/Max | Enabled |
| INSPECT | Reaction Force | Enabled (a table of the reaction at each constraint) |
| INSPECT | Slice Plane | Should |
| INSPECT | Point Probes, Iso-surface, Solver Data | Greyed |
| — | Convergence plot | Greyed (no adaptive refinement) |
| — | Finish Results | Enabled |

### 9.4 Builder notes: mapping to FreeCAD FEM (G; names checked in this repo's `src/Mod/Fem/ObjectsFem.py`)

| Fusion item | FreeCAD FEM piece | Note |
|---|---|---|
| Solve | `makeSolverCalculiX` or `makeSolverCalculiXCcxTools`, analysis type static | Linear static, CalculiX `ccx` already bundled. |
| Mesh settings | `makeMeshGmsh`: `ElementOrder` 2nd = Parabolic; `CharacteristicLengthMax` and `CharacteristicLengthMin` from the % values; `SecondOrderLinear` off = Create Curved Mesh Elements | Turn angle → `MeshSizeFromCurvature` (elements per 2π = 360 ÷ angle). Adjacent ratio and aspect ratio have no 1:1 Gmsh setting (G). |
| Local Mesh Control | `makeMeshRegion` (element length on faces and edges) | |
| Study material | `makeMaterialSolid` (E, ν, density) | SciForge keeps yield and UTS for the safety factor. |
| Fixed, partial Fixed, Prescribed Displacement | `makeConstraintFixed`; `makeConstraintDisplacement` (free or fixed per axis, plus values) | |
| Pin; Frictionless on a tilted face | `makeConstraintTransform` (cylindrical: radial, tangential, axial; rectangular for a tilted plane) plus `makeConstraintDisplacement` | |
| Force | `makeConstraintForce` | `femmesh/meshtools.py` already splits the **total** force over the picked faces by area, and over edges by length. That **matches Fusion's default**. Per Entity = the value × the number of entities, or one constraint per face. |
| Pressure | `makeConstraintPressure` | |
| Gravity | `makeConstraintSelfWeight` | |
| Bonded contact | `makeConstraintTie` (CalculiX *TIE with a tolerance) | Automatic contact detection (touching faces within 0.1 mm) is SciForge code. |
| Moment, Remote Force/Moment | `makeConstraintRigidBody` (a reference point with force and moment) | Verify that it handles a pure moment on a face. |
| Angular global load | `makeConstraintCentrif` | Later. |
| Bearing Load | No direct object | Needs SciForge-written node loads with a parabolic distribution. |
| Results | `ResultMechanical`: `vonMises`, `PrincipalMax`/`PrincipalMed`/`PrincipalMin`, `NodeStressXX`…`YZ`, `NodeStrainXX`…, `DisplacementVectors`, `DisplacementLengths` | Reaction forces: the writer already asks CalculiX for `RF` at fixed and displacement constraints (`write_step_output.py`). Safety factor = yield ÷ von Mises per node, capped at 15, computed by SciForge. |

### 9.5 Golden studies (acceptance, outline 7.18)

Use classic hand-calculation cases, which is also how Fusion's accuracy page works (A[64]):

- **Cantilever beam** with an end load: tip deflection = F·L³ ÷ (3·E·I); root stress = M·c ÷ I.
- **Plate with a hole** in tension: stress concentration Kt ≈ 3 for a small hole.
- **Thin-walled pressurised cylinder**: hoop stress = p·r ÷ t.

Each must match within a few percent. Also check two Fusion behaviours:

- Gravity off by default.
- A force on two faces of different areas is shared by area, and Per Entity doubles the total.

### 9.6 Pre-check messages SciForge should give (G; SciForge's own wording)

| State | Condition |
|---|---|
| Red | A body has no material, or is missing E, ν or density (with gravity on) |
| Red | No constraint at all, and Remove rigid body modes is off |
| Red | A load or constraint whose faces no longer exist |
| Red | The mesh failed (name the body) |
| Yellow | No loads (and gravity off) |
| Yellow | A body touches nothing and is not held |
| Yellow | The same face is constrained twice |
| Yellow | Yield strength missing (no safety factor possible) |
| Yellow | Remove rigid body modes is on while constraints exist |
| Green | Otherwise |

---

## 10. Open questions (a screenshot from Luca's Fusion would settle these)

1. **The results screen of a solved Static Stress study.** Is it the legacy legend (result and
   unit drop-downs) or the online viewer (result browser, range and threshold sliders, animation
   bar at the bottom)? This decides §5's look.
2. **The SETUP toolbar** and the open drop-downs of LOADS, CONSTRAINTS, CONTACTS, SOLVE and
   MANAGE: the group order and the exact commands, including whether Generate Mesh and Job Status
   are in SOLVE.
3. **The New Study dialog**: tiles or list, the exact list and order of study types, the Settings
   icon and "Create Study".
4. **Study Settings for Static Stress**: the tabs (is there a Contacts tab?) and every default on
   the Mesh and Adaptive Mesh Refinement tabs. Several values in §2.3 are G.
5. **The Structural Loads dialog** when it opens: the default force magnitude and Direction Type,
   and the default pressure and moment values.
6. **The safety factor plot**: the legend range and colours (red below 1?), the "very strong /
   meets target / not strong enough" bands, and where the lower and upper targets and the other
   pass/fail criteria are set, with their defaults.
7. **The browser tree** of a study with one force, one fixed support and gravity: the exact node
   names ("Simulation Model 1", "Study 1 - Static Stress", "Load Case1"?).
8. **Moment on several faces**: is the value shared or applied to each face? A right-click on a
   moment with two faces, with the dialog showing, would tell.
9. **Deformation scale**: the drop-down's exact entries. Does "Adjusted" draw the maximum movement
   at 5 % of the model size, with factor 0.05 (the listed percentages), or 0.5 (the help
   excerpt)?
10. **Pre-check** messages for a model with no constraint and for a body with no material, and the
    message after a solve fails because the model is under-constrained.
11. **Automatic Contacts**: the default Contact Detection Tolerance shown in the dialog.
12. **Gravity**: the default direction in Luca's setup (Z-up or Y-up) and the magnitude shown in
    Edit Gravity.

---

## References

**Autodesk help: Fusion Simulate** (help.autodesk.com; `cloudhelp/ENU/Fusion-Simulate/files/` is
shortened to `FS/`)

- [1] Static stress study: https://help.autodesk.com/cloudhelp/ENU/Fusion-Simulate/files/SIM-STATIC-STRESS-ANALYSIS.htm
- [2] Static stress analysis overview: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-SSA
- [3] Structural analyses simulations: FS/SIM-HOW-IT-WORKS.htm
- [4] General workflow to run a simulation study: FS/GUID-A312551A-F2B3-42C1-8F24-5A64D30FFADF.htm
- [5] Tutorial: Static stress analysis: FS/GUID-3E91212F-9158-4E7C-BB6A-662F22EF22C3.htm
- [6] Activity 1: Create a new static stress study: FS/GUID-8D0481D0-E6E3-4ECA-B627-D5E40DA0812C.htm
- [7] Activity 3: Apply constraints: FS/GUID-B14DCA9A-B8A1-46A4-BB7E-AC6C334AC96F.htm
- [8] Activity 4: Solve the analysis and review the results: FS/GUID-63BEE2EF-849E-4132-A0F2-1B8CA0629393.htm
- [9] Activity 1: Create a new thermal stress study (material defaults, safety factor): FS/GUID-534520EA-5DDB-4D2C-95E1-7A45165CD8AC.htm
- [10] Activity 4: Select a different material and rerun: FS/GUID-15B68BA1-B5C8-42B2-B3E1-D5E4EF189789.htm
- [11] Structural constraints: FS/SIM-STRUCTURAL-CONSTRAINTS-CONCEPT.htm
- [12] Constraint types: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-CONSTRAINT-TYPES
- [13] Fixed constraint: FS/SIM-FIXED-CONSTRAINT.htm
- [14] Pin constraint: FS/SIM-PIN-CONSTRAINT.htm
- [15] Frictionless constraint: FS/SIM-FRICTIONLESS-CONSTRAINT.htm
- [16] Prescribed displacement constraint: FS/SIM-PRESCRIBED-DISPLACEMENT-CONCEPT.htm
- [17] Remote constraint: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-REMOTE-CONSTRAINT-CONCEPT
- [18] Apply a structural load: FS/SIM-STRUCTURAL-LOADS-CMD.htm and https://help.autodesk.com/view/fusion360/ENU/?contextId=SIM-SETUP-STRUCT-LOAD
- [19] Force loads: FS/SIM-FORCE-LOAD-CONCEPT.htm
- [20] Pressure loads: FS/SIM-PRESSURE-LOAD-CONCEPT.htm
- [21] Moment loads: FS/SIM-MOMENT-LOADS-CONCEPT.htm
- [22] Bearing load: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-BEARING-LOAD-CONCEPT
- [23] Remote force loads, and Apply a remote force load: FS/SIM-REMOTE-FORCE-CONCEPT.htm, FS/SIM-REMOTE-FORCE-TASK.htm
- [24] Global loads: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-GLOBAL-LOADS-CONCEPT
- [25] Set angular global load: FS/SIM-ANGULAR-GLOBAL-LOAD-CMD.htm
- [26] Gravity in simulations, and Toggle gravity: FS/SIM-GRAVITY-CONCEPT.htm, FS/SIM-TOGGLE-GRAVITY-TSK.htm
- [27] Assign a point mass automatically: FS/GUID-889877A6-1B15-4DEA-A260-9ECDCDA9459E.htm
- [28] Load case: FS/SIM-LOAD-CASES-CONCEPT.htm
- [29] Material properties (Study Materials): FS/SIM-MATERIAL-PROPERTIES-CPT.htm
- [30] Safety factor calculation: FS/SIM-SAFETY-FACTOR-CALC-CONCEPT.htm
- [31] von Mises (equivalent) stress calculation: FS/VON-MISES-STRESS-EQ-CONCEPT.htm
- [32] Principal stress calculations: FS/SIM-PRINCIPAL-STRESS-EQ-CONCEPT.htm
- [33] Contacts in Simulation studies: FS/SIM-CONTACT-TYPES.htm
- [34] Define automatic contacts: FS/GUID-A102D11A-5D3F-4556-B669-0F4369000351.htm
- [35] Edit contact pairs (Contact Manager): https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-EDIT-CONTACT-PAIRS
- [36] Contact penetration types: FS/SIM-CONTACT-PENETRATION.htm
- [37] Mesh quality: FS/SIM-MESH-QUALITY.htm
- [38] Local mesh control, and Apply a local mesh control: FS/SIM-LOCAL-MESH-REFINE.htm, FS/GUID-336BE142-89A3-4E62-B7AD-4F695DAA983B.htm
- [39] Adaptive mesh refinement, and Apply adaptive mesh refinement: FS/SIM-ADAPTIVE-REFINEMENT-CONCEPT.htm, FS/SIM-SETUP-ADAPT-REFINE.htm
- [40] Remove rigid body modes, and its guidelines: FS/SIM-RIGID-BODY-MODES-CMD.htm, FS/SIM-RIGID-BODY-MODE-GUIDE-CONCEPT.htm
- [41] Rigid body motion: FS/SIM-RGD-BDY-MTN-CPT.htm
- [42] Pre-check and study errors: https://help.autodesk.com/view/fusion360/ENU/?contextId=PRE-HOW-TO and https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-9DB47C44-9949-4C24-9748-9D5554590B09
- [43] Tokens for Fusion Simulation studies (Solve dialog): https://help.autodesk.com/cloudhelp/ENU/Fusion-CloudCredits/files/GUID-97268379-A0C4-4426-8929-2FB3F3FB439C.htm
- [44] Job Status dialog: FS/GUID-C91E8298-38B9-4E7D-A89E-D01B1203EACF.htm
- [45] Simulation browser: FS/GUID-6576CDB3-00E5-49CC-B665-B0784D4D66BA.htm
- [46] Clone a simulation study: FS/SIM-CLONE-SDY_CPT.htm, FS/SIM-TO-CLONE-SDY-TSK.htm
- [47] Simulation results (overview; older viewer list): FS/GUID-99797676-4E9B-4257-AAB2-E83766121C9E.htm
- [48] Structural analysis results: FS/GUID-296056DA-ED8C-4EBF-8E3A-2209B1DE9AEE.htm
- [49] Results tab: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-RESULTS-TAB
- [50] Online viewer, standard results: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-VIS-FIM-RESULTS-CONCEPT
- [51] Deformation Scale, and Change the deformation scale: FS/SIM-VIZ-DEFORMATION-SCALE.htm, FS/SIM-DEFORM-SCALE-TASK.htm
- [52] Animation in a simulation study: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-ANIMATE-CONCEPT
- [53] Change the legend range: FS/SIM-LEGEND-MINMAX-TASK.htm
- [54] Results details dialog: FS/SIM-RESULT-DETAILS-REF.htm
- [55] Surface probes, and Point probes: FS/SIM-SURFACE-PROBE-CONCEPT.htm, https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-POINT-PROBE-CONCEPT
- [56] Create cutting (slice) planes: FS/GUID-E516E533-1F44-48A2-B970-EDA0BE9253E4.htm, https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-SLICE-PLANE-CONCEPT
- [57] Solver data: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-VIZ-SOLVER-DATA-TASK
- [58] Reactions results: FS/SIM-REACTION-FORCE-VIEW-CONCEPT.htm
- [59] Displacement results: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-DISPLACEMENT-VIEW-CONCEPT
- [60] Contact force results: https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-CONTACT-FORCE-VIEW-CONCEPT
- [61] Compare results, plus tutorial steps: FS/SIM-COMPARE-RESULTS-TASK.htm, https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-TUT-9-REVIEW-COMPARE, https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-TUT-9-CLONE-RERUN
- [62] Simulation report, and Create a report: FS/SIM-REPORTS-CONCEPT.htm, https://help.autodesk.com/view/NINVFUS/ENU/?guid=SIM-CREATE-REPORT-TASK
- [63] Model simplification, Remove Features, Replace with Primitives, Simplify modify commands, Remove bodies or components: FS/GUID-18D8F594-559B-4791-A475-F2B88638A410.htm, FS/GUID-EE27D6D0-3E3E-4547-B438-8DA0CFE5A870.htm, https://help.autodesk.com/view/fusion360/ENU/?contextId=SIMPLIFY-REPLACE-WITH-PRIMITIVES-CMD, https://help.autodesk.com/view/fusion360/ENU/?contextId=SIM-MODIFY-COMMANDS, FS/GUID-400239BF-5BEE-4F84-B88C-EE33FCC8F7DA.htm
- [64] Accuracy verification examples: FS/GUID-C75BE7CE-E4EE-4CAA-8697-095DA51459FB.htm
- [65] Set up, solve, and compare simulation studies for configurations: https://help.autodesk.com/cloudhelp/ENU/Fusion-Configurations/files/CFG-SIMULATION.htm
- [66] Quasi-static tutorial, constraints step (rigid-body DOF): https://help.autodesk.com/view/fusion360/ENU/?guid=SIM-TUT-10-QS-CONSTRAINTS
- [67] How to change units in Fusion: https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FHow-to-Change-Units-in-Fusion-360.html
- [68] View designs in the Fusion web client; Autodesk Drive "Simulation: View results": https://help.autodesk.com/cloudhelp/ENU/Fusion-Import/files/GUID-7BBC3139-A95B-42E7-A917-C7163F8C4F26.htm, https://help.autodesk.com/cloudhelp/ENU/DRIVE-USER/files/GUID-D838159D-5DCC-4DB7-B4FB-55815833AB0F.htm
- [69] Generative Design: Apply a gravity load (default direction from Preferences): https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-APPLY-GRAVITY-LOAD.htm
- [70] Fusion Simulation Extension help: https://help.autodesk.com/view/fusion360/ENU/?contextId=EXT-SIMULATION, https://help.autodesk.com/cloudhelp/ENU/Fusion-Portal/files/courses/sim-extension/AP-SIM-EXT.html

**Autodesk blog, Learn, AU and other Autodesk products**

- [71] Fusion blog, "Mastering Static Stress Simulations in Autodesk Fusion" (2025): https://www.autodesk.com/products/fusion-360/blog/static-stress-simulations-autodesk-fusion/
- [72] Fusion blog, "Making the most of Simplify in the Fusion 360 Simulation Workspace, Part 1": https://www.autodesk.com/products/fusion-360/blog/making-the-most-of-simplify-in-the-fusion-simulation-workspace-part-1/
- [73] Fusion blog, "Fusion 360 Simulation Extension": https://www.autodesk.com/products/fusion-360/blog/fusion-360-simulation-extension/
- [74] Autodesk Learn course, "Fusion 360 Simulation: applications for static stress analysis (professional)". Units: Mesh generation https://autodesk.com/learn/ondemand/course/fusion360-simulation-applications-for-static-stress-analysis-professional/unit/6r7X1AreecoPmYQgHVLRYn ; Simplify workspace .../unit/4HOYvRflmkGKHBoeylImr5 ; Structural loads .../unit/2ZAX5WfrcosqLL0A82XI6e ; Simulation results tools .../unit/W2TZxQi5gihEssk3isY3V ; Clone a simulation model .../unit/3EM6uKefNtRiAMPnjA3yCV
- [75] Autodesk Learn: "Set up a static stress simulation" https://app.learn-one.autodesk.com/learn/ondemand/course/static-stress-simulation/unit/3Dfx6yHaSmPIkDKX45KXa0 ; challenge exercise https://www.autodesk.com/learn/ondemand/module/challenge-exercise-set-up-solve-and-review-a-static-stress-simulation-study ; "Getting started: static stress overview" https://www.autodesk.com/learn/ondemand/curated/getting-started-with-simulation/KW9u4cqugIm75g2EoAc9q ; certification prep unit https://autodesk.com/learn/ondemand/course/fusion360-simulation-static-stress-analysis-cert-prep/unit/LwPfyU2hQgEb9ldlaAldg
- [76] AU AUME717, "Become a Fusion Simulation Expert in 60 Minutes": https://static.au-uw2-stg.autodesk.com/AUME717_-_Become_a_Fusion_Simulation_Expert_in_60_Minutes.pdf
- [77] AU MFG225930, "Understanding and Improving Your Results in Fusion 360 Simulation" (M. Fiedler): https://static.au-uw2-prd.autodesk.com/Class_Handout_MFG225930_Understanding_and_Improving_Your_Results_in_Fusion_360_Simulation_Michael_Fiedler.pdf
- [78] AU class handouts IM463460 and IM500020 (Pre-check/Solve step; double-click activates a load case): https://static.au-uw2-stg.autodesk.com/Class_Handout_IM463460.pdf, https://static.au-uw2-stg.autodesk.com/Class_Handout_IM500020_IM500020SubAU2021Handout.pdf
- [79] AU class "Getting Started: Simulation Fusion 360 Basics 2021": https://app.gnosis-mfe.autodesk.com/autodesk-university/class/Getting-Started-Simulation-Fusion-360-Basics-2021
- [80] Autodesk Knowledge, "Fusion 360: Static Stress Simulation": https://knowledge.autodesk.com/support/fusion-360/getting-started/caas/simplecontent/content/fusion-360-static-stress-simulation.html
- [81] (Inventor) Inventor 2014 help, Mesh Settings: https://help.autodesk.com/cloudhelp/2014/ENU/Inventor/files/GUID-10291E2B-03E4-4A5E-AB23-BC6083B6538A.htm
- [82] (Inventor) Inventor 2022 help, About visual results of analysis: https://help.autodesk.com/cloudhelp/2022/ENU/Inventor-Help/files/GUID-A88840EF-391B-4987-A77B-5D58F19600CA.htm
- [83] (Sim Mech) Simulation Mechanical 2014, Bearing loads: https://help.autodesk.com/cloudhelp/2014/ENU/SimMech/files/GUID-B7D6D68F-56BF-4259-AA29-5DBF80B43621.htm

**Autodesk Community forum** (forums.autodesk.com)

- [84] "Fusion 360 - Cloud solving will be the only option available for all simulation" (Aug 2022): https://forums.autodesk.com/t5/fusion-support-forum/fusion-360-cloud-solving-will-be-the-only-option-available-for/td-p/11342929
- [85] "model disappears after simulation run" (2024; results tied to the design version, out-of-date message): https://forums.autodesk.com/t5/fusion-support-forum/model-disappears-after-simulation-run/m-p/12758637
- [86] "Simulation Deformation Scale in Compare mode (static stress analysis)" (May 2025 reply): https://forums.autodesk.com/t5/fusion-design-validate-document/simulation-deformation-scale-in-compare-mode-static-stress/m-p/8415746
- [87] "Deformation Scale Description": https://forums.autodesk.com/t5/fusion-design-validate-document/deformation-scale-description/m-p/10126384
- [88] "safety factor" (2025; study-level criteria, target 1.4): https://forums.autodesk.com/t5/fusion-design-validate-document/safety-factor/m-p/13966373
- [89] "Safety Factor 15 Throughout Simulation" (2023): https://forums.autodesk.com/t5/fusion-support-forum/safety-factor-15-throughout-simulation/td-p/12280757
- [90] "legend box" (no min/max for Safety Factor): https://forums.autodesk.com/t5/fusion-support-forum/legend-box/td-p/8595331
- [91] "Reaction force" (Pin constraint holds every node): https://forums.autodesk.com/t5/fusion-design-validate-document/reaction-force/m-p/8660879
- [92] "Simulation" (pre-check traffic light, DOF View, Autodesk staff): https://forums.autodesk.com/t5/fusion-design-validate-document/simulation/td-p/7721897 ; "Fusion 360 simulation bolted connection error": https://forums.autodesk.com/t5/fusion-design-validate-document/fusion-360-simulation-bolted-connection-error/td-p/7440968
- [93] "Simulation warning" (redundant constraint): https://forums.autodesk.com/t5/fusion-design-validate-document/simulation-warning/td-p/8581501
- [94] "sliding contact sets and frictionless constraints in simulation environment": https://forums.autodesk.com/t5/fusion-support-forum/sliding-contact-sets-and-frictionless-contraints-in-simulation/td-p/9429430
- [95] "In simulation, what is a material with graph icon?": https://forums.autodesk.com/t5/fusion-360-design-validate/in-simulation-what-is-a-material-with-graph-icon/td-p/7300858
- [96] "Urgent Simulation latest update issue" (Sep 2017 simulation model and Simplify change, Autodesk architect): https://forums.autodesk.com/t5/fusion-support-forum/urgent-simulation-latest-update-issue-confusing-how-to-use/m-p/7401616
- [97] "Static Stress Simulation slow with Local Solve": https://forums.autodesk.com/t5/fusion-design-validate-document/static-stress-simulation-slow-with-local-solve/m-p/11184168
- [98] "Simulation: constrains and Rigid Body Modes": https://forums.autodesk.com/t5/fusion-design-validate-document/simulation-constrains-and-rigid-body-modes/m-p/10181009
- [99] "Units in Simulation Report": https://forums.autodesk.com/t5/fusion-360-design-validate/units-in-simulation-report/td-p/6521290
- [100] "Convergence Issues in Simulation": https://forums.autodesk.com/t5/fusion-design-validate-document/convergence-issues-in-simulation/m-p/6993621
- [101] "Static Stress Simulation Multiple Studies": https://forums.autodesk.com/t5/fusion-support-forum/static-stress-simulation-multiple-studies/m-p/13872320
- [102] "Design history missing in Simulation Simplify Mode" (2024): https://forums.autodesk.com/t5/fusion-support-forum/design-history-missing-in-simulation-simplify-mode/td-p/12797899
- [103] "simulation not working after update to only cloud solving" (2022): https://forums.autodesk.com/t5/fusion-support-forum/simulation-not-working-after-update-to-only-cloud-solving/td-p/11372475

**Tutorials and exported reports**

- [104] MIT fab class recitation, "Simulation: a toolset for virtual experiments": https://tourlomousis.pages.cba.mit.edu/fabclass-recitation-simulation/
- [105] LinkedIn Learning (Lynda), "Creating a static stress study" and "Assigning materials to model": https://origin-www.lynda.com/Fusion-360-tutorials/Creating-static-stress-study/2823570/2307067-4.html, https://origin-www.lynda.com/Fusion-360-tutorials/Assigning-materials-model/2875057/2392674-4.html
- [106] Norwegian Creations, "Basic Static Stress Simulation in Fusion 360" (2016): https://www.norwegiancreations.com/?p=4766
- [107] Fusion study reports exported by users: https://fabacademy.org/2023/labs/kochi/students/sreyas-george/assignments/week2/Studies_Report_2023-02-07.html ; https://astropolis.pl/applications/core/interface/file/attachment.php?id=231467 ; https://cdn.hackaday.io/files/1732857413825440/Zbiornik%20z%20wod%C4%85-MES.pdf ; https://indico.phys.sinica.edu.tw/event/496/contributions/3086/attachments/1432/2987/PR1p0mm.html
- [108] KETIV blog, "Fusion 360: Static Stress Simulation": https://ketiv.com/blog/fusion-360-static-stress-simulation/
- [109] CAD Forum (cadforum.cz), study types tip: https://www.cadforum.cz/cz/typy-simulacnich-uloh-ve-fusion-360-silove-a-tepelne-namahani-tip10853

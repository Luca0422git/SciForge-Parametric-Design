You are fixing SciForge, a FreeCAD 1.1.4 fork that must behave like Autodesk Fusion. The owner,
Luca, is a beginner who only tests: explain what you did in plain words. Read `CLAUDE.md`,
`MEMORY.md` (top and newest session logs) and `docs/sciforge/patch-release.md` first.

## Your job: patch release `0.1.0-beta.2.2`, branch `develop`

Four items from Luca's beta 3 list (2026-10-26) that he wants out as a **patch**, not in beta 3.
A patch ships SciForge's own files only (`src/Mod/SciForge/`): **no change to FreeCAD's C++** (the
patch workflow refuses one; it would need the 4-hour full build). A robotics team, college
students and Luca's manager use the beta, so the joint bug comes first.

When done: `src/Mod/SciForge/VERSION` and `_FALLBACK_VERSION` (`sciforge/__init__.py`) =
`0.1.0-beta.2.2`, a `## 0.1.0-beta.2.2` section in `CHANGELOG.md` (the patch intro line as in
`0.1.0-beta.2.1`, then "### Fixed"; the two additions can go under "### Improved"), the README and
`docs/sciforge/known-issues.md` title bumped as for 0.1.0-beta.2.1, push `develop`, wait for a
green "SciForge tests" run, then tell Luca to run **Actions > SciForge patch release**. Update
`MEMORY.md` (the "Patch 0.1.0-beta.2.2" block at the top and a session log).

## 1. Deleting a joint breaks a body (MAJOR bug)

Luca's words: "When deleting a joint, it also deletes the body. its still in the browser, but
there is no body. even sciforge gives an error saying that there is nothing if i try to edit it.
or the joint gets deleted, the body stays, but cant be edited (tested with fillet)."
His answers: deleted **from the browser** (right-click or Delete key on the joint's row), a
**Revolute** joint, the two bodies **on their own** (bodies at the document root, no
components). No crash log was sent.

Not reproduced yet. What was read (2026-10-26, nothing obviously removes the body):
- the browser's delete: `sciforge/browser_ui.py` `delete()` (a joint is a "step" kind, so it goes
  to `timeline_ops.delete`);
- `sciforge/timeline_ops.py` `delete()` (~line 1599): `rolls_back`, `_attached_to`,
  `_helpers_of` (removes OutList helpers nothing else uses), `remember_references` /
  `repair_references` (re-picks fillet edges by geometry after a delete), the Tip reset at the
  end (`_set_tips(doc, core.tips_for_count(...))`) and `_show_only_tip` for touched bodies;
- `sciforge/joints.py` `_DeleteWatch.slotDeletedObject` (~line 3090): removes a joint's helpers
  and motion links; a deleted body takes its joints.
Suspects, unconfirmed: (a) the assembly re-solve after the joint goes moves the body somewhere
odd or leaves a bad Placement (the body "is there" but nothing shows); (b) the body's Tip or a
step's references are reset wrongly by the delete (the fillet "cannot be edited");
(c) `repair_references` re-picking the fillet's edges by geometry on a body the joint had moved.

Do: reproduce in real FreeCAD under xvfb (`tools/sciforge/get_freecad.sh`, then a scenario like
`joints_basic`): two bodies, the moving one with a fillet, a Revolute joint, drive it to a
non-zero angle (and also at 0), delete the joint from the browser row; check each body's Shape
(not null, same volume), Placement, Tip, the fillet's Base edges and state, and that the fillet
edits and Ctrl+Z / Ctrl+Y work. Also delete from the timeline. Fix the root cause; add the case
to the joints scenarios. Fusion: deleting a joint leaves the components where they are
(`docs/sciforge/parity/joints.md`, "Delete, Suppress, Undo, save").

## 2. Drag a joint to set its limits

Luca: "Joints should have a way to drag them to drive them. especially for setting a min and
max. I should be able to drag it where i want it to max and min. simple as that."

What exists: Component Drag (`sciforge/joints_drag.py`: a canvas drag moves a part within its
joints, stops at limits; only outside commands); Edit Joint Limits / the Joint dialog's limits
(`sciforge/joints_ui.py` `_Limits`, ~line 740: ticking Minimum or Maximum fills in the joint's
value now); the drag arrows and angle handles (`handles3d.py`, `pickpanel.Arrow`,
`taskui.ArrowDragger`, used by Revolve's angle). Workaround today: drag the part, then open Edit
Joint Limits and tick the limit.

Build: while the Joint dialog's limits or Edit Joint Limits are open, a drag handle on the joint's
motion axis (an angle handle for a turn, an arrow for a slide) and dragging the part itself both
drive the joint live; the Minimum / Maximum (and Rest) rows each get a way to take the dragged
position (the row's value follows the drag while its box is the current one, or a small "use
position" button; pick the one closest to Fusion and say which in the parity doc). Show where
each limit is (a faint ghost of the part at Minimum and Maximum is ideal). One undo step; Cancel
puts everything back. Update `docs/sciforge/parity/joints.md`.

## 3. Ghost of a hidden body when its browser row is hovered

Luca: "If i hover over a body in the browser that is hidden, I should get a preview of that body
in the workspace. A ghost body if you will. it already highlights bodies that are visible, so it
should be pretty straight forward to faintly highlight a hidden body when hovering over it in the
browser."

Why nothing shows today: the browser's hover is FreeCAD's preselection
(`sciforge/browser_ui.py` ~line 1053, `Gui.Selection.setPreselection`), which colours only what
is drawn. Build: on hover of a hidden body's row, draw it faint and see-through (a temporary Coin
node, or `makeTemporaryVisible()` plus a see-through look on the Coin nodes as `fillet_ui.py`
does); remove it when the hover leaves, the row is clicked, or the document changes. **Never**
change a document or view property (FreeCAD records those in the undo history and the file).
Hidden components and mesh bodies the same way; nothing for a body hidden because the timeline
marker stands before it (it does not exist at that point). Keep the hover cheap on big designs
(cache the ghost per body until its shape changes).

## 4. Diagonal drag arrows on Fillet and Chamfer

Luca: "they only face the cardinal directions. in fusion, any dragging done on an angle has an
arrow that is diagonal. extruding at an angle already has diagonal arrows. So chamfers and
fillets should also be on an angle."

Why: `sciforge/fillet_ui.py` `_update_arrows` (~line 1702) puts the arrow lying on one of the two
faces, pointing away from the edge (directions from `blend.arrow_spots`); on a box those faces
are square to the axes. Build: the arrow points out of the material along the line halfway
between the two faces (diagonal on a 90° edge, follows the real angle on others), starting on the
blend; convert the drag distance along that line into the radius / distance with the spot's
`per_unit` (chord-length fillets already use one). Equal-distance chamfer: the same diagonal
arrow. Two Distances / Distance and Angle: check Fusion's documentation (each distance belongs to
one face, so one arrow per face may be right); write the source in
`docs/sciforge/parity/fillet.md`. The value box (`arrow_box_core.py`) already handles any arrow
direction. Variable-radius and rule fillet arrows the same way.

## Not in this patch

Auto Timeline (AI rebuilds a model with a timeline) and Simulation (static stress) are beta 3.
The VEX items (square-hole centre snaps for Align and Joint, many STEP parts in one assembly) are
not assigned yet: see MEMORY.md.

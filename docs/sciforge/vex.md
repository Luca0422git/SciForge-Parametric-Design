# VEX robots in SciForge

A short page for a VEX V5 team that builds its robot from VEX's parts, the way it does in
Fusion. (The details and the sources: `docs/sciforge/parity/vex-assembly.md`.)

## 1. Get the parts in

- VEX publishes a STEP file (`.step`, `.stp`) for every part on its product pages. Download
  the ones you need into one folder (they are for personal and educational use).
- **INSERT > Insert STEP**, then pick **several files at once** (Ctrl-click or Shift-click in
  the file window). Each file becomes a component named after it; they come in side by side,
  and the Move arrows let you place them. One Ctrl+Z takes the whole insert back.
- The **Data Panel** works too: **Upload** takes several files at once; select STEP cards and
  right-click > **Insert into Current Design**, or drag a card into the 3D view.
- Inserting the **same file again** gives another copy of the same part ("screw:2",
  "screw:3"...), linked to the first: it is lighter than a second import, and the parts list
  counts them as one part.

## 2. Use inches

Browser > the design's row > Document Settings > **Change Active Units** > Inch. VEX sizes are
in inches (holes 0.182 in square, 0.5 in apart).

## 3. Square holes: the centre dots

Fusion has no snap point in the middle of a square hole; SciForge has one (in Joint, Joint
Origin, As-built Joint, Duplicate With Joints and Align):

- Move the mouse onto the metal **next to a square hole**, onto its edge, or **into the hole**:
  a blue dot lights up at the hole's centre (with a small triad: the joint's axes). Click.
- Hovering the inside wall of a hole gives three dots on the hole's axis: where it starts,
  half-way, and where it comes out on the other side.
- Right on a corner or the middle of an edge, that point is taken instead (zoom in if the
  dots are crowded).
- Hold **Ctrl** to keep the face you are on while you move to a point on its edge (Fusion's
  Ctrl lock). In Align, hold **Shift** to switch the dots off.
- A joint made on a hole stays on that hole when the part changes later.

## 4. Screws, nuts, standoffs: joints, then Duplicate With Joints

1. **J** (Joint): click the round edge or the underside of the screw's head, then the dot in
   the hole. The screw drops into the hole. OK.
2. Add the nut the same way (its face onto the screw's end, or onto the hole's dot on the
   other side).
3. Select the screw and the nut, **ASSEMBLE > Duplicate With Joints**, then click the next
   holes one after the other: every click puts a joined screw and nut there. OK.

## 5. Frames and speed

- Parts that never move relative to each other (a frame): place them with joints or Align,
  then **ASSEMBLE > Rigid Group** instead of a rigid joint for each pair (Fusion's advice too).
- Hide parts you are not working on (the eye in the browser), or isolate a component
  (right-click > Isolate).
- Big robots are slower in SciForge than in Fusion today: see the speed numbers at the end of
  `parity/vex-assembly.md`.

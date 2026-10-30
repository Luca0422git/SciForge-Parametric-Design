# SPDX-License-Identifier: LGPL-2.1-or-later
"""REBUILD journey, part 3 (real clicks and keys; steps and hand numbers in
journey_rebuild_steps.py): a meshed STL of a plate with two holes (INSERT > Insert Mesh)
rebuilt BY HAND with the normal tools and Compare with Reference, with no AI set up.
Right-click the mesh body > Rebuild with Timeline (AI)...: the window for AI apps (closed),
the mesh is the reference and "<name> (rebuilt)" the body to build in. Create Sketch on XY,
a rectangle typed 80 x 48, E 8. Saved (Ctrl+S, the Save dialog), the design closed and
opened again half way: the reference, its ghost and the active rebuilt body are back.
UTILITIES > AI > Compare with Reference says two round holes about 10 mm across are not cut
yet at (20, 24) and (60, 24); two circles on the top face, E -8 (a cut); Compare again says
done; Finish Rebuild... > Finish: the plate takes the mesh body's name, a timeline of a
sketch, an extrude, a sketch and a cut. Saved again (the version prompt), closed, opened
again: the same plate; its extrude double-clicked and made 10 thick: the holes go through."""

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import journey_rebuild_steps as j

first, second = j.mesh_steps()
h.run(
    "journey_rebuild_mesh",
    first
    + j.reopen_steps("rebuild_half_way", j.mesh_reopened_half_way)
    + second
    + j.reopen_steps("rebuild_finished", j.mesh_reopened_finished)
    + j.mesh_edit_steps()
    + [j.finish_scenario("the mesh rebuild journey")],
    paced_by="state",
)

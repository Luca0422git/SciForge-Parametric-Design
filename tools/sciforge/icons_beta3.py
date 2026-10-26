# SPDX-License-Identifier: LGPL-2.1-or-later
# Beta 3 scaffold icons (orchestrator): the SIMULATION workspace entry. The builders draw their
# own in icons_simulation.py, icons_simresults.py, icons_rebuild.py and icons_vex.py.
# Run inside make_icons.py's namespace (block, poly, iso, ... are its helpers).
# Original artwork in the style of the existing icons.
# flake8: noqa


@icon("workspace_simulation")
def _():
    # a bracket fixed at its foot (hatched) with a force arrow on its arm, coloured from blue at
    # the free end to red at the foot like a stress result
    return (
        rect(6, 34, 14, 8, GREY[1], 1, 'stroke="%s" stroke-width="0.7"' % DARK)
        + line(7, 41, 11, 35, DARK, 1.0)
        + line(11, 41, 15, 35, DARK, 1.0)
        + line(15, 41, 19, 35, DARK, 1.0)
        + poly([(8, 34), (18, 34), (18, 20), (8, 24)], RED[1])
        + poly([(8, 24), (18, 20), (30, 17), (30, 23), (18, 26)], GOLD[1])
        + poly([(30, 17), (42, 14), (42, 20), (30, 23)], BLUE[1])
        + line(38, 4, 38, 12, DARK, 2.2)
        + poly([(34.5, 10), (41.5, 10), (38, 15)], DARK)
    )

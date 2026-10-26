# SPDX-License-Identifier: LGPL-2.1-or-later
# VEX assemblies (beta 3, builder vex): Duplicate With Joints.
# Run inside make_icons.py's namespace (block, poly, iso, ... are its helpers).
# Original artwork in the style of the existing icons.
# flake8: noqa


def _screw(x, y, colors):
    # a screw seen from the side: a round head and its shank
    return rect(x - 5, y, 10, 4, colors[1], 1.5) + rect(x - 1.8, y + 4, 3.6, 10, colors[2], 0.8)


@icon("duplicate_joints")
def _():
    # a plate with a row of square holes; a screw jointed in the first hole (grey), two copies
    # landing in the next holes (blue), a joint mark (orange) on each
    holes = "".join(rect(8 + 12 * k, 34, 5, 3, DARK, 0.4) for k in range(3))
    return (
        poly([(4, 32), (44, 32), (44, 38), (4, 38)], GREY[1])
        + holes
        + _screw(10.5, 18, GREY)
        + _screw(22.5, 18, BLUE)
        + _screw(34.5, 18, BLUE)
        + circle(10.5, 33, 2.2, ORANGE)
        + circle(22.5, 33, 2.2, ORANGE)
        + circle(34.5, 33, 2.2, ORANGE)
        + path("M14 12 Q22 4 30 12", STROKE, 1.6)
        + poly([(30, 12), (26.5, 9.5), (29.5, 7)], STROKE)
    )

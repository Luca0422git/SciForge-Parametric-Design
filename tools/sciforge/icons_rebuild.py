# SPDX-License-Identifier: LGPL-2.1-or-later
# Auto Timeline icons (beta 3, builder at-tools): Rebuild with Timeline (AI)..., Compare with
# Reference, Finish Rebuild. Run inside make_icons.py's namespace (block, poly, iso, ... are
# its helpers). Original artwork in the style of the existing icons.
# flake8: noqa


def _ghost_box(x, y, z, dx, dy, dz, ox=24, oy=27, s=1.0):
    """The outline of a box drawn dashed: the original kept as the reference."""
    c = lambda a, b, h: iso(a, b, h, ox, oy, s)  # noqa: E731
    corners = [
        c(x, y + dy, z),
        c(x + dx, y + dy, z),
        c(x + dx, y, z),
        c(x + dx, y, z + dz),
        c(x, y, z + dz),
        c(x, y + dy, z + dz),
    ]
    dash = 'stroke-dasharray="2.2,1.8"'
    out = ""
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        out += line(x1, y1, x2, y2, STROKE, 1.4, dash)
    a, b = c(x + dx, y + dy, z + dz), c(x, y + dy, z + dz)
    out += line(a[0], a[1], b[0], b[1], STROKE, 1.4, dash)
    a = c(x + dx, y + dy, z + dz)
    b = c(x + dx, y, z + dz)
    out += line(a[0], a[1], b[0], b[1], STROKE, 1.4, dash)
    a = c(x + dx, y + dy, z + dz)
    b = c(x + dx, y + dy, z)
    out += line(a[0], a[1], b[0], b[1], STROKE, 1.4, dash)
    return out


@icon("rebuild_ai")
def _():
    # the original as a dashed ghost, the rebuild growing inside it in blue, and a timeline
    # of three steps under it
    return (
        _ghost_box(0, 0, 0, 20, 14, 16)
        + block(0, 0, 0, 20, 14, 7, BLUE, 24, 27)
        + rect(8, 40, 32, 5, DARK, 1.5)
        + rect(10, 41.2, 5, 2.6, BLUE[2], 0.6)
        + rect(17, 41.2, 5, 2.6, BLUE[2], 0.6)
        + rect(24, 41.2, 5, 2.6, BLUE[2], 0.6)
        + rect(31, 41.2, 7, 2.6, GREY[2], 0.6)
    )


@icon("rebuild_compare")
def _():
    # the rebuild in grey, a red region it lacks and a green region it has too much
    return (
        block(0, 0, 0, 18, 14, 10, GREY, 22, 28)
        + block(18, 0, 0, 6, 14, 10, ("#f7b3b1", "#ef8b88", RED), 22, 28)
        + block(4, 4, 10, 8, 6, 6, ("#a8ebbd", "#6fd895", GREEN), 22, 28)
    )


@icon("rebuild_finish")
def _():
    # the rebuilt part with its timeline, and a check: it takes the original's place
    return (
        block(0, 0, 0, 20, 14, 12, BLUE, 22, 27)
        + rect(4, 40, 28, 5, DARK, 1.5)
        + rect(6, 41.2, 5, 2.6, BLUE[2], 0.6)
        + rect(13, 41.2, 5, 2.6, BLUE[2], 0.6)
        + rect(20, 41.2, 5, 2.6, BLUE[2], 0.6)
        + circle(37, 36, 8.5, GREEN)
        + path("M33 36 L36 39.5 L41.5 32.5", WHITE, 2.4)
    )

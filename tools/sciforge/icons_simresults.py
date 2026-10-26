# SPDX-License-Identifier: LGPL-2.1-or-later
# The RESULTS tab of the SIMULATION workspace (beta 3, builder sim-results): result tools,
# deformation scales, display options, inspect tools, Finish Results.
# Run inside make_icons.py's namespace (poly, line, circle, rect, path, arrow... are its helpers).
# Original artwork in the style of the existing icons: a small cantilever coloured like a stress
# result (red at the held end, through gold and green, to blue at the free end).
# flake8: noqa

_RESULT = (RED, GOLD[1], GREEN, BLUE[2])


def _beam(bend, x0=9.0, x1=43.0, y=22.0, h=7.0, colours=_RESULT):
    """A beam held at the left, its free end bent down by `bend` px, coloured by segments."""
    n = len(colours)
    out = ""
    for k in range(n):
        xa = x0 + (x1 - x0) * k / n
        xb = x0 + (x1 - x0) * (k + 1) / n
        ya = y + bend * ((xa - x0) / (x1 - x0)) ** 2
        yb = y + bend * ((xb - x0) / (x1 - x0)) ** 2
        out += poly([(xa, ya), (xb, yb), (xb, yb + h), (xa, ya + h)], colours[k])
    return out


def _wall(x=4.0, y=12.0, h=26.0):
    out = rect(x, y, 5, h, GREY[2])
    for k in range(4):
        yy = y + 3 + k * 6
        out += line(x - 1.5, yy + 4, x + 3, yy, DARK, 1.0)
    return out


def _outline(x0=9.0, x1=43.0, y=22.0, h=7.0):
    return rect(
        x0,
        y,
        x1 - x0,
        h,
        "none",
        0,
        'stroke="%s" stroke-width="1.2" stroke-dasharray="2.5,2"' % STROKE,
    )


def _bars(count, x=31.0, y=41.0):
    out = ""
    for k in range(count):
        out += rect(x + k * 5, y - 3 - 2 * k, 3.4, 4 + 2 * k, WHITE, 0.6)
    return out


@icon("simr_deform_none")
def _():
    return _wall() + _beam(0.0)


@icon("simr_deform_actual")
def _():
    return _wall() + _outline() + _beam(2.5)


@icon("simr_deform_half")
def _():
    return _wall() + _outline() + _beam(5.0) + rect(31, 39, 7, 3, WHITE, 0.6)


@icon("simr_deform_adjusted")
def _():
    return _wall() + _outline() + _beam(8.0) + _bars(1)


@icon("simr_deform_x2")
def _():
    return _wall() + _outline() + _beam(11.0) + _bars(2)


@icon("simr_deform_x5")
def _():
    return _wall() + _outline() + _beam(14.0) + _bars(3)


@icon("simr_animate")
def _():
    return (
        _wall()
        + _outline(y=14.0)
        + _beam(9.0, y=14.0)
        + circle(36, 36, 9.5, DBLUE[1])
        + poly([(33, 31), (41.5, 36), (33, 41)], WHITE)
    )


@icon("simr_details")
def _():
    return (
        rect(7, 6, 30, 36, GREY[0], 2.5, 'stroke="%s" stroke-width="1.0"' % GREY[2])
        + _beam(0.0, x0=11.0, x1=33.0, y=11.0, h=5.0)
        + line(12, 23, 31, 23, GREY[2], 1.6)
        + line(12, 28, 27, 28, GREY[2], 1.6)
        + circle(35, 35, 9.5, DBLUE[1])
        + rect(33.6, 33.5, 2.8, 7.0, WHITE, 1.0)
        + circle(35, 30, 1.7, WHITE)
    )


@icon("simr_compare")
def _():
    return (
        _beam(5.0, x0=5.0, x1=22.0, y=16.0, h=5.0)
        + _beam(9.0, x0=27.0, x1=44.0, y=16.0, h=5.0)
        + line(24.5, 8, 24.5, 40, STROKE, 1.4)
    )


@icon("simr_report")
def _():
    return (
        poly([(10, 5), (31, 5), (39, 13), (39, 43), (10, 43)], GREY[0])
        + poly([(31, 5), (39, 13), (31, 13)], GREY[2])
        + _beam(4.0, x0=14.0, x1=34.0, y=16.0, h=5.0)
        + line(14, 31, 34, 31, GREY[2], 1.6)
        + line(14, 36, 30, 36, GREY[2], 1.6)
    )


@icon("simr_mesh")
def _():
    out = _beam(0.0, x0=6.0, x1=42.0, y=14.0, h=20.0)
    for k in range(5):
        x = 6 + k * 9
        out += line(x, 14, x, 34, DARK, 0.9)
        if k < 4:
            out += line(x, 34, x + 9, 14, DARK, 0.9)
    return out + line(6, 24, 42, 24, DARK, 0.9)


@icon("simr_ghost")
def _():
    return (
        _wall()
        + rect(9, 14, 34, 7, GREY[1], 0, 'opacity="0.45"')
        + _outline(y=14.0)
        + _beam(12.0, y=14.0)
    )


@icon("simr_loads")
def _():
    return _wall() + _beam(4.0, y=24.0) + arrow(38, 6, 38, 21, WHITE, 2.4, 6.0)


@icon("simr_probe")
def _():
    return (
        _beam(0.0, x0=5.0, x1=43.0, y=28.0, h=9.0)
        + line(26, 31, 33, 17, DARK, 1.6)
        + circle(26, 31, 2.6, WHITE, DARK, 1.2)
        + rect(27, 6, 18, 11, DARK, 2.0)
        + line(30, 11.5, 42, 11.5, WHITE, 1.8)
    )


@icon("simr_minmax")
def _():
    return (
        _beam(0.0, x0=5.0, x1=43.0, y=22.0, h=8.0)
        + poly([(9, 9), (17, 9), (13, 3)], RED)
        + line(13, 9, 13, 21, DARK, 1.4)
        + poly([(33, 41), (41, 41), (37, 47)], BLUE[2])
        + line(37, 31, 37, 41, DARK, 1.4)
    )


@icon("simr_reaction")
def _():
    return (
        _wall(x=20.0, y=10.0, h=28.0)
        + _beam(3.0, x0=25.0, x1=44.0, y=20.0, h=7.0)
        + arrow(4, 15, 17, 15, GOLD[1], 2.4, 5.5)
        + arrow(4, 33, 17, 33, GOLD[1], 2.4, 5.5)
    )


@icon("simr_slice")
def _():
    return (
        poly([(6, 18), (24, 9), (42, 18), (24, 27)], GREY[0])
        + poly([(6, 18), (24, 27), (24, 41), (6, 32)], GREY[1])
        + poly([(24, 27), (42, 18), (42, 32), (24, 41)], GREY[2])
        + poly([(15, 13.5), (33, 22.5), (33, 36.5), (15, 27.5)], GOLD[1], 'opacity="0.95"')
        + poly([(15, 13.5), (33, 22.5), (33, 28), (15, 19)], RED)
        + poly([(15, 22.5), (33, 31.5), (33, 36.5), (15, 27.5)], BLUE[2])
        + line(11, 9, 37, 40, DBLUE[2], 1.4, 'stroke-dasharray="3,2"')
    )


@icon("simr_point_probe")
def _():
    return (
        poly([(8, 16), (30, 8), (40, 30), (18, 38)], GOLD[1])
        + poly([(8, 16), (30, 8), (34, 17), (12, 25)], RED)
        + circle(25, 24, 3.0, WHITE, DARK, 1.2)
        + line(25, 24, 38, 40, DARK, 1.6)
    )


@icon("simr_iso")
def _():
    return path(
        "M8 30 C 8 14, 22 8, 30 14 C 38 20, 44 30, 34 38 C 24 44, 8 42, 8 30 Z", STROKE, 1.6, GREEN
    ) + path(
        "M15 30 C 15 22, 22 18, 27 21 C 33 25, 34 31, 28 34 C 22 37, 15 36, 15 30 Z",
        DARK,
        1.0,
        GOLD[1],
    )


@icon("simr_solver_data")
def _():
    out = poly([(10, 5), (31, 5), (39, 13), (39, 43), (10, 43)], GREY[0])
    out += poly([(31, 5), (39, 13), (31, 13)], GREY[2])
    for k in range(5):
        out += line(14, 18 + k * 5, 35, 18 + k * 5, GREY[2], 1.4)
    return out + line(22, 16, 22, 40, GREY[2], 1.2)


@icon("simr_convergence")
def _():
    # a chart: a line settling down towards a level band, the last point green
    out = rect(6, 6, 36, 36, WHITE, 1.0, 'stroke="%s" stroke-width="1.2"' % STROKE)
    out += rect(11, 17, 30, 8, GREEN, 0, 'fill-opacity="0.45"')
    out += line(10, 40, 10, 8, DARK, 1.2) + line(10, 40, 40, 40, DARK, 1.2)
    points = [(14, 36), (22, 15), (30, 24), (37, 21)]
    for (xa, ya), (xb, yb) in zip(points, points[1:]):
        out += line(xa, ya, xb, yb, BLUE[2], 2.2)
    for x, y in points[:-1]:
        out += circle(x, y, 2.4, BLUE[2], DARK, 0.8)
    return out + circle(37, 21, 3.2, GREEN, DARK, 0.9)


@icon("simr_finish")
def _():
    return circle(24, 24, 16, GREEN) + path("M15 24 L22 31 L34 17", WHITE, 4)


@icon("simr_range")
def _():
    # the legend's colour bar with its two ends set by hand (two little sliders)
    out = ""
    colours = (RED, GOLD[1], GREEN, BLUE[2])
    for k, c in enumerate(colours):
        out += rect(18, 8 + k * 8, 10, 8, c)
    return (
        out
        + rect(18, 8, 10, 32, "none", 0, 'stroke="%s" stroke-width="1.2"' % STROKE)
        + poly([(8, 13), (15, 16), (8, 19)], WHITE)
        + line(8, 16, 34, 16, WHITE, 1.4)
        + poly([(8, 29), (15, 32), (8, 35)], WHITE)
        + line(8, 32, 34, 32, WHITE, 1.4)
    )

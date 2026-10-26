# SPDX-License-Identifier: LGPL-2.1-or-later
# The SIMULATION workspace's SETUP tab, its browser rows and its dialogs (builder sim-ui, beta 3).
# Run inside make_icons.py's namespace (block, poly, iso, arrow, ... are its helpers).
# Original artwork in the style of the existing icons.
# flake8: noqa

TEAL = "#2bb3b8"
TEAL_D = "#1f8a8e"
PUSH = "#f39b2f"
PRESS = "#e5584b"
WEIGHT = "#9b7be8"
OK_GREEN = "#3cc46a"
BAD_RED = "#e5534b"
HATCH = "#8a929d"


def _hatch(x0, y, x1, step=4.0, h=4.0, color=HATCH):
    out = line(x0, y, x1, y, color, 1.6)
    x = x0 + 1.0
    while x < x1:
        out += line(x, y + 0.6, x - h * 0.8, y + h, color, 1.1)
        x += step
    return out


def _bracket(ox=24, oy=30, s=1.0, colors=GREY):
    return block(-8, -6, 0, 16, 12, 10, colors, ox, oy, s)


def _check(cx, cy, r, color=OK_GREEN):
    return circle(cx, cy, r, color) + path(
        "M %.1f %.1f L %.1f %.1f L %.1f %.1f"
        % (cx - r * 0.5, cy, cx - r * 0.12, cy + r * 0.4, cx + r * 0.55, cy - r * 0.42),
        WHITE,
        max(1.6, r * 0.28),
    )


def _cross(cx, cy, r, color=BAD_RED):
    k = r * 0.42
    return (
        circle(cx, cy, r, color)
        + line(cx - k, cy - k, cx + k, cy + k, WHITE, max(1.6, r * 0.28))
        + line(cx - k, cy + k, cx + k, cy - k, WHITE, max(1.6, r * 0.28))
    )


def _stress_band(x, y, w, h):
    """A small colour bar from blue (low) to red (high), like a result legend."""
    colors = ["#3b6fe0", "#36c3e0", "#3cc46a", "#f2d24a", "#ef6f6c"]
    out = ""
    step = h / float(len(colors))
    for i, c in enumerate(colors):
        out += rect(x, y + h - (i + 1) * step, w, step + 0.2, c)
    return out


@icon("sim_study")
def _():
    return (
        rect(8, 34, 22, 6, GREY[2], 1)
        + _hatch(8, 40, 30)
        + poly([(12, 34), (26, 34), (26, 16), (12, 22)], GREY[1])
        + poly([(12, 22), (26, 16), (40, 12), (40, 19), (26, 23)], BLUE[1])
        + _stress_band(36, 26, 5, 14)
    )


@icon("sim_new_study")
def _():
    return (
        rect(6, 32, 20, 6, GREY[2], 1)
        + _hatch(6, 38, 26)
        + poly([(9, 32), (22, 32), (22, 15), (9, 20)], GREY[1])
        + poly([(9, 20), (22, 15), (34, 11), (34, 18), (22, 22)], BLUE[1])
        + plus_badge(36, 35)
    )


@icon("sim_static_stress")
def _():
    return (
        rect(5, 36, 18, 6, GREY[2], 1)
        + _hatch(5, 42, 23)
        + poly([(8, 36), (20, 36), (20, 18), (8, 23)], "#ef6f6c")
        + poly([(8, 23), (20, 18), (32, 14), (32, 21), (20, 25)], "#f2d24a")
        + poly([(32, 14), (43, 11), (43, 18), (32, 21)], "#3b6fe0")
        + arrow(39, 0, 39, 10, PUSH, 2.4, 6)
    )


@icon("sim_study_other")
def _():
    return (
        rect(8, 10, 32, 28, GREY[1], 3)
        + circle(24, 24, 8, "none", GREY[2], 2.5)
        + line(14, 32, 34, 16, GREY[2], 2.0)
    )


@icon("sim_materials")
def _():
    return (
        rect(6, 22, 14, 14, "#aeb2b8", 2)
        + rect(17, 16, 14, 14, GOLD[1], 2)
        + rect(28, 10, 14, 14, BLUE[2], 2)
        + rect(6, 38, 36, 4, GREY[2], 1)
    )


@icon("sim_constraints")
def _():
    return _bracket(24, 22) + poly([(18, 34), (30, 34), (24, 26)], TEAL) + _hatch(12, 36, 36)


@icon("sim_loads")
def _():
    return _bracket(24, 34) + arrow(24, 2, 24, 22, PUSH, 3.0, 8)


@icon("sim_gravity")
def _():
    return (
        poly([(14, 14), (34, 14), (40, 34), (8, 34)], WEIGHT)
        + circle(24, 10, 4.5, "none", WEIGHT, 2.4)
        + arrow(24, 20, 24, 44, DARK, 2.6, 7)
    )


@icon("sim_contacts")
def _():
    return (
        block(-12, -6, 0, 12, 12, 10, GREY, 22, 30)
        + block(0, -6, 0, 12, 12, 10, BLUE, 22, 30)
        + circle(23, 25, 2.2, OK_GREEN)
        + circle(23, 31, 2.2, OK_GREEN)
    )


@icon("sim_contact_manager")
def _():
    return (
        block(-10, -5, 0, 10, 10, 8, GREY, 16, 24)
        + block(0, -5, 0, 10, 10, 8, BLUE, 16, 24)
        + rect(28, 8, 16, 32, GREY[2], 2)
        + line(31, 15, 41, 15, WHITE, 2)
        + line(31, 22, 41, 22, WHITE, 2)
        + line(31, 29, 41, 29, WHITE, 2)
    )


@icon("sim_dof")
def _():
    return (
        _bracket(24, 30)
        + arrow(24, 18, 42, 10, PUSH, 2.2, 6)
        + arrow(24, 18, 6, 10, PUSH, 2.2, 6)
        + arrow(24, 18, 24, 2, PUSH, 2.2, 6)
    )


@icon("sim_mesh")
def _():
    pts = [(8, 38), (24, 38), (40, 38), (8, 24), (24, 24), (40, 24), (8, 10), (24, 10), (40, 10)]
    out = poly([(8, 38), (40, 38), (40, 10), (8, 10)], BLUE[0])
    for a, b in ((0, 2), (3, 5), (6, 8), (0, 6), (1, 7), (2, 8), (0, 4), (4, 8), (3, 7), (1, 5)):
        out += line(pts[a][0], pts[a][1], pts[b][0], pts[b][1], DBLUE[2], 1.6)
    return out


@icon("sim_local_mesh")
def _():
    out = poly([(6, 40), (42, 40), (42, 8), (6, 8)], BLUE[0])
    for x in (6, 24, 42):
        out += line(x, 8, x, 40, DBLUE[2], 1.4)
    for y in (8, 24, 40):
        out += line(6, y, 42, y, DBLUE[2], 1.4)
    out += line(6, 40, 24, 24, DBLUE[2], 1.2) + line(24, 24, 42, 8, DBLUE[2], 1.2)
    out += rect(24, 8, 18, 16, ORANGE, 0, 'fill-opacity="0.55"')
    for x in (28.5, 33, 37.5):
        out += line(x, 8, x, 24, DARK, 0.9)
    for y in (12, 16, 20):
        out += line(24, y, 42, y, DARK, 0.9)
    return out


@icon("sim_settings")
def _():
    import math as _m

    pts = []
    for i in range(16):
        r = 18 if i % 2 == 0 else 13
        a = _m.radians(i * 22.5)
        pts.append((24 + r * _m.cos(a), 24 + r * _m.sin(a)))
    return poly(pts, GREY[2]) + circle(24, 24, 6, DARK) + circle(24, 24, 3, GREY[0])


@icon("sim_attributes")
def _():
    return (
        rect(6, 8, 36, 32, GREY[1], 2)
        + rect(6, 8, 36, 7, GREY[2], 2)
        + line(18, 15, 18, 40, DARK, 1.0)
        + line(6, 23, 42, 23, DARK, 1.0)
        + line(6, 31, 42, 31, DARK, 1.0)
        + arrow(10, 17, 10, 22, PUSH, 1.6, 3.5)
        + poly([(8, 37), (12, 37), (10, 33)], TEAL)
    )


@icon("sim_precheck")
def _():
    return (
        rect(10, 6, 28, 36, GREY[1], 3)
        + rect(18, 3, 12, 6, GREY[2], 2)
        + line(15, 17, 33, 17, DARK, 2)
        + line(15, 25, 33, 25, DARK, 2)
        + line(15, 33, 27, 33, DARK, 2)
    )


@icon("sim_precheck_ok")
def _():
    return rect(10, 6, 28, 36, GREY[1], 3) + _check(30, 32, 10)


@icon("sim_precheck_warn")
def _():
    return rect(10, 6, 28, 36, GREY[1], 3) + warn_badge(30, 32, 20)


@icon("sim_precheck_error")
def _():
    return rect(10, 6, 28, 36, GREY[1], 3) + _cross(30, 32, 10)


@icon("sim_solve")
def _():
    return (
        rect(4, 8, 40, 26, GREY[2], 3)
        + rect(7, 11, 34, 20, DARK, 1)
        + poly([(19, 14), (19, 28), (31, 21)], OK_GREEN)
        + rect(18, 34, 12, 4, GREY[2], 1)
        + rect(12, 38, 24, 3, GREY[2], 1)
    )


@icon("sim_loadcase")
def _():
    return (
        rect(6, 14, 36, 26, GREY[1], 3)
        + rect(6, 10, 16, 6, GREY[1], 2)
        + arrow(30, 18, 30, 32, PUSH, 2.4, 6)
        + poly([(12, 34), (22, 34), (17, 26)], TEAL)
    )


@icon("sim_results")
def _():
    return (
        poly([(6, 38), (28, 38), (28, 14), (6, 22)], "#3b6fe0")
        + poly([(6, 22), (28, 14), (28, 22), (6, 30)], "#3cc46a")
        + poly([(6, 30), (28, 22), (28, 30), (6, 38)], "#ef6f6c")
        + _stress_band(34, 10, 7, 30)
    )


@icon("sim_fixed")
def _():
    return (
        poly([(14, 30), (34, 30), (24, 12)], TEAL)
        + rect(10, 30, 28, 4, TEAL_D, 1)
        + _hatch(10, 36, 38)
    )


@icon("sim_pin")
def _():
    return (
        circle(24, 24, 15, "none", GREY[2], 5)
        + circle(24, 24, 6, TEAL)
        + line(24, 4, 24, 44, TEAL_D, 3)
    )


@icon("sim_frictionless")
def _():
    return (
        rect(8, 10, 32, 16, GREY[1], 2)
        + circle(14, 30, 4, TEAL)
        + circle(24, 30, 4, TEAL)
        + circle(34, 30, 4, TEAL)
        + _hatch(6, 36, 42)
    )


@icon("sim_displacement")
def _():
    return (
        rect(
            6,
            18,
            20,
            20,
            "none",
            2,
            'stroke="%s" stroke-width="1.6" stroke-dasharray="3 2"' % GREY[2],
        )
        + rect(20, 10, 20, 20, TEAL, 2)
        + arrow(10, 42, 30, 42, TEAL_D, 2.2, 5)
    )


@icon("sim_force")
def _():
    return rect(6, 32, 36, 8, GREY[1], 1) + arrow(24, 4, 24, 30, PUSH, 3.2, 9)


@icon("sim_pressure")
def _():
    out = rect(6, 32, 36, 8, GREY[1], 1)
    for x in (11, 20, 29, 38):
        out += arrow(x, 10, x, 30, PRESS, 2.0, 5.5)
    return out


@icon("sim_moment")
def _():
    return (
        path("M 12 30 A 13 13 0 1 1 30 37", PUSH, 3.4)
        + poly([(26, 42), (35, 38), (27, 31)], PUSH)
        + circle(24, 24, 3, DARK)
    )


@icon("sim_bearing")
def _():
    return (
        circle(24, 26, 15, "none", GREY[2], 5)
        + circle(24, 26, 8, "none", DARK, 1.2)
        + arrow(24, 2, 24, 30, PUSH, 2.8, 7)
    )


@icon("sim_remote_force")
def _():
    return (
        rect(22, 26, 20, 14, GREY[1], 2)
        + line(9, 13, 30, 31, PUSH, 1.6, 'stroke-dasharray="3 2"')
        + circle(9, 13, 3.5, PUSH)
        + arrow(9, 3, 9, 11, PUSH, 2.4, 6)
    )


@icon("sim_stage_done")
def _():
    return _check(24, 24, 14)


@icon("sim_stage_running")
def _():
    return circle(24, 24, 14, "none", BLUE[2], 4) + path("M 24 10 A 14 14 0 0 1 38 24", DBLUE[2], 5)


@icon("sim_stage_waiting")
def _():
    return circle(24, 24, 13, "none", GREY[2], 3)


@icon("sim_stage_failed")
def _():
    return _cross(24, 24, 14)


# Fusion's SETUP commands SciForge does not build yet (greyed on the ribbon, with their own
# pictures so the menus read like Fusion's).
def _minus_badge(cx=37, cy=37, r=8.5):
    return circle(cx, cy, r, BAD_RED) + line(cx - r * 0.5, cy, cx + r * 0.5, cy, WHITE, 2.4)


@icon("sim_simplify")
def _():
    return (
        _bracket(22, 30)
        + ellipse(22, 22, 5.5, 3.2, "none", DARK, 1.4)
        + path("M 9 14 Q 14 6 21 9", ORANGE, 1.8, extra='stroke-dasharray="2.5 2"')
        + _minus_badge(37, 36)
    )


@icon("sim_global_linear")
def _():
    return (
        block(-6, -6, 0, 12, 12, 10, GREY, 16, 30)
        + arrow(28, 14, 44, 14, WEIGHT, 2.4, 6)
        + arrow(28, 24, 44, 24, WEIGHT, 2.4, 6)
        + arrow(28, 34, 44, 34, WEIGHT, 2.4, 6)
    )


@icon("sim_global_angular")
def _():
    return (
        block(-6, -6, 0, 12, 12, 10, GREY, 24, 34)
        + line(24, 4, 24, 44, DARK, 1.6, 'stroke-dasharray="3 2"')
        + path("M 10 14 A 14 6 0 1 0 38 14", WEIGHT, 2.6)
        + poly([(34, 9), (42, 13), (35, 18)], WEIGHT)
    )


@icon("sim_point_mass_auto")
def _():
    return (
        rect(6, 34, 36, 7, GREY[1], 1)
        + line(24, 16, 10, 34, DARK, 1.2)
        + line(24, 16, 24, 34, DARK, 1.2)
        + line(24, 16, 38, 34, DARK, 1.2)
        + circle(24, 14, 8, WEIGHT)
        + circle(21.5, 11.5, 2.2, "#c9b8f5")
    )


@icon("sim_point_mass_manual")
def _():
    return (
        line(4, 28, 44, 28, GREY[2], 1.4, 'stroke-dasharray="3 2"')
        + line(20, 4, 20, 44, GREY[2], 1.4, 'stroke-dasharray="3 2"')
        + circle(20, 28, 8, WEIGHT)
        + circle(17.5, 25.5, 2.2, "#c9b8f5")
        + rect(30, 6, 14, 9, GREY[1], 1.5)
        + line(32.5, 10.5, 41.5, 10.5, DARK, 1.4)
    )


@icon("sim_manual_contacts")
def _():
    return (
        block(-12, -6, 0, 12, 12, 10, GREY, 20, 30)
        + block(0, -6, 0, 12, 12, 10, BLUE, 20, 30)
        + circle(21, 25, 2.2, PUSH)
        + circle(21, 31, 2.2, PUSH)
        + plus_badge(38, 37, 7.5)
    )


@icon("sim_bolt")
def _():
    return (
        rect(6, 20, 36, 8, GREY[1], 1)
        + rect(6, 30, 36, 8, GREY[2], 1)
        + rect(20, 14, 8, 30, "#c9ced6", 1)
        + poly([(14, 8), (34, 8), (36, 14), (12, 14)], "#8a929d")
        + line(20, 40, 28, 38, DARK, 1.0)
        + line(20, 36, 28, 34, DARK, 1.0)
    )


@icon("sim_rigid_connector")
def _():
    import math as _m

    out = circle(24, 24, 16, "none", GREY[2], 3.5)
    for i in range(6):
        a = _m.radians(i * 60 + 15)
        x, y = 24 + 16 * _m.cos(a), 24 + 16 * _m.sin(a)
        out += line(24, 24, x, y, TEAL_D, 1.8) + circle(x, y, 2.2, TEAL)
    return out + circle(24, 24, 4, TEAL)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's RESULTS tab of a Static Stress study, the rules: no FreeCAD, no Qt (unit tested on
their own; the mesh helpers use numpy when it is there, as FreeCAD always has it).

What lives here: the legend's result list (Fusion's result types and their components), units
and conversions, the colour map and its legend, the safety factor targets and the sentence that
says what they mean, the deformation scale and the animation, the outer surface of a tetrahedral
mesh (what is drawn), a ray against that surface (probes), a plane through the mesh (slice
plane), and the report as HTML. The document side is simulation_results.py; the display and
the commands are simulation_results_ui.py. Spec: docs/sciforge/parity/simulation.md, section
"Results"; Fusion's behaviour with sources: docs/sciforge/dev/research/fusion-simulation.md,
section 5.
"""

import html
import math

from . import simulation_core as sim

# -- the result list -------------------------------------------------------------------------------
# Fusion's legend: a first drop-down picks the result type, a second one its component (research
# 5.3 and 5.5). Each entry: (group key, Fusion's name, ((result key, component name), ...)). The
# result keys are simulation_core.RESULTS's.
LEGEND = (
    ("safety", "Safety Factor", (("safety", "Safety Factor"),)),
    (
        "stress",
        "Stress",
        (
            ("von_mises", "Von Mises"),
            ("principal_1", "1st Principal"),
            ("principal_3", "3rd Principal"),
            ("sxx", "Normal XX"),
            ("syy", "Normal YY"),
            ("szz", "Normal ZZ"),
            ("sxy", "Shear XY"),
            ("syz", "Shear YZ"),
            ("szx", "Shear ZX"),
        ),
    ),
    (
        "displacement",
        "Displacement",
        (("displacement", "Total"), ("dx", "X"), ("dy", "Y"), ("dz", "Z")),
    ),
    (
        "strain",
        "Strain",
        (
            ("strain", "Equivalent"),
            ("strain_1", "1st Principal"),
            ("strain_3", "3rd Principal"),
            ("exx", "Normal XX"),
            ("eyy", "Normal YY"),
            ("ezz", "Normal ZZ"),
        ),
    ),
)
# results SciForge works out itself from the solve's strain tensor at each node (the engine lists
# the equivalent strain): (key, Fusion's name)
EXTRA_RESULTS = (
    ("strain_1", "Strain: 1st Principal"),
    ("strain_3", "Strain: 3rd Principal"),
    ("exx", "Strain: Normal XX"),
    ("eyy", "Strain: Normal YY"),
    ("ezz", "Strain: Normal ZZ"),
)
DEFAULT_RESULT = "safety"  # Fusion opens a Static Stress study's results on Safety Factor


def groups():
    """[(group key, name)] in the legend's order."""
    return [(key, name) for key, name, _parts in LEGEND]


def components(group):
    """[(result key, component name)] of a result group."""
    for key, _name, parts in LEGEND:
        if key == group:
            return list(parts)
    return []


def group_of(result):
    """The group key a result key belongs to ("von_mises" -> "stress")."""
    for key, _name, parts in LEGEND:
        if any(r == result for r, _c in parts):
            return key
    return None


def group_name(group):
    for key, name, _parts in LEGEND:
        if key == group:
            return name
    return str(group)


def result_keys():
    return [r for _k, _n, parts in LEGEND for r, _c in parts]


def result_name(result):
    """Fusion's full name of a result: "Stress: Von Mises", "Displacement: X", "Safety Factor"."""
    for key, name in EXTRA_RESULTS:
        if key == result:
            return name
    return sim.result_title(result)


def principal(xx, yy, zz, xy, yz, zx):
    """(largest, smallest) principal value of a symmetric tensor at every node (numpy arrays
    of its components)."""
    np = _np()
    n = len(xx)
    t = np.empty((n, 3, 3))
    t[:, 0, 0], t[:, 1, 1], t[:, 2, 2] = xx, yy, zz
    t[:, 0, 1] = t[:, 1, 0] = xy
    t[:, 1, 2] = t[:, 2, 1] = yz
    t[:, 0, 2] = t[:, 2, 0] = zx
    w = np.linalg.eigvalsh(t)  # ascending
    return w[:, 2], w[:, 0]


# -- units -----------------------------------------------------------------------------------------
# The legend's unit drop-down (research 5.5 and 6): metric or English, switched on the fly, not
# offered for the safety factor or strain (no unit). The first unit of each kind is SciForge's own
# (simulation_core.UNITS: mm, MPa).
UNIT_CHOICES = {
    "stress": ("MPa", "kPa", "Pa", "psi", "ksi"),
    "displacement": ("mm", "cm", "m", "in"),
    "safety": ("",),
    "strain": ("",),
}
# how many of each unit make one of the base unit (MPa, mm)
_PER_BASE = {
    "MPa": 1.0,
    "kPa": 1000.0,
    "Pa": 1.0e6,
    "psi": 145.0377377302092,
    "ksi": 0.1450377377302092,
    "mm": 1.0,
    "cm": 0.1,
    "m": 0.001,
    "in": 1.0 / 25.4,
    "": 1.0,
}


def kind_of(result):
    """ "stress" | "displacement" | "safety" | "strain" for a result key."""
    group = group_of(result)
    return group if group in UNIT_CHOICES else "strain"


def units_for(result):
    return list(UNIT_CHOICES.get(kind_of(result), ("",)))


def base_unit(result):
    return units_for(result)[0]


def convert(value, unit):
    """A value in SciForge's base unit (MPa, mm) given in `unit`. None stays None."""
    if value is None:
        return None
    return float(value) * _PER_BASE.get(unit, 1.0)


def unit_ok(result, unit):
    return unit in units_for(result)


# -- numbers ---------------------------------------------------------------------------------------
def fmt(value, digits=4):
    """A result value as the legend shows it (simulation_core.fmt: 4 significant figures)."""
    if value is None:
        return "-"
    try:
        if value != value:  # NaN
            return "-"
    except TypeError:
        return str(value)
    return sim.fmt(value, digits)


def fmt_plain(value, digits=4):
    """Like fmt() but never with an exponent for everyday sizes (200000, not 2e5): material
    tables."""
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value != value or value == 0 or not (1e-4 <= abs(value) < 1e12):
        return fmt(value, digits)
    decimals = max(0, digits - 1 - int(math.floor(math.log10(abs(value)))))
    text = "%.*f" % (decimals, round(value, decimals))
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def with_unit(value, unit, digits=4):
    text = fmt(value, digits)
    return "%s %s" % (text, unit) if unit and text != "-" else text


# -- colours ---------------------------------------------------------------------------------------
TEXELS = 256  # colour map texture width
BANDS = 9  # Fusion's legend can show colour bands instead of a smooth blend (research 5.5)
NO_VALUE = (0.55, 0.57, 0.6)  # a node with no value (no strength for the safety factor)
# The safety factor target bands (Fusion's guided results, research 5.4): below the lower target,
# between the targets, above the upper target
BAND_COLOURS = {
    "below": (0.91, 0.22, 0.2),
    "meets": (0.98, 0.78, 0.18),
    "above": (0.22, 0.55, 0.95),
}


def scale(result, lo, hi):
    """(lo, hi, reverse) of the colour scale of a result (simulation_core.scale_for: the safety
    factor from 0 to the cap with red low, everything else min to max with red high)."""
    return sim.scale_for(result, lo, hi)


def position(value, lo, hi, reverse=False):
    """Where `value` sits on the colour map, 0 (blue) .. 1 (red); None for no value."""
    if value is None or value != value:
        return None
    if lo is None or hi is None or hi - lo <= 1e-300:
        t = 0.0
    else:
        t = (float(value) - lo) / (hi - lo)
    t = min(max(t, 0.0), 1.0)
    return 1.0 - t if reverse else t


def map_colour(t, banded=False):
    """(r, g, b) of colour map position t (0 blue .. 1 red); banded: the colour of t's band."""
    if t is None:
        return NO_VALUE
    t = min(max(float(t), 0.0), 1.0)
    if banded:
        band = min(int(t * BANDS), BANDS - 1)
        t = (band + 0.5) / BANDS
    return sim.colour(t, 0.0, 1.0)


def target_band(value, lower, upper):
    """ "below" | "meets" | "above" for a safety factor and the two targets (None: no value)."""
    if value is None or value != value:
        return None
    if value < lower:
        return "below"
    if value > upper:
        return "above"
    return "meets"


def texture_rows(banded=False, targets=None):
    """The colour map texture: two rows of TEXELS RGB bytes, the map (blue left, red right) and
    the colour of "no value". With `targets` (lower, upper) the safety factor target bands
    (the texture position of a safety factor is 1 - value / SAFETY_CAP)."""
    row = bytearray()
    for i in range(TEXELS):
        t = (i + 0.5) / TEXELS
        if targets is not None:
            value = (1.0 - t) * sim.SAFETY_CAP
            colour = BAND_COLOURS[target_band(value, targets[0], targets[1])]
        else:
            colour = map_colour(t, banded)
        row.extend(int(round(255 * min(max(c, 0.0), 1.0))) for c in colour)
    grey = bytearray(int(round(255 * c)) for c in NO_VALUE) * TEXELS
    return bytes(row + grey)


def texture_coordinate(t):
    """(s, t) texture coordinate of a colour map position (None = the "no value" row)."""
    if t is None:
        return (0.5, 0.75)
    return (min(max(float(t), 0.0), 1.0), 0.25)


# -- the legend ------------------------------------------------------------------------------------
def legend(result, stats, unit=None, count=9, banded=False, targets=None):
    """What the legend shows for a result: {"title", "group", "component", "unit", "ticks":
    [(value in unit, text, position 0..1 from the bottom)], "min", "max" (in unit, texts),
    "reverse", "lo", "hi" (the colour scale, base unit), "bands"}.

    `stats`: {"min", "max"} of the result in SciForge's base unit (simulation.summary()'s
    stats). The safety factor's scale is 0 .. SAFETY_CAP whatever its values (Fusion shows it
    capped at 15); with `targets` its bar shows the three target bands."""
    unit = unit if unit is not None and unit_ok(result, unit) else base_unit(result)
    lo_v = stats.get("min") if stats else None
    hi_v = stats.get("max") if stats else None
    lo, hi, reverse = scale(result, lo_v, hi_v)
    if result == "safety":
        count = 11  # 0, 1.5, 3 ... 15: round numbers on the capped scale
    ticks = []
    for value in sim.legend_ticks(lo, hi, count):
        pos = 0.0 if hi is None or lo is None or hi == lo else (value - lo) / (hi - lo)
        shown = convert(value, unit)
        ticks.append((shown, fmt(shown), pos))
    group = group_of(result)
    component = next((c for r, c in components(group) if r == result), "")
    out = {
        "result": result,
        "title": result_name(result),
        "group": group_name(group),
        "component": component,
        "unit": unit,
        "ticks": ticks,
        "min": convert(lo_v, unit),
        "max": convert(hi_v, unit),
        "min_text": with_unit(convert(lo_v, unit), unit),
        "max_text": with_unit(convert(hi_v, unit), unit),
        "lo": lo,
        "hi": hi,
        "reverse": reverse,
        "banded": bool(banded),
        "bands": None,
    }
    if result == "safety" and targets is not None:
        out["bands"] = [
            ("above", "Above %s" % fmt(targets[1]), BAND_COLOURS["above"]),
            ("meets", "%s to %s" % (fmt(targets[0]), fmt(targets[1])), BAND_COLOURS["meets"]),
            ("below", "Below %s" % fmt(targets[0]), BAND_COLOURS["below"]),
        ]
    return out


# -- the safety factor target ----------------------------------------------------------------------
# Fusion's Results Details judge the lowest safety factor against a lower and an upper target
# (research 5.4; Autodesk Learn: "set as three with a lower limit and six is the upper limit").
DEFAULT_TARGETS = (3.0, 6.0)


def targets(lower=None, upper=None):
    """Valid (lower, upper) targets: positive, lower <= upper, defaults for what is missing."""
    lo = DEFAULT_TARGETS[0] if lower is None else float(lower)
    hi = DEFAULT_TARGETS[1] if upper is None else float(upper)
    lo = min(max(lo, 0.01), sim.SAFETY_CAP)
    hi = min(max(hi, lo), sim.SAFETY_CAP)
    return lo, hi


def verdict(min_safety, lower, upper):
    """(state, headline, advice) for the lowest safety factor of a study: state "below" /
    "meets" / "above" / "none"; the headline says it in a sentence (SciForge's words); the advice
    is a list of short sentences."""
    if min_safety is None or min_safety != min_safety:
        return (
            "none",
            "No safety factor: the study material has no strength to compare the stress with.",
            ["Choose a study material with a yield strength (Study Materials)."],
        )
    value = fmt(min_safety)
    state = target_band(min_safety, lower, upper)
    if state == "below":
        head = "Below the safety factor target: the lowest safety factor is %s (target %s)." % (
            value,
            fmt(lower),
        )
        advice = [
            "Add material where the stress is high (thicker walls, bigger fillets).",
            "Choose a stronger material in Study Materials.",
            "Check that the loads and constraints are what you meant.",
        ]
        if min_safety < 1.0:
            head += " Below 1 the part bends for good (it yields) under these loads."
        else:
            advice.insert(
                0,
                "Above 1 the part does not yield, but it has less margin than the target asks.",
            )
        return state, head, advice
    if state == "above":
        return (
            state,
            "Meets the safety factor target with room to spare: the lowest safety factor is %s "
            "(more than %s)." % (value, fmt(upper)),
            [
                "The part is much stronger than needed: material could be removed to make it "
                "lighter.",
            ],
        )
    return (
        state,
        "Meets the safety factor target: the lowest safety factor is %s (target %s to %s)."
        % (value, fmt(lower), fmt(upper)),
        ["Make the mesh finer near the lowest safety factor to confirm the number."],
    )


LIMITS = (
    "Linear static stress: small deflections, the material stays elastic and the same in every "
    "direction (3D-printed parts are not), loads do not change. Results are a guide, not a "
    "guarantee."
)
OUT_OF_DATE = (
    "These results are out of date: the design or the study changed after the solve. Solve "
    "again to see results for the design as it is now."
)
NO_RESULTS = "This study has no results yet: solve it (SETUP > Solve)."


# -- deformation and animation ---------------------------------------------------------------------
DEFORMATION_DEFAULT = "adjusted"  # Fusion draws Static Stress results Adjusted (research 5.6)


def deformations():
    """[(key, name)] of Fusion's deformation scale choices, in its order."""
    return [(k, n) for k, n, _m in sim.DEFORMATIONS]


def deformation_name(key):
    for k, n, _m in sim.DEFORMATIONS:
        if k == key:
            return n
    return str(key)


def deformation_factor(key, max_displacement, diagonal):
    """How many times the true displacement is drawn (simulation_core.deformation_factor)."""
    return sim.deformation_factor(key, max_displacement, diagonal)


ANIMATION_MODES = (("once", "Play Once"), ("loop", "Loop"), ("mirror", "Mirror Loop"))
ANIMATION_SPEEDS = (0.25, 0.5, 1.0, 1.5, 2.0)  # Fusion: 0.25x to 2x (research 5.7)
ANIMATION_FRAMES = (10, 20, 40, 60, 100)  # Fusion: up to 100 steps
SECONDS_PER_PASS = 1.2  # undeformed to deformed at 1x


def animation_fraction(step, frames, mode):
    """How much of the deformation is drawn at animation step `step` (0, 1, 2, ...): "once"
    goes 0 -> 1 and stays; "loop" 0 -> 1 then starts again; "mirror" 0 -> 1 -> 0 ..."""
    frames = max(int(frames), 2)
    last = frames - 1
    if mode == "once":
        return min(step, last) / float(last)
    if mode == "mirror":
        cycle = 2 * last
        k = step % cycle
        return (k if k <= last else cycle - k) / float(last)
    return (step % frames) / float(last)


def animation_done(step, frames, mode):
    return mode == "once" and step >= max(int(frames), 2) - 1


def animation_interval_ms(speed, frames):
    """Milliseconds between two animation steps."""
    speed = min(max(float(speed), 0.05), 10.0)
    return max(15, int(round(1000.0 * SECONDS_PER_PASS / speed / max(int(frames) - 1, 1))))


# -- the mesh: outer surface, edges, probes, slices (numpy) ----------------------------------------
# FreeCAD's tetrahedra (SMDS order): corners 0-3, then the mid-edge nodes of 01, 12, 20, 03, 13,
# 23 (checked on CalculiX results read by FreeCAD 1.1.4).
TET_FACES = ((0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 3, 1), (1, 2, 3, 0))  # 3 corners + the other one
MID = {}
for _i, (_a, _b) in enumerate(((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))):
    MID[(_a, _b)] = MID[(_b, _a)] = 4 + _i
# a 10-node tetrahedron as 8 straight ones (corner pieces, and the inner octahedron cut along
# its 02-13 diagonal): used to cut the mesh with a plane
SPLIT10 = (
    (0, 4, 6, 7),
    (1, 4, 5, 8),
    (2, 6, 5, 9),
    (3, 7, 8, 9),
    (6, 8, 4, 5),
    (6, 8, 5, 9),
    (6, 8, 9, 7),
    (6, 8, 7, 4),
)
FEATURE_ANGLE = 30.0  # degrees between neighbouring faces that make a drawn edge


def _np():
    import numpy

    return numpy


def surface(points, tets):
    """The outer surface of a tetrahedral mesh, ready to draw.

    points: (n, 3) node coordinates; tets: (m, 4) or (m, 10) node indices (SMDS order).
    Returns {"nodes": (k,) indices into points of the surface nodes, "triangles": (t, 3) into
    "nodes" (quadratic faces split in 4, all facing out), "faces": (f, 3) corner triangles into
    "nodes" (facing out), "lines": (e, 2 or 3) polylines into "nodes" along every surface
    element edge (Show Mesh), "features": the same along the sharp edges of the surface (the
    model's outline)}."""
    np = _np()
    points = np.asarray(points, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.ndim != 2 or len(tets) == 0:
        empty = np.zeros((0, 3), dtype=np.int64)
        return {
            "nodes": np.zeros(0, dtype=np.int64),
            "triangles": empty,
            "faces": empty,
            "lines": np.zeros((0, 2), dtype=np.int64),
            "features": np.zeros((0, 2), dtype=np.int64),
        }
    quadratic = tets.shape[1] >= 10
    m = len(tets)
    rows = []
    for a, b, c, d in TET_FACES:
        rows.append(tets[:, [a, b, c, d]])
    faces = np.concatenate(rows)  # (4m, 4): corners a, b, c and the other corner d
    which = np.repeat(np.arange(4), m)  # the TET_FACES entry of each row
    owner = np.tile(np.arange(m), 4)  # the tetrahedron of each row
    key = np.sort(faces[:, :3], axis=1)
    n = np.int64(max(int(points.shape[0]), int(tets.max()) + 1))
    code = (key[:, 0] * n + key[:, 1]) * n + key[:, 2]
    _uniq, first, counts = np.unique(code, return_index=True, return_counts=True)
    keep = first[counts == 1]
    keep.sort()
    abc = faces[keep, :3].copy()
    d = faces[keep, 3]
    pa, pb, pc, pd = points[abc[:, 0]], points[abc[:, 1]], points[abc[:, 2]], points[d]
    normal = np.cross(pb - pa, pc - pa)
    flip = np.einsum("ij,ij->i", normal, pd - pa) > 0  # pointing into the element: turn it
    abc[flip, 1], abc[flip, 2] = abc[flip, 2].copy(), abc[flip, 1].copy()
    if quadratic:
        # the mid nodes of each face's edges ab, bc, ca (corners b and c swapped: ca, bc, ab)
        cols = np.array([[MID[(a, b)], MID[(b, c)], MID[(c, a)]] for a, b, c, _d in TET_FACES])
        rowcols = cols[which[keep]]
        rowcols[flip] = rowcols[flip][:, ::-1]
        mids = tets[owner[keep][:, None], rowcols]
        A, B, C = abc[:, 0], abc[:, 1], abc[:, 2]
        AB, BC, CA = mids[:, 0], mids[:, 1], mids[:, 2]
        tris = np.concatenate(
            [
                np.stack([A, AB, CA], axis=1),
                np.stack([AB, B, BC], axis=1),
                np.stack([CA, BC, C], axis=1),
                np.stack([AB, BC, CA], axis=1),
            ]
        )
    else:
        mids = None
        tris = abc
    used = np.unique(tris)
    remap = np.full(int(n), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out_tris = remap[tris]
    out_faces = remap[abc]
    out_mids = remap[mids] if mids is not None else None
    lines, features = _edges(points[used], out_faces, out_mids)
    return {
        "nodes": used,
        "triangles": out_tris,
        "faces": out_faces,
        "lines": lines,
        "features": features,
    }


def _edges(points, faces, mids):
    """(k, 2 or 3) polylines (node indices, the mid node in the middle when there is one) of
    every edge of the corner triangles, and of the edges whose two faces meet at more than
    FEATURE_ANGLE (or that do not have exactly two faces)."""
    np = _np()
    width = 3 if mids is not None else 2
    if len(faces) == 0:
        empty = np.zeros((0, width), dtype=np.int64)
        return empty, empty
    a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
    normal = np.cross(points[b] - points[a], points[c] - points[a])
    length = np.linalg.norm(normal, axis=1)
    normal = normal / np.where(length > 0, length, 1.0)[:, None]
    pairs = np.concatenate([np.stack([a, b], 1), np.stack([b, c], 1), np.stack([c, a], 1)])
    face_of = np.tile(np.arange(len(faces)), 3)
    key = np.sort(pairs, axis=1)
    n = np.int64(len(points) + 1)
    code = key[:, 0] * n + key[:, 1]
    order = np.argsort(code, kind="stable")
    code_sorted = code[order]
    starts = np.flatnonzero(np.r_[True, code_sorted[1:] != code_sorted[:-1]])
    counts = np.diff(np.r_[starts, len(code_sorted)])
    rows = order[starts]
    if mids is not None:
        middle = np.concatenate([mids[:, 0], mids[:, 1], mids[:, 2]])
        lines = np.stack([key[rows, 0], middle[rows], key[rows, 1]], axis=1)
    else:
        lines = key[rows]
    sharp = counts != 2
    two = np.flatnonzero(counts == 2)
    if len(two):
        f1 = face_of[order[starts[two]]]
        f2 = face_of[order[starts[two] + 1]]
        dots = np.einsum("ij,ij->i", normal[f1], normal[f2])
        sharp[two] = dots < math.cos(math.radians(FEATURE_ANGLE))
    return lines, lines[sharp]


def ray_hit(origin, direction, vertices, triangles):
    """The nearest triangle a ray meets: (distance along the ray, triangle index, (w0, w1, w2)
    barycentric weights) or None. Both sides of a triangle count."""
    np = _np()
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    if len(triangles) == 0:
        return None
    o = np.asarray(origin, dtype=float)
    dvec = np.asarray(direction, dtype=float)
    v0 = vertices[triangles[:, 0]]
    e1 = vertices[triangles[:, 1]] - v0
    e2 = vertices[triangles[:, 2]] - v0
    p = np.cross(dvec, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = o - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ dvec) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    eps = 1e-9
    hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (t > 0)
    if not hit.any():
        return None
    distance = np.where(hit, t, np.inf)
    i = int(np.argmin(distance))
    return float(t[i]), i, (float(1.0 - u[i] - v[i]), float(u[i]), float(v[i]))


def nearest(points, point, candidates=None):
    """Index (into points) of the point nearest to `point`, among `candidates` if given."""
    np = _np()
    points = np.asarray(points, dtype=float)
    idx = np.arange(len(points)) if candidates is None else np.asarray(candidates, dtype=np.int64)
    if len(idx) == 0:
        return None
    dist = np.linalg.norm(points[idx] - np.asarray(point, dtype=float), axis=1)
    return int(idx[int(np.argmin(dist))])


def straight_tets(tets):
    """(m', 4) straight tetrahedra of a mesh: 10-node ones split in 8."""
    np = _np()
    tets = np.asarray(tets, dtype=np.int64)
    if tets.ndim != 2 or len(tets) == 0:
        return np.zeros((0, 4), dtype=np.int64)
    if tets.shape[1] < 10:
        return tets[:, :4]
    return np.concatenate([tets[:, list(piece)] for piece in SPLIT10])


def cut(points, values, tets, origin, normal):
    """Where the plane (origin, normal) cuts a mesh of straight tetrahedra (straight_tets): a
    list of triangles [(p0, p1, p2), ...] with their values [(v0, v1, v2), ...] interpolated
    along the cut edges, each wound to face against the normal. values: one per point (NaN
    allowed)."""
    np = _np()
    points = np.asarray(points, dtype=float)
    values = np.asarray(values, dtype=float)
    tets = np.asarray(tets, dtype=np.int64)
    n = np.asarray(normal, dtype=float)
    length = float(np.linalg.norm(n))
    if length < 1e-12 or len(tets) == 0:
        return [], []
    n = n / length
    dist = (points - np.asarray(origin, dtype=float)) @ n
    d = dist[tets]
    crossing = (d.min(axis=1) < 0) & (d.max(axis=1) > 0)
    tris, vals = [], []
    for tet, dd in zip(tets[crossing], d[crossing]):
        above = [k for k in range(4) if dd[k] > 0]
        below = [k for k in range(4) if dd[k] <= 0]

        def at(i, j):
            t = dd[i] / (dd[i] - dd[j])
            a, b = tet[i], tet[j]
            return points[a] + t * (points[b] - points[a]), values[a] + t * (values[b] - values[a])

        if len(above) == 1 or len(below) == 1:
            lone, others = (above[0], below) if len(above) == 1 else (below[0], above)
            corners = [at(lone, k) for k in others]
            tris.append(tuple(c[0] for c in corners))
            vals.append(tuple(c[1] for c in corners))
        else:
            a, b = above
            c, e = below
            quad = [at(a, c), at(a, e), at(b, e), at(b, c)]
            tris.append((quad[0][0], quad[1][0], quad[2][0]))
            vals.append((quad[0][1], quad[1][1], quad[2][1]))
            tris.append((quad[0][0], quad[2][0], quad[3][0]))
            vals.append((quad[0][1], quad[2][1], quad[3][1]))
    # every triangle wound to face against the normal (out of the half that is kept), so they
    # all take the light the same way
    for k, (p0, p1, p2) in enumerate(tris):
        if float(np.dot(np.cross(p1 - p0, p2 - p0), n)) > 0:
            tris[k] = (p0, p2, p1)
            v0, v1, v2 = vals[k]
            vals[k] = (v0, v2, v1)
    return tris, vals


# -- the report ------------------------------------------------------------------------------------
def _cell(value):
    return "<td>%s</td>" % html.escape(str(value))


def _table(headers, rows, cls=""):
    out = ['<table class="%s">' % cls if cls else "<table>"]
    out.append("<tr>%s</tr>" % "".join("<th>%s</th>" % html.escape(h) for h in headers))
    for row in rows:
        out.append("<tr>%s</tr>" % "".join(_cell(c) for c in row))
    out.append("</table>")
    return "\n".join(out)


REPORT_STYLE = """
body { font-family: Segoe UI, Helvetica, Arial, sans-serif; margin: 32px auto; max-width: 980px;
       color: #1f2329; }
h1 { font-size: 26px; margin-bottom: 4px; }
h2 { font-size: 19px; border-bottom: 2px solid #3fa9f5; padding-bottom: 4px; margin-top: 32px; }
h3 { font-size: 15px; margin-bottom: 6px; }
.meta { color: #5b6573; }
table { border-collapse: collapse; margin: 8px 0 16px 0; }
th, td { border: 1px solid #c9ced6; padding: 4px 10px; text-align: left; font-size: 13px; }
th { background: #eef1f5; }
.verdict { padding: 10px 14px; border-radius: 6px; margin: 12px 0; }
.below { background: #fde2e1; } .meets { background: #fff3cd; } .above { background: #dbeafe; }
.none { background: #eef1f5; }
.warning { background: #fff3cd; padding: 8px 12px; border-left: 4px solid #e8a400; }
.limits { color: #5b6573; font-size: 12px; }
figure { display: inline-block; margin: 8px 12px 16px 0; vertical-align: top; }
figure img { border: 1px solid #c9ced6; max-width: 460px; }
figcaption { font-size: 13px; color: #3b4453; }
"""


def report_html(data):
    """The study report (Fusion's RESULTS > Report, research 5.12) as one HTML page.

    data: {"title", "author", "date", "version", "design", "study", "study_type", "settings":
    [(name, value)], "materials": [row], "constraints": [row], "loads": [row], "contacts": text,
    "mesh": [(name, value)], "results": [(result, min, max, unit)], "bodies": [row],
    "verdict": (state, headline, advice), "out_of_date": bool, "images": [(caption, src)],
    "notes": [text]} (any key may be missing)."""
    esc = html.escape
    title = data.get("title") or "Static Stress report"
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>%s</title>" % esc(title),
        "<style>%s</style></head><body>" % REPORT_STYLE,
        "<h1>%s</h1>" % esc(title),
    ]
    meta = [
        data.get("design") and "Design: %s" % data["design"],
        data.get("study") and "Study: %s" % data["study"],
        data.get("author") and "Author: %s" % data["author"],
        data.get("date") and "Date: %s" % data["date"],
        data.get("version") and "Made with SciForge %s" % data["version"],
    ]
    parts.append('<p class="meta">%s</p>' % esc(" | ".join(m for m in meta if m)))
    if data.get("out_of_date"):
        parts.append('<p class="warning">%s</p>' % esc(OUT_OF_DATE))
    verdict_data = data.get("verdict")
    if verdict_data:
        state, head, advice = verdict_data
        parts.append('<div class="verdict %s"><b>%s</b>' % (esc(state), esc(head)))
        if advice:
            parts.append("<ul>%s</ul>" % "".join("<li>%s</li>" % esc(a) for a in advice))
        parts.append("</div>")
    parts.append('<p class="limits">%s</p>' % esc(LIMITS))

    parts.append("<h2>Study</h2>")
    rows = [("Study type", data.get("study_type") or "Static Stress")]
    rows += list(data.get("settings") or [])
    parts.append(_table(["Setting", "Value"], rows))

    parts.append("<h2>Materials</h2>")
    parts.append(
        _table(
            [
                "Body",
                "Study material",
                "Young's modulus (MPa)",
                "Poisson's ratio",
                "Density (kg/m3)",
                "Yield strength (MPa)",
                "Ultimate strength (MPa)",
                "Safety factor based on",
            ],
            data.get("materials") or [],
        )
    )
    parts.append("<h2>Constraints and loads</h2>")
    parts.append("<h3>Constraints</h3>")
    if data.get("constraints"):
        parts.append(_table(["Name", "Type", "On", "Details"], data["constraints"]))
    else:
        parts.append("<p>None.</p>")
    parts.append("<h3>Loads</h3>")
    if data.get("loads"):
        parts.append(_table(["Name", "Type", "On", "Details"], data["loads"]))
    else:
        parts.append("<p>None.</p>")
    if data.get("contacts"):
        parts.append("<h3>Contacts</h3><p>%s</p>" % esc(data["contacts"]))

    parts.append("<h2>Mesh</h2>")
    parts.append(_table(["", "Value"], data.get("mesh") or []))

    parts.append("<h2>Results</h2>")
    result_rows = [
        (result_name(key), fmt(lo), fmt(hi), unit or "-")
        for key, lo, hi, unit in data.get("results") or []
    ]
    parts.append(_table(["Result", "Min", "Max", "Unit"], result_rows))
    if data.get("bodies"):
        parts.append("<h3>Per body</h3>")
        parts.append(
            _table(
                [
                    "Body",
                    "Material",
                    "Strength (MPa)",
                    "Max von Mises (MPa)",
                    "Min safety factor",
                    "Max displacement (mm)",
                ],
                data["bodies"],
            )
        )
    images = data.get("images") or []
    if images:
        parts.append("<h2>Pictures</h2>")
        for caption, src in images:
            parts.append(
                '<figure><img src="%s" alt="%s"><figcaption>%s</figcaption></figure>'
                % (esc(src, quote=True), esc(caption, quote=True), esc(caption))
            )
    for note in data.get("notes") or []:
        parts.append('<p class="limits">%s</p>' % esc(note))
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"

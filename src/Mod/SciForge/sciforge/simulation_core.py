# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's Simulation workspace, limited to the Static Stress study (outline 7.18): the rules,
without FreeCAD and without Qt, so they are unit tested on their own.

What lives here: the study types Fusion lists (only Static Stress is available in SciForge),
the study settings and their defaults, the kinds of constraints and loads with their options
(checked and described in plain sentences), the mesh size rule, the units, the safety factor,
result statistics, the colour scale of the results and its legend, and the pre-check (what is
missing before a solve). The document side (studies in the design, FreeCAD's FEM objects,
Gmsh and CalculiX) is simulation.py; the dialogs are simulation_ui.py and the results display
simulation_results_ui.py. Spec: docs/sciforge/parity/simulation.md; Fusion's behaviour with
sources: docs/sciforge/dev/research/fusion-simulation.md.

Units inside SciForge's simulation: millimetres (mm), newtons (N), megapascals (MPa = N/mm2),
newton-millimetres (N mm) for moments, tonnes per cubic millimetre are never shown: densities
are kept in kg/m3 and converted where CalculiX needs them (FreeCAD's writer does that).
"""

import json
import math

# -- study types -----------------------------------------------------------------------------------
# (key, Fusion's name, available in SciForge). The New Study dialog shows them all, like Fusion,
# and greys out every type SciForge cannot solve yet with a sentence that says so.
STUDY_TYPES = (
    ("static_stress", "Static Stress", True),
    ("modal", "Modal Frequencies", False),
    ("thermal", "Thermal", False),
    ("thermal_stress", "Thermal Stress", False),
    ("buckling", "Structural Buckling", False),
    ("nonlinear_static", "Nonlinear Static Stress", False),
    ("event", "Event Simulation", False),
    ("quasi_static", "Quasi-Static Event Simulation", False),
    ("shape_optimization", "Shape Optimization", False),
    ("electronics_cooling", "Electronics Cooling", False),
    ("injection_molding", "Injection Molding", False),
)
NOT_AVAILABLE = "SciForge solves Static Stress studies only (for now)."


def study_type_title(key):
    for k, title, _ok in STUDY_TYPES:
        if k == key:
            return title
    return str(key)


def study_type_available(key):
    return any(k == key and ok for k, _t, ok in STUDY_TYPES)


# -- settings --------------------------------------------------------------------------------------
# A study's settings (Fusion: Study Settings). Kept as JSON in the study object.
DEFAULT_SETTINGS = {
    "mesh": {
        "size_pct": 10.0,  # Average Element Size, % of the model size (see model_size())
        "order": "parabolic",  # parabolic (2nd order, Fusion's default) | linear
        "curved": True,  # curved (mid-side nodes on the geometry) parabolic elements
        "scale_per_part": False,  # Fusion: Scale Mesh Size Per Part
        "min_pct": 20.0,  # smallest element, % of the average size
        "max_turn": 60.0,  # degrees an element may turn along a curve
    },
    "gravity": {"on": False, "direction": [0.0, 0.0, -1.0], "g": 9806.65},  # mm/s2
    "safety_basis": "yield",  # yield | ultimate: what the safety factor divides
    "contacts": "bonded",  # bodies that touch are glued (Fusion's automatic contacts)
    "contact_tolerance": 0.1,  # mm: faces closer than this touch
}

MESH_ORDERS = ("parabolic", "linear")
SAFETY_BASES = ("yield", "ultimate")


def settings(data=None):
    """The full settings of a study: the defaults with `data` (a dict or JSON) on top,
    unknown keys dropped, wrong types replaced by the default."""
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            data = {}
    data = data if isinstance(data, dict) else {}
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    for key, default in DEFAULT_SETTINGS.items():
        value = data.get(key)
        if isinstance(default, dict):
            if isinstance(value, dict):
                for sub, sub_default in default.items():
                    if sub in value and _same_kind(value[sub], sub_default):
                        out[key][sub] = value[sub]
        elif value is not None and _same_kind(value, default):
            out[key] = value
    if out["mesh"]["order"] not in MESH_ORDERS:
        out["mesh"]["order"] = DEFAULT_SETTINGS["mesh"]["order"]
    if out["safety_basis"] not in SAFETY_BASES:
        out["safety_basis"] = DEFAULT_SETTINGS["safety_basis"]
    out["mesh"]["size_pct"] = min(max(float(out["mesh"]["size_pct"]), 0.5), 50.0)
    return out


def _same_kind(value, default):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, (list, tuple))
    return isinstance(value, type(default))


def model_size(bbox):
    """The model size the mesh size is a percentage of: the diagonal of the bounding box of
    everything in the study (xmin, ymin, zmin, xmax, ymax, zmax), in mm."""
    dx, dy, dz = (bbox[3] - bbox[0]), (bbox[4] - bbox[1]), (bbox[5] - bbox[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def element_size(bbox, size_pct):
    """Average element size (mm) for `size_pct` % of the model size, never below 0.05 mm."""
    return max(model_size(bbox) * float(size_pct) / 100.0, 0.05)


# -- constraints and loads -------------------------------------------------------------------------
# Every kind: Fusion's name, what may be picked (faces / edges / vertices; "round" = only
# cylindrical faces, "flat" = only planar faces), its options with their defaults, and whether
# SciForge solves it yet (a kind not built yet stays in the dialog, greyed, with a sentence).
TARGETS_ANY = ("faces", "edges", "vertices")

CONSTRAINTS = {
    "fixed": {
        "title": "Fixed",
        "targets": TARGETS_ANY,
        "options": {"x": True, "y": True, "z": True},
        "built": True,
    },
    "pin": {
        "title": "Pin",
        "targets": ("faces",),
        "faces": "round",
        # Fusion's default holds radial and axial, leaves tangential free (research 3.4)
        "options": {"radial": True, "axial": True, "tangential": False},
        "built": False,
    },
    "frictionless": {
        "title": "Frictionless",
        "targets": ("faces",),
        "faces": "flat",
        "options": {},
        "built": False,
    },
    "displacement": {
        "title": "Prescribed Displacement",
        "targets": TARGETS_ANY,
        # None = free in that direction; a number = moved by that many mm
        "options": {"x": 0.0, "y": None, "z": None},
        "built": False,
    },
}

LOADS = {
    "force": {
        "title": "Force",
        "targets": TARGETS_ANY,
        # direction: normal (into a picked face, Fusion's default) or vector (any direction)
        "options": {
            "magnitude": 100.0,
            "direction": "normal",
            "vector": [0.0, 0.0, -1.0],
            "per_entity": False,
            "flip": False,
        },
        "built": True,
    },
    "pressure": {
        "title": "Pressure",
        "targets": ("faces",),
        "options": {"magnitude": 0.1, "flip": False},  # MPa, pushing into the face
        "built": True,
    },
    "moment": {
        "title": "Moment",
        "targets": ("faces",),
        "options": {"magnitude": 1000.0, "vector": [0.0, 0.0, 1.0]},  # N mm, about this axis
        "built": False,
    },
    "bearing": {
        "title": "Bearing Load",
        "targets": ("faces",),
        "faces": "round",
        "options": {"magnitude": 100.0, "vector": [0.0, 0.0, -1.0]},
        "built": False,
    },
    "remote_force": {
        "title": "Remote Force",
        "targets": ("faces",),
        "options": {"magnitude": 100.0, "vector": [0.0, 0.0, -1.0], "point": [0.0, 0.0, 0.0]},
        "built": False,
    },
}

UNITS = {
    "magnitude:force": "N",
    "magnitude:pressure": "MPa",
    "magnitude:moment": "N mm",
    "magnitude:bearing": "N",
    "magnitude:remote_force": "N",
    "displacement": "mm",
    "stress": "MPa",
    "safety": "",
    "strain": "",
    "force": "N",
}


class SimulationError(ValueError):
    """Something the person (or the AI) has to change; the message is a plain sentence."""


def kind_info(category, kind):
    table = CONSTRAINTS if category == "constraint" else LOADS
    info = table.get(kind)
    if info is None:
        raise SimulationError(
            "Unknown %s %r: choose one of %s." % (category, kind, ", ".join(sorted(table)))
        )
    return info


def options(category, kind, data=None):
    """The options of a constraint or load: its defaults with `data` on top (known keys)."""
    info = kind_info(category, kind)
    out = json.loads(json.dumps(info["options"]))
    for key, value in (data or {}).items():
        if key in out:
            out[key] = value
    return out


def check(category, kind, opts, picks):
    """Problems with a constraint or load, as sentences (an empty list when it is fine).
    `picks`: [(element kind "faces"/"edges"/"vertices", surface "plane"/"cylinder"/... or
    None)] of what was picked."""
    problems = []
    try:
        info = kind_info(category, kind)
    except SimulationError as exc:
        return [str(exc)]
    title = info["title"]
    if not picks:
        problems.append("%s needs at least one pick." % title)
    for element, surface in picks:
        if element not in info["targets"]:
            problems.append(
                "%s works on %s, not on %s." % (title, " / ".join(info["targets"]), element)
            )
        elif element == "faces" and info.get("faces") == "round" and surface != "cylinder":
            problems.append("%s needs round (cylindrical) faces." % title)
        elif element == "faces" and info.get("faces") == "flat" and surface != "plane":
            problems.append("%s needs flat faces." % title)
    opts = options(category, kind, opts)
    if category == "load":
        magnitude = opts.get("magnitude")
        if not isinstance(magnitude, (int, float)) or isinstance(magnitude, bool):
            problems.append("%s needs a number for its size." % title)
        elif magnitude == 0:
            problems.append("%s of 0 does nothing: give it a size." % title)
        vector = opts.get("vector")
        if vector is not None and (opts.get("direction", "vector") == "vector"):
            if not _vector_ok(vector):
                problems.append("%s needs a direction that is not zero." % title)
    if category == "constraint" and kind == "fixed":
        if not any(opts.get(axis) for axis in ("x", "y", "z")):
            problems.append("Fixed holds nothing with X, Y and Z all off: switch one on.")
    if category == "constraint" and kind == "displacement":
        if all(opts.get(axis) is None for axis in ("x", "y", "z")):
            problems.append("Prescribed Displacement needs a value in X, Y or Z.")
    return problems


def _vector_ok(vector):
    try:
        return len(vector) == 3 and math.sqrt(sum(float(c) ** 2 for c in vector)) > 1e-12
    except (TypeError, ValueError):
        return False


def unit_vector(vector):
    if not _vector_ok(vector):
        raise SimulationError("A direction must be three numbers that are not all zero.")
    length = math.sqrt(sum(float(c) ** 2 for c in vector))
    return [float(c) / length for c in vector]


def describe(category, kind, opts):
    """A short text for the browser and tooltips: "Fixed", "Force 100 N", "Pressure 0.5 MPa"."""
    info = kind_info(category, kind)
    opts = options(category, kind, opts)
    title = info["title"]
    if category == "constraint":
        if kind == "fixed":
            axes = [a.upper() for a in ("x", "y", "z") if opts.get(a)]
            return title if len(axes) == 3 else "%s (%s)" % (title, ", ".join(axes))
        if kind == "displacement":
            parts = [
                "%s %s mm" % (a.upper(), fmt(opts[a]))
                for a in ("x", "y", "z")
                if opts.get(a) is not None
            ]
            return "%s (%s)" % (title, ", ".join(parts))
        return title
    unit = UNITS.get("magnitude:" + kind, "")
    return "%s %s %s" % (title, fmt(opts.get("magnitude", 0.0)), unit)


def fmt(value, digits=4):
    """A number the way the dialogs show it: up to `digits` significant figures, no
    trailing zeros, no "-0"."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value == 0 or not math.isfinite(value):
        return "0" if value == 0 else str(value)
    text = "%.*g" % (digits, value)
    if "e" in text:
        mantissa, exponent = text.split("e")
        mantissa = mantissa.rstrip("0").rstrip(".") if "." in mantissa else mantissa
        return "%se%d" % (mantissa, int(exponent))
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


# -- materials -------------------------------------------------------------------------------------
# What CalculiX needs from a material (MPa, kg/m3) and what the safety factor divides by.
MATERIAL_KEYS = ("youngs_mpa", "poisson", "density", "yield_mpa", "ultimate_mpa")

# Values for FreeCAD library materials that lack a property a stress study needs (FreeCAD's
# Steel-Generic has no yield strength, Aluminum-Generic's is NaN, PMMA / PEEK have no Poisson
# ratio). Typical handbook values for each generic material, used only where FreeCAD's card
# has nothing; the Study Materials dialog says when one was used.
FALLBACK = {
    "Steel-Generic": {"yield_mpa": 207.0, "ultimate_mpa": 345.0},
    "Aluminum-Generic": {"yield_mpa": 95.0, "ultimate_mpa": 110.0},
    "PMMA-Generic": {"poisson": 0.37},
    "PEEK-Generic": {"poisson": 0.40},
    "Wood-Generic": {"yield_mpa": 40.0, "ultimate_mpa": 40.0},
    "Glass-Generic": {"yield_mpa": 33.0, "ultimate_mpa": 33.0},
}


def material_problems(name, props):
    """Sentences for what a stress study cannot do with this material."""
    problems = []
    if not _positive(props.get("youngs_mpa")):
        problems.append("%s has no Young's modulus: choose another study material." % name)
    nu = props.get("poisson")
    if not isinstance(nu, (int, float)) or not (0.0 <= nu < 0.5):
        problems.append("%s has no Poisson's ratio: choose another study material." % name)
    return problems


def strength(props, basis):
    """The strength the safety factor divides (MPa): the yield strength or the ultimate
    tensile strength, as the study's safety basis says; None when the material has none (the
    other strength is never used quietly in its place)."""
    key = "yield_mpa" if basis == "yield" else "ultimate_mpa"
    value = props.get(key)
    return float(value) if _positive(value) else None


def _positive(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and math.isfinite(value)
    )


# -- results ---------------------------------------------------------------------------------------
RESULTS = (
    # (key, Fusion's name, unit)
    ("safety", "Safety Factor", ""),
    ("von_mises", "Stress: Von Mises", "MPa"),
    ("principal_1", "Stress: 1st Principal", "MPa"),
    ("principal_3", "Stress: 3rd Principal", "MPa"),
    ("sxx", "Stress: Normal XX", "MPa"),
    ("syy", "Stress: Normal YY", "MPa"),
    ("szz", "Stress: Normal ZZ", "MPa"),
    ("sxy", "Stress: Shear XY", "MPa"),
    ("syz", "Stress: Shear YZ", "MPa"),
    ("szx", "Stress: Shear ZX", "MPa"),
    ("displacement", "Displacement: Total", "mm"),
    ("dx", "Displacement: X", "mm"),
    ("dy", "Displacement: Y", "mm"),
    ("dz", "Displacement: Z", "mm"),
    ("strain", "Strain: Equivalent", ""),
)
SAFETY_CAP = 15.0  # Fusion shows the safety factor capped at 15 (research 5.4)

# Fusion's deformation scale (research 5.6): (key, name, multiple of "Adjusted"); Adjusted draws
# the largest displacement at 5 % of the model size (the bounding box diagonal); Actual is the
# true displacement; Undeformed none.
DEFORMATIONS = (
    ("undeformed", "Undeformed", 0.0),
    ("actual", "Actual", None),
    ("adjusted_half", "Adjusted x 0.5", 0.5),
    ("adjusted", "Adjusted", 1.0),
    ("adjusted_2", "Adjusted x 2", 2.0),
    ("adjusted_5", "Adjusted x 5", 5.0),
)
ADJUSTED_FRACTION = 0.05


def deformation_factor(key, max_displacement, diagonal):
    """How many times the true displacement is drawn for deformation option `key`."""
    for k, _name, multiple in DEFORMATIONS:
        if k != key:
            continue
        if multiple is None:
            return 1.0
        if multiple == 0.0 or not max_displacement or max_displacement <= 0:
            return 0.0
        return multiple * ADJUSTED_FRACTION * float(diagonal) / float(max_displacement)
    raise SimulationError("Unknown deformation %r." % key)


def result_title(key):
    for k, title, _unit in RESULTS:
        if k == key:
            return title
    return key


def result_unit(key):
    for k, _title, unit in RESULTS:
        if k == key:
            return unit
    return ""


def safety_factors(von_mises, strength_mpa, cap=None):
    """Safety factor at every node: strength / stress (MPa): Fusion divides the yield strength by
    the von Mises stress, the ultimate tensile strength by the 1st principal stress (pass that
    list here then). A node without stress (or in compression for the 1st principal) gets `cap`
    (or infinity when cap is None)."""
    out = []
    top = float("inf") if cap is None else float(cap)
    for s in von_mises:
        if s is None or s <= 1e-12:
            out.append(top)
        else:
            out.append(min(strength_mpa / float(s), top))
    return out


def stats(values):
    """{"min", "max", "min_index", "max_index", "count"} of a list of numbers (NaN skipped)."""
    lo = hi = None
    lo_i = hi_i = -1
    n = 0
    for i, v in enumerate(values):
        if v is None or not isinstance(v, (int, float)) or v != v:
            continue
        n += 1
        if lo is None or v < lo:
            lo, lo_i = v, i
        if hi is None or v > hi:
            hi, hi_i = v, i
    return {"min": lo, "max": hi, "min_index": lo_i, "max_index": hi_i, "count": n}


# -- colours ---------------------------------------------------------------------------------------
# Results are coloured from blue (low) through cyan, green and yellow to red (high), like
# Fusion's legend; the safety factor runs the other way (red: low, unsafe; blue: high).
SPECTRUM = (
    (0.00, (0.0, 0.0, 1.0)),
    (0.25, (0.0, 1.0, 1.0)),
    (0.50, (0.0, 1.0, 0.0)),
    (0.75, (1.0, 1.0, 0.0)),
    (1.00, (1.0, 0.0, 0.0)),
)


def colour(value, lo, hi, reverse=False):
    """(r, g, b) in 0..1 for `value` on the scale lo..hi."""
    if hi is None or lo is None or hi - lo <= 1e-300:
        t = 0.0
    else:
        t = (float(value) - lo) / (hi - lo)
    t = min(max(t, 0.0), 1.0)
    if reverse:
        t = 1.0 - t
    for (t0, c0), (t1, c1) in zip(SPECTRUM, SPECTRUM[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return SPECTRUM[-1][1]


def scale_for(key, lo, hi):
    """(lo, hi, reverse) of the colour scale of a result: the safety factor from 0 to the cap
    (red low), anything else from its min to its max (red high)."""
    if key == "safety":
        return 0.0, SAFETY_CAP, True
    return lo, hi, False


def legend_ticks(lo, hi, count=9):
    """`count` evenly spaced values from hi down to lo (the legend's labels, top first)."""
    if lo is None or hi is None:
        return []
    if count < 2 or hi == lo:
        return [hi]
    step = (hi - lo) / float(count - 1)
    return [hi - i * step for i in range(count)]


# -- pre-check -------------------------------------------------------------------------------------
def precheck(summary):
    """What is missing before a solve, as [(level, sentence)] with level "error" (cannot
    solve) or "warning" (solves, but the result may not be what was meant).

    `summary`: {"bodies": [names], "materials": {body: (material name, props)},
    "constraints": [(kind, picks count, suppressed)], "loads": [...], "gravity": bool,
    "lost": [item labels whose picks are gone], "loose": [bodies held by nothing]}"""
    out = []
    bodies = summary.get("bodies") or []
    if not bodies:
        out.append(("error", "The study has no solid body to simulate."))
    for body, (name, props) in sorted((summary.get("materials") or {}).items()):
        for text in material_problems(name, props):
            out.append(("error", "%s: %s" % (body, text)))
        basis = summary.get("safety_basis", "yield")
        if strength(props, basis) is None:
            out.append(
                (
                    "warning",
                    "%s: %s has no %s strength, so its safety factor cannot be shown."
                    % (body, name, "yield" if basis == "yield" else "ultimate tensile"),
                )
            )
    active = [c for c in summary.get("constraints") or [] if not c[2]]
    if bodies and not active:
        out.append(
            ("error", "Nothing holds the model: add a constraint (Fixed) to keep it in place.")
        )
    loads = [c for c in summary.get("loads") or [] if not c[2]]
    if bodies and not loads and not summary.get("gravity"):
        out.append(("warning", "Nothing pushes on the model: add a load or switch gravity on."))
    for label in summary.get("lost") or []:
        out.append(("error", "%s lost what it was on: edit it and pick again." % label))
    for body in summary.get("loose") or []:
        out.append(
            (
                "error",
                "%s is not held by a constraint and does not touch a held body: it would fly "
                "away. Add a constraint on it." % body,
            )
        )
    return out


def can_solve(checks):
    return not any(level == "error" for level, _text in checks)

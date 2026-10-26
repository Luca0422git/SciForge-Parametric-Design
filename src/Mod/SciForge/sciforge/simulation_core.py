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
        "size_mm": 0.0,  # Average Element Size as a length (mm); 0 = use size_pct
        "order": "parabolic",  # parabolic (2nd order, Fusion's default) | linear
        "curved": True,  # curved (mid-side nodes on the geometry) parabolic elements
        "scale_per_part": False,  # Fusion: Scale Mesh Size Per Part
        "min_pct": 20.0,  # smallest element, % of the average size
        "max_turn": 60.0,  # degrees an element may turn along a curve
        "adjacent_ratio": 1.5,  # largest size ratio of neighbouring elements (local controls)
        "aspect_ratio": 10.0,  # elements longer than this x their height are reported
    },
    "adaptive": {
        # Fusion's Adaptive Mesh Refinement: "none" (default) or "custom"/"low"/"medium"/
        # "high" (see ADAPTIVE_LEVELS): solve, make the elements where the result changes the
        # most smaller, solve again, until the largest value changes by less than `tolerance`
        # % or `passes` solves were made
        "level": "none",
        "passes": 4,
        "tolerance": 5.0,  # %
        "portion": 10.0,  # % of the elements refined in each pass
        "result": "von_mises",  # von_mises | displacement | principal_1 | principal_3
    },
    "gravity": {"on": False, "direction": [0.0, 0.0, -1.0], "g": 9806.65},  # mm/s2
    "safety_basis": "yield",  # yield | ultimate: what the safety factor divides
    "contacts": "bonded",  # bodies that touch are glued (Fusion's automatic contacts)
    "contact_tolerance": 0.1,  # mm: faces closer than this touch
    # Fusion's Remove rigid body modes (General tab, off): for a model held by nothing whose
    # loads balance; SciForge holds each free piece at three of its corners, statically
    # determinate (the 3-2-1 rule), so the balanced loads give no reaction there
    "remove_rigid": False,
    # keep the mesh and the results in the design file (off: only the summary is saved, the
    # coloured results need a new solve after reopening; a fine mesh can add many MB)
    "keep_results": True,
}

ADAPTIVE_LEVELS = {
    # level: (passes, tolerance %, portion %)
    "low": (2, 10.0, 10.0),
    "medium": (4, 5.0, 10.0),
    "high": (6, 2.0, 15.0),
}
ADAPTIVE_RESULTS = ("von_mises", "displacement", "principal_1", "principal_3")

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
    mesh = out["mesh"]
    mesh["size_pct"] = min(max(float(mesh["size_pct"]), 0.5), 50.0)
    mesh["size_mm"] = max(float(mesh["size_mm"]), 0.0)
    mesh["min_pct"] = min(max(float(mesh["min_pct"]), 1.0), 100.0)
    mesh["max_turn"] = min(max(float(mesh["max_turn"]), 1.0), 90.0)
    mesh["adjacent_ratio"] = min(max(float(mesh["adjacent_ratio"]), 1.05), 10.0)
    mesh["aspect_ratio"] = min(max(float(mesh["aspect_ratio"]), 1.5), 1000.0)
    adaptive = out["adaptive"]
    if adaptive["level"] not in ("none", "custom") + tuple(ADAPTIVE_LEVELS):
        adaptive["level"] = "none"
    if adaptive["result"] not in ADAPTIVE_RESULTS:
        adaptive["result"] = "von_mises"
    adaptive["passes"] = int(min(max(int(adaptive["passes"]), 1), 10))
    adaptive["tolerance"] = min(max(float(adaptive["tolerance"]), 0.1), 50.0)
    adaptive["portion"] = min(max(float(adaptive["portion"]), 1.0), 100.0)
    out["contact_tolerance"] = min(max(float(out["contact_tolerance"]), 0.0), 10.0)
    return out


def adaptive_plan(adaptive):
    """(passes, tolerance %, portion %) of the adaptive refinement settings, or None when it
    is off. A named level ("low"/"medium"/"high") uses its own numbers; "custom" the
    settings'. `passes` counts every solve, the first one included."""
    level = (adaptive or {}).get("level", "none")
    if level == "none":
        return None
    if level in ADAPTIVE_LEVELS:
        return ADAPTIVE_LEVELS[level]
    return (int(adaptive["passes"]), float(adaptive["tolerance"]), float(adaptive["portion"]))


def converged(previous, current, tolerance_pct):
    """True when `current` differs from `previous` by at most `tolerance_pct` % (of the
    larger of the two)."""
    if previous is None or current is None:
        return False
    scale = max(abs(previous), abs(current))
    if scale <= 1e-300:
        return True
    return abs(current - previous) / scale * 100.0 <= tolerance_pct


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


def element_size(bbox, size_pct, size_mm=0.0):
    """Average element size (mm) for `size_pct` % of the model size (or `size_mm` when it is
    given), never below 0.05 mm."""
    if size_mm and float(size_mm) > 0:
        return max(float(size_mm), 0.05)
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
        # Fusion's default holds radial and axial, leaves tangential free (research 3.4):
        # radial = the hole keeps its size and place, axial = no sliding along the pin,
        # tangential = no turning about it
        "options": {"radial": True, "axial": True, "tangential": False},
        "built": True,
    },
    "frictionless": {
        "title": "Frictionless",
        # any face: no movement along the face's normal at each of its points, free to slide
        # along it (a flat face: a symmetry plane, a part resting on a smooth table)
        "targets": ("faces",),
        "options": {},
        "built": True,
    },
    "displacement": {
        "title": "Prescribed Displacement",
        "targets": TARGETS_ANY,
        # None = free in that direction; a number = moved by that many mm (design axes)
        "options": {"x": 0.0, "y": None, "z": None},
        "built": True,
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
        # N mm about an axis through the middle of the picked faces: normal = the first
        # face's normal (Fusion's Normal), vector = the axis [x, y, z] (Fusion's Vectors).
        # The faces turn as a whole but stay deformable (forces that grow with the distance
        # from the axis, as a shaft end in torsion); per_entity: each face gets the whole
        # moment about its own middle
        "options": {
            "magnitude": 1000.0,
            "direction": "normal",
            "vector": [0.0, 0.0, 1.0],
            "per_entity": False,
            "flip": False,
        },
        "built": True,
    },
    "bearing": {
        "title": "Bearing Load",
        "targets": ("faces",),
        "faces": "round",
        # N, the total; spread over the half of the round faces it pushes on, most in the
        # middle and none at the sides (a parabola), always pushing into the material
        "options": {"magnitude": 100.0, "vector": [0.0, 0.0, -1.0], "flip": False},
        "built": True,
    },
    "remote_force": {
        "title": "Remote Force",
        "targets": ("faces",),
        # N acting at `point` (mm, design coordinates), carried to the picked faces: the
        # force plus the moment of its lever arm, spread over the faces as a deformable link
        "options": {
            "magnitude": 100.0,
            "vector": [0.0, 0.0, -1.0],
            "point": [0.0, 0.0, 0.0],
            "flip": False,
        },
        "built": True,
    },
}

# Fusion's Local Mesh Control (SETUP > MANAGE): smaller (or larger) elements on picked faces,
# edges or whole bodies, blending into the global size.
MESH_CONTROLS = {
    "local": {
        "title": "Local Mesh Control",
        "targets": ("faces", "edges", "bodies"),
        "options": {"size": 1.0},  # mm
        "built": True,
    },
}

TABLES = {"constraint": CONSTRAINTS, "load": LOADS, "mesh": MESH_CONTROLS}
CATEGORIES = tuple(TABLES)

UNITS = {
    "magnitude:force": "N",
    "magnitude:pressure": "MPa",
    "magnitude:moment": "N mm",
    "magnitude:bearing": "N",
    "magnitude:remote_force": "N",
    "size:local": "mm",
    "displacement": "mm",
    "stress": "MPa",
    "safety": "",
    "strain": "",
    "force": "N",
}


class SimulationError(ValueError):
    """Something the person (or the AI) has to change; the message is a plain sentence."""


def kind_info(category, kind):
    table = TABLES.get(category)
    if table is None:
        raise SimulationError(
            "Unknown category %r: choose one of %s." % (category, ", ".join(CATEGORIES))
        )
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
    `picks`: [(element kind "faces"/"edges"/"vertices"/"bodies", surface "plane"/
    "cylinder"/... or None)] of what was picked."""
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
        if not _number_ok(magnitude):
            problems.append("%s needs a number for its size." % title)
        elif magnitude == 0:
            problems.append("%s of 0 does nothing: give it a size." % title)
        vector = opts.get("vector")
        if vector is not None and (opts.get("direction", "vector") == "vector"):
            if not _vector_ok(vector):
                problems.append("%s needs a direction that is not zero." % title)
        if "direction" in opts and opts["direction"] not in ("normal", "vector"):
            problems.append("%s: the direction is normal or vector." % title)
        if kind == "remote_force":
            point = opts.get("point")
            if not (
                isinstance(point, (list, tuple))
                and len(point) == 3
                and all(_number_ok(c) for c in point)
            ):
                problems.append("%s needs the point it acts from: three numbers (mm)." % title)
    if category == "constraint" and kind == "fixed":
        if not any(opts.get(axis) for axis in ("x", "y", "z")):
            problems.append("Fixed holds nothing with X, Y and Z all off: switch one on.")
    if category == "constraint" and kind == "pin":
        if not any(opts.get(axis) for axis in ("radial", "axial", "tangential")):
            problems.append(
                "Pin holds nothing with radial, axial and tangential all off: switch one on."
            )
    if category == "constraint" and kind == "displacement":
        values = [opts.get(axis) for axis in ("x", "y", "z")]
        if all(v is None for v in values):
            problems.append("Prescribed Displacement needs a value in X, Y or Z.")
        elif any(v is not None and not _number_ok(v) for v in values):
            problems.append("Prescribed Displacement needs numbers (mm) or nothing (free).")
    if category == "mesh":
        size = opts.get("size")
        if not _number_ok(size) or size <= 0:
            problems.append("%s needs an element size above 0 mm." % title)
    return problems


def _number_ok(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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
        if kind == "pin":
            held = [a for a in ("radial", "axial", "tangential") if opts.get(a)]
            if held == ["radial", "axial"]:
                return title
            return "%s (%s)" % (title, ", ".join(held))
        return title
    if category == "mesh":
        return "%s %s mm" % (title, fmt(opts.get("size", 0.0)))
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


# -- what CalculiX gets at the nodes ---------------------------------------------------------------
# SciForge writes the constraints itself (not with FreeCAD's constraint objects) so that every
# kind can share a node with every other: a Fixed face next to a Pin, a Frictionless symmetry
# plane meeting another one at a corner. Each node collects "spc" rows (a displacement set to
# a value along a design axis: dof 0/1/2 = X/Y/Z) and "eq" rows (no movement along a direction
# (cx, cy, cz): cx*ux + cy*uy + cz*uz = 0, a Pin's radial / axial / tangential, a Frictionless
# face's normal); node_constraints() merges them into CalculiX's *BOUNDARY and *EQUATION lines
# (an equation's first term is eliminated by CalculiX, so it must be free: not set by a
# *BOUNDARY and not first in another equation).
EPS = 1e-9


def node_constraints(rows, tol=1e-9):
    """Merge per-node constraint rows. `rows`: iterable of (node, source, kind, data) with
    kind "spc" (data = (dof, value)) or "eq" (data = (cx, cy, cz)).

    Returns {"spc": {node: {dof: value}}, "equations": [(node, [(dof, coef), ...])] (the first
    term is the dependent one, its coefficient 1), "conflicts": [(node, source, other)]}: two
    sources asking a node for different things (a Fixed face next to a Prescribed Displacement
    of 0.5 mm): the first one made wins and the conflict is reported."""
    per_node = {}
    order = []
    for node, source, kind, data in rows:
        if node not in per_node:
            per_node[node] = ([], [])
            order.append(node)
        per_node[node][0 if kind == "spc" else 1].append((source, data))
    spc_out, equations, conflicts = {}, [], []
    for node in order:
        spcs, eqs = per_node[node]
        fixed, fixed_by = {}, {}
        for source, (dof, value) in spcs:
            value = float(value)
            if dof in fixed:
                if abs(fixed[dof] - value) > tol * max(1.0, abs(value)):
                    conflicts.append((node, source, fixed_by[dof]))
                continue
            fixed[dof], fixed_by[dof] = value, source
        rows_m = []
        for source, vector in eqs:
            length = math.sqrt(sum(float(c) ** 2 for c in vector))
            if length > EPS:
                rows_m.append(([float(c) / length for c in vector], source))
        free = [d for d in range(3) if d not in fixed]
        used, pivots = set(), []
        while True:
            best = None
            for r, (row, _src) in enumerate(rows_m):
                if r in used:
                    continue
                for c in free:
                    if c in [p[1] for p in pivots]:
                        continue
                    if best is None or abs(row[c]) > abs(rows_m[best[0]][0][best[1]]):
                        best = (r, c)
            if best is None or abs(rows_m[best[0]][0][best[1]]) < 1e-7:
                break
            r, c = best
            row = rows_m[r][0]
            pivot = row[c]
            rows_m[r] = ([v / pivot for v in row], rows_m[r][1])
            for k, (other, src) in enumerate(rows_m):
                if k != r and abs(other[c]) > 0.0:
                    factor = other[c]
                    rows_m[k] = ([o - factor * p for o, p in zip(other, rows_m[r][0])], src)
            used.add(r)
            pivots.append((r, c))
        for r, (row, source) in enumerate(rows_m):
            if r in used:
                continue
            # nothing free left in it: either already true or impossible with these values
            rest = sum(row[d] * fixed[d] for d in fixed)
            if abs(rest) > 1e-7 * max(1.0, max(abs(v) for v in fixed.values() or [1.0])):
                conflicts.append(
                    (node, source, fixed_by.get(max(fixed, key=lambda d: abs(row[d]))))
                )
        pivot_cols = [p[1] for p in pivots]
        for r, c in pivots:
            row = rows_m[r][0]
            terms = [(c, 1.0)]
            others = [(d, row[d]) for d in free if d != c and d not in pivot_cols]
            others = [(d, v) for d, v in others if abs(v) > 1e-9]
            known = sum(row[d] * fixed[d] for d in fixed)
            if not others:
                # the direction is held completely: a plain displacement value
                fixed[c] = -known
                fixed_by[c] = rows_m[r][1]
                continue
            terms += others
            terms += [(d, row[d]) for d in fixed if abs(row[d]) > 1e-9 and abs(fixed[d]) > 0]
            equations.append((node, terms))
        if fixed:
            spc_out[node] = dict(sorted(fixed.items()))
    return {"spc": spc_out, "equations": equations, "conflicts": conflicts}


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _solve3(m, v):
    """x with m x = v (3 x 3), or None when m is (nearly) singular."""
    a, b, c = m
    det = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    scale = max(abs(x) for row in m for x in row) or 1.0
    if abs(det) <= 1e-12 * scale**3:
        return None
    out = []
    for i in range(3):
        cols = [list(row) for row in m]
        for r in range(3):
            cols[r][i] = v[r]
        a2, b2, c2 = cols
        out.append(
            (
                a2[0] * (b2[1] * c2[2] - b2[2] * c2[1])
                - a2[1] * (b2[0] * c2[2] - b2[2] * c2[0])
                + a2[2] * (b2[0] * c2[1] - b2[1] * c2[0])
            )
            / det
        )
    return out


def weighted_middle(points, weights):
    total = float(sum(weights))
    if total <= 0:
        raise SimulationError("The picked faces have no area to carry the load.")
    return [sum(w * p[i] for p, w in zip(points, weights)) / total for i in range(3)]


def distribute(points, weights, force=(0.0, 0.0, 0.0), moment=(0.0, 0.0, 0.0)):
    """Forces at `points` (each with its share `weights` of the area) that add up to `force`
    and to `moment` about their weighted middle: the force shared by area, the moment as
    forces that grow with the distance from the middle (the faces turn as a whole but stay
    deformable, as CalculiX's distributing coupling). Returns a list of [fx, fy, fz]."""
    middle = weighted_middle(points, weights)
    total = float(sum(weights))
    arms = [_sub(p, middle) for p in points]
    omega = [0.0, 0.0, 0.0]
    if _norm(moment) > 0.0:
        inertia = [[0.0] * 3 for _ in range(3)]
        for r, w in zip(arms, weights):
            rr = _dot(r, r)
            for i in range(3):
                for j in range(3):
                    inertia[i][j] += w * ((rr if i == j else 0.0) - r[i] * r[j])
        omega = _solve3(inertia, list(moment))
        if omega is None:
            raise SimulationError(
                "The picked faces cannot carry a moment about that axis (they lie on a line): "
                "pick faces that spread around it."
            )
    out = []
    for r, w in zip(arms, weights):
        turn = _cross(omega, r)
        out.append([w * (force[i] / total + turn[i]) for i in range(3)])
    return out


def remote_moment(points, weights, force, point):
    """The moment (about the weighted middle of `points`) of `force` acting at `point`."""
    middle = weighted_middle(points, weights)
    return _cross(_sub(point, middle), force)


def bearing_forces(points, weights, inward, direction, magnitude):
    """A bearing load: `magnitude` N along `direction` pushed onto round faces the way a
    shaft or pin presses: only where the face looks against the load (inward[i], the unit
    direction into the material at each point, has a positive share along the load), most in
    the middle of that half and none at its sides (a parabola over the angle), always pushing
    into the material. Returns a list of [fx, fy, fz] adding up to the load along its
    direction."""
    d = unit_vector(direction)
    raw = []
    for w, n in zip(weights, inward):
        cos = max(-1.0, min(1.0, _dot(n, d)))
        if cos <= 1e-9:
            raw.append([0.0, 0.0, 0.0])
            continue
        angle = math.acos(cos)
        share = w * max(0.0, 1.0 - (angle / (math.pi / 2.0)) ** 2)
        raw.append([share * n[0], share * n[1], share * n[2]])
    along = sum(_dot(f, d) for f in raw)
    if along <= 1e-12:
        raise SimulationError(
            "A bearing load pushes on the side of a round face that faces the load: none of "
            "the picked faces faces that direction. Flip the direction."
        )
    scale = float(magnitude) / along
    return [[c * scale for c in f] for f in raw]


def three_two_one(nodes):
    """Rows for node_constraints that hold a free piece without forcing it (Remove rigid
    body modes): its three nodes farthest apart, the first held in X, Y and Z, the second
    across the line to it, the third out of their plane. `nodes`: [(id, (x, y, z))]."""
    if len(nodes) < 3:
        raise SimulationError("A free piece has too few nodes to hold it still.")
    pts = {n: p for n, p in nodes}
    middle = [sum(p[i] for p in pts.values()) / len(pts) for i in range(3)]
    a = max(pts, key=lambda n: (_norm(_sub(pts[n], middle)), -n))
    b = max(pts, key=lambda n: (_norm(_sub(pts[n], pts[a])), -n))
    ab = _sub(pts[b], pts[a])

    def off_line(n):
        return _norm(_cross(ab, _sub(pts[n], pts[a])))

    c = max(pts, key=lambda n: (off_line(n), -n))
    normal = _cross(ab, _sub(pts[c], pts[a]))
    if _norm(normal) <= 1e-9 * max(1.0, _dot(ab, ab)):
        raise SimulationError("A free piece is too thin (all on a line) to hold it still.")
    normal = [v / _norm(normal) for v in normal]
    across = _cross(ab, normal)
    across = [v / _norm(across) for v in across]
    rows = [(a, "rigid", "spc", (dof, 0.0)) for dof in range(3)]
    rows.append((b, "rigid", "eq", tuple(normal)))
    rows.append((b, "rigid", "eq", tuple(across)))
    rows.append((c, "rigid", "eq", tuple(normal)))
    return rows


def inp_boundaries(spc):
    """*BOUNDARY data lines (node, first dof, last dof, value) for node_constraints' "spc"."""
    lines = []
    for node in sorted(spc):
        for dof, value in sorted(spc[node].items()):
            lines.append("%d,%d,%d,%.13g" % (node, dof + 1, dof + 1, value))
    return lines


def inp_equations(equations):
    """*EQUATION blocks for node_constraints' "equations"."""
    lines = []
    for node, terms in equations:
        lines.append("*EQUATION")
        lines.append("%d" % len(terms))
        fields = []
        for dof, coef in terms:
            fields.append("%d,%d,%.13g" % (node, dof + 1, coef))
        for i in range(0, len(fields), 4):
            lines.append(",".join(fields[i : i + 4]))
    return lines


def inp_loads(forces):
    """*CLOAD data lines for {node: [fx, fy, fz]} (zeros left out)."""
    lines = []
    for node in sorted(forces):
        for dof, value in enumerate(forces[node]):
            if abs(value) > 1e-14:
                lines.append("%d,%d,%.13g" % (node, dof + 1, value))
    return lines


def reactions_from_dat(text):
    """{set name (upper case): [fx, fy, fz]} of CalculiX's "total force" lines in a .dat
    file (the last time printed)."""
    out = {}
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if not low.startswith("total force (fx,fy,fz) for set"):
            continue
        name = low.split("for set", 1)[1].split("and time")[0].strip().upper()
        for follow in lines[i + 1 : i + 4]:
            parts = follow.split()
            if len(parts) == 3:
                try:
                    out[name] = [float(v) for v in parts]
                    break
                except ValueError:
                    continue
    return out


# -- held enough? (rigid body modes) ---------------------------------------------------------------
# A model must be held so that no piece of it can move or turn as a whole (Fusion: "rigid
# body motion"; its DOF View). CalculiX does not always notice: a part held only along X can
# come back "solved" with nonsense displacements, so SciForge checks before solving. Every
# constraint stops points of the piece moving in some directions; the piece is held when
# those rows stop all six rigid movements (three slides, three turns).
RIGID_WORDS = ("slide along X", "slide along Y", "slide along Z")


def free_modes(rows, centre, size):
    """The rigid movements `rows` leave free. rows: [(point (x, y, z), direction (cx, cy,
    cz))]: that point cannot move along that direction. centre: the middle of the piece,
    size: its size (mm, to weigh turns against slides). Returns [(kind "slide" / "turn",
    direction [x, y, z], point on the axis [x, y, z] or None)]."""
    size = max(float(size), 1e-9)
    m = [[0.0] * 6 for _ in range(6)]
    for point, direction in rows:
        c = list(direction)
        length = _norm(c)
        if length <= 1e-12:
            continue
        c = [v / length for v in c]
        r = _sub(point, centre)
        turn = _cross(r, c)
        a = c + [v / size for v in turn]
        for i in range(6):
            if a[i] == 0.0:
                continue
            for j in range(6):
                m[i][j] += a[i] * a[j]
    values, vectors = _jacobi(m)
    top = max(values) if values else 0.0
    out = []
    for value, vector in zip(values, vectors):
        if top > 0 and value > 1e-9 * top:
            continue
        slide = vector[:3]
        turn = [v / size for v in vector[3:]]
        if _norm(turn) * size <= 1e-6 * max(_norm(slide), 1e-12) or _norm(turn) <= 1e-15:
            out.append(("slide", _unit_or(slide), None))
        else:
            # the movement u(p) = slide + turn x (p - centre): an axis along turn through
            # centre + (turn x slide) / |turn|^2 (plus a slide along the axis)
            w = _dot(turn, turn)
            through = [centre[i] + _cross(turn, slide)[i] / w for i in range(3)]
            out.append(("turn", _unit_or(turn), through))
    return out


def _unit_or(v):
    length = _norm(v)
    if length <= 1e-15:
        return [0.0, 0.0, 0.0]
    out = [c / length for c in v]
    # point the main component the positive way, so the words read naturally
    big = max(range(3), key=lambda i: abs(out[i]))
    if out[big] < 0:
        out = [-c for c in out]
    return [0.0 if abs(c) < 1e-9 else c for c in out]


def _jacobi(a, sweeps=50):
    """Eigenvalues and eigenvectors of a small symmetric matrix (lists), Jacobi rotations."""
    n = len(a)
    a = [list(row) for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _sweep in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        scale = sum(a[i][i] ** 2 for i in range(n)) or 1.0
        if off <= 1e-30 * scale:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) <= 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s_ = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s_ * akq
                    a[k][q] = s_ * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s_ * aqk
                    a[q][k] = s_ * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s_ * vkq
                    v[k][q] = s_ * vkp + c * vkq
    values = [a[i][i] for i in range(n)]
    vectors = [[v[k][i] for k in range(n)] for i in range(n)]
    return values, vectors


def describe_free_mode(mode):
    """A free movement in words: "slide along X", "turn about an axis along Z through (50, 5,
    5)"."""
    kind, direction, through = mode
    names = ("X", "Y", "Z")
    axis = None
    for i in range(3):
        if abs(abs(direction[i]) - 1.0) <= 1e-6:
            axis = names[i]
    words = axis or "(%s)" % ", ".join(fmt(c, 3) for c in direction)
    if kind == "slide":
        return "slide along %s" % words
    return "turn about an axis along %s through (%s)" % (
        words,
        ", ".join(fmt(c, 4) for c in through),
    )


# -- what the programs say, in sentences -----------------------------------------------------------
def solver_failure(output):
    """CalculiX's complaint (its printed output) as a sentence a person can act on."""
    text = (output or "").lower()
    if "zero pivot" in text or "singular" in text:
        return (
            "The model is not held enough: a part can still move or spin freely. Add constraints "
            "so every body is held in X, Y and Z (a Fixed face is the simplest), or switch on "
            "Remove rigid body modes if the loads balance each other."
        )
    if "nonpositive jacobian" in text or "negative jacobian" in text:
        return (
            "The mesh has distorted elements CalculiX cannot use (large elements at thin walls "
            "or tight curves): try a smaller Average Element Size, or a Local Mesh Control on "
            "the thin or curved faces."
        )
    if (
        "dependent dof" in text
        or "is used as dependent" in text
        or ("mpc" in text and "error" in text)
    ):
        return (
            "Two constraints hold the same corner or edge in ways that cannot both be true: "
            "suppress one of them, or move one to a different face."
        )
    if "not enough memory" in text or ("allocation" in text and "fail" in text):
        return (
            "The computer ran out of memory for this mesh: make the Average Element Size "
            "larger, or use local mesh controls only where the stress matters."
        )
    if "material" in text and ("not defined" in text or "no elastic" in text):
        return "A body has no usable material: check the study materials."
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    return ("CalculiX could not solve the study. %s" % " ".join(lines[-4:])).strip()


def gmsh_errors(output):
    """(Gmsh's error lines, the surface numbers they name): Gmsh numbers the model's faces
    in order, so surface 12 is the model's Face12."""
    import re

    # (Gmsh ends with a summary of its errors: "-----", "Mesh generation error summary",
    # "2 errors", "Check the full log for details": not reasons)
    generic = ("------", "error summary", "warnings", "errors", "full log")
    errors = [
        line.strip()
        for line in (output or "").splitlines()
        if "Error" in line and not any(g in line for g in generic)
    ]
    numbers = []
    for line in errors:
        for match in re.finditer(r"[Ss]urfaces?\s+(\d+)", line):
            if int(match.group(1)) not in numbers:
                numbers.append(int(match.group(1)))
    return errors, numbers


# Gmsh's complaints when the surface mesh crosses itself: the triangles of two faces closer
# than the elements are large (a thin wall, a small gap) cut through each other. Smaller
# elements mesh it.
CROSSING_WORDS = ("intersect", "invalid boundary mesh", "overlapping facets", "self-intersect")


def mesh_crossed_itself(output):
    """True when Gmsh's output says the surface mesh crossed itself (see CROSSING_WORDS)."""
    errors, _numbers = gmsh_errors(output)
    text = " ".join(errors).lower()
    return any(word in text for word in CROSSING_WORDS)


# -- contacts --------------------------------------------------------------------------------------
# Fusion's contact types (research 3.6) and what SciForge does with each: bodies that touch or
# come closer than the contact tolerance are glued (Bonded, made automatically at solve time,
# Fusion's default); the others make the solve nonlinear (the bodies may open, slide or press
# harder as the load grows), which a linear Static Stress solve cannot do.
CONTACT_TYPES = (
    ("bonded", "Bonded", True),
    ("offset_bonded", "Offset Bonded", False),
    ("separation", "Separation", False),
    ("sliding", "Sliding", False),
    ("rough", "Rough", False),
    ("no_contact", "No Contact", False),
)
CONTACT_NOT_AVAILABLE = (
    "Not in SciForge yet: only bonded contacts, found automatically (bodies that touch or are "
    "closer than the contact tolerance are glued). Separation, sliding and rough contacts make "
    "the solve nonlinear, which a linear Static Stress study cannot do."
)


def contact_type_available(key):
    return any(k == key and ok for k, _t, ok in CONTACT_TYPES)


# -- mesh statistics -------------------------------------------------------------------------------
def mesh_quality(edge_lengths, aspect_ratios, limit):
    """{"smallest", "largest" (mm, element edge lengths), "worst_aspect", "over_limit" (how
    many elements are stretched more than `limit`)}."""
    out = {"smallest": None, "largest": None, "worst_aspect": None, "over_limit": 0}
    lengths = [v for v in edge_lengths if v and v > 0]
    if lengths:
        out["smallest"], out["largest"] = min(lengths), max(lengths)
    ratios = [v for v in aspect_ratios if v and v > 0]
    if ratios:
        out["worst_aspect"] = max(ratios)
        out["over_limit"] = sum(1 for v in ratios if v > limit)
    return out


def mesh_quality_note(info, limit):
    """A sentence when the mesh has elements stretched far beyond the study's aspect ratio
    limit (a thin wall or a sliver met by large elements: the results near them are less
    accurate), else None. `info`: mesh_quality's dict with "elements"."""
    worst = info.get("worst_aspect")
    over = int(info.get("over_limit") or 0)
    count = int(info.get("elements") or 0)
    if not worst or worst <= 3.0 * float(limit) and over <= 0.01 * max(count, 1):
        return None
    return (
        "%d of the %d mesh elements are stretched more than %s:1 (the worst %s:1): results near "
        "them are less accurate. A thin wall needs smaller elements (the Average Element Size, "
        "or a Local Mesh Control on it); a tiny step or sliver face is better removed from the "
        "model." % (over, count, fmt(limit, 3), fmt(worst, 3))
    )


def tetra_aspect(p0, p1, p2, p3):
    """Aspect ratio of a tetrahedron from its corners: the longest edge over the smallest
    height, scaled so a regular tetrahedron gives 1 (sqrt(3/2) * edge / height)."""
    pts = (p0, p1, p2, p3)
    edges = [_norm(_sub(pts[i], pts[j])) for i in range(4) for j in range(i + 1, 4)]
    volume = abs(_dot(_sub(p1, p0), _cross(_sub(p2, p0), _sub(p3, p0)))) / 6.0
    if volume <= 0:
        return float("inf")
    faces = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))
    largest_face = max(
        _norm(_cross(_sub(pts[j], pts[i]), _sub(pts[k], pts[i]))) / 2.0 for i, j, k in faces
    )
    height = 3.0 * volume / largest_face
    return max(edges) / height / math.sqrt(1.5)


# -- curved elements turned inside out -------------------------------------------------------------
# A curved parabolic tetrahedron has its mid-side nodes on the model's curved faces. Where an
# element is large next to a tight curve (a small hole in a coarse mesh) a curved edge can push
# through the element's other faces: it turns inside out and CalculiX stops ("nonpositive
# jacobian"). SciForge checks every curved element where CalculiX integrates it, at its corners
# and in its middle, and makes the bad ones straight-sided (their mid-side nodes back to the
# middle of their edges). Gmsh's own repair (HighOrderOptimize) took minutes on a big part.
TET10_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))  # CalculiX's C3D10 nodes 5-10
_GA, _GB = 0.5854101966249685, 0.1381966011250105
TET10_POINTS = (  # (L1, L2, L3, L4): CalculiX's four integration points, the corners, the middle
    (_GA, _GB, _GB, _GB),
    (_GB, _GA, _GB, _GB),
    (_GB, _GB, _GA, _GB),
    (_GB, _GB, _GB, _GA),
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
    (0.25, 0.25, 0.25, 0.25),
)
# Only elements inside out or nearly (the Jacobian somewhere below 1 % of the straight-sided
# element's) are made straight: a low but positive Jacobian solves well, and every straightened
# element flattens a bit of a curved face (straightening all below Gmsh's own aim of 10 % made
# a coarse shaft 18 % too soft in torsion; this rule: 1.2 %)
DISTORTION_LIMIT = 0.01


def tet10_gradients(point):
    """d N / d (xi, eta, zeta) of the ten shape functions of a parabolic tetrahedron at
    `point` (L1..L4, with L2 = xi, L3 = eta, L4 = zeta), in CalculiX's node order."""
    l1, l2, l3, l4 = point
    return [
        (1.0 - 4.0 * l1, 1.0 - 4.0 * l1, 1.0 - 4.0 * l1),
        (4.0 * l2 - 1.0, 0.0, 0.0),
        (0.0, 4.0 * l3 - 1.0, 0.0),
        (0.0, 0.0, 4.0 * l4 - 1.0),
        (4.0 * (l1 - l2), -4.0 * l2, -4.0 * l2),
        (4.0 * l3, 4.0 * l2, 0.0),
        (-4.0 * l3, 4.0 * (l1 - l3), -4.0 * l3),
        (-4.0 * l4, -4.0 * l4, 4.0 * (l1 - l4)),
        (4.0 * l4, 0.0, 4.0 * l2),
        (0.0, 4.0 * l4, 4.0 * l3),
    ]


def tet10_distortion(xyz, elements, chunk=20000):
    """For each parabolic tetrahedron, its smallest Jacobian over TET10_POINTS as a fraction
    of its straight-sided one (1: as good as straight; 0 or less: inside out; -inf: its
    corners themselves are inside out or flat, which straight sides do not mend). `xyz`:
    numpy (nodes, 3) array; `elements`: numpy (elements, 10) array of rows of `xyz`, in
    CalculiX's node order. Worked in chunks (a big mesh would need gigabytes at once)."""
    import numpy as np

    grads = np.array([tet10_gradients(p) for p in TET10_POINTS], dtype=float)
    out = np.empty(len(elements))
    for start in range(0, len(elements), chunk):
        coords = xyz[elements[start : start + chunk]]
        det = np.linalg.det(np.einsum("eai,paj->epij", coords, grads))
        c = coords[:, :4]
        straight = np.einsum(
            "ei,ei->e", c[:, 1] - c[:, 0], np.cross(c[:, 2] - c[:, 0], c[:, 3] - c[:, 0])
        )
        part = np.full(len(coords), -np.inf)
        good = straight > 0.0
        part[good] = (det[good] / straight[good, None]).min(axis=1)
        out[start : start + chunk] = part
    return out


def straighten_tets(xyz, elements, limit=DISTORTION_LIMIT, rounds=8):
    """Make the parabolic tetrahedra whose distortion (tet10_distortion) is below `limit`
    straight-sided, in place: their mid-side nodes moved to the middle of their edges; then
    the same for the neighbours this changed, until none is left or after `rounds` passes.
    `xyz`: numpy (nodes, 3) float array; `elements`: numpy (elements, 10) int array of rows
    of `xyz`. Returns (sorted moved rows of `xyz`, how many elements were made straight, how
    many are still bad: inside out at their corners, or left after `rounds`)."""
    import numpy as np

    elements = np.asarray(elements)
    straight = np.zeros(len(elements), dtype=bool)
    moved = set()
    ends_a = [a for a, _b in TET10_EDGES]
    ends_b = [b for _a, b in TET10_EDGES]
    worst = tet10_distortion(xyz, elements)
    check = np.arange(len(elements))
    for _round in range(rounds):
        bad = check[(worst[check] < limit) & np.isfinite(worst[check])]
        if not len(bad):
            break
        rows = elements[bad]
        mids = rows[:, 4:]
        xyz[mids] = 0.5 * (xyz[rows[:, ends_a]] + xyz[rows[:, ends_b]])
        straight[bad] = True
        changed = np.unique(mids)
        moved.update(int(n) for n in changed)
        worst[bad] = 1.0
        check = np.nonzero(np.isin(elements[:, 4:], changed).any(axis=1) & ~straight)[0]
        if len(check):
            worst[check] = tet10_distortion(xyz, elements[check])
    left = int(np.count_nonzero(worst < limit))
    return sorted(moved), int(np.count_nonzero(straight)), left


# -- pre-check -------------------------------------------------------------------------------------
def precheck(summary):
    """What is missing before a solve, as [(level, sentence)] with level "error" (cannot
    solve) or "warning" (solves, but the result may not be what was meant).

    `summary`: {"bodies": [names], "materials": {body: (material name, props)},
    "constraints": [(kind, picks count, suppressed)], "loads": [...], "gravity": bool,
    "safety_basis", "lost": [item labels whose picks are gone], "loose": [bodies held by
    nothing], "overlaps": [(body, body, volume mm3)], "twice": [(item, item)] constrained on
    the same face, "remove_rigid": bool, "order": "parabolic" | "linear"}"""
    out = []
    bodies = summary.get("bodies") or []
    remove_rigid = bool(summary.get("remove_rigid"))
    if not bodies:
        out.append(("error", "The study has no solid body to simulate."))
    for body, (name, props) in sorted((summary.get("materials") or {}).items()):
        for text in material_problems(name, props):
            out.append(("error", "%s: %s" % (body, text)))
        if summary.get("gravity") and not _positive(props.get("density")):
            out.append(
                (
                    "error",
                    "%s: %s has no density, so gravity cannot act on it: choose another "
                    "study material or switch gravity off." % (body, name),
                )
            )
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
    if bodies and not active and not remove_rigid:
        out.append(
            (
                "error",
                "Nothing holds the model: add a constraint (Fixed) to keep it in place, or "
                "switch on Remove rigid body modes if its loads balance each other.",
            )
        )
    if remove_rigid and active:
        out.append(
            (
                "warning",
                "Remove rigid body modes is on while constraints hold the model: it is meant "
                "for a model held by nothing whose loads balance; the reactions may be wrong.",
            )
        )
    elif remove_rigid:
        out.append(
            (
                "warning",
                "Remove rigid body modes is on: the loads must balance each other, or the "
                "results are wrong.",
            )
        )
    loads = [c for c in summary.get("loads") or [] if not c[2]]
    if bodies and not loads and not summary.get("gravity"):
        out.append(("warning", "Nothing pushes on the model: add a load or switch gravity on."))
    for label in summary.get("lost") or []:
        out.append(("error", "%s lost what it was on: edit it and pick again." % label))
    if not remove_rigid:
        for body in summary.get("loose") or []:
            out.append(
                (
                    "error",
                    "%s is not held by a constraint and does not touch a held body: it would "
                    "fly away. Add a constraint on it, or leave it out of the study." % body,
                )
            )
    for a, b, volume in summary.get("overlaps") or []:
        out.append(
            (
                "warning",
                "%s and %s overlap (%s mm3): the shared part is simulated once, as part of %s. "
                "Move them apart or combine them if that is not what you meant."
                % (a, b, fmt(volume, 3), a),
            )
        )
    for a, b in summary.get("twice") or []:
        out.append(
            (
                "warning",
                "%s and %s constrain the same face: where they ask for different things, "
                "%s wins." % (a, b, a),
            )
        )
    if summary.get("order") == "linear" and bodies:
        # (measured: a cantilever bends 0.082 mm instead of 0.200 at the default size, 0.161
        # at 3 %; parabolic: 0.1995)
        out.append(
            (
                "warning",
                "Linear elements are much too stiff where a part bends: a beam bends about half "
                "as much as it should at the default mesh size. Use Parabolic (the default) "
                "unless the mesh is very fine.",
            )
        )
    return out


def can_solve(checks):
    return not any(level == "error" for level, _text in checks)

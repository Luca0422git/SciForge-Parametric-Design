# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION workspace's SETUP side, the rules without FreeCAD and without Qt (unit tested
in SciForgeTests/unit/test_simulation_setup_core.py): the New Study dialog's descriptions, the
pre-check's traffic light, the solve stages in plain words, forces typed as components, the
study tree of the browser, the right-click menus, and the geometry of the glyphs drawn on the
model (arrows, arcs).

The dialogs are simulation_dialogs.py / simulation_panels.py / simulation_solve_dialog.py, the
workspace switch and the commands simulation_ui.py, the browser simulation_browser.py, the
glyphs simulation_glyphs.py. The engine (studies, items, solving) is simulation.py and
simulation_core.py (builder sim-core). Spec: docs/sciforge/parity/simulation.md "Setup";
Fusion's behaviour with sources: docs/sciforge/dev/research/fusion-simulation.md.
"""

import math

from . import browser_core as bcore
from . import simulation_core as core

# -- New Study -------------------------------------------------------------------------------
# One line per study type for the New Study dialog (SciForge's own words; Fusion shows a
# description of the type picked, research 2.1).
STUDY_TEXT = {
    "static_stress": (
        "How a part bends and how close it comes to breaking under loads that do not change: "
        "displacement, stress and safety factor. Solved on this computer."
    ),
    "modal": "The frequencies a part vibrates at by itself, and how it moves at each.",
    "thermal": "How heat spreads through the parts and the temperatures they reach.",
    "thermal_stress": "Stress caused by heating and cooling, from a temperature study.",
    "buckling": "The load at which a slender part suddenly gives way sideways.",
    "nonlinear_static": "Large movements, contacts that open and close, materials that yield.",
    "event": "Fast events over time: drops, impacts.",
    "quasi_static": "Slow loading with large movements, solved like an event over time.",
    "shape_optimization": "Removes material where a part does not need it.",
    "electronics_cooling": "Board temperatures with air flowing over the parts.",
    "injection_molding": "How molten plastic fills a mould.",
}
LIMITS = (
    "Static Stress here is linear: small movements, the material stays elastic and is the same "
    "in every direction (3D-printed parts are not), loads do not change. Treat the results as a "
    "guide, not a guarantee."
)


def study_rows():
    """[(key, title, available, text)] in Fusion's order (simulation_core.STUDY_TYPES); the
    text of a type SciForge cannot solve says so."""
    rows = []
    for key, title, available in core.STUDY_TYPES:
        text = STUDY_TEXT.get(key, "")
        if not available:
            text = (text + " " if text else "") + "Not in SciForge yet."
        rows.append((key, title, available, text))
    return rows


# -- pre-check: Fusion's traffic light (research 3.9) -----------------------------------------
LIGHTS = ("green", "yellow", "red")
LIGHT_ICONS = {
    "green": "sim_precheck_ok",
    "yellow": "sim_precheck_warn",
    "red": "sim_precheck_error",
    None: "sim_precheck",
}
LIGHT_TEXT = {
    "green": "Ready to solve.",
    "yellow": "It can solve, but check these first:",
    "red": "It cannot solve yet:",
    None: "No study: make one with New Simulation Study.",
}


def light(checks):
    """ "red" when a check is an error (cannot solve), "yellow" when there are only warnings,
    "green" when there is nothing to say. `checks`: [(level, sentence)] of the pre-check."""
    levels = {level for level, _text in checks or []}
    if "error" in levels:
        return "red"
    if levels:
        return "yellow"
    return "green"


def light_icon(state):
    return LIGHT_ICONS.get(state, LIGHT_ICONS[None])


def light_text(state):
    return LIGHT_TEXT.get(state, LIGHT_TEXT[None])


def ordered_checks(checks):
    """Errors first, then warnings, each in the order found."""
    checks = list(checks or [])
    return [c for c in checks if c[0] == "error"] + [c for c in checks if c[0] != "error"]


# -- solving ---------------------------------------------------------------------------------
STAGE_WORDS = (
    ("model", "Preparing the model"),
    ("mesh", "Meshing"),
    ("input", "Writing the solver input"),
    ("solve", "Solving"),
    ("results", "Reading the results"),
)
STATE_WORDS = {
    "running": "Running",
    "done": "Done",
    "failed": "Stopped",
    "cancelled": "Cancelled",
    "waiting": "Waiting",
    "suspect": "Not held enough",
}


def stage_rows(stage, state, stages=None):
    """[(stage key, words, status)] for the progress list: stages before `stage` are "done",
    `stage` is `state` ("running", or how the job ended), later ones "waiting" ("done" for all
    once the job is done)."""
    stages = stages or [k for k, _w in STAGE_WORDS]
    words = dict(STAGE_WORDS)
    rows = []
    try:
        at = stages.index(stage)
    except ValueError:
        at = 0
    for i, key in enumerate(stages):
        if state == "done":
            status = "done"
        elif i < at:
            status = "done"
        elif i == at:
            status = state
        else:
            status = "waiting"
        rows.append((key, words.get(key, key.title()), status))
    return rows


def elapsed_text(seconds):
    """ "0:07", "12:34", "1:02:03"."""
    seconds = max(int(seconds or 0), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def solve_button_text(count):
    """Fusion's button names the count: "Solve 1 Study", "Solve 2 Studies"."""
    if count <= 0:
        return "Solve"
    return "Solve %d %s" % (count, "Study" if count == 1 else "Studies")


def repair_step(info):
    """Fusion's Repair button (research 3.10) for a study that cannot solve: where to take the
    person first, as (what, name, sentence). `info`: {"lost": [item labels that lost their
    picks], "held": count of constraints not suppressed, "remove_rigid": bool, "loose": [body
    labels nothing holds], "materials": [body labels whose study material lacks what the solve
    needs], "outside": [(item label, body label) of items on bodies the study leaves out],
    "suppressed": [labels of suppressed constraints]}.
    what: "edit" (the item's dialog), "constraints" (Structural Constraints), "dof" (DOF View
    shows how the bodies move), "materials" (Study Materials) or "precheck" (the list). A
    study without a solid body ("bodies": 0) goes to the list: nothing in it can be picked."""
    if info.get("bodies") == 0:
        return (
            "precheck",
            None,
            "The study has no solid body to simulate: add one in Design (or tick one In Study).",
        )
    lost = info.get("lost") or []
    if lost:
        return (
            "edit",
            lost[0],
            "%s lost what it was on (the design changed): pick it again and press OK." % lost[0],
        )
    if not info.get("held") and not info.get("remove_rigid"):
        off = info.get("suppressed") or []
        if off:
            return (
                "constraints",
                None,
                "Nothing holds the model: %s %s suppressed (right-click > Unsuppress), or pick "
                "where it is held for a new one and press OK."
                % (", ".join(off), "is" if len(off) == 1 else "are"),
            )
        return (
            "constraints",
            None,
            "Nothing holds the model: pick where it is held (a Fixed face is the simplest) and "
            "press OK.",
        )
    loose = info.get("loose") or []
    if loose and not info.get("remove_rigid"):
        return (
            "dof",
            loose[0],
            "%s %s not held: DOF View shows how %s can move; add a constraint on %s, or leave "
            "%s out of the study."
            % (
                ", ".join(loose),
                "is" if len(loose) == 1 else "are",
                "it" if len(loose) == 1 else "they",
                "it" if len(loose) == 1 else "them",
                "it" if len(loose) == 1 else "them",
            ),
        )
    materials = info.get("materials") or []
    if materials:
        return (
            "materials",
            materials[0],
            "%s: its study material lacks a value the solve needs: choose another material for "
            "it." % materials[0],
        )
    outside = info.get("outside") or []
    if outside:
        item, body = outside[0]
        return (
            "materials",
            body,
            "%s is on %s, which the study leaves out: tick %s In Study (or suppress %s)."
            % (item, body, body, item),
        )
    return "precheck", None, "The pre-check lists what stops the study from solving."


# -- forces typed as components (Fusion's Vector direction: Fx, Fy, Fz) ----------------------
def force_from_components(fx, fy, fz):
    """(magnitude, unit direction) of a force typed as its X, Y and Z parts (N)."""
    parts = [float(fx), float(fy), float(fz)]
    size = math.sqrt(sum(p * p for p in parts))
    if size <= 1e-12:
        raise core.SimulationError("A force of 0 does nothing: type a value in X, Y or Z.")
    return size, [p / size for p in parts]


def components_of(magnitude, vector):
    """The X, Y and Z parts (N) of a force of `magnitude` along `vector`."""
    try:
        unit = core.unit_vector(vector)
    except core.SimulationError:
        unit = [0.0, 0.0, -1.0]
    return [float(magnitude) * c for c in unit]


# -- Fusion's Angle direction type (a force or a moment turned from the face's normal) ------------
def turned(vector, angles):
    """`vector` turned by `angles` (degrees) about the design's X axis, then Y, then Z: the
    direction of a load whose Direction Type is Angle (it starts from the first picked face's
    normal). Values within 1e-12 of 0 are 0."""
    x, y, z = [float(c) for c in vector]
    ax, ay, az = [math.radians(float(a or 0.0)) for a in angles]
    c, s = math.cos(ax), math.sin(ax)
    y, z = c * y - s * z, s * y + c * z
    c, s = math.cos(ay), math.sin(ay)
    x, z = c * x + s * z, c * z - s * x
    c, s = math.cos(az), math.sin(az)
    x, y = c * x - s * y, s * x + c * y
    return [0.0 if abs(v) < 1e-12 else v for v in (x, y, z)]


# -- the study tree of the browser (research 4) -----------------------------------------------
ITEM_ICONS = {
    ("constraint", "fixed"): "sim_fixed",
    ("constraint", "pin"): "sim_pin",
    ("constraint", "frictionless"): "sim_frictionless",
    ("constraint", "displacement"): "sim_displacement",
    ("load", "force"): "sim_force",
    ("load", "pressure"): "sim_pressure",
    ("load", "moment"): "sim_moment",
    ("load", "bearing"): "sim_bearing",
    ("load", "remote_force"): "sim_remote_force",
}


def item_icon(category, kind):
    if category == "constraint":
        return ITEM_ICONS.get((category, kind), "sim_constraints")
    if category == "load":
        return ITEM_ICONS.get((category, kind), "sim_loads")
    return "sim_local_mesh"


def _item_node(study_name, item):
    node = bcore._node(
        "sim_item:" + item["name"],
        item["label"],
        item_icon(item["category"], item["kind"]),
        "sim_item",
        item["name"],
        None,
        study=study_name,
        category=item["category"],
        item_kind=item["kind"],
        object_label=item.get("object_label", item["label"]),
    )
    tips = [item.get("describe") or ""]
    if item.get("suppressed"):
        node["status"] = "suppressed"
        tips.append("Suppressed: left out of the solve")
    elif item.get("lost"):
        node["status"] = "error"
        tips.append("Lost what it was on: edit it and pick again")
    elif item.get("unbuilt"):
        node["status"] = "warning"
        tips.append("Not in SciForge yet: suppress or delete it")
    node["tip"] = "; ".join(t for t in tips if t)
    return node


def study_node(study, active):
    """One study's subtree. `study`: {"name", "label", "type", "constraints": [item], "loads":
    [item], "gravity": bool, "gravity_text", "mesh": "made" | "" , "mesh_text", "local": [item],
    "solved": bool, "out_of_date": bool, "results_text", "contacts_text", "materials_text"};
    item: {"name", "label", "category", "kind", "suppressed", "lost", "unbuilt", "describe"}."""
    name = study["name"]
    constraints = [_item_node(name, i) for i in study.get("constraints", [])]
    loads = [_item_node(name, i) for i in study.get("loads", [])]
    if study.get("gravity"):
        loads.append(
            bcore._node(
                "sim_gravity:" + name,
                "Gravity",
                "sim_gravity",
                "sim_gravity",
                name,
                None,
                study=name,
                tip=study.get("gravity_text", "Gravity on: every body weighs on the model"),
            )
        )
    case_children = [
        bcore._node(
            "sim_constraints:" + name,
            "Constraints",
            "folder",
            "sim_folder",
            None,
            None,
            children=constraints,
            study=name,
            tip="Where the model is held",
        ),
        bcore._node(
            "sim_loads:" + name,
            "Loads",
            "folder",
            "sim_folder",
            None,
            None,
            children=loads,
            study=name,
            tip="What pushes on the model",
        ),
    ]
    mesh_children = [_item_node(name, i) for i in study.get("local", [])]
    mesh = bcore._node(
        "sim_mesh:" + name,
        "Mesh",
        "sim_mesh",
        "sim_mesh",
        name,
        None,
        children=mesh_children,
        study=name,
        tip=study.get("mesh_text") or "Made when the study solves (right-click: Generate Mesh)",
    )
    children = [
        bcore._node(
            "sim_materials:" + name,
            "Study Materials",
            "sim_materials",
            "sim_materials",
            name,
            None,
            study=name,
            tip=study.get("materials_text", "The material of each body in this study"),
        ),
        bcore._node(
            "sim_loadcase:" + name,
            "Load Case 1",
            "sim_loadcase",
            "sim_loadcase",
            name,
            None,
            children=case_children,
            study=name,
            tip="The constraints and loads solved together",
        ),
        bcore._node(
            "sim_contacts:" + name,
            "Contacts",
            "sim_contacts",
            "sim_contacts",
            name,
            None,
            study=name,
            tip=study.get(
                "contacts_text", "Bodies that touch are bonded (glued) automatically when it solves"
            ),
        ),
        mesh,
    ]
    if study.get("solved"):
        results = bcore._node(
            "sim_results:" + name,
            "Results",
            "sim_results",
            "sim_results",
            name,
            None,
            study=name,
            tip=study.get("results_text", "Double-click to show the results"),
        )
        if study.get("out_of_date"):
            results["status"] = "warning"
            results["label"] = "Results (out of date)"
            results["tip"] = (
                "The design or the study changed after the solve: solve again for results "
                "that match it"
            )
        children.append(results)
    node = bcore._node(
        "sim_study:" + name,
        study["label"],
        "sim_study",
        "sim_study",
        name,
        None,
        children=children,
        object_label=study.get("object_label", study["label"]),
    )
    node["active"] = bool(active)
    node["tip"] = (
        "Active study: the SETUP commands work on it"
        if active
        else "Double-click to make it the active study"
    )
    return node


def tree(doc_label, units, studies, active, model_bodies, views=()):
    """The browser in the SIMULATION workspace: Document Settings, Named Views, then Fusion's
    simulation model with the design's bodies and the studies under it (research 4).
    `studies`: [study dict] (study_node); `active`: name of the active study; `model_bodies`:
    [{"name", "label", "visible", "in_study"}]."""
    settings = bcore._node(
        "settings",
        "Document Settings",
        "tl_settings",
        "settings",
        children=[
            bcore._node(
                "settings:units",
                "Units: %s" % units,
                "units",
                "units",
                tip="Click to change the units of this design",
            )
        ],
    )
    named = [
        bcore._node("view:" + label, label.upper(), "nav_lookat", "view", command)
        for label, command in bcore.NAMED_VIEWS
    ]
    named += [bcore._node("saved_view:" + v, v, "nav_lookat", "saved_view", v) for v in views or ()]
    rows = []
    for body in model_bodies or []:
        row = bcore._node(
            "sim_body:" + body["name"],
            body["label"],
            "box",
            "sim_body",
            body["name"],
            body.get("visible"),
            object_label=body.get("object_label", body["label"]),
        )
        if not body.get("in_study", True):
            row["status"] = "suppressed"
            row["tip"] = "Left out of the active study (right-click: Include in Study)"
        rows.append(row)
    model_children = []
    if rows:
        model_children.append(bcore._folder("sim_bodies", "Bodies", rows))
    model_children += [study_node(s, s["name"] == active) for s in studies or []]
    model = bcore._node(
        "sim_model",
        "Simulation Model",
        "workspace_simulation",
        "sim_model",
        children=model_children,
        tip="The design as it is now: every study uses its bodies",
    )
    children = [settings, bcore._node("views", "Named Views", "folder", "views", children=named)]
    children.append(model)
    return bcore._node("document", doc_label, "document", "sim_document", children=children)


# Rows that start open in the SIMULATION browser (keys made per study start open too).
OPEN_KEYS = ("sim_model", "sim_bodies")
OPEN_PREFIXES = ("sim_loadcase:", "sim_constraints:", "sim_loads:", "sim_mesh:")

# What the right-click menu offers per kind of row, in Fusion's order (research 4; the
# entries that do not apply to a row are left out by simulation_browser).
MENUS = {
    "sim_study": [
        "Activate",
        "Settings",
        "Clone Study",
        "-",
        "Rename",
        "Delete",
    ],
    "sim_materials": ["Study Materials"],
    "sim_loadcase": ["Load Case Attributes", "-", "Structural Constraints", "Structural Loads"],
    "sim_folder": [],
    "sim_item": ["Edit", "-", "Suppress", "-", "Rename", "Delete"],
    "sim_gravity": ["Edit Gravity", "-", "Toggle Gravity Off"],
    "sim_contacts": ["Automatic Contacts", "Contact Manager"],
    "sim_mesh": ["Generate Mesh", "Mesh Settings", "Local Mesh Control"],
    "sim_results": ["Show Results", "-", "Solve"],
    "sim_body": ["Show/Hide", "-", "Exclude from Study"],
    "sim_model": [],
    "sim_document": ["Rename"],
}


def menu_for(node):
    """Right-click entries for a row of the SIMULATION browser ("-" is a separator)."""
    entries = list(MENUS.get(node.get("kind"), []))
    if node.get("kind") == "sim_study" and node.get("active"):
        entries = [e for e in entries if e != "Activate"]
    if node.get("kind") == "sim_body" and node.get("status") == "suppressed":
        entries = ["Include in Study" if e == "Exclude from Study" else e for e in entries]
    if node.get("kind") == "sim_item" and node.get("status") == "suppressed":
        entries = ["Unsuppress" if e == "Suppress" else e for e in entries]
    if node.get("kind") == "sim_item":
        what = "Load" if node.get("category") == "load" else "Constraint"
        if node.get("category") == "mesh":
            what = "Local Mesh Control"
        entries = [("Edit %s" % what) if e == "Edit" else e for e in entries]
    return entries


# -- glyph geometry (simulation_glyphs.py draws them with Coin) ---------------------------------
GLYPH_PIXELS = 46.0  # the length of a load arrow on the screen
GLYPH_MIN_MM = 0.2


def glyph_size(mm_per_pixel, pixels=GLYPH_PIXELS):
    """Size (mm) of a glyph that is `pixels` long on the screen at `mm_per_pixel`."""
    try:
        return max(float(mm_per_pixel) * float(pixels), GLYPH_MIN_MM)
    except (TypeError, ValueError):
        return 5.0


def norm(v):
    length = math.sqrt(sum(float(c) ** 2 for c in v))
    if length <= 1e-12:
        return None
    return tuple(float(c) / length for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def perpendicular(v):
    """A unit vector at right angles to `v`."""
    v = norm(v) or (0.0, 0.0, 1.0)
    other = (1.0, 0.0, 0.0) if abs(v[0]) < 0.9 else (0.0, 1.0, 0.0)
    return norm(cross(v, other))


def arc_points(centre, axis, radius, sweep_deg=270.0, count=24, start=None):
    """Points on an arc of `sweep_deg` degrees around `axis` through `centre` (a moment's
    curved arrow), turning the right-hand way about the axis."""
    axis = norm(axis) or (0.0, 0.0, 1.0)
    u = norm(start) if start is not None else perpendicular(axis)
    if u is None or abs(sum(a * b for a, b in zip(u, axis))) > 0.99:
        u = perpendicular(axis)
    w = cross(axis, u)
    out = []
    for i in range(count + 1):
        t = math.radians(sweep_deg) * i / float(count)
        c, s = math.cos(t), math.sin(t)
        out.append(tuple(centre[k] + radius * (c * u[k] + s * w[k]) for k in range(3)))
    return out


def arc_tangent(axis, point, centre):
    """The direction an arc around `axis` runs at `point` (unit)."""
    axis = norm(axis) or (0.0, 0.0, 1.0)
    radial = norm([p - c for p, c in zip(point, centre)]) or perpendicular(axis)
    return norm(cross(axis, radial))


def grid_fractions(count):
    """`count` evenly spread fractions inside 0..1 (the middle of `count` equal slices)."""
    count = max(int(count), 1)
    return [(i + 0.5) / count for i in range(count)]


def samples_per_side(extent, spacing, most=5):
    """How many glyphs across a face side `extent` long when glyphs are `spacing` apart."""
    if spacing <= 0:
        return 1
    return max(1, min(int(most), int(round(float(extent) / float(spacing)))))


# -- values typed with a unit (Fusion: every value field takes a unit override, research 6) -----
# family -> (unit SciForge's engine works in, {unit typed (normalised): factor to that unit})
QUANTITIES = {
    "force": (
        "N",
        {
            "n": 1.0,
            "kn": 1000.0,
            "mn": 0.001,
            "lbf": 4.4482216152605,
            "lb": 4.4482216152605,
            "kgf": 9.80665,
        },
    ),
    "pressure": (
        "MPa",
        {
            "mpa": 1.0,
            "n/mm2": 1.0,
            "kpa": 1e-3,
            "pa": 1e-6,
            "gpa": 1000.0,
            "bar": 0.1,
            "psi": 0.00689475729,
            "ksi": 6.89475729,
        },
    ),
    "moment": (
        "N mm",
        {
            "nmm": 1.0,
            "nm": 1000.0,
            "knm": 1e6,
            "lbfin": 112.984829,
            "lbfft": 1355.81795,
            "inlbf": 112.984829,
            "ftlbf": 1355.81795,
        },
    ),
    "length": (
        "mm",
        {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, '"': 25.4, "ft": 304.8, "um": 0.001},
    ),
    "acceleration": (
        "mm/s^2",
        {"mm/s2": 1.0, "m/s2": 1000.0, "g": 9806.65, "in/s2": 25.4, "ft/s2": 304.8},
    ),
    "angle": ("deg", {"deg": 1.0, "°": 1.0, "rad": 180.0 / math.pi}),
    "percent": ("%", {"%": 1.0}),
    "number": ("", {}),
}
FAMILY_OF_UNIT = {"N": "force", "MPa": "pressure", "N mm": "moment", "mm": "length"}


def _unit_key(text):
    key = text.strip().lower().replace("²", "2").replace("^", "")
    for ch in (" ", "*", "·", "-", "."):
        key = key.replace(ch, "")
    return key


def parse_quantity(text, family, shown=None):
    """A value typed in a field ("100", "100 N", "0.5 kN", "2 MPa", "10 lbf") in the unit the
    engine works in for `family` (QUANTITIES). A bare number is in `shown`, the unit the field
    shows (the engine's when None). Raises SimulationError with a sentence."""
    unit, factors = QUANTITIES.get(family, ("", {}))
    raw = str(text or "").strip().replace(",", ".")
    if not raw:
        raise core.SimulationError("Type a value.")
    number = ""
    i = 0
    while i < len(raw) and (raw[i].isdigit() or raw[i] in "+-.eE"):
        if raw[i] in "eE" and not (
            i + 1 < len(raw) and (raw[i + 1].isdigit() or raw[i + 1] in "+-")
        ):
            break
        number += raw[i]
        i += 1
    rest = raw[i:].strip()
    try:
        value = float(number)
    except ValueError:
        raise core.SimulationError("%r is not a number." % raw)
    if not rest:
        return value * unit_factor(family, shown)
    key = _unit_key(rest)
    if key in factors:
        return value * factors[key]
    if _unit_key(unit) == key:
        return value
    known = ", ".join(sorted({k for k in factors if k not in ('"',)}))
    raise core.SimulationError(
        "%s is not a unit this field takes%s." % (rest, (" (" + known + ")") if known else "")
    )


def format_quantity(value, family, digits=6, shown=None):
    """`value` (in the engine's unit of `family`) as a field shows it, in `shown` (the engine's
    unit when None): "100 N", "22.48 lbf"."""
    unit = shown or QUANTITIES.get(family, ("", {}))[0]
    text = core.fmt(value / unit_factor(family, unit), digits)
    return text + (" " + unit if unit else "")


def unit_factor(family, unit):
    """How many of the engine's units of `family` one `unit` is (1 for the engine's own)."""
    base, factors = QUANTITIES.get(family, ("", {}))
    if not unit or _unit_key(unit) == _unit_key(base):
        return 1.0
    return factors.get(_unit_key(unit), 1.0)


# The units the value fields of a design show (Fusion: Simulation follows the document's units,
# research 6): N, MPa and N mm with a metric length, lbf, psi and lbf in with inches or feet.
# The engine keeps N, MPa, N mm and mm whatever the design shows.
UNIT_SETS = {
    "mm": {
        "force": "N",
        "pressure": "MPa",
        "moment": "N mm",
        "length": "mm",
        "acceleration": "m/s^2",
    },
    "cm": {
        "force": "N",
        "pressure": "MPa",
        "moment": "N mm",
        "length": "cm",
        "acceleration": "m/s^2",
    },
    "m": {"force": "N", "pressure": "MPa", "moment": "N m", "length": "m", "acceleration": "m/s^2"},
    "in": {
        "force": "lbf",
        "pressure": "psi",
        "moment": "lbf in",
        "length": "in",
        "acceleration": "in/s^2",
    },
    "ft": {
        "force": "lbf",
        "pressure": "psi",
        "moment": "lbf ft",
        "length": "ft",
        "acceleration": "ft/s^2",
    },
}
MAGNITUDE_FAMILY = {"pressure": "pressure", "moment": "moment"}  # (the other loads: force)


def unit_set(doc_unit):
    """{family: unit shown} for a design whose length unit is `doc_unit` ("mm", "in", ...)."""
    return dict(UNIT_SETS.get(doc_unit or "mm", UNIT_SETS["mm"]))


def describe(category, kind, opts, units=None):
    """The engine's short text of a constraint or load ("Force 100 N") with its values in the
    design's units (`units` from unit_set)."""
    units = units or unit_set("mm")
    text = core.describe(category, kind, opts)
    try:
        opts = core.options(category, kind, opts)
        title = core.kind_info(category, kind)["title"]
        if category == "load":
            family = MAGNITUDE_FAMILY.get(kind, "force")
            return "%s %s" % (
                title,
                format_quantity(opts.get("magnitude", 0.0), family, 4, units.get(family)),
            )
        if category == "mesh":
            return "%s %s" % (
                title,
                format_quantity(opts.get("size", 0.0), "length", 4, units.get("length")),
            )
        if category == "constraint" and kind == "displacement":
            parts = [
                "%s %s" % (a.upper(), format_quantity(opts[a], "length", 4, units.get("length")))
                for a in ("x", "y", "z")
                if opts.get(a) is not None
            ]
            return "%s (%s)" % (title, ", ".join(parts))
    except Exception:
        pass
    return text

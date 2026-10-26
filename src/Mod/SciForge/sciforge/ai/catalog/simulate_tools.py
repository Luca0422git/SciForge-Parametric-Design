# SPDX-License-Identifier: LGPL-2.1-or-later
"""AI tools for Static Stress simulation (beta 3, builder sim-core): set up a study, solve it,
read its results. Fusion's SIMULATION workspace (Static Stress study only, outline 7.18):
create_study, add_constraint, add_load, local_mesh_control, set_study_material,
study_settings, precheck_study, solve_study, study_results, delete_study. The work is in
sciforge/ai/actions/simulate_actions.py, on the same engine as the workspace
(sciforge/simulation.py). Pure Python."""

from . import kit
from .kit import array, boolean, enum, free_object, number, positive, schema, step_ids, string
from .registry import define, example

CONSTRAINT_KINDS = ("fixed", "pin", "frictionless", "displacement")
LOAD_KINDS = ("force", "pressure", "moment", "bearing", "remote_force")
RESULT_KEYS = (
    "safety",
    "von_mises",
    "principal_1",
    "principal_3",
    "sxx",
    "syy",
    "szz",
    "sxy",
    "syz",
    "szx",
    "displacement",
    "dx",
    "dy",
    "dz",
    "strain",
)

PICKS_HELP = (
    'on: where it acts, a list of picks: {"face": selector}, {"edge": selector} or '
    '{"vertex": {"at": ...}} on a body, with "of": the body (or a step in it; default the '
    "active body). Every face / edge / corner a selector picks is used (give count)."
)
STUDY_HELP = "study: the study's id or name (create_study answers it; default the newest study)."


def _study():
    return string("the study's id or name (default: the newest study)")


def _picks(description):
    return array(free_object("a pick on a body (see the tool's description)"), description, 1)


def _extra_picks(args, problems, bodies_too=False):
    for i, pick in enumerate(args.get("on") or []):
        path = "on[%d]" % i
        if not isinstance(pick, dict):
            problems.append("%s must be a pick object: {face|edge|vertex: ..., of: body}" % path)
            continue
        if "body" in pick and not bodies_too:
            problems.append(
                "%s: a whole body is not a place for this; pick faces, edges or corners" % path
            )
            continue
        kit.check_body_pick(pick, path, problems)


def _extra_constraint(args, problems):
    _extra_picks(args, problems)
    kind = args.get("kind")
    for axis in ("x", "y", "z"):
        if axis not in args:
            continue
        value = args[axis]
        if kind == "fixed" and not isinstance(value, bool):
            problems.append("%s must be true or false for a fixed constraint (held or free)" % axis)
        if kind == "displacement" and not (value is None or kit.is_type(value, "number")):
            problems.append(
                "%s must be a distance in mm (or null: free) for a prescribed displacement" % axis
            )
        if kind in ("pin", "frictionless"):
            problems.append("%s does not apply to a %s constraint" % (axis, kind))
    for key in ("radial", "axial", "tangential"):
        if key in args and kind != "pin":
            problems.append("%s only applies to a pin" % key)
    if kind == "displacement" and not any(
        kit.is_type(args.get(axis), "number") for axis in ("x", "y", "z")
    ):
        problems.append("a prescribed displacement needs x, y or z (mm)")


def _extra_load(args, problems):
    _extra_picks(args, problems)
    kind = args.get("kind")
    if kind == "remote_force" and "point" not in args:
        problems.append("a remote force needs point: where it acts from [x, y, z] (mm)")
    if kind != "remote_force" and "point" in args:
        problems.append("point only applies to a remote force")
    if kind in ("bearing", "remote_force"):
        if args.get("direction") == "normal":
            problems.append("a %s takes a vector direction, not normal" % kind.replace("_", " "))
        if "vector" not in args:
            problems.append(
                "a %s needs vector: the direction it pushes [x, y, z]" % kind.replace("_", " ")
            )
    if kind == "pressure" and ("vector" in args or "direction" in args):
        problems.append("a pressure always pushes along the faces' normal: give no direction")
    if args.get("direction") == "vector" and "vector" not in args:
        problems.append("direction vector needs vector: [x, y, z]")
    if "per_entity" in args and kind not in ("force", "moment"):
        problems.append("per_entity only applies to a force or a moment")


def _extra_mesh(args, problems):
    _extra_picks(args, problems, bodies_too=True)


define(
    "create_study",
    "New simulation study",
    "simulate",
    "SIMULATION > SETUP > STUDY > New Simulation Study (Static Stress)",
    "Make a Static Stress study, Fusion's linear stress simulation: where a part is held "
    "(add_constraint), what pushes on it (add_load, or gravity in study_settings), then "
    "solve_study and study_results. The study uses each body's physical material (change it "
    "for the study only with set_study_material) and the bodies as they are now; bodies "
    "that touch (or are closer than 0.1 mm) are glued. bodies: the bodies it simulates "
    "(default: every solid body shown). Answers the study's id. Linear static only: small "
    "deflections, materials that stay elastic and isotropic (3D-printed parts are not); "
    "results are a guide.",
    schema(
        {
            "label": string('its name (default "Study N - Static Stress")'),
            "bodies": step_ids("the bodies to simulate (default: every solid body shown)"),
        }
    ),
    needs=("solid",),
    id_base="Study",
    title_fn=lambda a: "AI: New Static Stress study",
    examples=[
        example({}, "a study of every body"),
        example({"label": "Bracket load", "bodies": ["Body"]}, "a study of one body"),
    ],
)

define(
    "add_constraint",
    "Structural constraint",
    "simulate",
    "SIMULATION > SETUP > CONSTRAINTS > Structural Constraints",
    "Hold part of the model in a study (Fusion's structural constraints). kind: fixed (no "
    "movement; x / y / z false frees that design axis, a roller), pin (round faces only: "
    "radial keeps the hole's size and place, axial stops sliding along it, tangential stops "
    "turning about it; default radial and axial, so it can turn like a hinge), frictionless "
    "(faces: no movement across the face, free to slide along it: a symmetry plane or a "
    "smooth support), displacement (a prescribed displacement: x / y / z in mm, null = free). "
    + PICKS_HELP
    + " "
    + STUDY_HELP
    + " A model must be held so it cannot move or spin freely (six directions in all), or "
    "the solve fails with that reason.",
    schema(
        {
            "study": _study(),
            "kind": enum(CONSTRAINT_KINDS, "the kind of constraint"),
            "on": _picks("where it holds"),
            "x": {
                "type": ["boolean", "number", "null"],
                "description": "fixed: held along X (default true); displacement: mm or null",
            },
            "y": {
                "type": ["boolean", "number", "null"],
                "description": "fixed: held along Y (default true); displacement: mm or null",
            },
            "z": {
                "type": ["boolean", "number", "null"],
                "description": "fixed: held along Z (default true); displacement: mm or null",
            },
            "radial": boolean("pin: the hole keeps its size and place", default=True),
            "axial": boolean("pin: no sliding along the pin", default=True),
            "tangential": boolean("pin: no turning about the pin", default=False),
            "label": string("its name (default: Fixed 1, Pin 1...)"),
        },
        required=("kind", "on"),
    ),
    extra=_extra_constraint,
    id_base="Constraint",
    title_fn=lambda a: "AI: %s constraint" % str(a.get("kind", "")).capitalize(),
    examples=[
        example(
            {"kind": "fixed", "on": [{"face": {"normal": [0, 0, -1], "count": 1}}]},
            "the bottom face held in place",
        ),
        example(
            {"kind": "pin", "on": [{"face": {"type": "cylinder", "radius": 3.25, "count": 2}}]},
            "two holes on pins that let the part turn",
        ),
        example(
            {
                "kind": "frictionless",
                "on": [{"face": {"normal": [0, -1, 0], "count": 1}, "of": "Body"}],
            },
            "a symmetry plane",
        ),
        example(
            {
                "kind": "displacement",
                "on": [{"face": {"normal": [1, 0, 0], "count": 1}}],
                "x": None,
                "y": None,
                "z": -0.5,
            },
            "the end face pushed 0.5 mm down",
        ),
    ],
)

define(
    "add_load",
    "Structural load",
    "simulate",
    "SIMULATION > SETUP > LOADS > Structural Loads",
    "Push on part of the model in a study (Fusion's structural loads). kind: force (N; "
    "direction normal pushes into each picked face, Fusion's default; vector gives "
    "[x, y, z]; several picks share the force by area unless per_entity gives each one the "
    "whole force), pressure (MPa, always into the faces; negative pulls), moment (N mm "
    "about the first face's normal or about vector, spread over the faces as a twist that "
    "keeps them deformable; per_entity: each face gets the whole moment), bearing (N, round "
    "faces: a pin or shaft pressing along vector, most in the middle of the loaded half and "
    "never pulling), remote_force (N along vector acting from point [x, y, z] mm, carried to "
    "the faces with its lever arm). flip reverses it. "
    + PICKS_HELP
    + " "
    + STUDY_HELP
    + " Gravity is in study_settings.",
    schema(
        {
            "study": _study(),
            "kind": enum(LOAD_KINDS, "the kind of load"),
            "on": _picks("where it pushes"),
            "magnitude": number(
                "N (force, bearing, remote_force), MPa (pressure) or N mm (moment)"
            ),
            "direction": enum(
                ("normal", "vector"),
                "force / moment: along the face's normal or along vector",
                default="normal",
            ),
            "vector": dict(kit.vector3("the direction [x, y, z] (design axes)")),
            "point": dict(kit.point3("remote_force: where the force acts from (mm)")),
            "per_entity": boolean("force / moment: every pick gets the whole value", default=False),
            "flip": boolean("reverse the direction", default=False),
            "label": string("its name (default: Force 1, Pressure 1...)"),
        },
        required=("kind", "on", "magnitude"),
    ),
    extra=_extra_load,
    id_base="Load",
    title_fn=lambda a: "AI: %s load" % str(a.get("kind", "")).replace("_", " ").capitalize(),
    examples=[
        example(
            {
                "kind": "force",
                "on": [{"face": {"normal": [0, 0, 1], "count": 1}}],
                "magnitude": 200,
                "direction": "vector",
                "vector": [0, 0, -1],
            },
            "200 N pressing down on the top face",
        ),
        example(
            {
                "kind": "pressure",
                "on": [{"face": {"type": "cylinder", "count": 1}}],
                "magnitude": 2,
            },
            "2 MPa inside a bore",
        ),
        example(
            {
                "kind": "moment",
                "on": [{"face": {"normal": [0, 0, 1], "count": 1}}],
                "magnitude": 5000,
            },
            "5 N m twisting the end of a shaft about its axis",
        ),
        example(
            {
                "kind": "bearing",
                "on": [{"face": {"type": "cylinder", "count": 1}}],
                "magnitude": 1000,
                "vector": [0, 0, 1],
            },
            "a pin pulling a lug's hole upward with 1 kN",
        ),
        example(
            {
                "kind": "remote_force",
                "on": [{"face": {"normal": [1, 0, 0], "count": 1}}],
                "magnitude": 100,
                "vector": [0, 0, -1],
                "point": [150, 5, 5],
            },
            "100 N hanging 50 mm beyond the end face",
        ),
    ],
)

define(
    "local_mesh_control",
    "Local mesh control",
    "simulate",
    "SIMULATION > SETUP > MANAGE > Local Mesh Control",
    "Make the mesh finer (smaller elements, size in mm) on picked faces, edges or whole "
    "bodies of a study, blending back into the study's element size: where the stress "
    "matters (a hole, a fillet in a corner). "
    + PICKS_HELP
    + ' A whole body: {"body": id}. '
    + STUDY_HELP,
    schema(
        {
            "study": _study(),
            "on": _picks("where the mesh is finer"),
            "size": positive("the element size there (mm)"),
            "label": string("its name (default: Local Mesh Control 1...)"),
        },
        required=("on", "size"),
    ),
    extra=_extra_mesh,
    id_base="MeshControl",
    title_fn=lambda a: "AI: Local mesh control",
    examples=[
        example(
            {"on": [{"face": {"type": "cylinder", "count": 2}}], "size": 0.5},
            "0.5 mm elements in two holes",
        ),
    ],
)

define(
    "set_study_material",
    "Study material",
    "simulate",
    "SIMULATION > SETUP > MATERIALS > Study Materials",
    "Choose the material a body is made of in one study only (Fusion's Study Materials; the "
    "design keeps its own): material is a key of the material library (steel, stainless, "
    "iron, aluminium, aluminium_6061, copper, titanium, abs, pla, pet, nylon, polycarbonate, "
    "acetal, acrylic, polypropylene, ptfe, peek, wood, glass) or same_as_model to go back to "
    "the body's physical material. safety_basis: what the safety factor divides for the "
    "whole study (yield: yield strength / von Mises, Fusion's default; ultimate: ultimate "
    "tensile strength / 1st principal stress). Answers the values the study uses (E, "
    "Poisson's ratio, density, yield and ultimate strength). " + STUDY_HELP,
    schema(
        {
            "study": _study(),
            "body": string("the body (or a step in it)"),
            "material": string("a material key, or same_as_model"),
            "safety_basis": enum(("yield", "ultimate"), "what the safety factor divides"),
        },
        required=("body", "material"),
    ),
    id_base="StudyMaterial",
    title_fn=lambda a: "AI: Study material",
    examples=[
        example({"body": "Body", "material": "aluminium_6061"}, "this study in aluminium 6061"),
        example({"body": "Body", "material": "same_as_model"}, "back to the body's material"),
    ],
)

define(
    "study_settings",
    "Study settings",
    "simulate",
    "SIMULATION > SETUP > MANAGE > Settings",
    "Read or change a study's settings; with none given it answers them all. mesh_size: "
    "average element size in % of the model's size (default 10, Fusion's; smaller is finer "
    "and slower), or mesh_size_mm as a length; element_order parabolic (default, more "
    "accurate) or linear; curved_elements; gravity on / off (off by default) and "
    "gravity_direction; remove_rigid_body_modes: for a model held by nothing whose loads "
    "balance (off by default); contact_tolerance: bodies closer than this (mm, default 0.1) "
    "are glued; safety_basis yield / ultimate; keep_results: keep the mesh and results in the "
    "design file (on; off keeps only the numbers, the file stays small). " + STUDY_HELP,
    schema(
        {
            "study": _study(),
            "mesh_size": number(
                "average element size, % of the model size", minimum=0.5, maximum=50
            ),
            "mesh_size_mm": number("average element size in mm (0: use mesh_size)", minimum=0),
            "element_order": enum(("parabolic", "linear"), "element order"),
            "curved_elements": boolean("parabolic elements follow curved faces"),
            "gravity": boolean("switch gravity on or off"),
            "gravity_direction": dict(kit.vector3("which way gravity pulls [x, y, z]")),
            "remove_rigid_body_modes": boolean("hold free pieces whose loads balance"),
            "contact_tolerance": number(
                "bodies closer than this are glued (mm)", minimum=0, maximum=10
            ),
            "safety_basis": enum(("yield", "ultimate"), "what the safety factor divides"),
            "keep_results": boolean("keep the mesh and results in the design file"),
        }
    ),
    id_base="StudySettings",
    title_fn=lambda a: "AI: Study settings",
    examples=[
        example({}, "the settings as they are"),
        example({"mesh_size": 5, "gravity": True}, "a finer mesh and gravity on"),
    ],
)

define(
    "precheck_study",
    "Pre-check study",
    "simulate",
    "SIMULATION > SETUP > SOLVE > Pre-check",
    "Check a study before solving it, like Fusion's Pre-check traffic light: ready (green), "
    "caution (yellow: it solves, but read the warnings) or cannot solve (red: what to fix), "
    "with every message as a sentence: missing constraints or loads, materials without the "
    "values a stress study needs, constraints or loads whose faces are gone, bodies that "
    "would fly away, bodies that overlap. " + STUDY_HELP,
    schema({"study": _study()}),
    changes=False,
    examples=[example({}, "is the newest study ready to solve?")],
)

define(
    "solve_study",
    "Solve study",
    "simulate",
    "SIMULATION > SETUP > SOLVE > Solve",
    "Solve a study on this computer (Gmsh meshes it, CalculiX solves it; Fusion solves in "
    "Autodesk's cloud): seconds for a simple part, minutes for a fine mesh; SciForge waits "
    "until it is done (timeout, seconds: then it gives up). Answers the main numbers: the "
    "lowest safety factor and where, the largest von Mises stress and displacement, the mesh "
    "size; study_results has everything. A solve is not an undo step; the last results stay "
    "when it fails. " + STUDY_HELP,
    schema(
        {
            "study": _study(),
            "timeout": positive("give up after this many seconds", default=600, maximum=7200),
        }
    ),
    title_fn=lambda a: "AI: Solve study",
    examples=[example({}, "solve the newest study")],
)

define(
    "study_results",
    "Study results",
    "simulate",
    "SIMULATION > RESULTS (legend, Show Min / Max, Reaction Force, Results Details)",
    "The results of a study's last solve as numbers: the minimum and maximum of every result "
    "(safety factor, von Mises, 1st / 3rd principal and the stress components in MPa, "
    "displacement in mm, strain) with where they are [x, y, z] mm, per body (material, "
    "largest stress and displacement, lowest safety factor), the reaction force at every "
    "constraint (N), the mesh, and the verdict in a sentence (lowest safety factor against "
    'target: "lowest safety factor 1.4 at (x, y, z) on Body1: below 2"; below 1 the part '
    "would bend for good). out_of_date: the design or the study changed since the solve. "
    "results: only these result keys. Without a study and with several studies it lists "
    "them. " + STUDY_HELP,
    schema(
        {
            "study": _study(),
            "target": positive("the safety factor the part should reach", default=2.0),
            "results": array(enum(RESULT_KEYS), "only these results (default: all)", 1),
        }
    ),
    changes=False,
    examples=[
        example({}, "every number of the newest study's results"),
        example({"results": ["safety", "von_mises"], "target": 1.5}, "two results, target 1.5"),
    ],
)

define(
    "delete_study",
    "Delete study",
    "simulate",
    "SIMULATION > browser > study > Delete",
    "Delete a study with its constraints, loads, mesh controls and results (one undo step). "
    + STUDY_HELP,
    schema({"study": string("the study's id or name")}, required=("study",)),
    destructive=True,
    id_base="DeleteStudy",
    title_fn=lambda a: "AI: Delete study",
    examples=[example({"study": "Study 1 - Static Stress"}, "delete that study")],
)

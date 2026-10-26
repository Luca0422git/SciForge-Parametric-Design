# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline, part 1: what a solid without a timeline is made of (an imported STEP body, a
solid made from a mesh), and a plan of SciForge steps that builds it again WITH a timeline. No
Qt. Owner: builder at-recognize (beta 3); the AI tools that use it are rebuild.py and
ai/catalog/rebuild_tools.py (builder at-tools). Spec: docs/sciforge/parity/auto-timeline.md.

Luca (2026-10-26): "Using a connected AI, I want there to be the tool necessary for the AI to
reverse engineer premade models and make them parametric. That means mesh to parametric, or
objects with no timeline to have a timeline ... for non complex parts, i want a nicer option
to make real parametric objects."

The idea: an AI rebuilds a part far faster and more surely when it is handed the part's
features as numbers (the base shape and its profile, the holes and their sizes and places, the
fillet radii, the patterns) and a plan of tool calls in Fusion's order (base shape, cuts and
bosses, holes, patterns, chamfers, fillets last), than when it has to work all of that out from
hundreds of face facts and pictures. It still checks every step against the original
(rebuild.compare) and fixes what the plan got wrong.

CONTRACT (the orchestrator wrote it; at-recognize implements it; never rename or remove):

    describe(shape, options=None) -> dict

`shape`: a Part.Shape (one or more solids, design coordinates). `options` (all optional):
{"detail": "summary" | "full", "max_features": int, "units": "mm"}. Never raises for a shape
it does not understand: what it cannot read goes to "unrecognized" and "notes". The dict:

    {
      "summary": {"volume": mm3, "area": mm2, "bbox": [xmin, ymin, zmin, xmax, ymax, zmax],
                  "size": [dx, dy, dz], "solids": n, "faces": n, "edges": n,
                  "surfaces": {"plane": n, "cylinder": n, ...}},
      "base": {"kind": "extrude" | "revolve" | "box" | "cylinder" | "none", ...the numbers
               that describe it: plane / axis, profile (closed loops of lines and arcs in the
               sketch plane's own x / y), distance or angle...},
      "features": [{"id": "F1", "kind": "hole" | "counterbore" | "countersink" | "pocket" |
                    "boss" | "slot" | "fillet" | "chamfer" | "pattern" | "shell" | ...,
                    ...its numbers (diameter, depth, radius, distance, count, spacing, axis,
                    centre...), "faces": [selectors of the faces it explains]}],
      "plan": [{"step": 1, "tool": "<an AI tool name from sciforge/ai/catalog>",
                "args": {...arguments that pass that tool's schema},
                "why": "a plain sentence", "features": ["F1", ...]}],
      "unrecognized": [{"faces": [selectors], "why": "a plain sentence"}],
      "confidence": 0..1,
      "notes": ["plain sentences"],
    }

Every plan step must pass the catalogue's argument check (sciforge/ai/catalog: the same check
an AI's call goes through), so an AI can send the steps as they are.
"""


class RecognizeError(ValueError):
    """Only for wrong arguments (no shape at all); a shape that is hard to read is never an
    error: describe() says what it could not read."""


def describe(shape, options=None):
    """See the module's CONTRACT. Placeholder until at-recognize lands: the summary only."""
    if shape is None or shape.isNull():
        raise RecognizeError("There is no shape to describe.")
    box = shape.BoundBox
    surfaces = {}
    for face in shape.Faces:
        try:
            kind = face.Surface.TypeId.split("::")[-1].replace("Geom", "").lower()
        except Exception:
            kind = "other"
        surfaces[kind] = surfaces.get(kind, 0) + 1
    return {
        "summary": {
            "volume": shape.Volume,
            "area": shape.Area,
            "bbox": [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax],
            "size": [box.XLength, box.YLength, box.ZLength],
            "solids": len(shape.Solids),
            "faces": len(shape.Faces),
            "edges": len(shape.Edges),
            "surfaces": surfaces,
        },
        "base": {"kind": "none"},
        "features": [],
        "plan": [],
        "unrecognized": [],
        "confidence": 0.0,
        "notes": ["Feature recognition is not built yet."],
    }

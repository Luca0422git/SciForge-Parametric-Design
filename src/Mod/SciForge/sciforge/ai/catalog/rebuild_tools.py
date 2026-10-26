# SPDX-License-Identifier: LGPL-2.1-or-later
"""AI tools for Auto Timeline (beta 3, builder at-tools): rebuild a part that has no timeline
(an imported STEP body, a mesh) as real timeline steps, checked against the original. Beyond
Fusion (its Mesh to BRep gives a body without features). The work is in sciforge/rebuild.py
(the reference, compare, finish) and sciforge/recognize.py (the features and the plan); the
actions in sciforge/ai/actions/rebuild_actions.py. The recipe an AI follows:
docs/ai/recipes/reverse-engineer.md.

    start_rebuild        the part becomes the reference; a new empty body to rebuild it in
    describe_reference   its features and a plan of tool calls in Fusion's order
    compare_to_reference how far the rebuild is: match, missing / extra material, faces,
                         a verdict that says what to do next
    finish_rebuild       the rebuild takes the original's name and place

Pure Python (the MCP server imports it)."""

from . import registry
from .kit import boolean, enum, integer, schema, step_id, string
from .registry import define, example

# The tools' own category and need, entered here so the shared lists stay untouched by beta 3
if "rebuild" not in registry.CATEGORY_KEYS:
    registry.CATEGORIES = registry.CATEGORIES + (("rebuild", "Rebuild with a timeline"),)
    registry.CATEGORY_KEYS = registry.CATEGORY_KEYS + ("rebuild",)
registry.NEEDS.setdefault(
    "reference",
    "No rebuild is going on in this design: call start_rebuild with the body to rebuild "
    "first (an imported STEP body, any solid body or a mesh body).",
)

RIBBON = "Browser: right-click a body > Rebuild with Timeline (AI)... (beyond Fusion)"
REFERENCE_ARG = string(
    "the rebuild's reference (its id, or the original's / the rebuilt body's id); default: "
    "the rebuild of the active body, or the only one in the design"
)


def _title_start(args):
    return "AI: Start rebuild of %s" % args.get("body", "a body")


define(
    "start_rebuild",
    "Start rebuild",
    "rebuild",
    RIBBON,
    "Start rebuilding a part that has no timeline as real, editable timeline steps (Auto "
    "Timeline): an imported STEP body, any solid body, or a mesh body (made into a solid "
    "first; an open or broken mesh, or one of more than 10,000 triangles, is refused). "
    "SciForge freezes the part as the reference "
    "(drawn faint and see-through; never a body or a step, so it stays the target whatever "
    "you build), hides the original and makes a new empty body '<name> (rebuilt)' at its "
    "place, active: build the rebuild there with the normal tools. Then: describe_reference "
    "(the part's features and a plan of tool calls), build the plan step by step, "
    "compare_to_reference after every feature and fix what its verdict says, finish_rebuild "
    "when it says done. The recipe: docs_read recipes/reverse-engineer.md. One undo step. "
    "body: the id of the body (or of a step in it, of the mesh body, or of the component "
    "holding one body: what import_file answers); label: the reference's name (default "
    "'<name> (reference)').",
    schema(
        {
            "body": step_id(
                "the body to rebuild: its id (get_design lists them), or its component's"
            ),
            "label": string("a name for the reference (default '<name> (reference)')"),
        },
        ["body"],
    ),
    needs=("design",),
    title_fn=_title_start,
    examples=[
        example({"body": "Body001"}, "rebuild the imported body Body001 with a timeline"),
        example({"body": "Bracket"}, "a body named by its label"),
    ],
)

define(
    "describe_reference",
    "Describe reference",
    "rebuild",
    RIBBON,
    "What the reference of a rebuild is made of, read by SciForge from its faces: summary "
    "(volume, area, size, counts, the kinds of faces), base (the base shape: an extrude with "
    "its plane, profile and distance, a revolve, a box...), features (holes, counterbores, "
    "pockets, bosses, slots, fillets, chamfers, patterns, each with its numbers and the "
    "faces it explains), plan (tool calls in Fusion's order: base shape, cuts and bosses, "
    "holes, patterns, chamfers, fillets last; each step's args pass the tool's own check, so "
    "send them as they are, adjusting ids the answers give), unrecognized (faces it could "
    "not read, with selectors and why), confidence (0..1) and notes. Coordinates are the "
    "rebuilt body's (the design's for a part at the origin). detail: plan (default: the "
    "features and the plan), summary (the part's numbers only, quick) or full (also every "
    "face of every feature, as selectors).",
    schema(
        {
            "reference": REFERENCE_ARG,
            "detail": enum(
                ("plan", "summary", "full"),
                "plan: features and plan; summary: numbers only; full: also every face",
                default="plan",
            ),
            "max_features": integer("at most this many features", minimum=1, maximum=500),
        }
    ),
    changes=False,
    needs=("design", "reference"),
    examples=[
        example({}, "the features and the plan of the rebuild going on"),
        example({"detail": "full"}, "every face of every feature too"),
        example({"detail": "summary"}, "only the part's size, volume and kinds of faces"),
    ],
)

define(
    "compare_to_reference",
    "Compare to reference",
    "rebuild",
    "Rebuild > Compare with Reference (beyond Fusion)",
    "How far the rebuilt body is from the reference, to call after every feature: match "
    "(common volume / union volume; 1 is identical), volume (reference, rebuilt, common, "
    "missing, extra in mm3), missing (material of the original the rebuild lacks) and extra "
    "(material the rebuild has and the original does not: a hole not cut yet is extra "
    "material shaped like a cylinder), each region with its volume, centre, box, kind, what "
    "it looks like ('a round hole about 6 mm across, 10 deep', 'a rounded edge, radius "
    "about 2', 'a block 10 x 5 x 3') and, when SciForge is sure, fix: the tool call that "
    "makes it (a Single Hole, a fillet of exactly those edges); groups (equal regions "
    "together, with one fix for all of them); faces (how many of the original's faces the "
    "rebuild matches by geometry, and the unmatched ones of each side with a description "
    "and a selector); deviation (how far the surfaces are apart, max and mean, mm); "
    "size_notes; done (match >= 0.999, every face of the original matched and none of the "
    "rebuild left over); and verdict: what to do next, in words. Changes nothing; in the "
    "window it also shows the differences (missing material red, extra green, until the "
    "next compare or finish; show false: not). body: compare another body (default the "
    "rebuilt one). detail full lists every region and face.",
    schema(
        {
            "reference": REFERENCE_ARG,
            "body": step_id("the body to compare (default: the rebuild's own body)"),
            "detail": enum(("summary", "full"), "full: every region and face", default="summary"),
            "show": boolean("show the differences in the window's 3D view", default=True),
        }
    ),
    changes=False,
    needs=("design", "reference"),
    examples=[
        example({}, "how far the rebuild is, and what to do next"),
        example({"detail": "full", "show": False}, "every region and face, no picture"),
    ],
)


def _title_finish(args):
    return "AI: Finish rebuild"


define(
    "finish_rebuild",
    "Finish rebuild",
    "rebuild",
    "Rebuild > Finish Rebuild (beyond Fusion)",
    "Finish a rebuild: the rebuilt body takes the original's name, component and place, "
    "with its timeline; the original (the featureless body or the mesh body) is deleted, or "
    "kept hidden as '<name> (original)' with keep_original: true; the reference is removed "
    "(keep_reference: true keeps it, hidden). Whatever used the original (joints, grounds, a "
    "pattern of it, sketches on its faces...) moves onto the rebuild, face for face; what "
    "cannot move keeps the original (kept hidden; the answer says so). It first compares and "
    "refuses a rebuild that is not done yet (the answer says what is left); "
    "even_if_different: true finishes it as it is (a person happy with a close rebuild of a "
    "mesh). One undo step.",
    schema(
        {
            "reference": REFERENCE_ARG,
            "keep_original": boolean(
                "keep the original body, hidden and renamed '<name> (original)'", default=False
            ),
            "keep_reference": boolean("keep the reference, hidden", default=False),
            "even_if_different": boolean(
                "finish even though compare_to_reference does not say done", default=False
            ),
        }
    ),
    needs=("design", "reference"),
    destructive=True,
    title_fn=_title_finish,
    examples=[
        example({}, "the rebuild becomes the part, the original is deleted"),
        example({"keep_original": True}, "keep the original, hidden"),
    ],
)

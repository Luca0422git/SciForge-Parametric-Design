# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline, part 2: the reference a rebuild is checked against, and the comparison. No Qt
(rebuild_ui.py has the commands: a body's right-click "Rebuild with Timeline (AI)..."). Owner:
builder at-tools (beta 3); the feature reading is recognize.py (builder at-recognize). Spec:
docs/sciforge/parity/auto-timeline.md.

How a rebuild goes (an AI does it through the tools in ai/catalog/rebuild_tools.py; a person can
do it by hand too):

1. start: the part to rebuild (a body without a timeline: an imported STEP body; a mesh body,
   turned into a solid first) becomes the **reference**: its solid is frozen in a hidden object
   (SciForgeType "RebuildReference") shown faint and see-through, never a body, never a step, so
   whatever happens to the original, the target stays. The rebuild happens in a new body.
2. describe: recognize.describe() of the reference: features and a plan of tool calls.
3. build: the AI calls the normal tools (create_sketch, extrude, hole, pattern, fillet...); each
   is a timeline step, editable afterwards, like steps made by hand.
4. compare (after every few steps): how far the new body is from the reference, in numbers and
   in words (what material is missing, what is extra, which faces are not matched yet).
5. finish: when the match is good (the AI decides with the numbers; a person with the picture),
   the reference is removed (or kept hidden), the new body takes the original's name and place.

CONTRACT (the orchestrator wrote it; at-tools implements it; never rename or remove):

    start(doc, source, label=None) -> reference object
    references(doc) -> [reference objects]
    reference_shape(ref) -> Part.Shape (the frozen solid, design coordinates)
    compare(ref, target, options=None) -> dict
        target: a body (its solid now) or a Part.Shape. The dict:
        {"match": 0..1 (common volume / union volume),
         "volume": {"reference", "rebuilt", "common", "missing", "extra"} (mm3),
         "missing": [{"volume", "center", "bbox", "looks_like"}],  material the rebuild lacks
         "extra": [{...}],                                         material it has too much
         "faces": {"reference": n, "matched": n,
                   "unmatched_reference": [{"kind", "describe", "selector"}],
                   "unmatched_rebuilt": [{...}]},
         "deviation": {"max": mm, "mean": mm},
         "done": bool,           (match >= 0.999 and every reference face matched)
         "verdict": "a plain sentence: what to do next"}
    finish(ref, target, keep_reference=False) -> the finished body
"""


class RebuildError(ValueError):
    """Something the person or the AI has to change; the message is a plain sentence."""


REFERENCE = "RebuildReference"


def references(doc):
    if doc is None:
        return []
    return sorted(
        (o for o in doc.Objects if getattr(o, "SciForgeType", "") == REFERENCE), key=lambda o: o.ID
    )


def start(doc, source, label=None):
    raise RebuildError("Auto Timeline is not built yet.")


def reference_shape(ref):
    raise RebuildError("Auto Timeline is not built yet.")


def compare(ref, target, options=None):
    raise RebuildError("Auto Timeline is not built yet.")


def finish(ref, target, keep_reference=False):
    raise RebuildError("Auto Timeline is not built yet.")

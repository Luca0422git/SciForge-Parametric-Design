# SPDX-License-Identifier: LGPL-2.1-or-later
"""The actions of the rebuild AI tools (beta 3, builder at-tools; catalog/rebuild_tools.py
says what each answers): start_rebuild, describe_reference, compare_to_reference,
finish_rebuild. They call sciforge/rebuild.py (the reference, compare, finish) and
sciforge/recognize.py (describe), the same code as the window's Rebuild commands
(rebuild_ui.py). start and finish are one undo step each; describe and compare change
nothing."""

from ..executor import UserError, json_result
from . import action


def _rebuild():
    from ... import rebuild

    return rebuild


def reference(ctx, args):
    """The reference a call is about: the one named (its id or label, or the original's /
    the rebuilt body's id), else the rebuild of the active body, else the only one."""
    rebuild = _rebuild()
    doc = ctx.need_doc()
    ident = args.get("reference")
    if ident:
        obj = ctx.resolve(ident, "rebuild reference or body")
        if rebuild.is_reference(obj):
            return obj
        from ... import bodies

        body = obj if bodies.is_body(obj) else (bodies.body_of(obj) or obj)
        ref = rebuild.reference_for(body)
        if ref is None:
            raise UserError(
                "%r is not a rebuild reference, and no rebuild was started from it or into "
                "it (start_rebuild makes one)." % ident
            )
        return ref
    try:
        ref = rebuild.find(doc, ctx.host.find_body(doc))
    except rebuild.RebuildError as exc:
        raise UserError(str(exc))
    if ref is None:
        raise UserError(
            "This design has no rebuild going on: call start_rebuild with the body to rebuild "
            "first."
        )
    return ref


def _size(shape):
    box = shape.BoundBox
    return "%s x %s x %s mm" % tuple(_num(v) for v in (box.XLength, box.YLength, box.ZLength))


def _num(value):
    from ... import rebuild_core

    return rebuild_core.num(value, 3)


@action("start_rebuild")
def start_rebuild(ctx, args):
    rebuild = _rebuild()
    doc = ctx.need_doc()
    source = ctx.resolve(args["body"], "body or mesh body")

    def work():
        return rebuild.start(doc, source, args.get("label"))

    try:
        ref = ctx.change(work)
    except rebuild.RebuildError as exc:
        raise UserError(str(exc))
    target = rebuild.target_of(ref)
    if target is not None:
        ctx.host.set_active_body(target)
    shape = rebuild.reference_shape(ref)
    note = rebuild.NOTES.get(ref.Name) or ""
    text = (
        "Done: %s. %s is the reference now (id %r: frozen, drawn faint; %d faces, %s mm3, %s%s). "
        "The new empty body %r is active: build the rebuild there. Its id is %r. Next: "
        "describe_reference (the part's features and a plan of tool calls), build the plan "
        "step by step, compare_to_reference after every feature, finish_rebuild when it says "
        "done."
        % (
            ctx.title,
            ref.SourceLabel,
            ref.Name,
            len(shape.Faces),
            _num(sum(s.Volume for s in shape.Solids)),
            _size(shape),
            ("; " + note) if note else "",
            target.Label if target is not None else "?",
            target.Name if target is not None else "?",
        )
    )
    return ctx.done(text, doc)


@action("describe_reference")
def describe_reference(ctx, args):
    from ... import recognize

    rebuild = _rebuild()
    ref = reference(ctx, args)
    detail = args.get("detail", "plan")
    doc = ctx.need_doc()
    options = {"detail": "summary" if detail == "summary" else "full"}
    if args.get("max_features"):
        options["max_features"] = args["max_features"]
    if getattr(ref, "SourceKind", "") == "mesh":
        options["source"] = "mesh"
    # the plan's ids are the ones SciForge will give (Sketch1 when no Sketch1 is taken yet)
    options["taken_ids"] = sorted({o.Name for o in doc.Objects} | {o.Label for o in doc.Objects})
    try:
        data = rebuild.describe(ref, options)
    except (rebuild.RebuildError, recognize.RecognizeError) as exc:
        raise UserError(str(exc))
    if detail == "plan":
        data = _without_face_lists(data)
    target = rebuild.target_of(ref)
    head = {
        "reference": ref.Name,
        "original": ref.SourceLabel,
        "original_kind": ref.SourceKind,
        "rebuilt": target.Name if target is not None else None,
        "coordinates": (
            "design"
            if rebuild.frame(ref).isIdentity()
            else "the rebuilt body's own (where its sketches and selectors work)"
        ),
    }
    head.update(data)
    head.pop("timing", None)  # (in the log: an answer is the same every time it is asked)
    head.pop("timing_detail", None)
    plan = data.get("plan") or []
    words = "%s, read from its %d faces: %d feature%s, a plan of %d step%s" % (
        ref.SourceLabel,
        (data.get("summary") or {}).get("faces", 0),
        len(data.get("features") or []),
        "" if len(data.get("features") or []) == 1 else "s",
        len(plan),
        "" if len(plan) == 1 else "s",
    )
    if data.get("unrecognized"):
        words += "; %d group%s of faces not read (see unrecognized)" % (
            len(data["unrecognized"]),
            "" if len(data["unrecognized"]) == 1 else "s",
        )
    words += (
        ". Build the plan in the active body %r, compare_to_reference after each "
        "feature." % (target.Label if target is not None else "?")
    )
    return json_result(head, text=words, compact=True)


def _without_face_lists(data):
    """The answer without each feature's list of face selectors (detail full has them): the
    count stays, the plan is whole."""
    out = dict(data)
    features = []
    for feature in data.get("features") or []:
        row = dict(feature)
        faces = row.pop("faces", None)
        if isinstance(faces, list):
            row["face_count"] = len(faces)
        features.append(row)
    out["features"] = features
    return out


LIMITS = {"summary": (6, 8), "full": (100, 200)}


@action("compare_to_reference")
def compare_to_reference(ctx, args):
    rebuild = _rebuild()
    ref = reference(ctx, args)
    target = ctx.body_of(args["body"]) if args.get("body") else None
    regions, faces = LIMITS[args.get("detail", "summary")]
    options = {"regions": regions, "faces": faces, "show": bool(args.get("show", True))}
    try:
        data = rebuild.compare(ref, target, options)
    except rebuild.RebuildError as exc:
        raise UserError(str(exc))
    data.pop("seconds", None)  # (in the log: an answer is the same every time it is asked)
    return json_result(data, text=data["verdict"], compact=True)


@action("finish_rebuild")
def finish_rebuild(ctx, args):
    from ... import timeline_ops

    rebuild = _rebuild()
    doc = ctx.need_doc()
    ref = reference(ctx, args)
    if not args.get("even_if_different"):
        try:
            data = rebuild.compare(
                ref, None, {"selectors": False, "deviation": False, "show": False}
            )
        except rebuild.RebuildError as exc:
            raise UserError(str(exc))
        if not data["done"]:
            raise UserError(
                "Not finished: the rebuild does not match the original yet. %s Or give "
                "even_if_different: true to finish it as it is." % data["verdict"]
            )
    original = ref.SourceLabel

    def work():
        return rebuild.finish(
            ref,
            None,
            keep_reference=bool(args.get("keep_reference")),
            keep_original=bool(args.get("keep_original")),
        )

    try:
        body = ctx.change(work)
    except rebuild.RebuildError as exc:
        raise UserError(str(exc))
    ctx.host.set_active_body(body)
    try:
        steps = [i for i in timeline_ops.timeline(doc).items if i.body == body.Name]
    except Exception:
        steps = []
    text = (
        "Done: %s. %s is now the rebuilt part (id %r) with %d timeline steps; the original "
        % (
            ctx.title,
            body.Label,
            body.Name,
            len(steps),
        )
        + (
            "is kept hidden as %r" % ("%s (original)" % original)
            if args.get("keep_original")
            else "was deleted"
        )
        + (
            ", the reference kept hidden."
            if args.get("keep_reference")
            else ", the reference removed."
        )
    )
    return ctx.done(text, doc)

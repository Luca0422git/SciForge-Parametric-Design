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

Added by at-tools (the contract's names unchanged): finish's keyword keep_original (the
original body is kept, hidden and renamed "<name> (original)", instead of deleted); compare
accepts target None (the reference's own rebuilt body) and also answers "kind" and the
feature's numbers for each region, "fix" (a tool call that would make it, when one is
certain), "groups" (equal regions together), "size_notes", "frame", "method" and "seconds";
`done` also needs no face of the rebuild left over (an extra hole of 1 mm hides inside the
0.1 % volume tolerance, so the faces decide). describe(ref) is recognize.describe() of the
reference in the frame the tools build in.

Where things are: the reference (an App::FeaturePython, never a Part::Feature, so no geometry
code takes it for a part) keeps the frozen solid in FrozenShape (design coordinates), the
original's name, label and kind, and the rebuilt body's name. Comparisons and descriptions
are made in the rebuilt body's own coordinates (its frame: what create_sketch's planes and the
selectors use); for a body at the design's origin, as made by Insert STEP, they are the
design's coordinates. Needs FreeCAD.
"""

import math
import time

import FreeCAD as App

from . import bodies, log, warn
from . import rebuild_core as core


class RebuildError(ValueError):
    """Something the person or the AI has to change; the message is a plain sentence."""


REFERENCE = "RebuildReference"
SHAPE = "FrozenShape"
LISTENERS = []  # fn(event, ref, data): the window's red / green overlay (rebuild_ui)
_HIDDEN = {}  # document name -> {reference name: original's name}: hidden while it is rebuilt


def references(doc):
    if doc is None:
        return []
    return sorted(
        (o for o in doc.Objects if getattr(o, "SciForgeType", "") == REFERENCE), key=lambda o: o.ID
    )


# -- the reference object -------------------------------------------------------------------------
class ReferenceFeature:
    """Saved in files as "sciforge.rebuild.ReferenceFeature": keep the name and properties."""

    def __init__(self, obj):
        obj.Proxy = self
        self.ensure(obj)

    @staticmethod
    def ensure(obj):
        import Part  # noqa: F401  (Part::PropertyPartShape)

        add = bodies.add_prop
        add(obj, "Part::PropertyPartShape", SHAPE, "Rebuild", "The original's solid, frozen")
        add(obj, "App::PropertyString", "SourceName", "Rebuild", "The original body or mesh")
        add(obj, "App::PropertyString", "SourceLabel", "Rebuild", "The original's name")
        add(obj, "App::PropertyString", "SourceKind", "Rebuild", "body or mesh")
        add(obj, "App::PropertyString", "TargetName", "Rebuild", "The body the rebuild is in")
        add(obj, "App::PropertyFloat", "Tolerance", "Rebuild", "Faces agree within this (mm)")
        if add(obj, "App::PropertyBool", "Shown", "Rebuild", "Drawn faint in the 3D view"):
            obj.Shown = True
        bodies.mark(obj, REFERENCE)
        bodies.hide_from_timeline(obj)

    def onDocumentRestored(self, obj):
        self.ensure(obj)
        try:
            if getattr(obj, "Shown", True):
                _resume_later(obj.Document.Name)
        except Exception as exc:
            warn("rebuild: %s" % exc)

    def execute(self, obj):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def is_reference(obj):
    try:
        return obj is not None and getattr(obj, "SciForgeType", "") == REFERENCE
    except Exception:
        return False


def reference_shape(ref):
    """The frozen solid, in design coordinates (a copy)."""
    if not is_reference(ref) or not bodies.alive(ref):
        raise RebuildError("That is not a rebuild reference (start_rebuild makes one).")
    shape = getattr(ref, SHAPE, None)
    if shape is None or shape.isNull() or not shape.Solids:
        raise RebuildError("The reference %s holds no solid." % ref.Label)
    return shape.copy()


def source_of(ref):
    """The original body or mesh, while it is in the design."""
    name = getattr(ref, "SourceName", "") or ""
    found = ref.Document.getObject(name) if name else None
    return found if bodies.alive(found) else None


def target_of(ref):
    """The body the rebuild is made in, while it is in the design."""
    name = getattr(ref, "TargetName", "") or ""
    found = ref.Document.getObject(name) if name else None
    return found if bodies.alive(found) and bodies.is_body(found) else None


def reference_for(obj):
    """The reference made from `obj` or rebuilt into it (a body or mesh), or None: a rebuild
    going on first, else one finished and kept (hidden)."""
    if obj is None:
        return None
    found = [
        ref
        for ref in references(obj.Document)
        if obj.Name in (getattr(ref, "SourceName", ""), getattr(ref, "TargetName", ""))
    ]
    going = [ref for ref in found if getattr(ref, "Shown", True)]
    return (going or found or [None])[0]


def active_references(doc):
    """The references still being worked on (drawn; Finish with keep keeps one hidden)."""
    return [r for r in references(doc) if getattr(r, "Shown", True)]


def working_body(doc):
    """The body the rebuild going on is made in, when there is exactly one (a design opened
    again carries on there: QA found the next steps going into another body), else None."""
    try:
        live = [r for r in active_references(doc) if target_of(r) is not None]
    except Exception:
        return None
    return target_of(live[0]) if len(live) == 1 else None


def _resume_later(name, tries=0):
    """In the window: once a design with a rebuild going on is open, its rebuilt body is the
    active one again (FreeCAD keeps no active body in the file, and SciForge would pick the
    design's oldest body: the AI's or the person's next steps went there)."""
    if not App.GuiUp:
        return
    from .compat import QtCore

    def run():
        try:
            doc = App.listDocuments().get(name)
            if doc is None:
                return
            if getattr(doc, "Restoring", False) or getattr(doc, "Recomputing", False):
                if tries < 50:
                    _resume_later(name, tries + 1)
                return
            import FreeCADGui as Gui

            gdoc = Gui.getDocument(name)
            if gdoc is None or gdoc.ActiveView is None:
                if tries < 50:
                    _resume_later(name, tries + 1)
                return
            body = working_body(doc)
            if body is None or bodies.active_body(doc) is not None:
                return
            from . import components

            components.activate_body(body)
            log("rebuild: %s is the active body again (a rebuild goes on there)" % body.Label)
        except Exception as exc:
            warn("rebuild: %s" % exc)

    QtCore.QTimer.singleShot(0 if tries == 0 else 100, run)


def find(doc, body=None):
    """The reference to work with: the one rebuilt into `body` (the active body), else the
    only one being worked on. None when there is none; RebuildError when it is not clear."""
    if body is not None:
        ref = reference_for(body)
        if ref is not None:
            return ref
    live = active_references(doc)
    if len(live) == 1:
        return live[0]
    if not live:
        kept = references(doc)
        return kept[0] if len(kept) == 1 else None
    names = ", ".join("%s (rebuilt into %s)" % (r.Name, r.TargetName) for r in live)
    raise RebuildError(
        "This design has %d rebuilds going on (%s): say which reference, or make its rebuilt "
        "body the active one." % (len(live), names)
    )


# -- start ----------------------------------------------------------------------------------------
def _original(source):
    """(kind, object): a body ("body"; a step in it counts as its body) or a mesh body."""
    from . import insert

    if insert.is_mesh_body(source):
        return "mesh", source
    body = source if bodies.is_body(source) else bodies.body_of(source)
    if body is not None:
        return "body", body
    raise RebuildError(
        "%s is not a body or a mesh body: pick the body to rebuild (an imported STEP body, "
        "any solid body, or a mesh body)." % getattr(source, "Label", source)
    )


def _solid_of(kind, source):
    """The original's solid in design coordinates, and a note (or "")."""
    import Part

    from . import insert

    note = ""
    if kind == "mesh":
        mesh = insert.kernel_copy(source)
        broken = _mesh_problem(mesh)
        if broken:
            raise RebuildError(
                "%s cannot be rebuilt: %s, so it does not close into a solid. Repair the mesh "
                "first (MESH tab > Repair), then try again." % (source.Label, broken)
            )
        try:
            solid = insert.solid_from_mesh(mesh, "Prismatic")
        except insert.InsertError as exc:
            raise RebuildError("%s cannot be rebuilt: %s" % (source.Label, exc))
        if not _same_size(solid, mesh):
            raise RebuildError(
                "%s cannot be rebuilt: its triangles do not close into a solid of the mesh's "
                "size (a mesh that is not watertight). Repair the mesh first (MESH tab > "
                "Repair), then try again." % source.Label
            )
        try:
            place = source.getGlobalPlacement()
        except Exception:
            place = source.Placement
        if not place.isIdentity():
            solid = bodies.baked(solid)
            solid.transformShape(place.toMatrix(), True)
        note = "made from the mesh's %d triangles (flat facets)" % source.Mesh.CountFacets
    else:
        if not bodies.has_solid(source):
            raise RebuildError(
                "%s has no solid to rebuild (an empty body or a surface body): Auto Timeline "
                "rebuilds solids." % source.Label
            )
        shape = bodies.global_shape(source)
        solids = list(shape.Solids)
        solid = solids[0] if len(solids) == 1 else Part.makeCompound(solids)
    if not solid.isValid():
        fixed = solid.copy()
        try:
            fixed.fix(1e-7, 1e-7, 1e-4)
        except Exception:
            pass
        if fixed.isValid():
            solid = fixed
        else:
            note = (note + "; " if note else "") + (
                "OpenCASCADE finds flaws in this solid, so comparisons may be less exact"
            )
    return solid, note


def _mesh_problem(mesh):
    """Why a mesh cannot become a solid, in words ("" when it can)."""
    try:
        if mesh.CountFacets == 0:
            return "the mesh has no triangles"
        if not mesh.isSolid():
            return "the mesh is not watertight (it has holes or loose edges)"
        if mesh.hasNonManifolds():
            return "the mesh has edges shared by more than two triangles"
    except Exception:
        return ""
    return ""


def _same_size(solid, mesh):
    """The solid made from a mesh has the mesh's box and (about) its volume."""
    try:
        a, b = solid.BoundBox, mesh.BoundBox
        tol = max(1e-3, 1e-4 * b.DiagonalLength)
        for x, y in (
            (a.XMin, b.XMin),
            (a.YMin, b.YMin),
            (a.ZMin, b.ZMin),
            (a.XMax, b.XMax),
            (a.YMax, b.YMax),
            (a.ZMax, b.ZMax),
        ):
            if abs(x - y) > tol:
                return False
        volume = abs(float(mesh.Volume))
        return volume <= 0 or abs(solid.Volume - volume) <= 0.01 * volume
    except Exception:
        return True


def start(doc, source, label=None):
    """Make `source` (a body, a step in one, or a mesh body) the reference of a rebuild and a
    new empty body "<name> (rebuilt)" to rebuild it in, at the original's place and active.
    The original is hidden. Inside the caller's undo step. Returns the reference."""
    from . import components

    if doc is None:
        raise RebuildError("No design is open.")
    if source is None or not bodies.alive(source):
        raise RebuildError("Pick the body to rebuild.")
    if is_reference(source):
        raise RebuildError("%s is a rebuild reference itself; pick a body." % source.Label)
    kind, source = _original(source)
    ref = reference_for(source)
    if ref is not None and not getattr(ref, "Shown", True):
        ref = None  # a finished rebuild whose reference was kept: this is a new one
    if ref is not None:
        if getattr(ref, "TargetName", "") == source.Name:
            raise RebuildError(
                "%s is the rebuild of %s: rebuild the original, or finish this rebuild first."
                % (source.Label, ref.SourceLabel)
            )
        if target_of(ref) is not None:
            raise RebuildError(
                "%s is already being rebuilt in %s (reference %s): carry on there, or "
                "finish_rebuild first." % (source.Label, target_of(ref).Label, ref.Name)
            )
    solid, note = _solid_of(kind, source)
    container = components.container_of(source)
    if ref is None:
        ref = doc.addObject("App::FeaturePython", REFERENCE)
        ReferenceFeature(ref)
        ref.Label = label or "%s (reference)" % source.Label
        setattr(ref, SHAPE, solid)
        ref.SourceName = source.Name
        ref.SourceLabel = source.Label
        ref.SourceKind = kind
        size = solid.BoundBox.DiagonalLength
        ref.Tolerance = core.mesh_tolerance(size) if kind == "mesh" else core.FACE_TOL
    target = components.new_body_in(doc, container, "%s (rebuilt)" % source.Label)
    if kind == "body":
        try:
            target.Placement = source.Placement
        except Exception:
            pass
    ref.TargetName = target.Name
    ref.Shown = True
    _attach_view(ref)
    bodies.set_shown(source, False)
    _HIDDEN.setdefault(doc.Name, {})[ref.Name] = source.Name
    try:
        components.activate_body(target)
    except Exception:
        bodies.set_active_body(target)
    NOTES[ref.Name] = note
    log(
        "rebuild: %s frozen as %s, rebuilt in %s%s"
        % (source.Label, ref.Name, target.Label, (" (%s)" % note) if note else "")
    )
    return ref


NOTES = {}  # reference name -> what start had to say about the original (not saved)


def _attach_view(ref):
    """The faint see-through picture of the reference (the window only; rebuild_ui)."""
    if not App.GuiUp:
        return
    try:
        from . import rebuild_ui

        rebuild_ui.attach_view(ref)
    except Exception as exc:
        warn("rebuild: the reference is not drawn (%s)" % exc)


# -- the frame -----------------------------------------------------------------------------------
def frame(ref=None, body=None):
    """The placement of the coordinates rebuilds are described in: the rebuilt body's (what
    its sketches' planes and the selectors work in); identity for a body at the origin."""
    if body is None and ref is not None:
        body = target_of(ref)
    if body is None:
        return App.Placement()
    try:
        return body.getGlobalPlacement()
    except Exception:
        return App.Placement()


def in_frame(shape, place):
    """A shape in design coordinates moved into a frame (a copy when it has to move)."""
    if place is None or place.isIdentity():
        return shape
    out = bodies.baked(shape)
    out.transformShape(place.inverse().toMatrix(), True)
    return out


def out_of_frame(shape, place):
    if place is None or place.isIdentity():
        return shape
    out = bodies.baked(shape)
    out.transformShape(place.toMatrix(), True)
    return out


def describe(ref, options=None):
    """recognize.describe() of the reference, in the rebuilt body's frame (the numbers an AI
    passes to the tools). A reference made from a mesh is read from the mesh's triangles
    while the mesh body is there (recognize_mesh fits its round regions)."""
    from . import recognize

    options = dict(options or {})
    place = frame(ref)
    if getattr(ref, "SourceKind", "") == "mesh":
        source = source_of(ref)
        if source is not None:
            try:
                from . import insert, recognize_mesh
            except ImportError:
                recognize_mesh = None
            if recognize_mesh is not None and hasattr(recognize_mesh, "describe_mesh"):
                mesh = insert.kernel_copy(source)
                try:
                    whole = place.inverse().multiply(source.getGlobalPlacement())
                except Exception:
                    whole = place.inverse().multiply(source.Placement)
                if not whole.isIdentity():
                    mesh.transform(whole.toMatrix())
                return recognize_mesh.describe_mesh(mesh, options)
        options.setdefault("source", "mesh")
    shape = in_frame(reference_shape(ref), place)
    return recognize.describe(shape, options)


# -- compare ---------------------------------------------------------------------------------------
DEFAULTS = {
    "regions": 12,  # regions listed per side (the biggest first; groups count them all)
    "faces": 20,  # unmatched faces listed per side
    "deviation": True,
    "selectors": True,
    "tolerance": None,  # mm (default: the reference's)
    "show": True,  # the window shows the differences (missing red, extra green)
}


def _target_shape(target):
    """(body or None, its solids in design coordinates or None)."""
    import Part

    if isinstance(target, Part.Shape):
        return None, target if not target.isNull() and target.Solids else None
    body = target if bodies.is_body(target) else bodies.body_of(target)
    if body is None:
        raise RebuildError("Compare with a body (the rebuilt one).")
    if not bodies.has_solid(body):
        return body, None
    shape = bodies.global_shape(body)
    solids = list(shape.Solids)
    return body, solids[0] if len(solids) == 1 else Part.makeCompound(solids)


def compare(ref, target=None, options=None):
    """How far `target` (the rebuilt body; None: the reference's own) is from the reference:
    the contract's dict (module docstring). Never changes the design."""
    began = time.perf_counter()
    opts = dict(DEFAULTS)
    opts.update(options or {})
    if target is None:
        target = target_of(ref)
        if target is None:
            raise RebuildError(
                "The rebuilt body of %s is gone (deleted?): undo that, or call start_rebuild "
                "on %s again for a new one." % (ref.Label, ref.SourceLabel or "the original")
            )
    body, rebuilt = _target_shape(target)
    place = frame(body=body) if body is not None else App.Placement()
    known = _reference_facts(ref, place)  # (measured once for all the compares of a rebuild)
    reference = known["shape"]
    tol = float(opts["tolerance"] or getattr(ref, "Tolerance", 0.0) or core.FACE_TOL)
    mesh = getattr(ref, "SourceKind", "") == "mesh"
    v_ref = known["volume"]
    result = {
        "reference": ref.Name,
        "rebuilt": body.Name if body is not None else None,
        "frame": "design" if place.isIdentity() else "the rebuilt body's own coordinates",
        "tolerance": tol,
    }
    if rebuilt is None:
        result.update(
            match=0.0,
            volume={
                "reference": round(v_ref, 6),
                "rebuilt": 0.0,
                "common": 0.0,
                "missing": round(v_ref, 6),
                "extra": 0.0,
            },
            missing=[],
            extra=[],
            faces={
                "reference": len(known["rows"]),
                "matched": 0,
                "unmatched_reference": [],
                "unmatched_rebuilt": [],
            },
            deviation={"max": None, "mean": None},
            done=False,
            empty=True,
            method="none",
        )
        result["verdict"] = core.verdict(result)
        result["seconds"] = round(time.perf_counter() - began, 3)
        if opts.get("show", True):
            _notify("clear", ref, None)
        return result
    rebuilt = in_frame(rebuilt, place)
    v_new = _volume(rebuilt)
    rows = (known["rows"], _face_rows(rebuilt))
    opts["_edges"] = None  # (the rebuild's edges, measured once for the fillet calls)
    opts["_flat"] = None  # (its flat faces, for the hole calls)
    opts["_fixes"] = {"missing": 0, "extra": 0}
    opts["_index"] = dict(known["index"])  # (selector indexes, built once: _refs)
    faces = _match_faces(reference, rebuilt, tol, mesh, opts, rows)
    if not mesh and _same_solid(faces, v_ref, v_new):
        # every face of each part lies on a face of the other and the volumes agree: the same
        # solid, no boolean needed
        v_common, v_missing, v_extra, missing, extra = min(v_ref, v_new), 0.0, 0.0, [], []
        method = "faces"
    else:
        # (a copy: an OpenCASCADE boolean may touch its arguments' tolerances)
        v_common, v_missing, v_extra, missing, extra, method = _pieces(
            reference.copy(), rebuilt, rows, (v_ref, v_new)
        )
    union = v_ref + v_new - v_common
    match = max(0.0, min(1.0, v_common / union)) if union > 1e-12 else 0.0
    missing = sorted(missing, key=lambda pair: -pair[1])  # ([(solid, volume)], biggest first)
    extra = sorted(extra, key=lambda pair: -pair[1])
    regions_missing = [_region(s, "missing", rebuilt, tol, opts, v) for s, v in missing]
    regions_extra = [_region(s, "extra", rebuilt, tol, opts, v) for s, v in extra]
    regions_missing = [r for r in regions_missing if r is not None]
    regions_extra = [r for r in regions_extra if r is not None]
    deviation = _deviation(faces["_rows"]) if opts["deviation"] else {"max": None, "mean": None}
    groups = core.group_regions(regions_missing + regions_extra, reference_volume=v_ref)
    done = (
        match >= core.MATCH_DONE
        and faces["matched"] == faces["reference"]
        and faces["rebuilt_matched"] == faces["rebuilt"]
    )
    limit = int(opts["regions"])
    result.update(
        match=round(match, 6),
        volume={
            "reference": round(v_ref, 6),
            "rebuilt": round(v_new, 6),
            "common": round(v_common, 6),
            "missing": round(v_missing, 6),
            "extra": round(v_extra, 6),
        },
        missing=[_public(r) for r in sorted(regions_missing, key=lambda r: -r["volume"])][:limit],
        extra=[_public(r) for r in sorted(regions_extra, key=lambda r: -r["volume"])][:limit],
        regions={"missing": len(regions_missing), "extra": len(regions_extra)},
        faces={k: v for k, v in faces.items() if not k.startswith("_")},
        deviation=deviation,
        done=bool(done),
        method=method,
        size_notes=core.size_notes(_bbox(reference), _bbox(rebuilt), max(tol, 1e-6)),
    )
    result["groups"] = [_group_public(g) for g in groups]
    for i, (group, public) in enumerate(zip(groups, result["groups"])):
        if public.get("fix"):
            group["fix_at"] = i
    result["verdict"] = core.verdict(dict(result, groups=groups))
    result["seconds"] = round(time.perf_counter() - began, 3)
    if method == "sampled":
        result["note"] = (
            "OpenCASCADE could not split these two solids by each other, so the volumes were "
            "measured along 4096 rays through them (about 1 % exact) and the regions are not "
            "listed."
        )
        result["verdict"] = "(Volumes sampled, about 1 % exact: see note.) " + result["verdict"]
    if opts.get("show", True):
        _notify(
            "compare",
            ref,
            {
                "missing": [out_of_frame(s, place) for s, _v in missing],
                "extra": [out_of_frame(s, place) for s, _v in extra],
                "done": result["done"],
            },
        )
    _keep_index(known, opts)
    log(
        "rebuild: compare %s with %s: match %.6f, %d/%d faces, %.2f s"
        % (
            ref.Name,
            result["rebuilt"],
            match,
            faces["matched"],
            faces["reference"],
            result["seconds"],
        )
    )
    return result


_KNOWN = {}  # (document, reference) -> the reference as compare measured it (_reference_facts)


def _reference_facts(ref, place):
    """The reference in the frame, its volume, its face rows and selector indexes: measured
    once for all the compares of a rebuild (the reference never changes; a 300-face one takes
    a third of a second to measure). Measured again when its shape or the frame changes."""
    frozen = getattr(ref, SHAPE, None)
    try:
        box = frozen.BoundBox
        stamp = (
            frozen.hashCode(),
            len(frozen.Faces),
            tuple(round(v, 6) for v in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax)),
            round(box.ZMax, 6),
            tuple(round(v, 9) for v in place.toMatrix().A),
        )
    except Exception:
        stamp = None
    key = (ref.Document.Name, ref.Name)
    known = _KNOWN.get(key)
    if known is not None and stamp is not None and known["stamp"] == stamp:
        for row in known["rows"]:
            row.matched = False
        return known
    shape = in_frame(reference_shape(ref), place)
    known = {
        "stamp": stamp,
        "shape": shape,
        "volume": _volume(shape),
        "rows": _face_rows(shape),
        "index": {},
    }
    if stamp is not None:
        if len(_KNOWN) >= 8:
            _KNOWN.clear()
        _KNOWN[key] = known
    return known


def _keep_index(known, opts):
    """Keep the reference's selector indexes a compare built, for the next compare."""
    mine = id(known["shape"])
    for key, value in (opts.get("_index") or {}).items():
        if key[0] == mine:
            known["index"][key] = value


def forget(doc=None):
    """Drop what compare kept of the references (of one document, or all)."""
    for key in list(_KNOWN):
        if doc is None or key[0] == getattr(doc, "Name", doc):
            _KNOWN.pop(key, None)


def _volume(shape):
    try:
        return sum(s.Volume for s in shape.Solids)
    except Exception:
        return 0.0


def _bbox(shape):
    box = shape.BoundBox
    return [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]


def _same_solid(faces, v_ref, v_new):
    """Every face of each part lies on a face of the other (within the tolerance) and the
    volumes agree: the same solid."""
    return (
        faces["reference"] > 0
        and faces["matched"] == faces["reference"]
        and faces["rebuilt_matched"] == faces["rebuilt"]
        and abs(v_ref - v_new) <= 1e-6 * max(1.0, v_ref, v_new)
    )


def _pieces(a, b, rows=None, volumes=None):
    """(common volume, missing volume, extra volume, [(missing solid, its volume)], [(extra
    solid, its volume)], method): a split of both solids by each other (OpenCASCADE's General
    Fuse), each piece put where it lies: read from its faces (a face of a piece lies on a face
    of A or B; facing the same way, the piece is inside that solid), else from a point inside
    it. Checked: the pieces must add up to both volumes; else again with a fuzzy tolerance;
    else the volumes are sampled (no regions; method "sampled"). Each volume is measured once
    (a 300-face piece takes OpenCASCADE tens of milliseconds)."""
    v_a, v_b = volumes if volumes is not None else (_volume(a), _volume(b))
    scale = max(1.0, v_a, v_b)
    rows_a, rows_b = rows if rows is not None else (_face_rows(a), _face_rows(b))
    on = 1e-6 * max(1.0, a.BoundBox.DiagonalLength)
    for fuzzy in (0.0, 1e-5 * max(1.0, a.BoundBox.DiagonalLength)):
        try:
            result, _map = a.generalFuse([b], fuzzy) if fuzzy else a.generalFuse([b])
        except Exception as exc:
            log("rebuild: the general fuse gave nothing (%s)" % exc)
            continue
        common, missing, extra = [], [], []
        ok = True
        noise = 0.0
        for piece in result.Solids:
            volume = piece.Volume
            if abs(volume) <= 1e-7 * scale:
                # a sliver between faces that lie on each other within a hair (a mesh's facets
                # and their copies): no material either side, only rounding
                noise += abs(volume)
                continue
            # every piece lies in A or in B: when it is not in one, it is in the other
            points = _PiecePoints(piece)
            in_a = _membership(points, rows_a, on)
            in_b = _membership(points, rows_b, on)
            if in_a is False and in_b is None:
                in_b = True
            elif in_b is False and in_a is None:
                in_a = True
            if in_a is None or in_b is None or not (in_a or in_b):
                point = _inside_point(piece)
                if point is None:
                    ok = False
                    break
                in_b = b.isInside(point, 1e-9, True)
                in_a = a.isInside(point, 1e-9, True) if in_b else True
            if in_a and in_b:
                common.append((piece, volume))
            elif in_a:
                missing.append((piece, volume))
            elif in_b:
                extra.append((piece, volume))
        if not ok:
            continue
        v_c = sum(v for _s, v in common)
        v_m = sum(v for _s, v in missing)
        v_e = sum(v for _s, v in extra)
        slack = 1e-6 * scale + noise
        if abs(v_c + v_m - v_a) <= slack and abs(v_c + v_e - v_b) <= slack:
            method = "exact" if not fuzzy else "fuzzy"
            return v_c, v_m, v_e, _merge(missing), _merge(extra), method
        log(
            "rebuild: the pieces do not add up (%.6g + %.6g vs %.6g; %.6g + %.6g vs %.6g)"
            % (v_c, v_m, v_a, v_c, v_e, v_b)
        )
    common, missing, extra = _sampled(a, b)
    return common, missing, extra, [], [], "sampled"


class _PiecePoints:
    """A point (and the outward normal) on each face of a piece, worked out when first asked:
    the tests against both solids read the same points (and no face's area is measured)."""

    def __init__(self, piece):
        faces = piece.Faces
        # curved faces first: they lie on small faces of the solids (holes, fillets), whose
        # inside test is quick; a flat face often lies on a big face with many holes
        flat = [_is_flat(f) for f in faces]
        self.faces = [f for f, x in zip(faces, flat) if not x] + [
            f for f, x in zip(faces, flat) if x
        ]
        self.found = {}

    def __len__(self):
        return len(self.faces)

    def point(self, i):
        if i not in self.found:
            face = self.faces[i]
            got = _face_points(face, 1) or _face_points(face, 3)
            self.found[i] = got[0] if got else None
        return self.found[i]


def _is_flat(face):
    try:
        return face.Surface.TypeId == "Part::GeomPlane"
    except Exception:
        return False


def _membership(points, rows, tol):
    """True / False: the piece lies inside / outside the solid these face rows belong to, read
    from a face of the piece that lies on one of the solid's faces (the piece's outward normal
    agrees with the solid's there: inside); None when no face of the piece lies on them.
    points: the piece's _PiecePoints."""
    for i in range(len(points)):
        found = points.point(i)
        if found is None:
            continue
        p, n = found
        for row in rows:
            box = row.box
            if not (
                box.XMin - tol <= p.x <= box.XMax + tol
                and box.YMin - tol <= p.y <= box.YMax + tol
                and box.ZMin - tol <= p.z <= box.ZMax + tol
            ):
                continue
            if not _near_face(p, row, tol):
                continue
            out = _outward(row, p)
            if out is None:
                continue
            d = n.dot(out)
            if abs(d) < 0.5:
                continue
            return d > 0
    return None


def _outward(row, p):
    """The outward normal of a solid's face at a point on it."""
    try:
        if row.kind == "plane" and row.key is not None:
            return row.key[0]
        if row.kind in ("cylinder", "sphere") and row.key is not None:
            if row.kind == "cylinder":
                axis, centre, _radius, concave = row.key
                foot = centre + axis * (p - centre).dot(axis)
            else:
                foot, _radius, concave = row.key
            if concave is not None:
                radial = p - foot
                if radial.Length > 1e-12:
                    radial.normalize()
                    return radial * -1.0 if concave else radial
        u, v = row.face.Surface.parameter(p)
        return row.face.normalAt(u, v)
    except Exception:
        return None


def _merge(pairs):
    """Pieces that touch along a face are one region (a General Fuse can split a region where
    a face of the other solid ends inside it). pairs: [(solid, volume)]; so is the answer."""
    if len(pairs) < 2:
        return pairs
    boxes = [solid.BoundBox for solid, _v in pairs]  # (once: a box is measured on each ask)
    groups = []
    for i, (solid, _v) in enumerate(pairs):
        joined = [
            g for g in groups if any(_touch(solid, boxes[i], pairs[j][0], boxes[j]) for j in g)
        ]
        merged = [i]
        for g in joined:
            merged.extend(g)
            groups.remove(g)
        groups.append(merged)
    out = []
    for g in groups:
        if len(g) == 1:
            out.append(pairs[g[0]])
            continue
        solids = [pairs[j][0] for j in g]
        try:
            fused = solids[0].fuse(solids[1:]).removeSplitter()
            if fused.Solids:
                out.extend((s, s.Volume) for s in fused.Solids)
            else:
                out.extend(pairs[j] for j in g)
        except Exception:
            out.extend(pairs[j] for j in g)
    return out


def _touch(a, box_a, b, box_b):
    if not _boxes_near(box_a, box_b, 1e-7):
        return False
    try:
        for fa in a.Faces:
            for fb in b.Faces:
                if fa.isSame(fb):
                    return True
    except Exception:
        pass
    return False


def _inside_point(solid):
    """A point strictly inside a solid: its centre of mass, else a point stepped a little
    inside from the middle of one of its faces."""
    try:
        centre = solid.CenterOfMass
        if solid.isInside(centre, 1e-9, False):
            return centre
    except Exception:
        pass
    size = max(1e-6, solid.BoundBox.DiagonalLength)
    for face in sorted(solid.Faces, key=lambda f: -f.Area):
        for p, n in _face_points(face, 3):
            for step in (1e-4, 1e-3, 1e-2, 1e-5):
                q = p - n * (step * size)
                try:
                    if solid.isInside(q, 1e-9, False):
                        return q
                except Exception:
                    break
    return None


def _face_points(face, n, full=False):
    """[(point, outward normal)] at the centres of an n x n grid of the face's parameters
    that lie on the face (full: the face is its whole parameter rectangle, every point is on
    it: no domain test, which costs a millisecond on a face with many holes)."""
    out = []
    try:
        u0, u1, v0, v1 = face.ParameterRange
    except Exception:
        return out
    for i in range(n):
        for j in range(n):
            u = u0 + (u1 - u0) * (i + 0.5) / n
            v = v0 + (v1 - v0) * (j + 0.5) / n
            try:
                if full or face.isPartOfDomain(u, v):
                    out.append((face.valueAt(u, v), face.normalAt(u, v)))
            except Exception:
                continue
    return out


def _sampled(a, b, count=4096):
    """(common, missing, extra) volumes measured along rays (the fallback when booleans fail):
    a grid of `count` rays along Z over both solids' box; along each ray, where it is inside A
    and inside B (its crossings of each solid's triangles, OpenCASCADE's tessellation), and
    their overlap. About 1 % exact and a fraction of a second (a point test per grid point
    took minutes on a 300-face part)."""
    import numpy

    box = App.BoundBox(a.BoundBox)
    box.add(b.BoundBox)
    n = max(8, int(round(math.sqrt(count))))
    dx, dy = box.XLength / n, box.YLength / n
    if dx <= 0 or dy <= 0:
        return 0.0, 0.0, 0.0
    # (a little off the cells' centres: no ray runs along an edge of a part drawn on a grid)
    xs = box.XMin + (numpy.arange(n) + 0.5 + 0.0137) * dx
    ys = box.YMin + (numpy.arange(n) + 0.5 - 0.0219) * dy
    inside_a, odd_a = _ray_insides(a, xs, ys, box)
    inside_b, odd_b = _ray_insides(b, xs, ys, box)
    common = missing = extra = 0.0
    for ray in (set(inside_a) | set(inside_b)) - odd_a - odd_b:
        along_a, along_b = inside_a.get(ray, []), inside_b.get(ray, [])
        both = _overlap(along_a, along_b)
        common += both
        missing += sum(z1 - z0 for z0, z1 in along_a) - both
        extra += sum(z1 - z0 for z0, z1 in along_b) - both
    cell = dx * dy
    return common * cell, max(0.0, missing) * cell, max(0.0, extra) * cell


def _ray_insides(shape, xs, ys, box):
    """({ray: [(z0, z1)]}, {rays left out}): where the rays along Z through (xs[i], ys[j]) (ray
    i * len(ys) + j) are inside the solid: their crossings of its triangles, in pairs. A ray
    with an odd number of crossings (it grazes an edge) is left out (of both solids)."""
    import numpy as np

    size = max(box.DiagonalLength, 1e-6)
    points, triangles = shape.tessellate(1e-3 * size)
    if not triangles:
        return {}, set()
    xyz = np.array([(p.x, p.y, p.z) for p in points])
    tri = np.array(triangles, dtype=int)
    pa, pb, pc = xyz[tri[:, 0]], xyz[tri[:, 1]], xyz[tri[:, 2]]
    nx, ny = len(xs), len(ys)
    sx = xs[1] - xs[0] if nx > 1 else 1.0
    sy = ys[1] - ys[0] if ny > 1 else 1.0
    lo = np.minimum(np.minimum(pa, pb), pc)
    hi = np.maximum(np.maximum(pa, pb), pc)
    # the rays each triangle's box covers: (i0..i1) x (j0..j1)
    i0 = np.clip(np.ceil((lo[:, 0] - xs[0]) / sx), 0, nx).astype(int)
    i1 = np.clip(np.floor((hi[:, 0] - xs[0]) / sx), -1, nx - 1).astype(int)
    j0 = np.clip(np.ceil((lo[:, 1] - ys[0]) / sy), 0, ny).astype(int)
    j1 = np.clip(np.floor((hi[:, 1] - ys[0]) / sy), -1, ny - 1).astype(int)
    wide = np.maximum(0, i1 - i0 + 1)
    tall = np.maximum(0, j1 - j0 + 1)
    counts = wide * tall
    total = int(counts.sum())
    if total == 0:
        return {}, set()
    which = np.repeat(np.arange(len(tri)), counts)
    k = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    tall_k = np.repeat(tall, counts)
    ii = np.repeat(i0, counts) + k // tall_k
    jj = np.repeat(j0, counts) + k % tall_k
    a, b, c = pa[which], pb[which], pc[which]
    e0x, e0y = c[:, 0] - a[:, 0], c[:, 1] - a[:, 1]
    e1x, e1y = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
    qx, qy = xs[ii] - a[:, 0], ys[jj] - a[:, 1]
    den = e0x * e1y - e1x * e0y
    ok = np.abs(den) > 1e-15 * size * size  # (a triangle seen edge-on: a wall, never crossed)
    den = np.where(ok, den, 1.0)
    u = (qx * e1y - e1x * qy) / den
    v = (e0x * qy - qx * e0y) / den
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1)
    z = a[:, 2] + u * (c[:, 2] - a[:, 2]) + v * (b[:, 2] - a[:, 2])
    rays = (ii * ny + jj)[hit]
    z = z[hit]
    order = np.lexsort((z, rays))
    rays, z = rays[order], z[order]
    out = {}
    odd = set()
    same = 1e-9 * size
    start = 0
    for end in list(np.nonzero(np.diff(rays))[0] + 1) + [len(rays)]:
        zs = []
        for value in z[start:end]:
            if not zs or value - zs[-1] > same:  # (two triangles meeting where the ray crosses)
                zs.append(float(value))
        if len(zs) % 2:
            odd.add(int(rays[start]))
        elif zs:
            out[int(rays[start])] = [(zs[i], zs[i + 1]) for i in range(0, len(zs), 2)]
        start = end
    return out, odd


def _overlap(one, other):
    """The length two sorted lists of stretches [(z0, z1)] share."""
    total = 0.0
    i = j = 0
    while i < len(one) and j < len(other):
        low = max(one[i][0], other[j][0])
        high = min(one[i][1], other[j][1])
        if high > low:
            total += high - low
        if one[i][1] < other[j][1]:
            i += 1
        else:
            j += 1
    return total


# -- regions ----------------------------------------------------------------------------------
def _xyz(v, digits=6):
    return [_r(v.x, digits), _r(v.y, digits), _r(v.z, digits)]


def _r(value, digits=6):
    out = round(float(value), digits)
    return 0.0 if out == 0 else out


def region_facts(solid, volume=None):
    """The plain numbers rebuild_core classifies a region of material by (volume: the solid's,
    when already measured)."""
    from .ai.ops import selectors

    box = solid.BoundBox
    centre = solid.CenterOfMass
    faces = []
    for face in solid.Faces:
        kind = selectors.face_type(face)
        row = {"type": kind, "area": face.Area}
        surface = face.Surface
        try:
            if kind == "plane":
                row["normal"] = list(selectors._unit(selectors.face_normal(face)))
            elif kind in ("cylinder", "cone", "torus", "sphere"):
                row.update(_round_facts(face, surface, kind, centre))
        except Exception:
            pass
        faces.append(row)
    return {
        "volume": solid.Volume if volume is None else volume,
        "center": _xyz(centre),
        "bbox": [_r(v) for v in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)],
        "faces": faces,
    }


def _round_facts(face, surface, kind, centre):
    row = {}
    mid = _face_points(face, 1) or _face_points(face, 3)
    if kind == "sphere":
        row["radius"] = surface.Radius
        if mid:
            p, n = mid[0]
            row["convex"] = (p - surface.Center).dot(n) > 0
        return row
    axis = App.Vector(surface.Axis)
    axis.normalize()
    point = App.Vector(surface.Center if kind != "cone" else surface.Apex)
    row["axis"] = [axis.x, axis.y, axis.z]
    ts = []
    for edge in face.Edges:
        try:
            for q in edge.discretize(12):
                ts.append((q - point).dot(axis))
        except Exception:
            continue
    length = (max(ts) - min(ts)) if ts else 0.0
    # the axis point beside the region's centre (where the hole is, seen along its axis)
    t = (centre - point).dot(axis)
    row["point"] = _xyz(point + axis * t)
    if kind == "cylinder":
        row["radius"] = surface.Radius
        row["length"] = length
        row["span"] = face.Area / (surface.Radius * length) if length > 1e-12 else 0.0
        if ts:
            row["ends"] = [_xyz(point + axis * min(ts)), _xyz(point + axis * max(ts))]
    elif kind == "torus":
        row["major"] = surface.MajorRadius
        row["minor"] = surface.MinorRadius
    if mid:
        p, n = mid[0]
        foot = point + axis * (p - point).dot(axis)
        if kind == "torus":
            radial = p - foot
            radial.normalize()
            foot = foot + radial * surface.MajorRadius
        row["convex"] = (p - foot).dot(n) > 0
    return row


def _region(solid, side, rebuilt, tol, opts, volume=None):
    """One region of missing / extra material: its numbers, what it looks like, and the tool
    call that would make it when that is certain (fillet / chamfer the edges found)."""
    try:
        facts = region_facts(solid, volume)
    except Exception as exc:
        warn("rebuild: a region could not be measured (%s)" % exc)
        return None
    if facts["volume"] <= 1e-9:
        return None
    shape = core.classify_region(facts, side)
    row = {
        "side": side,
        "volume": facts["volume"],
        "center": facts["center"],
        "bbox": facts["bbox"],
        "looks_like": shape["looks_like"],
        "shape": shape,
    }
    budget = opts.get("_fixes", {})
    can_fix = opts.get("selectors") and budget.get(side, 0) < MAX_FIXES
    if side == "extra" and shape["kind"] in ("fillet", "chamfer") and can_fix:
        budget[side] = budget.get(side, 0) + 1
        try:
            fix = _edge_fix(solid, shape, rebuilt, tol, opts)
            if fix:
                row["fix"] = fix
        except Exception as exc:
            log("rebuild: no edge selector for a %s (%s)" % (shape["kind"], exc))
    if shape["kind"] in ("cylinder", "stepped_cylinder"):
        for f in facts["faces"]:
            if f.get("type") == "cylinder" and f.get("ends"):
                shape["ends"] = f["ends"]
                break
        if side == "extra" and shape["kind"] == "cylinder" and can_fix:
            budget[side] = budget.get(side, 0) + 1
            try:
                fix = _hole_fix(shape, rebuilt, tol, opts)
                if fix:
                    row["fix"] = fix
            except Exception as exc:
                log("rebuild: no hole call for a region (%s)" % exc)
    return row


def _flat_faces(rebuilt, opts):
    """[(name, face, outward normal, box)] of the rebuild's flat faces, once per compare."""
    table = opts.get("_flat") if opts is not None else None
    if table is None:
        table = []
        for i, face in enumerate(rebuilt.Faces, start=1):
            if face.Surface.TypeId != "Part::GeomPlane":
                continue
            try:
                u0, u1, v0, v1 = face.ParameterRange
                normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            except Exception:
                continue
            table.append(("Face%d" % i, face, normal, face.BoundBox))
        if opts is not None:
            opts["_flat"] = table
    return table


def _hole_fix(shape, rebuilt, tol, opts=None):
    """A hole the rebuild has not cut: a Single Hole call on the flat face it starts on
    (through_all when it comes out on the other side too)."""
    ends = shape.get("ends")
    if not ends:
        return None
    axis = App.Vector(*shape["axis"])
    near = max(tol, 1e-6)
    found = []
    for end in ends:
        point = App.Vector(*end)
        hit = None
        for name, face, normal, box in _flat_faces(rebuilt, opts):
            if abs(abs(normal.dot(axis)) - 1.0) > 1e-6:
                continue
            if not (
                box.XMin - near <= point.x <= box.XMax + near
                and box.YMin - near <= point.y <= box.YMax + near
                and box.ZMin - near <= point.z <= box.ZMax + near
            ):
                continue
            try:
                if face.isInside(point, near, True):
                    hit = (name, normal, point)
                    break
            except Exception:
                continue
        found.append(hit)
    starts = [h for h in found if h is not None]
    if not starts:
        return None
    name, _normal, point = starts[0]
    refs = _refs(rebuilt, "faces", {name}, opts)
    if not refs.get(name):
        return None
    args = {
        "face": refs[name],
        "at": [_nice(point.x), _nice(point.y), _nice(point.z)],
        "diameter": _nice(shape["diameter"]),
    }
    if len(starts) == 2:
        args["through_all"] = True
    else:
        args["depth"] = _nice(shape["depth"])
    return {"tool": "hole", "args": args}


MAX_FIXES = 24  # regions per side given a ready call (the biggest first)


def _refs(shape, element, names, opts=None):
    """geometry_facts.stable_refs for these names, with the shape's selector index built once
    per compare (24 hole calls on a 300-face part built it 24 times: about a second)."""
    from .ai import geometry_facts

    make = getattr(geometry_facts, "_Index", None)
    unique = getattr(geometry_facts, "_unique", None)
    if opts is None or make is None or unique is None:
        return geometry_facts.stable_refs(shape, element, set(names))
    cache = opts.setdefault("_index", {})
    key = (id(shape), element)
    if key not in cache:
        cache[key] = (shape, make(shape, element))  # (the shape kept: its id stays its own)
    index = cache[key][1]
    out = {}
    for i, (name, _sub) in enumerate(index.items):
        if name not in names:
            continue
        spec = unique(index, i)
        if spec is not None:
            try:
                if index.select(spec) != [i]:
                    spec = None
            except Exception:
                spec = None
        out[name] = spec
    return out


def _edge_table(rebuilt, opts):
    """[(name, middle point, end points)] of the rebuild's edges, measured once per compare."""
    table = opts.get("_edges")
    if table is None:
        table = []
        for i, edge in enumerate(rebuilt.Edges, start=1):
            try:
                mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
                ends = [v.Point for v in edge.Vertexes]
            except Exception:
                continue
            table.append(("Edge%d" % i, mid, ends))
        opts["_edges"] = table
    return table


def _edge_fix(solid, shape, rebuilt, tol, opts=None):
    """The rebuilt part's sharp edges a missing fillet / chamfer sits on, as a fillet /
    chamfer call: {"tool", "args": {"edges": selector, "radius" | "distance"}}."""
    import Part

    names = []
    box = solid.BoundBox
    near = max(tol, 1e-6)
    for name, mid, ends in _edge_table(rebuilt, opts if opts is not None else {}):
        if not (
            box.XMin - tol <= mid.x <= box.XMax + tol
            and box.YMin - tol <= mid.y <= box.YMax + tol
            and box.ZMin - tol <= mid.z <= box.ZMax + tol
        ):
            continue
        try:
            if solid.distToShape(Part.Vertex(mid))[0] > near:
                continue
            # the sharp edge runs along the strip: both its ends are on the region too
            if ends and any(solid.distToShape(Part.Vertex(p))[0] > near for p in ends):
                continue
        except Exception:
            continue
        names.append(name)
    if not names:
        return None
    refs = _refs(rebuilt, "edges", set(names), opts)
    picks = [refs[n] for n in names if refs.get(n)]
    if len(picks) != len(names):
        return None
    if len(picks) == 1:
        edges = picks[0]
    else:
        edges = {"any_of": picks, "count": len(picks)}
    if shape["kind"] == "fillet":
        return {"tool": "fillet", "args": {"edges": edges, "radius": _nice(shape["radius"])}}
    a, b = shape["distances"]
    if abs(a - b) > 1e-3:
        return None
    return {"tool": "chamfer", "args": {"edges": edges, "distance": _nice(a)}}


def _nice(value):
    """A measured size as the number a person typed: 1.9999999 -> 2."""
    for digits in (3, 4, 6):
        rounded = round(value, digits)
        if abs(rounded - value) <= 1e-6:
            return rounded
    return round(value, 6)


_KEYS = (
    "diameter",
    "depth",
    "axis",
    "at",
    "ends",
    "steps",
    "radius",
    "length",
    "edges",
    "distances",
    "size",
    "thickness",
    "thin_axis",
)


def _plain(value):
    if isinstance(value, float):
        return _r(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _public(region):
    row = {k: _plain(region[k]) for k in ("volume", "center", "bbox", "looks_like")}
    shape = region["shape"]
    row["kind"] = shape["kind"]
    for key in _KEYS:
        if key in shape:
            row[key] = _plain(shape[key])
    if "fix" in region:
        row["fix"] = region["fix"]
    return row


def _group_public(group):
    out = {
        "side": group["side"],
        "kind": group["kind"],
        "count": group["count"],
        "volume": _r(group["volume"]),
        "says": core.group_text(group),
    }
    fix = group_fix(group)
    if fix:
        out["fix"] = fix
    return out


def group_fix(group):
    """One call for a group of equal fillets / chamfers (Fusion makes one step of all the
    edges of one size): the edges of every region's call together."""
    fixes = [r.get("fix") for r in group["regions"]]
    if not fixes or any(f is None for f in fixes):
        return None
    if group["kind"] not in ("fillet", "chamfer"):
        return fixes[0] if len(fixes) == 1 else None
    picks = []
    for fix in fixes:
        edges = fix["args"]["edges"]
        picks.extend(edges["any_of"] if "any_of" in edges else [edges])
    args = dict(fixes[0]["args"])
    args["edges"] = picks[0] if len(picks) == 1 else {"any_of": picks, "count": len(picks)}
    return {"tool": fixes[0]["tool"], "args": args}


# -- faces ----------------------------------------------------------------------------------------
class _FaceRow:
    """What the face matching needs of one face, worked out once."""

    __slots__ = (
        "index",
        "face",
        "kind",
        "area",
        "box",
        "key",
        "matched",
        "samples",
        "grid",
        "full",
        "range",
    )

    def __init__(self, index, face, grid=5, area=None):
        from .ai.ops import selectors

        self.index = index
        self.face = face
        self.kind = selectors.face_type(face)
        self.area = face.Area if area is None else area
        self.box = face.BoundBox
        self.key = None
        self.matched = False
        self.samples = None
        self.grid = grid
        surface = face.Surface
        self.full = False  # a plane / cylinder face that is its whole parameter rectangle
        self.range = None
        try:
            if self.kind in ("plane", "cylinder") and len(face.Wires) == 1:
                u0, u1, v0, v1 = face.ParameterRange
                rect = (u1 - u0) * (v1 - v0)
                if self.kind == "cylinder":
                    rect *= surface.Radius
                self.full = rect > 0 and abs(rect - self.area) <= 1e-7 * max(1.0, self.area)
                self.range = (u0, u1, v0, v1)
        except Exception:
            self.full = False
        try:
            if self.kind == "plane":
                n = App.Vector(*selectors._unit(selectors.face_normal(face)))
                on = face.Vertexes[0].Point if face.Vertexes else face.CenterOfMass
                self.key = (n, n.dot(on))
            elif self.kind == "cylinder":
                axis = App.Vector(surface.Axis)
                axis.normalize()
                mid = _face_points(face, 1) or _face_points(face, 3)
                concave = None
                if mid:
                    p, n = mid[0]
                    foot = surface.Center + axis * (p - surface.Center).dot(axis)
                    concave = (p - foot).dot(n) < 0
                self.key = (axis, App.Vector(surface.Center), surface.Radius, concave)
            elif self.kind == "sphere":
                mid = _face_points(face, 1) or _face_points(face, 3)
                concave = None
                if mid:
                    p, n = mid[0]
                    concave = (p - surface.Center).dot(n) < 0
                self.key = (App.Vector(surface.Center), surface.Radius, concave)
            elif self.kind == "cone":
                axis = App.Vector(surface.Axis)
                axis.normalize()
                self.key = (App.Vector(surface.Apex), axis, abs(surface.SemiAngle))
            elif self.kind == "torus":
                axis = App.Vector(surface.Axis)
                axis.normalize()
                self.key = (
                    App.Vector(surface.Center),
                    axis,
                    surface.MajorRadius,
                    surface.MinorRadius,
                )
        except Exception:
            self.key = None

    def points(self):
        if self.samples is None:
            found = [p for p, _n in _face_points(self.face, self.grid, self.full)]
            if len(found) < 3:
                found += [p for p, _n in _face_points(self.face, 11)][:25]
            if not found:
                try:
                    found = [
                        e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
                        for e in self.face.Edges
                    ]
                except Exception:
                    found = []
            self.samples = found
        return self.samples


def _on_full(row, p, tol):
    """p lies on a face that is its whole parameter rectangle (row.full: a plane or cylinder
    face without holes or trims), measured on its surface instead of with OpenCASCADE's face
    classifier."""
    surface = row.face.Surface
    u, v = surface.parameter(p)
    if (surface.value(u, v) - p).Length > tol:
        return False
    u0, u1, v0, v1 = row.range
    du = tol
    if row.kind == "cylinder":
        du = tol / max(surface.Radius, 1e-12)
        turn = 2.0 * math.pi
        while u < u0 - du:
            u += turn
        while u > u1 + du and u - turn >= u0 - du:
            u -= turn
    return u0 - du <= u <= u1 + du and v0 - tol <= v <= v1 + tol


def _on_face(row, p, tol):
    """p lies on the row's face (within tol)."""
    if row.full:
        try:
            return _on_full(row, p, tol)
        except Exception:
            pass
    return row.face.isInside(p, tol, True)


def _face_rows(shape):
    """The faces' rows; small faces get fewer sample points (a mesh's narrow facets)."""
    faces = list(shape.Faces)
    areas = [f.Area for f in faces]  # (once: an area is measured on each ask)
    biggest = max(areas or [0.0])
    return [
        _FaceRow(i, f, 5 if a >= 0.02 * biggest else 3, a)
        for i, (f, a) in enumerate(zip(faces, areas))
    ]


def _same_surface(a, b, tol):
    """Two faces lie on the same surface (and face the same way)."""
    if a.kind != b.kind or a.key is None or b.key is None:
        return False
    if a.kind == "plane":
        (na, da), (nb, db) = a.key, b.key
        return na.dot(nb) > 1 - 1e-6 and abs(da - db) <= tol
    if a.kind == "cylinder":
        axa, pa, ra, ca = a.key
        axb, pb, rb, cb = b.key
        if abs(ra - rb) > tol or abs(axa.dot(axb)) < 1 - 1e-6 or ca != cb:
            return False
        d = pb - pa
        off = d - axa * d.dot(axa)
        return off.Length <= tol
    if a.kind == "sphere":
        ca, ra, va = a.key
        cb, rb, vb = b.key
        return abs(ra - rb) <= tol and (ca - cb).Length <= tol and va == vb
    if a.kind == "cone":
        pa, axa, sa = a.key
        pb, axb, sb = b.key
        # (either way along the axis: the cover test below decides which nappe)
        return (pa - pb).Length <= tol and abs(axa.dot(axb)) > 1 - 1e-6 and abs(sa - sb) <= 1e-6
    if a.kind == "torus":
        ca, axa, ma, na = a.key
        cb, axb, mb, nb = b.key
        return (
            (ca - cb).Length <= tol
            and abs(axa.dot(axb)) > 1 - 1e-6
            and abs(ma - mb) <= tol
            and abs(na - nb) <= tol
        )
    return False


def _same_box(a, b, tol):
    return (
        abs(a.XMin - b.XMin) <= tol
        and abs(a.YMin - b.YMin) <= tol
        and abs(a.ZMin - b.ZMin) <= tol
        and abs(a.XMax - b.XMax) <= tol
        and abs(a.YMax - b.YMax) <= tol
        and abs(a.ZMax - b.ZMax) <= tol
    )


def _boxes_near(a, b, tol):
    return not (
        a.XMin > b.XMax + tol
        or b.XMin > a.XMax + tol
        or a.YMin > b.YMax + tol
        or b.YMin > a.YMax + tol
        or a.ZMin > b.ZMax + tol
        or b.ZMin > a.ZMax + tol
    )


def _covered(row, others, tol):
    """Every sample point of the face lies on one of the other faces."""
    if not others:
        return False
    for other in others:
        # the same face (same surface, area and box): no need to sample it
        if abs(other.area - row.area) <= 1e-7 * max(1.0, row.area) and _same_box(
            row.box, other.box, tol
        ):
            return True
    points = row.points()
    if not points:
        return False
    for p in points:
        hit = False
        for other in others:
            box = other.box
            if not (
                box.XMin - tol <= p.x <= box.XMax + tol
                and box.YMin - tol <= p.y <= box.YMax + tol
                and box.ZMin - tol <= p.z <= box.ZMax + tol
            ):
                continue
            try:
                if _on_face(other, p, tol):
                    hit = True
                    break
            except Exception:
                continue
        if not hit:
            return False
    return True


class _Distances:
    """Exact distances from points to a shape's faces, the faces' boxes first (numpy)."""

    def __init__(self, rows):
        import numpy

        self.rows = rows
        self.np = numpy
        self.lo = numpy.array([[r.box.XMin, r.box.YMin, r.box.ZMin] for r in rows] or [[0, 0, 0]])
        self.hi = numpy.array([[r.box.XMax, r.box.YMax, r.box.ZMax] for r in rows] or [[0, 0, 0]])

    def __call__(self, point, limit=None):
        import Part

        if not self.rows:
            return float("inf")
        np = self.np
        p = np.array([point.x, point.y, point.z])
        gap = np.maximum(np.maximum(self.lo - p, p - self.hi), 0.0)
        bound = np.sqrt((gap * gap).sum(axis=1))
        best = float("inf")
        vertex = Part.Vertex(point)
        for i in np.argsort(bound):
            if bound[i] >= best or (limit is not None and bound[i] > limit):
                break
            try:
                d = self.rows[int(i)].face.distToShape(vertex)[0]
            except Exception:
                continue
            if d < best:
                best = d
                if best <= 1e-9:
                    break
        return best


def _match_faces(reference, rebuilt, tol, mesh, opts, rows=None):
    """Faces of the original and of the rebuild matched by geometry: on the same surface
    (type, plane / axis / radius within tol, facing the same way) and covering each other
    (every sample point of one lies on the other). A reference made from a mesh is flat
    facets: there a face is matched when all its sample points lie within tol of the other
    part's surface."""
    rows_a, rows_b = rows if rows is not None else (_face_rows(reference), _face_rows(rebuilt))
    if mesh:
        # the exact test first (the mesh's flat faces are exact planes), then within tol of
        # the other part's surface for the facets of round regions and the round faces
        for mine, theirs in ((rows_a, rows_b), (rows_b, rows_a)):
            near = _BoxIndex(theirs, tol)
            for row in mine:
                same = [o for o in near(row) if _same_surface(row, o, tol)]
                row.matched = _covered(row, same, tol) or _near_surfaces(row, theirs, tol)
    else:
        for mine, theirs in ((rows_a, rows_b), (rows_b, rows_a)):
            near = _BoxIndex(theirs, tol)
            for row in mine:
                same = [o for o in near(row) if _same_surface(row, o, tol)]
                row.matched = _covered(row, same, tol)
                if not row.matched and (row.key is None or row.kind in ("cone", "torus")):
                    # (a cone or torus may be described from its other end: measured)
                    row.matched = _twin(row, theirs, tol) or _on_surfaces(row, theirs, tol)
    limit = int(opts.get("faces", 20))
    out = {
        "reference": len(rows_a),
        "matched": sum(1 for r in rows_a if r.matched),
        "rebuilt": len(rows_b),
        "rebuilt_matched": sum(1 for r in rows_b if r.matched),
        "unmatched_reference": _face_list(
            reference, [r for r in rows_a if not r.matched], limit, opts
        ),
        "unmatched_rebuilt": _face_list(rebuilt, [r for r in rows_b if not r.matched], limit, opts),
        "_rows": (rows_a, rows_b),
    }
    return out


class _BoxIndex:
    """The rows whose boxes come within tol of a row's box, in their order (numpy: a 300-face
    part against another made 90 000 box tests in Python)."""

    def __init__(self, rows, tol):
        import numpy

        self.rows = rows
        self.np = numpy
        self.tol = tol
        self.lo = numpy.array([[r.box.XMin, r.box.YMin, r.box.ZMin] for r in rows] or [[0, 0, 0]])
        self.hi = numpy.array([[r.box.XMax, r.box.YMax, r.box.ZMax] for r in rows] or [[0, 0, 0]])

    def __call__(self, row):
        if not self.rows:
            return []
        b, t, np = row.box, self.tol, self.np
        fits = np.all(self.lo <= np.array([b.XMax + t, b.YMax + t, b.ZMax + t]), axis=1) & np.all(
            self.hi >= np.array([b.XMin - t, b.YMin - t, b.ZMin - t]), axis=1
        )
        return [self.rows[int(i)] for i in np.nonzero(fits)[0]]


def _twin(row, others, tol):
    """A face of the other part of the same kind, area and box: the same face (a free-form
    face copied exactly), matched without measuring distances."""
    for other in others:
        if (
            other.kind == row.kind
            and abs(other.area - row.area) <= 1e-7 * max(1.0, row.area)
            and _same_box(row.box, other.box, tol)
        ):
            return True
    return False


def _near_surfaces(row, others, tol):
    """Every sample point of the face lies within tol of a face of the other part (its
    surface, inside its boundary): a mesh's facets against round faces and the other way."""
    near = [o for o in others if _boxes_near(row.box, o.box, tol)]
    if not near:
        return False
    for p in row.points():
        if not any(_near_face(p, o, tol) for o in near):
            return False
    return True


def _near_face(point, row, tol):
    """The point lies within tol of the face (plane, cylinder, sphere: measured on the
    surface and checked inside the face's boundary; other faces: OpenCASCADE's distance)."""
    box = row.box
    if not (
        box.XMin - tol <= point.x <= box.XMax + tol
        and box.YMin - tol <= point.y <= box.YMax + tol
        and box.ZMin - tol <= point.z <= box.ZMax + tol
    ):
        return False
    try:
        if row.kind == "plane" and row.key is not None:
            normal, offset = row.key
            gap = normal.dot(point) - offset
            if abs(gap) > tol:
                return False
            foot = point - normal * gap
        elif row.kind == "cylinder" and row.key is not None:
            axis, centre, radius, _concave = row.key
            on_axis = centre + axis * (point - centre).dot(axis)
            radial = point - on_axis
            if abs(radial.Length - radius) > tol:
                return False
            foot = on_axis + radial * (radius / radial.Length) if radial.Length > 1e-12 else point
        elif row.kind == "sphere" and row.key is not None:
            centre, radius, _concave = row.key
            radial = point - centre
            if abs(radial.Length - radius) > tol:
                return False
            foot = centre + radial * (radius / radial.Length) if radial.Length > 1e-12 else point
        elif row.kind == "cone" and row.key is not None:
            apex, axis, half = row.key
            along = (point - apex).dot(axis)
            across = (point - apex - axis * along).Length
            # distance to the cone's surface in the plane through its axis and the point
            if abs(across * math.cos(half) - abs(along) * math.sin(half)) > tol:
                return False
            foot = point
        elif row.kind == "torus" and row.key is not None:
            centre, axis, major, minor = row.key
            along = (point - centre).dot(axis)
            across = (point - centre - axis * along).Length
            if abs(math.hypot(across - major, along) - minor) > tol:
                return False
            foot = point
        else:
            import Part

            return row.face.distToShape(Part.Vertex(point))[0] <= tol
        return _on_face(row, foot, tol)
    except Exception:
        return False


def _on_surfaces(row, others, tol):
    """A face without an analytic key (free-form, cone, torus): every sample point within
    tol of a face of the other part of the same type (exact distances)."""
    same = [o for o in others if o.kind == row.kind and _boxes_near(row.box, o.box, tol)]
    if not same:
        return False
    distance = _Distances(same)
    return all(distance(p, tol) <= tol for p in row.points())


def _face_list(shape, rows, limit, opts):
    """The unmatched faces: kind, words, a selector that picks exactly that face."""
    from .ai import geometry_facts

    rows = sorted(rows, key=lambda r: -r.area)
    shown = rows[:limit]
    refs = {}
    if opts.get("selectors") and shown:
        try:
            wanted = {"Face%d" % (r.index + 1) for r in shown}
            refs = _refs(shape, "faces", wanted, opts)
        except Exception as exc:
            log("rebuild: face selectors not made (%s)" % exc)
    out = []
    for row in shown:
        facts = geometry_facts.face_facts(row.face)
        if row.kind == "cylinder" and row.key is not None:
            facts["concave"] = row.key[3]
        out.append(
            {
                "kind": row.kind,
                "describe": core.describe_face(facts),
                "selector": refs.get("Face%d" % (row.index + 1)),
                "area": _r(row.area),
            }
        )
    if len(rows) > limit:
        out.append(
            {
                "kind": "more",
                "describe": "%d more faces" % (len(rows) - limit),
                "selector": None,
                "area": _r(sum(r.area for r in rows[limit:])),
            }
        )
    return out


# -- deviation ------------------------------------------------------------------------------------
DEVIATION_FACES = 48  # unmatched faces measured at most (spread over their sizes)


def _spread(rows, count):
    """At most `count` of the rows, from the biggest to the smallest, evenly spread."""
    if len(rows) <= count:
        return rows
    ordered = sorted(rows, key=lambda r: -r.area)
    if count <= 1:
        return ordered[:1]
    return [ordered[round(i * (len(ordered) - 1) / (count - 1))] for i in range(count)]


def _deviation(rows, budget=160):
    """How far the surfaces are apart: sample points of the unmatched faces of each part,
    their exact distance to the other part (matched faces count 0). max and an
    area-weighted mean, mm. Beyond DEVIATION_FACES unmatched faces, a spread of them is
    measured (and the mean scaled to all of them): an estimate, as the sampling is."""
    rows_a, rows_b = rows
    open_a = [r for r in rows_a if not r.matched]
    open_b = [r for r in rows_b if not r.matched]
    total_area = sum(r.area for r in rows_a) + sum(r.area for r in rows_b)
    if not open_a and not open_b:
        return {"max": 0.0, "mean": 0.0}
    count = len(open_a) + len(open_b)
    if count > DEVIATION_FACES:
        keep_a = max(1, round(DEVIATION_FACES * len(open_a) / count)) if open_a else 0
        sides = (_spread(open_a, keep_a), _spread(open_b, max(1, DEVIATION_FACES - keep_a)))
        per_face = 1  # (the middle of each: a spread of faces says more than more points)
    else:
        sides = (open_a, open_b)
        per_face = max(1, min(9, budget // max(1, count)))
    worst = 0.0
    weighted = 0.0
    for rows_all, rows_open, other in ((open_a, sides[0], rows_b), (open_b, sides[1], rows_a)):
        distance = _Distances(other)
        picked_area = sum(r.area for r in rows_open)
        scale = sum(r.area for r in rows_all) / picked_area if picked_area > 0 else 1.0
        for row in rows_open:
            if per_face == 1 and row.samples is None:
                # (one point a face: its middle, not a whole grid sampled to keep one)
                points = [p for p, _n in _face_points(row.face, 1, row.full)] or row.points()
            else:
                points = row.points()
            if len(points) > per_face:
                step = len(points) / float(per_face)
                points = [points[int(i * step)] for i in range(per_face)]
            found = [d for d in (distance(p) for p in points) if math.isfinite(d)]
            if not found:
                continue
            worst = max(worst, max(found))
            weighted += scale * row.area * sum(found) / len(found)
    mean = weighted / total_area if total_area > 0 else 0.0
    return {"max": _r(worst), "mean": _r(mean)}


# -- finish ---------------------------------------------------------------------------------------
def finish(ref, target=None, keep_reference=False, keep_original=False):
    """The rebuild becomes the part: the rebuilt body takes the original's name, component
    and place; the original is deleted (keep_original: kept hidden, renamed "<name>
    (original)"); the reference goes (keep_reference: kept, hidden). Inside the caller's
    undo step. Returns the finished body."""
    from . import components, insert

    if not is_reference(ref) or not bodies.alive(ref):
        raise RebuildError("There is no rebuild to finish (start_rebuild makes one).")
    if not getattr(ref, "Shown", True):
        raise RebuildError(
            "The rebuild of %s is finished already (its reference was kept, hidden, to compare "
            "with later)." % (getattr(ref, "SourceLabel", "") or ref.Label)
        )
    doc = ref.Document
    target = target if target is not None else target_of(ref)
    if target is not None and not bodies.is_body(target):
        target = bodies.body_of(target)
    if target is None:
        raise RebuildError(
            "The rebuilt body of %s is gone: there is nothing to finish (start_rebuild again)."
            % (ref.SourceLabel or ref.Label)
        )
    if not bodies.has_solid(target):
        raise RebuildError(
            "%s is still empty: build the part first (describe_reference gives the plan)."
            % target.Label
        )
    source = source_of(ref)
    label = getattr(ref, "SourceLabel", "") or (source.Label if source is not None else "")
    report = {"followed": [], "kept_because": [], "kept_original": bool(keep_original)}
    if source is not None:
        container = components.container_of(source)
        if components.container_of(target) is not container:
            components.place(target, container, keep_position=True)
        _take_looks(source, target)
        place = _timeline_place(doc, source, target)
        # what used the original (joints, patterns, sketches on its faces...) follows the
        # rebuild; what cannot follow keeps the original, hidden (QA: deleting it took the
        # joints of a jointed part with it)
        users = []
        if not insert.is_mesh_body(source):
            from . import rebuild_links

            follow = rebuild_links.Follow(doc, source, target, ref).plan()
            follow.apply()
            report["followed"] = [o.Label for o in follow.moved]
        users = _still_used(doc, source, target, ref)
        if users and not keep_original:
            keep_original = True
            report["kept_because"] = users
        report["kept_original"] = bool(keep_original)
        if keep_original:
            new_label = "%s (original)" % label
            if insert.is_mesh_body(source):
                from . import mesh

                mesh.rename_body(source, new_label)
            else:
                source.Label = new_label
            bodies.set_shown(source, False)
        else:
            _delete_original(doc, source)
        if place is not None:
            place()
    FINISHED[ref.Name] = report
    if label:
        target.Label = label
    _HIDDEN.get(doc.Name, {}).pop(ref.Name, None)
    NOTES.pop(ref.Name, None)
    _KNOWN.pop((doc.Name, ref.Name), None)
    _notify("clear", ref, None)
    if keep_reference:
        ref.Shown = False
    else:
        doc.removeObject(ref.Name)
    bodies.set_shown(target, True)
    try:
        components.activate_body(target)
    except Exception:
        bodies.set_active_body(target)
    log(
        "rebuild: finished %s (original %s, reference %s)"
        % (
            target.Label,
            "kept" if keep_original else "deleted",
            "kept" if keep_reference else "removed",
        )
    )
    return target


FINISHED = {}  # reference name -> what its finish did: {"followed", "kept_because", ...}


def _still_used(doc, source, target, ref):
    """Words for what still needs the original after the links followed the rebuild (it is
    then kept, hidden): objects that link it, and steps of other bodies its extrudes drive."""
    from . import rebuild_links, timeline_ops

    out = []
    try:
        for obj in rebuild_links.still_used(doc, source, target, ref):
            out.append(obj.Label)
        own = rebuild_links.own_objects(source)
        for name in timeline_ops.followers(doc, own):
            obj = doc.getObject(name)
            if obj is not None and name not in own and obj.Label not in out:
                out.append(obj.Label)
    except Exception as exc:
        warn("rebuild: %s" % exc)
    return out


def _take_looks(source, target):
    """The original's material and appearance (an imported STEP's colours, kept by the
    faces' places) go to the rebuild: it is the same part."""
    try:
        from . import appearance

        mat = getattr(source, "ShapeMaterial", None)
        if mat is not None and "ShapeMaterial" in target.PropertiesList:
            if getattr(target.ShapeMaterial, "UUID", None) != getattr(mat, "UUID", None):
                target.ShapeMaterial = mat
                for step in target.Group:
                    if "ShapeMaterial" in step.PropertiesList:
                        step.ShapeMaterial = mat
        for prop in ("SciForgeUserMaterial", appearance.PROP):
            text = getattr(source, prop, "") if prop in source.PropertiesList else ""
            if text and getattr(target, prop, None) != text:
                bodies.add_prop(target, "App::PropertyString", prop, "Base", "", True)
                setattr(target, prop, text)
        if App.GuiUp:
            appearance.apply(target)
    except Exception as exc:
        warn("rebuild: the original's look was not taken over (%s)" % exc)


def _timeline_place(doc, source, target):
    """A function that puts the rebuild's steps where the original's stood in the timeline
    (whatever used the original comes after it there, as before), or None when they stay
    at the end (the history marker rolled back, or a step of the rebuild uses a step that
    came later than the original)."""
    from . import rebuild_links, timeline_ops

    try:
        if not timeline_ops.timeline(doc, deps=False).at_end:
            return None
        old = rebuild_links.own_objects(source)
        new = rebuild_links.own_objects(target)
        rows = [(obj, timeline_ops._key(obj)) for obj, _body in timeline_ops.steps(doc)]
        theirs = [k for obj, k in rows if obj.Name in old]
        ours = [obj for obj, _k in rows if obj.Name in new]  # (in the body's own order)
        if not theirs or not ours:
            return None
        low = min(theirs)
        later = [k for obj, k in rows if obj.Name not in old and obj.Name not in new and k > low]
        high = min(later) if later else None
        if high is not None and max(timeline_ops._key(o) for o in ours) < high:
            return None  # (already there)
        for obj in ours:
            for dep in obj.OutList:
                if dep.Name in new or not timeline_ops._is_step(dep):
                    continue
                if timeline_ops._key(dep) > low:
                    return None  # (it would come before a step it uses)
        keys = core.keys_between(len(ours), low, high)
    except Exception as exc:
        warn("rebuild: the rebuild stays at the end of the timeline (%s)" % exc)
        return None

    def apply():
        for obj, key in zip(ours, keys):
            try:
                if bodies.alive(obj):
                    timeline_ops._add_prop(
                        obj, "App::PropertyFloat", timeline_ops.RANK, "Place in the design timeline"
                    )
                    setattr(obj, timeline_ops.RANK, float(key))
            except Exception as exc:
                warn("rebuild: %s keeps its place in the timeline (%s)" % (obj.Label, exc))

    return apply


def _delete_original(doc, source):
    """The original body (with its imported shape) or mesh body, gone."""
    from . import insert, timeline_ops

    if insert.is_mesh_body(source):
        from . import mesh

        try:
            mesh.delete_body(source)
        except Exception:
            doc.removeObject(source.Name)
        return
    bases = [getattr(source, "BaseFeature", None)]
    for step in source.Group:  # an Insert STEP step's imported shape (outside the body)
        if "BaseFeature" in step.PropertiesList:
            bases.append(getattr(step, "BaseFeature", None))
    bases = [b for b in bases if b is not None and bodies.body_of(b) is None]
    timeline_ops.delete_bodies(doc, [source.Name], transaction=False)
    for base in bases:
        if not bodies.alive(base):
            continue
        # a component holding it is no use of it (QA: the imported shape stayed behind in
        # the component, a stray "Body001 (imported)" step in the timeline)
        users = [
            u for u in base.InList if bodies.alive(u) and not u.hasExtension("App::GroupExtension")
        ]
        if not users:
            try:
                for holder in base.InList:
                    if bodies.alive(holder) and hasattr(holder, "removeObject"):
                        holder.removeObject(base)
                doc.removeObject(base.Name)
            except Exception as exc:
                warn("rebuild: the original's imported shape stays (%s)" % exc)


# -- the window ----------------------------------------------------------------------------------
def _notify(event, ref, data):
    for fn in list(LISTENERS):
        try:
            fn(event, ref, data)
        except Exception as exc:
            warn("rebuild: %s" % exc)


def sync(doc):
    """After an undo / redo: the original of every rebuild in progress is hidden, and an
    original whose rebuild was taken back is shown again (FreeCAD's undo does not record
    what is shown)."""
    if doc is None:
        return
    try:
        hidden = _HIDDEN.setdefault(doc.Name, {})
        live = {r.Name: r for r in references(doc)}
        for ref_name, source_name in list(hidden.items()):
            if ref_name in live and getattr(live[ref_name], "Shown", True):
                continue
            hidden.pop(ref_name, None)
            source = doc.getObject(source_name)
            if source is not None and ref_name not in live:
                bodies.set_shown(source, True)
        for ref in live.values():
            if not getattr(ref, "Shown", True) or target_of(ref) is None:
                continue
            source = source_of(ref)
            if source is not None:
                bodies.set_shown(source, False)
                hidden[ref.Name] = source.Name
    except Exception as exc:
        warn("rebuild: %s" % exc)


class _Watch:
    def slotUndoDocument(self, doc):
        sync(doc)

    def slotRedoDocument(self, doc):
        sync(doc)

    def slotDeletedDocument(self, doc):
        try:
            _HIDDEN.pop(doc.Name, None)
            forget(doc)
        except Exception:
            pass


_WATCH = {"on": None}


def install():
    """Watch undo / redo for the originals' visibility (once)."""
    if _WATCH["on"] is not None:
        return
    try:
        _WATCH["on"] = _Watch()
        App.addDocumentObserver(_WATCH["on"])
    except Exception as exc:
        _WATCH["on"] = None
        warn("rebuild: undo is not watched (%s)" % exc)


install()

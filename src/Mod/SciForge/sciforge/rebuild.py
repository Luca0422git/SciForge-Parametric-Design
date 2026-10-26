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
    """The reference made from `obj` or rebuilt into it (a body or mesh), or None."""
    if obj is None:
        return None
    for ref in references(obj.Document):
        if obj.Name in (getattr(ref, "SourceName", ""), getattr(ref, "TargetName", "")):
            return ref
    return None


def active_references(doc):
    """The references still being worked on (drawn; Finish with keep keeps one hidden)."""
    return [r for r in references(doc) if getattr(r, "Shown", True)]


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
    passes to the tools)."""
    from . import recognize

    shape = in_frame(reference_shape(ref), frame(ref))
    return recognize.describe(shape, options or {})


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
    reference = in_frame(reference_shape(ref), place)
    tol = float(opts["tolerance"] or getattr(ref, "Tolerance", 0.0) or core.FACE_TOL)
    mesh = getattr(ref, "SourceKind", "") == "mesh"
    v_ref = _volume(reference)
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
                "reference": len(reference.Faces),
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
    common, missing, extra, method = _pieces(reference, rebuilt)
    if method == "sampled":
        v_common, v_missing, v_extra = common, missing, extra
        missing_solids, extra_solids = [], []
    else:
        v_common = sum(s.Volume for s in common)
        missing_solids, extra_solids = missing, extra
        v_missing = sum(s.Volume for s in missing)
        v_extra = sum(s.Volume for s in extra)
    union = v_ref + v_new - v_common
    match = max(0.0, min(1.0, v_common / union)) if union > 1e-12 else 0.0
    regions_missing = [_region(s, "missing", rebuilt, tol, opts) for s in missing_solids]
    regions_extra = [_region(s, "extra", rebuilt, tol, opts) for s in extra_solids]
    regions_missing = [r for r in regions_missing if r is not None]
    regions_extra = [r for r in regions_extra if r is not None]
    faces = _match_faces(reference, rebuilt, tol, mesh, opts)
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
            "OpenCASCADE's boolean failed on these solids, so the volumes were measured by "
            "sampling points (about 1 % exact) and the regions are not listed."
        )
    if opts.get("show", True):
        _notify(
            "compare",
            ref,
            {
                "missing": [out_of_frame(s, place) for s in missing_solids],
                "extra": [out_of_frame(s, place) for s in extra_solids],
                "done": result["done"],
            },
        )
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


def _volume(shape):
    try:
        return sum(s.Volume for s in shape.Solids)
    except Exception:
        return 0.0


def _bbox(shape):
    box = shape.BoundBox
    return [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]


def _pieces(a, b):
    """(common solids, missing solids, extra solids, method): a split of both solids by each
    other (OpenCASCADE's General Fuse), each piece put where a point inside it lies. Checked:
    the pieces must add up to both volumes; else again with a fuzzy tolerance; else the
    volumes are sampled: (common, missing, extra volumes, "sampled")."""
    v_a, v_b = _volume(a), _volume(b)
    scale = max(1.0, v_a, v_b)
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
            if abs(piece.Volume) <= 1e-7 * scale:
                # a sliver between faces that lie on each other within a hair (a mesh's facets
                # and their copies): no material either side, only rounding
                noise += abs(piece.Volume)
                continue
            point = _inside_point(piece)
            if point is None:
                ok = False
                break
            in_a = a.isInside(point, 1e-9, True)
            in_b = b.isInside(point, 1e-9, True)
            if in_a and in_b:
                common.append(piece)
            elif in_a:
                missing.append(piece)
            elif in_b:
                extra.append(piece)
        if not ok:
            continue
        v_c = sum(s.Volume for s in common)
        v_m = sum(s.Volume for s in missing)
        v_e = sum(s.Volume for s in extra)
        slack = 1e-6 * scale + noise
        if abs(v_c + v_m - v_a) <= slack and abs(v_c + v_e - v_b) <= slack:
            return common, _merge(missing), _merge(extra), "exact" if not fuzzy else "fuzzy"
        log(
            "rebuild: the pieces do not add up (%.6g + %.6g vs %.6g; %.6g + %.6g vs %.6g)"
            % (v_c, v_m, v_a, v_c, v_e, v_b)
        )
    common, missing, extra = _sampled(a, b)
    return common, missing, extra, "sampled"


def _merge(solids):
    """Pieces that touch along a face are one region (a General Fuse can split a region where
    a face of the other solid ends inside it)."""
    if len(solids) < 2:
        return solids
    groups = []
    for solid in solids:
        joined = [g for g in groups if any(_touch(solid, other) for other in g)]
        merged = [solid]
        for g in joined:
            merged.extend(g)
            groups.remove(g)
        groups.append(merged)
    out = []
    for g in groups:
        if len(g) == 1:
            out.append(g[0])
            continue
        try:
            fused = g[0].fuse(g[1:]).removeSplitter()
            out.extend(fused.Solids if fused.Solids else g)
        except Exception:
            out.extend(g)
    return out


def _touch(a, b):
    if not _boxes_near(a.BoundBox, b.BoundBox, 1e-7):
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


def _face_points(face, n):
    """[(point, outward normal)] at the centres of an n x n grid of the face's parameters
    that lie on the face."""
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
                if face.isPartOfDomain(u, v):
                    out.append((face.valueAt(u, v), face.normalAt(u, v)))
            except Exception:
                continue
    return out


def _sampled(a, b, count=20000):
    """(common, missing, extra) volumes from points on a grid over both solids' box (the
    fallback when booleans fail)."""
    box = App.BoundBox(a.BoundBox)
    box.add(b.BoundBox)
    n = max(4, int(round(count ** (1.0 / 3.0))))
    dx, dy, dz = box.XLength / n, box.YLength / n, box.ZLength / n
    cell = dx * dy * dz
    common = missing = extra = 0.0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                p = App.Vector(
                    box.XMin + (i + 0.5) * dx, box.YMin + (j + 0.5) * dy, box.ZMin + (k + 0.5) * dz
                )
                in_a = a.isInside(p, 1e-7, True)
                in_b = b.isInside(p, 1e-7, True)
                if in_a and in_b:
                    common += cell
                elif in_a:
                    missing += cell
                elif in_b:
                    extra += cell
    return common, missing, extra


# -- regions ----------------------------------------------------------------------------------
def _xyz(v, digits=6):
    return [_r(v.x, digits), _r(v.y, digits), _r(v.z, digits)]


def _r(value, digits=6):
    out = round(float(value), digits)
    return 0.0 if out == 0 else out


def region_facts(solid):
    """The plain numbers rebuild_core classifies a region of material by."""
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
        "volume": solid.Volume,
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


def _region(solid, side, rebuilt, tol, opts):
    """One region of missing / extra material: its numbers, what it looks like, and the tool
    call that would make it when that is certain (fillet / chamfer the edges found)."""
    try:
        facts = region_facts(solid)
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
    if side == "extra" and shape["kind"] in ("fillet", "chamfer") and opts.get("selectors"):
        try:
            fix = _edge_fix(solid, shape, rebuilt, tol)
            if fix:
                row["fix"] = fix
        except Exception as exc:
            log("rebuild: no edge selector for a %s (%s)" % (shape["kind"], exc))
    if shape["kind"] in ("cylinder", "stepped_cylinder"):
        for f in facts["faces"]:
            if f.get("type") == "cylinder" and f.get("ends"):
                shape["ends"] = f["ends"]
                break
        if side == "extra" and shape["kind"] == "cylinder" and opts.get("selectors"):
            try:
                fix = _hole_fix(shape, rebuilt, tol)
                if fix:
                    row["fix"] = fix
            except Exception as exc:
                log("rebuild: no hole call for a region (%s)" % exc)
    return row


def _hole_fix(shape, rebuilt, tol):
    """A hole the rebuild has not cut: a Single Hole call on the flat face it starts on
    (through_all when it comes out on the other side too)."""
    from .ai import geometry_facts

    ends = shape.get("ends")
    if not ends:
        return None
    axis = App.Vector(*shape["axis"])
    found = []
    for end in ends:
        point = App.Vector(*end)
        hit = None
        for i, face in enumerate(rebuilt.Faces, start=1):
            if face.Surface.TypeId != "Part::GeomPlane":
                continue
            try:
                u0, u1, v0, v1 = face.ParameterRange
                normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
                if abs(abs(normal.dot(axis)) - 1.0) > 1e-6:
                    continue
                if face.isInside(point, max(tol, 1e-6), True):
                    hit = ("Face%d" % i, normal, point)
                    break
            except Exception:
                continue
        found.append(hit)
    starts = [h for h in found if h is not None]
    if not starts:
        return None
    name, _normal, point = starts[0]
    refs = geometry_facts.stable_refs(rebuilt, "faces", {name})
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


def _edge_fix(solid, shape, rebuilt, tol):
    """The rebuilt part's sharp edges a missing fillet / chamfer sits on, as a fillet /
    chamfer call: {"tool", "args": {"edges": selector, "radius" | "distance"}}."""
    import Part

    from .ai import geometry_facts

    names = []
    box = solid.BoundBox
    for i, edge in enumerate(rebuilt.Edges, start=1):
        try:
            mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
        except Exception:
            continue
        if not (
            box.XMin - tol <= mid.x <= box.XMax + tol
            and box.YMin - tol <= mid.y <= box.YMax + tol
            and box.ZMin - tol <= mid.z <= box.ZMax + tol
        ):
            continue
        try:
            if solid.distToShape(Part.Vertex(mid))[0] > max(tol, 1e-6):
                continue
            # the sharp edge runs along the strip: both its ends are on the region too
            ends = [v.Point for v in edge.Vertexes]
            if ends and any(solid.distToShape(Part.Vertex(p))[0] > max(tol, 1e-6) for p in ends):
                continue
        except Exception:
            continue
        names.append("Edge%d" % i)
    if not names:
        return None
    refs = geometry_facts.stable_refs(rebuilt, "edges", set(names))
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

    __slots__ = ("index", "face", "kind", "area", "box", "key", "matched", "samples", "grid")

    def __init__(self, index, face, grid=5):
        from .ai.ops import selectors

        self.index = index
        self.face = face
        self.kind = selectors.face_type(face)
        self.area = face.Area
        self.box = face.BoundBox
        self.key = None
        self.matched = False
        self.samples = None
        self.grid = grid
        surface = face.Surface
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
        except Exception:
            self.key = None

    def points(self):
        if self.samples is None:
            found = [p for p, _n in _face_points(self.face, self.grid)]
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


def _face_rows(shape):
    """The faces' rows; small faces get fewer sample points (a mesh's narrow facets)."""
    faces = list(shape.Faces)
    biggest = max([f.Area for f in faces] or [0.0])
    return [_FaceRow(i, f, 5 if f.Area >= 0.02 * biggest else 3) for i, f in enumerate(faces)]


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
                if other.face.isInside(p, tol, True):
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


def _match_faces(reference, rebuilt, tol, mesh, opts):
    """Faces of the original and of the rebuild matched by geometry: on the same surface
    (type, plane / axis / radius within tol, facing the same way) and covering each other
    (every sample point of one lies on the other). A reference made from a mesh is flat
    facets: there a face is matched when all its sample points lie within tol of the other
    part's surface."""
    rows_a = _face_rows(reference)
    rows_b = _face_rows(rebuilt)
    if mesh:
        # the exact test first (the mesh's flat faces are exact planes), then within tol of
        # the other part's surface for the facets of round regions and the round faces
        for mine, theirs in ((rows_a, rows_b), (rows_b, rows_a)):
            for row in mine:
                same = [
                    o
                    for o in theirs
                    if _boxes_near(row.box, o.box, tol) and _same_surface(row, o, tol)
                ]
                row.matched = _covered(row, same, tol) or _near_surfaces(row, theirs, tol)
    else:
        for mine, theirs in ((rows_a, rows_b), (rows_b, rows_a)):
            for row in mine:
                same = [
                    o
                    for o in theirs
                    if _boxes_near(row.box, o.box, tol) and _same_surface(row, o, tol)
                ]
                row.matched = _covered(row, same, tol)
                if not row.matched and row.key is None:
                    row.matched = _on_surfaces(row, theirs, tol)
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
        else:
            import Part

            return row.face.distToShape(Part.Vertex(point))[0] <= tol
        return row.face.isInside(foot, tol, True)
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
            refs = geometry_facts.stable_refs(shape, "faces", wanted)
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
def _deviation(rows, budget=400):
    """How far the surfaces are apart: sample points of the unmatched faces of each part,
    their exact distance to the other part (matched faces count 0). max and an
    area-weighted mean, mm."""
    rows_a, rows_b = rows
    open_a = [r for r in rows_a if not r.matched]
    open_b = [r for r in rows_b if not r.matched]
    total_area = sum(r.area for r in rows_a) + sum(r.area for r in rows_b)
    if not open_a and not open_b:
        return {"max": 0.0, "mean": 0.0}
    per_face = max(1, min(9, budget // max(1, len(open_a) + len(open_b))))
    worst = 0.0
    weighted = 0.0
    for rows_open, other in ((open_a, rows_b), (open_b, rows_a)):
        distance = _Distances(other)
        for row in rows_open:
            points = row.points()
            if len(points) > per_face:
                step = len(points) / float(per_face)
                points = [points[int(i * step)] for i in range(per_face)]
            found = [d for d in (distance(p) for p in points) if math.isfinite(d)]
            if not found:
                continue
            worst = max(worst, max(found))
            weighted += row.area * sum(found) / len(found)
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
    if source is not None:
        container = components.container_of(source)
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
        if components.container_of(target) is not container:
            components.place(target, container, keep_position=True)
    if label:
        target.Label = label
    _HIDDEN.get(doc.Name, {}).pop(ref.Name, None)
    NOTES.pop(ref.Name, None)
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
    base = getattr(source, "BaseFeature", None)
    timeline_ops.delete_bodies(doc, [source.Name], transaction=False)
    if base is not None and bodies.alive(base):
        users = [u for u in base.InList if bodies.alive(u)]
        if not users:
            try:
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

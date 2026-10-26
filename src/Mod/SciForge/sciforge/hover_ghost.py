# SPDX-License-Identifier: LGPL-2.1-or-later
"""A faint, see-through ghost of a hidden body while its browser row is hovered (Luca,
2026-10-26: "If i hover over a body in the browser that is hidden, I should get a preview of
that body in the workspace. A ghost body if you will.").

The browser lights a shown body up through FreeCAD's preselection, which only colours what
is drawn. A hidden body, component or mesh body gets a temporary Coin node instead: its
faces, light blue and see-through, unclickable, in the 3D view's scene graph. Nothing else
changes: no document or view property is touched (FreeCAD records those in the undo history
and in the file). A body the timeline marker stands before has no solid there and gets no
ghost; neither does a component the marker hid. The tessellation is kept per object until
its shape or place changes, so hovering up and down a big design stays quick.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import warn

COLOUR = (0.45, 0.62, 0.92)
TRANSPARENCY = 0.72
DEFLECTION = 0.002  # of the shape's size: coarse is fine for a ghost
_STATE = {"node": None, "view": None, "object": None}
_CACHE = {}  # (document, object) -> (key, coin node)
_LIMIT = 40


def current():
    """The object whose ghost is shown, or None (tests)."""
    return _STATE["object"]


def node():
    """The ghost's Coin node in the scene graph, or None (tests)."""
    return _STATE["node"]


def _rolled_back(obj):
    try:
        from . import timeline_ops

        return bool(getattr(obj, timeline_ops.ROLLED_HIDDEN, False))
    except Exception:
        return False


def _visible(obj):
    try:
        return obj.ViewObject is not None and bool(obj.ViewObject.Visibility)
    except Exception:
        return False


def _placed(obj):
    """(shape or mesh in design coordinates, key) of one solid thing, or (None, None)."""
    try:
        place = obj.getGlobalPlacement()
    except Exception:
        place = App.Placement()
    if obj.TypeId == "PartDesign::Body" and getattr(obj, "Tip", None) is None:
        return None, None  # the marker stands before its first step: nothing exists yet
    mesh = getattr(obj, "Mesh", None)
    if mesh is not None and obj.isDerivedFrom("Mesh::Feature"):
        copy = mesh.copy()
        copy.Placement = place
        return copy, ("mesh", obj.Name, mesh.CountFacets, tuple(place.toMatrix().A))
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or not (shape.Faces or shape.Solids):
        return None, None
    copy = shape.copy()
    copy.Placement = place
    return copy, ("shape", obj.Name, shape.hashCode(), tuple(place.toMatrix().A))


def _pieces(obj):
    """The solid things a ghost of `obj` shows: a body, a mesh body, a solid, or each one
    of them inside a component."""
    if obj.TypeId == "App::Part":
        found = []
        for child in obj.OutListRecursive:
            if child.TypeId == "PartDesign::Body" or child.isDerivedFrom("Mesh::Feature"):
                found.append(child)
            elif child.isDerivedFrom("Part::Feature") and child.getParentGeoFeatureGroup() in (
                obj,
                None,
            ):
                try:
                    from . import bodies

                    if bodies.body_of(child) is None and child.Shape.Solids:
                        found.append(child)
                except Exception:
                    pass
        return found
    return [obj]


def _faces(placed):
    """(points, triangles) of a shape or mesh."""
    if hasattr(placed, "Topology") and hasattr(placed, "CountFacets"):
        points, facets = placed.Topology
        return points, facets
    size = max(placed.BoundBox.DiagonalLength, 1e-3)
    return placed.tessellate(max(size * DEFLECTION, 0.01))


def placed_pieces(obj):
    """[shape or mesh in design coordinates] of what a ghost of `obj` shows (other ghosts
    use them too: a joint's limits, joints_limit_drag)."""
    out = []
    for piece in _pieces(obj):
        shape, _key = _placed(piece)
        if shape is not None:
            out.append(shape)
    return out


def build(pieces, colour=COLOUR, transparency=TRANSPARENCY):
    """A see-through, unclickable Coin node of placed shapes / meshes (not yet in a view; the
    caller adds it to a scene graph and takes it out again), or None."""
    return _build(pieces, colour, transparency)


def _build(pieces, colour=COLOUR, transparency=TRANSPARENCY):
    from pivy import coin

    sep = coin.SoSeparator()
    sep.setName("SciForgeHoverGhost")
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    sep.addChild(pick)
    hints = coin.SoShapeHints()
    hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
    hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
    sep.addChild(hints)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*colour)
    material.emissiveColor.setValue(*(c * 0.35 for c in colour))
    material.transparency.setValue(transparency)
    sep.addChild(material)
    drawn = 0
    for placed in pieces:
        points, triangles = _faces(placed)
        if not points or not triangles:
            continue
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
        index = []
        for tri in triangles:
            index += [int(tri[0]), int(tri[1]), int(tri[2]), -1]
        faces = coin.SoIndexedFaceSet()
        faces.coordIndex.setValues(0, len(index), index)
        group = coin.SoSeparator()
        group.addChild(coords)
        group.addChild(faces)
        sep.addChild(group)
        drawn += 1
    return sep if drawn else None


def _ghost_of(obj):
    """The Coin node of `obj`'s ghost (kept until its shapes or places change), or None."""
    placed, keys = [], []
    for piece in _pieces(obj):
        if piece is not obj and obj.TypeId == "App::Part" and _rolled_back(piece):
            continue
        shape, key = _placed(piece)
        if shape is not None:
            placed.append(shape)
            keys.append(key)
    if not placed:
        return None
    key = tuple(keys)
    memo = (obj.Document.Name, obj.Name)
    found = _CACHE.get(memo)
    if found is not None and found[0] == key:
        return found[1]
    built = _build(placed)
    if built is None:
        return None
    built.ref()  # kept alive between hovers (the cache owns it)
    if found is not None:
        try:
            found[1].unref()
        except Exception:
            pass
    _CACHE[memo] = (key, built)
    if len(_CACHE) > _LIMIT:
        old = next(iter(_CACHE))
        if old != memo:
            try:
                _CACHE.pop(old)[1].unref()
            except Exception:
                pass
    return built


def wanted(obj):
    """True when hovering `obj`'s row shows a ghost: a hidden body, component, mesh body or
    loose solid that exists at the marker's place."""
    try:
        if obj is None or obj.Document is None or _visible(obj) or _rolled_back(obj):
            return False
        if obj.TypeId in ("PartDesign::Body", "App::Part"):
            return True
        if obj.isDerivedFrom("Mesh::Feature"):
            return True
        if obj.isDerivedFrom("Part::Feature") and obj.getParentGeoFeatureGroup() is None:
            from . import bodies

            return bodies.body_of(obj) is None and bool(obj.Shape.Solids)
    except Exception:
        return False
    return False


def show(obj):
    """Show `obj`'s ghost (and no other) when it is wanted; hide any ghost otherwise. Never
    raises."""
    try:
        if obj is not None and obj is _STATE["object"] and _STATE["node"] is not None:
            return
        hide()
        if not wanted(obj):
            return
        gdoc = Gui.getDocument(obj.Document.Name)
        view = gdoc.ActiveView if gdoc is not None else None
        if view is None or not hasattr(view, "getSceneGraph"):
            return
        ghost = _ghost_of(obj)
        if ghost is None:
            return
        view.getSceneGraph().addChild(ghost)
        _STATE.update(node=ghost, view=view, object=obj)
    except Exception as exc:
        warn("hover ghost: %s" % exc)


def hide():
    """Take the ghost out of the 3D view, if one is shown. Never raises."""
    ghost, view = _STATE["node"], _STATE["view"]
    _STATE.update(node=None, view=None, object=None)
    if ghost is None or view is None:
        return
    try:
        view.getSceneGraph().removeChild(ghost)
    except Exception:
        pass


def forget(doc_name=None):
    """Drop the kept ghosts (of one document, or all)."""
    hide()
    for memo in [m for m in _CACHE if doc_name is None or m[0] == doc_name]:
        try:
            _CACHE.pop(memo)[1].unref()
        except Exception:
            pass

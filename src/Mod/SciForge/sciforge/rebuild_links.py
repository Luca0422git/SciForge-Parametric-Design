# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline: at Finish, what used the original body follows the rebuilt body. No Qt.
(Beta 3 QA; rebuild.finish calls it. Spec: docs/sciforge/parity/auto-timeline.md, Finish.)

A VEX team rebuilds imported parts that are already jointed, patterned or drawn. Deleting the
original took every joint on it with it (joints.remove_joints_of: Fusion deletes a deleted
component's joints) and every step that used one of its faces lost that face. So Finish first
moves those links over to the rebuilt body:

* every link property of every other object (joints, grounds, rigid groups, contact sets,
  patterns of bodies, construction planes, sketches on its faces, extrudes up to it,
  drawings, studies...) that points at the original body or at a step in it points at the
  rebuilt body (or at its last step) instead, each face / edge / corner name swapped for the
  rebuild's element on the same geometry (the rebuild matches the original face for face);
* a link that reaches the body through its component ("Body001.Face7" in a joint) gets the
  body's name in its path swapped the same way;
* a joint's own record of its snap (the element, the faces or edges of a Between Two Faces
  or Two Edge Intersection origin) is swapped too, so its origin lands where it was.

What cannot follow (a link to the original's sketch, or to a face the rebuild does not have
because it was finished while different; a step in the rebuild itself that uses the
original) stays on the original: Finish then keeps the original, hidden, instead of
deleting it, and says why.
"""

import json
import re

import FreeCAD as App

from . import bodies, warn
from . import rebuild_core as core

_ELEMENT = re.compile(r"^(Face|Edge|Vertex)\d+$")
# a container's own children and a body's internals: never "a use" of the original
_SKIP_PROPS = ("Group", "Tip", "Origin", "OriginFeatures", "ExpressionEngine", "_GroupTouched")


def _link_props(obj):
    out = []
    for prop in obj.PropertiesList:
        if prop in _SKIP_PROPS:
            continue
        try:
            kind = obj.getTypeIdOfProperty(prop)
        except Exception:
            continue
        if kind.startswith(("App::PropertyLink", "App::PropertyXLink")):
            out.append((prop, kind))
    return out


# -- the rebuild's element on the same geometry ------------------------------------------------
class Elements:
    """old element name ("Face3", "Edge7", "Vertex2") of a shape of the original -> the
    rebuilt shape's element on the same geometry, or None. Both shapes in design
    coordinates; each name is worked out once, when it is asked for."""

    def __init__(self, old, new, tol=1e-3):
        self.old = old
        self.new = new
        self.tol = tol
        self.found = {}
        self._rows = None

    def __call__(self, name):
        if name in self.found:
            return self.found[name]
        try:
            if name.startswith("Face"):
                out = self._face(name)
            elif name.startswith("Edge"):
                out = self._edge(name)
            elif name.startswith("Vertex"):
                out = self._vertex(name)
            else:
                out = None
        except Exception as exc:
            warn("rebuild: %s not followed (%s)" % (name, exc))
            out = None
        self.found[name] = out
        return out

    def _face(self, name):
        from . import rebuild

        old = self.old.getElement(name)
        if self._rows is None:
            self._rows = rebuild._face_rows(self.new)
        row = rebuild._FaceRow(0, old)
        same = [o for o in self._rows if rebuild._same_surface(row, o, self.tol)]
        if not same:
            return None
        for other in same:  # the same face (the usual case: the rebuild matches face for face)
            if abs(other.area - row.area) <= 1e-6 * max(1.0, row.area) and rebuild._same_box(
                row.box, other.box, self.tol
            ):
                return "Face%d" % (other.index + 1)
        points = row.points()
        best, hits = None, 0
        for other in same:  # a face split another way: the one holding most of its points
            count = sum(1 for p in points if rebuild._on_face(other, p, self.tol))
            if count > hits:
                best, hits = other, count
        return "Face%d" % (best.index + 1) if best is not None else None

    def _edge(self, name):
        import Part

        old = self.old.getElement(name)
        kind = _curve_kind(old)
        mid = old.valueAt(0.5 * (old.FirstParameter + old.LastParameter))
        ends = [v.Point for v in old.Vertexes]
        tol = self.tol
        holding = []
        probe = Part.Vertex(mid)
        for i, edge in enumerate(self.new.Edges):
            if _curve_kind(edge) != kind or not _near_box(edge.BoundBox, mid, tol):
                continue
            try:
                if edge.distToShape(probe)[0] > tol:
                    continue
            except Exception:
                continue
            theirs = [v.Point for v in edge.Vertexes]
            same_ends = len(theirs) == len(ends) and all(
                any((a - b).Length <= tol for b in theirs) for a in ends
            )
            if same_ends and abs(edge.Length - old.Length) <= tol:
                return "Edge%d" % (i + 1)
            holding.append((abs(edge.Length - old.Length), i))
        if holding:  # an edge split another way: the closest in length that holds its middle
            return "Edge%d" % (min(holding)[1] + 1)
        return None

    def _vertex(self, name):
        point = self.old.getElement(name).Point
        best = None
        for i, v in enumerate(self.new.Vertexes):
            d = (v.Point - point).Length
            if d <= self.tol and (best is None or d < best[0]):
                best = (d, i)
        return "Vertex%d" % (best[1] + 1) if best is not None else None


def _curve_kind(edge):
    try:
        kind = edge.Curve.TypeId
    except Exception:
        return "?"
    return "line" if kind in ("Part::GeomLine", "Part::GeomLineSegment") else kind


def _near_box(box, p, tol):
    return (
        box.XMin - tol <= p.x <= box.XMax + tol
        and box.YMin - tol <= p.y <= box.YMax + tol
        and box.ZMin - tol <= p.z <= box.ZMax + tol
    )


# -- what belongs to which body ------------------------------------------------------------------
def own_objects(body):
    """Names of the objects that are part of a body: itself, its steps, its origin and its
    datums, the imported shape it is based on."""
    names = {body.Name}
    for obj in list(getattr(body, "Group", []) or []):
        names.add(obj.Name)
        base = getattr(obj, "BaseFeature", None) if "BaseFeature" in obj.PropertiesList else None
        if base is not None and bodies.body_of(base) is None:
            names.add(base.Name)  # (an Insert STEP step's imported shape)
    origin = getattr(body, "Origin", None)
    if origin is not None:
        names.add(origin.Name)
        for feature in getattr(origin, "OriginFeatures", []) or []:
            names.add(feature.Name)
    base = getattr(body, "BaseFeature", None)
    if base is not None:
        names.add(base.Name)
    return names


class Follow:
    """The plan of what follows the rebuild (worked out before anything changes), then
    apply(). changes: [(object, property, new value)]; stuck: [(object, why)]."""

    def __init__(self, doc, original, rebuilt, ref=None, tol=1e-3):
        self.doc = doc
        self.original = original
        self.rebuilt = rebuilt
        self.ref = ref
        self.tol = tol
        self.old_names = own_objects(original)
        self.new_names = own_objects(rebuilt)
        self.changes = []
        self.snaps = []  # (joint, property, new json text)
        self.stuck = []
        self.moved = []  # the objects that follow (each once)
        self._elements = {}
        self._swap_names = None

    # the rebuild's object for one of the original's
    def counterpart(self, obj):
        if obj is None:
            return None
        if obj is self.original:
            return self.rebuilt
        role = getattr(obj, "Role", "") if "Role" in obj.PropertiesList else ""
        if role:  # an origin plane / axis / point: the rebuild's of the same role
            origin = getattr(self.rebuilt, "Origin", None)
            for feature in getattr(origin, "OriginFeatures", []) or []:
                if getattr(feature, "Role", "") == role:
                    return feature
            return None
        if obj.TypeId == "App::Origin":
            return getattr(self.rebuilt, "Origin", None)
        if _is_solid_step(obj):
            tip = getattr(self.rebuilt, "Tip", None)
            return tip if tip is not None else self.rebuilt
        return None  # a sketch, a construction plane of its own...: nothing to follow to

    def elements(self, obj):
        """The element map for links to `obj` (the original or a solid step of it)."""
        key = obj.Name
        if key not in self._elements:
            try:
                old = bodies.global_shape(obj)
            except Exception:
                old = None
            new = bodies.global_shape(self.rebuilt)
            if old is None or old.isNull():
                self._elements[key] = lambda _name: None
            else:
                self._elements[key] = Elements(old, new, self.tol)
        return self._elements[key]

    def swap_names(self):
        """{old name: new name or ""} for a path through the original: the body's name
        swapped, a step inside it dropped (the rebuilt body holds the whole shape)."""
        if self._swap_names is None:
            names = {n: "" for n in self.old_names}
            names[self.original.Name] = self.rebuilt.Name
            self._swap_names = names
        return self._swap_names

    def _path_elements(self, sub):
        """The element map of a path through the original: from the deepest of its objects
        named in the path (the body, or a step in it)."""
        path, _element = core.split_sub(sub)
        deepest = self.original
        for name in path:
            if name in self.old_names and name != self.original.Name:
                obj = self.doc.getObject(name)
                if obj is not None and _is_solid_step(obj):
                    deepest = obj
        return self.elements(deepest)

    # -- one value ----------------------------------------------------------------------------
    def _one(self, obj, subs):
        """(new object, new subs, changed) for a link to obj with sub names; raises _Stuck."""
        subs = [s for s in (subs or [])]
        if obj is not None and obj.Name in self.old_names:
            new = self.counterpart(obj)
            if new is None:
                raise _Stuck("it uses %s of the original, which the rebuild has not" % obj.Label)
            if not subs:
                return new, subs, True
            mapped = core.rewrite_direct(subs, self.elements(obj))
            if mapped is None:
                raise _Stuck(
                    "it uses %s of the original, and the rebuild has no face, edge or corner "
                    "there" % ", ".join(core.split_sub(s)[1] for s in subs)
                )
            return new, mapped, True
        if obj is None or not subs:
            return obj, subs, False
        out, changed = [], False
        for sub in subs:
            text, moved = core.rewrite_sub(sub, self.swap_names(), self._path_elements(sub))
            if text is None:
                raise _Stuck(
                    "it uses %s of the original, and the rebuild has no face, edge or corner "
                    "there" % core.split_sub(sub)[1]
                )
            out.append(text)
            changed = changed or moved
        return obj, out, changed

    def _value(self, kind, value):
        """(new value, changed) of one link property; raises _Stuck."""
        if value is None:
            return value, False
        if isinstance(value, App.DocumentObject):
            new, _subs, changed = self._one(value, [])
            return new, changed
        if isinstance(value, tuple) and len(value) == 2 and _is_obj(value[0]):
            obj, subs = value
            single = isinstance(subs, str)
            new, out, changed = self._one(obj, [subs] if single else list(subs or []))
            if single:
                out = out[0] if out else ""
            return (new, out), changed
        if isinstance(value, (list, tuple)):
            items, changed = [], False
            for item in value:
                new, moved = self._value(kind, item)
                items.append(new)
                changed = changed or moved
            return (items if isinstance(value, list) else tuple(items)), changed
        return value, False

    # -- the whole design --------------------------------------------------------------------
    def plan(self):
        from . import rebuild

        for obj in list(self.doc.Objects):
            if obj.Name in self.old_names or (self.ref is not None and obj is self.ref):
                continue
            if rebuild.is_reference(obj):
                continue
            mine = obj.Name in self.new_names
            todo = []
            try:
                if _follows_original(obj, self.old_names):
                    # a step the original's extrude drives in another body: part of that
                    # extrude, it cannot follow (the original is kept for it)
                    raise _Stuck("it is a step of the original's own extrude in another body")
                for prop, kind in _link_props(obj):
                    try:
                        value = obj.getPropertyByName(prop)
                    except Exception:
                        continue
                    new, changed = self._value(kind, value)
                    if changed:
                        todo.append((prop, new))
                if todo and mine:
                    raise _Stuck("it is a step of the rebuild that uses the original itself")
                snaps = self._joint_snaps(obj) if todo else []
            except _Stuck as stuck:
                self.stuck.append((obj, str(stuck)))
                continue
            except Exception as exc:
                self.stuck.append((obj, "its links could not be read (%s)" % exc))
                continue
            if todo:
                self.changes += [(obj, prop, new) for prop, new in todo]
                self.snaps += snaps
                self.moved.append(obj)
        self._pattern_sources()
        return self

    def _joint_snaps(self, obj):
        """A joint's snap records for the sides that reach the original, with the element
        names swapped (raises _Stuck when one has no counterpart)."""
        from . import joints

        if not (joints.is_joint(obj) or joints.is_helper(obj)):
            return []
        out = []
        for index, prop in enumerate(("Reference1", "Reference2")):
            ref = getattr(obj, prop, None)
            if not ref or len(ref) < 2:
                continue
            subs = list(ref[1]) if not isinstance(ref[1], str) else [ref[1]]
            through = ref[0] is not None and ref[0].Name in self.old_names
            if subs and not through:
                path, _e = core.split_sub(subs[0])
                through = any(p in self.old_names for p in path)
            if not through:
                continue
            key = joints.PROPS["snap1" if index == 0 else "snap2"]
            record = joints._json(obj, key)
            if not record:
                continue
            element_for = (
                self.elements(ref[0])
                if ref[0].Name in self.old_names
                else self._path_elements(subs[0])
            )
            changed = False
            for field in ("element", "at"):
                name = record.get(field)
                if isinstance(name, str) and _ELEMENT.match(name):
                    new = element_for(name)
                    if not new:
                        raise _Stuck("its snap on %s has no counterpart in the rebuild" % name)
                    if new != name:
                        record[field] = new
                        changed = True
            for field in ("faces", "edges"):
                names = record.get(field)
                if isinstance(names, list):
                    new_names = []
                    for name in names:
                        new = element_for(name) if _ELEMENT.match(str(name)) else name
                        if not new:
                            raise _Stuck("its snap on %s has no counterpart in the rebuild" % name)
                        new_names.append(new)
                    if new_names != names:
                        record[field] = new_names
                        changed = True
            if changed:
                out.append((obj, key, json.dumps(record, sort_keys=True)))
        return out

    def _pattern_sources(self):
        """A pattern of bodies keeps the copied body's NAME (SourceBody) beside its link."""
        for obj in self.doc.Objects:
            if getattr(obj, "SourceBody", None) == self.original.Name and obj.Name not in (
                self.old_names
            ):
                self.changes.append((obj, "SourceBody", self.rebuilt.Name))
                if obj not in self.moved:
                    self.moved.append(obj)

    def apply(self):
        """Move the links (inside the caller's undo step)."""
        for obj, prop, new in self.changes:
            try:
                setattr(obj, prop, new)
            except Exception as exc:
                warn("rebuild: %s.%s did not follow the rebuild (%s)" % (obj.Label, prop, exc))
        for obj, prop, text in self.snaps:
            try:
                setattr(obj, prop, text)
            except Exception as exc:
                warn("rebuild: %s's snap did not follow the rebuild (%s)" % (obj.Label, exc))
        self._joint_places()
        self._assembly_records()

    def _joint_places(self):
        """The joints that follow find their origins again on the rebuilt body."""
        from . import joints

        for obj in self.moved:
            try:
                if not (joints.is_joint(obj) or joints.is_helper(obj)):
                    continue
                obj.Placement1 = obj.Proxy.findPlacement(obj, obj.Reference1, 0)
                obj.Placement2 = obj.Proxy.findPlacement(obj, obj.Reference2, 1)
            except Exception as exc:
                warn("rebuild: %s's origin was not found again (%s)" % (obj.Label, exc))

    def _assembly_records(self):
        """Where the joints put the parts is kept by each part's name (a body at the root of
        the design is a part of its own): the rebuild's name takes the original's."""
        from . import joints

        old, new = self.original.Name, self.rebuilt.Name
        for obj in self.doc.Objects:
            for key in (joints.PROPS["baseline"], joints.PROPS["placements"]):
                if key not in obj.PropertiesList:
                    continue
                record = joints._json(obj, key)
                if isinstance(record, dict) and old in record:
                    record[new] = record.pop(old)
                    joints._set_json(obj, key, record)


class _Stuck(Exception):
    pass


def _follows_original(obj, names):
    """A follower step (timeline_ops: a multi-body extrude's step in another body) led by a
    step of the original."""
    try:
        from . import timeline_ops

        if not timeline_ops.is_follower(obj):
            return False
        lead = getattr(obj, "Source", None)
        return lead is not None and lead.Name in names
    except Exception:
        return False


def _is_obj(value):
    return isinstance(value, App.DocumentObject)


def _is_solid_step(obj):
    """A step that holds the body's solid as it stands there (not a sketch or a datum)."""
    try:
        if obj.TypeId == "PartDesign::Body":
            return False
        if obj.isDerivedFrom("Part::Datum") or obj.TypeId.startswith("Sketcher::"):
            return False
        return obj.isDerivedFrom("Part::Feature") and not obj.Shape.isNull()
    except Exception:
        return False


def still_used(doc, original, rebuilt, ref=None):
    """The objects outside the original that still link it or a step in it (after the
    links followed): those keep the original from being deleted."""
    names = own_objects(original)
    from . import rebuild

    found = []
    for obj in doc.Objects:
        if obj.Name in names or obj is ref or rebuild.is_reference(obj):
            continue
        for prop, _kind in _link_props(obj):
            try:
                value = obj.getPropertyByName(prop)
            except Exception:
                continue
            if _reaches(value, names):
                found.append(obj)
                break
    return found


def _reaches(value, names):
    if value is None:
        return False
    if isinstance(value, App.DocumentObject):
        return value.Name in names
    if isinstance(value, tuple) and len(value) == 2 and _is_obj(value[0]):
        obj, subs = value
        if obj.Name in names:
            return True
        for sub in [subs] if isinstance(subs, str) else list(subs or []):
            path, _e = core.split_sub(sub)
            if any(p in names for p in path):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_reaches(v, names) for v in value)
    return False

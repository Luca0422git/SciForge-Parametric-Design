# SPDX-License-Identifier: LGPL-2.1-or-later
"""Snap points of a shape's faces and edges, from an index built once per shape, with the
centres of holes of any outline (SciForge). No Qt. The maths is hole_snaps_core.py; the
callers are joints._shape_snaps (Joint, Joint Origin, As-built Joint, Duplicate With Joints)
and align.snap_points (Align). Spec: docs/sciforge/parity/vex-assembly.md.

What a face or an edge offers (Fusion's keypoints, plus the holes):

- a face: its centre (centre of area for a flat face, a point on the axis for a cylinder),
  its corners, the middles of its straight edges, the centres of its round edges, and, on a
  flat face, the centre of every closed inner outline (a square, a hex, a slot, any shape:
  kind "loop", Z = the face's normal, X along the outline's longest straight side);
- a flat wall of a hole (a face that meets the outline of a hole in another face): the hole's
  centre where it starts (kind "hole_top", Z = that face's normal), half-way ("hole_mid") and
  where it ends ("hole_bottom", Z = the other side's normal);
- an edge: its circle's centre, the centre of the hole outline it belongs to, its middle and
  its ends.

Speed (VEX parts have hundreds of holes: a steel 1x5x1x35 C-channel has 1970 faces and 5904
edges): the old code looked every corner and edge of a face up by scanning the whole part
(0.15 s per edge there: minutes for the web face). Now names come from FreeCAD's own indexed
map of the shape (findSubShape, one call per face), each face's and edge's snaps are worked
out once and kept with the shape they came from (`index_for`: a shape keeps its index while
it is the same OpenCASCADE shape; a recompute makes a new one), and the callers only draw the
dots near the pointer.
"""

import FreeCAD as App

from . import hole_snaps_core as core

_CACHE = []  # [ShapeIndex], most recently used last
_LIMIT = 16
PLANE = "Part::GeomPlane"
LINE_TYPES = ("Part::GeomLine", "Part::GeomLineSegment")
WALL_EDGES = 12  # a hole's flat wall is a simple face with a few edges


def _t(v):
    return (float(v.x), float(v.y), float(v.z))


def _v(t):
    return App.Vector(t[0], t[1], t[2])


def _base(shape):
    """`shape` without its own placement: the same OpenCASCADE shape (nothing copied)."""
    import Part

    base = Part.Shape(shape)
    try:
        if not base.Placement.isIdentity():
            base.Placement = App.Placement()
    except Exception:
        pass
    return base


def index_for(shape):
    """The ShapeIndex of `shape` (made on first use, kept while the shape is the same)."""
    for i in range(len(_CACHE) - 1, -1, -1):
        idx = _CACHE[i]
        try:
            if idx.shape.isPartner(shape):
                if i != len(_CACHE) - 1:
                    _CACHE.append(_CACHE.pop(i))
                return idx
        except Exception:
            continue
    idx = ShapeIndex(_base(shape))
    _CACHE.append(idx)
    while len(_CACHE) > _LIMIT:
        _CACHE.pop(0)
    return idx


def forget():
    """Drop every index (tests; a document closed)."""
    del _CACHE[:]


def snaps(shape, element):
    """The snap points of `element` of `shape`, in the shape's coordinates (its placement
    included): new dicts {kind, at, point, z, hint[, loop]} the caller may change."""
    try:
        idx = index_for(shape)
        found = idx.snaps(element)
    except Exception:
        return []
    plc = shape.Placement
    moved = not plc.isIdentity()
    out = []
    for s in found:
        d = dict(s)
        if moved:
            d["point"] = plc.multVec(s["point"])
            if s["z"] is not None:
                d["z"] = plc.Rotation.multVec(s["z"])
            if s["hint"] is not None:
                d["hint"] = plc.Rotation.multVec(s["hint"])
        else:
            d["point"] = App.Vector(s["point"])
            if s["z"] is not None:
                d["z"] = App.Vector(s["z"])
            if s["hint"] is not None:
                d["hint"] = App.Vector(s["hint"])
        if "loop" in s:
            d["loop"] = _moved_loop(s["loop"], plc) if moved else dict(s["loop"])
        out.append(d)
    return out


def _moved_loop(loop, plc):
    out = dict(loop)
    out["c"] = _t(plc.multVec(_v(loop["c"])))
    out["n"] = _t(plc.Rotation.multVec(_v(loop["n"])))
    return out


def all_loops(shape):
    """Every closed inner outline of every flat face of `shape` (identity dicts {c, n, a, r,
    face, at}, the shape's coordinates without its placement)."""
    return index_for(shape).all_loops()


def refind(shape, record):
    """The snap a record of a hole snap ({"kind", "loop": {c, n, a, r}, ...}) means on the
    shape as it is now (after an edit): the same hole found by where it is, its size and
    direction. None when it is gone. In the shape's coordinates (placement included)."""
    loop = record.get("loop")
    if not loop or record.get("kind") not in core.HOLE_KINDS:
        return None
    plc = shape.Placement
    stored = _moved_loop(loop, plc.inverse()) if not plc.isIdentity() else loop
    idx = index_for(shape)
    found = idx.find_loop(stored)
    if found is None:
        return None
    snap = idx.snap_of_loop(found, record["kind"])
    if snap is None:
        return None
    s = dict(snap)
    if not plc.isIdentity():
        s["point"] = plc.multVec(snap["point"])
        s["z"] = plc.Rotation.multVec(snap["z"]) if snap["z"] is not None else None
        s["hint"] = plc.Rotation.multVec(snap["hint"]) if snap["hint"] is not None else None
    return s


def stored_snap(record, shape):
    """A hole snap where the record says the hole was (when the hole is gone: the joint
    stays where it was rather than jumping to some other point)."""
    loop = record.get("loop") or {}
    try:
        point = _v(loop["c"])
        z = _v(loop["n"])
        hint = _v(loop["x"]) if loop.get("x") else None
    except Exception:
        return None
    if record.get("kind") in (core.HOLE_MID, core.HOLE_BOTTOM) and loop.get("depth"):
        depth = float(loop["depth"])
        point = point - z * (depth * (0.5 if record["kind"] == core.HOLE_MID else 1.0))
        if record["kind"] == core.HOLE_BOTTOM:
            z = z * -1
    plc = shape.Placement
    if not plc.isIdentity():
        point = plc.multVec(point)
        z = plc.Rotation.multVec(z)
        hint = plc.Rotation.multVec(hint) if hint is not None else None
    return {
        "kind": record.get("kind"),
        "at": record.get("at", ""),
        "point": point,
        "z": z,
        "hint": hint,
    }


# -- the index -------------------------------------------------------------------------------------
class ShapeIndex:
    """What one shape offers, worked out once: snaps per face / edge, its holes."""

    def __init__(self, shape):
        self.shape = shape
        self._snaps = {}
        self._face_loops = {}
        self._edge_faces = {}
        self._all = None

    # -- names ---------------------------------------------------------------------------------
    def names(self, subs, kind):
        """Element names ("Edge12") of sub-shapes of this shape, in one call."""
        if not subs:
            return []
        try:
            found = self.shape.findSubShape(list(subs))
        except Exception:
            found = []
        out = []
        for entry in found:
            try:
                typ, i = entry
                out.append("%s%d" % (kind, i) if i else "")
            except Exception:
                out.append("")
        while len(out) < len(subs):
            out.append("")
        return out

    def element(self, name):
        try:
            return self.shape.getElement(name)
        except Exception:
            return None

    # -- snaps -----------------------------------------------------------------------------------
    def snaps(self, element):
        if element in self._snaps:
            return self._snaps[element]
        if element.startswith("Face"):
            found = self._face_snaps(element)
        elif element.startswith("Edge"):
            found = self._edge_snaps(element)
        elif element.startswith("Vertex"):
            v = self.element(element)
            found = [] if v is None else [_snap("vertex", element, v.Point, None, None)]
        else:
            found = []
        self._snaps[element] = found
        return found

    def _face_snaps(self, element):
        from . import joints

        face = self.element(element)
        if face is None:
            return []
        centre, z, hint = joints._face_frame(face)
        out = [_snap("centre", element, centre, z, hint)]
        vertexes = face.Vertexes
        for v, name in zip(vertexes, self.names(vertexes, "Vertex")):
            if name:
                out.append(_snap("vertex", name, v.Point, z, hint))
        edges = face.Edges
        for edge, name in zip(edges, self.names(edges, "Edge")):
            kind = edge.Curve.TypeId
            if kind == "Part::GeomCircle":
                axis = App.Vector(edge.Curve.Axis)
                if axis.dot(z) < 0:
                    axis = axis * -1  # a face's round edge turns with the face's normal
                out.append(_snap("circle", name, App.Vector(edge.Curve.Center), axis, hint))
            elif kind in LINE_TYPES:
                mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
                out.append(_snap("midpoint", name, mid, z, hint))
        if face.Surface.TypeId == PLANE:
            frame = (_t(z), _t(hint) if hint is not None else None)
            for loop in self.face_loops(element, face, frame):
                out.append(self._loop_snap(loop))
            if len(edges) <= WALL_EDGES and len(face.Wires) == 1:
                out.extend(self._wall_snaps(element, face))
        return [s for s in out if s["at"] or s["kind"] in ("centre", "midpoint", "circle")]

    def _edge_snaps(self, element):
        from . import joints

        edge = self.element(element)
        if edge is None:
            return []
        z, hint = joints._edge_frame(edge)
        out = []
        if joints._is_circle(edge):
            out.append(_snap("circle", element, App.Vector(edge.Curve.Center), z, hint))
        for loop in self.loops_of_edge(element, edge):
            out.append(self._loop_snap(loop))
        mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
        out.append(_snap("midpoint", element, mid, z, hint))
        vertexes = edge.Vertexes
        for v, name in zip(vertexes, self.names(vertexes, "Vertex")):
            if name:
                out.append(_snap("vertex", name, v.Point, z, hint))
        return out

    # -- holes -----------------------------------------------------------------------------------
    def face_loops(self, element, face=None, frame=None):
        """The closed inner outlines of a flat face, as identity dicts. `frame`: the face's
        (normal, X hint) when the caller has it already."""
        if element in self._face_loops:
            return self._face_loops[element]
        face = face if face is not None else self.element(element)
        loops = []
        try:
            if face is not None and face.Surface.TypeId == PLANE:
                outer = face.OuterWire
                inner = [w for w in face.Wires if not w.isSame(outer)]
                if inner:
                    normal, hint = frame if frame is not None else _face_normal_hint(face)
                    for wire in inner:
                        loop = _loop(wire, normal, hint, self)
                        if loop is not None:
                            loop["face"] = element
                            loops.append(loop)
        except Exception:
            loops = []
        self._face_loops[element] = loops
        return loops

    def faces_of_edge(self, element, edge=None):
        """Names of the faces an edge bounds (cached per edge)."""
        if element in self._edge_faces:
            return self._edge_faces[element]
        import Part

        edge = edge if edge is not None else self.element(element)
        names = []
        try:
            faces = self.shape.ancestorsOfType(edge, Part.Face)
            names = [n for n in self.names(faces, "Face") if n]
        except Exception:
            names = []
        self._edge_faces[element] = names
        return names

    def loops_of_edge(self, element, edge=None):
        """The hole outlines (inner loops of flat faces) an edge belongs to."""
        out = []
        for face_name in self.faces_of_edge(element, edge):
            for loop in self.face_loops(face_name):
                if element in loop["edges"]:
                    out.append(loop)
        return out

    def _loop_snap(self, loop):
        return _snap(
            core.LOOP,
            loop["at"],
            _v(loop["c"]),
            _v(loop["n"]),
            _v(loop["x"]) if loop["x"] else None,
            loop=_identity(loop),
        )

    def _wall_snaps(self, element, face):
        """A flat wall of a hole: the hole's centre at its two ends and half-way."""
        try:
            normal = face.normalAt(*face.Surface.parameter(face.CenterOfMass))
        except Exception:
            return []
        loops = []
        seen = set()
        edges = face.Edges
        for edge, name in zip(edges, self.names(edges, "Edge")):
            if not name:
                continue
            for face_name in self.faces_of_edge(name, edge):
                if face_name == element:
                    continue
                for loop in self.face_loops(face_name):
                    key = (loop["face"], loop["at"])
                    if name in loop["edges"] and key not in seen:
                        if abs(core.dot(core.unit(_t(normal)), core.unit(loop["n"]))) < 0.1:
                            seen.add(key)
                            loops.append(loop)
        if not loops:
            return []
        loops.sort(key=lambda lp: (_number(lp["face"]), _number(lp["at"])))
        top = loops[0]
        out = []
        for kind in (core.HOLE_TOP, core.HOLE_MID, core.HOLE_BOTTOM):
            snap = self.snap_of_loop(top, kind, walls=[face], others=loops[1:])
            if snap is not None:
                out.append(snap)
        return out

    def hole_end(self, loop, walls=None, others=None):
        """(point, normal) where the hole that starts at `loop` comes out (or ends), and its
        depth: the outline on the far side when there is one, else the wall's far end."""
        n = core.unit(loop["n"])
        c = loop["c"]
        candidates = list(others or [])
        if not candidates:
            candidates = [lp for lp in self.all_loops() if lp is not loop]
        best = None
        for other in candidates:
            if core.dot(core.unit(other["n"]), n) > -0.999:
                continue
            offset = core.sub(c, other["c"])
            along = core.dot(offset, n)
            if along <= 1e-9:
                continue
            across = core.length(core.sub(offset, core.scale(n, along)))
            if across > max(1e-6, 1e-3 * loop["r"]):
                continue
            if loop["a"] > 1e-9 and abs(other["a"] - loop["a"]) > 0.05 * loop["a"]:
                continue
            if best is None or along < best[0]:
                best = (along, other)
        if best is not None:
            return best[1]["c"], core.scale(n, -1.0), best[0]
        depth = 0.0
        for wall in walls or self._walls_of(loop):
            try:
                for v in wall.Vertexes:
                    depth = max(depth, core.dot(core.sub(c, _t(v.Point)), n))
            except Exception:
                continue
        if depth <= 1e-9:
            return None
        return core.sub(c, core.scale(n, depth)), core.scale(n, -1.0), depth

    def _walls_of(self, loop):
        out = []
        for name in loop["edges"][:1]:
            for face_name in self.faces_of_edge(name):
                if face_name != loop["face"]:
                    f = self.element(face_name)
                    if f is not None:
                        out.append(f)
        return out

    def snap_of_loop(self, loop, kind, walls=None, others=None):
        """The snap of kind loop / hole_top / hole_mid / hole_bottom for a hole outline."""
        if kind == core.LOOP:
            return self._loop_snap(loop)
        end = self.hole_end(loop, walls, others)
        if end is None:
            return None
        far, far_normal, depth = end
        ident = _identity(loop)
        ident["depth"] = depth
        hint = _v(loop["x"]) if loop["x"] else None
        if kind == core.HOLE_TOP:
            return _snap(kind, loop["at"], _v(loop["c"]), _v(loop["n"]), hint, loop=ident)
        if kind == core.HOLE_MID:
            mid = core.scale(core.add(loop["c"], far), 0.5)
            return _snap(kind, loop["at"], _v(mid), _v(loop["n"]), hint, loop=ident)
        if kind == core.HOLE_BOTTOM:
            return _snap(kind, loop["at"], _v(far), _v(far_normal), hint, loop=ident)
        return None

    # -- every hole of the shape (finding a hole again after an edit) -----------------------------
    def all_loops(self):
        if self._all is None:
            found = []
            try:
                faces = self.shape.Faces
                for i, face in enumerate(faces):
                    try:
                        if face.Surface.TypeId != PLANE or len(face.Wires) < 2:
                            continue
                    except Exception:
                        continue
                    found.extend(self.face_loops("Face%d" % (i + 1), face))
            except Exception:
                found = []
            self._all = found
        return self._all

    def find_loop(self, stored):
        """The loop a stored identity means now: by its edges' names first (when they still
        make the same hole), else by where it is, its size and direction."""
        face = stored.get("face")
        if face:
            for loop in self.face_loops(face):
                if core.same_loop(stored, loop):
                    return loop
        loops = self.all_loops()
        i = core.best_loop(stored, loops)
        return loops[i] if i is not None else None


# -- helpers ---------------------------------------------------------------------------------------
def _snap(kind, at, point, z, hint, loop=None):
    s = {"kind": kind, "at": at, "point": point, "z": z, "hint": hint}
    if loop is not None:
        s["loop"] = loop
    return s


def _identity(loop):
    """What a joint stores to find a hole again: centre, normal, X, area, radius, the face
    and the first edge it was on."""
    return {
        "c": list(loop["c"]),
        "n": list(loop["n"]),
        "x": list(loop["x"]) if loop["x"] else None,
        "a": loop["a"],
        "r": loop["r"],
        "face": loop.get("face", ""),
        "edge": loop["at"],
    }


def _number(name):
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0


def _face_normal_hint(face):
    from . import joints

    centre, normal, hint = joints._face_frame(face)
    return _t(normal), (_t(hint) if hint is not None else None)


def _loop(wire, normal, hint, index):
    """The identity of one closed outline: centre of area, area, radius, X, edge names."""
    edges = wire.OrderedEdges
    names = index.names(edges, "Edge")
    if not names or not all(names):
        return None
    sides = []
    arcs = {}
    extra = []
    exact = True
    try:
        points = [_t(v.Point) for v in wire.OrderedVertexes]
    except Exception:
        points = []
    if len(points) != len(edges) or len(points) < 2:
        exact = False
    for i, e in enumerate(edges):
        kind = e.Curve.TypeId
        a = _t(e.valueAt(e.FirstParameter))
        b = _t(e.valueAt(e.LastParameter))
        if kind in LINE_TYPES:
            sides.append((a, b))
            continue
        if kind == "Part::GeomCircle" and exact:
            mid = _t(e.valueAt((e.FirstParameter + e.LastParameter) / 2.0))
            extra.append(mid)
            arcs[i] = (
                _t(e.Curve.Center),
                float(e.Curve.Radius),
                float(e.LastParameter - e.FirstParameter),
                mid,
            )
            continue
        exact = False
    centre = area = None
    if exact and len(points) >= 3:
        # the corners in the order of the edges: edge i runs from points[i] to points[i + 1]
        centre, area = core.outline_centroid(points, arcs, normal)
    if centre is None or not area:
        try:
            import Part

            flat = Part.Face(wire)
            centre = _t(flat.CenterOfMass)
            area = float(flat.Area)
            if not exact:
                extra = [_t(p) for p in wire.discretize(24)]
        except Exception:
            return None
    x = core.x_direction(sides, hint, normal)
    names = [names[i] for i in range(len(names))]
    return {
        "c": centre,
        "n": core.unit(normal),
        "x": x,
        "a": float(area),
        "r": core.circumradius(centre, points + extra),
        "edges": names,
        "at": min(names, key=_number),
    }

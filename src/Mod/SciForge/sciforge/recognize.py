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

What at-recognize added on top of the contract (extra keys, nothing renamed):
  * options "taken_ids": ids already used in the design the plan will run in (the plan's ids
    are then the ones SciForge will give: Sketch1, Extrude1... skipping those), "source":
    "mesh" (set by recognize_mesh: numbers rounded the way a person reads them).
  * every plan step has "id": the id the step will make (create_sketch -> "Sketch1"), and
    "uses": {argument: step number} for the arguments that name an earlier step's id (an AI
    whose step got another id puts that id there instead).
  * "base" has "steps": the plan steps that make it; "features" items carry "steps" too.
  * "timing": seconds spent.

How it reads a solid (each stage can fail on its own without stopping the others):
  1. faces: kind, plane / axis / radius, which faces meet along which edges and whether
     smoothly (tangent);
  2. holes: concave round faces that go all the way round, with their counterbore /
     countersink / drill point / flat bottom (coaxial faces), through or blind;
  3. fillets: round faces (cylinder, torus, sphere) tangent to their neighbours, constant
     radius; chamfers: narrow flat faces between two faces, equal distances;
  4. defeaturing (OpenCASCADE through FreeCAD, shape.defeaturing): the solid without those
     features; a feature that cannot be taken off stays in the base and is said so;
  5. the base: prismatic along an origin axis (levels, a section per level: the base extrude
     and the bosses / cuts on it) or turned about an origin axis (the half profile and a
     revolve);
  6. patterns of equal holes (grid, circle, row), the plan in Fusion's order, the fillet and
     chamfer edges as selectors on the part as it will be when the step runs.
"""

import math
import time

from . import log, warn
from . import recognize_core as core


class RecognizeError(ValueError):
    """Only for wrong arguments (no shape at all); a shape that is hard to read is never an
    error: describe() says what it could not read."""


LIN = 1e-6  # mm: two B-rep values this close are the same
SMOOTH = 0.9998  # cos of ~1.1 degrees: two faces meeting this smoothly are tangent


# -- the entry point ----------------------------------------------------------------------------
def describe(shape, options=None):
    """See the module's CONTRACT."""
    if shape is None:
        raise RecognizeError("There is no shape to describe.")
    try:
        null = shape.isNull()
    except Exception:
        raise RecognizeError("That is not a shape (a Part.Shape is needed).")
    if null:
        raise RecognizeError("There is no shape to describe.")
    options = dict(options or {})
    started = time.time()
    out = {
        "summary": summary(shape),
        "base": {"kind": "none"},
        "features": [],
        "plan": [],
        "unrecognized": [],
        "confidence": 0.0,
        "notes": [],
    }
    if options.get("detail") == "summary":
        out["notes"].append("Summary only (detail: summary).")
        out["timing"] = round(time.time() - started, 3)
        return out
    try:
        _Reader(shape, options).read(out)
    except Exception as exc:  # never raise for a shape it does not understand
        import traceback

        warn("recognize: stopped early: %s\n%s" % (exc, traceback.format_exc()))
        out["notes"].append(
            "Recognition stopped early (%s): what is listed is what was read before." % exc
        )
    max_features = options.get("max_features")
    if isinstance(max_features, int) and max_features >= 0 and len(out["features"]) > max_features:
        out["notes"].append(
            "Only the first %d of %d features are listed (max_features)."
            % (max_features, len(out["features"]))
        )
        out["features"] = out["features"][:max_features]
    out["timing"] = round(time.time() - started, 3)
    log(
        "recognize: %d faces -> base %s, %d features, %d plan steps, confidence %.2f (%.2f s)"
        % (
            out["summary"]["faces"],
            out["base"].get("kind"),
            len(out["features"]),
            len(out["plan"]),
            out["confidence"],
            out["timing"],
        )
    )
    return out


def summary(shape):
    """Volume, area, box, counts and the census of surface kinds."""
    from .ai.ops import selectors

    try:
        box = shape.optimalBoundingBox(False, False)
        if not box.isValid():
            box = shape.BoundBox
    except Exception:
        box = shape.BoundBox
    surfaces = {}
    for face in shape.Faces:
        try:
            kind = selectors.face_type(face)
        except Exception:
            kind = "other"
        surfaces[kind] = surfaces.get(kind, 0) + 1
    try:
        volume = shape.Volume
    except Exception:
        volume = 0.0
    return {
        "volume": _r(volume),
        "area": _r(shape.Area),
        "bbox": [_r(v) for v in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)],
        "size": [_r(box.XLength), _r(box.YLength), _r(box.ZLength)],
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "surfaces": surfaces,
    }


def _r(value, digits=6):
    out = round(float(value), digits)
    return 0.0 if out == 0 else out


def _t(vec):
    return (vec.x, vec.y, vec.z)


def _vec(t):
    import FreeCAD as App

    return App.Vector(float(t[0]), float(t[1]), float(t[2]))


# -- faces --------------------------------------------------------------------------------------
class FaceFacts:
    """What the recognizer needs to know about one face, measured once."""

    def __init__(self, index, face):
        from .ai.ops import selectors

        self.index = index
        self.name = "Face%d" % (index + 1)
        self.face = face
        self.kind = selectors.face_type(face)
        self.area = face.Area
        self.center = _t(face.CenterOfMass)
        self.normal = None  # planes: outward normal
        self.h = None  # planes: position along the normal
        self.axis = None  # cylinders, cones, tori: canonical direction
        self.point = None  # a point of the axis (the one nearest the origin)
        self.radius = None
        self.concave = None
        self.span = None  # cylinders: the angle (radians) the face goes round
        self.semi = None  # cones: half angle (radians)
        self.apex = None
        self.minor = None  # tori
        surface = face.Surface
        try:
            if self.kind == "plane":
                self.normal = core.unit(selectors.face_normal(face))
                self.h = core.dot(self.center, self.normal)
            elif self.kind in ("cylinder", "cone", "torus"):
                self.axis = core.canonical_direction(_t(surface.Axis))
                anchor = _t(surface.Center if self.kind != "cone" else surface.Apex)
                self.point = _axis_point(anchor, self.axis)
                if self.kind == "cylinder":
                    self.radius = surface.Radius
                    u0, u1, _v0, _v1 = face.ParameterRange
                    self.span = abs(u1 - u0)
                elif self.kind == "cone":
                    self.semi = abs(surface.SemiAngle)
                    self.apex = _t(surface.Apex)
                else:
                    self.radius = surface.MajorRadius
                    self.minor = surface.MinorRadius
                self.concave = _concave(face, self.point, self.axis)
            elif self.kind == "sphere":
                self.point = _t(surface.Center)
                self.radius = surface.Radius
        except Exception as exc:
            warn("recognize: %s not measured (%s)" % (self.name, exc))


def _axis_point(anchor, axis):
    """The point of the line (anchor, axis) nearest the origin: one name for one line."""
    t = core.dot(anchor, axis)
    return core.sub(anchor, core.mul(axis, t))


def _boundary_point(face):
    edge = face.Edges[0]
    return edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter))


def _normal_at(face, point):
    u, v = face.Surface.parameter(point)
    return _t(face.normalAt(u, v))


def _concave(face, axis_point, axis):
    """A round face whose outward normal points at its axis (the wall of a hole, an inside
    corner) is concave."""
    p = _boundary_point(face)
    n = _normal_at(face, p)
    radial = core.sub(_t(p), axis_point)
    radial = core.sub(radial, core.mul(axis, core.dot(radial, axis)))
    return core.dot(n, radial) < 0


class Topology:
    """Which faces meet along which edges, and whether smoothly."""

    def __init__(self, shape, facts):
        self.shape = shape
        self.facts = facts
        self.edge_faces = {}  # edge hash -> [face indexes]
        self.edges = {}  # edge hash -> edge
        self.face_edges = []  # face index -> [edge hashes]
        for i, f in enumerate(facts):
            keys = []
            for e in f.face.Edges:
                key = e.hashCode()
                if key not in keys:
                    keys.append(key)
                owners = self.edge_faces.setdefault(key, [])
                if i not in owners:
                    owners.append(i)
                self.edges.setdefault(key, e)
            self.face_edges.append(keys)
        self._smooth = {}

    def neighbours(self, i):
        out = []
        for key in self.face_edges[i]:
            for j in self.edge_faces.get(key, []):
                if j != i and j not in out:
                    out.append(j)
        return out

    def shared(self, i, j):
        return [k for k in self.face_edges[i] if j in self.edge_faces.get(k, [])]

    def smooth(self, key):
        """The two faces of this edge meet tangentially (same normal along it)."""
        if key in self._smooth:
            return self._smooth[key]
        owners = self.edge_faces.get(key, [])
        result = False
        if len(owners) == 2:
            edge = self.edges[key]
            try:
                p = edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter))
                f1, f2 = self.facts[owners[0]], self.facts[owners[1]]
                n1 = f1.normal if f1.normal is not None else _normal_at(f1.face, p)
                n2 = f2.normal if f2.normal is not None else _normal_at(f2.face, p)
                result = core.dot(core.unit(n1), core.unit(n2)) > SMOOTH
            except Exception:
                result = False
        self._smooth[key] = result
        return result

    def tangent_neighbours(self, i):
        out = []
        for key in self.face_edges[i]:
            owners = self.edge_faces.get(key, [])
            if len(owners) == 2 and self.smooth(key):
                j = owners[0] if owners[1] == i else owners[1]
                if j != i and j not in out:
                    out.append(j)
        return out


# -- the reader ---------------------------------------------------------------------------------
class _Reader:
    def __init__(self, shape, options):
        self.options = options
        self.mesh = options.get("source") == "mesh"
        self.notes = []
        self.unrecognized = []
        self.original = shape
        solids = list(shape.Solids)
        if not solids:
            raise RecognizeError("The shape has no solid.")
        if len(solids) > 1:
            solids.sort(key=lambda s: -s.Volume)
            self.notes.append(
                "The shape has %d solids: only the largest is read (%.6g mm3); describe the "
                "others one by one." % (len(solids), solids[0].Volume)
            )
            self.unrecognized.append(
                {
                    "faces": [],
                    "why": "%d more solid(s) beside the largest one are not read."
                    % (len(solids) - 1),
                }
            )
        self.shape = solids[0]
        self.facts = [FaceFacts(i, f) for i, f in enumerate(self.shape.Faces)]
        self.topo = Topology(self.shape, self.facts)
        self.refs = None
        self.counter = 0

    # -- helpers ------------------------------------------------------------------------------
    def new_id(self):
        self.counter += 1
        return "F%d" % self.counter

    def face_refs(self, indexes):
        """Selectors of these faces of the original solid (geometry_facts' stable refs)."""
        if self.refs is None:
            from .ai import geometry_facts

            try:
                self.refs = geometry_facts.stable_refs(self.shape, "faces")
            except Exception as exc:
                warn("recognize: face selectors not made (%s)" % exc)
                self.refs = {}
        out = []
        for i in indexes:
            ref = self.refs.get("Face%d" % (i + 1))
            out.append(ref if ref is not None else {"face": "Face%d" % (i + 1)})
        return out

    def value(self, v, tol=None):
        """A length as the plan writes it: float noise off (B-rep), or rounded the way a person
        reads a measured value (mesh)."""
        if self.mesh:
            return core.round_measured(v)[0]
        return core.snap(v, tol or LIN)

    # -- the stages -----------------------------------------------------------------------------
    def read(self, out):
        t0 = time.time()
        timing = {}
        holes = self.find_holes()
        timing["holes"] = time.time() - t0
        t = time.time()
        blends = self.find_fillets(holes)
        chamfers = self.find_chamfers(holes, blends)
        timing["blends"] = time.time() - t
        t = time.time()
        removed = self.defeature(holes, chamfers, blends)
        timing["defeaturing"] = time.time() - t
        t = time.time()
        self.base_shape = removed["base"]
        base = self.find_base(removed["base"])
        timing["base"] = time.time() - t
        t = time.time()
        plan = core.Plan(self.options.get("taken_ids") or ())
        features = []
        self.plan_base(base, plan, features)
        kept_holes = [h for h in holes if h["id"] in removed["ok"]]
        self.plan_holes(kept_holes, plan, features)
        kept_chamfers = [c for c in chamfers if c["id"] in removed["ok"]]
        self.plan_chamfers(kept_chamfers, removed, plan, features)
        kept_blends = [b for b in blends if b["id"] in removed["ok"]]
        self.plan_fillets(kept_blends, removed, plan, features)
        timing["plan"] = time.time() - t
        out["base"] = base["public"]
        out["features"] = features
        out["plan"] = plan.steps
        explained = set()
        for f in features:
            explained.update(f.get("_faces", []))
        explained.update(base.get("faces", []))
        for f in features:
            f.pop("_faces", None)
        missing = [f.index for f in self.facts if f.index not in explained]
        if missing:
            self.unrecognized.append(
                {
                    "faces": self.face_refs(missing),
                    "why": "%d face(s) are not explained by the plan (the base or a feature "
                    "could not be read there): compare after the plan and add what is "
                    "missing." % len(missing),
                }
            )
        out["unrecognized"] = self.unrecognized
        area_ok = sum(f.area for f in self.facts if f.index in explained)
        out["confidence"] = core.confidence(
            area_ok,
            self.shape.Area,
            base.get("volume_error", self.shape.Volume),
            self.shape.Volume,
        )
        problems = self.check_plan(plan.steps)
        if problems:
            out["confidence"] = round(out["confidence"] * 0.5, 3)
        out["notes"] = self.notes + problems
        out["timing_detail"] = {k: round(v, 3) for k, v in timing.items()}

    def check_plan(self, steps):
        from .ai import catalog

        return [
            "Plan step %d does not pass the tool's check: %s" % (n, sentence)
            for n, sentence in core.check_plan(steps, catalog.validate)
        ]

    # -- holes ----------------------------------------------------------------------------------
    def find_holes(self):
        """Concave round faces that go all the way round, grouped by their axis line, with the
        coaxial faces that make a counterbore, a countersink, a drill point or a flat bottom."""
        bores = {}  # (line key, radius) -> [face indexes]
        for f in self.facts:
            if f.kind == "cylinder" and f.concave and f.radius:
                key = (_line_key(f), round(f.radius, 5))
                bores.setdefault(key, []).append(f.index)
        holes = []
        used = set()
        lines = {}
        for (line, radius), idx in bores.items():
            span = sum(self.facts[i].span or 0 for i in idx)
            if span < 2 * math.pi - 1e-4:
                continue  # a part of a round face (a notch, an inside corner): no hole
            lines.setdefault(line, []).append((radius, idx))
        for line, bore_list in lines.items():
            bore_list.sort()
            radius, idx = bore_list[0]
            if any(i in used for i in idx):
                continue
            hole = self._hole(idx, bore_list[1:])
            if hole is None:
                continue
            for i in hole["_faces"]:
                used.add(i)
            holes.append(hole)
        return holes

    def _extent(self, indexes, axis, origin):
        """(lowest, highest) position of the faces' corners along the axis (from origin)."""
        lo, hi = None, None
        for i in indexes:
            f = self.facts[i]
            if f.kind == "plane" and core.parallel(f.normal, axis, 1e-9):
                t = (f.h - core.dot(origin, f.normal)) * core.dot(f.normal, axis)
                ts = (t,)
            else:
                pts = f.__dict__.get("_points")
                if pts is None:
                    pts = f._points = [_t(v.Point) for v in f.face.Vertexes]
                ts = [core.dot(core.sub(p, origin), axis) for p in pts]
            if ts:
                lo = min(ts) if lo is None else min(lo, min(ts))
                hi = max(ts) if hi is None else max(hi, max(ts))
        return (lo, hi) if lo is not None else (0.0, 0.0)

    def _hole(self, idx, bigger):
        f0 = self.facts[idx[0]]
        axis, origin, radius = f0.axis, f0.point, f0.radius
        t0, t1 = self._extent(idx, axis, origin)
        faces = list(idx)
        ends = {}
        for side, t in (("low", t0), ("high", t1)):
            ends[side] = self._hole_end(idx, axis, origin, radius, t, side, bigger, faces)
        # the open end: where the hole starts
        opening = ("open", "counterbore", "countersink")
        opens = [s for s in ("high", "low") if ends[s]["kind"] in opening]
        if not opens:
            return None  # closed at both ends: an inside void, not a hole
        through = len(opens) == 2
        start_side = opens[0]
        for s in opens:  # a counterbore / countersink end is where the hole starts
            if ends[s]["kind"] in ("counterbore", "countersink"):
                start_side = s
                break
        start = ends[start_side]
        into = core.mul(axis, -1.0 if start_side == "high" else 1.0)  # drilling direction
        t_start = start["t_open"]
        far = ends["low" if start_side == "high" else "high"]
        depth = abs(far["t"] - t_start)
        hole = {
            "kind": "hole",
            "diameter": self.value(2 * radius),
            "axis": [core.snap(c) for c in into],
            "through": through,
            "_faces": faces,
            "_axis": axis,
            "_origin": origin,
            "_t_start": t_start,
            "_start_side": start_side,
            "_start_point": core.add(origin, core.mul(axis, t_start)),
        }
        hole["start"] = [self.value(c) for c in hole["_start_point"]]
        if not through:
            hole["depth"] = self.value(depth)
            hole["bottom"] = far["kind"]
            if far["kind"] == "drill_point":
                hole["drill_angle"] = self.value(far["angle"], 1e-4)
        if start["kind"] == "counterbore":
            hole["kind"] = "counterbore"
            hole["counterbore"] = {
                "diameter": self.value(2 * start["radius"]),
                "depth": self.value(start["depth"]),
            }
        elif start["kind"] == "countersink":
            hole["kind"] = "countersink"
            hole["countersink"] = {
                "diameter": self.value(2 * start["radius"]),
                "angle": self.value(start["angle"], 1e-4),
            }
        hole["start_face"] = start.get("face")
        hole["id"] = self.new_id()
        return hole

    def _hole_end(self, idx, axis, origin, radius, t, side, bigger, faces):
        """What closes or opens the hole's bore at height t: open (the part's face), bottom
        (a flat disc), drill_point (a cone to a point), counterbore (a shoulder and a wider
        bore that opens), countersink (a cone that widens to the face)."""
        out = {"kind": "open", "t": t, "t_open": t}
        sign = 1.0 if side == "high" else -1.0
        neighbours = []
        for i in idx:
            for j in self.topo.neighbours(i):
                if j in idx or j in neighbours:
                    continue
                tj0, tj1 = self._extent([j], axis, origin)
                if min(abs(tj0 - t), abs(tj1 - t)) < 1e-5:
                    neighbours.append(j)
        for j in neighbours:
            fj = self.facts[j]
            tj0, tj1 = self._extent([j], axis, origin)
            beyond = (tj1 - t) * sign > 1e-6 or (tj0 - t) * sign > 1e-6
            if fj.kind == "plane" and core.parallel(fj.normal, axis, 1e-6):
                # a disc of the hole's own size: a flat bottom; a shoulder: a counterbore
                if fj.area <= math.pi * radius * radius * (1 + 1e-6):
                    if core.dot(fj.normal, axis) * sign > 0:
                        continue  # (faces outward: the part's face, not a bottom)
                    faces.append(j)
                    return {"kind": "bottom", "t": t, "t_open": t, "face": j}
                outer = self._shoulder(j, idx, axis, origin, bigger, sign)
                if outer is not None:
                    faces.extend([j] + outer["faces"])
                    return {
                        "kind": "counterbore",
                        "t": t,
                        "t_open": outer["t_open"],
                        "radius": outer["radius"],
                        "depth": abs(outer["t_open"] - t),
                        "face": outer.get("face"),
                    }
                out = {"kind": "open", "t": t, "t_open": t, "face": j}
            elif fj.kind == "cone" and fj.axis is not None and core.parallel(fj.axis, axis, 1e-6):
                apex_t = core.dot(core.sub(fj.apex, origin), axis)
                angle = math.degrees(2 * fj.semi)
                if (apex_t - t) * sign > 0 and beyond:
                    # narrowing away from the bore: a drill point
                    faces.append(j)
                    return {"kind": "drill_point", "t": t, "t_open": t, "angle": angle, "face": j}
                if beyond:
                    # widening away from the bore: a countersink that opens on a face
                    t_far = tj1 if side == "high" else tj0
                    r_far = radius + abs(t_far - t) * math.tan(fj.semi)
                    faces.append(j)
                    return {
                        "kind": "countersink",
                        "t": t,
                        "t_open": t_far,
                        "radius": r_far,
                        "angle": angle,
                        "face": self._opening_face(j, idx + [j]),
                    }
            elif beyond:
                out = {"kind": "open", "t": t, "t_open": t, "face": j}
        return out

    def _opening_face(self, j, exclude):
        for k in self.topo.neighbours(j):
            if k not in exclude:
                return k
        return None

    def _shoulder(self, j, idx, axis, origin, bigger, sign):
        """The wider bore of a counterbore that starts at this shoulder face (j), or None."""
        for _big_radius, big_idx in bigger:
            if not any(k in self.topo.neighbours(j) for k in big_idx):
                continue
            span = sum(self.facts[k].span or 0 for k in big_idx)
            if span < 2 * math.pi - 1e-4:
                continue
            b0, b1 = self._extent(big_idx, axis, origin)
            t_open = b1 if sign > 0 else b0
            return {
                "radius": self.facts[big_idx[0]].radius,
                "t_open": t_open,
                "faces": list(big_idx),
                "face": self._opening_face(big_idx[0], idx + list(big_idx) + [j]),
            }
        return None

    # -- fillets and chamfers ---------------------------------------------------------------------
    def find_fillets(self, holes):
        """Round faces tangent to two neighbours (or more), of constant radius: one entry per
        connected chain of blend faces of one radius."""
        in_holes = set(i for h in holes for i in h["_faces"])
        blend = {}
        for f in self.facts:
            if f.index in in_holes or f.kind not in ("cylinder", "torus", "sphere"):
                continue
            if f.kind == "cylinder" and (f.span is None or f.span >= math.pi - 1e-3):
                continue
            if len(self.topo.tangent_neighbours(f.index)) < 2:
                continue
            blend[f.index] = f.minor if f.kind == "torus" else f.radius
        # corner pieces (free-form or spherical) between blends take their neighbours' radius
        for f in self.facts:
            if f.index in blend or f.index in in_holes:
                continue
            if f.kind in ("bspline", "other", "sphere", "torus"):
                tangent = self.topo.tangent_neighbours(f.index)
                radii = [blend[j] for j in tangent if j in blend]
                if len(radii) >= 2 and max(radii) - min(radii) < 1e-6:
                    blend[f.index] = radii[0]
        chains = []
        seen = set()
        for i in sorted(blend):
            if i in seen:
                continue
            chain, todo = [], [i]
            seen.add(i)
            while todo:
                k = todo.pop()
                chain.append(k)
                for j in self.topo.tangent_neighbours(k):
                    if j in blend and j not in seen and abs(blend[j] - blend[i]) < 1e-6:
                        seen.add(j)
                        todo.append(j)
            chains.append(
                {
                    "id": self.new_id(),
                    "kind": "fillet",
                    "radius": self.value(blend[i]),
                    "_faces": sorted(chain),
                }
            )
        return chains

    def find_chamfers(self, holes, blends):
        """Narrow flat faces cut across the edge between two faces."""
        taken = set(i for h in holes for i in h["_faces"]) | set(
            i for b in blends for i in b["_faces"]
        )
        out = []
        for f in self.facts:
            if f.kind != "plane" or f.index in taken:
                continue
            found = self._chamfer(f, taken)
            if found is not None:
                out.append(found)
        return out

    def _chamfer(self, f, taken):
        lines = []
        for j in self.topo.neighbours(f.index):
            fj = self.facts[j]
            if fj.kind != "plane" or j in taken:
                continue
            if core.parallel(fj.normal, f.normal, 1e-6):
                continue
            for key in self.topo.shared(f.index, j):
                edge = self.topo.edges[key]
                if type(edge.Curve).__name__ not in ("Line", "LineSegment"):
                    continue
                if self.topo.smooth(key):
                    continue
                lines.append((edge.Length, j, edge))
        if len(lines) < 2:
            return None
        lines.sort(key=lambda item: -item[0])
        # two long edges on two neighbours that are not parallel to each other, with this
        # face's normal between theirs
        for a in range(len(lines)):
            for b in range(a + 1, len(lines)):
                _la, ja, ea = lines[a]
                _lb, jb, eb = lines[b]
                if ja == jb:
                    continue
                na, nb = self.facts[ja].normal, self.facts[jb].normal
                if core.parallel(na, nb, 1e-6):
                    continue
                da = _t(ea.Vertexes[-1].Point - ea.Vertexes[0].Point)
                db = _t(eb.Vertexes[-1].Point - eb.Vertexes[0].Point)
                if not core.parallel(da, db, 1e-6):
                    continue
                if core.dot(f.normal, na) <= 1e-6 or core.dot(f.normal, nb) <= 1e-6:
                    continue
                d1, d2 = _chamfer_distances(self.facts[ja], self.facts[jb], ea, eb)
                if d1 is None:
                    continue
                width = _line_distance(ea, eb)
                reach_a = _extent_across(self.facts[ja].face, da)
                reach_b = _extent_across(self.facts[jb].face, db)
                if width > reach_a or width > reach_b or min(ea.Length, eb.Length) < 1.5 * width:
                    continue  # too wide for a chamfer: a real slanted face of the part
                item = {
                    "id": self.new_id(),
                    "kind": "chamfer",
                    "distance": self.value(d1),
                    "_faces": [f.index],
                    "_between": (ja, jb),
                }
                if abs(d1 - d2) > 1e-5:
                    item["distance2"] = self.value(d2)
                return item
        return None

    # -- defeaturing ----------------------------------------------------------------------------
    def _defeature(self, groups, shape=None):
        """The solid (the original, or `shape`: one whose untouched faces are the original's)
        without the faces of these feature groups (OpenCASCADE's defeaturing), or None when
        it cannot take them off. Results are kept: the same set is asked for more than once."""
        shape = self.shape if shape is None else shape
        faces = [i for g in groups for i in g["_faces"]]
        if not faces:
            return shape
        key = (id(shape), tuple(sorted(set(faces))))
        cache = self.__dict__.setdefault("_defeatured", {})
        if key in cache:
            return cache[key]
        out = None
        try:
            got = shape.defeaturing([self.facts[i].face for i in key[1]])
            if not got.isNull() and got.isValid() and len(got.Solids) == 1:
                out = got.Solids[0]
                try:
                    refined = out.removeSplitter()
                    if not refined.isNull() and refined.isValid() and len(refined.Solids) == 1:
                        out = refined.Solids[0]
                except Exception:
                    pass
        except Exception:
            out = None
        cache[key] = out
        return out

    def _accept(self, groups, start=(), shape=None):
        """(accepted, rejected): the groups OpenCASCADE can take off together with `start`
        (all at once, else by halves)."""
        accepted = list(start)
        rejected = []

        def attempt(candidates):
            if not candidates:
                return
            if self._defeature(accepted + candidates, shape) is not None:
                accepted.extend(candidates)
                return
            if len(candidates) == 1:
                rejected.extend(candidates)
                return
            half = len(candidates) // 2
            attempt(candidates[:half])
            attempt(candidates[half:])

        attempt(list(groups))
        return accepted[len(start) :], rejected

    def _drop_holes(self, holes):
        """(solid, holes taken off, holes left): the original solid with the holes closed by
        rebuilding the faces that carry their rims without those rims and leaving the holes'
        own faces out (milliseconds, where defeaturing a few hundred holes takes minutes).
        A hole whose rim is not a whole inner loop of a face (it cuts an edge of the part,
        it meets another hole) is left for defeaturing."""
        import Part

        if not holes:
            return self.shape, [], []
        owner = {}  # edge key -> hole ids
        for h in holes:
            for i in h["_faces"]:
                for key in self.topo.face_edges[i]:
                    owner.setdefault(key, set()).add(h["id"])
        in_hole = {i: h["id"] for h in holes for i in h["_faces"]}
        bad = set()
        rims = {}  # face index -> [(wire, hole id)]
        for f in self.facts:
            if f.index in in_hole:
                continue
            outer = f.face.OuterWire
            for wire in f.face.Wires:
                keys = [e.hashCode() for e in wire.Edges]
                ids = set()
                for key in keys:
                    ids |= owner.get(key, set())
                if not ids:
                    continue
                whole = all(owner.get(key) == ids for key in keys) and len(ids) == 1
                if wire.isSame(outer) or not whole:
                    bad |= ids
                    continue
                rims.setdefault(f.index, []).append((wire, next(iter(ids))))
        # every edge a hole shares with the rest of the part must be in a dropped rim
        dropped_keys = set()
        for items in rims.values():
            for wire, hid in items:
                dropped_keys.update(e.hashCode() for e in wire.Edges)
        for h in holes:
            for i in h["_faces"]:
                for key in self.topo.face_edges[i]:
                    others = [j for j in self.topo.edge_faces.get(key, []) if j not in in_hole]
                    if others and key not in dropped_keys:
                        bad.add(h["id"])
        good = [h for h in holes if h["id"] not in bad]
        if not good:
            return self.shape, [], list(holes)
        good_ids = {h["id"] for h in good}
        faces = []
        try:
            for f in self.facts:
                if in_hole.get(f.index) in good_ids:
                    continue
                drop = [w for w, hid in rims.get(f.index, []) if hid in good_ids]
                if not drop:
                    faces.append(f.face)
                    continue
                gone = {d.hashCode() for d in drop} | {f.face.OuterWire.hashCode()}
                keep = [w for w in f.face.Wires if w.hashCode() not in gone]
                rebuilt = Part.Face(f.face.Surface, f.face.OuterWire)
                if keep:
                    rebuilt = rebuilt.cutHoles(keep)
                p = rebuilt.CenterOfMass
                n_new = rebuilt.normalAt(*rebuilt.Surface.parameter(p))
                n_old = f.face.normalAt(*f.face.Surface.parameter(p))
                if n_new.dot(n_old) < 0:
                    rebuilt.reverse()
                faces.append(rebuilt)
            solid = Part.Solid(Part.Shell(faces))
            if solid.isNull() or not solid.isValid():
                raise ValueError("not a valid solid")
            expected = self.shape.Volume + sum(_hole_void(self, h) for h in good)
            if abs(solid.Volume - expected) > 1e-6 * max(1.0, expected):
                raise ValueError("%.6g mm3, %.6g expected" % (solid.Volume, expected))
        except Exception as exc:
            warn("recognize: holes not closed by their rims (%s)" % exc)
            return self.shape, [], list(holes)
        return solid, good, [h for h in holes if h["id"] in bad]

    def defeature(self, holes, chamfers, blends):
        """Take off every feature that can be taken off: the holes first (their rims closed,
        or with OpenCASCADE's defeaturing), then chamfers and fillets (defeaturing: all at
        once, else by halves). The ones that cannot be taken off stay in the base and are
        listed as such. Returns {"base": shape, "ok": {feature ids}, "accepted": [features]}."""
        start, holes_ok, left = self._drop_holes(holes)
        groups = left + chamfers + blends
        ok, rejected = self._accept(groups, shape=start)
        base = self._defeature(ok, start) if ok else start
        if base is None:  # (cannot happen: it was tried)
            base, ok = start, []
        if base is not start or holes_ok:
            try:
                refined = base.removeSplitter()
                if not refined.isNull() and refined.isValid() and len(refined.Solids) == 1:
                    base = refined.Solids[0]
            except Exception:
                pass
        accepted = holes_ok + ok
        for g in rejected:
            self.notes.append(
                "%s %s could not be taken off the base shape (OpenCASCADE's defeaturing "
                "refused it): it is left in the base and not in the plan."
                % (g["kind"].capitalize(), g["id"])
            )
            self.unrecognized.append(
                {
                    "faces": self.face_refs(g["_faces"]),
                    "why": "a %s that could not be separated from the base shape" % g["kind"],
                }
            )
        return {"base": base, "ok": {g["id"] for g in accepted}, "accepted": accepted}

    # -- the base -------------------------------------------------------------------------------
    def find_base(self, solid):
        """The base shape: prismatic along an origin axis (fewest steps first) or turned about
        an origin axis."""
        best = None
        for axis in ("Z", "Y", "X"):
            try:
                found = _prismatic(solid, axis)
            except Exception as exc:
                warn("recognize: prismatic along %s not read (%s)" % (axis, exc))
                found = None
            if found is None:
                continue
            score = (len(found["ops"]), found["slabs"], ("Z", "Y", "X").index(axis))
            if best is None or score < best[0]:
                best = (score, found)
        revolved = None
        if best is None or len(best[1]["ops"]) >= 3:
            try:
                revolved = _revolved(solid)
            except Exception as exc:
                warn("recognize: revolve not read (%s)" % exc)
        if revolved is not None:
            chosen = revolved
        elif best is not None:
            chosen = best[1]
        else:
            chosen = None
        if chosen is None:
            self.notes.append(
                "The base shape is neither an extrude along X, Y or Z nor a revolve about "
                "one of them: build it yourself (look at render and query_geometry), then "
                "follow the rest of the plan."
            )
            return {
                "public": {"kind": "none"},
                "ops": [],
                "faces": [],
                "volume_error": solid.Volume,
            }
        # how well the decomposition rebuilds the defeatured solid
        try:
            rebuilt = _build_ops(chosen)
            error = rebuilt.cut(solid).Volume + solid.cut(rebuilt).Volume
        except Exception as exc:
            warn("recognize: base check failed (%s)" % exc)
            error = solid.Volume
        chosen["volume_error"] = error
        good = error <= 1e-4 * max(1.0, solid.Volume)
        if not good:
            self.notes.append(
                "The base read from the part differs from it by %.4g mm3: compare after the "
                "base steps." % error
            )
        # every face of the original that is still in the defeatured base is explained by it
        chosen["faces"] = self._faces_in(solid) if good else []
        return chosen

    def _faces_in(self, solid):
        """Indexes of the original's faces that lie on the surface of a face of `solid`."""
        buckets = {}
        for face in solid.Faces:
            buckets.setdefault(_surface_key(face), []).append(face)
        out = []
        for f in self.facts:
            for face in buckets.get(_surface_key(f.face), []):
                if _same_surface(f.face, face, 1e-5):
                    out.append(f.index)
                    break
        return out

    # -- the plan -------------------------------------------------------------------------------
    def plan_base(self, base, plan, features):
        public = base["public"]
        if public["kind"] == "none":
            return
        steps = []
        if public["kind"] == "revolve":
            sketch = plan.add(
                "create_sketch",
                core.sketch_args(public["plane"], 0.0, public.pop("geometry")),
                "The half profile of the turned part (%s), on the %s plane, on one side of the "
                "%s axis." % (public["profile_words"], public["plane"], public["axis"]),
            )
            rev = plan.add(
                "revolve",
                {"profile": sketch, "axis": public["axis"]},
                "Revolve it a full turn about the %s axis: the base shape." % public["axis"],
                uses={"profile": plan.step_of(sketch)},
            )
            public["steps"] = [plan.step_of(sketch), plan.step_of(rev)]
            return
        first = True
        for op in _group_ops(base["ops"], self._pattern_args):
            plane, offset = op["plane"], op["offset"]
            kind = op["kind"]
            where = (" at %s mm" % core.fmt(offset)) if offset else ""
            if first:
                why_sketch = "The base profile (%s) on the %s plane%s." % (
                    op["words"],
                    plane,
                    where,
                )
            else:
                why_sketch = "The profile of the %s (%s) on the %s plane%s." % (
                    "cut" if kind == "cut" else "boss",
                    op["words"],
                    plane,
                    where,
                )
            sketch = plan.add(
                "create_sketch", core.sketch_args(plane, offset, op["geometry"]), why_sketch
            )
            args = {"profile": sketch}
            args.update(op["extrude"])
            if first:
                why = "Extrude it %s mm: the base shape." % core.fmt(op["height"])
                fids = []
            else:
                fid = self.new_id()
                fids = [fid]
                features.append(
                    {
                        "id": fid,
                        "kind": "pocket" if kind == "cut" else "boss",
                        "plane": plane,
                        "offset": core.snap(offset),
                        "height": core.snap(op["height"]),
                        "through": bool(op["extrude"].get("through_all")),
                        "profile": op["loops_public"],
                        "profile_words": op["words"],
                        "faces": [],
                        "_faces": [],
                    }
                )
                if op["extrude"].get("through_all"):
                    why = "Cut it through the whole part."
                elif kind == "cut":
                    why = "Cut it %s mm into the part." % core.fmt(op["height"])
                else:
                    why = "Extrude it %s mm, joined to the part: a boss." % core.fmt(op["height"])
            if op.get("count", 1) > 1 and not op.get("pattern"):
                why = why[:-1] + " (%d of them, drawn in one sketch)." % op["count"]
            ext = plan.add("extrude", args, why, fids, uses={"profile": plan.step_of(sketch)})
            made = [plan.step_of(sketch), plan.step_of(ext)]
            if op.get("pattern"):
                tool, pargs, pattern = op["pattern"]
                pid = self.new_id()
                plan.add(
                    tool,
                    dict(features=[ext], **pargs),
                    "Repeat it: %s." % _pattern_words(pattern),
                    [pid],
                    uses={"features[0]": plan.step_of(ext)},
                )
                made.append(len(plan.steps))
                features.append(
                    {
                        "id": pid,
                        "kind": "pattern",
                        "of": fids[0],
                        "pattern": _public_pattern(pattern, op["plane"], op["offset"]),
                        "count": op["count"],
                        "steps": [len(plan.steps)],
                        "faces": [],
                        "_faces": [],
                    }
                )
            steps += made
            if fids:
                for f in features:
                    if f["id"] == fids[0]:
                        f["steps"] = made
            first = False
        public["steps"] = steps

    def plan_holes(self, holes, plan, features):
        """One hole step per group of equal holes on one plane: a pattern step when they make
        a grid / circle / row the pattern tool can repeat, else one sketch with every centre."""
        groups = {}
        for h in holes:
            axis_name = core.origin_axis(h["_axis"])
            key = (
                h["kind"],
                h["diameter"],
                h.get("depth"),
                h["through"],
                repr(h.get("counterbore")),
                repr(h.get("countersink")),
                h.get("bottom"),
                h.get("drill_angle"),
                axis_name,
                tuple(h["axis"]),
                core.snap(core.dot(h["_start_point"], h["_axis"]), 1e-5),
            )
            groups.setdefault(key, []).append(h)
        round_centres = self._round_centres()
        for key, group in groups.items():
            h0 = group[0]
            axis_name = key[8]
            if axis_name is None:
                for h in group:
                    self._plan_single_hole(h, plan, features)
                continue
            plane = core.PLANE_OF_AXIS[axis_name]
            by_point = {}
            for h in group:
                x, y, _hh = core.to_plane(plane, h["_start_point"])
                by_point[(core.snap(x), core.snap(y))] = h
            pts = list(by_point)
            offset = core.to_plane(plane, h0["_start_point"])[2]
            centres2d = [core.to_plane(plane, c)[:2] for c in round_centres.get(axis_name, [])]
            tol = 0.02 if self.mesh else 1e-4
            pattern = core.find_pattern(pts, tol, centres2d) if len(pts) >= 2 else None
            pattern_step = self._pattern_args(pattern, plane) if pattern else None
            ordered = core.pattern_order(pts, pattern) if pattern_step else sorted(pts)
            drawn = ordered[:1] if pattern_step else ordered
            group = [by_point[p] for p in ordered]
            r = h0["diameter"] / 2.0
            geometry = [{"circle": [x, y, r]} for x, y in drawn]
            words = self._hole_words(h0)
            sketch = plan.add(
                "create_sketch",
                core.sketch_args(plane, offset, geometry),
                "The centre%s of the %s on the %s plane%s, where the hole%s start%s."
                % (
                    "" if len(drawn) == 1 else "s",
                    words,
                    plane,
                    (" at %s mm" % core.fmt(offset)) if offset else "",
                    "" if len(group) == 1 else "s",
                    "s" if len(group) == 1 else "",
                ),
            )
            args = {"sketch": sketch, "diameter": h0["diameter"]}
            if h0["through"]:
                args["through_all"] = True
            else:
                args["depth"] = h0["depth"]
            if h0.get("counterbore"):
                args["counterbore"] = dict(h0["counterbore"])
            if h0.get("countersink"):
                args["countersink"] = dict(h0["countersink"])
            if h0.get("bottom") == "drill_point":
                args["drill_point"] = "angle"
                args["drill_angle"] = h0["drill_angle"]
            fids = [h["id"] for h in group]
            how = " through the part" if h0["through"] else " %s mm deep" % core.fmt(h0["depth"])
            count = "" if len(drawn) == 1 else "%d " % len(drawn)
            hole_id = plan.add(
                "hole",
                args,
                "Drill %s%s%s." % (count or "the ", words, how),
                fids if not pattern_step else fids[:1],
                uses={"sketch": plan.step_of(sketch)},
            )
            steps = [plan.step_of(sketch), plan.step_of(hole_id)]
            if pattern_step:
                pid = self.new_id()
                tool, pargs = pattern_step
                pargs = dict(features=[hole_id], **pargs)
                plan.add(
                    tool,
                    pargs,
                    "Repeat the hole: %s." % _pattern_words(pattern),
                    [pid] + fids[1:],
                    uses={"features[0]": plan.step_of(hole_id)},
                )
                steps.append(len(plan.steps))
                features.append(
                    {
                        "id": pid,
                        "kind": "pattern",
                        "of": fids[0],
                        "features": fids,
                        "pattern": _public_pattern(pattern, plane, offset),
                        "count": len(group),
                        "steps": [len(plan.steps)],
                        "faces": [],
                        "_faces": [],
                    }
                )
            for h in group:
                features.append(self._public_hole(h, steps))

    def _plan_single_hole(self, h, plan, features):
        """A hole along no origin axis: a Single Hole on its start face (a flat face), else the
        hole is listed for the AI to make (no plan step)."""
        face = h.get("start_face")
        if face is None or self.facts[face].kind != "plane":
            self.unrecognized.append(
                {
                    "faces": self.face_refs(h["_faces"]),
                    "why": "a hole of diameter %s along %s that starts on a face the plan "
                    "cannot sketch on: make it with hole (face + at)"
                    % (core.fmt(h["diameter"]), h["axis"]),
                }
            )
            features.append(self._public_hole(h, []))
            return
        self.notes.append(
            "Hole %s runs along no origin axis: the plan uses a Single Hole on its face; check "
            "the face selector after the base is built." % h["id"]
        )
        f = self.facts[face]
        args = {
            "face": {"normal": [core.snap(c, 1e-9) for c in f.normal], "count": 1},
            "at": [core.snap(c) for c in h["_start_point"]],
            "diameter": h["diameter"],
        }
        if h["through"]:
            args["extent"] = "all"
        else:
            args["depth"] = h["depth"]
        plan.add("hole", args, "Drill a %s." % self._hole_words(h), [h["id"]])
        features.append(self._public_hole(h, [len(plan.steps)]))

    def _round_centres(self):
        """{axis name: [points]}: the axes of the part's round faces (a flange's middle)."""
        out = {}
        for f in self.facts:
            if f.kind in ("cylinder", "cone", "torus") and f.axis is not None:
                name = core.origin_axis(f.axis)
                if name:
                    out.setdefault(name, []).append(f.point)
        return out

    def _pattern_args(self, pattern, plane):
        """(tool, arguments) of Fusion's pattern dialog for a pattern found in the sketch plane
        (the features argument is added by the caller), or None when no tool says it."""
        frame = core.PLANES[plane]
        if pattern["kind"] == "rectangular":
            first_axis = frame["x"] if pattern.get("axis", "x") == "x" else frame["y"]
            name1 = core.origin_axis(first_axis)
            args = {
                "direction": name1,
                "quantity": pattern["count"],
                "distance": core.snap(pattern["spacing"]),
                "distribution": "spacing",
            }
            if pattern["count2"] > 1:
                args.update(
                    direction2=core.origin_axis(frame["y"]),
                    quantity2=pattern["count2"],
                    distance2=core.snap(pattern["spacing2"]),
                )
            if args["quantity"] < 2:
                return None
            return "rectangular_pattern", args
        if pattern["kind"] == "circular":
            cx, cy = pattern["center"]
            axis = core.origin_axis(frame["n"])
            if abs(cx) > 1e-6 or abs(cy) > 1e-6:
                axis = self._axis_face(plane, (cx, cy))
                if axis is None:
                    return None  # about an axis no round face of the part shows
            args = {"axis": axis, "quantity": pattern["count"]}
            if not pattern["full"]:
                if core.dot(frame["n"], core.AXES[core.origin_axis(frame["n"])]) < 0:
                    return None  # (turns the other way about the axis: one sketch instead)
                args["type"] = "angle"
                args["angle"] = core.snap(pattern["step"] * (pattern["count"] - 1), 1e-7)
            return "circular_pattern", args
        return None

    def _axis_face(self, plane, centre):
        """{"face": selector} of a round face of the base around the axis through this sketch
        point (square to the plane), for a circular pattern about it; None when there is
        none."""
        from .ai import geometry_facts

        shape = getattr(self, "base_shape", None)
        if shape is None:
            return None
        frame = core.PLANES[plane]
        point = core.from_plane(plane, centre[0], centre[1], 0.0)
        wanted = []
        for i, face in enumerate(shape.Faces, start=1):
            facts = FaceFacts(i - 1, face)
            if facts.kind != "cylinder" or not core.parallel(facts.axis, frame["n"], 1e-7):
                continue
            if core.norm(core.sub(facts.point, _axis_point(point, facts.axis))) < 1e-5:
                wanted.append("Face%d" % i)
        if not wanted:
            return None
        refs = geometry_facts.stable_refs(shape, "faces", wanted=set(wanted[:1]))
        ref = refs.get(wanted[0])
        return {"face": ref} if ref else None

    def _hole_words(self, h):
        size = "d %s" % core.fmt(h["diameter"])
        if h["kind"] == "counterbore":
            return "counterbored hole %s (counterbore d %s x %s)" % (
                size,
                core.fmt(h["counterbore"]["diameter"]),
                core.fmt(h["counterbore"]["depth"]),
            )
        if h["kind"] == "countersink":
            return "countersunk hole %s (countersink d %s, %s degrees)" % (
                size,
                core.fmt(h["countersink"]["diameter"]),
                core.fmt(h["countersink"]["angle"]),
            )
        if h.get("bottom") == "drill_point":
            return "hole %s with a %s degree drill point" % (size, core.fmt(h["drill_angle"]))
        return "hole %s" % size

    def _public_hole(self, h, steps):
        out = {"id": h["id"], "kind": h["kind"], "diameter": h["diameter"]}
        for key in ("through", "depth", "bottom", "drill_angle", "counterbore", "countersink"):
            if key in h:
                out[key] = h[key]
        out["axis"] = h["axis"]
        out["start"] = h["start"]
        out["faces"] = self.face_refs(h["_faces"])
        out["steps"] = steps
        out["_faces"] = list(h["_faces"])
        return out

    def plan_chamfers(self, chamfers, removed, plan, features):
        """One chamfer step per size (two distances: per side, measured as SciForge's Chamfer
        does: distance 1 on the edge's first face), the edges picked on the part without its
        chamfers and fillets."""
        if not chamfers:
            return
        accepted = removed["accepted"]
        shape = self._defeature([g for g in accepted if g["kind"] in ("chamfer", "fillet")])
        by_size = {}
        for c in chamfers:
            d1, d2 = c["distance"], c.get("distance2")
            if d2 is not None and shape is not None and not self._first_face_is_a(shape, c):
                d1, d2 = d2, d1
            by_size.setdefault((d1, d2), []).append(c)
        for (d1, d2), group in sorted(by_size.items(), key=lambda kv: -kv[0][0]):
            edges = self._sharp_edges(shape, group) if shape is not None else []
            sel = self._edge_selector(shape, edges) if edges else None
            fids = [c["id"] for c in group]
            if sel is None:
                self.notes.append(
                    "The edges of chamfer%s %s were not found on the part as it will be: "
                    "pick them with query_geometry."
                    % ("s" if len(group) > 1 else "", ", ".join(fids))
                )
            else:
                words = "Chamfer %d edge%s %s mm%s." % (
                    len(edges),
                    "" if len(edges) == 1 else "s",
                    core.fmt(d1),
                    "" if d2 is None else " x %s mm (flip swaps the two sides)" % core.fmt(d2),
                )
                if _chain_complete(shape, edges):
                    args = {"edges": sel, "distance": d1}
                    if d2 is not None:
                        args["distance2"] = d2
                    plan.add("chamfer", args, words, fids)
                else:
                    row = {"edges": sel, "distance": d1, "tangent_chain": False}
                    if d2 is not None:
                        row.update(chamfer_type="two", distance2=d2)
                    plan.add(
                        "fillet_sets",
                        {"kind": "chamfer", "sets": [row], "tangent_chain": False},
                        words[:-1] + ", Tangent Chain off (only these edges).",
                        fids,
                    )
            for c in group:
                item = {"id": c["id"], "kind": "chamfer", "distance": c["distance"]}
                if "distance2" in c:
                    item["distance2"] = c["distance2"]
                item["faces"] = self.face_refs(c["_faces"])
                item["steps"] = [len(plan.steps)] if sel is not None else []
                item["_faces"] = list(c["_faces"])
                features.append(item)

    def _first_face_is_a(self, shape, chamfer):
        """Whether SciForge's Chamfer measures distance 1 (the one on face A) for this
        chamfer: its sharp edge's first face on `shape` lies on face A."""
        import Part

        names = self._sharp_edges(shape, [chamfer])
        if not names:
            return True
        try:
            edge = shape.getElement(names[0])
            first = shape.ancestorsOfType(edge, Part.Face)[0]
        except Exception:
            return True
        return _same_surface(self.facts[chamfer["_between"][0]].face, first)

    def plan_fillets(self, blends, removed, plan, features):
        """One fillet step per radius (biggest first), each with its edges picked on the part
        as it will be then (the later fillets not made yet)."""
        if not blends:
            return
        by_radius = {}
        for b in blends:
            by_radius.setdefault(b["radius"], []).append(b)
        radii = sorted(by_radius, key=lambda r: -r)
        groups = [by_radius[r] for r in radii]
        for k, group in enumerate(groups):
            later = [b for g in groups[k:] for b in g]
            shape = self._defeature(later)
            edges = self._sharp_edges(shape, group) if shape is not None else []
            sel = self._edge_selector(shape, edges) if edges else None
            fids = [b["id"] for b in group]
            radius = group[0]["radius"]
            if sel is None:
                self.notes.append(
                    "The edges of the %s mm fillet%s (%s) were not found on the part as it "
                    "will be: pick them with query_geometry."
                    % (core.fmt(radius), "s" if len(group) > 1 else "", ", ".join(fids))
                )
            elif _chain_complete(shape, edges):
                plan.add(
                    "fillet",
                    {"edges": sel, "radius": radius},
                    "Round %d edge%s with a %s mm fillet."
                    % (len(edges), "" if len(edges) == 1 else "s", core.fmt(radius)),
                    fids,
                )
            else:  # the edges go on smoothly into edges that stay sharp
                plan.add(
                    "fillet_sets",
                    {
                        "sets": [{"edges": sel, "radius": radius, "tangent_chain": False}],
                        "tangent_chain": False,
                    },
                    "Round %d edge%s with a %s mm fillet, Tangent Chain off (the edges they "
                    "run on into stay sharp)."
                    % (len(edges), "" if len(edges) == 1 else "s", core.fmt(radius)),
                    fids,
                )
            for b in group:
                features.append(
                    {
                        "id": b["id"],
                        "kind": "fillet",
                        "radius": b["radius"],
                        "faces": self.face_refs(b["_faces"]),
                        "steps": [len(plan.steps)] if sel is not None else [],
                        "_faces": list(b["_faces"]),
                    }
                )

    def _sharp_edges(self, shape, group):
        """Names of the edges of `shape` (the part without these blends) where the blends
        were: for each blend face, the edge between the two faces it joined (the faces it is
        tangent to; a chamfer's two faces), close to it."""
        pairs = []  # (blend face index, [joined face indexes], reach)
        for g in group:
            size = max(g.get("radius") or 0, g.get("distance") or 0, g.get("distance2") or 0)
            reach = 2.5 * size + 1e-6
            if g["kind"] == "chamfer":
                pairs.append((g["_faces"][0], list(g["_between"]), reach))
                continue
            for i in g["_faces"]:
                joined = [j for j in self.topo.tangent_neighbours(i) if j not in g["_faces"]]
                if len(joined) >= 2:
                    pairs.append((i, joined, reach))
        edge_owner = {}
        for fi, face in enumerate(shape.Faces):
            for e in face.Edges:
                owners = edge_owner.setdefault(e.hashCode(), [])
                if fi not in owners:
                    owners.append(fi)
        names = []
        for ei, edge in enumerate(shape.Edges, start=1):
            owners = edge_owner.get(edge.hashCode(), [])
            if len(owners) != 2:
                continue
            fa, fb = shape.Faces[owners[0]], shape.Faces[owners[1]]
            mid = None
            for i, joined, reach in pairs:
                sa = any(_same_surface(self.facts[j].face, fa) for j in joined)
                if not sa:
                    continue
                sb = any(_same_surface(self.facts[j].face, fb) for j in joined)
                if not sb:
                    continue
                if mid is None:
                    try:
                        mid = _vertex(
                            _t(edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter)))
                        )
                    except Exception:
                        break
                if self.facts[i].face.distToShape(mid)[0] <= reach:
                    names.append("Edge%d" % ei)
                    break
        return names

    def _edge_selector(self, shape, names):
        """A selector that picks exactly these edges of `shape`: a short one when one fits
        (the edges at the top...), else one ref per edge (any_of)."""
        from .ai import geometry_facts
        from .ai.ops import selectors

        names = sorted(set(names), key=_natural)
        want = set(names)

        def picks(spec):
            try:
                return set(selectors.select(shape, spec, "edges")) == want
            except Exception:
                return False

        edges = [shape.getElement(n) for n in names]
        kinds = {selectors.edge_type(e) for e in edges}
        if len(want) == len(shape.Edges):
            return {"all": True, "count": len(want)}
        kind = kinds.pop() if len(kinds) == 1 else None
        candidates = []
        if kind == "line":
            dirs = set()
            for e in edges:
                d = core.canonical_direction(_t(e.Vertexes[-1].Point - e.Vertexes[0].Point))
                dirs.add(tuple(core.snap(c, 1e-9) for c in d))
            if len(dirs) == 1:
                d = list(dirs.pop())
                candidates.append({"type": "line", "parallel": d, "count": len(want)})
                for axis in ("z", "y", "x"):
                    for value in ("max", "min"):
                        candidates.append(
                            {
                                "type": "line",
                                "parallel": d,
                                "at": {"axis": axis, "value": value},
                                "count": len(want),
                            }
                        )
        for axis in ("z", "y", "x"):
            for value in ("max", "min"):
                spec = {"at": {"axis": axis, "value": value}, "count": len(want)}
                if kind:
                    spec = dict({"type": kind}, **spec)
                candidates.append(spec)
        for spec in candidates:
            if picks(spec):
                return spec
        refs = geometry_facts.stable_refs(shape, "edges", wanted=want)
        parts = [refs.get(n) for n in names]
        if any(p is None for p in parts):
            return None
        if len(parts) == 1:
            return parts[0]
        spec = {"any_of": parts, "count": len(parts)}
        return spec if picks(spec) else None


def _hole_void(reader, h):
    """The volume a hole takes out of the part (its cylinders and cones), worked out from
    its faces."""
    axis, origin = h["_axis"], h["_origin"]
    total = 0.0
    for i in h["_faces"]:
        f = reader.facts[i]
        if f.kind == "cylinder":
            t0, t1 = reader._extent([i], axis, origin)
            total += math.pi * f.radius**2 * (t1 - t0)
        elif f.kind == "cone":
            rings = {}
            for v in f.face.Vertexes:
                w = core.sub(_t(v.Point), origin)
                t = core.dot(w, axis)
                rings[round(t, 6)] = core.norm(core.sub(w, core.mul(axis, t)))
            if len(rings) == 1:
                rings[round(core.dot(core.sub(f.apex, origin), axis), 6)] = 0.0
            (ta, ra), (tb, rb) = sorted(rings.items())[:2]
            total += math.pi * (tb - ta) * (ra * ra + ra * rb + rb * rb) / 3.0
    return total


def _chain_complete(shape, names):
    """True when no edge that runs on smoothly from a picked edge (tangent where they meet:
    what OpenCASCADE's fillet follows by itself) is left out of the pick."""
    want = set(names)
    if not want:
        return True
    at_vertex = {}
    for i, e in enumerate(shape.Edges, start=1):
        for v in e.Vertexes:
            at_vertex.setdefault(v.hashCode(), []).append(("Edge%d" % i, e))
    for name in want:
        edge = shape.getElement(name)
        for v in edge.Vertexes:
            try:
                t1 = edge.tangentAt(edge.parameterAt(v))
            except Exception:
                continue
            for other_name, other in at_vertex.get(v.hashCode(), []):
                if other_name == name or other_name in want:
                    continue
                try:
                    t2 = other.tangentAt(other.parameterAt(v))
                except Exception:
                    continue
                if t1.Length > 0 and t2.Length > 0:
                    if abs(t1.dot(t2)) / (t1.Length * t2.Length) > 0.9998:
                        return False
    return True


# -- shape helpers ------------------------------------------------------------------------------
def _natural(name):
    digits = "".join(ch for ch in name if ch.isdigit())
    return (name.rstrip("0123456789"), int(digits) if digits else 0)


def _vertex(point):
    import Part

    return Part.Vertex(_vec(point))


def _inner_uv(face):
    """A (u, v) of a point on the face (inside it where that is easy to find)."""
    try:
        c = face.CenterOfMass
        u, v = face.Surface.parameter(c)
        if face.isInside(face.valueAt(u, v), 1e-6, True):
            return u, v
    except Exception:
        pass
    try:
        edge = face.Edges[0]
        p = edge.valueAt(0.5 * (edge.FirstParameter + edge.LastParameter))
        return face.Surface.parameter(p)
    except Exception:
        u0, u1, v0, v1 = face.ParameterRange
        return 0.5 * (u0 + u1), 0.5 * (v0 + v1)


def _surface_key(face):
    """A coarse key of a face's surface (kind and direction) to bucket faces by."""
    kind = _face_kind(face)
    try:
        if kind in ("plane", "cylinder", "cone", "torus"):
            d = core.canonical_direction(_t(face.Surface.Axis))
            return (kind,) + tuple(round(c, 3) + 0.0 for c in d)
    except Exception:
        pass
    return (kind,)


def _line_key(f):
    return (
        tuple(round(c, 5) + 0.0 for c in f.axis),
        tuple(round(c, 4) + 0.0 for c in f.point),
    )


def _same_surface(a, b, tol=1e-6):
    """Two faces lie on one surface (a plane, a cylinder...)."""
    from .ai.ops import selectors

    ka, kb = selectors.face_type(a), selectors.face_type(b)
    if ka != kb:
        return False
    sa, sb = a.Surface, b.Surface
    try:
        if ka == "plane":
            na = core.unit(_t(sa.Axis))
            nb = core.unit(_t(sb.Axis))
            if not core.parallel(na, nb, 1e-7):
                return False
            return abs(core.dot(core.sub(_t(sa.Position), _t(sb.Position)), na)) < tol
        if ka == "cylinder":
            if abs(sa.Radius - sb.Radius) > tol:
                return False
            if not core.parallel(_t(sa.Axis), _t(sb.Axis), 1e-7):
                return False
            axis = core.unit(_t(sa.Axis))
            gap = core.sub(_axis_point(_t(sa.Center), axis), _axis_point(_t(sb.Center), axis))
            return core.norm(gap) < 1e-5
        if ka == "cone":
            if not core.parallel(_t(sa.Axis), _t(sb.Axis), 1e-7):
                return False
            if abs(abs(sa.SemiAngle) - abs(sb.SemiAngle)) > 1e-7:
                return False
            return core.norm(core.sub(_t(sa.Apex), _t(sb.Apex))) < 1e-5
        if ka == "sphere":
            return (
                abs(sa.Radius - sb.Radius) < tol
                and core.norm(core.sub(_t(sa.Center), _t(sb.Center))) < 1e-5
            )
        if ka == "torus":
            return (
                abs(sa.MajorRadius - sb.MajorRadius) < tol
                and abs(sa.MinorRadius - sb.MinorRadius) < tol
                and core.norm(core.sub(_t(sa.Center), _t(sb.Center))) < 1e-5
            )
    except Exception:
        return False
    return False


def _line_distance(ea, eb):
    """Distance between two parallel straight edges."""
    a0 = _t(ea.Vertexes[0].Point)
    d = core.unit(_t(ea.Vertexes[-1].Point - ea.Vertexes[0].Point))
    w = core.sub(_t(eb.Vertexes[0].Point), a0)
    return core.norm(core.sub(w, core.mul(d, core.dot(w, d))))


def _extent_across(face, direction):
    """How far a flat face reaches square to a direction lying in it."""
    d = core.unit(direction)
    try:
        n = core.unit(_t(face.Surface.Axis))
    except Exception:
        return 1e9
    across = core.cross(n, d)
    ts = [core.dot(_t(v.Point), across) for v in face.Vertexes]
    return (max(ts) - min(ts)) if ts else 1e9


def _chamfer_distances(fa, fb, ea, eb):
    """(d1, d2): how far the chamfer's edges ea (on face A) and eb (on face B) are from the
    sharp edge where A's and B's planes meet."""
    na, nb = fa.normal, fb.normal
    line = core.cross(na, nb)
    if core.norm(line) < 1e-9:
        return None, None
    d = core.unit(line)
    # a point of both planes: p = (hA (nB x L) + hB (L x nA)) / |L|^2 with L = nA x nB
    p = core.mul(
        core.add(core.mul(core.cross(nb, line), fa.h), core.mul(core.cross(line, na), fb.h)),
        1.0 / core.dot(line, line),
    )

    def dist(edge):
        w = core.sub(_t(edge.Vertexes[0].Point), p)
        return core.norm(core.sub(w, core.mul(d, core.dot(w, d))))

    return dist(ea), dist(eb)


# -- prismatic and turned bases -----------------------------------------------------------------
def _face_kind(face):
    from .ai.ops import selectors

    return selectors.face_type(face)


def _levels(solid, axis_name):
    """The heights (along the axis) of the flat faces square to it, or None when some face
    is neither square to the axis nor running along it."""
    from . import draft_walls
    from .ai.ops import selectors

    d = core.AXES[axis_name]
    heights = []
    for face in solid.Faces:
        kind = _face_kind(face)
        if kind == "plane":
            n = core.unit(selectors.face_normal(face))
            if core.parallel(n, d, 1e-7):
                heights.append(core.dot(_t(face.Vertexes[0].Point), d))
                continue
            if core.square(n, d, 1e-7):
                continue
            return None
        if kind == "cylinder":
            if core.parallel(_t(face.Surface.Axis), d, 1e-7):
                continue
            return None
        try:
            if draft_walls.is_wall(face, _vec(d)):
                continue
        except Exception:
            pass
        return None
    levels = []
    for h in sorted(heights):
        if not levels or h - levels[-1] > 1e-6:
            levels.append(h)
    return levels


def _section(solid, plane, h, box):
    """The flat faces of the solid's section by the plane at height h (along the plane's
    normal)."""
    import Part

    frame = core.PLANES[plane]
    size = 4.0 * box.DiagonalLength + 20.0
    center = (box.Center.x, box.Center.y, box.Center.z)
    cx = core.dot(center, frame["x"])
    cy = core.dot(center, frame["y"])
    corner = core.from_plane(plane, cx - size / 2.0, cy - size / 2.0, h)
    face = Part.makePlane(size, size, _vec(corner), _vec(frame["n"]), _vec(frame["x"]))
    common = solid.common(face)
    return [f for f in common.Faces if f.Area > 1e-9]


def _loops_of(faces, plane):
    """[(outer loop, [inner loops])] of flat faces, in the plane's sketch coordinates."""
    out = []
    for face in faces:
        outer = face.OuterWire
        inner = [w for w in face.Wires if not w.isSame(outer)]
        out.append((_wire_loop(outer, plane), [_wire_loop(w, plane) for w in inner]))
    return out


def _wire_loop(wire, plane):
    frame = core.PLANES[plane]

    def p2(v):
        t = _t(v)
        return (core.dot(t, frame["x"]), core.dot(t, frame["y"]))

    edges = list(wire.OrderedEdges)
    if len(edges) == 1 and edges[0].isClosed():
        e = edges[0]
        if type(e.Curve).__name__ == "Circle":
            return [{"kind": "circle", "c": p2(e.Curve.Center), "r": e.Curve.Radius}]
        return [{"kind": "other", "a": p2(e.Vertexes[0].Point), "b": p2(e.Vertexes[0].Point)}]
    ends = [(e.Vertexes[0].Point, e.Vertexes[-1].Point) for e in edges]
    if len(edges) > 1:
        a, b = ends[0]
        na, nb = ends[1]
        if min((b - na).Length, (b - nb).Length) <= min((a - na).Length, (a - nb).Length):
            cur = a
        else:
            cur = b
    else:
        cur = ends[0][0]
    loop = []
    for e, (a, b) in zip(edges, ends):
        if (a - cur).Length <= (b - cur).Length:
            start, end = a, b
        else:
            start, end = b, a
        kind = type(e.Curve).__name__
        if kind in ("Line", "LineSegment"):
            loop.append({"kind": "line", "a": p2(start), "b": p2(end)})
        elif kind == "Circle":
            c = p2(e.Curve.Center)
            m = p2(e.valueAt(0.5 * (e.FirstParameter + e.LastParameter)))
            s2, e2 = p2(start), p2(end)
            ts = math.atan2(s2[1] - c[1], s2[0] - c[0])
            tm = (math.atan2(m[1] - c[1], m[0] - c[0]) - ts) % (2 * math.pi)
            te = (math.atan2(e2[1] - c[1], e2[0] - c[0]) - ts) % (2 * math.pi)
            loop.append(
                {"kind": "arc", "c": c, "r": e.Curve.Radius, "a": s2, "b": e2, "ccw": tm < te}
            )
        else:
            loop.append({"kind": "other", "a": p2(start), "b": p2(end), "what": kind})
        cur = end
    return loop


def _region_geometry(regions):
    """create_sketch geometry for [(outer, [inner])] regions, or (None, None, None) when a
    loop cannot be drawn; also the loops as plain data and a few words."""
    geometry, public, words = [], [], []
    for outer, inner in regions:
        for loop in [outer] + inner:
            clean = core.clean_loop(loop)
            item = core.loop_geometry(clean)
            if item is None:
                return None, None, None
            geometry.append(item)
            public.append(_public_loop(clean))
        text = core.describe_loop(core.clean_loop(outer))
        if inner:
            text += " with %d opening%s" % (len(inner), "" if len(inner) == 1 else "s")
        words.append(text)
    return geometry, public, ", ".join(words)


def _public_loop(loop):
    out = []
    for s in loop:
        if s["kind"] == "circle":
            out.append({"circle": [s["c"][0], s["c"][1], s["r"]]})
        elif s["kind"] == "line":
            out.append({"line": [s["a"][0], s["a"][1], s["b"][0], s["b"][1]]})
        elif s["kind"] == "arc":
            out.append(core._arc_item(s))
        else:
            out.append({"other": [s["a"][0], s["a"][1], s["b"][0], s["b"][1]]})
    return out


def _prismatic(solid, axis_name):
    """The solid as extrudes along this origin axis: the base extrude (the biggest level's
    region over the levels whose outline it covers) and the bosses / cuts that make the
    rest, or None."""
    levels = _levels(solid, axis_name)
    if levels is None or len(levels) < 2:
        return None
    plane = core.PLANE_OF_AXIS[axis_name]
    frame = core.PLANES[plane]
    sign = 1 if core.dot(frame["n"], core.AXES[axis_name]) > 0 else -1
    hs = sorted(sign * h for h in levels)  # heights along the plane's normal (XZ's is -Y)
    box = solid.BoundBox
    slabs = []
    for lo, hi in zip(hs, hs[1:]):
        faces = _section(solid, plane, 0.5 * (lo + hi), box)
        slabs.append({"lo": lo, "hi": hi, "faces": faces, "area": _area(faces)})
    if not any(s["area"] > 1e-9 for s in slabs):
        return None
    k = max(range(len(slabs)), key=lambda i: slabs[i]["area"])
    base_outline = _outline(slabs[k]["faces"])
    covered = [False] * len(slabs)
    covered[k] = True
    for step in (1, -1):
        i = k + step
        while 0 <= i < len(slabs) and _covers(base_outline, slabs[i]["faces"]):
            covered[i] = True
            i += step
    run = [i for i in range(len(slabs)) if covered[i]]
    lo, hi = slabs[run[0]]["lo"], slabs[run[-1]]["hi"]
    base_faces = slabs[k]["faces"]
    first = _op("base", base_faces, plane, lo, hi)
    if first is None:
        return None
    ops = [first]
    prism = _extrude_faces(base_faces, plane, lo, hi)
    extra = solid.cut(prism)
    missing = prism.cut(solid)
    for piece_shape, operation in ((extra, "join"), (missing, "cut")):
        for piece in piece_shape.Solids:
            if piece.Volume < 1e-9:
                continue
            got = _piece_ops(piece, plane, operation, hs[0], hs[-1])
            if got is None:
                return None
            ops += got
    return {
        "public": {
            "kind": "extrude",
            "plane": plane,
            "direction": axis_name,
            "offset": core.snap(first["offset"]),
            "distance": core.snap(hi - lo),
            "from": core.snap(lo),
            "to": core.snap(hi),
            "profile": first["loops_public"],
            "profile_words": first["words"],
            "levels": [core.snap(h) for h in hs],
        },
        "ops": ops,
        "slabs": len(slabs),
        "plane": plane,
    }


def _outline(faces):
    """The faces with their openings filled (the region inside their outer loops)."""
    import Part

    filled = []
    for f in faces:
        try:
            filled.append(Part.Face(f.OuterWire))
        except Exception:
            filled.append(f)
    return filled


def _area(faces):
    return sum(f.Area for f in faces)


def _covers(base_outline, faces):
    """The base's outline holds this level's outline and at least half of it: the base goes
    on through this level (and what this level lacks is cut out of it)."""
    import Part

    if not faces:
        return False
    outline = _outline(faces)
    a_out = _area(outline)
    a_base = _area(base_outline)
    if a_out < 0.5 * a_base:
        return False
    try:
        mine = Part.makeCompound(outline)
        base = Part.makeCompound(base_outline)
        shift = base_outline[0].CenterOfMass.sub(outline[0].CenterOfMass)
        normal = base_outline[0].Surface.Axis
        mine.translate(normal * shift.dot(normal))  # (into the base outline's plane)
        outside = mine.cut(base)
        return outside.Area <= 1e-6 * max(1.0, a_base)
    except Exception:
        return False


def _extrude_faces(faces, plane, lo, hi):
    n = core.PLANES[plane]["n"]
    solids = []
    for f in faces:
        moved = f.copy()
        h = core.dot(_t(f.CenterOfMass), n)
        moved.translate(_vec(core.mul(n, lo - h)))
        solids.append(moved.extrude(_vec(core.mul(n, hi - lo))))
    shape = solids[0]
    for s in solids[1:]:
        shape = shape.fuse(s)
    return shape if len(solids) == 1 else shape.removeSplitter()


def _op(kind, faces, plane, lo, hi):
    """One extrude of the plan: its sketch (plane, offset, geometry) and arguments."""
    loops = _loops_of(faces, plane)
    geometry, public, words = _region_geometry(loops)
    if geometry is None:
        return None
    if kind == "base":
        offset, extrude = core.base_extrude_args(lo, hi)
    else:
        offset, extrude = core.extent_args(lo, hi, "cut" if kind == "cut" else "join")
    return {
        "kind": kind,
        "plane": plane,
        "offset": offset,
        "geometry": geometry,
        "loops_public": public,
        "words": words,
        "extrude": extrude,
        "height": hi - lo,
        "lo": lo,
        "hi": hi,
        "faces": faces,
    }


def _piece_ops(piece, plane, operation, part_lo, part_hi):
    """A boss or cut piece as one extrude per height band (consecutive equal regions
    merged), or None when it is not prismatic along the plane's normal."""
    n = core.PLANES[plane]["n"]
    axis_name = core.origin_axis(n)
    levels = _levels(piece, axis_name)
    if levels is None or len(levels) < 2:
        return None
    sign = 1 if core.dot(n, core.AXES[axis_name]) > 0 else -1
    hs = sorted(sign * h for h in levels)
    box = piece.BoundBox
    bands = []
    for lo, hi in zip(hs, hs[1:]):
        faces = _section(piece, plane, 0.5 * (lo + hi), box)
        if not faces:
            continue
        if bands and abs(bands[-1]["hi"] - lo) < 1e-9 and _same_region(bands[-1]["faces"], faces):
            bands[-1]["hi"] = hi
            continue
        bands.append({"lo": lo, "hi": hi, "faces": faces})
    out = []
    for band in bands:
        lo, hi = band["lo"], band["hi"]
        op = _op(operation, band["faces"], plane, lo, hi)
        if op is None:
            return None
        if operation == "cut" and lo <= part_lo + 1e-6 and hi >= part_hi - 1e-6:
            op["extrude"] = {"through_all": True, "operation": "cut", "flip": True}
            op["offset"] = hi
        out.append(op)
    return out


def _same_region(a, b):
    """Two lists of flat faces (parallel planes) cover the same region seen along the
    normal."""
    import Part

    try:
        ca, cb = Part.makeCompound(a), Part.makeCompound(b)
        normal = a[0].Surface.Axis
        shift = a[0].CenterOfMass.sub(b[0].CenterOfMass)
        cb.translate(normal * shift.dot(normal))
        diff = ca.cut(cb).Area + cb.cut(ca).Area
        return diff <= 1e-6 * max(1.0, ca.Area)
    except Exception:
        return False


def _group_ops(ops, pattern_args=None):
    """The base first, then the bosses, then the cuts. Bosses / cuts on one plane at one
    offset with the same extrude arguments go in one step: copies of one shape on a grid or
    a circle as one extrude and a pattern (pattern_args(pattern, plane) -> (tool, args) or
    None says whether a pattern tool can make it), the others as one sketch with them all."""
    if not ops:
        return []
    buckets = {}
    for op in ops[1:]:
        key = (op["kind"], op["plane"], round(op["offset"], 6), repr(sorted(op["extrude"].items())))
        buckets.setdefault(key, []).append(op)
    out = [ops[0]]
    for members in buckets.values():
        found = _ops_pattern(members, pattern_args) if len(members) >= 2 else None
        if found is not None:
            out.append(found)
            continue
        merged = dict(members[0])
        for op in members[1:]:
            merged["geometry"] = merged["geometry"] + op["geometry"]
            merged["loops_public"] = merged["loops_public"] + op["loops_public"]
            merged["words"] = merged["words"] + ", " + op["words"]
        merged["count"] = len(members)
        out.append(merged)
    order = {"base": 0, "join": 1, "cut": 2}
    return [out[0]] + sorted(out[1:], key=lambda o: order.get(o["kind"], 3))


def _ops_pattern(members, pattern_args):
    """One extrude and a pattern for copies of one shape (moved, not turned), or None."""
    if pattern_args is None:
        return None
    plane = members[0]["plane"]
    centres = []
    for op in members:
        area = sum(f.Area for f in op["faces"])
        if area <= 0:
            return None
        c = [0.0, 0.0, 0.0]
        for f in op["faces"]:
            p = f.CenterOfMass
            for k, v in enumerate((p.x, p.y, p.z)):
                c[k] += v * f.Area / area
        x, y, _h = core.to_plane(plane, tuple(c))
        centres.append((x, y))
    x0, y0 = centres[0]
    for op, (x, y) in zip(members[1:], centres[1:]):
        moved = [core.shift_item(item, x0 - x, y0 - y) for item in op["geometry"]]
        if not core.same_items(members[0]["geometry"], moved, 1e-5):
            return None
    pattern = core.find_pattern(centres, 1e-4)
    if pattern is None:
        return None
    call = pattern_args(pattern, plane)
    if call is None:
        return None
    first_point = core.pattern_order(centres, pattern)[0]
    first = members[centres.index(first_point)]
    return dict(first, pattern=(call[0], call[1], pattern), count=len(members))


def _build_ops(chosen):
    """The solid the base's steps make (to check them against the defeatured solid)."""
    if chosen["public"]["kind"] == "revolve":
        return chosen["solid_check"]
    shape = None
    for op in chosen["ops"]:
        prism = _extrude_faces(op["faces"], op["plane"], op["lo"], op["hi"])
        if shape is None:
            shape = prism
        elif op["kind"] == "cut":
            shape = shape.cut(prism)
        else:
            shape = shape.fuse(prism)
    return shape


def _revolved(solid):
    """The solid as a profile turned about an origin axis, or None."""
    import Part

    from .ai.ops import selectors

    for axis_name in ("Z", "X", "Y"):
        d = core.AXES[axis_name]
        ok = True
        round_faces = 0
        for face in solid.Faces:
            kind = selectors.face_type(face)
            s = face.Surface
            if kind == "plane":
                n = core.unit(selectors.face_normal(face))
                if not core.parallel(n, d, 1e-7):
                    ok = False
                else:
                    for e in face.Edges:  # its edges: circles about the axis
                        if type(e.Curve).__name__ != "Circle":
                            ok = False
                        elif not _on_axis(_t(e.Curve.Center), d) or not core.parallel(
                            _t(e.Curve.Axis), d, 1e-7
                        ):
                            ok = False
            elif kind in ("cylinder", "cone", "torus"):
                anchor = _t(s.Center if kind != "cone" else s.Apex)
                if not core.parallel(_t(s.Axis), d, 1e-7) or not _on_axis(anchor, d):
                    ok = False
                round_faces += 1
            elif kind == "sphere":
                if not _on_axis(_t(s.Center), d):
                    ok = False
                round_faces += 1
            else:
                ok = False
            if not ok:
                break
        if not ok or round_faces == 0:
            continue
        # the half profile: the solid cut by the half plane that holds the axis
        plane = {"Z": "XZ", "X": "XY", "Y": "XY"}[axis_name]
        frame = core.PLANES[plane]
        radial = frame["y"] if axis_name == "X" else frame["x"]
        box = solid.BoundBox
        reach = box.DiagonalLength + 10.0
        corners = [(box.XMin, box.YMin, box.ZMin), (box.XMax, box.YMax, box.ZMax)]
        lo = min(core.dot(c, d) for c in corners) - 5.0
        hi = max(core.dot(c, d) for c in corners) + 5.0
        # a rectangle from the axis outward (radial) and along it (d)
        pts = [
            core.mul(d, lo),
            core.add(core.mul(d, lo), core.mul(radial, reach)),
            core.add(core.mul(d, hi), core.mul(radial, reach)),
            core.mul(d, hi),
        ]
        half = Part.Face(Part.makePolygon([_vec(p) for p in pts + pts[:1]]))
        faces = [f for f in solid.common(half).Faces if f.Area > 1e-9]
        if not faces:
            continue
        loops = _loops_of(faces, plane)
        geometry, public, words = _region_geometry(loops)
        if geometry is None:
            continue
        try:
            check = Part.makeCompound(faces).revolve(_vec((0, 0, 0)), _vec(d), 360)
            if not check.Solids:
                check = Part.makeSolid(check)
        except Exception:
            check = solid
        return {
            "public": {
                "kind": "revolve",
                "plane": plane,
                "axis": axis_name,
                "angle": 360,
                "profile": public,
                "profile_words": words,
                "geometry": geometry,
            },
            "ops": [],
            "slabs": 0,
            "solid_check": check,
        }
    return None


def _on_axis(point, d):
    """The point lies on the origin axis d."""
    off = core.sub(point, core.mul(d, core.dot(point, d)))
    return core.norm(off) < 1e-6


def _pattern_words(pattern):
    if pattern["kind"] == "rectangular":
        if pattern["count2"] > 1:
            return "a %d x %d grid, %s x %s mm apart" % (
                pattern["count"],
                pattern["count2"],
                core.fmt(pattern["spacing"]),
                core.fmt(pattern["spacing2"]),
            )
        return "a row of %d, %s mm apart" % (pattern["count"], core.fmt(pattern["spacing"]))
    if pattern["kind"] == "circular":
        return "%d around a circle of diameter %s%s" % (
            pattern["count"],
            core.fmt(2 * pattern["radius"]),
            "" if pattern["full"] else " (%s degrees apart)" % core.fmt(pattern["step"]),
        )
    return "a row of %d, %s mm apart" % (pattern["count"], core.fmt(pattern["spacing"]))


def _public_pattern(pattern, plane, offset):
    out = {"kind": pattern["kind"], "plane": plane, "offset": core.snap(offset)}
    for key in ("count", "spacing", "count2", "spacing2", "radius", "step", "full", "axis"):
        if key in pattern:
            value = pattern[key]
            out[key] = core.snap(value) if isinstance(value, float) else value
    if "center" in pattern:
        out["center"] = [core.snap(c) for c in pattern["center"]]
    if "origin" in pattern:
        out["origin"] = [core.snap(c) for c in pattern["origin"]]
    return out

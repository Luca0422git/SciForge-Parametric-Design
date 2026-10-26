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
DEFEATURE_BUDGET = 15.0  # seconds of defeaturing tries before the rest is left in the base
DESCRIBE_BUDGET = 30.0  # seconds: past this, optional work (more readings, edges) is skipped
MAX_SLABS = 60  # levels along one axis beyond which that axis is not read (a free-form part)
MAX_PIECES = 400  # bosses + cuts beyond which a reading is dropped (it is not the part's)
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
    if not options.get("_in_frame"):
        try:
            frame = turned_frame(shape)
        except Exception as exc:
            warn("recognize: the part's own frame not found (%s)" % exc)
            frame = None
        if frame is not None:
            return _describe_turned(shape, options, frame, started)
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


def turned_frame(shape):
    """The rotation (3 x 3 rows, world from local) of the frame a part turned away from the
    origin planes is drawn in; None when the part lines up with the origin's X, Y and Z
    (most of its flat and round faces square to or along them)."""
    from .ai.ops import selectors

    dirs = []  # [direction, area]
    for face in shape.Faces:
        kind = selectors.face_type(face)
        try:
            if kind == "plane":
                d = selectors.face_normal(face)
            elif kind in ("cylinder", "cone", "torus"):
                d = _t(face.Surface.Axis)
            else:
                continue
            d = core.canonical_direction(d)
        except Exception:
            continue
        for item in dirs:
            if core.parallel(item[0], d, 1e-6):
                item[1] += face.Area
                break
        else:
            dirs.append([d, face.Area])
    if not dirs:
        return None
    total = sum(w for _d, w in dirs)
    lined_up = sum(w for d, w in dirs if core.origin_axis(d, 1e-6))
    if lined_up >= 0.5 * total:
        return None  # (its slanted faces are features: a chamfer, a wedge...)
    dirs.sort(key=lambda item: -item[1])
    d1 = dirs[0][0]
    d2 = next((d for d, _w in dirs[1:] if core.square(d, d1, 1e-6)), None)
    if d2 is None:
        world = min(core.AXES.values(), key=lambda a: abs(core.dot(a, d1)))
        d2 = core.sub(world, core.mul(d1, core.dot(world, d1)))
    rot = core.closest_frame(d1, d2)
    if all(abs(rot[i][j] - (1.0 if i == j else 0.0)) < 1e-9 for i in range(3) for j in range(3)):
        return None
    return rot


def _describe_turned(shape, options, rot, started):
    """describe() of a part turned away from the origin planes: read in its own frame (the
    plan builds it there, lined up with the origin), then a last step turns it into place."""
    import FreeCAD as App

    m = App.Matrix()
    for i in range(3):
        for j in range(3):
            setattr(m, "A%d%d" % (i + 1, j + 1), rot[j][i])  # the inverse turn (transpose)
    local = shape.copy()
    local.transformShape(m)
    out = describe(local, dict(options, _in_frame=True, _refs_shape=shape))
    rx, ry, rz = core.euler_xyz(rot)
    out["summary"] = summary(shape)
    out["frame"] = {
        "rotation": [[core.snap(v, 1e-12) for v in row] for row in rot],
        "rx": rx,
        "ry": ry,
        "rz": rz,
    }
    first = next(
        (step for step in out["plan"] if step["tool"] in ("extrude", "revolve") and "id" in step),
        None,
    )
    if first is not None:
        taken = set(options.get("taken_ids") or ()) | {st.get("id") for st in out["plan"]}
        plan = core.Plan(taken)
        ident = plan.new_id("move_copy")
        out["plan"].append(
            {
                "step": len(out["plan"]) + 1,
                "tool": "move_copy",
                "args": {
                    "bodies": [first["id"]],
                    "move_type": "free",
                    "rx": rx,
                    "ry": ry,
                    "rz": rz,
                    "pivot": [0, 0, 0],
                },
                "why": "Turn the finished part into its place (it was built lined up with the "
                "origin planes): about X %s, then Y %s, then Z %s degrees, about the origin."
                % (core.fmt(rx), core.fmt(ry), core.fmt(rz)),
                "features": [],
                "id": ident,
                "uses": {"bodies[0]": first["step"]},
            }
        )
    out["notes"].insert(
        0,
        "The part is turned away from the origin planes: the plan builds it lined up with "
        "them (the base's and the features' numbers are in that frame; the face selectors "
        "pick the original's faces) and its last step turns it into place (Move, free: X %s, "
        "Y %s, Z %s degrees about the origin); compare with the original after that step."
        % (core.fmt(rx), core.fmt(ry), core.fmt(rz)),
    )
    out["timing"] = round(time.time() - started, 3)
    return out


def summary(shape):
    """Volume, area, box, counts and the census of surface kinds."""
    from .ai.ops import selectors

    surfaces = {}
    for face in shape.Faces:
        try:
            kind = selectors.face_type(face)
        except Exception:
            kind = "other"
        surfaces[kind] = surfaces.get(kind, 0) + 1
    box = shape.BoundBox
    if set(surfaces) - {"plane", "cylinder", "cone", "sphere", "torus"}:
        try:  # (FreeCAD's quick box holds a free-form face's control points: measure it)
            tight = shape.optimalBoundingBox(False, False)
            if tight.isValid():
                box = tight
        except Exception:
            pass
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
        self.started = time.time()
        self.edges_off = None  # why the chamfers' and fillets' edges are not looked for
        self.listed = set()  # faces already in an `unrecognized` entry of their own

    def late(self):
        """Past the time budget: skip what is optional."""
        return time.time() - self.started > DESCRIBE_BUDGET

    # -- helpers ------------------------------------------------------------------------------
    def new_id(self):
        self.counter += 1
        return "F%d" % self.counter

    def face_refs(self, indexes):
        """Selectors of these faces of the original solid (geometry_facts' stable refs)."""
        if self.refs is None:
            from .ai import geometry_facts

            target = self.shape
            world = self.options.get("_refs_shape")
            if world is not None and world.Solids:  # (a turned part: the real part's faces,
                target = max(world.Solids, key=lambda sol: sol.Volume)  # same order)
            try:
                self.refs = geometry_facts.stable_refs(target, "faces")
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
        free = self._free_form(holes + chamfers + blends)
        if free:
            # no extrude or revolve makes these faces: the base cannot be read, so the
            # features are not taken off (defeaturing such parts can take minutes)
            removed = {
                "base": self.shape,
                "ok": {g["id"] for g in holes + chamfers + blends},
                "accepted": holes + chamfers + blends,
            }
            self.edges_off = "the part has free-form faces"
            self.unrecognized.append(
                {
                    "faces": self.face_refs(free),
                    "why": "%d free-form face(s) (B-spline, swept or offset surfaces): no "
                    "extrude or revolve of lines and arcs makes them" % len(free),
                }
            )
            self.listed.update(free)
            self.notes.append(
                "The part has %d free-form face(s) (listed in unrecognized): its base shape "
                "is neither an extrude nor a revolve; build it yourself (look at render and "
                "query_geometry), then follow the rest of the plan." % len(free)
            )
            base = {"public": {"kind": "none"}, "ops": [], "faces": [], "volume_error": 0.0}
            self.base_shape = self.shape
        else:
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
        for b in getattr(self, "bends", []):
            item = {k: v for k, v in b.items() if not k.startswith("_")}
            item["faces"] = self.face_refs(b["_faces"])
            item["steps"] = list(base["public"].get("steps", []))
            item["in_profile"] = base["public"]["kind"] != "none"
            features.append(item)
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
        missing = [
            f.index for f in self.facts if f.index not in explained and f.index not in self.listed
        ]
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

    def _free_form(self, groups):
        """Faces no feature took that no extrude or revolve of lines and arcs makes
        (B-spline, swept or offset surfaces; a flat B-spline is a tapered wall)."""
        used = set()
        for g in groups:
            used.update(g["_faces"])
        out = []
        for f in self.facts:
            if f.index in used or f.kind in ("plane", "cylinder", "cone", "sphere", "torus"):
                continue
            if _flat_normal(f.face) is not None:
                continue
            out.append(f.index)
        return out

    # -- holes ----------------------------------------------------------------------------------
    def find_holes(self):
        """Concave round faces that go all the way round, grouped by their axis line (one
        group while only air lies between them: the same hole through both sides of a
        channel), with the coaxial faces that make a counterbore, a countersink, a drill point
        or a flat bottom."""
        bores = {}  # (line key, radius) -> [face indexes]
        for f in self.facts:
            if f.kind == "cylinder" and f.concave and f.radius:
                key = (_line_key(f), round(f.radius, 5))
                bores.setdefault(key, []).append(f.index)
        holes = []
        used = set()
        lines = {}
        for (line, radius), idx in bores.items():
            for run in self._bore_runs(idx):
                span = sum(self.facts[i].span or 0 for i in run)
                if span < 2 * math.pi - 1e-4:
                    continue  # a part of a round face (a notch, an inside corner): no hole
                lines.setdefault(line, []).append((radius, run))
        for line, bore_list in lines.items():
            bore_list.sort(key=lambda b: (b[0], min(b[1])))
            for n, (radius, idx) in enumerate(bore_list):
                if any(i in used for i in idx):
                    continue  # (the wider bore of a counterbore already read)
                bigger = [
                    b
                    for b in bore_list[n + 1 :]
                    if b[0] > radius + 1e-9 and not any(i in used for i in b[1])
                ]
                hole = self._hole(idx, bigger)
                if hole is None:
                    continue
                used.update(hole["_faces"])
                holes.append(hole)
        return holes

    def _bore_runs(self, idx):
        """The faces of one bore (one line, one radius) in runs along its axis that no
        material separates (two blind holes drilled from both sides are two holes)."""
        if len(idx) < 2:
            return [list(idx)]
        f0 = self.facts[idx[0]]
        axis, origin = f0.axis, f0.point
        spans = sorted(self._extent([i], axis, origin) + (i,) for i in idx)
        runs = [[spans[0]]]
        for a, b, i in spans[1:]:
            top = max(x[1] for x in runs[-1])
            if a > top + 1e-6:
                mid = core.add(origin, core.mul(axis, 0.5 * (top + a)))
                try:
                    between = self.shape.isInside(_vec(mid), 1e-6, False)
                except Exception:
                    between = False
                if between:  # material between: another hole
                    runs.append([(a, b, i)])
                    continue
            runs[-1].append((a, b, i))
        return [[i for _a, _b, i in run] for run in runs]

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

    def _rim_extent(self, indexes, axis, origin):
        """(lowest, highest) along the axis of the faces' edges, sampled (a rim on a slanted
        face is an ellipse whose top is no corner)."""
        lo, hi = self._extent(indexes, axis, origin)
        for i in indexes:
            for e in self.facts[i].face.Edges:
                try:
                    pts = e.discretize(24)
                except Exception:
                    continue
                for p in pts:
                    t = core.dot(core.sub(_t(p), origin), axis)
                    lo, hi = min(lo, t), max(hi, t)
        return lo, hi

    def _hole(self, idx, bigger):
        f0 = self.facts[idx[0]]
        axis, origin, radius = f0.axis, f0.point, f0.radius
        t0, t1 = self._extent(idx, axis, origin)
        r0, r1 = self._rim_extent(idx, axis, origin)
        if r1 - t1 > 1e-6 or t0 - r0 > 1e-6:  # a rim that is not square to the axis
            t0, t1 = r0, r1
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
        if through and far["kind"] == "open" and self._overreaches(origin, axis, radius, far, into):
            # it opens into a hollow (a port into a pipe): through all would drill the far
            # wall too, so it is drilled to its far end (the bottom is in the hollow)
            through = False
            far = dict(far, kind="bottom")
            depth = self._nice_depth(origin, axis, radius, far["t"], into, depth)
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
        if through and far["kind"] in ("counterbore", "countersink"):
            # the other end widens too: the hole tool makes one end; the other end's
            # recess is a short hole of its own, drilled from the other side
            if far["kind"] == "counterbore":
                hole["far_recess"] = {
                    "diameter": self.value(2 * far["radius"]),
                    "depth": self.value(far["depth"]),
                    "point": core.add(origin, core.mul(axis, far["t_open"])),
                    "into": [core.snap(-c) for c in into],
                }
            else:
                self.notes.append(
                    "Hole %s is countersunk at its other end too: the plan makes the first "
                    "end only; add the other countersink after it." % hole["id"]
                )
        return hole

    def _overreaches(self, origin, axis, radius, far, into):
        """Whether a through hole's Hole step (through all) would cut more of the part
        beyond its far end: the part goes on there (only then is it checked, with a boolean)
        and the bore's cylinder carried on meets material."""
        import Part

        far_point = core.add(origin, core.mul(axis, far["t"]))
        box = self.shape.BoundBox
        beyond = max(
            core.dot(core.sub((x, y, z), far_point), into)
            for x in (box.XMin, box.XMax)
            for y in (box.YMin, box.YMax)
            for z in (box.ZMin, box.ZMax)
        )
        if beyond <= 1e-6:
            return False
        try:
            cyl = Part.makeCylinder(
                radius * (1.0 - 1e-6), beyond + 1.0, _vec(far_point), _vec(into)
            )
            return cyl.common(self.shape).Volume > 1e-6 * max(1.0, cyl.Volume)
        except Exception:
            return False

    def _nice_depth(self, origin, axis, radius, t_far, into, depth):
        """A rounder depth for a hole that ends in a hollow (15 for 13.38) when the bore
        carried on that far meets no material."""
        import Part

        far_point = core.add(origin, core.mul(axis, t_far))
        for unit in (5.0, 1.0):
            nice = math.ceil(depth / unit - 1e-9) * unit
            extra = nice - depth
            if extra < 1e-9:
                return depth
            try:
                cyl = Part.makeCylinder(radius * (1.0 - 1e-6), extra, _vec(far_point), _vec(into))
                if cyl.common(self.shape).Volume <= 1e-6 * max(1.0, cyl.Volume):
                    return nice
            except Exception:
                pass
        return depth

    def _hole_end(self, idx, axis, origin, radius, t, side, bigger, faces):
        """What closes or opens the hole's bore at height t: open (the part's face), bottom
        (a flat disc), drill_point (a cone to a point), counterbore (a shoulder and a wider
        bore that opens), countersink (a cone that widens to the face)."""
        out = {"kind": "open", "t": t, "t_open": t}
        sign = 1.0 if side == "high" else -1.0
        neighbours = []
        for i in idx:  # the faces met along an edge that reaches this end of the bore
            for key in self.topo.face_edges[i]:
                for j in self.topo.edge_faces.get(key, []):
                    if j in idx or j in neighbours:
                        continue
                    try:
                        pts = self.topo.edges[key].discretize(12)
                    except Exception:
                        continue
                    ts = [core.dot(core.sub(_t(p), origin), axis) for p in pts]
                    if min(abs(min(ts) - t), abs(max(ts) - t)) < 1e-5:
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
        # bends of a sheet-like wall (an inside and an outside round face on one axis, the
        # wall's thickness apart) are part of the shape, not fillets: they stay in the base
        self.bends = []
        cylinders = [i for i in blend if self.facts[i].kind == "cylinder"]
        for i in cylinders:
            fi = self.facts[i]
            if not fi.concave:
                continue
            for j in cylinders:
                fj = self.facts[j]
                if j == i or fj.concave or fj.radius <= fi.radius + 1e-6:
                    continue
                if any(j in b["_faces"] for b in self.bends):
                    continue
                if abs(fi.span - fj.span) > 1e-4 or not _coaxial(fi, fj):
                    continue
                if not self._overlap_along_axis(i, j):
                    continue
                self.bends.append(
                    {
                        "kind": "bend",
                        "radius": self.value(fi.radius),
                        "thickness": self.value(fj.radius - fi.radius),
                        "angle": self.value(math.degrees(fi.span), 1e-4),
                        "axis": [core.snap(c) for c in fi.axis],
                        "_faces": [i, j],
                    }
                )
                break
        # a thin wall's bends stay in the base: they become arcs of its profile (exact and
        # quick); as fillets, OpenCASCADE's defeaturing took 40 s on a 14-face sheet and its
        # fillet builder crashed on bends meeting at a corner
        for b in self.bends:
            b["id"] = self.new_id()
            for k in b["_faces"]:
                blend.pop(k, None)
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

    def _overlap_along_axis(self, i, j):
        """The two coaxial faces face each other across the wall (they share a stretch of
        their axis)."""
        f = self.facts[i]
        a0, a1 = self._extent([i], f.axis, f.point)
        b0, b1 = self._extent([j], f.axis, f.point)
        return min(a1, b1) - max(a0, b0) > 1e-6

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
        if len(f.face.Wires) > 1 or len(f.face.Edges) > 12:
            return None  # (a chamfer is a narrow strip: no openings, a few edges)
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
        began = time.time()

        def attempt(candidates):
            if not candidates:
                return
            if time.time() - began > DEFEATURE_BUDGET:  # (a pathological shape: stop trying)
                rejected.extend(candidates)
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

    def _partial_blends(self, base, groups):
        """The round faces taken for fillets that do not run along the whole edge they would
        round on the base (the curved edge of a thin rib): those are part of the shape."""
        out = []
        for g in groups:
            if g["kind"] != "fillet":
                continue
            faces = g["_faces"]
            if not all(self.facts[i].kind == "cylinder" for i in faces):
                continue
            axis = self.facts[faces[0]].axis
            if not all(core.parallel(self.facts[i].axis, axis, 1e-6) for i in faces):
                continue
            extent = 0.0
            for i in faces:
                a0, a1 = self._extent([i], axis, self.facts[i].point)
                extent += a1 - a0
            try:
                names = self._sharp_edges(base, [g])
            except Exception:
                continue
            length = 0.0
            for name in names:
                e = base.getElement(name)
                if type(e.Curve).__name__ in ("Line", "LineSegment"):
                    d = _t(e.Vertexes[-1].Point - e.Vertexes[0].Point)
                    if core.parallel(d, axis, 1e-6):
                        length += e.Length
            if length > 1.5 * extent + 1e-6:
                out.append(g)
        return out

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
        partial = self._partial_blends(base, ok)
        if partial:
            ok = [g for g in ok if g not in partial]
            base = self._defeature(ok, start) if ok else start
            if base is None:
                base, ok = start, []
            try:
                refined = base.removeSplitter()
                if not refined.isNull() and refined.isValid() and len(refined.Solids) == 1:
                    base = refined.Solids[0]
            except Exception:
                pass
            for g in partial:
                self.notes.append(
                    "The round face%s of %s (radius %s) cover%s only a part of the edge it "
                    "would round: read as part of the shape (a curved edge of a rib or a "
                    "boss), not as a fillet."
                    % (
                        "s" if len(g["_faces"]) > 1 else "",
                        g["id"],
                        core.fmt(g["radius"]),
                        "" if len(g["_faces"]) > 1 else "s",
                    )
                )
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
        an origin axis; else prismatic along an axis some faces of which belong to bosses or
        cuts along another (a keyway in a shaft)."""
        best = self._best_prismatic(solid, False)
        revolved = None
        drafted = best is not None and any(op.get("taper") for op in best[1]["ops"])
        if best is None or len(best[1]["ops"]) >= 3 or drafted:
            try:
                revolved = _revolved(solid)
            except Exception as exc:
                warn("recognize: revolve not read (%s)" % exc)
        if best is None and revolved is None:
            if self.late():
                self.notes.append(
                    "Time budget spent: the readings along an axis with features along the "
                    "others (a keyway in a shaft) were not tried."
                )
            else:
                best = self._best_prismatic(solid, True)
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

    def _best_prismatic(self, solid, lenient):
        """(score, reading) of the best extrude reading along X, Y or Z, or None."""
        best = None
        for axis in ("Z", "Y", "X"):
            try:
                found = _prismatic(solid, axis, lenient)
            except Exception as exc:
                warn("recognize: prismatic along %s not read (%s)" % (axis, exc))
                found = None
            if found is None:
                continue
            # fewest steps, then the least volume added / taken by them (a round boss on a
            # block is a boss along Z, not the block's side profile with its corners cut off)
            steps = len(_group_ops(found["ops"]))
            moved = round(found.get("feature_volume", 0.0) / max(solid.Volume, 1e-9), 4)
            score = (steps, moved, len(found["ops"]), found["slabs"], ("Z", "Y", "X").index(axis))
            if best is None or score < best[0]:
                best = (score, found)
        return best

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
                core.sketch_args(
                    public["plane"], 0.0, core.name_items(public.pop("geometry"), "profile")
                ),
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
            if op.get("shell") and not first:
                made = self._plan_shell(op, base, plan, features)
                if made:
                    steps += made
                    continue
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
            if first:
                prefix = "base"
            elif kind != "cut":
                prefix = "boss"
            else:
                prefix = "cut" if op["extrude"].get("through_all") else "pocket"
            geometry = core.name_items(op["geometry"], prefix)
            sketch = plan.add(
                "create_sketch", core.sketch_args(plane, offset, geometry), why_sketch
            )
            args = {"profile": sketch}
            args.update(op["extrude"])
            draft = (
                " with a %s degree draft" % core.fmt(abs(op["taper"])) if op.get("taper") else ""
            )
            if first:
                why = "Extrude it %s mm%s: the base shape." % (core.fmt(op["height"]), draft)
                fids = []
            else:
                fid = self.new_id()
                fids = [fid]
                if kind != "cut":
                    feature_kind = "boss"
                elif len(op["geometry"]) == op.get("count", 1) and all(
                    "slot" in item for item in op["geometry"]
                ):
                    feature_kind = "slot"
                elif op["extrude"].get("through_all"):
                    feature_kind = "cut"
                else:
                    feature_kind = "pocket"
                features.append(
                    {
                        "id": fid,
                        "kind": feature_kind,
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
                    why = "Cut it %s mm into the part%s." % (core.fmt(op["height"]), draft)
                else:
                    why = "Extrude it %s mm%s, joined to the part: a boss." % (
                        core.fmt(op["height"]),
                        draft,
                    )
                if op.get("taper"):
                    features[-1]["draft"] = abs(op["taper"])
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

    def _plan_shell(self, op, base, plan, features):
        """The shell tool for a cut marked as a shell: the open face(s) of the base picked
        on the base as built (its top / bottom along the extrude), the thickness."""
        shell = op["shell"]
        n = core.PLANES[op["plane"]]["n"]
        axis_name = core.origin_axis(n)
        sign = 1 if core.dot(n, core.AXES[axis_name]) > 0 else -1
        picks = []
        for side in ("top", "bottom"):
            if shell["open"] not in (side, "both"):
                continue
            outward = n if side == "top" else core.mul(n, -1.0)
            value = "max" if (side == "top") == (sign > 0) else "min"
            picks.append(
                {
                    "normal": [core.snap(c) for c in outward],
                    "at": {"axis": axis_name.lower(), "value": value},
                    "count": 1,
                }
            )
        faces = picks[0] if len(picks) == 1 else {"any_of": picks, "count": len(picks)}
        fid = self.new_id()
        plan.add(
            "shell",
            {"faces": faces, "thickness": shell["thickness"]},
            "Shell it %s mm inside, the %s face%s taken away (an open %s)."
            % (
                core.fmt(shell["thickness"]),
                "top and bottom" if shell["open"] == "both" else shell["open"],
                "s" if shell["open"] == "both" else "",
                "tube" if shell["open"] == "both" else "box",
            ),
            [fid],
        )
        features.append(
            {
                "id": fid,
                "kind": "shell",
                "thickness": shell["thickness"],
                "open": shell["open"],
                "steps": [len(plan.steps)],
                "faces": [],
                "_faces": [],
            }
        )
        return [len(plan.steps)]

    def plan_holes(self, holes, plan, features):
        """One hole step per group of equal holes on one plane: a pattern step when they make
        a grid / circle / row the pattern tool can repeat, else one sketch with every centre.
        A hole that widens at both ends gets its other end as a short hole of its own."""
        recesses = []
        for h in holes:
            far = h.get("far_recess")
            if not far:
                continue
            recesses.append(
                {
                    "id": h["id"] + "b",
                    "kind": "hole",
                    "recess_of": h["id"],
                    "diameter": far["diameter"],
                    "depth": far["depth"],
                    "through": False,
                    "bottom": "bottom",
                    "axis": far["into"],
                    "start": [self.value(c) for c in far["point"]],
                    "_axis": h["_axis"],
                    "_start_point": far["point"],
                    "_faces": [],
                    "start_face": None,
                }
            )
        if recesses:  # first: the hole tool aims at material at each centre
            self._plan_hole_groups(recesses, plan, features)
        self._plan_hole_groups(holes, plan, features)

    def _plan_hole_groups(self, holes, plan, features):
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
            geometry = core.name_items([{"circle": [x, y, r]} for x, y in drawn], "hole")
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
            if core.dot(tuple(h0["axis"]), core.PLANES[plane]["n"]) > 0.5:
                args["flip"] = True  # drilled along the sketch's normal (from under the part)
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
        if h.get("far_recess"):
            far = h["far_recess"]
            out["other_end"] = {"counterbore": {"diameter": far["diameter"], "depth": far["depth"]}}
        if h.get("recess_of"):
            out["recess_of"] = h["recess_of"]
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
        if self._edges_skipped(chamfers, features):
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

    def _edges_skipped(self, groups, features):
        """When the edges are not looked for (a free-form part, the time budget spent): the
        chamfers / fillets listed without plan steps. True when so."""
        if self.edges_off is None and self.late():
            self.edges_off = "the time budget was spent"
        if not self.edges_off:
            return False
        if not getattr(self, "_edges_noted", False):
            self._edges_noted = True
            self.notes.append(
                "The chamfers' and fillets' edges were not looked for (%s): they are listed "
                "without plan steps; pick their edges with query_geometry." % self.edges_off
            )
        for g in groups:
            item = {"id": g["id"], "kind": g["kind"]}
            for key in ("radius", "distance", "distance2"):
                if key in g:
                    item[key] = g[key]
            item["faces"] = self.face_refs(g["_faces"])
            item["steps"] = []
            item["_faces"] = list(g["_faces"])
            features.append(item)
        return True

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
        if self._edges_skipped(blends, features):
            return
        by_radius = {}
        for b in blends:
            by_radius.setdefault(b["radius"], []).append(b)
        radii = sorted(by_radius, key=lambda r: -r)
        groups = [by_radius[r] for r in radii]
        first_shape = None
        for k, group in enumerate(groups):
            later = [b for g in groups[k:] for b in g]
            earlier = [b for g in groups[:k] for b in g]
            if k and first_shape is not None and not self._touch(group, earlier):
                # the earlier fillets do not touch these: their edges are the same on the
                # part without any fillet (one defeaturing less: ~0.1 s per face)
                shape = first_shape
            else:
                shape = self._defeature(later)
            if k == 0:
                first_shape = shape
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

    def _touch(self, groups_a, groups_b):
        """Whether a face of one set of blends shares a corner with a face of the other."""
        corners = set()
        for g in groups_b:
            for i in g["_faces"]:
                for v in self.facts[i].face.Vertexes:
                    corners.add(v.hashCode())
        for g in groups_a:
            for i in g["_faces"]:
                for v in self.facts[i].face.Vertexes:
                    if v.hashCode() in corners:
                        return True
        return False

    def _shape_index(self, shape):
        """(faces, coarse surface keys, edge hash -> face indexes) of a shape, made once."""
        cache = self.__dict__.setdefault("_indexes", {})
        found = cache.get(id(shape))
        if found is not None and found[0] is shape:
            return found[1]
        faces = shape.Faces
        keys = [_coarse_key(f) for f in faces]
        owners = {}
        for fi, face in enumerate(faces):
            for e in face.Edges:
                lst = owners.setdefault(e.hashCode(), [])
                if fi not in lst:
                    lst.append(fi)
        cache[id(shape)] = (shape, (faces, keys, owners))
        return faces, keys, owners

    def _key_of(self, i):
        f = self.facts[i]
        if not hasattr(f, "_coarse"):
            f._coarse = _coarse_key(f.face)
        return f._coarse

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
        faces, keys, owners = self._shape_index(shape)
        by_key = {}  # coarse key -> [(pair number, joined face)]
        for n, (_i, joined, _reach) in enumerate(pairs):
            for j in joined:
                by_key.setdefault(self._key_of(j), []).append((n, j))
        names = []
        for ei, edge in enumerate(shape.Edges, start=1):
            own = owners.get(edge.hashCode(), [])
            if len(own) != 2:
                continue
            a, b = own
            on_a = by_key.get(keys[a])
            on_b = by_key.get(keys[b])
            if not on_a or not on_b:
                continue
            both = sorted({n for n, _j in on_a} & {n for n, _j in on_b})
            mid = None
            for n in both:
                i, _joined, reach = pairs[n]
                if not any(_same_surface(self.facts[j].face, faces[a]) for m, j in on_a if m == n):
                    continue
                if not any(_same_surface(self.facts[j].face, faces[b]) for m, j in on_b if m == n):
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


def _coarse_key(face):
    """A coarse key of a face's surface (kind, direction and size at 2 decimals): faces on
    one surface share it (checked exactly afterwards with _same_surface)."""
    kind = _face_kind(face)
    try:
        if kind == "bspline":
            flat = _flat_normal(face)
            if flat is None:
                return ("bspline", id(face))
            d = core.canonical_direction(flat)
            h = core.dot(_t(face.Vertexes[0].Point), d)
            return ("plane",) + tuple(round(c, 2) + 0.0 for c in d) + (round(h, 1) + 0.0,)
        s = face.Surface
        if kind == "plane":
            d = core.canonical_direction(_t(s.Axis))
            h = core.dot(_t(s.Position), d)
            return ("plane",) + tuple(round(c, 2) + 0.0 for c in d) + (round(h, 1) + 0.0,)
        if kind in ("cylinder", "cone", "torus"):
            d = core.canonical_direction(_t(s.Axis))
            size = s.Radius if kind == "cylinder" else (s.MajorRadius if kind == "torus" else 0.0)
            return (kind,) + tuple(round(c, 2) + 0.0 for c in d) + (round(size, 1) + 0.0,)
        if kind == "sphere":
            return ("sphere", round(s.Radius, 1) + 0.0)
    except Exception:
        pass
    return (kind, id(face))


def _surface_key(face):
    """A coarse key of a face's surface (kind and direction) to bucket faces by."""
    kind = _face_kind(face)
    try:
        if kind == "bspline":
            flat = _flat_normal(face)
            if flat is not None:
                d = core.canonical_direction(flat)
                return ("plane",) + tuple(round(c, 3) + 0.0 for c in d)
        if kind in ("plane", "cylinder", "cone", "torus"):
            d = core.canonical_direction(_t(face.Surface.Axis))
            return (kind,) + tuple(round(c, 3) + 0.0 for c in d)
    except Exception:
        pass
    return (kind,)


def _coaxial(a, b):
    """Two round faces turn about one axis line."""
    if a.axis is None or b.axis is None or not core.parallel(a.axis, b.axis, 1e-7):
        return False
    return core.norm(core.sub(a.point, b.point)) < 1e-5


def _line_key(f):
    return (
        tuple(round(c, 5) + 0.0 for c in f.axis),
        tuple(round(c, 4) + 0.0 for c in f.point),
    )


def _same_surface(a, b, tol=1e-6):
    """Two faces lie on one surface (a plane, a cylinder...)."""
    from .ai.ops import selectors

    ka, kb = selectors.face_type(a), selectors.face_type(b)
    if "bspline" in (ka, kb) and {ka, kb} <= {"bspline", "plane"}:
        na = _flat_normal(a) if ka == "bspline" else core.unit(_t(a.Surface.Axis))
        nb = _flat_normal(b) if kb == "bspline" else core.unit(_t(b.Surface.Axis))
        if na is None or nb is None or not core.parallel(na, nb, 1e-7):
            return False
        gap = core.sub(_t(a.Vertexes[0].Point), _t(b.Vertexes[0].Point))
        return abs(core.dot(gap, na)) < tol
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


def _levels(solid, axis_name, allow_taper=False):
    """The heights (along the axis) of the flat faces square to it, or None when some face
    is neither square to the axis nor running along it (nor, with allow_taper, leaning
    from it by a draft angle: a flat face at an angle, a cone about a line along it)."""
    got = _walls(solid, axis_name, allow_taper)
    return None if got is None else got[0]


def _walls(solid, axis_name, allow_taper=False, lenient=False, ranges=None):
    """(levels, [taper angles in degrees, one per leaning wall]) or None. lenient: flat,
    round and conical faces that fit no rule (up to a quarter of the area) are passed over
    (a boss or a cut along another axis: a piece of its own) instead of refusing the axis,
    their ends along it made levels (so a keyway's length is a band of its own) and added to
    `ranges`."""
    from . import draft_walls
    from .ai.ops import selectors

    d = core.AXES[axis_name]
    heights = []
    tapers = []
    straight = 0
    skipped = 0.0
    for face in solid.Faces:
        kind = _face_kind(face)
        flat = _flat_normal(face) if kind == "bspline" else None
        if flat is not None:
            kind = "plane"
        if kind == "plane":
            n = flat if flat is not None else core.unit(selectors.face_normal(face))
            if core.parallel(n, d, 1e-7):
                heights.append(core.dot(_t(face.Vertexes[0].Point), d))
                continue
            if core.square(n, d, 1e-7):
                straight += 1
                continue
            c = abs(core.dot(n, d))
            if allow_taper and c < math.sin(math.radians(60)):
                tapers.append(math.degrees(math.asin(c)))
                ts = [core.dot(_t(v.Point), d) for v in face.Vertexes]
                heights += [min(ts), max(ts)]  # (a draft may start where no flat face is)
                continue
            if lenient:
                span = _range_along(face, d)
                heights += span
                skipped += face.Area
                if ranges is not None and span:
                    ranges.append(span)
                continue
            return None
        if kind == "cylinder":
            if core.parallel(_t(face.Surface.Axis), d, 1e-7):
                straight += 1
                continue
            if lenient:
                span = _range_along(face, d)
                heights += span
                skipped += face.Area
                if ranges is not None and span:
                    ranges.append(span)
                continue
            return None
        if kind == "cone" and allow_taper:
            if core.parallel(_t(face.Surface.Axis), d, 1e-7):
                tapers.append(math.degrees(abs(face.Surface.SemiAngle)))
                continue
            if lenient:
                span = _range_along(face, d)
                heights += span
                skipped += face.Area
                if ranges is not None and span:
                    ranges.append(span)
                continue
            return None
        try:
            if draft_walls.is_wall(face, _vec(d)):
                straight += 1
                continue
        except Exception:
            pass
        return None
    if skipped > 0.25 * solid.Area:
        return None
    levels = []
    for h in sorted(heights):
        if not levels or h - levels[-1] > 1e-6:
            levels.append(h)
    if tapers and straight and allow_taper == "pure":
        return None  # (a band of one draft cannot have straight walls too)
    return levels, tapers


def _range_along(face, d):
    """[lowest, highest] of the face's boundary along the direction d."""
    try:
        pts = [v.Point for v in face.Vertexes]
        for e in face.Edges:
            pts += e.discretize(16)
        ts = [core.dot(_t(p), d) for p in pts]
        return [min(ts), max(ts)] if ts else []
    except Exception:
        return []


def _flat_normal(face):
    """The normal of a free-form face that is in fact flat (SciForge's tapered extrude makes
    its walls as flat B-spline faces), or None."""
    try:
        plane = face.findPlane(1e-7)
    except Exception:
        return None
    if plane is None:
        return None
    try:
        return core.unit(_t(plane.Axis))
    except Exception:
        return None


def _caps_at(solid, plane, h):
    """The solid's flat faces square to the plane's normal at height h."""
    n = core.PLANES[plane]["n"]
    out = []
    for face in solid.Faces:
        if _face_kind(face) != "plane":
            continue
        try:
            axis = _t(face.Surface.Axis)
        except Exception:
            continue
        if not core.parallel(axis, n, 1e-7):
            continue
        if abs(core.dot(_t(face.Vertexes[0].Point), n) - h) < 1e-6:
            out.append(face)
    return out


def _tapered(solid, plane, lo, hi, box, outline=False):
    """Whether the band between lo and hi changes its section (or only its outline, the
    openings filled) with the height: walls on a draft."""
    delta = 1e-3 * (hi - lo)
    a = _section(solid, plane, lo + delta, box)
    b = _section(solid, plane, hi - delta, box)
    if not a or not b:
        return False
    if outline:
        a, b = _outline(a), _outline(b)
    return not _same_region(a, b)


def _taper_op(kind, solid, plane, lo, hi, tapers):
    """One extrude with a draft (taper) for a band whose walls all lean by one angle: the
    profile is the solid's own flat face at the sketch's end (exact), the taper's sign from
    whether it widens on its way. None when the walls lean by different angles or some do
    not lean."""
    angle = tapers[0]
    if any(abs(t - angle) > 1e-6 for t in tapers):
        return None
    box = solid.BoundBox
    delta = 1e-3 * (hi - lo)
    low = _area(_section(solid, plane, lo + delta, box))
    high = _area(_section(solid, plane, hi - delta, box))
    straight = _section(solid, plane, 0.5 * (lo + hi), box)
    if not straight:
        return None
    start = lo if kind != "cut" else hi
    caps = _caps_at(solid, plane, start)
    if not caps:
        return None
    op = _op(kind, caps, plane, lo, hi)
    if op is None:
        return None
    widening = high > low if kind != "cut" else low > high
    taper = core.snap(angle if widening else -angle, 1e-7)
    if kind == "base":
        op["offset"] = lo
        op["extrude"] = {"distance": core.snap(hi - lo)}
    op["extrude"]["taper"] = taper
    op["solid"] = solid
    op["taper"] = taper
    return op


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
        elif abs(e.Length - (end - start).Length) <= 1e-7 * max(1.0, e.Length):
            loop.append({"kind": "line", "a": p2(start), "b": p2(end)})  # (a straight spline)
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


def _prismatic(solid, axis_name, lenient=False):
    """The solid as extrudes along this origin axis: the base extrude (the biggest level's
    region over the levels whose outline it covers) and the bosses / cuts that make the
    rest, or None. lenient: some faces may belong to bosses / cuts along another axis."""
    ranges = []  # (lenient) where the faces of features along other axes are
    walls = _walls(solid, axis_name, allow_taper=True, lenient=lenient, ranges=ranges)
    if walls is None or len(walls[0]) < 2:
        return None
    levels, tapers = walls
    plane = core.PLANE_OF_AXIS[axis_name]
    frame = core.PLANES[plane]
    sign = 1 if core.dot(frame["n"], core.AXES[axis_name]) > 0 else -1
    hs = sorted(sign * h for h in levels)  # heights along the plane's normal (XZ's is -Y)
    if len(hs) - 1 > MAX_SLABS:
        return None
    ranges = [sorted((sign * a, sign * b)) for a, b in ranges]
    box = solid.BoundBox
    if (
        tapers
        and len(hs) == 2
        and _tapered(solid, plane, hs[0], hs[1], box)
        and _walls(solid, axis_name, allow_taper="pure") is not None
    ):  # one extrude on a draft (with straight walls too: a drafted pocket in a block)
        op = _taper_op("base", solid, plane, hs[0], hs[1], tapers)
        if op is None:
            return None
        return _prismatic_result(op, [op], 1, plane, axis_name, hs)
    slabs = []
    for lo, hi in zip(hs, hs[1:]):
        faces = _section(solid, plane, 0.5 * (lo + hi), box)
        slabs.append({"lo": lo, "hi": hi, "faces": faces, "area": _area(faces)})
    if not any(s["area"] > 1e-9 for s in slabs):
        return None

    def touched(i):  # a feature along another axis passes through this level
        a, b = slabs[i]["lo"], slabs[i]["hi"]
        return any(r[0] < b - 1e-6 and r[1] > a + 1e-6 for r in ranges)

    clean = [i for i in range(len(slabs)) if slabs[i]["area"] > 1e-9 and not touched(i)]
    k = max(clean or range(len(slabs)), key=lambda i: slabs[i]["area"])
    base_outline = _outline(slabs[k]["faces"])
    covered = [False] * len(slabs)
    covered[k] = True

    def goes_on(i):  # the base goes on through this level
        if _covers(base_outline, slabs[i]["faces"]):
            return True
        return touched(i) and _mostly_covers(base_outline, slabs[i]["faces"])

    def drafted(i):  # its outline leans (a drafted pocket inside it does not count)
        if not tapers:
            return False
        return _tapered(solid, plane, slabs[i]["lo"], slabs[i]["hi"], box, outline=True)

    for step in (1, -1):
        i = k + step
        while 0 <= i < len(slabs) and goes_on(i) and not drafted(i):
            covered[i] = True  # (a drafted level is a boss / cut of its own, not the base)
            i += step
    run = [i for i in range(len(slabs)) if covered[i]]
    lo, hi = slabs[run[0]]["lo"], slabs[run[-1]]["hi"]
    base_faces = slabs[k]["faces"]
    if tapers and _tapered(solid, plane, slabs[k]["lo"], slabs[k]["hi"], box):
        if drafted(k):
            return None  # a drafted base with more on it: not read (yet)
        base_faces = _outline(base_faces)  # its openings lean: cuts of their own
    else:
        base_faces = _fill_copies(base_faces)  # copies of one opening: a cut and a pattern
    first = _op("base", base_faces, plane, lo, hi)
    if first is None:
        return None
    ops = [first]
    prism = _extrude_faces(base_faces, plane, lo, hi)
    extra = solid.cut(prism)
    missing = prism.cut(solid)
    if len(extra.Solids) + len(missing.Solids) > MAX_PIECES:
        return None
    cache = {}  # (moved copies of one piece are read once)
    for piece_shape, operation in ((extra, "join"), (missing, "cut")):
        for piece in piece_shape.Solids:
            if piece.Volume < 1e-9:
                continue
            got = None
            for other in _piece_planes(piece, prism, plane):
                if other == plane:
                    got = _piece_ops(
                        piece, plane, operation, hs[0], hs[-1], lo, (solid, prism), cache
                    )
                else:  # a boss / cut along another axis (the holes in a channel's sides)
                    span = _span(solid, other)
                    got = _piece_ops(
                        piece, other, operation, span[0], span[1], None, (solid, prism), cache
                    )
                if got is not None:
                    break
            if got is None:
                return None
            ops += got
    _through_cuts(ops, solid)
    _mark_shell(ops, solid)
    result = _prismatic_result(first, ops, len(slabs), plane, axis_name, hs)
    result["feature_volume"] = extra.Volume + missing.Volume
    return result


def _on_boundary(shape, face):
    """A point inside the face lies on the shape's surface."""
    p = face.valueAt(*_inner_uv(face))
    return shape.isInside(p, 1e-6, True) and not shape.isInside(p, 1e-6, False)


def _piece_planes(piece, region, plane):
    """The origin planes to read a boss / cut piece on, best first: the one its open sides
    face when they all face one way (its faces on the base extrude's surface, `region`: where
    a cut opens to the air or a boss meets the rest of the part), then the base's plane, then
    the others."""
    order = [plane] + [p for p in ("XY", "XZ", "YZ") if p != plane]
    axes = set()
    try:
        for face in piece.Faces:
            if not _on_boundary(region, face):
                continue  # (on the part's own surface: a wall or the floor)
            n = _flat_normal(face)
            axis = None if n is None else core.origin_axis(n)
            if axis is None:
                return order
            axes.add(axis)
    except Exception:
        return order
    if len(axes) == 1:
        best = core.PLANE_OF_AXIS[axes.pop()]
        order.remove(best)
        order.insert(0, best)
    return order


def _through_cuts(ops, solid):
    """A cut that may go through the whole part without taking anything more (a hole in one
    flange of a channel that lines up with one in the other) is made through all, from the
    part's outer side: equal through cuts then go in one sketch (deduplicated)."""
    for op in ops[1:]:
        if op["kind"] != "cut" or op["extrude"].get("through_all") or op.get("taper"):
            continue
        lo, hi = _span(solid, op["plane"])
        if op["lo"] <= lo + 1e-6 and op["hi"] >= hi - 1e-6:
            continue
        try:
            prism = _extrude_faces(op["faces"], op["plane"], lo - 1.0, hi + 1.0)
            if prism.common(solid).Volume > 1e-9:
                continue  # (it would cut material the part has)
        except Exception:
            continue
        op["extrude"] = {"through_all": True, "operation": "cut", "flip": True}
        op["offset"] = hi
        op["through_extended"] = True


def _span(solid, plane):
    """(lowest, highest) of the solid along the plane's normal (its tight box: the plain one
    is padded by the tolerances, 10.000025 for a 10)."""
    n = core.PLANES[plane]["n"]
    box = _tight_box(solid)
    corners = [
        (x, y, z)
        for x in (box.XMin, box.XMax)
        for y in (box.YMin, box.YMax)
        for z in (box.ZMin, box.ZMax)
    ]
    ts = [core.dot(c, n) for c in corners]
    return min(ts), max(ts)


def _tight_box(shape):
    """The shape's bounding box without the tolerance padding (made once per shape)."""
    cache = _tight_box.__dict__.setdefault("cache", {})
    key = id(shape)
    got = cache.get(key)
    if got is not None and got[0] is shape:
        return got[1]
    try:
        box = shape.optimalBoundingBox(False, False)
    except Exception:
        box = shape.BoundBox
    if len(cache) > 64:
        cache.clear()
    cache[key] = (shape, box)
    return box


def _mark_shell(ops, solid):
    """A base whose only cut is its own outline moved inward by one thickness t, open on one
    side (or both) and t thick at the other, is Fusion's Shell: mark the cut so the plan
    makes it with the shell tool (the face(s) taken away, the thickness)."""
    if len(ops) != 2 or ops[1]["kind"] != "cut" or ops[1].get("taper") or ops[0].get("taper"):
        return
    base, cut = ops
    lo, hi = base["lo"], base["hi"]
    open_top = abs(cut["hi"] - hi) < 1e-6
    open_bottom = abs(cut["lo"] - lo) < 1e-6
    if not (open_top or open_bottom):
        return
    try:
        outer = [f for f in base["faces"]]
        if len(outer) != 1 or len(outer[0].Wires) != 1 or len(cut["faces"]) != 1:
            return
        region = cut["faces"][0]
        # the thickness: from the bottom (or top) left standing, else from the side walls
        if open_top and not open_bottom:
            t = cut["lo"] - lo
        elif open_bottom and not open_top:
            t = hi - cut["hi"]
        else:
            t = None
        inner_wire = outer[0].OuterWire
        guess = t
        if guess is None:  # open both ends: the wall's thickness, outline to opening
            moved_wire = region.OuterWire.copy()
            normal = outer[0].Surface.Axis
            shift = outer[0].CenterOfMass.sub(region.CenterOfMass)
            moved_wire.translate(normal * shift.dot(normal))
            guess = inner_wire.distToShape(moved_wire)[0]
        if guess is None or guess <= 1e-6:
            return
        offset = inner_wire.makeOffset2D(-guess, 2, False, False, False)
        import Part

        shrunk = Part.Face(offset)
        moved = region.copy()
        normal = outer[0].Surface.Axis
        shift = outer[0].CenterOfMass.sub(region.CenterOfMass)
        moved.translate(normal * shift.dot(normal))
        diff = shrunk.cut(moved).Area + moved.cut(shrunk).Area
        if diff > 1e-6 * max(1.0, outer[0].Area):
            return
    except Exception:
        return
    cut["shell"] = {
        "thickness": core.snap(guess),
        "open": "both" if (open_top and open_bottom) else ("top" if open_top else "bottom"),
    }


def _prismatic_result(first, ops, slabs, plane, axis_name, hs):
    public = {
        "kind": "extrude",
        "plane": plane,
        "direction": axis_name,
        "offset": core.snap(first["offset"]),
        "distance": core.snap(first["hi"] - first["lo"]),
        "from": core.snap(first["lo"]),
        "to": core.snap(first["hi"]),
        "profile": first["loops_public"],
        "profile_words": first["words"],
        "levels": [core.snap(h) for h in hs],
    }
    if first.get("taper"):
        public["taper"] = first["taper"]
    return {"public": public, "ops": ops, "slabs": slabs, "plane": plane}


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


def _fill_copies(faces):
    """The faces with the openings that are copies of one another filled (a plate's grid of
    square holes): those become cuts of their own, which the plan repeats with a pattern.
    Openings of a kind of their own stay in the base's sketch."""
    import Part

    def key(wire):
        box = wire.BoundBox
        return (
            len(wire.Edges),
            round(wire.Length, 4),
            round(box.XLength, 4),
            round(box.YLength, 4),
            round(box.ZLength, 4),
        )

    def inner(f):
        outer = f.OuterWire
        return [w for w in f.Wires if not w.isSame(outer)]

    counts = {}
    for f in faces:
        for w in inner(f):
            counts[key(w)] = counts.get(key(w), 0) + 1
    if not any(n >= 2 for n in counts.values()):
        return faces
    out = []
    for f in faces:
        openings = inner(f)
        keep = [w for w in openings if counts.get(key(w), 0) < 2]
        if len(keep) == len(openings):
            out.append(f)
            continue
        try:
            filled = Part.Face(f.OuterWire)
            if keep:
                filled = filled.cutHoles(keep)
            out.append(filled if filled.isValid() else f)
        except Exception:
            out.append(f)
    return out


def _mostly_covers(base_outline, faces):
    """This level's region fills nearly all of the base's outline (a boss along another axis
    may stick out of it: a piece of its own)."""
    import Part

    if not faces:
        return False
    try:
        mine = Part.makeCompound(_outline(faces))
        base = Part.makeCompound(base_outline)
        shift = base_outline[0].CenterOfMass.sub(faces[0].CenterOfMass)
        normal = base_outline[0].Surface.Axis
        mine.translate(normal * shift.dot(normal))
        return mine.common(base).Area >= 0.9 * base.Area
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


def _piece_ops(piece, plane, operation, part_lo, part_hi, base_lo=None, within=None, cache=None):
    """A boss or cut piece as one extrude per height band (consecutive equal regions
    merged), or None when it is not prismatic along the plane's normal. within: (the solid,
    the base extrude) for a piece that opens onto a round face (_open_piece_op). cache: a
    dict shared by the pieces of one reading; a moved copy of a piece read before (a grid of
    square holes) takes that one's bands, moved."""
    n = core.PLANES[plane]["n"]
    axis_name = core.origin_axis(n)
    key = None
    if cache is not None:
        bb = piece.BoundBox
        key = (plane, operation, len(piece.Faces), round(piece.Volume, 6))
        key += tuple(round(v, 6) for v in (bb.XLength, bb.YLength, bb.ZLength))
        bands = _moved_bands(cache.get(key), piece, n)
        if bands is not None:
            return _band_ops(bands, plane, operation, part_lo, part_hi, base_lo)
    walls = _walls(piece, axis_name, allow_taper=True)
    if walls is None or len(walls[0]) < 2:
        if within is None:
            return None
        return _open_piece_op(piece, within[0], within[1], plane, operation, part_lo, part_hi)
    levels, tapers = walls
    if tapers and _walls(piece, axis_name, allow_taper="pure") is None:
        return None  # some walls lean and some do not: no single draft makes it
    sign = 1 if core.dot(n, core.AXES[axis_name]) > 0 else -1
    hs = sorted(sign * h for h in levels)
    box = piece.BoundBox
    if tapers:  # a boss or pocket on a draft: one band only
        if len(hs) != 2:
            return None
        op = _taper_op(operation, piece, plane, hs[0], hs[1], tapers)
        return None if op is None else [op]
    bands = []
    for lo, hi in zip(hs, hs[1:]):
        faces = _section(piece, plane, 0.5 * (lo + hi), box)
        if not faces:
            continue
        if bands and abs(bands[-1]["hi"] - lo) < 1e-9 and _same_region(bands[-1]["faces"], faces):
            bands[-1]["hi"] = hi
            continue
        bands.append({"lo": lo, "hi": hi, "faces": faces})
    if key is not None:
        cache[key] = (piece, bands)
    return _band_ops(bands, plane, operation, part_lo, part_hi, base_lo)


def _moved_bands(hit, piece, n):
    """The bands of a piece read before (hit: (piece, bands)), moved onto this piece when it
    is a moved copy of that one, else None."""
    if hit is None:
        return None
    ref, ref_bands = hit
    try:
        shift = piece.BoundBox.Center.sub(ref.BoundBox.Center)
        moved = sorted(_t(v.Point + shift) for v in ref.Vertexes)
        here = sorted(_t(v.Point) for v in piece.Vertexes)
        if len(moved) != len(here) or abs(ref.Area - piece.Area) > 1e-6 * max(1.0, ref.Area):
            return None
        if any(core.norm(core.sub(p, q)) > 1e-6 for p, q in zip(moved, here)):
            return None  # (the same size, another shape)
    except Exception:
        return None
    dn = core.dot(_t(shift), n)
    out = []
    for band in ref_bands:
        faces = []
        for f in band["faces"]:
            g = f.copy()
            g.translate(shift)
            faces.append(g)
        out.append({"lo": band["lo"] + dn, "hi": band["hi"] + dn, "faces": faces})
    return out


def _band_ops(bands, plane, operation, part_lo, part_hi, base_lo=None):
    """The extrudes of a piece's bands (see _piece_ops), or None."""
    bands = list(bands)
    base_lo = part_lo if base_lo is None else base_lo
    if operation == "join" and bands and bands[-1]["hi"] <= base_lo + 1e-6:
        bands.reverse()  # below the base: the band touching it first, so each one joins
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


def _open_piece_op(piece, solid, region, plane, operation, part_lo, part_hi):
    """A cut that opens onto a round or slanted face of the part (a keyway or a flat on a
    shaft) or a boss standing on one (a port on a pipe): the piece's faces on the part's
    surface all run along the plane's normal, but for one flat end (a cut's floor, a boss's
    top). The extrude goes from that end out of the part (a cut) or into it down to where the
    boss meets it: [op] when that takes or adds exactly the piece, else None. region: the
    base extrude (the piece's faces on its surface are where it opens)."""
    n = core.PLANES[plane]["n"]
    d = core.AXES[core.origin_axis(n)]
    ends, open_ts = [], []
    try:
        for face in piece.Faces:
            if _on_boundary(region, face):
                # where the cut opens to the air, or the boss meets the rest of the part
                pts = [v.Point for v in face.Vertexes]
                for e in face.Edges:
                    pts += e.discretize(16)
                open_ts += [core.dot(_t(q), n) for q in pts]
                continue
            kind = _face_kind(face)
            flat = _flat_normal(face) if kind in ("plane", "bspline") else None
            if flat is not None and core.parallel(flat, d, 1e-7):
                ends.append(face)
            elif flat is not None and core.square(flat, d, 1e-7):
                pass  # a wall along the normal
            elif kind == "cylinder" and core.parallel(_t(face.Surface.Axis), d, 1e-7):
                pass
            else:
                return None
    except Exception:
        return None
    if not ends or not open_ts:
        return None
    heights = {round(core.dot(_t(f.Vertexes[0].Point), n), 7) for f in ends}
    if len(heights) != 1:
        return None
    h = heights.pop()
    if min(open_ts) >= h - 1e-6:  # it opens above its end
        above = True
        far = part_hi if operation == "cut" else max(open_ts)
    elif max(open_ts) <= h + 1e-6:
        above = False
        far = part_lo if operation == "cut" else min(open_ts)
    else:
        return None
    # a boss may start anywhere inside the part: a round value (the origin plane, ...)
    tries = [far] if operation == "cut" else core.rounder_values(far, not above)
    tol = 1e-7 * solid.Volume + 1e-6
    found = None
    for value in tries:
        lo, hi = (h, value) if above else (value, h)
        if hi - lo < 1e-6:
            continue
        try:
            prism = _extrude_faces(ends, plane, lo, hi)
            if piece.cut(prism).Volume > tol:
                continue  # the extrude would miss some of the piece
            more = prism.common(solid) if operation == "cut" else prism.cut(solid)
            if more.Volume > tol:
                continue  # it would take (add) more than the piece
        except Exception:
            continue
        found = (lo, hi)
        break
    if found is None:
        return None
    lo, hi = found
    op = _op(operation, ends, plane, lo, hi)
    if op is None:
        return None
    if operation == "cut" and lo <= part_lo + 1e-6 and hi >= part_hi - 1e-6:
        op["extrude"] = {"through_all": True, "operation": "cut", "flip": True}
        op["offset"] = hi
    return [op]


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
        unique = []  # (the same cut through all twice: a hole in each flange of a channel)
        for op in members:
            if not any(core.same_items(op["geometry"], u["geometry"], 1e-6) for u in unique):
                unique.append(op)
        members = unique
        found = _ops_pattern(members, pattern_args) if len(members) >= 2 else None
        if found is not None:
            out.append(found)
            continue
        sets = []  # regions that touch go in separate sketches (one sketch would join them)
        for op in members:
            for group in sets:
                if not any(_touching(op, other) for other in group):
                    group.append(op)
                    break
            else:
                sets.append([op])
        for group in sets:
            merged = dict(group[0])
            for op in group[1:]:
                merged["geometry"] = merged["geometry"] + op["geometry"]
                merged["loops_public"] = merged["loops_public"] + op["loops_public"]
                merged["words"] = merged["words"] + ", " + op["words"]
            merged["count"] = len(group)
            out.append(merged)
    order = {"base": 0, "join": 1, "cut": 2}
    return [out[0]] + sorted(out[1:], key=lambda o: order.get(o["kind"], 3))


def _touching(a, b):
    """Two extrudes' sketch regions (on one plane at one height) meet at an edge or a
    point."""
    try:
        ba, bb = _op_box(a), _op_box(b)
        if not ba.intersect(bb):
            return False  # (far apart: no distance to work out)
        return _op_compound(a).distToShape(_op_compound(b))[0] < 1e-6
    except Exception:
        return True


def _op_compound(op):
    import Part

    if op.get("_compound") is None:
        op["_compound"] = Part.makeCompound(op["faces"])
    return op["_compound"]


def _op_box(op):
    """The op's faces' box, a little larger (made once)."""
    if op.get("_box") is None:
        box = _op_compound(op).BoundBox
        box.enlarge(1e-5)
        op["_box"] = box
    return op["_box"]


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
    joins, cuts = [], []  # (all at once: the bosses join before any cut, as in the plan)
    for op in chosen["ops"]:
        if op.get("solid") is not None:
            prism = op["solid"]
        else:
            prism = _extrude_faces(op["faces"], op["plane"], op["lo"], op["hi"])
        if shape is None:
            shape = prism
        elif op["kind"] == "cut":
            cuts.append(prism)
        else:
            joins.append(prism)
    if joins:
        shape = shape.fuse(joins)
    if cuts:
        shape = shape.cut(cuts)
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

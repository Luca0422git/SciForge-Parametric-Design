# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline for meshes (builder at-recognize, beta 3): a mesh body (STL, OBJ, 3MF) of a
simple part read the way recognize.describe() reads a solid, so an AI can rebuild it with a
timeline. Luca (2026-10-26): "mesh to parametric ... for non complex parts, i want a nicer
option to make real parametric objects." No Qt.

How a mesh is read:
  1. the mesh becomes a solid with SciForge's own Convert Mesh (insert.solid_from_mesh,
     Prismatic: the triangles that lie in one plane are merged into one flat face; round
     faces stay thin flat strips);
  2. the round regions are found: strips of thin faces that meet at small angles along
     parallel edges; a cylinder is fitted to each (least squares: its axis is the strips'
     direction, its circle is fitted to the corners seen along it): radius, axis, centre;
  3. the strips that go all the way round on the inside are holes: they are closed (their
     rims taken out of the flat faces);
  4. what is left is rebuilt exactly along the origin axis it is prismatic along: a section
     per level, the runs of corners that lie on a fitted circle turned into arcs, every
     number rounded the way a person reads it (a 5.98 mm hole is 6, the measured value is
     kept beside it), the levels extruded;
  5. the holes are cut back as true cylinders, and recognize.describe() reads the result.

What it cannot read (cones, spheres and free-form regions of a mesh, a part that is not
prismatic once its holes are closed) is said in the notes, never guessed: describe() of the
faceted solid is answered instead, with its round regions listed as not recognized.
"""

import math

from . import log, warn
from . import recognize
from . import recognize_core as core

SOFT = 35.0  # degrees: two faces of a mesh meeting at less than this are one round region
POSITION_TOL = 0.01  # mm: how far a rounded position may be from the measured one


def describe_mesh(mesh, options=None):
    """recognize.describe()'s dict for a mesh (Mesh.Mesh, or an object with a .Mesh)."""
    options = dict(options or {})
    mesh = getattr(mesh, "Mesh", mesh)
    if mesh is None or getattr(mesh, "CountFacets", 0) == 0:
        raise recognize.RecognizeError("There is no mesh to describe (no triangles).")
    notes = [
        "Read from a mesh of %d triangles: sizes are rounded the way a person reads them (the "
        "measured value is given beside each)." % mesh.CountFacets
    ]
    from . import insert

    try:
        closed = mesh.isSolid()
    except Exception:
        closed = True
    if not closed:
        return _empty(
            mesh,
            "The mesh is not closed (it has holes or loose triangles), so it is no solid and "
            "cannot be read: repair it first (MESH tab > Repair), then try again.",
        )
    try:
        faceted = insert.solid_from_mesh(mesh, "Prismatic")
        if not faceted.isValid() or not all(sh.isClosed() for sh in faceted.Shells):
            raise ValueError("the triangles do not close into a valid solid")
    except Exception as exc:
        out = _empty(mesh, "The mesh could not become a solid: %s" % exc)
        return out
    try:
        clean, measured, more = rebuild_exact(faceted)
        notes += more
    except Exception as exc:
        import traceback

        warn("recognize_mesh: %s\n%s" % (exc, traceback.format_exc()))
        clean, measured = None, []
        notes.append("The mesh's round regions could not be fitted (%s)." % exc)
    opts = dict(options, source="mesh")
    if clean is None:
        notes.append(
            "The part is not prismatic along X, Y or Z once its holes are closed (or a round "
            "region is not a cylinder): read as the faceted solid; its round regions are "
            "listed as not recognized."
        )
        out = recognize.describe(faceted, opts)
    else:
        out = recognize.describe(clean, opts)
        _add_measured(out, measured)
    out["notes"] = notes + out["notes"]
    out["summary"]["mesh"] = {"triangles": mesh.CountFacets, "volume": round(mesh.Volume, 6)}
    log("recognize_mesh: %d triangles -> %s" % (mesh.CountFacets, out["base"].get("kind")))
    return out


def _empty(mesh, why):
    box = mesh.BoundBox
    return {
        "summary": {
            "volume": round(mesh.Volume, 6),
            "area": round(mesh.Area, 6),
            "bbox": [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax],
            "size": [box.XLength, box.YLength, box.ZLength],
            "solids": 0,
            "faces": 0,
            "edges": 0,
            "surfaces": {},
            "mesh": {"triangles": mesh.CountFacets},
        },
        "base": {"kind": "none"},
        "features": [],
        "plan": [],
        "unrecognized": [{"faces": [], "why": why}],
        "confidence": 0.0,
        "notes": [why],
    }


def _t(v):
    return (v.x, v.y, v.z)


def _vec(t):
    import FreeCAD as App

    return App.Vector(float(t[0]), float(t[1]), float(t[2]))


# -- round regions ------------------------------------------------------------------------------
def strips(solid):
    """The round regions of a faceted solid: [{"faces": [indexes], "axis", "center" (a point
    of the axis), "radius", "rms", "concave", "full", "t0", "t1"}] (cylinders only)."""
    faces = solid.Faces
    normals = []
    for f in faces:
        u0, u1, v0, v1 = f.ParameterRange
        normals.append(core.unit(_t(f.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1)))))
    owners = {}
    edges = {}
    for i, f in enumerate(faces):
        for e in f.Edges:
            key = e.hashCode()
            lst = owners.setdefault(key, [])
            if i not in lst:
                lst.append(i)
            edges[key] = e
    soft = {}  # face -> [(other face, edge direction)]
    limit = math.cos(math.radians(SOFT))
    for key, pair in owners.items():
        if len(pair) != 2:
            continue
        i, j = pair
        c = core.dot(normals[i], normals[j])
        if c >= 1 - 1e-9 or c < limit:
            continue
        e = edges[key]
        if type(e.Curve).__name__ not in ("Line", "LineSegment"):
            continue
        d = core.canonical_direction(_t(e.Vertexes[-1].Point - e.Vertexes[0].Point))
        soft.setdefault(i, []).append((j, d))
        soft.setdefault(j, []).append((i, d))
    seen = set()
    found = []
    for start in soft:
        if start in seen:
            continue
        group, dirs, todo = [], [], [start]
        seen.add(start)
        while todo:
            k = todo.pop()
            group.append(k)
            for j, d in soft.get(k, []):
                dirs.append(d)
                if j not in seen:
                    seen.add(j)
                    todo.append(j)
        if len(group) < 3:
            continue
        for part in _split_group(solid, group, soft):
            part_dirs = [d for k in part for j, d in soft.get(k, []) if j in part]
            if len(part) < 3 or not part_dirs:
                continue
            axis = part_dirs[0]
            if any(not core.parallel(axis, d, 2e-3) for d in part_dirs):
                continue  # not a cylinder (a cone, a sphere...): left as it is
            fitted = _fit(solid, part, axis, normals)
            if fitted is not None:
                found.append(fitted)
    return found


def _split_group(solid, group, soft):
    """The round strips of a group of faces met at small angles: a big flat face that runs
    on smoothly from a strip (the side of a plate after its rounded corner) is no part of
    it; without such faces the group falls apart into its strips."""
    faces = solid.Faces
    areas = sorted(faces[i].Area for i in group)
    typical = areas[len(areas) // 2]
    small = {i for i in group if faces[i].Area <= 4.0 * typical}
    if len(small) == len(group):
        return [group]
    parts = []
    seen = set()
    for start in sorted(small):
        if start in seen:
            continue
        part, todo = [], [start]
        seen.add(start)
        while todo:
            k = todo.pop()
            part.append(k)
            for j, _d in soft.get(k, []):
                if j in small and j not in seen:
                    seen.add(j)
                    todo.append(j)
        parts.append(sorted(part))
    return parts


def _fit(solid, group, axis, normals):
    faces = solid.Faces
    pts = []
    for i in group:
        for v in faces[i].Vertexes:
            pts.append(_t(v.Point))
    name = core.origin_axis(axis, 2e-3)
    if name:
        axis = core.AXES[name]
    ex = core.unit(core.cross(axis, (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)))
    ey = core.cross(axis, ex)
    flat = [(core.dot(p, ex), core.dot(p, ey)) for p in pts]
    circle = core.fit_circle(flat)
    if circle is None:
        return None
    cx, cy, r = circle
    rms = math.sqrt(sum((math.hypot(x - cx, y - cy) - r) ** 2 for x, y in flat) / len(flat))
    if rms > max(1e-3, 2e-3 * r):
        return None
    center = core.add(core.mul(ex, cx), core.mul(ey, cy))
    # inside or outside: a face's normal against the way out from the axis
    f0 = faces[group[0]]
    c0 = _t(f0.CenterOfMass)
    radial = core.sub(core.sub(c0, center), core.mul(axis, core.dot(core.sub(c0, center), axis)))
    concave = core.dot(normals[group[0]], radial) < 0
    angles = sorted(math.atan2(y - cy, x - cx) for x, y in flat)
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 2 * math.pi - angles[-1]]
    full = max(gaps) < math.radians(SOFT + 5)
    ts = [core.dot(p, axis) for p in pts]
    return {
        "faces": sorted(group),
        "axis": axis,
        "center": center,
        "radius": r,
        "rms": rms,
        "concave": concave,
        "full": full,
        "t0": min(ts),
        "t1": max(ts),
    }


# -- the exact part -----------------------------------------------------------------------------
def rebuild_exact(faceted):
    """(exact solid or None, [measured values], [notes]) from a faceted solid: the holes
    closed, the rest rebuilt from fitted sections, the holes cut back as true cylinders."""
    found = strips(faceted)
    holes = [s for s in found if s["concave"] and s["full"]]
    notes = []
    closed = faceted
    hole_rims = []
    if holes:
        closed, kept, hole_rims = _close_holes(faceted, holes)
        if len(kept) != len(holes):
            notes.append(
                "%d of %d holes of the mesh could not be closed; they stay in the faceted "
                "part." % (len(holes) - len(kept), len(holes))
            )
        holes = kept
    others = [s for s in found if s not in holes]
    _regularize(holes)
    exact = _exact_prism(closed, others)
    if exact is None:
        exact = _exact_revolve(closed)
        if exact is not None:
            notes.append(
                "Read as a turned part: its half profile was taken through a row of the "
                "mesh's corners and its lines and arcs fitted."
            )
    if exact is None:
        return None, [], notes
    measured = []
    for h in holes:
        cut = _hole_solid(h, exact)
        if cut is None:
            notes.append("A hole of measured diameter %.4g was not rebuilt." % (2 * h["radius"]))
            continue
        exact = exact.cut(cut["solid"])
        measured.append(cut["measured"])
    try:
        refined = exact.removeSplitter()
        if refined.isValid() and len(refined.Solids) == 1:
            exact = refined.Solids[0]
    except Exception:
        pass
    for s in others:
        measured.append(
            {
                "kind": "round",
                "radius": core.round_measured(s["radius"])[0],
                "measured_radius": round(s["radius"], 4),
            }
        )
    return exact, measured, notes


def _regularize(holes):
    """Equal holes on one plane that make a pattern (a bolt circle, a grid) on the mesh are
    put exactly where the pattern says (its numbers rounded), so the plan can repeat one."""
    groups = {}
    for h in holes:
        key = (
            round(2 * h["radius"], 1),
            tuple(round(c, 3) for c in h["axis"]),
            round(h["t0"], 1),
            round(h["t1"], 1),
        )
        groups.setdefault(key, []).append(h)
    for group in groups.values():
        if len(group) < 2:
            continue
        axis = group[0]["axis"]
        ex = core.unit(core.cross(axis, (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)))
        name = core.origin_axis(axis, 1e-6)
        if name:  # the sketch plane's own x / y, so rounded numbers are the sketch's
            frame = core.PLANES[core.PLANE_OF_AXIS[name]]
            ex = frame["x"]
        ey = core.cross(axis, ex)
        pts = [(core.dot(h["center"], ex), core.dot(h["center"], ey)) for h in group]
        pattern = core.find_pattern(pts, 0.02)
        if pattern is None:
            continue
        for h, (x, y) in zip(group, core.ideal_points(pts, pattern, POSITION_TOL)):
            h["center"] = core.add(core.mul(ex, x), core.mul(ey, y))
            h["ideal"] = True


def _close_holes(faceted, holes):
    """(solid without the holes, holes closed, rims): each hole's strip (and its flat bottom)
    taken out and its rims closed in the flat faces around it."""
    import Part

    faces = faceted.Faces
    owners = {}
    for i, f in enumerate(faces):
        for e in f.Edges:
            owners.setdefault(e.hashCode(), set()).add(i)
    in_hole = {}
    for k, h in enumerate(holes):
        for i in h["faces"]:
            in_hole[i] = k
    # a flat bottom: a face whose outer loop is all hole edges
    for k, h in enumerate(holes):
        keys = {e.hashCode() for i in h["faces"] for e in faces[i].Edges}
        for i, f in enumerate(faces):
            if i in in_hole:
                continue
            outer = {e.hashCode() for e in f.OuterWire.Edges}
            if outer and outer <= keys and len(f.Wires) == 1:
                in_hole[i] = k
                h["faces"] = sorted(set(h["faces"]) | {i})
                h["bottom"] = i
                h["bottom_point"] = _t(f.CenterOfMass)
    drop = {}  # face -> wires to take out
    bad = set()
    for i, f in enumerate(faces):
        if i in in_hole:
            continue
        outer = f.OuterWire
        for w in f.Wires:
            ks = [e.hashCode() for e in w.Edges]
            hit = {in_hole[j] for key in ks for j in owners.get(key, ()) if j in in_hole}
            if not hit:
                continue
            whole = all(any(j in in_hole for j in owners.get(key, ())) for key in ks)
            if w.isSame(outer) or len(hit) != 1 or not whole:
                bad |= hit
                continue
            drop.setdefault(i, []).append((w, next(iter(hit))))
    good = [k for k in range(len(holes)) if k not in bad]
    new_faces = []
    try:
        for i, f in enumerate(faces):
            if in_hole.get(i) in good:
                continue
            gone = [w for w, k in drop.get(i, []) if k in good]
            if not gone:
                new_faces.append(f)
                continue
            skip = {w.hashCode() for w in gone} | {f.OuterWire.hashCode()}
            keep = [w for w in f.Wires if w.hashCode() not in skip]
            rebuilt = Part.Face(f.OuterWire)
            if keep:
                rebuilt = rebuilt.cutHoles(keep)
            if _normal(rebuilt).dot(_normal(f)) < 0:
                rebuilt.reverse()
            new_faces.append(rebuilt)
        solid = Part.Solid(Part.Shell(new_faces))
        if not solid.isValid() or solid.Volume <= faceted.Volume:
            raise ValueError("not a valid solid")
        merged = solid.removeSplitter()
        if merged.isValid() and len(merged.Solids) == 1:
            solid = merged.Solids[0]
    except Exception as exc:
        warn("recognize_mesh: holes not closed (%s)" % exc)
        return faceted, [], []
    return solid, [holes[k] for k in good], []


def _normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))


def _mesh_levels(solid, axis_name, tol=1e-4):
    """The heights of the flat faces square to the axis, or None when a face is neither
    square to it nor along it (within a mesh's float noise)."""
    d = core.AXES[axis_name]
    heights = []
    for f in solid.Faces:
        if type(f.Surface).__name__ != "Plane":
            return None
        n = core.unit(_t(_normal(f)))
        c = abs(core.dot(n, d))
        if c > 1 - tol:
            heights.append(core.dot(_t(f.Vertexes[0].Point), d))
        elif c > tol * 10:
            return None
    levels = []
    for h in sorted(heights):
        if not levels or h - levels[-1] > 1e-3:
            levels.append(h)
    return levels


def _exact_prism(solid, rounds):
    """The solid rebuilt exactly along the origin axis it is prismatic along (fewest
    levels): every level's section with arcs fitted on the round regions along that axis,
    rounded, extruded; or None."""
    import Part

    best = None
    for axis_name in ("Z", "Y", "X"):
        levels = _mesh_levels(solid, axis_name)
        if levels is None or len(levels) < 2:
            continue
        if best is None or len(levels) < len(best[1]):
            best = (axis_name, levels)
    if best is None:
        return None
    axis_name, levels = best
    plane = core.PLANE_OF_AXIS[axis_name]
    frame = core.PLANES[plane]
    sign = 1 if core.dot(frame["n"], core.AXES[axis_name]) > 0 else -1
    hs = sorted(sign * h for h in levels)
    hs = [core.nice(h, POSITION_TOL) for h in hs]
    circles = []
    for s in rounds:
        if core.parallel(s["axis"], core.AXES[axis_name], 2e-3):
            x, y, _h = core.to_plane(plane, s["center"])
            circles.append((x, y, s["radius"]))
    box = solid.BoundBox
    prisms = []
    for lo, hi in zip(hs, hs[1:]):
        faces = recognize._section(solid, plane, 0.5 * (lo + hi), box)
        for face in faces:
            wires = [face.OuterWire] + [w for w in face.Wires if not w.isSame(face.OuterWire)]
            made = []
            for w in wires:
                pts = _points(w, frame)
                loop = core.fit_arcs(pts, circles, tol=max(1e-3, 1e-5 * box.DiagonalLength))
                if not loop:
                    return None
                loop = core.clean_loop(loop, 1e-9)
                loop = _round_loop(loop)
                made.append(_wire(loop, plane, lo))
            try:
                flat = Part.makeFace(made, "Part::FaceMakerBullseye")
            except Exception:
                return None
            prisms.append(flat.extrude(_vec(core.mul(frame["n"], hi - lo))))
    if not prisms:
        return None
    shape = prisms[0]
    for p in prisms[1:]:
        shape = shape.fuse(p)
    try:
        shape = shape.removeSplitter()
    except Exception:
        pass
    if not shape.isValid() or len(shape.Solids) != 1:
        return None
    return shape.Solids[0]


def _exact_revolve(solid):
    """The faceted solid rebuilt as a profile turned about an origin axis (a turned part
    with cones, spheres or tori, which no prism reads), or None. The mesh's corners lie on
    rings about the axis; a half plane through one corner's row (a meridian) cuts the facets
    along their edges, so the section's corners lie exactly on the profile."""
    import Part

    verts = [_t(v.Point) for v in solid.Vertexes]
    if len(verts) < 6:
        return None
    for axis_name in ("Z", "X", "Y"):
        d = core.AXES[axis_name]
        plane = {"Z": "XZ", "X": "XY", "Y": "XY"}[axis_name]
        rings = {}
        for p in verts:
            t = core.dot(p, d)
            off = core.sub(p, core.mul(d, t))
            rings.setdefault((round(t, 3), round(core.norm(off), 3)), 0)
            rings[(round(t, 3), round(core.norm(off), 3))] += 1
        if len(rings) > 0.4 * len(verts):
            continue  # its corners are not on rings about this axis (through the origin)
        u = _meridian(verts, d)
        if u is None:
            continue
        box = solid.BoundBox
        reach = box.DiagonalLength + 10.0
        ts = [core.dot(p, d) for p in verts]
        lo, hi = min(ts) - 5.0, max(ts) + 5.0
        pts = [
            core.mul(d, lo),
            core.add(core.mul(d, lo), core.mul(u, reach)),
            core.add(core.mul(d, hi), core.mul(u, reach)),
            core.mul(d, hi),
        ]
        half = Part.Face(Part.makePolygon([_vec(p) for p in pts + pts[:1]]))
        try:
            faces = [f for f in solid.common(half).Faces if f.Area > 1e-9]
        except Exception:
            continue
        if len(faces) != 1:
            continue
        face = faces[0]
        wires = [face.OuterWire] + [w for w in face.Wires if not w.isSame(face.OuterWire)]
        made = []
        for w in wires:
            # the profile in (radius, height), drawn in the sketch plane's x / y
            loop_pts = []
            for v in w.OrderedVertexes:
                q = _t(v.Point)
                t = core.dot(q, d)
                r = core.dot(q, u)
                loop_pts.append((r, t) if axis_name != "X" else (t, r))
            loop = core.fit_arcs(loop_pts, _circles_on(loop_pts), tol=1e-3)
            if not loop:
                return None
            loop = core.clean_loop(loop, 1e-9)
            loop = _round_loop(loop)
            made.append(_wire(loop, plane, 0.0))
        try:
            profile = Part.makeFace(made, "Part::FaceMakerBullseye")
            turned = profile.revolve(_vec((0, 0, 0)), _vec(d), 360)
            turned = Part.makeSolid(turned) if not turned.Solids else turned.Solids[0]
            turned = turned.removeSplitter()
        except Exception:
            continue
        if not turned.isValid() or not turned.Solids:
            continue
        turned = turned.Solids[0]
        if abs(turned.Volume - solid.Volume) > 0.003 * solid.Volume:
            continue  # (a profile that does not fit the mesh is refused, never used)
        return turned
    return None


def _meridian(verts, d):
    """The direction (square to d) of the half plane through the most mesh corners: a
    meridian every ring of the turned part has a corner on, so the section's corners lie on
    the true profile."""
    ex = core.unit(core.cross(d, (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)))
    ey = core.cross(d, ex)
    counts = {}
    for p in verts:
        x, y = core.dot(p, ex), core.dot(p, ey)
        if math.hypot(x, y) < 1e-6:
            continue  # (on the axis)
        key = round(math.degrees(math.atan2(y, x)), 2)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    best = max(counts, key=lambda k: counts[k])
    a = math.radians(best)
    return core.add(core.mul(ex, math.cos(a)), core.mul(ey, math.sin(a)))


def _circles_on(points, tol=1e-3):
    """Circles through runs of points that turn gently (an arc of a sphere or a torus in a
    turned part's profile): [(cx, cy, r)]."""
    n = len(points)
    out = []
    i = 0
    while i < n:
        j = i + 2
        best = None
        while j < n:
            run = points[i : j + 1]
            fit = core.fit_circle(run)
            if fit is None:
                break
            cx, cy, r = fit
            if any(abs(math.hypot(x - cx, y - cy) - r) > tol for x, y in run):
                break
            if r > 1e4:
                break  # (a straight run)
            best = fit
            j += 1
        if best is not None and j - i >= 3:
            out.append(best)
            i = j
        else:
            i += 1
    return out


def _points(wire, frame):
    pts = []
    for v in wire.OrderedVertexes:
        t = _t(v.Point)
        pts.append((core.dot(t, frame["x"]), core.dot(t, frame["y"])))
    return pts


def _round_loop(loop):
    """Arc centres and radii, and line ends, rounded the way a person reads them (to 0.01
    mm and rounder), the loop kept closed."""
    out = []
    for s in loop:
        t = dict(s)
        if "c" in t:
            t["c"] = tuple(core.nice(c, POSITION_TOL) for c in t["c"])
            t["r"] = core.round_measured(t["r"], 0.005, POSITION_TOL)[0]
        out.append(t)
    return core.snap_loop(out, POSITION_TOL)


def _wire(loop, plane, h):
    import Part

    def p3(p):
        return _vec(core.from_plane(plane, p[0], p[1], h))

    edges = []
    normal = _vec(core.PLANES[plane]["n"])
    for s in loop:
        if s["kind"] == "circle":
            edges.append(Part.makeCircle(s["r"], p3(s["c"]), normal))
        elif s["kind"] == "line":
            edges.append(Part.LineSegment(p3(s["a"]), p3(s["b"])).toShape())
        else:
            mid = core.arc_mid(s)
            edges.append(Part.Arc(p3(s["a"]), p3(mid), p3(s["b"])).toShape())
    return Part.Wire(edges)


def _hole_solid(h, exact):
    """The exact cylinder of a hole (rounded diameter, axis on an origin axis when it is
    one, centre rounded), through the part or to its measured depth."""
    import Part

    axis = h["axis"]
    radius = h["radius"]
    diameter, measured = core.round_measured(2 * radius, 0.005, POSITION_TOL)
    if h.get("ideal"):
        center = tuple(h["center"])
    else:
        center = tuple(core.nice(c, POSITION_TOL) for c in h["center"])
    t0 = core.nice(h["t0"], POSITION_TOL)
    t1 = core.nice(h["t1"], POSITION_TOL)
    lo, hi = t0 - 1.0, t1 + 1.0
    if "bottom" in h:  # a blind hole: exact at its bottom, past the face it opens on
        t_bottom = core.dot(h["bottom_point"], axis)
        if abs(t_bottom - t0) < abs(t_bottom - t1):
            lo = t0
        else:
            hi = t1
    base = core.add(center, core.mul(axis, lo))
    solid = Part.makeCylinder(diameter / 2.0, hi - lo, _vec(base), _vec(axis))
    return {
        "solid": solid,
        "measured": {
            "kind": "hole",
            "diameter": diameter,
            "measured_diameter": measured,
            "center": [core.nice(c, POSITION_TOL) for c in center],
            "axis": list(axis),
        },
    }


def _add_measured(out, measured):
    """Put each hole's measured diameter beside the rounded one."""
    holes = [m for m in measured if m["kind"] == "hole"]
    for f in out["features"]:
        if f["kind"] not in ("hole", "counterbore", "countersink"):
            continue
        for m in holes:
            if abs(m["diameter"] - f["diameter"]) < 1e-6 and _on_line(f, m):
                f["measured_diameter"] = m["measured_diameter"]
                break
    rounds = [m for m in measured if m["kind"] == "round"]
    if rounds:
        out["notes"].append(
            "Round faces fitted on the mesh: %s."
            % ", ".join(
                "r %s (measured %s)" % (core.fmt(m["radius"]), m["measured_radius"]) for m in rounds
            )
        )


def _on_line(feature, m):
    start = feature.get("start")
    if not start:
        return True
    w = core.sub(tuple(start), tuple(m["center"]))
    axis = tuple(m["axis"])
    off = core.sub(w, core.mul(axis, core.dot(w, axis)))
    return core.norm(off) < 0.05

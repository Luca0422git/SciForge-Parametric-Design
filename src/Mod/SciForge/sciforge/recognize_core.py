# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline, feature recognition: the pure-Python half (no FreeCAD, no Qt; unit tested in
SciForgeTests/unit/test_recognize_core.py). recognize.py measures a solid with FreeCAD and
hands this module plain numbers; this module groups them (patterns of equal holes), cleans
2D profiles (loops of lines and arcs), turns them into the arguments of the AI tools
(create_sketch geometry items, hole / pattern / fillet calls) and orders the plan the way a
Fusion user builds a part: base shape, cuts and bosses, holes, patterns, chamfers, fillets.

Conventions (the same as sciforge/ai/catalog and sciforge/ai/ops):
  * Lengths in mm, angles in degrees.
  * The origin planes: XY (sketch x/y = X/Y, normal +Z), XZ (x/y = X/Z, normal -Y), YZ (x/y =
    Y/Z, normal +X); a sketch's offset moves it along that normal.
  * A 2D loop is a list of segments, each a dict: {"kind": "line", "a": (x, y), "b": (x, y)},
    {"kind": "arc", "c": (cx, cy), "r": r, "a": start, "b": end, "ccw": bool} (the loop runs
    from a to b, counter-clockwise or not) or {"kind": "circle", "c": (cx, cy), "r": r} (a
    loop of its own).
"""

import math

TOL = 1e-6  # lengths (mm): what two B-rep values may differ by and still be "the same"
ANGLE_TOL = 1e-6  # (radians, as a sine)

PLANES = {
    "XY": {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "n": (0.0, 0.0, 1.0)},
    "XZ": {"x": (1.0, 0.0, 0.0), "y": (0.0, 0.0, 1.0), "n": (0.0, -1.0, 0.0)},
    "YZ": {"x": (0.0, 1.0, 0.0), "y": (0.0, 0.0, 1.0), "n": (1.0, 0.0, 0.0)},
}
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
# Which origin plane a sketch for a given direction goes on (its normal along that axis)
PLANE_OF_AXIS = {"Z": "XY", "Y": "XZ", "X": "YZ"}

# Fusion's order of a timeline (the brief: base shape, cuts and bosses, holes, patterns,
# chamfers, fillets last)
ORDER = ("base", "boss", "cut", "hole", "pattern", "shell", "chamfer", "fillet")


# -- numbers ------------------------------------------------------------------------------------
def snap(value, tol=TOL):
    """value with float noise taken off: the fewest decimals (0..6) that stay within tol of
    it (9.9999999997 -> 10.0, 0.30000000004 -> 0.3); -0.0 becomes 0.0."""
    value = float(value)
    for digits in range(0, 7):
        r = round(value, digits)
        if abs(r - value) <= tol:
            return 0.0 if r == 0 else r
    r = round(value, 9)
    return 0.0 if r == 0 else r


def nice(value, tol):
    """The roundest number within tol of value (for measured values, e.g. from a mesh): a
    multiple of 1, 0.5, 0.25, 0.1, 0.05, 0.01 or 0.001, in that order; value itself (to 4
    decimals) when none is close enough."""
    value = float(value)
    for step in (1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.001):
        r = round(value / step) * step
        if abs(r - value) <= tol:
            return snap(r, 1e-9)
    return snap(round(value, 4), 1e-9)


def snap_point(p, tol=TOL):
    return tuple(snap(c, tol) for c in p)


def same(a, b, tol=TOL):
    return abs(a - b) <= tol


# -- vectors (3D tuples) ------------------------------------------------------------------------
def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, k):
    return tuple(x * k for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    if n < 1e-15:
        raise ValueError("zero-length vector")
    return tuple(x / n for x in a)


def parallel(a, b, tol=ANGLE_TOL):
    """a and b point along one line (either sense)."""
    return norm(cross(unit(a), unit(b))) <= tol


def square(a, b, tol=ANGLE_TOL):
    """a and b are at right angles."""
    return abs(dot(unit(a), unit(b))) <= tol


def origin_axis(direction, tol=ANGLE_TOL):
    """'X', 'Y' or 'Z' when direction runs along that origin axis (either sense), else None."""
    d = unit(direction)
    for name, axis in AXES.items():
        if abs(abs(dot(d, axis)) - 1.0) <= tol:
            return name
    return None


def canonical_direction(direction):
    """The direction with its sign fixed (largest component positive), so one line has one
    name."""
    d = unit(direction)
    k = max(range(3), key=lambda i: abs(d[i]))
    return d if d[k] > 0 else mul(d, -1.0)


def to_plane(plane, point):
    """(x, y, h): point in the origin plane's sketch coordinates, h along its normal."""
    frame = PLANES[plane]
    return (dot(point, frame["x"]), dot(point, frame["y"]), dot(point, frame["n"]))


def from_plane(plane, x, y, h=0.0):
    frame = PLANES[plane]
    return add(add(mul(frame["x"], x), mul(frame["y"], y)), mul(frame["n"], h))


def plane_for_direction(direction):
    """(plane, sign): the origin plane whose normal runs along direction (sign +1 when it
    points the same way), or (None, 0) for a direction along no origin axis."""
    axis = origin_axis(direction)
    if axis is None:
        return None, 0
    plane = PLANE_OF_AXIS[axis]
    return plane, (1 if dot(unit(direction), PLANES[plane]["n"]) > 0 else -1)


# -- 2D loops -----------------------------------------------------------------------------------
def _angle(c, p):
    return math.atan2(p[1] - c[1], p[0] - c[0])


def arc_sweep(seg):
    """The angle (radians, > 0) an arc segment turns through from a to b."""
    a0, a1 = _angle(seg["c"], seg["a"]), _angle(seg["c"], seg["b"])
    turn = (a1 - a0) if seg["ccw"] else (a0 - a1)
    turn %= 2 * math.pi
    if turn < 1e-12:
        turn = 2 * math.pi
    return turn


def arc_mid(seg):
    a0 = _angle(seg["c"], seg["a"])
    half = arc_sweep(seg) / 2.0
    t = a0 + half if seg["ccw"] else a0 - half
    return (seg["c"][0] + seg["r"] * math.cos(t), seg["c"][1] + seg["r"] * math.sin(t))


def polygon_of(loop, per_turn=72):
    """The loop as points (arcs and circles cut into short lines), for areas and inside
    tests."""
    pts = []
    for seg in loop:
        if seg["kind"] == "circle":
            cx, cy = seg["c"]
            for k in range(per_turn):
                t = 2 * math.pi * k / per_turn
                pts.append((cx + seg["r"] * math.cos(t), cy + seg["r"] * math.sin(t)))
        elif seg["kind"] == "arc":
            n = max(2, int(math.ceil(arc_sweep(seg) / (2 * math.pi) * per_turn)))
            a0 = _angle(seg["c"], seg["a"])
            sweep = arc_sweep(seg) * (1 if seg["ccw"] else -1)
            for k in range(n):
                t = a0 + sweep * k / n
                pts.append(
                    (seg["c"][0] + seg["r"] * math.cos(t), seg["c"][1] + seg["r"] * math.sin(t))
                )
        else:
            pts.append(tuple(seg["a"]))
    return pts


def signed_area(loop):
    """Area of the loop, positive when it runs counter-clockwise (arcs exactly)."""
    if len(loop) == 1 and loop[0]["kind"] == "circle":
        return math.pi * loop[0]["r"] ** 2
    total = 0.0
    for seg in loop:
        (x0, y0), (x1, y1) = seg["a"], seg["b"]
        total += x0 * y1 - x1 * y0  # the chord (shoelace)
        if seg["kind"] == "arc":
            theta = arc_sweep(seg)
            circular = 0.5 * seg["r"] ** 2 * (theta - math.sin(theta))  # segment beyond chord
            total += 2 * circular * (1 if seg["ccw"] else -1)
    return total / 2.0


def point_inside(point, loop):
    """Whether point lies inside the loop (even-odd rule on its polygon)."""
    pts = polygon_of(loop)
    x, y = point
    inside = False
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xc > x:
                inside = not inside
    return inside


def _same_pt(p, q, tol):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def _collinear(s, t, tol):
    """Two consecutive lines on one straight line, running the same way."""
    d1 = (s["b"][0] - s["a"][0], s["b"][1] - s["a"][1])
    d2 = (t["b"][0] - t["a"][0], t["b"][1] - t["a"][1])
    l1, l2 = math.hypot(*d1), math.hypot(*d2)
    if l1 < tol or l2 < tol:
        return True
    crossed = (d1[0] * d2[1] - d1[1] * d2[0]) / (l1 * l2)
    return abs(crossed) <= 1e-9 and (d1[0] * d2[0] + d1[1] * d2[1]) > 0


def _cocircular(s, t, tol):
    return (
        s["kind"] == "arc"
        and t["kind"] == "arc"
        and s["ccw"] == t["ccw"]
        and _same_pt(s["c"], t["c"], tol)
        and abs(s["r"] - t["r"]) <= tol
    )


def clean_loop(loop, tol=TOL):
    """A tidy copy of a loop: float noise snapped, zero-length pieces dropped, collinear lines
    and arcs of one circle merged, every piece starting exactly where the one before it
    ends (so the loop stays closed)."""
    segs = []
    for seg in loop:
        s = dict(seg)
        for key in ("a", "b", "c"):
            if key in s:
                s[key] = snap_point(s[key], tol)
        if "r" in s:
            s["r"] = snap(s["r"], tol)
        if s["kind"] == "line" and _same_pt(s["a"], s["b"], tol):
            continue
        segs.append(s)
    if len(segs) == 1 and segs[0]["kind"] == "circle":
        return segs
    if len(segs) == 1 and segs[0]["kind"] == "arc" and _same_pt(segs[0]["a"], segs[0]["b"], tol):
        return [{"kind": "circle", "c": segs[0]["c"], "r": segs[0]["r"]}]
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i in range(len(segs)):
            s, t = segs[i], segs[(i + 1) % len(segs)]
            if s is t:
                break
            if s["kind"] == "line" and t["kind"] == "line" and _collinear(s, t, tol):
                merged = {"kind": "line", "a": s["a"], "b": t["b"]}
            elif _cocircular(s, t, tol):
                merged = dict(s, b=t["b"])
            else:
                continue
            j = (i + 1) % len(segs)
            segs[i] = merged
            del segs[j]
            changed = True
            break
    if len(segs) == 1 and segs[0]["kind"] == "arc":
        return [{"kind": "circle", "c": segs[0]["c"], "r": segs[0]["r"]}]
    for i in range(len(segs)):  # close every joint exactly
        prev = segs[i - 1]
        if segs[i]["kind"] != "circle" and prev["kind"] != "circle":
            segs[i]["a"] = prev["b"]
    return segs


def _deg(rad):
    d = math.degrees(rad)
    return snap(d, 1e-9)


def _arc_item(s):
    """An arc as create_sketch's {"arc": [cx, cy, r, a0, a1]}: counter-clockwise from a0 to
    a1 (degrees), whichever way the loop runs through it."""
    start, end = (s["a"], s["b"]) if s["ccw"] else (s["b"], s["a"])
    a0 = _deg(_angle(s["c"], start))
    a1 = _deg(_angle(s["c"], end))
    while a1 <= a0:
        a1 += 360.0
    return {"arc": [s["c"][0], s["c"][1], s["r"], a0, snap(a1, 1e-9)]}


def _arc_ends(item):
    """Where SciForge's sketch puts the ends of an {"arc": [cx, cy, r, a0, a1]} item (the
    same arithmetic, so a line drawn to them meets the arc exactly)."""
    cx, cy, r, a0, a1 = item["arc"]
    return (
        (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))),
        (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))),
    )


def _segments(loop):
    """A loop as create_sketch "segments": arcs counter-clockwise, every line's ends taken
    from the arcs beside it, so the chain closes within FreeCAD's 1e-7 mm."""
    pieces = []
    for s in loop:
        if s["kind"] == "arc":
            item = _arc_item(s)
            p0, p1 = _arc_ends(item)
            pieces.append([item, p0, p1] if s["ccw"] else [item, p1, p0])
        else:
            pieces.append([None, s["a"], s["b"]])
    n = len(pieces)
    for i, piece in enumerate(pieces):
        if piece[0] is None:
            before, after = pieces[i - 1], pieces[(i + 1) % n]
            if before[0] is not None:
                piece[1] = before[2]
            if after[0] is not None:
                piece[2] = after[1]
    out = []
    for item, a, b in pieces:
        out.append(item if item is not None else {"line": [a[0], a[1], b[0], b[1]]})
    return out


def _rect_of(loop, tol):
    if len(loop) != 4 or any(s["kind"] != "line" for s in loop):
        return None
    xs = sorted({snap(p, tol) for s in loop for p in (s["a"][0], s["b"][0])})
    ys = sorted({snap(p, tol) for s in loop for p in (s["a"][1], s["b"][1])})
    if len(xs) != 2 or len(ys) != 2:
        return None
    for s in loop:  # every side horizontal or vertical
        if not (same(s["a"][0], s["b"][0], tol) or same(s["a"][1], s["b"][1], tol)):
            return None
    return [xs[0], ys[0], xs[1], ys[1]]


def _slot_of(loop, tol):
    """[x1, y1, x2, y2, width] when the loop is a straight slot (two half circles joined by
    two lines), else None."""
    if len(loop) != 4:
        return None
    kinds = [s["kind"] for s in loop]
    if kinds not in (["line", "arc", "line", "arc"], ["arc", "line", "arc", "line"]):
        return None
    arcs = [s for s in loop if s["kind"] == "arc"]
    if abs(arcs[0]["r"] - arcs[1]["r"]) > tol:
        return None
    for a in arcs:
        if abs(arc_sweep(a) - math.pi) > 1e-6:
            return None
    (x1, y1), (x2, y2) = arcs[0]["c"], arcs[1]["c"]
    if _same_pt(arcs[0]["c"], arcs[1]["c"], tol):
        return None
    return [x1, y1, x2, y2, snap(2 * arcs[0]["r"], tol)]


def loop_geometry(loop, name=None, tol=TOL):
    """One create_sketch geometry item for a clean loop (circle, rect, slot, polyline or
    segments), or None when the loop has a piece the tools cannot draw (an ellipse arc, a
    free-form curve)."""
    if any(s["kind"] not in ("line", "arc", "circle") for s in loop):
        return None
    item = None
    if len(loop) == 1 and loop[0]["kind"] == "circle":
        c = loop[0]
        item = {"circle": [c["c"][0], c["c"][1], c["r"]]}
    elif _rect_of(loop, tol) is not None:
        item = {"rect": _rect_of(loop, tol)}
    elif _slot_of(loop, tol) is not None:
        item = {"slot": _slot_of(loop, tol)}
    elif all(s["kind"] == "line" for s in loop) and len(loop) >= 3:
        item = {"polyline": [[s["a"][0], s["a"][1]] for s in loop]}
    elif len(loop) >= 2 and all(s["kind"] in ("line", "arc") for s in loop):
        item = {"segments": _segments(loop)}
    if item is not None and name and ("rect" in item or "circle" in item):
        item["name"] = name
    return item


def loop_box(loop):
    pts = polygon_of(loop, 16)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def describe_loop(loop):
    """A few words for a loop: "rectangle 40 x 20", "circle d 12", "slot 30 x 10",
    "outline of 6 lines and 2 arcs"."""
    if len(loop) == 1 and loop[0]["kind"] == "circle":
        return "circle d %s" % fmt(2 * loop[0]["r"])
    rect = _rect_of(loop, TOL)
    if rect:
        return "rectangle %s x %s" % (fmt(rect[2] - rect[0]), fmt(rect[3] - rect[1]))
    slot = _slot_of(loop, TOL)
    if slot:
        length = math.hypot(slot[2] - slot[0], slot[3] - slot[1]) + slot[4]
        return "slot %s x %s" % (fmt(length), fmt(slot[4]))
    lines = len([s for s in loop if s["kind"] == "line"])
    arcs = len([s for s in loop if s["kind"] == "arc"])
    words = []
    if lines:
        words.append("%d line%s" % (lines, "" if lines == 1 else "s"))
    if arcs:
        words.append("%d arc%s" % (arcs, "" if arcs == 1 else "s"))
    return "outline of " + " and ".join(words or ["curves"])


def fmt(value):
    """A number as a person writes it: 10, 2.5, 0.125."""
    v = snap(value, 1e-6)
    if v == int(v):
        return "%d" % int(v)
    return ("%.4f" % v).rstrip("0").rstrip(".")


# -- patterns -----------------------------------------------------------------------------------
def _clusters(values, tol):
    """Sorted distinct values (within tol)."""
    out = []
    for v in sorted(values):
        if not out or v - out[-1][-1] > tol:
            out.append([v])
        else:
            out[-1].append(v)
    return [sum(c) / len(c) for c in out]


def _even(values, tol):
    """The common step of sorted values, or None when they are not evenly spaced."""
    if len(values) < 2:
        return None
    step = (values[-1] - values[0]) / (len(values) - 1)
    if step <= tol:
        return None
    for i, v in enumerate(values):
        if abs(v - (values[0] + i * step)) > tol:
            return None
    return step


def fit_circle(points):
    """(cx, cy, r) of the circle through 2D points (least squares, Kasa's method), or None."""
    n = len(points)
    if n < 3:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in points:
        u, v = x - mx, y - my
        suu += u * u
        suv += u * v
        svv += v * v
        suuu += u * u * u
        svvv += v * v * v
        suvv += u * v * v
        svuu += v * u * u
    det = suu * svv - suv * suv
    if abs(det) < 1e-18:
        return None
    b1 = 0.5 * (suuu + suvv)
    b2 = 0.5 * (svvv + svuu)
    uc = (b1 * svv - b2 * suv) / det
    vc = (suu * b2 - suv * b1) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return (uc + mx, vc + my, r)


def find_pattern(points, tol=1e-4, circle_centres=()):
    """How 2D points (equal features' centres) are laid out, or None:
    {"kind": "rectangular", "origin": (x, y), "count": nx, "spacing": sx, "count2": ny,
     "spacing2": sy} (a grid along the sketch's x and y; count2 1 for one row),
    {"kind": "linear", "origin": (x, y), "direction": (ux, uy), "count": n, "spacing": s},
    {"kind": "circular", "center": (cx, cy), "radius": r, "count": n, "start": deg,
     "step": deg, "full": bool}.
    circle_centres: centres of round faces of the part; a circle of points about one of
    them is read as a circular pattern even when the points also make a square grid (a
    flange's four bolts)."""
    pts = [tuple(p) for p in points]
    n = len(pts)
    if n < 2:
        return None
    grid = _grid(pts, tol)
    circ = _circle_pattern(pts, tol) if n >= 3 else None
    if circ is not None and (grid is None or _near_any(circ["center"], circle_centres, tol)):
        return circ
    if grid is not None:
        return grid
    if circ is not None:
        return circ
    return _line_pattern(pts, tol)


def _near_any(p, centres, tol):
    return any(_same_pt(p, c, max(tol, 1e-3)) for c in centres)


def _grid(pts, tol):
    xs, ys = _clusters([p[0] for p in pts], tol), _clusters([p[1] for p in pts], tol)
    if len(xs) * len(ys) != len(pts):
        return None
    for x in xs:  # every grid node present
        for y in ys:
            if not any(_same_pt((x, y), p, tol) for p in pts):
                return None
    sx = _even(xs, tol) if len(xs) > 1 else 0.0
    sy = _even(ys, tol) if len(ys) > 1 else 0.0
    if sx is None or sy is None:
        return None
    if len(xs) == 1:  # one column: a row along y
        return {
            "kind": "rectangular",
            "origin": (xs[0], ys[0]),
            "count": len(ys),
            "spacing": sy,
            "axis": "y",
            "count2": 1,
            "spacing2": 0.0,
        }
    return {
        "kind": "rectangular",
        "origin": (xs[0], ys[0]),
        "count": len(xs),
        "spacing": sx,
        "axis": "x",
        "count2": len(ys),
        "spacing2": sy,
    }


def _circle_pattern(pts, tol):
    fit = fit_circle(pts)
    if fit is None:
        return None
    cx, cy, r = fit
    if r <= tol:
        return None
    if any(abs(math.hypot(p[0] - cx, p[1] - cy) - r) > tol for p in pts):
        return None
    angles = sorted(math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360.0 for p in pts)
    n = len(angles)
    gaps = [(angles[(i + 1) % n] - angles[i]) % 360.0 for i in range(n)]
    angle_tol = math.degrees(tol / r) * 4 + 1e-6
    full_step = 360.0 / n
    if all(abs(g - full_step) <= angle_tol for g in gaps):
        start = angles[0]
        return {
            "kind": "circular",
            "center": (cx, cy),
            "radius": r,
            "count": n,
            "start": start,
            "step": full_step,
            "full": True,
        }
    # a partial arc: one big gap, the others equal
    big = max(range(n), key=lambda i: gaps[i])
    others = [g for i, g in enumerate(gaps) if i != big]
    step = sum(others) / len(others)
    if step <= angle_tol or any(abs(g - step) > angle_tol for g in others):
        return None
    start = angles[(big + 1) % n]
    return {
        "kind": "circular",
        "center": (cx, cy),
        "radius": r,
        "count": n,
        "start": start,
        "step": step,
        "full": False,
    }


def _line_pattern(pts, tol):
    if len(pts) < 2:
        return None
    a = min(pts)
    far = max(pts, key=lambda p: math.hypot(p[0] - a[0], p[1] - a[1]))
    length = math.hypot(far[0] - a[0], far[1] - a[1])
    if length <= tol:
        return None
    u = ((far[0] - a[0]) / length, (far[1] - a[1]) / length)
    ts = []
    for p in pts:
        dx, dy = p[0] - a[0], p[1] - a[1]
        if abs(dx * u[1] - dy * u[0]) > tol:
            return None
        ts.append(dx * u[0] + dy * u[1])
    ts.sort()
    step = _even(ts, tol)
    if step is None:
        return None
    return {"kind": "linear", "origin": a, "direction": u, "count": len(pts), "spacing": step}


def pattern_order(points, pattern):
    """The points in the pattern's own order: the first is the one the feature is drawn at."""
    if pattern is None:
        return list(points)
    if pattern["kind"] == "circular":
        cx, cy = pattern["center"]
        start = pattern["start"]
        return sorted(
            points, key=lambda p: (math.degrees(math.atan2(p[1] - cy, p[0] - cx)) - start) % 360.0
        )
    if pattern["kind"] == "linear":
        o, u = pattern["origin"], pattern["direction"]
        return sorted(points, key=lambda p: (p[0] - o[0]) * u[0] + (p[1] - o[1]) * u[1])
    return sorted(points, key=lambda p: (round(p[1], 6), round(p[0], 6)))


# -- the plan -----------------------------------------------------------------------------------
_ID_BASES = {
    "create_sketch": "Sketch",
    "create_curve_sketch": "Sketch",
    "extrude": "Extrude",
    "revolve": "Revolve",
    "hole": "Hole",
    "pattern": "Pattern",
    "rectangular_pattern": "Pattern",
    "circular_pattern": "Pattern",
    "fillet": "Fillet",
    "chamfer": "Chamfer",
    "shell": "Shell",
    "primitive": "Primitive",
    "mirror": "Mirror",
}


class Plan:
    """The plan's steps in order, with the id each step will get in a design that has none of
    `taken` (SciForge names a new step <Tool><n>, the first free n: Sketch1, Extrude1...)."""

    def __init__(self, taken=()):
        self.steps = []
        self.taken = set(taken)

    def new_id(self, tool):
        base = _ID_BASES.get(tool) or "".join(w.capitalize() for w in tool.split("_"))
        n = 1
        while "%s%d" % (base, n) in self.taken:
            n += 1
        ident = "%s%d" % (base, n)
        self.taken.add(ident)
        return ident

    def add(self, tool, args, why, features=(), uses=None, makes_id=True):
        """Append a step; returns the id it will make (None when it makes none)."""
        ident = self.new_id(tool) if makes_id else None
        step = {
            "step": len(self.steps) + 1,
            "tool": tool,
            "args": args,
            "why": why,
            "features": list(features),
        }
        if ident:
            step["id"] = ident
        if uses:
            step["uses"] = dict(uses)
        self.steps.append(step)
        return ident

    def step_of(self, ident):
        for step in self.steps:
            if step.get("id") == ident:
                return step["step"]
        return None


def sketch_args(plane, offset, geometry):
    args = {"plane": plane}
    if offset:
        args["offset"] = snap(offset)
    args["geometry"] = geometry
    return args


def extent_args(h0, h1, operation):
    """The extrude arguments for material between h0 and h1 (h0 < h1, along the sketch
    plane's normal) from a sketch at `start`: (start, args). A join starts at its lower end
    and goes up; a cut starts at its upper end and goes down (flip), as a cut drawn on the
    face it goes into."""
    distance = snap(h1 - h0)
    if operation == "cut":
        return h1, {"distance": distance, "operation": "cut", "flip": True}
    args = {"distance": distance}
    if operation != "join":
        args["operation"] = operation
    return h0, args


def base_extrude_args(h0, h1):
    """(sketch offset, extrude arguments) for the first solid between h0 and h1: on the
    origin plane itself when the part touches it (flipped or two sides when needed)."""
    h0, h1 = snap(h0), snap(h1)
    if same(h0, 0.0):
        return 0.0, {"distance": snap(h1)}
    if same(h1, 0.0):
        return 0.0, {"distance": snap(-h0), "flip": True}
    if h0 < 0.0 < h1:
        if same(-h0, h1):
            return 0.0, {"distance": snap(h1 - h0), "direction": "symmetric"}
        return 0.0, {"distance": snap(h1), "direction": "two_sides", "distance2": snap(-h0)}
    return h0, {"distance": snap(h1 - h0)}


def order_key(kind):
    """Where a feature kind goes in Fusion's order."""
    groups = {
        "pocket": "cut",
        "slot": "cut",
        "cut": "cut",
        "groove": "cut",
        "boss": "boss",
        "join": "boss",
        "hole": "hole",
        "counterbore": "hole",
        "countersink": "hole",
        "pattern": "pattern",
        "shell": "shell",
        "chamfer": "chamfer",
        "fillet": "fillet",
    }
    return ORDER.index(groups.get(kind, "cut")) if kind != "base" else 0


def ordered(features):
    """Features sorted into Fusion's order (stable within one kind)."""
    return sorted(features, key=lambda f: order_key(f["kind"]))


def check_plan(steps, validate):
    """Problems of the plan's steps by the catalogue's own check (validate(tool, args) ->
    [sentences]): [(step number, sentence)]."""
    problems = []
    for step in steps:
        for sentence in validate(step["tool"], step["args"]):
            problems.append((step["step"], sentence))
    return problems


def confidence(area_explained, total_area, volume_error, total_volume):
    """0..1 from how much of the area the features explain and how far the base's own
    rebuild is from the solid in volume."""
    if total_area <= 0 or total_volume <= 0:
        return 0.0
    area_part = max(0.0, min(1.0, area_explained / total_area))
    volume_part = max(0.0, 1.0 - min(1.0, abs(volume_error) / total_volume * 20.0))
    return round(area_part * volume_part, 3)


# -- meshes -------------------------------------------------------------------------------------
def eigen_symmetric3(m):
    """Eigenvalues and eigenvectors of a symmetric 3 x 3 matrix (Jacobi rotations):
    [(value, (x, y, z))] sorted by value, smallest first."""
    a = [list(row) for row in m]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _sweep in range(50):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off < 1e-15:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-18:
                continue
            theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
            t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
            c = 1 / math.sqrt(t * t + 1)
            s = t * c
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = c * akp - s * akq
                a[k][q] = s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = c * apk - s * aqk
                a[q][k] = s * apk + c * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p] = c * vkp - s * vkq
                v[k][q] = s * vkp + c * vkq
    pairs = [(a[i][i], (v[0][i], v[1][i], v[2][i])) for i in range(3)]
    return sorted(pairs, key=lambda pair: pair[0])


def fit_cylinder(points, normals):
    """(axis point, axis direction, radius, rms error) of the cylinder through 3D points whose
    surface normals are given: the axis is the direction square to every normal (the
    smallest eigenvector of their scatter), the circle is fitted to the points seen along
    it. None when the points are not round."""
    if len(points) < 3 or len(normals) < 2:
        return None
    m = [[0.0] * 3 for _ in range(3)]
    for n in normals:
        nx = unit(n)
        for i in range(3):
            for j in range(3):
                m[i][j] += nx[i] * nx[j]
    axis = canonical_direction(eigen_symmetric3(m)[0][1])
    ex = unit(cross(axis, (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)))
    ey = cross(axis, ex)
    flat = [(dot(p, ex), dot(p, ey)) for p in points]
    circle = fit_circle(flat)
    if circle is None:
        return None
    cx, cy, r = circle
    rms = math.sqrt(sum((math.hypot(x - cx, y - cy) - r) ** 2 for x, y in flat) / len(flat))
    centre = add(mul(ex, cx), mul(ey, cy))
    return centre, axis, r, rms


def round_measured(value, relative=0.01, absolute=0.05):
    """A value measured on a mesh, rounded the way a person would read it: (rounded,
    measured). 5.98 -> 6.0; within max(relative * value, absolute)."""
    tol = max(abs(value) * relative, absolute)
    return nice(value, tol), round(float(value), 4)


def fit_arcs(points, circles=(), tol=1e-3, max_step=50.0):
    """A closed polygon (points in order: a mesh's section) as a loop of lines and arcs: runs
    of at least 3 points that lie on one of `circles` ((cx, cy, r): the round faces fitted
    on the mesh), each step turning at most max_step degrees about it, become one arc (a
    whole ring of points: a circle). Other runs stay lines."""
    pts = [tuple(p) for p in points]
    n = len(pts)
    if n < 3:
        return []
    on = []
    for p in pts:
        hit = None
        for k, (cx, cy, r) in enumerate(circles):
            if abs(math.hypot(p[0] - cx, p[1] - cy) - r) <= tol:
                hit = k
                break
        on.append(hit)

    def step_ok(i, k):
        cx, cy, _r = circles[k]
        a = math.atan2(pts[i][1] - cy, pts[i][0] - cx)
        b = math.atan2(pts[(i + 1) % n][1] - cy, pts[(i + 1) % n][0] - cx)
        turn = abs((b - a + math.pi) % (2 * math.pi) - math.pi)
        return math.degrees(turn) <= max_step

    # links: i -> i+1 runs on circle k when both points are on it and the step is short
    link = []
    for i in range(n):
        k = on[i]
        link.append(k if k is not None and on[(i + 1) % n] == k and step_ok(i, k) else None)
    if all(k is not None and k == link[0] for k in link):  # a whole circle
        cx, cy, r = circles[link[0]]
        return [{"kind": "circle", "c": (cx, cy), "r": r}]
    # start at a point where the link kind changes, so no run wraps around the end
    start = 0
    for i in range(n):
        if link[i - 1] != link[i]:
            start = i
            break
    order = [(start + i) % n for i in range(n)]
    segs = []
    i = 0
    while i < n:
        idx = order[i]
        k = link[idx]
        j = i
        while j + 1 < n and link[order[j + 1]] == k and k is not None:
            j += 1
        a = pts[idx]
        b = pts[(order[j] + 1) % n]
        if k is None:
            for m in range(i, j + 1):
                p = pts[order[m]]
                q = pts[(order[m] + 1) % n]
                segs.append({"kind": "line", "a": p, "b": q})
        elif j - i + 1 >= 2:  # at least 3 points on the circle
            cx, cy, r = circles[k]
            mid = pts[order[(i + j + 1) // 2]] if j > i else pts[(idx + 1) % n]
            ta = math.atan2(a[1] - cy, a[0] - cx)
            tm = (math.atan2(mid[1] - cy, mid[0] - cx) - ta) % (2 * math.pi)
            tb = (math.atan2(b[1] - cy, b[0] - cx) - ta) % (2 * math.pi)
            segs.append({"kind": "arc", "c": (cx, cy), "r": r, "a": a, "b": b, "ccw": tm < tb})
        else:
            segs.append({"kind": "line", "a": a, "b": b})
        i = j + 1
    return segs


def snap_loop(loop, nice_tol):
    """A loop whose numbers came from a mesh, rounded the way a person reads them: circle
    centres and radii and line ends to the roundest value within nice_tol; an arc's ends
    are put back on its rounded circle (so the loop stays closed and tangent)."""
    out = []
    for s in loop:
        t = dict(s)
        if "c" in t:
            t["c"] = (nice(t["c"][0], nice_tol), nice(t["c"][1], nice_tol))
            t["r"] = nice(t["r"], nice_tol)
        for key in ("a", "b"):
            if key in t:
                t[key] = (nice(t[key][0], nice_tol), nice(t[key][1], nice_tol))
        out.append(t)
    for t in out:  # arc ends back on the rounded circle
        if t["kind"] == "arc":
            for key in ("a", "b"):
                ang = math.atan2(t[key][1] - t["c"][1], t[key][0] - t["c"][0])
                t[key] = (t["c"][0] + t["r"] * math.cos(ang), t["c"][1] + t["r"] * math.sin(ang))
    n = len(out)
    for i in range(n):  # lines meet the arcs where the arcs now end
        s = out[i]
        if s["kind"] == "arc":
            prev, nxt = out[i - 1], out[(i + 1) % n]
            if prev["kind"] == "line":
                prev["b"] = s["a"]
            if nxt["kind"] == "line":
                nxt["a"] = s["b"]
    return out


def ideal_points(points, pattern, tol):
    """The points of a pattern found on measured values (a mesh), put where the pattern says
    with its numbers rounded (centre, radius, start angle, spacing): one ideal point per
    input point, in the same order."""
    if pattern is None:
        return [tuple(p) for p in points]
    n = len(points)
    if pattern["kind"] == "circular":
        cx, cy = (nice(c, tol) for c in pattern["center"])
        r = nice(pattern["radius"], tol)
        start = nice(pattern["start"], 0.05)
        step = 360.0 / n if pattern["full"] else nice(pattern["step"], 0.05)
        ideal = [
            (
                cx + r * math.cos(math.radians(start + k * step)),
                cy + r * math.sin(math.radians(start + k * step)),
            )
            for k in range(n)
        ]
    elif pattern["kind"] == "rectangular":
        ox, oy = (nice(c, tol) for c in pattern["origin"])
        s1 = nice(pattern["spacing"], tol)
        s2 = nice(pattern["spacing2"], tol)
        if pattern.get("axis", "x") == "x":
            ideal = [
                (ox + i * s1, oy + j * s2)
                for j in range(pattern["count2"])
                for i in range(pattern["count"])
            ]
        else:
            ideal = [(ox, oy + i * s1) for i in range(pattern["count"])]
    else:
        ox, oy = (nice(c, tol) for c in pattern["origin"])
        ang = nice(math.degrees(math.atan2(pattern["direction"][1], pattern["direction"][0])), 0.05)
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        s = nice(pattern["spacing"], tol)
        ideal = [(ox + k * s * u[0], oy + k * s * u[1]) for k in range(n)]
    out = []
    free = list(ideal)
    for p in points:
        if not free:
            out.append(tuple(p))
            continue
        q = min(free, key=lambda c: math.hypot(c[0] - p[0], c[1] - p[1]))
        if math.hypot(q[0] - p[0], q[1] - p[1]) > 10 * tol:
            out.append(tuple(p))
            continue
        free.remove(q)
        out.append(q)
    return out


def shift_item(item, dx, dy):
    """A create_sketch geometry item moved by (dx, dy)."""
    out = dict(item)
    if "circle" in out:
        cx, cy, r = out["circle"]
        out["circle"] = [cx + dx, cy + dy, r]
    elif "rect" in out:
        x0, y0, x1, y1 = out["rect"]
        out["rect"] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    elif "center_rect" in out:
        cx, cy, w, h = out["center_rect"]
        out["center_rect"] = [cx + dx, cy + dy, w, h]
    elif "slot" in out:
        x1, y1, x2, y2, w = out["slot"]
        out["slot"] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy, w]
    elif "polyline" in out:
        out["polyline"] = [[x + dx, y + dy] for x, y in out["polyline"]]
    elif "polygon" in out:
        spec = dict(out["polygon"])
        spec["center"] = [spec["center"][0] + dx, spec["center"][1] + dy]
        out["polygon"] = spec
    elif "segments" in out:
        segs = []
        for seg in out["segments"]:
            if "line" in seg:
                x0, y0, x1, y1 = seg["line"]
                segs.append({"line": [x0 + dx, y0 + dy, x1 + dx, y1 + dy]})
            elif "arc" in seg:
                cx, cy, r, a0, a1 = seg["arc"]
                segs.append({"arc": [cx + dx, cy + dy, r, a0, a1]})
            else:
                segs.append(dict(seg))
        out["segments"] = segs
    return out


def same_items(a, b, tol=1e-6):
    """Two geometry item lists alike (same kinds, numbers within tol), in any order."""
    if len(a) != len(b):
        return False
    left = list(b)
    for item in a:
        for k, other in enumerate(left):
            if _close(item, other, tol):
                del left[k]
                break
        else:
            return False
    return True


def _close(a, b, tol):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) - {"name"} != set(b) - {"name"}:
            return False
        return all(_close(a[k], b[k], tol) for k in a if k != "name")
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


# -- parts turned away from the origin planes ------------------------------------------------
def closest_frame(d1, d2):
    """The rotation (3 x 3, rows; world from local: R * local = world) whose local axes run
    along d1, d2 and d1 x d2 (in some order and sense), closest to no turn at all."""
    import itertools

    a = unit(d1)
    b = unit(sub(d2, mul(a, dot(d2, a))))
    c = cross(a, b)
    best = None
    for perm in itertools.permutations((a, b, c)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            cols = [mul(v, s) for v, s in zip(perm, signs)]
            if dot(cross(cols[0], cols[1]), cols[2]) < 0:
                continue  # (a mirror, not a turn)
            trace = cols[0][0] + cols[1][1] + cols[2][2]
            if best is None or trace > best[0] + 1e-12:
                best = (trace, cols)
    cols = best[1]
    return [[cols[j][i] for j in range(3)] for i in range(3)]


def euler_xyz(rot):
    """(rx, ry, rz) in degrees with rot = Rz(rz) * Ry(ry) * Rx(rx) (turned about X first,
    then Y, then Z: SciForge's free Move)."""
    r20 = max(-1.0, min(1.0, rot[2][0]))
    ry = math.asin(-r20)
    if abs(r20) < 1 - 1e-9:
        rx = math.atan2(rot[2][1], rot[2][2])
        rz = math.atan2(rot[1][0], rot[0][0])
    else:  # (straight up or down: X and Z turn about one line)
        rz = 0.0
        rx = math.atan2(-rot[1][2], rot[1][1])
    return tuple(snap(math.degrees(v), 1e-9) for v in (rx, ry, rz))


def rotation_xyz(rx, ry, rz):
    """The matrix (rows) of Rz(rz) * Ry(ry) * Rx(rx), angles in degrees."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    ca, sa, cb, sb, cc, sc = (
        math.cos(a),
        math.sin(a),
        math.cos(b),
        math.sin(b),
        math.cos(c),
        math.sin(c),
    )
    return [
        [cb * cc, sa * sb * cc - ca * sc, ca * sb * cc + sa * sc],
        [cb * sc, sa * sb * sc + ca * cc, ca * sb * sc - sa * cc],
        [-sb, sa * cb, ca * cb],
    ]


def name_items(items, prefix):
    """Name the rectangles and circles of a sketch's geometry so their dimensions read as a
    person would name them (base.width, hole.x, boss2.diameter): the first gets the prefix,
    the next ones prefix2, prefix3..."""
    out = []
    k = 0
    for item in items:
        item = dict(item)
        if any(key in item for key in ("rect", "circle", "center_rect")) and "name" not in item:
            k += 1
            item["name"] = prefix if k == 1 else "%s%d" % (prefix, k)
        out.append(item)
    return out

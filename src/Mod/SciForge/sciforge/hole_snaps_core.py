# SPDX-License-Identifier: LGPL-2.1-or-later
"""The maths of SciForge's hole-centre snaps, without FreeCAD or Qt (unit tested in
SciForgeTests/unit/test_hole_snaps_core.py). The document side is hole_snaps.py.

Fusion offers no snap point at the centre of a square (or any non-round) hole: its keypoints
are the ends, middles and centres of edges, circles and faces. VEX metal is full of square
holes on a half-inch grid, so SciForge adds one (a deliberate difference, marked (SciForge) in
docs/sciforge/parity/joints.md and direct-modify.md): the centre of area of every closed inner
outline of a flat face, offered on the face, on the outline's edges and (at both ends and
half-way) on the flat walls of the hole.

Points are (x, y, z) tuples; screen points (x, y) pixels.
"""

import math

# kinds of snap a hole gives
LOOP = "loop"  # the centre of a closed inner outline, on its face
HOLE_TOP = "hole_top"  # a hole's centre where it meets the face it was hovered from
HOLE_MID = "hole_mid"  # half-way through
HOLE_BOTTOM = "hole_bottom"  # where it comes out on the other side
HOLE_KINDS = (LOOP, HOLE_TOP, HOLE_MID, HOLE_BOTTOM)
SNAP_PIXELS = 8.0  # the pointer this near another dot takes that dot, not the hole's centre
ZONE = 1.6  # a hole's centre is taken while the pointer is within ZONE x its radius
MIN_ZONE_PIXELS = 10.0


# -- vectors -----------------------------------------------------------------------------------
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if n < 1e-15:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def distance(a, b):
    return length(sub(a, b))


# -- outlines --------------------------------------------------------------------------------------
def polygon_centroid(points, normal):
    """Centre of area of a flat polygon (its corners in order, 3D points in one plane with
    `normal`) and its area. A degenerate polygon gives its corners' average, area 0."""
    n = unit(normal)
    if len(points) < 3 or length(n) < 0.5:
        if not points:
            return (0.0, 0.0, 0.0), 0.0
        avg = scale(
            (sum(p[0] for p in points), sum(p[1] for p in points), sum(p[2] for p in points)),
            1.0 / len(points),
        )
        return avg, 0.0
    origin = points[0]
    total = 0.0
    acc = (0.0, 0.0, 0.0)
    for i in range(1, len(points) - 1):
        a = sub(points[i], origin)
        b = sub(points[i + 1], origin)
        area2 = dot(cross(a, b), n)  # twice the signed triangle area
        centre = scale(add(add(origin, points[i]), points[i + 1]), 1.0 / 3.0)
        acc = add(acc, scale(centre, area2))
        total += area2
    if abs(total) < 1e-15:
        return polygon_centroid(points[:2], (0.0, 0.0, 0.0))
    return scale(acc, 1.0 / total), abs(total) / 2.0


def outline_centroid(points, arcs, normal):
    """Centre of area and area of a flat outline made of straight sides and circular arcs:
    `points` its corners in order (3D, one plane with `normal`), `arcs` {i: (centre,
    radius, sweep radians, mid point)} for the side from points[i] to points[i + 1] that is
    an arc. Each arc adds (bulging out) or takes away (bulging in) the circular segment
    between its chord and itself; exact for rounded squares and slots, no face is made."""
    n = unit(normal)
    centre, area = polygon_centroid(points, n)
    if not arcs or area <= 0.0:
        return centre, area
    # the polygon's orientation about the normal (its interior on the left when > 0)
    origin = points[0]
    signed = 0.0
    for i in range(1, len(points) - 1):
        signed += dot(cross(sub(points[i], origin), sub(points[i + 1], origin)), n)
    orient = 1.0 if signed >= 0 else -1.0
    moment = scale(centre, area)
    total = area
    count = len(points)
    for i, (c, r, sweep, mid) in arcs.items():
        a, b = points[i % count], points[(i + 1) % count]
        theta = abs(sweep)
        if r <= 0 or theta <= 1e-12:
            continue
        seg = 0.5 * r * r * (theta - math.sin(theta))
        if seg <= 0:
            continue
        chord_mid = scale(add(a, b), 0.5)
        toward = unit(sub(mid, c)) if distance(mid, c) > 1e-12 else unit(sub(chord_mid, c))
        d = 4.0 * r * math.sin(theta / 2.0) ** 3 / (3.0 * (theta - math.sin(theta)))
        seg_centre = add(c, scale(toward, d))
        # outside the polygon (bulging out) when the arc's middle is right of a -> b
        side = dot(cross(sub(b, a), sub(mid, a)), n) * orient
        sign = -1.0 if side > 0 else 1.0
        moment = add(moment, scale(seg_centre, sign * seg))
        total += sign * seg
    if total <= 1e-15:
        return centre, area
    return scale(moment, 1.0 / total), total


def circumradius(centre, points):
    """The largest distance from the centre to the outline's points."""
    return max((distance(centre, p) for p in points), default=0.0)


def x_direction(sides, hint=None, normal=None):
    """X of a hole's snap: along its longest straight side (a list of (start, end) points);
    sides of (almost) the same length are told apart by the one nearest the `hint` direction
    (the face's own longest edge), so all the square holes of a part point the same way;
    turned to agree with the hint. None when there is no straight side."""
    best = []
    longest = 0.0
    for a, b in sides:
        d = sub(b, a)
        size = length(d)
        if size < 1e-9:
            continue
        if size > longest * 1.01:
            longest = size
            best = [d]
        elif size >= longest * 0.99:
            best.append(d)
    best = [d for d in best if length(d) >= longest * 0.99]
    if not best:
        return None
    if normal is not None:  # in the outline's plane
        n = unit(normal)
        best = [sub(d, scale(n, dot(d, n))) for d in best]
    if hint is not None and length(hint) > 1e-12:
        h = unit(hint)
        best.sort(key=lambda d: -abs(dot(unit(d), h)))
        chosen = unit(best[0])
        if dot(chosen, h) < 0:
            chosen = scale(chosen, -1.0)
        return chosen
    return unit(best[0])


# -- which dot the pointer takes -------------------------------------------------------------------
def choose_hot(candidates, pointer, reach=1e9, snap_pixels=SNAP_PIXELS):
    """Index of the dot a click would take. `candidates`: [(pixel (x, y), zone)] where zone
    is None for an ordinary dot and, for a hole's centre, how far (pixels) from the centre
    the hole "reaches" (ZONE x its radius on the screen). A dot within `snap_pixels` of the
    pointer wins (the nearest); else a hole whose zone holds the pointer (the one the pointer
    is deepest in); else the nearest dot within `reach`. None when nothing qualifies."""
    best_plain = None
    best_zone = None
    best_any = None
    for i, (pixel, zone) in enumerate(candidates):
        if pixel is None:
            continue
        d = math.hypot(pixel[0] - pointer[0], pixel[1] - pointer[1])
        if best_any is None or d < best_any[0]:
            best_any = (d, i)
        if zone is None:
            if best_plain is None or d < best_plain[0]:
                best_plain = (d, i)
        elif zone > 0 and d <= zone:
            depth = d / zone
            if best_zone is None or depth < best_zone[0]:
                best_zone = (depth, i)
    if best_plain is not None and best_plain[0] <= snap_pixels:
        if best_zone is None or candidates[best_zone[1]][0] is None:
            return best_plain[1]
        # a hole centre right under the pointer beats a dot a few pixels away
        zone_d = best_zone[0] * candidates[best_zone[1]][1]
        return best_zone[1] if zone_d < best_plain[0] else best_plain[1]
    if best_zone is not None:
        return best_zone[1]
    if best_any is not None and best_any[0] <= reach:
        return best_any[1]
    return None


def zone_pixels(radius_pixels):
    return max(MIN_ZONE_PIXELS, ZONE * radius_pixels)


# -- the hole a joint was made on, after an edit ---------------------------------------------------
def same_loop(stored, loop, tol=None):
    """True when `loop` ({"c", "n", "a", "r"}) is the stored one: same direction, about the
    same size, its centre within a small distance (an edit far away moved nothing)."""
    try:
        if dot(unit(stored["n"]), unit(loop["n"])) < 0.999:
            return False
        a0, a1 = float(stored.get("a", 0.0)), float(loop.get("a", 0.0))
        if a0 > 1e-9 and abs(a1 - a0) > 0.05 * a0:
            return False
        reach = tol if tol is not None else max(1e-4, 1e-3 * float(stored.get("r", 1.0)))
        return distance(stored["c"], loop["c"]) <= reach
    except Exception:
        return False


def best_loop(stored, loops):
    """Index of the loop that is most likely the stored one after an edit: same direction,
    about the same size (area within 5 %), the nearest centre, no farther than the hole's
    own radius (a hole that moved more than its size is taken to be gone). None if none."""
    best = None
    try:
        n0 = unit(stored["n"])
        a0 = float(stored.get("a", 0.0))
        r0 = max(float(stored.get("r", 0.0)), 1e-6)
        for i, loop in enumerate(loops):
            if dot(n0, unit(loop["n"])) < 0.999:
                continue
            a1 = float(loop.get("a", 0.0))
            if a0 > 1e-9 and abs(a1 - a0) > 0.05 * a0:
                continue
            d = distance(stored["c"], loop["c"])
            if d > r0:
                continue
            if best is None or d < best[0]:
                best = (d, i)
    except Exception:
        return None
    return None if best is None else best[1]


# -- many dots -------------------------------------------------------------------------------------
def dedupe_points(points, tol=1e-7):
    """Indices of the points to keep: the first of every group closer than `tol` (a grid of
    `tol`-sized cells, so a face with thousands of dots is not compared pair by pair)."""
    if tol <= 0:
        return list(range(len(points)))
    cells = {}
    kept = []
    for i, p in enumerate(points):
        key = (
            int(math.floor(p[0] / tol)),
            int(math.floor(p[1] / tol)),
            int(math.floor(p[2] / tol)),
        )
        clash = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in cells.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if distance(points[j], p) <= tol:
                            clash = True
                            break
                    if clash:
                        break
                if clash:
                    break
            if clash:
                break
        if not clash:
            cells.setdefault(key, []).append(i)
            kept.append(i)
    return kept


def nearest_indices(points, target, count):
    """The indices of the `count` points nearest to `target`, nearest first."""
    order = sorted(range(len(points)), key=lambda i: distance(points[i], target))
    return order[: max(0, int(count))]


# -- what a click takes ----------------------------------------------------------------------------
NEAR_HIT = 0.2  # FreeCAD's selection: an edge or a corner this near the first hit (squared, mm)


def hit_rank(element):
    """FreeCAD's pick priority (SoFCUnifiedSelection::getPriority): corner 3, edge 2, face 1."""
    element = str(element or "")
    for rank, prefix in ((3, "Vertex"), (2, "Edge"), (1, "Face")):
        if element.startswith(prefix):
            return rank
    return 0


def choose_hit(hits, owner=None):
    """The hit FreeCAD's selection takes of the hits along the pointer's ray (nearest first:
    dicts with x, y, z and Component, as view.getObjectsInfo gives them): of the hits on the
    first hit's object (`owner(hit)`), an edge or a corner right at the first hit wins over
    it (SoFCUnifiedSelection::getPickedList). None: no hit."""
    if not hits:
        return None
    owner = owner or (lambda hit: hit.get("Object"))
    best = first = hits[0]
    rank, who = hit_rank(first.get("Component")), owner(first)
    for hit in hits[1:]:
        if owner(hit) != who:
            break
        here = hit_rank(hit.get("Component"))
        d2 = sum((hit[k] - first[k]) ** 2 for k in ("x", "y", "z"))
        if here > rank and d2 <= NEAR_HIT:
            best, rank = hit, here
    return best

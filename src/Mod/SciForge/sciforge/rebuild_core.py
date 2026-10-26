# SPDX-License-Identifier: LGPL-2.1-or-later
"""Auto Timeline, the words of a comparison (pure Python: no FreeCAD, no Qt; unit tested in
SciForgeTests/unit/test_rebuild_core.py). rebuild.py measures the reference and the rebuilt
part with OpenCASCADE and hands this module plain numbers: what each region of missing or
extra material looks like ("a round hole about 6 mm across, 10 deep"), the regions grouped
the way a person would say them ("4 holes 6 mm across ... at (10, 10), (50, 10)..."), the
faces described in words, and the verdict: one paragraph that tells an AI (or a person)
exactly what to do next, in Fusion's order (the base shape first, then cuts and bosses,
holes, chamfers, fillets last). Spec: docs/sciforge/parity/auto-timeline.md.

A region is {"volume", "center": [x, y, z], "bbox": [x0, y0, z0, x1, y1, z1], "faces": [face
facts]}; a face's facts: {"type": "plane" | "cylinder" | "cone" | "sphere" | "torus" | ...,
"area", and by type "normal", "radius", "axis", "point", "length" (along the axis), "span"
(radians around it), "convex" (the region's material lies on the axis side: a solid
cylinder, a boss), "minor" / "major" (torus)}. "missing" material is in the original and not
(yet) in the rebuilt part; "extra" material is in the rebuilt part and not in the original:
a hole the rebuild has not cut yet is extra material shaped like a cylinder.
"""

import math

MATCH_DONE = 0.999  # the share of the volume that must agree (common / union) to be done
FACE_TOL = 1e-3  # mm: two faces on the same surface within this are the same face
MESH_TOL_SHARE = 0.002  # a reference from a mesh: faces agree within this share of its size
MESH_TOL_MIN, MESH_TOL_MAX = 0.02, 0.5

AXES = ("x", "y", "z")


# -- numbers in words ----------------------------------------------------------------------------
def num(value, digits=3):
    """A length or count the way a person writes it: 6, 6.5, 0.25, 12.346."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(value):
        return str(value)
    if abs(value) >= 100:
        digits = min(digits, 2)
    text = ("%%.%df" % digits) % value
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def about(value):
    """A measured size rounded for words: 5.9998 -> 6, 2.4996 -> 2.5, 0.123 -> 0.12."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    size = abs(value)
    if size >= 10:
        return num(round(value, 1), 1)
    if size >= 1:
        return num(round(value, 2), 2)
    return num(round(value, 3), 3)


def point_text(point, axis=None):
    """(x, y) for something along Z (its place seen from the top), (x, z) along Y, (y, z)
    along X; (x, y, z) otherwise."""
    if point is None:
        return "?"
    k = _axis_index(axis)
    if k is None:
        return "(%s)" % ", ".join(num(round(c, 3)) for c in point)
    keep = [c for i, c in enumerate(point) if i != k]
    return "(%s)" % ", ".join(num(round(c, 3)) for c in keep)


def axis_name(axis):
    """ "Z" for [0, 0, 1] or [0, 0, -1]; "" for a slanted direction."""
    k = _axis_index(axis)
    return AXES[k].upper() if k is not None else ""


def _axis_index(axis, tol=1e-6):
    if not axis or len(axis) != 3:
        return None
    for k in range(3):
        if abs(abs(axis[k]) - 1.0) < tol:
            return k
    return None


def _unit(v):
    length = math.sqrt(sum(c * c for c in v)) if v else 0.0
    return [c / length for c in v] if length > 1e-12 else [0.0, 0.0, 0.0]


def direction_text(vector):
    """+Z, -X..., or [0.6, 0, 0.8] for a slanted one."""
    k = _axis_index(vector)
    if k is not None:
        return ("+" if vector[k] > 0 else "-") + AXES[k].upper()
    return "[%s]" % ", ".join(num(round(c, 4), 4) for c in vector)


def mesh_tolerance(size):
    """How closely the faces of a reference made from a mesh are expected to agree with the
    rebuilt part (a mesh is flat facets: a 6 mm hole of 32 facets is 0.014 mm off)."""
    try:
        size = float(size)
    except (TypeError, ValueError):
        size = 0.0
    return min(MESH_TOL_MAX, max(MESH_TOL_MIN, MESH_TOL_SHARE * size))


# -- one region ----------------------------------------------------------------------------------
def _dims(region):
    box = region.get("bbox") or [0, 0, 0, 0, 0, 0]
    return [max(0.0, box[3] - box[0]), max(0.0, box[4] - box[1]), max(0.0, box[5] - box[2])]


def _curved(region, kinds=("cylinder", "torus", "sphere", "cone")):
    return [f for f in region.get("faces", []) if f.get("type") in kinds]


def _planes(region):
    return [f for f in region.get("faces", []) if f.get("type") == "plane"]


def _close(a, b, share):
    return abs(a - b) <= share * max(abs(a), abs(b), 1e-12)


def classify_region(region, side):
    """What a region of material looks like, as a feature: {"kind", "looks_like", plus its
    numbers ("diameter", "depth", "radius", "size"...)}. side: "missing" (in the original,
    not in the rebuild) or "extra" (in the rebuild, not in the original)."""
    volume = float(region.get("volume") or 0.0)
    dims = _dims(region)
    found = (
        _cylinder(region, volume, side)
        or _fillet(region, volume, side)
        or _chamfer(region, volume, dims, side)
        or _block(region, volume, dims, side)
    )
    if found is None:
        found = {
            "kind": "other",
            "size": [round(d, 6) for d in dims],
            "looks_like": "a %s region about %s (%s mm3)"
            % (
                "piece of material" if side == "missing" else "piece of extra material",
                " x ".join(about(d) for d in dims),
                about(volume),
            ),
        }
    found["side"] = side
    return found


def _cylinder(region, volume, side):
    """A hole (extra material shaped like a cylinder) or a boss / pin (missing)."""
    curved = _curved(region, ("cylinder",))
    full = [
        f
        for f in curved
        if f.get("convex") and f.get("radius") and f.get("span", 0.0) >= 1.9 * math.pi
    ]
    if not full:
        return None
    # the biggest full cylinder; others on the same axis make it stepped (a counterbore)
    full.sort(key=lambda f: -f["radius"])
    main = full[0]
    axis = _unit(main.get("axis") or [0, 0, 1])
    same_axis = [f for f in full if _parallel(f.get("axis"), axis)]
    others = [f for f in _curved(region) if f not in same_axis and f.get("type") != "cone"]
    expected = sum(math.pi * f["radius"] ** 2 * f.get("length", 0.0) for f in same_axis)
    if expected <= 0 or others:
        return None
    cones = [f for f in _curved(region, ("cone",))]
    share = 0.04 if not cones else 0.25  # a drill point (a cone end) adds up to a third
    if not (volume <= expected * (1 + share) and volume >= expected * (1 - 0.04)):
        return None
    depth = sum(f.get("length", 0.0) for f in same_axis)
    if cones:
        depth = max(depth, _extent_along(region, axis))
    out = {
        "kind": "cylinder" if len(same_axis) == 1 else "stepped_cylinder",
        "diameter": round(2 * main["radius"], 9),
        "depth": round(depth, 9),
        "axis": [round(c, 9) for c in axis],
        "at": [round(c, 9) for c in (main.get("point") or region.get("center") or [0, 0, 0])],
    }
    across = about(2 * main["radius"])
    if len(same_axis) > 1:
        steps = sorted(same_axis, key=lambda f: -f["radius"])
        words = ", then ".join(
            "%s mm across %s %s"
            % (
                about(2 * f["radius"]),
                about(f.get("length", 0.0)),
                "deep" if side == "extra" else "tall",
            )
            for f in steps
        )
        out["steps"] = [
            {"diameter": round(2 * f["radius"], 9), "depth": round(f.get("length", 0.0), 9)}
            for f in steps
        ]
        out["looks_like"] = (
            "a stepped round hole (counterbore): %s" % words
            if side == "extra"
            else "a stepped round boss: %s" % words
        )
        return out
    end = " with a pointed (drilled) end" if cones else ""
    if side == "extra":
        out["looks_like"] = "a round hole about %s mm across, %s deep%s" % (
            across,
            about(depth),
            end,
        )
    else:
        out["looks_like"] = "a round boss (pin) about %s mm across, %s tall%s" % (
            across,
            about(depth),
            end,
        )
    return out


def _extent_along(region, axis):
    box = region.get("bbox") or [0, 0, 0, 0, 0, 0]
    k = _axis_index(axis, 1e-3)
    if k is not None:
        return box[k + 3] - box[k]
    dims = _dims(region)
    return max(dims)


def _parallel(a, b, tol=1e-6):
    if not a or not b:
        return False
    a, b = _unit(a), _unit(b)
    return abs(sum(x * y for x, y in zip(a, b))) > 1 - tol


def _fillet(region, volume, side):
    """A rounded edge: the corner strip between two faces and a round face of radius r.
    Its cross-section is r^2 (1 - pi/4); several edges of one radius (chained around a
    corner) are one region."""
    curved = _curved(region, ("cylinder", "torus", "sphere"))
    if not curved:
        return None
    radii = []
    length = 0.0
    for f in curved:
        if f.get("convex"):
            return None  # the region would be inside the round face: not a corner strip
        r = f.get("minor") if f.get("type") == "torus" else f.get("radius")
        if not r:
            return None
        radii.append(r)
        if f.get("type") == "cylinder":
            length += f.get("length", 0.0)
    r = max(radii)
    if any(not _close(x, r, 0.02) for x in radii) or length <= 0:
        return None
    expected = (1 - math.pi / 4) * r * r * length
    if not (0.75 * expected <= volume <= 1.3 * expected + 0.6 * r**3):
        return None
    edges = sum(1 for f in curved if f.get("type") == "cylinder")
    out = {"kind": "fillet", "radius": round(r, 9), "length": round(length, 9), "edges": edges}
    many = " (%d edges, %s mm long in all)" % (edges, about(length)) if edges > 1 else ""
    if side == "extra":
        out["looks_like"] = "a rounded edge, radius about %s%s" % (about(r), many)
    else:
        out["looks_like"] = "a rounded inside corner (fillet), radius about %s%s" % (
            about(r),
            many,
        )
    return out


def _chamfer(region, volume, dims, side):
    """A chamfered edge: a strip with a triangle cross-section, flat faces only."""
    if _curved(region) or len(_planes(region)) < 5:
        return None
    ordered = sorted(dims)
    a, b, length = ordered
    if length <= 0 or a <= 0 or length < 3 * b:
        return None
    if not 0.45 <= volume / (a * b * length) <= 0.55:
        return None
    out = {"kind": "chamfer", "distances": [round(a, 9), round(b, 9)], "length": round(length, 9)}
    sizes = about(a) if _close(a, b, 0.02) else "%s x %s" % (about(a), about(b))
    if side == "extra":
        out["looks_like"] = "a chamfered edge, about %s (%s mm long)" % (sizes, about(length))
    else:
        out["looks_like"] = "a filled inside corner (a strip with a triangle section), about %s" % (
            sizes
        )
    return out


def _block(region, volume, dims, side):
    """A box of material (a pocket or slot the rebuild has not cut, a block or a step it
    has not built), or a thin layer: the rebuilt part is too tall / short there."""
    if _curved(region):
        return None
    box_volume = dims[0] * dims[1] * dims[2]
    if box_volume <= 0 or volume < 0.98 * box_volume:
        return None
    ordered = sorted(dims)
    thin = ordered[0] < 0.12 * ordered[1]
    out = {"kind": "layer" if thin else "block", "size": [round(d, 9) for d in dims]}
    size = " x ".join(about(d) for d in dims)
    if thin:
        k = dims.index(ordered[0])
        out["thin_axis"] = AXES[k]
        out["thickness"] = round(ordered[0], 9)
        out["looks_like"] = "a layer about %s thick (%s) %s" % (
            about(ordered[0]),
            size,
            "the rebuild lacks" if side == "missing" else "the rebuild has too much",
        )
    elif side == "extra":
        out["looks_like"] = "a block %s of material to cut away (a pocket, slot or step)" % size
    else:
        out["looks_like"] = "a block %s of material to add (a boss, rib or step)" % size
    return out


# -- groups --------------------------------------------------------------------------------------
_ORDER = {  # Fusion's order of features: the base first, fillets last
    "layer": 0,
    "other": 1,
    "block": 2,
    "stepped_cylinder": 3,
    "cylinder": 4,
    "chamfer": 5,
    "fillet": 6,
}


def _key(region):
    shape = region.get("shape", {})
    kind = shape.get("kind", "other")
    if kind in ("cylinder", "stepped_cylinder"):
        return (
            region["side"],
            kind,
            round(shape["diameter"], 2),
            round(shape["depth"], 2),
            axis_name(shape.get("axis")),
        )
    if kind == "fillet":
        return (region["side"], kind, round(shape["radius"], 2))
    if kind == "chamfer":
        return (region["side"], kind, tuple(round(d, 2) for d in shape["distances"]))
    return (region["side"], kind, id(region))


def group_regions(regions, big=0.05, reference_volume=0.0):
    """Regions of the same kind and size together (four equal holes are one line), in the
    order to build them: big differences of the base shape first, fillets last. Each group:
    {"side", "kind", "count", "regions", "volume", "first"}."""
    groups = {}
    order = []
    for region in regions:
        key = _key(region)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(region)
    out = []
    for key in order:
        items = groups[key]
        shape = items[0].get("shape", {})
        volume = sum(r.get("volume", 0.0) for r in items)
        kind = shape.get("kind", "other")
        rank = _ORDER.get(kind, 1)
        if reference_volume > 0 and volume >= big * reference_volume and kind != "fillet":
            rank = -1  # a big difference: the base shape is not right yet
        out.append(
            {
                "side": items[0]["side"],
                "kind": kind,
                "count": len(items),
                "regions": items,
                "volume": volume,
                "rank": rank,
            }
        )
    out.sort(key=lambda g: (g["rank"], -g["volume"]))
    return out


def group_text(group, places=4):
    """One group in words: "4 round holes about 6 mm across, 10 deep (along Z) are not cut
    yet, at (10, 10), (50, 10), ..."."""
    first = group["regions"][0]
    shape = first.get("shape", {})
    kind = group["kind"]
    count = group["count"]
    side = group["side"]
    if kind in ("cylinder", "stepped_cylinder"):
        axis = shape.get("axis")
        where = ", ".join(point_text(r["shape"].get("at"), axis) for r in group["regions"][:places])
        if count > places:
            where += " and %d more" % (count - places)
        line = "along %s" % (axis_name(axis) or direction_text(axis))
        what = shape["looks_like"]
        if count > 1:
            what = "%d %s" % (count, _plural(what))
        verb = "are" if count > 1 else "is"
        state = "not cut yet" if side == "extra" else "missing"
        return "%s (%s) %s %s, at %s" % (what, line, verb, state, where)
    if kind == "fillet":
        edges = sum(r["shape"].get("edges", 1) for r in group["regions"])
        radius = about(shape["radius"])
        if side == "extra":
            if edges == 1:
                return "1 rounded edge of radius about %s is still sharp in the rebuild" % radius
            return "%d rounded edges of radius about %s are still sharp in the rebuild" % (
                edges,
                radius,
            )
        return "%d rounded inside corner%s (fillet) of radius about %s %s missing" % (
            edges,
            "s" if edges > 1 else "",
            radius,
            "are" if edges > 1 else "is",
        )
    if kind == "chamfer":
        if count > 1:
            return "%d strips like %s" % (count, shape["looks_like"])
        return shape["looks_like"]
    centre = first.get("center")
    where = " at %s" % point_text(centre) if centre else ""
    if count > 1:
        return "%d regions like %s" % (count, shape["looks_like"] + where)
    return shape["looks_like"] + where


# -- faces in words --------------------------------------------------------------------------------
def describe_face(facts):
    """A face in words: "a flat face 40 x 30 facing +Z at z = 10", "a round hole face 6 mm
    across along Z at (10, 10)"."""
    kind = facts.get("type", "other")
    area = facts.get("area_mm2", facts.get("area", 0.0))
    if kind == "plane":
        normal = facts.get("normal") or [0, 0, 1]
        box = facts.get("bbox_mm") or facts.get("bbox")
        size = ""
        k = _axis_index(normal, 1e-6)
        if box and k is not None:
            dims = [box[i + 3] - box[i] for i in range(3) if i != k]
            size = " %s" % " x ".join(about(d) for d in dims)
            where = " at %s = %s" % (AXES[k], about(box[k]))
        else:
            centre = facts.get("center_mm") or facts.get("center")
            where = " through %s" % point_text(centre) if centre else ""
        return "a flat face%s facing %s%s (%s mm2)" % (
            size,
            direction_text(normal),
            where,
            about(area),
        )
    if kind == "cylinder":
        radius = facts.get("radius_mm", facts.get("radius", 0.0))
        axis = facts.get("axis") or [0, 0, 1]
        point = facts.get("axis_point_mm") or facts.get("point")
        concave = facts.get("concave")
        what = "a round face"
        if concave is True:
            what = "a round hole face"
        elif concave is False:
            what = "a round outer face"
        line = axis_name(axis) or direction_text(axis)
        return "%s %s mm across along %s at %s (%s mm2)" % (
            what,
            about(2 * radius),
            line,
            point_text(point, axis),
            about(area),
        )
    if kind == "torus":
        return "a rounded (torus) face, radius about %s around a %s mm circle (%s mm2)" % (
            about(facts.get("minor_radius_mm", facts.get("minor", 0.0))),
            about(2 * facts.get("major_radius_mm", facts.get("major", 0.0))),
            about(area),
        )
    if kind == "sphere":
        return "a ball face, radius about %s (%s mm2)" % (
            about(facts.get("radius_mm", facts.get("radius", 0.0))),
            about(area),
        )
    if kind == "cone":
        return "a cone face, half angle %s deg (%s mm2)" % (
            about(facts.get("half_angle_deg", 0.0)),
            about(area),
        )
    centre = facts.get("center_mm") or facts.get("center")
    return "a %s face near %s (%s mm2)" % (
        "free-form" if kind in ("bspline", "other") else kind,
        point_text(centre),
        about(area),
    )


# -- the verdict ---------------------------------------------------------------------------------
def size_notes(ref_box, new_box, tol=FACE_TOL):
    """How the rebuilt part's overall size differs: ["it is 2 mm taller (Z): 0 to 12, the
    original 0 to 10"]."""
    notes = []
    if not ref_box or not new_box:
        return notes
    words = {"x": ("longer", "shorter"), "y": ("deeper", "shallower"), "z": ("taller", "lower")}
    for k, axis in enumerate(AXES):
        r0, r1 = ref_box[k], ref_box[k + 3]
        n0, n1 = new_box[k], new_box[k + 3]
        grow = (n1 - n0) - (r1 - r0)
        moved = abs(n0 - r0) > tol or abs(n1 - r1) > tol
        if not moved:
            continue
        if abs(grow) > tol:
            notes.append(
                "it is %s mm %s along %s (%s to %s; the original %s to %s)"
                % (
                    about(abs(grow)),
                    words[axis][0 if grow > 0 else 1],
                    axis.upper(),
                    about(n0),
                    about(n1),
                    about(r0),
                    about(r1),
                )
            )
        else:
            notes.append(
                "it is shifted %s mm along %s (%s to %s; the original %s to %s)"
                % (about(n0 - r0), axis.upper(), about(n0), about(n1), about(r0), about(r1))
            )
    return notes


def verdict(result, limit=3):
    """The paragraph that says what to do next, from compare's dict (plus "groups":
    group_regions of its missing + extra regions, and "size_notes")."""
    match = result.get("match", 0.0)
    faces = result.get("faces", {})
    total = faces.get("reference", 0)
    matched = faces.get("matched", 0)
    left_over = len(faces.get("unmatched_rebuilt", []))
    if result.get("empty"):
        return (
            "The rebuilt body is still empty: build the base shape first (describe_reference "
            "gives the plan; its step 1 is the base), then compare_to_reference again."
        )
    if result.get("done"):
        return (
            "Done: the rebuilt part matches the original (match %s, all %d faces matched). "
            "Call finish_rebuild." % (num(match, 6), total)
        )
    head = "Match %s (1 is identical); %d of %d faces of the original matched." % (
        num(match, 4),
        matched,
        total,
    )
    todo = []
    notes = result.get("size_notes") or []
    if notes and match < MATCH_DONE:
        todo.append("Overall: " + "; ".join(notes) + ".")
    groups = result.get("groups") or []
    for group in groups[:limit]:
        line = _capital(group_text(group))
        if group.get("fix_at") is not None:
            line += " (the %s call is ready in groups[%d].fix)" % (
                group["regions"][0].get("fix", {}).get("tool", "tool"),
                group["fix_at"],
            )
        todo.append(line + ".")
    if len(groups) > limit:
        todo.append(
            "And %d more difference%s (missing / extra list them)."
            % (
                len(groups) - limit,
                "s" if len(groups) - limit > 1 else "",
            )
        )
    if not groups and total - matched > 0:
        first = faces.get("unmatched_reference", [])[:2]
        words = "; ".join(f.get("describe", "") for f in first)
        todo.append(
            "No material differs by more than a sliver, but %d face%s of the original %s not "
            "matched yet (a size or place slightly off, or a face the rebuild splits "
            "differently): %s."
            % (
                total - matched,
                "s" if total - matched > 1 else "",
                "are" if total - matched > 1 else "is",
                words,
            )
        )
    if not groups and left_over and total == matched:
        first = faces.get("unmatched_rebuilt", [])[:2]
        words = "; ".join(f.get("describe", "") for f in first)
        todo.append(
            "Every face of the original is matched, but the rebuild has %d face%s the "
            "original does not: %s." % (left_over, "s" if left_over > 1 else "", words)
        )
    if not todo:
        todo.append("Look at missing / extra and the unmatched faces.")
    return head + " Next: " + " ".join(todo) + " Fix that, then compare_to_reference again."


def _capital(text):
    return text[:1].upper() + text[1:] if text else text


_PLURALS = (
    ("a stepped round hole (counterbore)", "stepped round holes (counterbores)"),
    ("a stepped round boss", "stepped round bosses"),
    ("a round hole", "round holes"),
    ("a round boss (pin)", "round bosses (pins)"),
)


def _plural(text):
    """ "a round hole about 6 mm across, 10 deep" -> "round holes about 6 mm across, 10
    deep"."""
    for one, many in _PLURALS:
        if text.startswith(one):
            return many + text[len(one) :]
    return text[2:] if text.startswith("a ") else text


# -- the message a person sends an AI ------------------------------------------------------------
def chat_message(body_label, rebuilt_label=None, mesh=False):
    """The ready message of Rebuild with Timeline (AI)...: the person reads it, may change
    it, and sends it to the built-in chat or pastes it into an AI app."""
    rebuilt = rebuilt_label or "%s (rebuilt)" % body_label
    source = "mesh body" if mesh else "body"
    return (
        'Rebuild the %s "%s" with a timeline, so it becomes a real parametric part. SciForge '
        'has frozen it as the reference and made the empty body "%s" (active) for the new '
        "steps. Read the recipe recipes/reverse-engineer.md (docs_read), then: call "
        "describe_reference for its features and a plan, build the plan step by step with "
        "the normal tools (key sizes as user parameters), call compare_to_reference after "
        "every feature and fix what its verdict says, and call finish_rebuild when it says "
        "done." % (source, body_label, rebuilt)
    )

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's Duplicate With Joints (ASSEMBLE): the document side, no Qt (the dialog is
duplicate_joints_ui.py; spec docs/sciforge/parity/vex-assembly.md).

Fusion: pick components that are already joined (a screw; a screw and its nut), pick the
**open** joint (one that goes from them to a component outside the selection), then click new
places with the Simple or Between Two Faces origin modes: each click adds a duplicate, joined
there; **enclosed** joints (between two selected components, such as screw and nut) are
duplicated with them.

SciForge: each duplicate is an occurrence of the component (instances.make_instance: linked,
"Screw:2"), placed by a new joint of the open joint's type, offsets, axes and limits from
the occurrence's copy of the open joint's snap to the clicked one (the occurrence moves, as
component 1 of a Joint does); the other selected components' occurrences keep where they
were relative to it, and the enclosed joints (and Rigid Groups that hold two or more of the
selected components together) are made again between the occurrences.
"""

import FreeCAD as App

from . import components, instances, joints, log


class DuplicateError(ValueError):
    """Duplicate With Joints cannot do what was asked; the message says why and what to do."""


def open_joints(members):
    """The joints that go from `members` (parts) to a part outside them: [(joint, side)] with
    side 0 when the member is the joint's component 1."""
    names = {m.Name for m in members}
    found = []
    for joint in joints.joints(members[0].Document) if members else []:
        p1, p2 = joints.part1(joint), joints.part2(joint)
        if p1 is None or p2 is None or getattr(joint, "Suppressed", False):
            continue
        if (p1.Name in names) != (p2.Name in names):
            found.append((joint, 0 if p1.Name in names else 1))
    return found


def enclosed_joints(members):
    """The joints between two of `members` (a screw and its nut)."""
    names = {m.Name for m in members}
    found = []
    for joint in joints.joints(members[0].Document) if members else []:
        p1, p2 = joints.part1(joint), joints.part2(joint)
        if p1 is not None and p2 is not None and p1.Name in names and p2.Name in names:
            found.append(joint)
    return found


def enclosed_groups(members):
    """The Rigid Groups that hold two or more of `members` together (a screw and its nut
    put in a Rigid Group instead of a joint): [(group, those members in the group's order)].
    (Fusion lists Rigid Groups with the joints; the copies are held together the same way,
    else a later move of a screw's copy left its nut's copy behind: beta 3 QA.)"""
    names = {m.Name for m in members}
    found = []
    for group in joints.rigid_groups(members[0].Document) if members else []:
        if getattr(group, "Suppressed", False):
            continue
        inside = [m for m in (group.Members or []) if m is not None and m.Name in names]
        if len(inside) >= 2:
            found.append((group, inside))
    return found


def _record(joint, side):
    return joints._json(joint, joints.PROPS["snap1" if side == 0 else "snap2"])


def check(members, joint, side):
    """'' when the open joint can be duplicated, else why not."""
    if not members:
        return "Pick the jointed components to duplicate (a screw, or a screw and its nut)."
    if joint is None:
        return "%s has no joint to a component outside the selection." % ", ".join(
            m.Label for m in members
        )
    record = _record(joint, side)
    if record.get("kind") in ("asbuilt", "origin") or not record:
        return (
            "%s is not made on a face, an edge or a corner of %s (an as-built joint or a "
            "joint origin): Duplicate With Joints needs one that is."
            % (joint.Label, _part(joint, side).Label)
        )
    return ""


def _part(joint, side):
    return joints.part1(joint) if side == 0 else joints.part2(joint)


def _copy_body(copy, body):
    """The body of the occurrence `copy` that repeats `body` (a body of the original, or a
    copy of it in another occurrence)."""
    wanted = instances.source_body(body) or body
    for feature, made in instances.copy_features(copy):
        try:
            if feature.Source is wanted and made is not None:
                return made
        except Exception:
            continue
    return None


def _moved_pick(joint, side, copies):
    """The joint's pick on one side, moved onto the occurrence that copies its part."""
    ref = joint.Reference1 if side == 0 else joint.Reference2
    record = _record(joint, side)
    part = ref[0]
    copy = copies.get(part.Name)
    if copy is None:
        raise DuplicateError("%s is not among the components to duplicate." % part.Label)
    obj = joints.shape_owner(ref)
    if obj is None or not hasattr(obj, "Shape"):
        raise DuplicateError("%s's joint is not on a body." % part.Label)
    body = obj if obj.TypeId == "PartDesign::Body" else None
    if body is None:
        raise DuplicateError("%s's joint is not on a body: it cannot be duplicated." % part.Label)
    made = _copy_body(copy, body)
    if made is None:
        raise DuplicateError("%s has no copy of %s." % (copy.Label, body.Label))
    element = record.get("element") or joints.element_name(ref[1][0])
    pick = joints.Pick(copy, made, element)
    snap = {"kind": record.get("kind"), "at": record.get("at", ""), "oriented": True}
    if record.get("kind") in ("twofaces", "twoedges"):
        snap["record"] = dict(record)
    if record.get("loop"):
        snap["loop"] = record["loop"]
    return pick, snap


def _copy_settings(source, target):
    """Type, offsets, axes and limits of `source` onto `target`."""
    joints.set_offset(target, **{k: v for k, v in joints.offsets(source).items()})
    axes = joints._json(
        source, joints.PROPS["axes"], joints.default_axes(joints.fusion_type(source))
    )
    try:
        joints.set_axes(target, **{k: v for k, v in axes.items() if v in ("x", "y", "z")})
    except Exception:
        pass
    lim = joints.limits(source)
    try:
        joints.set_limits(target, angle=lim["angle"], slide=lim["slide"])
    except Exception:
        pass


def duplicate(doc, members, joint, side, pick, snap):
    """One duplicate of `members` (parts), joined at (pick, snap) like `joint` (an open joint;
    `side`: the member's side of it). Returns (occurrences, joints made). The caller holds
    the undo step."""
    why = check(members, joint, side)
    if why:
        raise DuplicateError(why)
    if pick is None or snap is None:
        raise DuplicateError("Click a snap point where the copy goes (a hole's centre...).")
    if any(pick.part is m for m in members):
        raise DuplicateError(
            "Click where the copy goes on another component, not on %s." % pick.part.Label
        )
    copies, made = {}, []
    try:
        return _duplicate(doc, members, joint, side, pick, snap, copies, made)
    except Exception:
        _take_back(doc, copies, made)  # a copy that failed half way leaves nothing behind
        raise


def _take_back(doc, copies, made):
    for new in reversed(made):
        try:
            joints.delete_joint(new)
        except Exception as exc:
            log("Duplicate With Joints: %s not removed (%s)" % (new.Name, exc))
    for copy in copies.values():
        try:
            components.remove(doc, copy, _top=False)
        except Exception as exc:
            log("Duplicate With Joints: %s not removed (%s)" % (copy.Name, exc))
    try:
        doc.recompute()
    except Exception:
        pass


def _duplicate(doc, members, joint, side, pick, snap, copies, made):
    for member in members:
        copies[member.Name] = instances.make_instance(
            member, components.KEEP, placement=joints.global_placement(member)
        )
    doc.recompute()  # the occurrences' copies take their shapes
    inside = _part(joint, side)
    pick1, snap1 = _moved_pick(joint, side, copies)
    kind = joints.fusion_type(joint)
    made.append(joints.create_joint(doc, kind, pick1, snap1, pick, snap))
    _copy_settings(joint, made[0])
    copy_inside = copies[inside.Name]
    before = joints.global_placement(copy_inside)
    joints.align(made[0], first=True)
    moved = joints.global_placement(copy_inside).multiply(before.inverse())
    for member in members:  # the others keep where they were, relative to it
        if member is inside:
            continue
        other = copies[member.Name]
        joints.set_global_placement(other, moved.multiply(joints.global_placement(other)))
    for enclosed in enclosed_joints(members):
        a = _moved_pick(enclosed, 0, copies)
        b = _moved_pick(enclosed, 1, copies)
        new = joints.create_joint(doc, joints.fusion_type(enclosed), a[0], a[1], b[0], b[1])
        _copy_settings(enclosed, new)
        joints.refresh_placements(new)
        made.append(new)
    for group, inside in enclosed_groups(members):
        held = joints.create_rigid_group(
            doc, [copies[m.Name] for m in inside], bool(getattr(group, "IncludeChildren", True))
        )
        made.append(held)
    code = joints.solve(doc)
    text = joints.solve_message(code)
    if text:
        raise DuplicateError(text)
    log(
        "duplicated %s with %s at %s"
        % (", ".join(m.Label for m in members), joint.Label, pick.part.Label)
    )
    return list(copies.values()), made


def label_of(members):
    return ", ".join(m.Label for m in members)


def default_joint(members):
    """The open joint to duplicate when there is just one (else None: the person picks)."""
    found = open_joints(members)
    return found[0] if len(found) == 1 else (None, 0)


def global_point(snap):
    try:
        return App.Vector(snap["point"])
    except Exception:
        return None

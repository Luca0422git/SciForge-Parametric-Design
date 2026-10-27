# SPDX-License-Identifier: LGPL-2.1-or-later
"""Simulation studies in a design (Fusion's Simulation workspace, Static Stress), the document
side: no Qt. The rules (settings, kinds, units, safety factor, colours, pre-check) are in
simulation_core.py; the dialogs in simulation_ui.py; the results display in
simulation_results_ui.py. Spec: docs/sciforge/parity/simulation.md.

How a study is kept (saved with the design, never a timeline step, never in the browser's
design folders):

- A **study** is an App::FeaturePython (SciForgeType "SimStudy", proxy StudyProxy) holding its
  type, settings and study materials as JSON (`SciForgeSimStudy`), the bodies it simulates
  (`SimBodies`; empty = the design's bodies, design_bodies), and a summary of its last
  solve (`SciForgeSimResult`).
- Every **constraint** and **load** is an App::FeaturePython of its own (SciForgeType
  "SimItem", proxy ItemProxy): its picks in `References` (faces / edges / corners of the
  design's bodies, so FreeCAD keeps them through renames and edits), its kind and options as
  JSON (`SciForgeSimItem`), `Suppressed`, and the study it belongs to (`SimStudy`).
- A **solve** makes the study's hidden run (`SimRun`, a FreeCAD Fem::FemAnalysis, SciForgeType
  "SimRun"): the simulation model (`SimModel`, a Part::Feature holding the study's solids in
  design coordinates; touching bodies, and bodies closer than the contact tolerance, are split
  where they meet so the mesh is shared and they are glued, Fusion's bonded contacts),
  FreeCAD's Gmsh mesh, CalculiX solver, materials, forces, pressures and gravity made from the
  study's items (picks found again on the model by their geometry), and the results CalculiX
  gives back (a Fem::FemResultObject; the safety factor at every node is kept in its
  UserDefined list). A new solve replaces the run only once it has succeeded: a failed or
  cancelled solve leaves the last results as they were (out of date).
- The **constraints** (Fixed, Pin, Frictionless, Prescribed Displacement), the loads FreeCAD
  has no object for (Moment, Bearing Load, Remote Force) and Remove rigid body modes are
  written into CalculiX's input by SciForge itself, node by node
  (simulation_core.node_constraints merges what several constraints ask of one node), with a
  reaction force printed for every constraint (summary "reactions").
- **Generate Mesh** (`Job(study, mesh_only=True)`) makes a run with only the mesh
  (`SimMeshRun`), next to the last results; `mesh_object()` / `mesh_summary()` read it.
- A **local mesh control** is a study item too (category "mesh"): smaller elements on its
  faces, edges or bodies, blending into the global size (Gmsh size fields).

Solving: `solve(study)` does everything and waits (scripts, the AI, tests); `Job(study)` does
the same in stages so a dialog stays responsive: model, mesh, input, solver and results, with
the slow programs (Gmsh, CalculiX, Netgen when Gmsh cannot mesh) in a background thread and
everything that touches the document on the caller's thread (`Job.poll()` from a timer), and
`Job.cancel()`. Nothing a solve makes lands in the undo history (an undo step the caller left
open is closed first), and its temporary folder is removed whatever happens.
"""

import functools
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time

import FreeCAD as App

from . import bodies, log, warn
from . import simulation_core as core

STUDY = "SimStudy"
ITEM = "SimItem"
RUN = "SimRun"
MODEL = "SimModel"
HELPER = "SimHelper"  # a hidden line that gives a FreeCAD force its direction
STUDY_PROP = "SciForgeSimStudy"  # JSON: {"type", "settings", "materials"}
ITEM_PROP = "SciForgeSimItem"  # JSON: {"category", "kind", "options"}
RESULT_PROP = "SciForgeSimResult"  # JSON: the summary of the last solve
MESH_PROP = "SciForgeSimMesh"  # JSON: the statistics of the last mesh (Generate Mesh or solve)
TYPE_PROP = "SciForgeType"
GEOMETRY_TOL = 1e-3  # mm: a model face lies on a picked face when its points are this close

SimulationError = core.SimulationError


# -- the saved objects (module and class names are written into files: never rename) -------------
class StudyProxy:
    """A simulation study. Saved as "sciforge.simulation.StudyProxy"."""

    def __init__(self, obj):
        obj.Proxy = self
        StudyProxy.ensure(obj)

    @staticmethod
    def ensure(obj):
        bodies.add_prop(obj, "App::PropertyString", STUDY_PROP, "SciForge")
        bodies.add_prop(obj, "App::PropertyString", RESULT_PROP, "SciForge")
        bodies.add_prop(obj, "App::PropertyString", MESH_PROP, "SciForge")
        bodies.add_prop(obj, "App::PropertyLinkListHidden", "SimBodies", "SciForge")
        bodies.add_prop(obj, "App::PropertyLinkHidden", "SimRun", "SciForge")
        bodies.add_prop(obj, "App::PropertyLinkHidden", "SimMeshRun", "SciForge")

    def onDocumentRestored(self, obj):
        StudyProxy.ensure(obj)

    def execute(self, obj):
        pass

    def onChanged(self, obj, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ItemProxy:
    """A constraint or load of a study. Saved as "sciforge.simulation.ItemProxy"."""

    def __init__(self, obj):
        obj.Proxy = self
        ItemProxy.ensure(obj)

    @staticmethod
    def ensure(obj):
        bodies.add_prop(obj, "App::PropertyString", ITEM_PROP, "SciForge")
        bodies.add_prop(obj, "App::PropertyLinkHidden", "SimStudy", "SciForge")
        if "References" not in obj.PropertiesList:
            obj.addProperty(
                "App::PropertyLinkSubListGlobal", "References", "SciForge", "What it is on"
            )
        bodies.add_prop(obj, "App::PropertyBool", "Suppressed", "SciForge", hidden=False)

    def onDocumentRestored(self, obj):
        ItemProxy.ensure(obj)

    def execute(self, obj):
        pass

    def onChanged(self, obj, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


# -- finding studies and items ---------------------------------------------------------------------
def _type(obj):
    try:
        return getattr(obj, TYPE_PROP, "") or ""
    except Exception:
        return ""


def is_study(obj):
    return _type(obj) == STUDY


def is_item(obj):
    return _type(obj) == ITEM


def is_simulation_object(obj):
    """Anything a study made (study, item, run, model, FreeCAD's FEM objects inside a run):
    never a body, a step or a design folder entry."""
    if _type(obj) in (STUDY, ITEM, RUN, MODEL, HELPER):
        return True
    try:
        for parent in obj.InList:
            if _type(parent) == RUN:
                return True
    except Exception:
        pass
    return False


def studies(doc):
    if doc is None:
        return []
    return sorted((o for o in doc.Objects if is_study(o)), key=lambda o: o.ID)


def items(study, category=None):
    """The study's constraints and loads in the order they were made (category:
    "constraint" / "load" / None for both)."""
    if study is None:
        return []
    found = []
    for o in study.Document.Objects:
        if is_item(o) and getattr(o, "SimStudy", None) is study:
            if category is None or item_data(o).get("category") == category:
                found.append(o)
    return sorted(found, key=lambda o: o.ID)


def study_of(item):
    return getattr(item, "SimStudy", None) if is_item(item) else None


# -- studies ---------------------------------------------------------------------------------------
def _label_number(labels, stem):
    taken = set(labels)
    n = 1
    while any(
        label == "%s %d" % (stem, n) or label.startswith("%s %d " % (stem, n)) for label in taken
    ):
        n += 1
    return n


def _all_item_labels(doc, but=None):
    """Every study item's label in the design (FreeCAD keeps labels unique in a document, so
    items are numbered across all studies: "Fixed 1" in the first study, "Fixed 2" next)."""
    return [o.Label for o in doc.Objects if is_item(o) and o is not but]


def create_study(doc, kind="static_stress", label=None, study_bodies=None):
    """A new study of `kind` (only "static_stress" solves). Fusion names it "Study 1 - Static
    Stress"; `study_bodies` (default: the design's bodies, shown or hidden: design_bodies)."""
    if doc is None:
        raise SimulationError("Open a design first.")
    if not core.study_type_available(kind):
        raise SimulationError(
            "%s studies are not in SciForge yet. %s"
            % (core.study_type_title(kind), core.NOT_AVAILABLE)
        )
    obj = doc.addObject("App::FeaturePython", "SimStudy")
    StudyProxy(obj)
    bodies.mark(obj, STUDY)
    bodies.hide_from_timeline(obj)
    number = _label_number([s.Label for s in studies(doc) if s is not obj], "Study")
    obj.Label = label or "Study %d - %s" % (number, core.study_type_title(kind))
    _save(obj, STUDY_PROP, {"type": kind, "settings": core.settings(), "materials": {}})
    if study_bodies:
        obj.SimBodies = list(study_bodies)
    _clean(obj)
    return obj


def study_data(study):
    data = bodies.load_meta(study, STUDY_PROP)
    data.setdefault("type", "static_stress")
    data["settings"] = core.settings(data.get("settings"))
    data.setdefault("materials", {})
    return data


def settings(study):
    return study_data(study)["settings"]


def set_settings(study, new):
    """Change a study's settings (a partial dict is merged into the current settings)."""
    data = study_data(study)
    merged = data["settings"]
    for key, value in (new or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    data["settings"] = core.settings(merged)
    _save(study, STUDY_PROP, data)
    if "keep_results" in (new or {}):
        apply_keep_results(study)
    return data["settings"]


def delete_study(study):
    doc = study.Document
    for item in items(study):
        doc.removeObject(item.Name)
    _remove_run(study)
    _remove_run(study, "SimMeshRun")
    doc.removeObject(study.Name)


def clone_study(study, label=None):
    """Fusion's Clone Study: a copy with the same bodies, settings, materials, constraints,
    loads and mesh controls, and no results."""
    doc = study.Document
    data = study_data(study)
    copy = create_study(doc, data["type"], label, list(getattr(study, "SimBodies", []) or []))
    _save(copy, STUDY_PROP, data)
    for item in items(study):
        d = item_data(item)
        obj = doc.addObject("App::FeaturePython", "SimItem")
        ItemProxy(obj)
        bodies.mark(obj, ITEM)
        bodies.hide_from_timeline(obj)
        obj.SimStudy = copy
        obj.References = item.References
        title = core.kind_info(d["category"], d["kind"])["title"]
        obj.Label = "%s %d" % (title, _label_number(_all_item_labels(doc, obj), title))
        obj.Suppressed = bool(item.Suppressed)
        _save(obj, ITEM_PROP, d)
    _clean(copy)
    return copy


def _save(obj, prop, data):
    bodies.save_meta(obj, prop, data)
    _clean(obj)


def _clean(*objs):
    """Studies and their items have nothing to compute (their execute does nothing): a change
    SciForge makes to one leaves no recompute mark ("touched"), so the design does not ask for
    a recompute after a solve or a setting changed after it (a study changed after its solve
    was still touched when the design was saved, and came back touched). The design is still
    marked modified (Save asks), and the results' fingerprint still sees the change."""
    for obj in objs:
        try:
            obj.purgeTouched()
        except Exception:
            pass


def study_bodies(study):
    """The solid bodies the study simulates, in the design's order: the ones chosen for it
    (SimBodies), else the design's (design_bodies)."""
    doc = study.Document
    chosen = [b for b in (getattr(study, "SimBodies", None) or []) if bodies.has_solid(b)]
    if chosen:
        return sorted(chosen, key=lambda b: b.ID)
    return design_bodies(doc)


def design_bodies(doc):
    """The bodies a study of the whole design simulates (Fusion: the simulation model is the
    design's bodies): every body with a solid, shown or hidden, but not the ones a step uses
    up (a Combine without Keep Tools: they are no longer part of the design) nor the ones the
    history marker has not made yet. Never by what is shown: it went by the eyes, so turning a
    body's eye off after a solve (the RESULTS tab says to, to look inside) made the results
    out of date, and changed the bodies the next solve took."""
    if doc is None:
        return []
    for name in ("combine", "mesh", "extrude_bodies"):  # (the steps that use bodies up)
        try:
            __import__("sciforge." + name)
        except Exception:
            pass
    try:
        used = bodies.consumed(doc)
    except Exception:
        used = set()
    return [
        b
        for b in bodies.solid_bodies(doc)
        if b.Name not in used and not getattr(b, "SciForgeRolledHidden", False)
    ]


# -- constraints and loads -------------------------------------------------------------------------
def item_data(item):
    data = bodies.load_meta(item, ITEM_PROP)
    data.setdefault("category", "constraint")
    data.setdefault("kind", "fixed")
    data.setdefault("options", {})
    return data


def _picks(refs):
    """[(obj, sub)] from what FreeCAD's LinkSubList gives or from [(obj, "Face1"), (obj,
    ["Face2", "Face3"])]."""
    out = []
    for entry in refs or []:
        obj, subs = entry[0], entry[1]
        if isinstance(subs, str):
            subs = [subs]
        for sub in subs or [""]:
            out.append((obj, sub))
    return out


def _element_kind(sub):
    name = sub.split(".")[-1]
    for prefix, kind in (("Face", "faces"), ("Edge", "edges"), ("Vertex", "vertices")):
        if name.startswith(prefix):
            return kind
    return "bodies"


def _surface_of(obj, sub):
    try:
        element = bodies.global_shape(obj, copy=False).getElement(sub.split(".")[-1])
        return element.Surface.TypeId.split("::")[-1].lower().replace("geom", "")
    except Exception:
        return None


def describe_picks(refs):
    """[(element kind, surface)] of picks, as simulation_core.check wants them."""
    out = []
    for obj, sub in _picks(refs):
        kind = _element_kind(sub)
        out.append((kind, _surface_of(obj, sub) if kind == "faces" else None))
    return out


def add_item(study, category, kind, refs, opts=None, label=None):
    """A new constraint (category "constraint") or load ("load") of `kind` on `refs`."""
    info = core.kind_info(category, kind)
    if not info.get("built"):
        raise SimulationError("%s is not in SciForge yet." % info["title"])
    opts = core.options(category, kind, opts)
    problems = core.check(category, kind, opts, describe_picks(refs))
    if problems:
        raise SimulationError(" ".join(problems))
    doc = study.Document
    obj = doc.addObject("App::FeaturePython", "SimItem")
    ItemProxy(obj)
    bodies.mark(obj, ITEM)
    bodies.hide_from_timeline(obj)
    obj.SimStudy = study
    obj.References = _link_list(refs)
    number = _label_number(_all_item_labels(doc, obj), info["title"])
    obj.Label = label or "%s %d" % (info["title"], number)
    data = {"category": category, "kind": kind, "options": opts, "sigs": _signatures(refs)}
    _save(obj, ITEM_PROP, data)
    return obj


def update_item(item, refs=None, opts=None, suppressed=None):
    data = item_data(item)
    category, kind = data["category"], data["kind"]
    new_opts = core.options(category, kind, dict(data["options"], **(opts or {})))
    new_refs = refs if refs is not None else item.References
    problems = core.check(category, kind, new_opts, describe_picks(new_refs))
    if problems:
        raise SimulationError(" ".join(problems))
    if refs is not None:
        item.References = _link_list(refs)
        data["sigs"] = _signatures(refs)
    data["options"] = new_opts
    _save(item, ITEM_PROP, data)
    if suppressed is not None:
        item.Suppressed = bool(suppressed)
    _clean(item)
    return item


def delete_item(item):
    item.Document.removeObject(item.Name)


def _link_list(refs):
    grouped = {}
    order = []
    for obj, sub in _picks(refs):
        if obj.Name not in grouped:
            grouped[obj.Name] = (obj, [])
            order.append(obj.Name)
        if sub not in grouped[obj.Name][1]:
            grouped[obj.Name][1].append(sub)
    # (a whole object is the element "": FreeCAD drops an entry with no element at all)
    return [(grouped[n][0], grouped[n][1] or [""]) for n in order]


def lost_items(study):
    """Items whose picks are gone (deleted geometry, found nowhere by their shape): the
    pre-check refuses them."""
    lost = []
    for item in items(study):
        if item.Suppressed:
            continue
        resolved = resolve_picks(item)
        if not resolved or any(not names for _obj, names, _moved in resolved):
            lost.append(item)
    return lost


# -- picks that survive edits ----------------------------------------------------------------------
# FreeCAD follows a picked face through later edits by its history, and marks it lost ("?Face5")
# when it cannot (a Press Pull, a direct edit, a step changed early in the timeline). Every pick
# also remembers its shape (_signature: the kind of surface, its normal or axis, where it is,
# its size), and a pick FreeCAD lost is found again by that shape: the same face where it was
# (split in pieces: all of them), or the face it moved to.
def _vec(v):
    return [round(v.x, 9), round(v.y, 9), round(v.z, 9)]


def _signature(element):
    """What a picked face / edge / corner looks like, in design coordinates."""
    kind = element.ShapeType
    out = {"kind": kind}
    try:
        if kind == "Face":
            surface = element.Surface
            out["type"] = surface.TypeId.split("::")[-1]
            out["center"] = _vec(element.CenterOfMass)
            out["area"] = element.Area
            box = element.BoundBox
            out["box"] = [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]
            if out["type"] == "GeomPlane":
                n = element.normalAt(*_middle_uv(element))
                out["normal"] = _vec(n)
                out["offset"] = n.dot(element.CenterOfMass)
            elif out["type"] == "GeomCylinder":
                out["axis"] = _vec(surface.Axis)
                out["origin"] = _vec(surface.Center)
                out["radius"] = surface.Radius
        elif kind == "Edge":
            out["type"] = element.Curve.TypeId.split("::")[-1]
            out["center"] = _vec(element.CenterOfMass)
            out["length"] = element.Length
        elif kind == "Vertex":
            out["center"] = _vec(element.Point)
    except Exception:
        pass
    return out


_LOCAL_SHAPES = {}


def _local_shape(obj):
    """The object's shape in its own coordinates (its placement and its component's left
    out), so a pick's remembered shape does not change when the body or its component moves.
    Remembered per shape (callers only read it): the copy of a 366-face part takes 27 ms, and
    every pick asked for it (120 fixed holes: a pre-check of 8 s)."""
    own = obj.Shape
    key = None
    try:
        box = own.BoundBox
        key = (
            obj.Document.Name,
            obj.Name,
            own.hashCode(),
            tuple(
                round(v, 6) for v in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)
            ),
            tuple(round(x, 9) for x in own.Placement.toMatrix().A),
        )
        hit = _LOCAL_SHAPES.get(key)
        if hit is not None:
            return hit
    except Exception:
        key = None
    shape = own.copy(False)  # (FreeCAD's own is read-only; this copy shares geometry)
    shape.Placement = App.Placement()
    if key is not None:
        if len(_LOCAL_SHAPES) >= 8:
            _LOCAL_SHAPES.pop(next(iter(_LOCAL_SHAPES)))
        _LOCAL_SHAPES[key] = shape
    return shape


def _signatures(refs):
    """[[object name, element name, signature]] of picks, in the order of the picks (FreeCAD
    may rename a pick it lost, "?Face1" for what was Face8, but keeps their order)."""
    out = []
    shapes = {}
    for obj, sub in _picks(refs):
        name = sub.split(".")[-1]
        sig = None
        if name:
            try:
                if obj.Name not in shapes:  # (once per object)
                    shapes[obj.Name] = _local_shape(obj)
                sig = _signature(shapes[obj.Name].getElement(name))
            except Exception:
                sig = None
        out.append([obj.Name, name, sig])
    return out


def _signature_of(sigs, index, obj, name, positional=True):
    """The remembered shape of the index-th pick (by its place in the list when the list
    still matches the picks, else by its name)."""
    if isinstance(sigs, list):
        if positional and index < len(sigs) and sigs[index][0] == obj.Name:
            return sigs[index][2]
        for owner, element, sig in sigs:
            if owner == obj.Name and element == name.lstrip("?"):
                return sig
        return None
    if isinstance(sigs, dict):  # (the first form, never released)
        return sigs.get("%s:%s" % (obj.Name, name.lstrip("?")))
    return None


def _same_direction(a, b, tol=1e-6):
    return abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) > 1.0 - tol


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _boxes_touch(a, b, tol):
    return all(a[i] <= b[i + 3] + tol and b[i] <= a[i + 3] + tol for i in range(3))


def _fits(element, sig, tol):
    """Whether an element still is the picked one (FreeCAD kept the name): the same kind of
    surface turned the same way (a face that moved or grew is still the same face)."""
    now = _signature(element)
    if now.get("kind") != sig.get("kind") or now.get("type") != sig.get("type"):
        return False
    if "normal" in sig:
        n, m = now.get("normal"), sig["normal"]
        return bool(n) and sum(a * b for a, b in zip(n, m)) > 1.0 - 1e-6
    if "axis" in sig:
        return (
            _same_direction(now.get("axis", [0, 0, 0]), sig["axis"])
            and abs(now.get("radius", 0) - sig["radius"]) <= tol
        )
    return True


def _refind(shape, sig, tol):
    """Names of the elements of `shape` that are the picked one by its shape: the same face
    where it was (all its pieces when an edit split it), else the face it moved to."""
    kind = sig.get("kind")
    if kind == "Vertex":
        best = None
        for i, v in enumerate(shape.Vertexes, 1):
            d = _distance(_vec(v.Point), sig["center"])
            if best is None or d < best[0]:
                best = (d, "Vertex%d" % i)
        return [best[1]] if best and best[0] <= max(10 * tol, 1e-3) else []
    if kind == "Edge":
        best = None
        for i, e in enumerate(shape.Edges, 1):
            try:
                if e.Curve.TypeId.split("::")[-1] != sig.get("type"):
                    continue
            except Exception:
                continue
            d = _distance(_vec(e.CenterOfMass), sig["center"]) + abs(e.Length - sig["length"])
            if best is None or d < best[0]:
                best = (d, "Edge%d" % i)
        return [best[1]] if best and best[0] <= max(0.05 * sig["length"], tol) else []
    same, moved = [], []
    for i, f in enumerate(shape.Faces, 1):
        try:
            now = _signature(f)
        except Exception:
            continue
        if now.get("type") != sig.get("type"):
            continue
        name = "Face%d" % i
        if "normal" in sig:
            if not now.get("normal") or sum(a * b for a, b in zip(now["normal"], sig["normal"])) < (
                1.0 - 1e-6
            ):
                continue
            if abs(now["offset"] - sig["offset"]) <= tol and _boxes_touch(
                now["box"], sig["box"], tol
            ):
                same.append(name)
            else:
                # moved along its normal: how far its middle is from the old middle across it
                n = sig["normal"]
                d = [now["center"][k] - sig["center"][k] for k in range(3)]
                along = sum(d[k] * n[k] for k in range(3))
                across = _distance(d, [along * n[k] for k in range(3)])
                moved.append((across + abs(now["area"] - sig["area"]) ** 0.5, name))
        elif "axis" in sig:
            if not _same_direction(now.get("axis", [0, 0, 0]), sig["axis"]):
                continue
            if abs(now.get("radius", 0) - sig["radius"]) > tol:
                continue
            o = [now["origin"][k] - sig["origin"][k] for k in range(3)]
            a = sig["axis"]
            along = sum(o[k] * a[k] for k in range(3))
            off_axis = _distance(o, [along * a[k] for k in range(3)])
            if off_axis <= tol and _boxes_touch(now["box"], sig["box"], tol):
                same.append(name)
            else:
                moved.append((off_axis + _distance(now["center"], sig["center"]), name))
        else:
            if abs(now["area"] - sig["area"]) <= 0.2 * sig["area"]:
                moved.append((_distance(now["center"], sig["center"]), name))
    if same:
        return same
    if moved:
        moved.sort()
        size = max(sig["box"][3] - sig["box"][0], sig["box"][4] - sig["box"][1])
        size = max(size, sig["box"][5] - sig["box"][2], 1.0)
        if moved[0][0] <= 0.5 * size:
            return [moved[0][1]]
    return []


def resolve_picks(item):
    """[(object, [element names], moved)] of an item's picks as the design is now: FreeCAD's
    own name when it still fits, else the elements found again by the pick's shape (moved =
    True), else [] (lost). A whole-body pick gives [""]."""
    data = item_data(item)
    sigs = data.get("sigs")
    picks = _picks(item.References)
    # (the remembered shapes follow the picks' order, unless the picks were changed without
    # update_item: then they are matched by name)
    positional = isinstance(sigs, list) and len(sigs) == len(picks)
    out = []
    sizes = {}
    for index, (obj, sub) in enumerate(picks):
        if not bodies.alive(obj):
            out.append((obj, [], False))
            continue
        if not sub:
            out.append((obj, [""] if bodies.has_solid(obj) else [], False))
            continue
        name = sub.split(".")[-1]
        sig = _signature_of(sigs, index, obj, name, positional)
        try:
            if obj.Name not in sizes:  # (once per object)
                local = _local_shape(obj)
                sizes[obj.Name] = (local, max(1e-6 * _shape_size(local), 1e-4))
            shape, tol = sizes[obj.Name]
        except Exception:
            out.append((obj, [], False))
            continue
        element = None
        if not name.startswith("?"):
            try:
                element = shape.getElement(name)
                if element is None or element.isNull():
                    element = None
            except Exception:
                element = None
        if element is not None and (sig is None or _fits(element, sig, tol)):
            out.append((obj, [name], False))
            continue
        if sig is None:
            out.append((obj, [], False))
            continue
        found = _refind(shape, sig, tol)
        out.append((obj, found, bool(found)))
    return out


def refresh_signatures(study):
    """Remember every resolved pick's shape as it is now (so the next edit is followed from
    here); items whose picks are lost are left as they are."""
    for item in items(study):
        resolved = resolve_picks(item)
        if not resolved or any(not names for _obj, names, _moved in resolved):
            continue
        data = item_data(item)
        fresh = _signatures(_picks(item.References))
        if fresh != data.get("sigs"):
            data["sigs"] = fresh
            _save(item, ITEM_PROP, data)


def _shape_size(shape):
    box = shape.BoundBox
    return max(box.XLength, box.YLength, box.ZLength, 1.0)


def repair_picks(study):
    """Point every item whose picks FreeCAD lost (or that moved) at the faces found again by
    their shape, and remember their shape there. Returns the labels of the items changed.
    (The Job calls it before a solve; the workspace may call it after an edit.)"""
    changed = []
    for item in items(study):
        resolved = resolve_picks(item)
        if not any(moved for _obj, _names, moved in resolved):
            continue
        if any(not names for _obj, names, _moved in resolved):
            continue  # (lost: the pre-check says so, nothing is changed)
        refs = []
        for obj, names, _moved in resolved:
            refs += [(obj, n) for n in names]
        data = item_data(item)
        item.References = _link_list(refs)
        data["sigs"] = _signatures(refs)
        _save(item, ITEM_PROP, data)
        changed.append(item.Label)
    if changed:
        log(
            "simulation: found again what %s %s on"
            % (", ".join(changed), "is" if len(changed) == 1 else "are")
        )
    return changed


# -- materials -------------------------------------------------------------------------------------
def _number(mat, prop, unit):
    try:
        if not mat.hasPhysicalProperty(prop):
            return None
        value = mat.getPhysicalValue(prop)
        if value is None:
            return None
        if unit is None:
            return float(value)
        return float(value.getValueAs(unit))
    except Exception:
        return None


def card(mat):
    """(name, {youngs_mpa, poisson, density (kg/m3), yield_mpa, ultimate_mpa}) of a FreeCAD
    material, with simulation_core.FALLBACK filling what the card lacks."""
    name = getattr(mat, "Name", "") or "Material"
    props = {
        "youngs_mpa": _number(mat, "YoungsModulus", "MPa"),
        "poisson": _number(mat, "PoissonRatio", None),
        "density": _number(mat, "Density", "kg/m^3"),
        "yield_mpa": _number(mat, "YieldStrength", "MPa"),
        "ultimate_mpa": _number(mat, "UltimateTensileStrength", "MPa"),
    }
    for key, value in core.FALLBACK.get(name, {}).items():
        current = props.get(key)
        if current is None or current != current:  # missing or NaN
            props[key] = value
            props.setdefault("filled", []).append(key)
    return name, props


def _material_object(body):
    from . import material

    try:
        key = material.key_of(body)
    except Exception:
        key = None
    if not key:
        key = material.default_key()
    row = material.entry(key) or material.entry(material.DEFAULT_KEY)
    try:
        uuid = body.ShapeMaterial.UUID
        if uuid and uuid != material.FREECAD_DEFAULT_UUID:
            return body.ShapeMaterial
    except Exception:
        pass
    return material.material_of(row)


def model_material(body):
    """The body's own physical material as a card (Fusion's "Same as Model")."""
    return card(_material_object(body))


def study_material(study, body):
    """(name, props, "model" | "study") of the material the study uses for `body`."""
    from . import material

    key = study_data(study)["materials"].get(body.Name)
    if key:
        row = material.entry(key)
        if row is not None:
            name, props = card(material.material_of(row))
            return name, props, "study"
    name, props = model_material(body)
    return name, props, "model"


def set_study_material(study, body, key):
    """Use material `key` (material.LIBRARY / a user material) for `body` in this study only;
    None goes back to the body's own material (Fusion: Same as Model)."""
    from . import material

    data = study_data(study)
    if key is None:
        data["materials"].pop(body.Name, None)
    else:
        if material.entry(key) is None:
            raise SimulationError("Unknown material %r." % key)
        data["materials"][body.Name] = key
    _save(study, STUDY_PROP, data)


# -- contacts --------------------------------------------------------------------------------------
# Contacts and overlaps of the study's bodies, worked out once per geometry: the pre-check
# runs after every SETUP command, and for 20 stacked plates with holes they took 4 s and 2 s.
_GEOMETRY_CACHE = {}


def _geometry_key(found, tol):
    """What the contacts depend on: every body's shape (FreeCAD makes a new one at every
    change), its size and place, and its component's place; None when it cannot be told."""
    rows = []
    try:
        for b in found:
            shape = b.Shape
            parent = b.getParentGeoFeatureGroup()
            place = parent.getGlobalPlacement() if parent is not None else App.Placement()
            box = shape.BoundBox
            rows.append(
                (
                    b.Name,
                    shape.hashCode(),
                    # (cheap checks besides the hash, which a new shape at a freed one's
                    # memory could repeat)
                    (len(shape.Faces), len(shape.Edges), len(shape.Vertexes)),
                    tuple(
                        round(v, 6)
                        for v in (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)
                    ),
                    tuple(round(x, 9) for x in shape.Placement.toMatrix().A),
                    tuple(round(x, 9) for x in place.toMatrix().A),
                )
            )
    except Exception:
        return None
    return (tuple(rows), round(float(tol), 9))


def _touch_kind(cut, sa, sb):
    """How two touching bodies touch: None on a face, "edge" along a line only, "corner" at a
    point only. From the section of their shapes (its edges close around a shared area), and
    when that does not tell (two coincident round faces, a pin in its hole, give only lines),
    from their faces: a pair of faces with an area in common."""
    import Part

    kind = "corner" if not cut.Edges else "edge"
    if cut.Edges:
        try:
            for group in Part.sortEdges(cut.Edges):
                if Part.Wire(group).isClosed():
                    return None
        except Exception:
            return None  # (when in doubt: a face, as before)
    try:
        for fa in sa.Faces:
            box = fa.BoundBox
            box.enlarge(1e-6)
            for fb in sb.Faces:
                if not box.intersect(fb.BoundBox):
                    continue
                common = fa.common(fb)
                if common.Area > 1e-6 * min(fa.Area, fb.Area):
                    return None
    except Exception:
        return None
    return kind


def _contact_data(study):
    """([(body, body, "bonded")] touching or closer than the contact tolerance, [(body, body,
    volume mm3)] overlapping, [(body, body, "edge" / "corner")] touching only along an edge or
    at a corner) of the study's bodies, remembered for the same geometry (at most 16 answers
    kept). Two bodies whose boundaries cross (OpenCASCADE's section: a third of the time of a
    distance) touch; the others are measured; only touching ones can overlap."""
    found = study_bodies(study)
    tol = float(settings(study)["contact_tolerance"])
    key = _geometry_key(found, tol)
    full = None if key is None else ("contacts", study.Document.Name, key)
    by_name = {b.Name: b for b in found}
    hit = _GEOMETRY_CACHE.get(full) if full is not None else None
    if hit is not None:
        return tuple([(by_name[a], by_name[b], v) for a, b, v in rows] for rows in hit)
    shapes = [(b, bodies.global_shape(b, copy=False)) for b in found]
    volumes = {}
    touching, overlapping, slight = [], [], []
    for i, (a, sa) in enumerate(shapes):
        box = sa.BoundBox
        near = sa.BoundBox
        near.enlarge(tol)
        for b, sb in shapes[i + 1 :]:
            if not near.intersect(sb.BoundBox):
                continue
            gap = None
            kind = None
            try:
                cut = sa.section(sb)
                if cut.Edges or cut.Vertexes:
                    gap = 0.0
                    kind = _touch_kind(cut, sa, sb)
            except Exception:
                gap = None
            if gap is None:
                try:
                    gap = sa.distToShape(sb)[0]
                except Exception:
                    continue
            if gap <= tol + 1e-9:
                touching.append((a, b, "bonded"))
                if kind is not None:
                    slight.append((a, b, kind))
            if gap <= 1e-9 and box.intersect(sb.BoundBox):
                try:
                    volume = sa.common(sb).Volume
                    for body, shape in ((a, sa), (b, sb)):
                        if body.Name not in volumes:
                            volumes[body.Name] = shape.Volume
                except Exception:
                    continue
                if volume > 1e-6 * max(1.0, min(volumes[a.Name], volumes[b.Name])):
                    overlapping.append((a, b, volume))
    if full is not None:
        if len(_GEOMETRY_CACHE) >= 16:
            _GEOMETRY_CACHE.pop(next(iter(_GEOMETRY_CACHE)))
        _GEOMETRY_CACHE[full] = tuple(
            [(x.Name, y.Name, v) for x, y, v in rows] for rows in (touching, overlapping, slight)
        )
    return touching, overlapping, slight


def contacts(study):
    """Fusion's automatic contacts: [(body, body, "bonded")] of the study's bodies that touch
    or are closer than the contact tolerance (they are glued when the study solves)."""
    return _contact_data(study)[0]


def overlaps(study):
    """[(body, body, volume mm3)] of the study's bodies that overlap."""
    return _contact_data(study)[1]


def slight_contacts(study):
    """[(body, body, "edge" / "corner")] of the study's bodies that touch only along an edge or
    at a corner: glued only there, like a hinge (Fusion's contacts are between faces)."""
    return _contact_data(study)[2]


def loose_bodies(study, touching=None):
    """The study's bodies that no constraint holds and that touch (through other bodies) no
    held body: they would fly away."""
    found = study_bodies(study)
    if touching is None:
        touching = contacts(study)
    held = set()
    for item in items(study, "constraint"):
        if item.Suppressed:
            continue
        for obj, _sub in _picks(item.References):
            body = obj if obj in found else bodies.body_of(obj)
            if body is not None:
                held.add(body.Name)
    links = {}
    for a, b, _kind in touching:
        links.setdefault(a.Name, set()).add(b.Name)
        links.setdefault(b.Name, set()).add(a.Name)
    reached = set(held)
    todo = list(held)
    while todo:
        name = todo.pop()
        for other in links.get(name, ()):
            if other not in reached:
                reached.add(other)
                todo.append(other)
    return [b for b in found if b.Name not in reached]


def _twice(study):
    """[(item, item)] of constraints that hold the same face (research 9.6, yellow)."""
    seen = {}
    out = []
    for item in items(study, "constraint"):
        if item.Suppressed:
            continue
        for obj, sub in _picks(item.References):
            if not sub.split(".")[-1].startswith("Face"):
                continue
            key = (obj.Name, sub.split(".")[-1])
            first = seen.get(key)
            if first is None:
                seen[key] = item
            elif first is not item and (first.Label, item.Label) not in out:
                out.append((first.Label, item.Label))
    return out


# -- held enough? -------------------------------------------------------------------------------
def _sample_points(element):
    """Points spread over a picked face, edge or corner (design coordinates)."""
    kind = element.ShapeType
    if kind == "Vertex":
        return [element.Point]
    if kind == "Edge":
        a, b = element.FirstParameter, element.LastParameter
        return [element.valueAt(a + (b - a) * f) for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    pts = [v.Point for v in element.Vertexes]
    # points along the face's edges: the grid below can miss a narrow face entirely (a tube's
    # end ring had only its two seam corners, both on one line, and "could still turn")
    for edge in element.Edges:
        try:
            a, b = edge.FirstParameter, edge.LastParameter
            pts += [edge.valueAt(a + (b - a) * f) for f in (0.125, 0.375, 0.625, 0.875)]
        except Exception:
            continue
    try:
        u0, u1, v0, v1 = element.ParameterRange
        for i in range(5):
            for j in range(5):
                u = u0 + (u1 - u0) * (0.1 + 0.2 * i)
                v = v0 + (v1 - v0) * (0.1 + 0.2 * j)
                if element.isPartOfDomain(u, v):
                    pts.append(element.valueAt(u, v))
    except Exception:
        pts.append(element.CenterOfMass)
    return pts


def _held_rows(item):
    """[(body, point, direction)]: where an item's constraint stops the model moving and
    along which directions (sampled over its picks)."""
    data = item_data(item)
    kind = data["kind"]
    opts = core.options("constraint", kind, data["options"])
    axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    out = []
    for obj, names, _moved in resolve_picks(item):
        body = obj if bodies.is_body(obj) else (bodies.body_of(obj) or obj)
        try:
            shape = bodies.global_shape(obj, copy=False)
        except Exception:
            continue
        for name in names:
            if not name:
                continue
            try:
                element = shape.getElement(name)
            except Exception:
                continue
            frame = None
            if kind == "pin" and element.ShapeType == "Face":
                try:
                    frame = _cylinder_frame(element)
                except Exception:
                    frame = None
            for p in _sample_points(element):
                point = (p.x, p.y, p.z)
                if kind == "fixed":
                    dirs = [axes[i] for i, a in enumerate("xyz") if opts.get(a)]
                elif kind == "displacement":
                    dirs = [axes[i] for i, a in enumerate("xyz") if opts.get(a) is not None]
                elif kind == "pin" and frame is not None:
                    centre, axis, _sign = frame
                    radial = _radial(point, centre, axis)
                    dirs = []
                    if radial is not None:
                        if opts.get("radial"):
                            dirs.append(tuple(radial))
                        if opts.get("tangential"):
                            dirs.append(tuple(core._cross(axis, radial)))
                    if opts.get("axial"):
                        dirs.append(tuple(axis))
                elif kind == "frictionless" and element.ShapeType == "Face":
                    dirs = [_face_normal_at(element, point)]
                else:
                    dirs = []
                out += [(body, point, d) for d in dirs]
    return out


def _pieces(study, touching=None):
    """The study's bodies grouped by what touches what (glued pieces move together)."""
    found = study_bodies(study)
    if touching is None:
        touching = contacts(study) if len(found) > 1 else []
    parent = {b.Name: b.Name for b in found}

    def root(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for a, b, _kind in touching:
        if a.Name in parent and b.Name in parent:
            parent[root(b.Name)] = root(a.Name)
    groups = {}
    for b in found:
        groups.setdefault(root(b.Name), []).append(b)
    return list(groups.values())


def not_held(study, touching=None):
    """[(bodies, [free movement in words])] of the pieces of the study that its constraints
    hold (at least one constraint on them) but not completely: they could still slide or turn
    as a whole, and the solve would fail or give nonsense (Fusion's rigid body motion)."""
    rows = []
    for item in items(study, "constraint"):
        if not item.Suppressed:
            rows += _held_rows(item)
    out = []
    for piece in _pieces(study, touching):
        names = set(b.Name for b in piece)
        mine = [(p, d) for body, p, d in rows if body.Name in names]
        if not mine:
            continue  # (held by nothing: loose_bodies / Remove rigid body modes)
        box = None
        for b in piece:
            bb = bodies.global_shape(b, copy=False).BoundBox
            if box is None:
                box = bb
            else:
                box.add(bb)
        centre = (box.Center.x, box.Center.y, box.Center.z)
        free = core.free_modes(mine, centre, max(box.DiagonalLength, 1.0))
        if free:
            out.append((piece, [core.describe_free_mode(m) for m in free]))
    return out


# -- pre-check -------------------------------------------------------------------------------------
def precheck(study):
    """[(level, sentence)] of simulation_core.precheck for this study as it is now."""
    data = study_data(study)
    found = study_bodies(study)
    opts = data["settings"]
    summary = {
        "bodies": [b.Label for b in found],
        "materials": {},
        "constraints": [],
        "loads": [],
        "gravity": bool(opts["gravity"]["on"]),
        "safety_basis": opts["safety_basis"],
        "lost": [i.Label for i in lost_items(study)],
        "remove_rigid": bool(opts["remove_rigid"]),
        "twice": _twice(study),
        "order": opts["mesh"]["order"],
    }
    for body in found:
        name, props, _source = study_material(study, body)
        summary["materials"][body.Label] = (name, props)
    for item in items(study):
        d = item_data(item)
        try:
            info = core.kind_info(d["category"], d["kind"])
        except SimulationError:
            summary.setdefault("unbuilt", []).append(item.Label)
            continue
        if d["category"] in ("constraint", "load"):
            row = (d["kind"], len(_picks(item.References)), bool(item.Suppressed))
            summary["constraints" if d["category"] == "constraint" else "loads"].append(row)
        if not item.Suppressed and not info.get("built"):
            summary.setdefault("unbuilt", []).append(item.Label)
    slight = []
    if len(found) > 1:
        try:
            touching = contacts(study)
            summary["overlaps"] = [(a.Label, b.Label, v) for a, b, v in overlaps(study)]
            slight = slight_contacts(study)
        except Exception as exc:
            warn("simulation pre-check: %s" % exc)
            touching = []
    else:
        touching = []
    if found and any(not c[2] for c in summary["constraints"]):
        summary["loose"] = [b.Label for b in loose_bodies(study, touching)]
    checks = core.precheck(summary)
    names = set(b.Name for b in found)
    for item in items(study):
        if item.Suppressed:
            continue
        outside = []
        for obj, _sub in _picks(item.References):
            body = obj if bodies.is_body(obj) else bodies.body_of(obj)
            if body is not None and bodies.alive(body) and body.Name not in names:
                if body.Label not in outside:
                    outside.append(body.Label)
        if outside:
            checks.append(
                (
                    "error",
                    "%s is on %s, which this study leaves out: include %s in the study, or "
                    "suppress or delete %s."
                    % (
                        item.Label,
                        " and ".join(outside),
                        "it" if len(outside) == 1 else "them",
                        item.Label,
                    ),
                )
            )
    try:
        for piece, free in not_held(study, touching if len(found) > 1 else []):
            checks.append(
                (
                    "error",
                    "%s is not held enough: it could still %s. Add a constraint that stops "
                    "it (a Fixed face is the simplest)."
                    % (" and ".join(b.Label for b in piece), " or ".join(free)),
                )
            )
    except Exception as exc:
        warn("simulation pre-check (held enough): %s" % exc)
    for a, b, kind in slight:
        checks.append(
            (
                "warning",
                "%s and %s touch only %s: they are glued only there, like a hinge, so one can "
                "still turn about it (the solve fails, or gives nonsense). Let them share a face, "
                "or move them apart and hold each one."
                % (a.Label, b.Label, "along an edge" if kind == "edge" else "at a corner"),
            )
        )
    for label in summary.get("unbuilt", []):
        checks.append(("error", "%s is not in SciForge yet: suppress or delete it." % label))
    try:
        from . import material

        for body in found:
            key = data["materials"].get(body.Name)
            if key and material.entry(key) is None:
                name = summary["materials"][body.Label][0]
                checks.append(
                    (
                        "warning",
                        "%s's study material %r is no longer in the materials: the study uses "
                        "%s's own material (%s). Choose one in Study Materials."
                        % (body.Label, key, body.Label, name),
                    )
                )
    except Exception as exc:
        warn("simulation pre-check (materials): %s" % exc)
    return checks


# -- the simulation model --------------------------------------------------------------------------
def _study_solids(study):
    """[(body, solid in design coordinates)] of every body of the study."""
    out = []
    for body in study_bodies(study):
        shape = bodies.global_shape(body)
        for solid in shape.Solids:
            out.append((body, solid))
    return out


def build_model(study):
    """(model shape, [body of each model solid]): the study's solids in design coordinates.
    Several solids are split where they touch, or come closer than the study's contact
    tolerance (FreeCAD's general fuse with that fuzzy value), so the mesh is shared there and
    they are glued (Fusion's automatic bonded contacts)."""
    import Part

    pieces = _study_solids(study)
    if not pieces:
        raise SimulationError("The study has no solid body to simulate.")
    if len(pieces) == 1:
        return Part.makeCompound([pieces[0][1]]), [pieces[0][0]]
    tol = float(settings(study)["contact_tolerance"])
    first, rest = pieces[0][1], [p[1] for p in pieces[1:]]
    try:
        fused, history = first.generalFuse(rest, tol)
    except Exception as exc:
        raise SimulationError("The bodies could not be joined for the mesh: %s" % exc)
    solids = list(fused.Solids)
    owners = []
    for solid in solids:
        # the general fuse says which body each piece came from (where two bodies overlap,
        # the first); a piece's centre of mass is no guide: a plate with a hole in its middle
        # has it in the hole, nearer the next plate
        owner = None
        for (body, _piece), made in zip(pieces, history or []):
            if any(solid.isSame(m) for m in made):
                owner = body
                break
        if owner is None:
            owner = _owner_by_geometry(solid, pieces)
        owners.append(owner)
    return Part.makeCompound(solids), owners


def _inside_point(solid):
    """A point inside a solid: its centre of mass when that is inside, else a point just
    under one of its faces."""
    centre = solid.CenterOfMass
    try:
        if solid.isInside(centre, 1e-9, False):
            return centre
        size = max(solid.BoundBox.DiagonalLength, 1e-6)
        for face in solid.Faces:
            u0, u1, v0, v1 = face.ParameterRange
            for fu, fv in ((0.5, 0.5), (0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)):
                u, v = u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv
                if not face.isPartOfDomain(u, v):
                    continue
                p, n = face.valueAt(u, v), face.normalAt(u, v)
                for depth in (1e-4, 1e-3, 1e-2):
                    q = p - n * (depth * size)
                    if solid.isInside(q, 1e-9, False):
                        return q
    except Exception:
        pass
    return centre


def _owner_by_geometry(solid, pieces):
    """The body a model solid lies in (when the general fuse did not say): the first whose
    solid holds a point inside it, else the nearest."""
    import Part

    point = _inside_point(solid)
    for body, piece in pieces:
        try:
            if piece.isInside(point, 1e-6, True):
                return body
        except Exception:
            continue
    return min(pieces, key=lambda p: p[1].distToShape(Part.Vertex(point))[0])[0]


def _model_element(model, sub):
    """A sub-element of the model shape by name, solids too ("Solid2")."""
    if sub.startswith("Solid"):
        return model.Solids[int(sub[5:]) - 1]
    return model.getElement(sub)


def _probe_points(face):
    """A few points on a face: points at chosen spots of its parameter range that lie on the
    face (not in a hole of it), else points along its edges (an L-shaped or a ring face can
    have every chosen spot, and its centre of mass, off the face)."""
    pts = []
    try:
        u0, u1, v0, v1 = face.ParameterRange
        spots = ((0.5, 0.5), (0.31, 0.43), (0.69, 0.57), (0.43, 0.69), (0.57, 0.31))
        spots += tuple((0.1 + 0.2 * i, 0.1 + 0.2 * j) for i in range(5) for j in range(5))
        for fu, fv in spots:
            u, v = u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv
            if face.isPartOfDomain(u, v):
                pts.append(face.valueAt(u, v))
            if len(pts) >= 3:
                break
    except Exception:
        pass
    if len(pts) < 3:
        for edge in face.Edges:
            try:
                pts.append(edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0))
            except Exception:
                continue
            if len(pts) >= 3:
                break
    if not pts:
        pts.append(face.CenterOfMass)
    return pts


def _model_index(model):
    """The model's faces and edges with their boxes (made once for all the picks of a solve:
    120 picked holes on a 366-face part asked for every face's box 120 times, 3.4 s)."""
    faces, edges = list(model.Faces), list(model.Edges)
    return {
        "faces": faces,
        "face_boxes": [f.BoundBox for f in faces],
        "edges": edges,
        "edge_boxes": [e.BoundBox for e in edges],
        "vertexes": list(model.Vertexes),
    }


def map_picks(item, model, owners=None, index=None):
    """The model's sub-elements ("Face12", "Edge3", "Vertex5", "Solid2") that lie on the
    item's picks (a whole-body pick: the model solids that body owns). index: _model_index of
    the model, when several items are mapped onto it."""
    picked = []
    for obj, found, _moved in resolve_picks(item):
        picked += [(obj, n) for n in found]
    return _map_onto(picked, model, owners, index)


def map_pick_groups(item, model, owners=None, index=None):
    """[[the model's sub-elements of the 1st pick], [... of the 2nd], ...]: map_picks pick by
    pick. Force Per Entity and Moment Per Entity give each pick (Fusion's entity) the whole
    load, and one picked face can be several faces of the model: the bodies are split where
    another body touches them (a block glued on a plate splits the plate's top face), or an
    edit split the face. Giving every model face the whole load doubled it."""
    if index is None:
        index = _model_index(model)
    return [
        _map_onto([(obj, n) for n in found], model, owners, index)
        for obj, found, _moved in resolve_picks(item)
    ]


def _map_onto(picked, model, owners=None, index=None):
    """map_picks for [(object, element name)] of resolved picks."""
    import Part

    if index is None:
        index = _model_index(model)
    names = []
    shapes = {}
    for obj, sub in picked:
        if not sub:
            body = obj if bodies.is_body(obj) else bodies.body_of(obj)
            for i, owner in enumerate(owners or [], 1):
                if owner is obj or owner is body:
                    names.append("Solid%d" % i)
            continue
        try:
            if obj.Name not in shapes:  # (once per object: a moved body's shape is a copy)
                shapes[obj.Name] = bodies.global_shape(obj, copy=False)
            element = shapes[obj.Name].getElement(sub.split(".")[-1])
        except Exception:
            continue
        if element is None or element.isNull():
            continue
        kind = _element_kind(sub)
        box = element.BoundBox
        box.enlarge(GEOMETRY_TOL * 10)
        if kind == "faces":
            for i, (face, face_box) in enumerate(zip(index["faces"], index["face_boxes"]), 1):
                if not box.intersect(face_box):
                    continue
                ok = True
                for p in _probe_points(face):
                    if element.distToShape(Part.Vertex(p))[0] > GEOMETRY_TOL:
                        ok = False
                        break
                if ok:
                    names.append("Face%d" % i)
        elif kind == "edges":
            for i, (edge, edge_box) in enumerate(zip(index["edges"], index["edge_boxes"]), 1):
                if not box.intersect(edge_box):
                    continue
                mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
                ends = [v.Point for v in edge.Vertexes]
                if all(
                    element.distToShape(Part.Vertex(p))[0] <= GEOMETRY_TOL for p in [mid] + ends
                ):
                    names.append("Edge%d" % i)
        elif kind == "vertices":
            for i, vertex in enumerate(index["vertexes"], 1):
                if (vertex.Point - element.Point).Length <= GEOMETRY_TOL:
                    names.append("Vertex%d" % i)
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


# -- the run (FreeCAD's FEM objects) ---------------------------------------------------------------
def run_of(study, link="SimRun"):
    """The study's run with its results (link "SimRun"), or its Generate Mesh run
    ("SimMeshRun"); None when there is none."""
    run = getattr(study, link, None)
    return run if bodies.alive(run) else None


def _remove_objects(doc, objs):
    for obj in objs:
        try:
            if bodies.alive(obj) and doc.getObject(obj.Name) is not None:
                doc.removeObject(obj.Name)
        except Exception:
            pass


def _run_members(run):
    """Everything a run holds: its members, theirs (a results pipeline's filters) and the
    result meshes its results link to (FreeCAD's result import does not put those in the
    analysis)."""
    found, todo = [], [run]
    while todo:
        obj = todo.pop()
        if not bodies.alive(obj) or obj in found:
            continue
        found.append(obj)
        todo += list(getattr(obj, "Group", []) or [])
        mesh = getattr(obj, "Mesh", None) if obj.isDerivedFrom("Fem::FemResultObject") else None
        if mesh is not None:
            todo.append(mesh)
    return found


def _remove_run(study, link="SimRun"):
    run = run_of(study, link)
    if run is None:
        return
    setattr(study, link, None)
    _remove_objects(study.Document, list(reversed(_run_members(run))))


# (document name, run name) of the runs a job is still making: not linked to their study yet
_LIVE_RUNS = set()


def _orphans(doc):
    """The objects of solves that no study links and no job is still making: a design saved
    while a solve ran keeps that solve's half-made run (its mesh too), which nothing else would
    ever remove."""
    kept = set()
    for study in studies(doc):
        for link in ("SimRun", "SimMeshRun"):
            run = run_of(study, link)
            if run is not None:
                kept.update(o.Name for o in _run_members(run))
    for doc_name, name in list(_LIVE_RUNS):
        run = doc.getObject(name) if doc_name == doc.Name else None
        if run is not None:
            kept.update(o.Name for o in _run_members(run))
    found = [o for o in doc.Objects if _type(o) in (RUN, MODEL, HELPER) and o.Name not in kept]
    # (a run's members with it)
    out = []
    for obj in found:
        for member in _run_members(obj) if _type(obj) == RUN else [obj]:
            if member.Name not in kept and member not in out:
                out.append(member)
    return out


def _hide(obj):
    try:
        obj.Visibility = False
        if App.GuiUp and obj.ViewObject is not None:
            obj.ViewObject.Visibility = False
    except Exception:
        pass


def _close_open_transaction(doc):
    """A solve never lands in the person's undo history: an undo step left open by whoever
    started the solve (a command's automatic one) is closed first, keeping what is in it, so
    what the solve makes is recorded nowhere."""
    try:
        if App.getActiveTransaction():
            App.closeActiveTransaction(False)
    except Exception:
        pass
    try:
        if getattr(doc, "HasPendingTransaction", False):
            doc.commitTransaction()
    except Exception:
        pass


def _make_run(study, model_shape, owners, mesh_only=False, straight=False):
    """A fresh hidden FEM analysis for `study` (not linked to it yet: the Job does that once
    it succeeds) with the model, the Gmsh mesh object and, unless `mesh_only`, the solver,
    materials, pressures and gravity. Returns (analysis, model feature, mesh object, {item
    name: model sub-elements})."""
    import ObjectsFem

    doc = study.Document
    data = study_data(study)
    opts = data["settings"]
    analysis = ObjectsFem.makeAnalysis(doc, "SimRun")
    bodies.mark(analysis, RUN)
    bodies.hide_from_timeline(analysis)
    analysis.Label = "%s %s" % (study.Label, "mesh" if mesh_only else "run")
    try:
        model = doc.addObject("Part::Feature", "SimModel")
        bodies.mark(model, MODEL)
        bodies.hide_from_timeline(model)
        model.Shape = model_shape
        _hide(model)
        analysis.addObject(model)

        subs = {}
        index = None
        for item in items(study, "mesh" if mesh_only else None):
            if item.Suppressed:
                continue
            if index is None:
                index = _model_index(model_shape)
            found = map_picks(item, model_shape, owners, index)
            if not found:
                raise SimulationError(
                    "%s lost what it was on: edit it and pick again." % item.Label
                )
            subs[item.Name] = found

        if not mesh_only:
            solver = ObjectsFem.makeSolverCalculiX(doc, "SimSolver")
            solver.AnalysisType = "static"
            if "GeometricalNonlinearity" in solver.PropertiesList:
                solver.GeometricalNonlinearity = "linear"
            analysis.addObject(solver)
            _add_materials(doc, study, analysis, model, owners)

        mesh = ObjectsFem.makeMeshGmsh(doc, "SimMesh")
        mesh.Shape = model
        size, smallest = _mesh_sizes(study, model_shape, owners)
        mesh.CharacteristicLengthMax = "%r mm" % size
        mesh.CharacteristicLengthMin = "%r mm" % smallest
        mesh.ElementOrder = "2nd" if opts["mesh"]["order"] == "parabolic" else "1st"
        if "SecondOrderLinear" in mesh.PropertiesList:
            mesh.SecondOrderLinear = not opts["mesh"]["curved"]
        if "MeshSizeFromCurvature" in mesh.PropertiesList:
            turn = max(float(opts["mesh"]["max_turn"]), 5.0)
            mesh.MeshSizeFromCurvature = int(round(360.0 / turn))
        if "CoherenceMesh" in mesh.PropertiesList:
            # Gmsh's "Coherence Mesh" merges nodes closer than a millionth of the model's size:
            # the two diagonals' middles of a flat sliver element became one node and CalculiX
            # refused the element (a 3 mm plate at 2 %). The model's bodies share their faces
            # (the general fuse), so the mesh needs no merging to be glued.
            mesh.CoherenceMesh = False
        if straight and "SecondOrderLinear" in mesh.PropertiesList:
            mesh.SecondOrderLinear = True
        # (curved elements that turn inside out at a tight curve are made straight-sided
        # before the solve, _straighten_input: Gmsh's HighOrderOptimize took minutes on a big
        # part)
        _hide(mesh)
        analysis.addObject(mesh)

        if not mesh_only:
            for item in items(study, "load"):
                if item.Suppressed:
                    continue
                for fem in _fem_objects(doc, item, model, subs[item.Name]):
                    analysis.addObject(fem)
            if opts["gravity"]["on"]:
                gravity = ObjectsFem.makeConstraintSelfWeight(doc, "SimGravity")
                gravity.GravityAcceleration = "%r mm/s^2" % float(opts["gravity"]["g"])
                gravity.GravityDirection = App.Vector(
                    *core.unit_vector(opts["gravity"]["direction"])
                )
                analysis.addObject(gravity)
        for obj in analysis.Group:
            bodies.hide_from_timeline(obj)
            _hide(obj)
    except Exception:
        _remove_objects(doc, list(analysis.Group) + [analysis])
        raise
    return analysis, model, mesh, subs


def _add_materials(doc, study, analysis, model, owners):
    """One FreeCAD material per distinct study material, on the model's solids it is for."""
    import ObjectsFem

    groups = {}
    for index, body in enumerate(owners, 1):
        name, props, _source = study_material(study, body)
        problems = core.material_problems(name, props)
        if problems:
            raise SimulationError("%s: %s" % (body.Label, " ".join(problems)))
        key = json.dumps(
            [name, props.get("youngs_mpa"), props.get("poisson"), props.get("density")]
        )
        groups.setdefault(key, (name, props, []))[2].append("Solid%d" % index)
    for n, (name, props, solid_names) in enumerate(groups.values(), 1):
        mat = ObjectsFem.makeMaterialSolid(doc, "SimMaterial%d" % n)
        card_data = dict(mat.Material)
        density = props.get("density")
        card_data.update(
            {
                "Name": name,
                "YoungsModulus": "%r MPa" % props["youngs_mpa"],
                "PoissonRatio": "%r" % props["poisson"],
                # (without gravity the density is not used: the pre-check refuses gravity on
                # a material without one)
                "Density": "%r kg/m^3" % (density if density and density > 0 else 1000.0),
            }
        )
        mat.Material = card_data
        if len(groups) > 1:
            mat.References = [(model, solid_names)]
        analysis.addObject(mat)


def _bbox(shape):
    b = shape.BoundBox
    return (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)


def _mesh_sizes(study, model_shape, owners):
    """(largest element size, smallest element size) the mesher is given (mm): the study's
    average size (each body's own with Scale Mesh Size Per Part), the smallest from the
    minimum % and the local mesh controls."""
    opts = settings(study)["mesh"]
    sizes = [_global_size(study, model_shape)]
    if opts["scale_per_part"]:
        sizes = list(_part_sizes(study, model_shape, owners).values()) or sizes
    largest = max(sizes)
    smallest = min(sizes) * opts["min_pct"] / 100.0
    for item in items(study, "mesh"):
        if item.Suppressed:
            continue
        size = float(core.options("mesh", "local", item_data(item)["options"])["size"])
        smallest = min(smallest, size * opts["min_pct"] / 100.0)
    return largest, max(smallest, 0.01)


def _global_size(study, model_shape):
    opts = settings(study)["mesh"]
    return core.element_size(_bbox(model_shape), opts["size_pct"], opts["size_mm"])


def _part_sizes(study, model_shape, owners):
    """{model solid index: element size} for Scale Mesh Size Per Part: each body's size from
    its own bounding box."""
    opts = settings(study)["mesh"]
    per_body = {}
    for index, (solid, body) in enumerate(zip(model_shape.Solids, owners), 1):
        per_body.setdefault(body.Name, []).append((index, solid))
    out = {}
    for _name, pieces in per_body.items():
        box = pieces[0][1].BoundBox
        for _i, solid in pieces[1:]:
            box.add(solid.BoundBox)
        size = core.element_size(
            (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax),
            opts["size_pct"],
            opts["size_mm"],
        )
        for index, _solid in pieces:
            out[index] = size
    return out


def _fem_objects(doc, item, model, subs):
    """FreeCAD FEM objects for one load: a pressure (FreeCAD writes it per element face,
    exact on curved faces too). Forces, moments, bearing loads and remote forces are written
    by SciForge itself (_solver_cards)."""
    import ObjectsFem

    data = item_data(item)
    kind = data["kind"]
    opts = core.options("load", kind, data["options"])
    info = core.kind_info("load", kind)
    if not info.get("built"):
        raise SimulationError("%s is not in SciForge yet." % info["title"])
    out = []
    if kind == "pressure":
        faces = [s for s in subs if s.startswith("Face")]
        pressure = ObjectsFem.makeConstraintPressure(doc, "SimPressure")
        pressure.References = [(model, faces)]
        pressure.Pressure = "%r MPa" % abs(float(opts["magnitude"]))
        # FreeCAD's pressure pushes into the face; a negative size or Flip pulls
        pressure.Reversed = bool(opts.get("flip")) != (float(opts["magnitude"]) < 0)
        out.append(pressure)
    return out


# -- what SciForge writes into CalculiX's input ----------------------------------------------------
class _MeshData:
    """The mesh's nodes and the lookups the solver cards need, made once per solve. `groups`
    ({"Face": {12: (elements, nodes)}, "Edge": ..., "Solid": ...}: what Gmsh put on each model
    face, edge and solid, read before the groups were dropped) answers at once what FreeCAD's
    search by geometry takes minutes for on a big mesh (getNodesByFace: 31 s for one face of
    a 366-face part at 2.5 % mesh)."""

    def __init__(self, femmesh, groups=None):
        from femmesh import meshtools

        self.femmesh = femmesh
        self.nodes = femmesh.Nodes
        self.groups = groups or {}
        self._elements = None
        self._meshtools = meshtools

    @property
    def elements(self):
        if self._elements is None:
            self._elements = self._meshtools.get_femelement_table(self.femmesh)
        return self._elements

    def _group(self, sub):
        for kind in ("Face", "Edge", "Solid"):
            if sub.startswith(kind) and sub[len(kind) :].isdigit():
                return self.groups.get(kind, {}).get(int(sub[len(kind) :]))
        return None

    def nodes_of(self, model, sub):
        group = self._group(sub)
        if group is not None:
            return list(group[1])
        element = _model_element(model, sub)
        kind = element.ShapeType
        if kind == "Face":
            return list(self.femmesh.getNodesByFace(element))
        if kind == "Edge":
            return list(self.femmesh.getNodesByEdge(element))
        if kind == "Vertex":
            return list(self.femmesh.getNodesByVertex(element))
        if kind == "Solid":
            return list(self.femmesh.getNodesBySolid(element))
        return []

    def face_weights(self, model, sub):
        """{node: area share} of a model face (FreeCAD's consistent shares for a uniform
        load: on a 6-node triangle the corners get 0, the mid-side nodes a third each)."""
        mt = self._meshtools
        group = self._group(sub)
        if group is not None and group[0]:
            table = {e: self.femmesh.getElementNodes(e) for e in group[0]}
        else:
            table = mt.get_ref_facenodes_table(
                self.femmesh, self.elements, _model_element(model, sub)
            )
        if not table:
            return {}
        return mt.get_ref_shape_node_sum_geom_table(mt.get_ref_facenodes_areas(self.nodes, table))

    def edge_weights(self, model, sub):
        mt = self._meshtools
        group = self._group(sub)
        if group is not None and group[0]:
            table = {e: self.femmesh.getElementNodes(e) for e in group[0]}
        else:
            table = mt.get_ref_edgenodes_table(
                self.femmesh, self.elements, _model_element(model, sub)
            )
        if not table:
            return {}
        return mt.get_ref_shape_node_sum_geom_table(mt.get_ref_edgenodes_lengths(self.nodes, table))

    def point(self, node):
        p = self.nodes[node]
        return (p.x, p.y, p.z)


def _mesh_groups(mesh):
    """{"Face" / "Edge" / "Solid": {index: (element ids, node ids)}} of the groups Gmsh named
    after the model's faces, edges and solids ("Face12"; the mesh reader adds a suffix such
    as "Face12_Faces" or "Face12_Nodes" when a group has nodes too); {} without groups."""
    import re

    pattern = re.compile(r"^(Edge|Face|Solid)(\d+)(?:_\w+)?$")
    found = {"Face": {}, "Edge": {}, "Solid": {}}
    try:
        for group in mesh.Groups:
            match = pattern.match(mesh.getGroupName(group))
            if not match:
                continue
            kind, number = match.group(1), int(match.group(2))
            elements, nodes = found[kind].setdefault(number, ([], set()))
            ids = list(mesh.getGroupElements(group))
            if mesh.getGroupElementType(group) == "Node":
                nodes.update(ids)
            else:
                elements.extend(ids)
                for element in ids:
                    nodes.update(mesh.getElementNodes(element))
    except Exception as exc:
        log("simulation: the mesh's groups could not be read (%s): searching by geometry" % exc)
        return {}
    return {
        kind: {n: (elements, sorted(nodes)) for n, (elements, nodes) in table.items()}
        for kind, table in found.items()
    }


def _face_normal_at(face, point):
    """The outward normal of a face at (near) a point."""
    try:
        u, v = face.Surface.parameter(App.Vector(*point))
        n = face.normalAt(u, v)
        return (n.x, n.y, n.z)
    except Exception:
        n = face.normalAt(*_middle_uv(face))
        return (n.x, n.y, n.z)


def _flat(face):
    """True for a planar face (its normal is the same everywhere)."""
    try:
        return face.Surface.TypeId == "Part::GeomPlane"
    except Exception:
        return False


def _middle_uv(face):
    u0, u1, v0, v1 = face.ParameterRange
    return (u0 + u1) / 2.0, (v0 + v1) / 2.0


def _cylinder_frame(face):
    """(point on the axis, unit axis, +1 / -1: whether the face's outward normal points away
    from the axis) of a cylindrical face."""
    surface = face.Surface
    axis = surface.Axis
    centre = surface.Center
    u, v = _middle_uv(face)
    p = face.valueAt(u, v)
    n = face.normalAt(u, v)
    d = p - centre
    radial = d - axis * d.dot(axis)
    sign = 1.0 if n.dot(radial) >= 0 else -1.0
    return (centre.x, centre.y, centre.z), core.unit_vector((axis.x, axis.y, axis.z)), sign


def _radial(point, centre, axis):
    d = [point[i] - centre[i] for i in range(3)]
    along = sum(d[i] * axis[i] for i in range(3))
    r = [d[i] - along * axis[i] for i in range(3)]
    length = sum(c * c for c in r) ** 0.5
    if length <= 1e-12:
        return None
    return [c / length for c in r]


def _weights_on(mesh, model, subs):
    """{node: area / length share} over the item's faces (or edges), summed where faces
    meet, and {node: the face it came from} (the first)."""
    weights, owner = {}, {}
    faces = [s for s in subs if s.startswith("Face")]
    edges = [s for s in subs if s.startswith("Edge")]
    for sub in faces:
        for node, w in mesh.face_weights(model, sub).items():
            weights[node] = weights.get(node, 0.0) + w
            owner.setdefault(node, sub)
    if not faces:
        for sub in edges:
            for node, w in mesh.edge_weights(model, sub).items():
                weights[node] = weights.get(node, 0.0) + w
                owner.setdefault(node, sub)
    return weights, owner


def _constraint_rows(item, model, mesh, subs):
    """node_constraints rows of one constraint item."""
    data = item_data(item)
    kind = data["kind"]
    opts = core.options("constraint", kind, data["options"])
    source = item.Label
    rows = []
    if kind in ("fixed", "displacement"):
        values = {}
        for dof, axis in enumerate(("x", "y", "z")):
            if kind == "fixed" and opts.get(axis):
                values[dof] = 0.0
            elif kind == "displacement" and opts.get(axis) is not None:
                values[dof] = float(opts[axis])
        nodes = set()
        for sub in subs:
            nodes.update(mesh.nodes_of(model, sub))
        for node in sorted(nodes):
            for dof, value in values.items():
                rows.append((node, source, "spc", (dof, value)))
        return rows, nodes
    nodes = set()
    for sub in subs:
        if not sub.startswith("Face"):
            continue
        face = _model_element(model, sub)
        face_nodes = mesh.nodes_of(model, sub)
        nodes.update(face_nodes)
        if kind == "pin":
            centre, axis, _sign = _cylinder_frame(face)
            for node in face_nodes:
                radial = _radial(mesh.point(node), centre, axis)
                if radial is None:
                    continue
                if opts.get("radial"):
                    rows.append((node, source, "eq", tuple(radial)))
                if opts.get("axial"):
                    rows.append((node, source, "eq", tuple(axis)))
                if opts.get("tangential"):
                    tangent = (
                        axis[1] * radial[2] - axis[2] * radial[1],
                        axis[2] * radial[0] - axis[0] * radial[2],
                        axis[0] * radial[1] - axis[1] * radial[0],
                    )
                    rows.append((node, source, "eq", tangent))
        elif kind == "frictionless":
            flat = face.Surface.TypeId == "Part::GeomPlane"
            normal = (
                _face_normal_at(face, mesh.point(face_nodes[0])) if flat and face_nodes else None
            )
            for node in face_nodes:
                n = normal if flat else _face_normal_at(face, mesh.point(node))
                rows.append((node, source, "eq", tuple(n)))
    return rows, nodes


def _load_forces(item, model, mesh, subs):
    """{node: [fx, fy, fz]} of a force, moment, bearing load or remote force item."""
    data = item_data(item)
    kind = data["kind"]
    opts = core.options("load", kind, data["options"])
    magnitude = float(opts["magnitude"]) * (-1.0 if opts.get("flip") else 1.0)
    out = {}

    def add(node, f):
        acc = out.setdefault(node, [0.0, 0.0, 0.0])
        for i in range(3):
            acc[i] += f[i]

    if kind == "force":
        faces = [s for s in subs if s.startswith("Face")]
        edges = [s for s in subs if s.startswith("Edge")]
        vertices = [s for s in subs if s.startswith("Vertex")]
        per_entity = bool(opts.get("per_entity"))
        normal = opts.get("direction") == "normal"
        # (the dialogs refuse these with the same sentences: simulation_core.check; an item
        # saved before they did is refused here rather than solved with a part of its picks
        # left out, or with its total counted twice)
        if normal and (edges or vertices or not faces):
            raise SimulationError("%s: %s" % (item.Label, core.FORCE_NORMAL_NEEDS_FACES))
        kinds = [k for k in (faces, edges, vertices) if k]
        if not normal and not per_entity and len(kinds) > 1:
            raise SimulationError("%s: %s" % (item.Label, core.FORCE_ONE_KIND))
        # an entity is one pick of the person's (each gets the whole force with Force Per
        # Entity), else all the picks together share it
        entities = map_pick_groups(item, model) if per_entity else [list(subs)]
        groups = []  # (direction, {node: weight}, share of the force)
        for entity in entities:
            e_faces = [s for s in entity if s.startswith("Face")]
            e_edges = [s for s in entity if s.startswith("Edge")]
            e_vertices = [s for s in entity if s.startswith("Vertex")]
            if normal:
                # each face along its own normal, the faces sharing the force by area (flat
                # faces: a curved one has no one normal, simulation_core.NORMAL_NEEDS_FLAT)
                if any(not _flat(_model_element(model, s)) for s in e_faces):
                    raise SimulationError("%s: Force %s" % (item.Label, core.NORMAL_NEEDS_FLAT))
                areas = [_model_element(model, s).Area for s in e_faces]
                total = sum(areas) or 1.0
                for sub, area in zip(e_faces, areas):
                    face = _model_element(model, sub)
                    n = face.normalAt(*_middle_uv(face))
                    # a positive force pushes into the face (against its outward normal)
                    weights, _owner = _weights_on(mesh, model, [sub])
                    groups.append(((-n.x, -n.y, -n.z), weights, area / total))
                continue
            direction = core.unit_vector(opts.get("vector") or [0, 0, -1])
            if e_faces or e_edges:
                # faces share it by area, edges by length (FreeCAD's consistent node shares)
                weights, _owner = _weights_on(mesh, model, e_faces or e_edges)
                groups.append((direction, weights, 1.0))
            for sub in e_vertices:
                weights = {n: 1.0 for n in mesh.nodes_of(model, sub)}
                groups.append((direction, weights, 1.0 / len(e_vertices)))
        for direction, weights, share in groups:
            total = sum(weights.values())
            if total <= 0:
                continue
            for node, w in weights.items():
                f = magnitude * share * w / total
                add(node, [f * direction[0], f * direction[1], f * direction[2]])
        return out
    faces = [s for s in subs if s.startswith("Face")]
    if kind == "moment":
        if opts.get("per_entity"):
            # each pick of the person's gets the whole moment (map_pick_groups)
            sets = [[s for s in g if s.startswith("Face")] for g in map_pick_groups(item, model)]
            sets = [g for g in sets if g]
        else:
            sets = [faces]
        for group in sets:
            weights, _owner = _weights_on(mesh, model, group)
            nodes = sorted(weights)
            if not nodes:
                continue
            if opts.get("direction") == "normal":
                face = _model_element(model, group[0])
                if not _flat(face):
                    raise SimulationError("%s: Moment %s" % (item.Label, core.NORMAL_NEEDS_FLAT))
                n = face.normalAt(*_middle_uv(face))
                axis = (n.x, n.y, n.z)
            else:
                axis = core.unit_vector(opts.get("vector") or [0, 0, 1])
            moment = [magnitude * c for c in axis]
            forces = core.distribute(
                [mesh.point(n) for n in nodes], [weights[n] for n in nodes], (0, 0, 0), moment
            )
            for node, f in zip(nodes, forces):
                add(node, f)
        return out
    weights, owner = _weights_on(mesh, model, faces)
    nodes = sorted(weights)
    if not nodes:
        return out
    points = [mesh.point(n) for n in nodes]
    w = [weights[n] for n in nodes]
    direction = core.unit_vector(opts.get("vector") or [0, 0, -1])
    if kind == "remote_force":
        force = [magnitude * c for c in direction]
        moment = core.remote_moment(points, w, force, [float(c) for c in opts["point"]])
        forces = core.distribute(points, w, force, moment)
    elif kind == "bearing":
        frames = {s: _cylinder_frame(_model_element(model, s)) for s in faces}
        inward = []
        for node, p in zip(nodes, points):
            centre, axis, sign = frames[owner[node]]
            radial = _radial(p, centre, axis) or [0.0, 0.0, 0.0]
            # into the material: against the face's outward normal
            inward.append([-sign * c for c in radial])
        if magnitude < 0:
            direction = [-c for c in direction]
        forces = core.bearing_forces(points, w, inward, direction, abs(magnitude))
    else:
        raise SimulationError("%s is not in SciForge yet." % core.kind_info("load", kind)["title"])
    for node, f in zip(nodes, forces):
        add(node, f)
    return out


def _rigid_rows(study, model, mesh, held_nodes):
    """Remove rigid body modes: 3-2-1 rows for every connected piece of the model that no
    constraint holds."""
    rows = []
    solids = list(model.Solids)
    # pieces: solids that share a face (the general fuse made them share it) belong together
    parent = list(range(len(solids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            if find(i) == find(j):
                continue
            if any(fa.isSame(fb) for fa in solids[i].Faces for fb in solids[j].Faces):
                parent[find(j)] = find(i)
    groups = {}
    for i in range(len(solids)):
        groups.setdefault(find(i), []).append(i)
    for members in groups.values():
        nodes = set()
        for i in members:
            nodes.update(mesh.nodes_of(model, "Solid%d" % (i + 1)))
        if nodes & held_nodes:
            continue
        rows += core.three_two_one([(n, mesh.point(n)) for n in sorted(nodes)])
    return rows


def _solver_cards(study, model, femmesh, subs, groups=None):
    """The constraints, loads and reaction outputs SciForge writes into CalculiX's input:
    {"model": lines before *STEP, "step": lines inside the step, "reactions": {set name: item
    label}, "notes": [sentences]}."""
    mesh = _MeshData(femmesh, groups)
    rows, reactions, notes = [], {}, []
    held = set()
    directions = {}  # node -> [(constraint label, direction it holds there)]
    model_lines, step_lines = [], []
    constraint_items = [i for i in items(study, "constraint") if not i.Suppressed]
    for index, item in enumerate(constraint_items, 1):
        item_rows, nodes = _constraint_rows(item, model, mesh, subs[item.Name])
        if not nodes:
            raise SimulationError(
                "%s found no mesh nodes on what it holds: make the mesh finer there." % item.Label
            )
        rows += item_rows
        held.update(nodes)
        for node, _source, kind, data in item_rows:
            d = [0.0, 0.0, 0.0]
            if kind == "spc":
                d[data[0]] = 1.0
            else:
                d = list(data)
            directions.setdefault(node, []).append((item.Label, tuple(d)))
        name = "SFR%d" % index
        reactions[name] = item.Label
        model_lines.append("*NSET,NSET=%s" % name)
        ordered = sorted(nodes)
        for i in range(0, len(ordered), 16):
            model_lines.append(",".join(str(n) for n in ordered[i : i + 16]))
    if settings(study)["remove_rigid"]:
        rows += _rigid_rows(study, model, mesh, held)
    merged = core.node_constraints(rows)
    if merged["conflicts"]:
        pairs = sorted({(b or "?", a) for _n, a, b in merged["conflicts"]})
        for first, second in pairs:
            notes.append(
                "%s and %s ask different things of the same corner or edge: %s wins there."
                % (first, second, first)
            )
    model_lines += core.inp_equations(merged["equations"])
    boundary = core.inp_boundaries(merged["spc"])
    if boundary:
        step_lines.append("*BOUNDARY")
        step_lines += boundary
    loads = {}
    for item in items(study, "load"):
        if item.Suppressed or item_data(item)["kind"] == "pressure":
            continue
        for node, f in _load_forces(item, model, mesh, subs[item.Name]).items():
            acc = loads.setdefault(node, [0.0, 0.0, 0.0])
            for i in range(3):
                acc[i] += f[i]
    cloads = core.inp_loads(loads)
    if cloads:
        step_lines.append("*CLOAD")
        step_lines += cloads
    for name in reactions:
        step_lines.append("*NODE PRINT, NSET=%s, TOTALS=ONLY" % name)
        step_lines.append("RF")
    if held:
        # every held node's force too: the reactions are worked out node by node from them
        # (simulation_core.split_reactions; the totals above are the fallback)
        model_lines.append("*NSET,NSET=%s" % HELD_SET)
        ordered = sorted(held)
        for i in range(0, len(ordered), 16):
            model_lines.append(",".join(str(n) for n in ordered[i : i + 16]))
        step_lines.append("*NODE PRINT, NSET=%s" % HELD_SET)
        step_lines.append("RF")
    return {
        "model": model_lines,
        "step": step_lines,
        "reactions": reactions,
        "held": directions,
        "notes": notes,
        "equations": len(merged["equations"]),
    }


def _inject(path, cards):
    """Put SciForge's cards into FreeCAD's CalculiX input: the node sets and equations before
    the step, the boundaries, loads and outputs at the end of the step."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    step = next((i for i, line in enumerate(lines) if line.upper().startswith("*STEP")), None)
    end = max(
        (i for i, line in enumerate(lines) if line.upper().startswith("*END STEP")), default=None
    )
    if step is None or end is None:
        raise SimulationError("The solver input has no step: it could not be written.")
    head = ["**", "** SciForge: node sets and equations"] + cards["model"] + ["**"]
    tail = ["**", "** SciForge: constraints, loads and reactions"] + cards["step"] + ["**"]
    lines = lines[:step] + head + lines[step:end] + tail + lines[end:]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


HELD_SET = "SFRHELD"  # the node set of every held node (its forces are printed node by node)


def _held_reactions(inp_path, dat_path, held):
    """({constraint label: [fx, fy, fz]}, None): the force each constraint takes, from the
    solver's forces at the held nodes less the loads acting right at them, each node shared
    among the constraints that hold it (simulation_core.split_reactions); or (None, the reason
    it could not be worked out). Pure file work, never raises (it runs in the background)."""
    if not held:
        return {}, None
    try:
        with open(dat_path, encoding="utf-8", errors="replace") as handle:
            forces = core.node_forces_from_dat(handle.read(), HELD_SET)
        if not forces:
            return None, "the solver printed no forces at the held nodes"
        with open(inp_path, encoding="utf-8", errors="replace") as handle:
            applied = core.inp_loads_at(handle.read(), set(held))
        return core.split_reactions(forces, applied, held), None
    except Exception as exc:
        return None, str(exc) or exc.__class__.__name__


def _straighten_input(path):
    """The curved elements of a CalculiX input that turned inside out (or nearly) made
    straight-sided (core.straighten_tets): the lines of the nodes it moved are rewritten.
    Pure file work (it runs in the background thread). Returns (elements made straight,
    elements still bad)."""
    import numpy as np

    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().split("\n")
    ids, xyz, where, elements, pending = [], [], [], [], []
    section = None
    for i, line in enumerate(lines):
        if line.startswith("*"):
            upper = line.upper().replace(" ", "")
            if upper == "*NODE" or upper.startswith("*NODE,"):
                section = "node"
            elif upper.startswith("*ELEMENT,") and "TYPE=C3D10," in upper + ",":
                section, pending = "tet10", []
            else:
                section = None
            continue
        if section == "node":
            parts = line.split(",")
            if len(parts) >= 4:
                ids.append(int(parts[0]))
                xyz.append((float(parts[1]), float(parts[2]), float(parts[3])))
                where.append(i)
        elif section == "tet10":
            pending += [int(p) for p in line.split(",") if p.strip()]
            if len(pending) >= 11:  # (an element's numbers may go on over two lines)
                elements.append(pending[1:11])
                pending = []
    if not elements or not ids:
        return 0, 0
    ids_a = np.array(ids, dtype=np.int64)
    row_of = np.full(int(ids_a.max()) + 1, -1, dtype=np.int64)
    row_of[ids_a] = np.arange(len(ids_a))
    elements_a = np.array(elements, dtype=np.int64)
    if elements_a.max() >= len(row_of) or elements_a.min() < 0:
        return 0, 0  # (an element names a node that is not listed: CalculiX will say so)
    rows = row_of[elements_a]
    if (rows < 0).any():
        return 0, 0
    xyz_a = np.array(xyz, dtype=float)
    moved, straightened, left = core.straighten_tets(xyz_a, rows)
    if moved:
        for row in moved:
            x, y, z = xyz_a[row]
            lines[where[row]] = "%d, %.13e, %.13e, %.13e" % (ids[row], x, y, z)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    return straightened, left


# -- the mesh: Gmsh's size fields, Netgen when Gmsh fails, statistics ------------------------------
def _size_fields(study, model, owners, subs, global_size, view=None):
    """Gmsh .geo lines for the local mesh controls and Scale Mesh Size Per Part: a size
    field per control (the picked faces / edges / bodies get the control's size, which grows
    back to the global size at the study's adjacent size ratio), combined with Min."""
    opts = settings(study)["mesh"]
    ratio = float(opts["adjacent_ratio"])
    lines, finals = [], []
    n = 100  # (FreeCAD's .geo uses no fields itself without boundary layers)
    for item in items(study, "mesh"):
        if item.Suppressed or item.Name not in subs:
            continue
        size = float(core.options("mesh", "local", item_data(item)["options"])["size"])
        picked = subs[item.Name]
        faces = [s[4:] for s in picked if s.startswith("Face")]
        edges = [s[4:] for s in picked if s.startswith("Edge")]
        solids = [s[5:] for s in picked if s.startswith("Solid")]
        if solids:
            n += 1
            lines += [
                "Field[%d] = Constant;" % n,
                "Field[%d].VIn = %r;" % (n, size),
                "Field[%d].VOut = 1e22;" % n,
                "Field[%d].VolumesList = {%s};" % (n, ", ".join(solids)),
                "Field[%d].IncludeBoundary = 1;" % n,
            ]
            finals.append(n)
        if faces or edges:
            n += 1
            dist = n
            lines.append("Field[%d] = Distance;" % dist)
            if faces:
                lines.append("Field[%d].SurfacesList = {%s};" % (dist, ", ".join(faces)))
            if edges:
                lines.append("Field[%d].CurvesList = {%s};" % (dist, ", ".join(edges)))
            lines.append("Field[%d].Sampling = 40;" % dist)
            n += 1
            spread = max(global_size - size, 0.0) / max(ratio - 1.0, 0.05)
            lines += [
                "Field[%d] = Threshold;" % n,
                "Field[%d].InField = %d;" % (n, dist),
                "Field[%d].SizeMin = %r;" % (n, size),
                "Field[%d].SizeMax = %r;" % (n, max(global_size, size)),
                "Field[%d].DistMin = 0;" % n,
                "Field[%d].DistMax = %r;" % (n, max(spread, size)),
            ]
            finals.append(n)
    if opts["scale_per_part"]:
        for index, size in sorted(_part_sizes(study, model, owners).items()):
            n += 1
            lines += [
                "Field[%d] = Constant;" % n,
                "Field[%d].VIn = %r;" % (n, size),
                "Field[%d].VOut = 1e22;" % n,
                "Field[%d].VolumesList = {%d};" % (n, index),
                "Field[%d].IncludeBoundary = 1;" % n,
            ]
            finals.append(n)
    if view:
        # adaptive refinement: the sizes of the last pass's elements, smaller where the
        # result changed the most (a Gmsh post-processing view used as a size field)
        n += 1
        lines += [
            'Merge "%s";' % view,
            "Field[%d] = PostView;" % n,
            "Field[%d].ViewIndex = 0;" % n,
        ]
        finals.append(n)
    if not finals:
        return []
    n += 1
    lines += [
        "Field[%d] = Min;" % n,
        "Field[%d].FieldsList = {%s};" % (n, ", ".join(str(f) for f in finals)),
        "Background Field = %d;" % n,
    ]
    return ["// SciForge: local mesh controls"] + lines + [""]


def _write_size_view(path, mesh, result, key, portion):
    """A Gmsh view (.pos) of the element sizes for the next adaptive pass: every element of
    this mesh with its size at its corners, halved on the `portion` % of the elements where
    the result `key` changes the most across the element."""
    values = Results(result)
    by_node = dict(zip(values.node_ids, values.values(key)))
    nodes = mesh.Nodes
    elements = []
    for e in mesh.Volumes:
        ids = mesh.getElementNodes(e)
        corners = ids[:4]
        pts = [nodes[n] for n in corners]
        size = sum((pts[i] - pts[j]).Length for i in range(4) for j in range(i + 1, 4)) / 6.0
        found = [by_node[n] for n in ids if n in by_node]
        change = (max(found) - min(found)) if found else 0.0
        elements.append((change, size, corners))
    count = max(1, int(round(len(elements) * portion / 100.0)))
    marked = set(
        i
        for _c, i in sorted(((c, i) for i, (c, _s, _n) in enumerate(elements)), reverse=True)[
            :count
        ]
    )
    target = {}
    for i, (_change, size, corners) in enumerate(elements):
        want = size / 2.0 if i in marked else size
        for n in corners:
            if n not in target or want < target[n]:
                target[n] = want
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('View "sizes" {\n')
        for _change, _size, corners in elements:
            xyz = ",".join("%.9g,%.9g,%.9g" % (nodes[n].x, nodes[n].y, nodes[n].z) for n in corners)
            handle.write("SS(%s){%s};\n" % (xyz, ",".join("%.9g" % target[n] for n in corners)))
        handle.write("};\n")


def _write_fields(geo_path, lines):
    """SciForge's lines into FreeCAD's Gmsh input: the size fields, and one thread (Gmsh's
    threads mesh the surfaces in a different order on every run, so the same study gave a
    slightly different mesh and different numbers each time; its 3D meshing is on one thread
    anyway)."""
    import re

    with open(geo_path, encoding="utf-8") as handle:
        text = handle.read()
    text = re.sub(r"General\.NumThreads\s*=\s*\d+;", "General.NumThreads = 1;", text)
    if lines:
        marker = "// optimize the mesh"
        if marker not in text:
            marker = "Mesh  3;"
        text = text.replace(marker, "\n".join(lines) + "\n" + marker, 1)
    with open(geo_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _gmsh_problem(output, model, owners):
    """A sentence about what Gmsh could not mesh, naming the bodies of the surfaces it
    reported (Gmsh numbers the model's faces in order)."""
    errors, numbers = core.gmsh_errors(output)
    names = []
    for number in numbers:
        if 1 <= number <= len(model.Faces):
            face = model.Faces[number - 1]
            for solid, body in zip(model.Solids, owners):
                if any(face.isSame(f) for f in solid.Faces):
                    if body.Label not in names:
                        names.append(body.Label)
                    break
    text = " ".join(errors[-2:])
    if names:
        return "Gmsh could not mesh some faces of %s (%s)." % (", ".join(names), text)
    return "Gmsh could not mesh the model (%s)." % (text or "no reason given")


NETGEN_SCRIPT = """import sys
import FreeCAD as App
import Part
import ObjectsFem

shape = Part.Shape()
shape.read({brep!r})
doc = App.newDocument("SciForgeNetgen")
feature = doc.addObject("Part::Feature", "Model")
feature.Shape = shape
mesh = ObjectsFem.makeMeshNetgenLegacy(doc, "Mesh")
mesh.Shape = feature
mesh.Fineness = "UserDefined"
mesh.MaxSize = {size!r}
mesh.MinSize = {smallest!r}
mesh.GrowthRate = 0.3
mesh.NbSegsPerEdge = 1
mesh.NbSegsPerRadius = 2
mesh.SecondOrder = {second!r}
mesh.Optimize = True
doc.recompute()
femmesh = mesh.FemMesh
if femmesh.VolumeCount == 0:
    print("SciForge netgen: no volume elements")
    sys.exit(2)
femmesh.write({out!r})
print("SciForge netgen: %d nodes" % femmesh.NodeCount)
"""


def _thin_wall_note(femmesh, owners, groups, sample=2000):
    """simulation_core.thin_wall_note for the mesh: each body's wall thickness (2 V / A of
    its solid) against the median edge of its elements (Gmsh's groups say which elements are
    whose; without them, the whole mesh against all the bodies together). A sample of at most
    `sample` elements a body is measured."""
    import statistics

    solids = (groups or {}).get("Solid", {})
    per_body = {}
    for index, body in enumerate(owners, 1):
        entry = per_body.setdefault(body.Name, (body, []))
        found = solids.get(index)
        if found:
            entry[1].extend(found[0])
    if not any(elements for _b, elements in per_body.values()):
        everything = list(femmesh.Volumes)
        unique = [b for b, _e in per_body.values()]
        rows_in = [(" and ".join(b.Label for b in unique), unique, everything)]
    else:
        rows_in = [(b.Label, [b], elements) for b, elements in per_body.values() if elements]
    nodes = femmesh.Nodes
    rows = []
    for label, owned, elements in rows_in:
        volume = sum(b.Shape.Volume for b in owned)
        area = sum(b.Shape.Area for b in owned)
        if area <= 0 or volume <= 0:
            continue
        step = max(1, len(elements) // sample)
        sizes = []
        for e in elements[::step]:
            corners = femmesh.getElementNodes(e)[:4]
            if len(corners) < 4:
                continue
            p = [nodes[n] for n in corners]
            sizes.append(sum((p[i] - p[j]).Length for i in range(4) for j in range(i + 1, 4)) / 6)
        if sizes:
            rows.append((label, 2.0 * volume / area, statistics.median(sizes)))
    return core.thin_wall_note(rows)


def _mesh_stats(femmesh, limit):
    """{"nodes", "elements", "smallest", "largest", "worst_aspect", "over_limit", "sampled"}
    of a volume mesh (element edge lengths and aspect ratios from the corner nodes; a big
    mesh is measured on an even sample of its elements)."""
    nodes = femmesh.Nodes
    volumes = list(femmesh.Volumes)
    step = max(1, len(volumes) // 15000)
    lengths, ratios = [], []
    for e in volumes[::step]:
        corners = femmesh.getElementNodes(e)[:4]
        if len(corners) < 4:
            continue
        pts = [nodes[n] for n in corners]
        pts = [(p.x, p.y, p.z) for p in pts]
        for i in range(4):
            for j in range(i + 1, 4):
                a, b = pts[i], pts[j]
                lengths.append(
                    ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
                )
        ratios.append(core.tetra_aspect(*pts))
    out = core.mesh_quality(lengths, ratios, limit)
    out.update({"nodes": femmesh.NodeCount, "elements": femmesh.VolumeCount, "sampled": step > 1})
    return out


# -- programs --------------------------------------------------------------------------------------
def _binary(name):
    """Path of a program FreeCAD ships (ccx, gmsh): next to FreeCAD first, then FreeCAD's FEM
    setting, then the PATH."""
    exe = name + (".exe" if os.name == "nt" else "")
    home = App.getHomePath()
    for folder in ("bin", os.path.join("Library", "bin")):
        candidate = os.path.join(home, folder, exe)
        if os.path.isfile(candidate):
            return candidate
    try:
        if name == "ccx":
            from femsolver import settings as fem_settings

            found = fem_settings.get_binary("Calculix", silent=True)
            if found and os.path.isfile(found):
                return found
    except Exception:
        pass
    found = shutil.which(exe) or shutil.which(name)
    if found:
        return found
    raise SimulationError(
        "SciForge could not find %s, the program it uses to %s. Reinstall SciForge."
        % (name, "solve" if name == "ccx" else "mesh")
    )


def _freecad_cmd():
    """The command-line FreeCAD (SciForge's) next to this one, for Netgen in its own process;
    None when there is none."""
    home = App.getHomePath()
    names = ("SciForgeCmd", "sciforgecmd", "FreeCADCmd", "freecadcmd")
    # (Linux / Windows: bin next to FreeCAD's home; macOS: the app bundle's Contents/MacOS)
    for folder in ("bin", "", os.path.join("..", "MacOS")):
        for name in names:
            candidate = os.path.join(home, folder, name + (".exe" if os.name == "nt" else ""))
            if os.path.isfile(candidate):
                return candidate
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


# -- solving ---------------------------------------------------------------------------------------
STAGES = ("model", "mesh", "input", "solve", "results")
# a mesh this big takes CalculiX minutes and GBs (143 000 nodes: 2 minutes on 2 threads; 300 000
# nodes: over 6 GB and 9 minutes): the solve's message says so
BIG_MESH_NODES = 150000


class Job:
    """One solve of a study (or, with mesh_only, Fusion's Generate Mesh), in stages. Call
    poll() repeatedly (a timer every 100-200 ms) until done; everything that touches the
    document runs inside poll() on the caller's thread, Gmsh, Netgen and CalculiX run in a
    background thread. cancel() stops it at any stage; a failed or cancelled job leaves the
    study's last results (and its last mesh) as they were, and no temporary files.

    state: "running" | "done" | "failed" | "cancelled"; stage: one of STAGES; message: what
    it is doing (or why it failed); summary: the result summary once done (a mesh-only job:
    the mesh statistics, also in mesh_summary(study)); notes: sentences about what SciForge
    adjusted (constraints that disagreed on a shared edge, Netgen used instead of Gmsh)."""

    def __init__(self, study, mesh_only=False):
        self.study = study
        self.doc = study.Document
        self.mesh_only = bool(mesh_only)
        self.state = "running"
        self.stage = "model"
        self.message = "Preparing the model"
        self.summary = None
        self.notes = []
        self.started = time.time()
        self.work = tempfile.mkdtemp(prefix="sciforge_sim_")
        self.timings = {}
        self.mesher = "gmsh"
        self.mesh_info = None
        self.passes = []  # adaptive refinement: [{"nodes", "value"}] per solve
        self._thread = None
        self._process = None
        self._output = ""
        self._returncode = None
        self._run_error = None
        self._cancel = False
        self._mesh_tools = None
        self._analysis = self._model = self._mesh = None
        self._model_shape = None
        self._owners = []
        self._subs = {}
        self._input = None
        self._reactions = {}
        self._held = {}  # held node -> [(constraint label, direction it holds)]
        self._held_forces = None  # constraint label -> its reaction (node by node)
        self._held_error = None
        self._netgen_out = None
        self._gmsh_problem = None
        self._straight = False  # mesh again with straight-sided elements (bad curved ones)
        self._curved = None  # (made straight, still bad, error) of the check before a solve
        self._curved_text = None  # its note
        self._fingerprints = None  # (signature, mesh signature) when the solve started
        self._mesh_scale = 1.0  # smaller elements (0.5, 0.25) after Gmsh's mesh crossed itself
        self._quality_text = None  # the note on stretched mesh elements
        self._thin_text = None  # the note on walls much thinner than the elements
        self._checked = False  # the pre-check passed (the model is built on the next turn)
        self._getter = None  # FreeCAD's mesh tables for the input (made a turn earlier)
        self._results_step = None  # the next turn of reading the results
        self._made = set()  # (document name, run name) of the runs this job made
        self._solid_nodes = {}  # model solid index -> its mesh nodes (from Gmsh's groups)
        self._groups = {}  # Gmsh's groups: model faces / edges / solids -> elements, nodes
        self._previous_run = None  # adaptive refinement: the last pass's run, until the next
        self._pos = None  # adaptive refinement: the element sizes Gmsh meshes to next
        self._frd_data = None  # the solver's results, read in the background

    # -- public
    def poll(self):
        """Advance as far as possible without waiting. Returns the state."""
        if self.state != "running":
            return self.state
        try:
            if self._thread is not None:
                if self._thread.is_alive():
                    return self.state
                self._thread = None
                if self._cancel:
                    return self._stop("cancelled", "Cancelled.")
                _close_open_transaction(self.doc)  # (what a turn changes is no undo step)
                self._after_background()
                return self.state
            if self._cancel:
                return self._stop("cancelled", "Cancelled.")
            _close_open_transaction(self.doc)
            getattr(self, "_stage_" + self.stage)()
        except SimulationError as exc:
            return self._stop("failed", str(exc))
        except Exception as exc:
            warn("simulation: %s" % exc)
            return self._stop("failed", "The solve failed: %s" % exc)
        return self.state

    def wait(self, timeout=None, idle=None):
        """Run to the end on this thread (scripts, tests, the AI). idle(): called between the
        turns while the background thread works (the AI's solve keeps the window painted
        with it)."""
        end = None if timeout is None else time.time() + timeout
        while self.poll() == "running":
            if end is not None and time.time() > end:
                self.cancel()
                self.poll()
                return self._stop("failed", "The solve took longer than %d s." % timeout)
            if idle is not None:
                try:
                    idle()
                except Exception:
                    pass
            if self._thread is not None:
                self._thread.join(0.05)
        return self.state

    def cancel(self):
        self._cancel = True
        process = self._process
        if process is not None:
            try:
                process.kill()
            except Exception:
                pass

    @property
    def progress(self):
        """0..1, by stage."""
        if self.state == "done":
            return 1.0
        stages = STAGES[:2] if self.mesh_only else STAGES
        index = stages.index(self.stage) if self.stage in stages else 0
        return index / float(len(stages))

    @property
    def elapsed(self):
        return time.time() - self.started

    # -- stages (main thread)
    def _stage_model(self):
        _close_open_transaction(self.doc)
        if self._checked:
            return self._build_model()
        try:
            left = _orphans(self.doc)
            if left:
                _remove_objects(self.doc, list(reversed(left)))
                log("simulation: removed %d objects of an unfinished solve" % len(left))
        except Exception as exc:
            warn("simulation: tidying up: %s" % exc)
        try:
            repaired = repair_picks(self.study)
        except Exception as exc:
            warn("simulation: finding picks again: %s" % exc)
            repaired = []
        if repaired:
            self.notes.append(
                "The design changed, so SciForge found again the faces of %s by their shape."
                % ", ".join(repaired)
            )
        try:
            refresh_signatures(self.study)
        except Exception as exc:
            warn("simulation: remembering picks: %s" % exc)
        if self._fingerprints is None:
            # what the results and the mesh are of: the study as the solve starts (a design
            # changed while it runs leaves them out of date)
            self._fingerprints = (signature(self.study), mesh_signature(self.study))
        checks = precheck(self.study)
        if self.mesh_only:
            errors = [
                text
                for level, text in checks
                if level == "error" and ("no solid body" in text or "lost what" in text)
            ]
        else:
            errors = [text for level, text in checks if level == "error"]
        if errors:
            raise SimulationError(" ".join(errors))
        # the model is built on the next turn (the window gets a moment between the two; a
        # further pass of the same solve starts there)
        self._checked = True

    def _build_model(self):
        t = time.time()
        shape, self._owners = build_model(self.study)
        self._model_shape = shape
        self._analysis, self._model, self._mesh, self._subs = _make_run(
            self.study, shape, self._owners, self.mesh_only, self._straight
        )
        made = (self.doc.Name, self._analysis.Name)
        self._made.add(made)
        _LIVE_RUNS.add(made)
        self.timings["model"] = time.time() - t
        self.stage, self.message = "mesh", "Meshing"
        self._start_mesh()

    def _start_mesh(self):
        from femmesh.gmshtools import GmshTools

        # (Gmsh first every time: a mesh made again after a failed solve tries Gmsh again)
        self.mesher, self._netgen_out = "gmsh", None
        if self._mesh_scale != 1.0:  # (smaller elements after Gmsh's mesh crossed itself)
            size, smallest = _mesh_sizes(self.study, self._model_shape, self._owners)
            self._mesh.CharacteristicLengthMax = "%r mm" % (size * self._mesh_scale)
            self._mesh.CharacteristicLengthMin = "%r mm" % (smallest * self._mesh_scale)
            if "MeshSizeFromCurvature" in self._mesh.PropertiesList:
                turn = max(float(settings(self.study)["mesh"]["max_turn"]), 5.0)
                self._mesh.MeshSizeFromCurvature = int(round(360.0 / turn / self._mesh_scale))
        tools = GmshTools(self._mesh)
        # GmshTools.prepare() without get_gmsh_command(): that one only looks on the PATH and
        # reports an error when Gmsh is elsewhere (next to SciForge on Windows)
        tools.load_properties()
        tools.update_mesh_data()
        tools.get_tmp_file_paths(self.work, True)
        tools.gmsh_bin = _binary("gmsh")
        tools.error = False
        tools.write_part_file()
        tools.write_geo()
        size = _global_size(self.study, self._model_shape) * self._mesh_scale
        _write_fields(
            tools.temp_file_geo,
            _size_fields(self.study, self._model_shape, self._owners, self._subs, size, self._pos),
        )
        self._mesh_tools = tools
        self._background([tools.gmsh_bin, "-", tools.temp_file_geo], "mesh")

    def _start_netgen(self):
        """Gmsh could not mesh: Netgen (FreeCAD's) in a FreeCAD of its own, in the
        background, on the same model."""
        cmd = _freecad_cmd()
        if cmd is None:
            raise SimulationError(self._gmsh_problem + " " + MESH_ADVICE)
        tools = self._mesh_tools
        opts = settings(self.study)["mesh"]
        size, smallest = _mesh_sizes(self.study, self._model_shape, self._owners)
        script = os.path.join(self.work, "netgen_mesh.py")
        self._netgen_out = os.path.join(self.work, "netgen_mesh.unv")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(
                NETGEN_SCRIPT.format(
                    brep=tools.temp_file_geometry,
                    size=float(size) * self._mesh_scale,
                    smallest=float(smallest) * self._mesh_scale,
                    second=opts["order"] == "parabolic",
                    out=self._netgen_out,
                )
            )
        self.mesher = "netgen"
        self.message = "Meshing again with Netgen"
        log("simulation: %s Trying Netgen." % self._gmsh_problem)
        self._background([cmd, script], "mesh")

    def _after_background(self):
        if self._run_error:
            raise SimulationError(self._run_error)
        if self.stage == "mesh":
            self._after_mesh()
        elif self.stage == "solve":
            self._start_read()
        elif self.stage == "results":
            self._stage_results()

    def _start_read(self):
        """The solver's result file read (parsed) in the background: the slow part of
        reading results (tens of MB for a big mesh), done without the document."""
        self.stage, self.message = "results", "Reading the results"
        self._curved_note()
        frd = os.path.join(self.work, self._input + ".frd")
        if self._returncode not in (0, None) or not os.path.isfile(frd) or not os.path.getsize(frd):
            self._frd_data = None
            self._stage_results()
            return
        from feminout import importCcxFrdResults as frd_module

        inp = os.path.join(self.work, self._input + ".inp")
        dat = os.path.join(self.work, self._input + ".dat")
        held = dict(self._held)

        def work():
            quiet, real = _Quiet(), frd_module.Console
            frd_module.Console = quiet  # (no printing from this thread)
            try:
                self._frd_data = frd_module.read_frd_result(frd)
            finally:
                frd_module.Console = real
            self._held_forces, self._held_error = _held_reactions(inp, dat, held)

        self._background_call(work, "results")

    def _curved_note(self):
        """The note of the check of the curved elements that ran before the solver (the
        last solve's only, with adaptive refinement)."""
        done, self._curved = self._curved, None
        if not done:
            return
        straightened, _left, error = done
        if error:
            warn("simulation: checking the curved mesh elements: %s" % error)
        if self._curved_text in self.notes:
            self.notes.remove(self._curved_text)
        self._curved_text = None
        if straightened:
            self._curved_text = (
                "SciForge made %d curved mesh element%s straight-sided: at tight curves %s "
                "would have turned inside out."
                % (
                    straightened,
                    "" if straightened == 1 else "s",
                    "it" if straightened == 1 else "they",
                )
            )
            self.notes.append(self._curved_text)

    def _after_mesh(self):
        t = time.time()
        if self.mesher == "gmsh":
            tools = self._mesh_tools
            made = os.path.isfile(tools.temp_file_mesh) and os.path.getsize(tools.temp_file_mesh)
            failed = not made or any(
                line.lstrip().startswith("Error") for line in self._output.splitlines()
            )
            if failed:
                if self._mesh_scale > 0.3 and core.mesh_crossed_itself(self._output):
                    # the surface mesh crossed itself (a wall thinner than the elements, a
                    # small gap): elements half as big, at most twice, before Netgen
                    self._mesh_scale *= 0.5
                    self.message = "Meshing again with smaller elements"
                    self._start_mesh()
                    return
                self._gmsh_problem = _gmsh_problem(self._output, self._model_shape, self._owners)
                self._start_netgen()
                return
            tools.read_and_set_new_mesh()
            if self._mesh_scale < 1.0:
                note = (
                    "Gmsh could not mesh at the study's element size (its surface mesh crossed "
                    "itself: a wall thinner than the elements, or a small gap), so SciForge "
                    "made the elements %d times smaller." % int(round(1.0 / self._mesh_scale))
                )
                if note not in self.notes:
                    self.notes.append(note)
        else:
            if not (self._netgen_out and os.path.isfile(self._netgen_out)):
                raise SimulationError(
                    "%s Netgen could not mesh it either. %s"
                    % (self._gmsh_problem or "The mesh could not be made.", MESH_ADVICE)
                )
            import Fem

            self._mesh.FemMesh = Fem.read(self._netgen_out)
            note = "Gmsh could not mesh the model, so Netgen made the mesh (%s)." % (
                self._gmsh_problem or ""
            )
            if note not in self.notes:
                self.notes.append(note)
        # FreeCAD 1.1's Gmsh run names a group after every solid, face and edge; with any
        # group in the mesh, the solver input looks for groups named after the materials,
        # finds none and reports an error before searching the mesh itself. SciForge does
        # not use the groups: drop them, so the search runs straight away.
        mesh = self._mesh.FemMesh
        self._groups = _mesh_groups(mesh)
        solids = self._groups.get("Solid", {})
        if len(solids) == len(self._model_shape.Solids):
            self._solid_nodes = {i: nodes for i, (_elements, nodes) in solids.items()}
        if mesh.GroupCount:
            for group in list(mesh.Groups):
                mesh.removeGroup(group)
            self._mesh.FemMesh = mesh
        mesh = self._mesh.FemMesh
        if mesh.VolumeCount == 0:
            raise SimulationError(
                "The mesh has no solid elements: the model may not be a closed solid. "
                + MESH_ADVICE
            )
        self.timings["mesh_read"] = time.time() - t
        limit = float(settings(self.study)["mesh"]["aspect_ratio"])
        t = time.time()
        self.mesh_info = _mesh_stats(mesh, limit)
        self.mesh_info.update(
            {
                "mesher": self.mesher,
                "size": _global_size(self.study, self._model_shape) * self._mesh_scale,
                "order": settings(self.study)["mesh"]["order"],
                "signature": (
                    self._fingerprints[1] if self._fingerprints else mesh_signature(self.study)
                ),
                "made": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self.timings["mesh_stats"] = time.time() - t
        quality = core.mesh_quality_note(self.mesh_info, limit)
        if self._quality_text in self.notes:  # (the last mesh's only, with adaptive passes)
            self.notes.remove(self._quality_text)
        self._quality_text = quality
        if quality:
            self.notes.append(quality)
        try:
            thin = _thin_wall_note(mesh, self._owners, self._groups)
        except Exception as exc:
            warn("simulation: measuring the walls against the mesh: %s" % exc)
            thin = None
        if self._thin_text in self.notes:
            self.notes.remove(self._thin_text)
        self._thin_text = thin
        if thin:
            self.notes.append(thin)
        if self.mesh_only:
            _close_open_transaction(self.doc)
            _remove_run(self.study, "SimMeshRun")
            self.study.SimMeshRun = self._analysis
            _save(self.study, MESH_PROP, self.mesh_info)
            apply_keep_results(self.study)
            _untouch(self.study)
            self.summary = dict(self.mesh_info)
            self._analysis = None  # (kept)
            return self._stop("done", "Done")
        # (the input is written on the next turn: the window gets a moment between the two)
        self.stage, self.message = "input", "Writing the solver input"

    def _stage_input(self):
        t = time.time()
        from femmesh import meshsetsgetter
        from femsolver.calculix import writer
        from femtools import membertools

        from femmesh import meshtools

        solver = next(o for o in self._analysis.Group if o.Name.startswith("SimSolver"))
        groups = getattr(self, "_groups", None) or {}
        real_search = meshtools.get_femnodes_by_refshape
        model = self._model

        def search(femmesh, ref):
            # the nodes of the model's faces / solids from Gmsh's groups (FreeCAD's search by
            # geometry takes minutes on a big mesh)
            obj, names = ref
            if groups and getattr(obj, "Name", None) == model.Name:
                found = []
                for name in names:
                    kind = next((k for k in ("Face", "Edge", "Solid") if name.startswith(k)), None)
                    group = groups.get(kind, {}).get(int(name[len(kind) :])) if kind else None
                    if group is None:
                        return real_search(femmesh, ref)
                    found += group[1]
                return found
            return real_search(femmesh, ref)

        if self._getter is None:
            # FreeCAD's tables of the mesh (seconds on a big one) on this turn, the input on
            # the next: the window gets a moment between the two
            meshtools.get_femnodes_by_refshape = search
            try:
                self._getter = meshsetsgetter.MeshSetsGetter(
                    self._analysis, solver, self._mesh, membertools.AnalysisMember(self._analysis)
                )
            finally:
                meshtools.get_femnodes_by_refshape = real_search
            self.timings["input"] = time.time() - t
            return
        getter, self._getter = self._getter, None
        meshtools.get_femnodes_by_refshape = search
        try:
            getter.get_mesh_sets()
            # the writer makes a second getter of its own "for compatibility" that CalculiX's
            # writer never reads (4 s of tables on a big mesh): it gets this one
            getter_class = meshsetsgetter.MeshSetsGetter
            meshsetsgetter.MeshSetsGetter = lambda *args, **kwargs: getter
            try:
                w = writer.FemInputWriterCcx(
                    self._analysis,
                    solver,
                    self._mesh,
                    getter.member,
                    self.work,
                    getter.mat_geo_sets,
                )
            finally:
                meshsetsgetter.MeshSetsGetter = getter_class
            path = w.write_solver_input()
        finally:
            meshtools.get_femnodes_by_refshape = real_search
        if not path or not os.path.isfile(path):
            raise SimulationError("The solver input could not be written.")
        cards = _solver_cards(self.study, self._model_shape, self._mesh.FemMesh, self._subs, groups)
        _inject(path, cards)
        self._reactions = cards["reactions"]
        self._held = cards.get("held", {})
        self.notes += cards["notes"]
        self._input = os.path.splitext(os.path.basename(path))[0]
        self.timings["input"] = self.timings.get("input", 0.0) + time.time() - t
        nodes = self._mesh.FemMesh.NodeCount
        self.stage = "solve"
        self.message = "Solving %s nodes with CalculiX" % "{:,}".format(nodes).replace(",", " ")
        if nodes > BIG_MESH_NODES:
            self.message += (
                ": a big mesh, it can take several minutes and some GB of memory (a larger "
                "element size solves faster)"
            )
        env = dict(os.environ)
        if not env.get("OMP_NUM_THREADS"):
            env["OMP_NUM_THREADS"] = str(max(1, (os.cpu_count() or 2) - 1))
        opts = settings(self.study)["mesh"]
        self._curved = None
        check = opts["order"] == "parabolic" and opts["curved"] and not self._straight

        def straighten():
            # (background thread) curved elements turned inside out made straight-sided
            try:
                self._curved = _straighten_input(path) + (None,)
            except Exception as exc:
                self._curved = (0, 0, str(exc))

        self._background(
            [_binary("ccx"), "-i", self._input],
            "solve",
            env=env,
            before=straighten if check else None,
        )

    def _stage_results(self):
        if self._results_step is not None:  # (the next turn of reading the results)
            step, self._results_step = self._results_step, None
            return step()
        t = time.time()
        frd = os.path.join(self.work, self._input + ".frd")
        if self._returncode not in (0, None) or not os.path.isfile(frd) or not os.path.getsize(frd):
            opts = settings(self.study)["mesh"]
            if (
                "jacobian" in (self._output or "").lower()
                and not self._straight
                and opts["order"] == "parabolic"
            ):
                # curved elements turned inside out: the same mesh with straight sides
                self._straight = True
                if self._curved_text in self.notes:
                    self.notes.remove(self._curved_text)
                self.notes.append(
                    "Some curved mesh elements turned inside out, so SciForge made the mesh "
                    "again with straight-sided elements."
                )
                _remove_objects(self.doc, list(reversed(_run_members(self._analysis))))
                self._analysis = None
                self.stage, self.message = "model", "Meshing again with straight-sided elements"
                return
            raise SimulationError(_solver_failure(self._output))
        from feminout import importCcxFrdResults

        before = set(o.Name for o in self.doc.Objects)
        data = getattr(self, "_frd_data", None)
        real_read, real_pipeline = (
            importCcxFrdResults.read_frd_result,
            importCcxFrdResults.setupPipeline,
        )
        if data is not None:  # (parsed in the background already)
            importCcxFrdResults.read_frd_result = lambda _path: data
        # no VTK results pipeline: SciForge draws the results itself (it doubled the time and
        # the size of the results in the file); von Mises and the principal stresses for every
        # node at once with numpy (FreeCAD's loop over the nodes took 9 s for 140 000 nodes)
        from femresult import resulttools

        real = (
            resulttools.add_von_mises,
            resulttools.add_principal_stress_std,
            resulttools.add_disp_apps,
            resulttools.compact_result,
        )
        importCcxFrdResults.setupPipeline = lambda *args, **kwargs: None
        resulttools.add_von_mises = _fast_von_mises
        resulttools.add_principal_stress_std = _fast_principal_stresses
        resulttools.add_disp_apps = _fast_displacement_lengths
        # FreeCAD renumbers the result mesh without gaps (seconds on a big mesh): on the next
        # turn (nothing in between reads the numbering)
        resulttools.compact_result = lambda res_obj: res_obj
        try:
            importCcxFrdResults.importFrd(frd, self._analysis, "Sim")
        finally:
            importCcxFrdResults.read_frd_result = real_read
            importCcxFrdResults.setupPipeline = real_pipeline
            (
                resulttools.add_von_mises,
                resulttools.add_principal_stress_std,
                resulttools.add_disp_apps,
                resulttools.compact_result,
            ) = real
            self._frd_data = None
        made = [o for o in self.doc.Objects if o.Name not in before]
        result = next((o for o in made if o.isDerivedFrom("Fem::FemResultObject")), None)
        if result is None:
            raise SimulationError(_solver_failure(self._output))
        for obj in made:
            if not _type(obj):
                bodies.mark(obj, HELPER)  # (the result mesh: not in the analysis' group)
            bodies.hide_from_timeline(obj)
            _hide(obj)
        reactions = {}
        dat = os.path.join(self.work, self._input + ".dat")
        if os.path.isfile(dat):
            with open(dat, encoding="utf-8", errors="replace") as handle:
                printed = core.reactions_from_dat(handle.read())
            split = self._held_forces
            if split is None and self._held_error:
                warn(
                    "simulation: the reactions could not be worked out node by node (%s): "
                    "CalculiX's totals are shown" % self._held_error
                )
            for name, label in self._reactions.items():
                if split is not None:
                    # node by node: CalculiX's force at a held node is the reaction plus the
                    # loads acting right there, and a node two constraints hold is shared
                    fx, fy, fz = split.get(label, (0.0, 0.0, 0.0))
                    reactions[label] = {
                        "x": fx,
                        "y": fy,
                        "z": fz,
                        "total": (fx * fx + fy * fy + fz * fz) ** 0.5,
                    }
                elif name.upper() in printed:
                    fx, fy, fz = printed[name.upper()]
                    reactions[label] = {
                        "x": fx,
                        "y": fy,
                        "z": fz,
                        "total": (fx * fx + fy * fy + fz * fz) ** 0.5,
                    }
        self.timings["results"] = time.time() - t
        self._results_step = functools.partial(self._results_compact, result, reactions)

    def _results_compact(self, result, reactions):
        """(results, second turn) FreeCAD's renumbering of the result mesh."""
        from femresult import resulttools

        t = time.time()
        if not result.MassFlowRate:  # (as FreeCAD's import does it)
            resulttools.compact_result(result)
        self.timings["results"] = self.timings.get("results", 0.0) + time.time() - t
        self._results_step = functools.partial(self._results_finish, result, reactions)

    def _results_finish(self, result, reactions):
        """(results, last turn) the checks, the safety factor, the summary, the run linked to
        the study (or the next adaptive pass)."""
        t = time.time()
        try:
            moved = max(result.DisplacementLengths) if result.DisplacementLengths else 0.0
        except Exception:
            moved = 0.0
        size = self._model_shape.BoundBox.DiagonalLength
        if not (moved == moved) or moved > size:
            # CalculiX does not always notice a model that can still move: its numbers are
            # then nonsense (it "moved" by more than its own size)
            raise SimulationError(
                "The model is not held enough: the solve moved it by more than its own size, "
                "so a part can still move or spin freely. Add constraints so every body is held "
                "in X, Y and Z (a Fixed face is the simplest)."
            )
        plan = core.adaptive_plan(settings(self.study)["adaptive"])
        if plan is not None and self._adapt(result, plan):
            return  # (another pass, on a mesh refined where the result changes the most)
        _close_open_transaction(self.doc)
        self.timings["results"] = self.timings.get("results", 0.0) + time.time() - t
        self.summary = _finish(self.study, result, self._mesh, self._owners, self, reactions)
        _remove_run(self.study, "SimRun")
        _remove_run(self.study, "SimMeshRun")
        self.study.SimRun = self._analysis
        _save(self.study, MESH_PROP, self.mesh_info)
        apply_keep_results(self.study)
        _untouch(self.study)
        self._analysis = None  # (kept)
        self._stop("done", "Done")

    def _adapt(self, result, plan):
        """Fusion's adaptive mesh refinement, one pass: True when another solve starts on a
        mesh made finer where the result changes the most across an element, False when it
        is done (the change of the result's extreme between two passes is within the
        tolerance, or the passes are used up)."""
        passes, tolerance, portion = plan
        key = settings(self.study)["adaptive"]["result"]
        values = Results(result).values(key)
        extreme = min(values) if key == "principal_3" else max(values)
        mesh = self._mesh.FemMesh
        self.passes.append(
            {"nodes": mesh.NodeCount, "elements": mesh.VolumeCount, "value": extreme}
        )
        previous = self.passes[-2]["value"] if len(self.passes) > 1 else None
        if core.converged(previous, extreme, tolerance) or len(self.passes) >= passes:
            if self._previous_run is not None:
                _remove_objects(self.doc, list(reversed(_run_members(self._previous_run))))
                self._previous_run = None
            self.notes.append(
                "Adaptive mesh refinement: %d solves, %s %s (%s)."
                % (
                    len(self.passes),
                    core.result_title(key),
                    " -> ".join(core.fmt(p["value"]) for p in self.passes),
                    (
                        "converged within %s %%" % core.fmt(tolerance)
                        if core.converged(previous, extreme, tolerance)
                        else "not converged within %s %% after %d solves"
                        % (core.fmt(tolerance), passes)
                    ),
                )
            )
            return False
        t = time.time()
        path = os.path.join(self.work, "sizes%d.pos" % len(self.passes))
        _write_size_view(path, mesh, result, key, portion)
        self.timings["refine"] = self.timings.get("refine", 0.0) + time.time() - t
        if self._previous_run is not None:
            _remove_objects(self.doc, list(reversed(_run_members(self._previous_run))))
        self._previous_run, self._analysis = self._analysis, None
        self._pos = os.path.basename(path)
        self.stage = "model"
        self.message = "Refining the mesh (solve %d of up to %d)" % (len(self.passes) + 1, passes)
        return False if self._cancel else True

    # -- helpers
    def _background_call(self, fn, stage):
        """fn() in the background thread (Python work that needs no document)."""
        self.stage = stage
        self._run_error = None
        t = time.time()

        def work():
            try:
                fn()
            except Exception as exc:
                self._run_error = "Could not read the solver's results: %s" % exc
            finally:
                self.timings[stage + "_read"] = time.time() - t

        self._thread = threading.Thread(target=work, name="SciForge %s" % stage, daemon=True)
        self._thread.start()

    def _background(self, command, stage, env=None, before=None):
        """Run `command` in the background thread (after `before()`, Python work on files
        only, when given); poll() picks up its output."""
        self.stage = stage
        self._output, self._returncode, self._run_error = "", None, None
        t = time.time()

        def work():
            try:
                if before is not None and not self._cancel:
                    before()
                if self._cancel:  # (cancelled before the program started)
                    return
                self._process = subprocess.Popen(
                    command,
                    cwd=self.work,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    **_no_window(),
                )
                if self._cancel:  # (cancelled while it was starting: cancel() saw no process)
                    self._process.kill()
                out, _err = self._process.communicate()
                self._output = (out or b"").decode("utf-8", "replace")
                self._returncode = self._process.returncode
            except Exception as exc:
                self._run_error = "Could not run %s: %s" % (os.path.basename(command[0]), exc)
            finally:
                self._process = None
                self.timings[stage] = self.timings.get(stage, 0.0) + time.time() - t

        self._thread = threading.Thread(target=work, name="SciForge %s" % stage, daemon=True)
        self._thread.start()
        if self._cancel:  # cancelled while it was starting
            self.cancel()

    def _stop(self, state, message):
        self.state, self.message = state, message
        # FreeCAD's GmshTools holds a QProcess with a connected signal: dropped now, not when
        # Python shuts down (freecadcmd crashed in Qt at exit with a job still referenced)
        self._mesh_tools = None
        if state != "done":
            log("simulation %s: %s" % (state, message))
        # (no undo step is closed here: a cancel can come while a dialog of the person has
        # its own open, which its Cancel must still be able to undo)
        for run in (self._analysis, self._previous_run):
            if run is not None:  # a run that did not make it: nothing left behind
                try:
                    _remove_objects(self.doc, list(reversed(_run_members(run))))
                except Exception:
                    pass
        self._analysis = self._previous_run = None
        self._getter = self._results_step = None
        for doc_name, name in list(self._made):
            _LIVE_RUNS.discard((doc_name, name))
        shutil.rmtree(self.work, ignore_errors=True)
        return state


MESH_ADVICE = (
    "Thin walls need elements about as small as they are thick: try a smaller Average Element "
    "Size, or a Local Mesh Control on the thin faces; also look for tiny gaps, slivers and very "
    "short edges in the model."
)


def _stress_arrays(res_obj):
    import numpy as np

    return np.array(
        [
            res_obj.NodeStressXX,
            res_obj.NodeStressYY,
            res_obj.NodeStressZZ,
            res_obj.NodeStressXY,
            res_obj.NodeStressXZ,
            res_obj.NodeStressYZ,
        ],
        dtype=float,
    )


def _fast_stats(values):
    """simulation_core.stats with numpy, the same answer (15 results of 130 000 nodes took a
    second in plain Python)."""
    import numpy as np

    try:
        a = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return core.stats(values)
    if a.ndim != 1:
        return core.stats(values)
    ok = ~np.isnan(a)
    count = int(ok.sum())
    if not count:
        return {"min": None, "max": None, "min_index": -1, "max_index": -1, "count": 0}
    lo_i = int(np.argmin(np.where(ok, a, np.inf)))
    hi_i = int(np.argmax(np.where(ok, a, -np.inf)))
    if np.isnan(a[lo_i]) or np.isnan(a[hi_i]):  # (only infinities besides NaN)
        return core.stats(values)
    return {
        "min": float(a[lo_i]),
        "max": float(a[hi_i]),
        "min_index": lo_i,
        "max_index": hi_i,
        "count": count,
    }


def _fast_displacement_lengths(res_obj):
    """FreeCAD's resulttools.add_disp_apps, for every node at once (it called numpy once per
    node: 1.3 s for 130 000 nodes)."""
    import numpy as np

    vectors = res_obj.DisplacementVectors
    if not vectors:
        res_obj.DisplacementLengths = []
        return res_obj
    a = np.array([(v.x, v.y, v.z) for v in vectors], dtype=float)
    res_obj.DisplacementLengths = np.sqrt((a * a).sum(axis=1)).tolist()
    return res_obj


def _fast_von_mises(res_obj):
    """FreeCAD's resulttools.add_von_mises, for every node at once (the same formula)."""
    import numpy as np

    s = _stress_arrays(res_obj)
    normal, shear = s[:3], s[3:]
    pressure = normal.mean(axis=0)
    vm = np.sqrt(1.5 * ((normal - pressure) ** 2).sum(axis=0) + 3.0 * (shear**2).sum(axis=0))
    res_obj.vonMises = vm.tolist()
    return res_obj


def _fast_principal_stresses(res_obj):
    """FreeCAD's resulttools.add_principal_stress_std, for every node at once (a node with a
    NaN stress gets NaN, as there; the nonlinear material part does not apply here)."""
    import numpy as np

    s = _stress_arrays(res_obj)
    n = s.shape[1]
    bad = np.isnan(s).any(axis=0)
    s = np.where(bad, 0.0, s)
    sigma = np.empty((n, 3, 3))
    sigma[:, 0, 0], sigma[:, 1, 1], sigma[:, 2, 2] = s[0], s[1], s[2]
    sigma[:, 0, 1] = sigma[:, 1, 0] = s[3]
    sigma[:, 0, 2] = sigma[:, 2, 0] = s[4]
    sigma[:, 1, 2] = sigma[:, 2, 1] = s[5]
    eig = np.linalg.eigvalsh(sigma) if n else np.zeros((0, 3))  # ascending
    big, mid, small = eig[:, 2].copy(), eig[:, 1].copy(), eig[:, 0].copy()
    for values in (big, mid, small):
        values[bad] = np.nan
    res_obj.PrincipalMax = big.tolist()
    res_obj.PrincipalMed = mid.tolist()
    res_obj.PrincipalMin = small.tolist()
    res_obj.MaxShear = ((big - small) / 2.0).tolist()
    return res_obj


def _untouch(study):
    """What a solve changed on the study, its items and its runs needs no recompute (their
    execute does nothing): cleared, so the design does not ask for one after the solve."""
    objects = [study] + items(study)
    for link in ("SimRun", "SimMeshRun"):
        run = run_of(study, link)
        if run is not None:
            objects += _run_members(run)
    for obj in objects:
        try:
            obj.purgeTouched()
        except Exception:
            pass


class _Quiet:
    """Stands in for FreeCAD's Console in a background thread (it must not print there)."""

    def __init__(self):
        self.lines = []

    def _keep(self, text):
        self.lines.append(text)

    PrintMessage = PrintLog = PrintWarning = PrintError = _keep


def _no_window():
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW: no console flashes up
    return {}


def _last_lines(text, count=4):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " ".join(lines[-count:])


def _solver_failure(output):
    """CalculiX's complaint as a sentence a person can act on (simulation_core)."""
    return core.solver_failure(output)


def solve(study, timeout=None):
    """Solve a study and wait. Returns the result summary; raises SimulationError with a
    plain sentence when it cannot."""
    job = Job(study)
    state = job.wait(timeout)
    if state != "done":
        raise SimulationError(job.message)
    return job.summary


def generate_mesh(study, timeout=None):
    """Fusion's Generate Mesh, waiting: the mesh statistics (mesh_summary)."""
    job = Job(study, mesh_only=True)
    state = job.wait(timeout)
    if state != "done":
        raise SimulationError(job.message)
    return job.summary


def mesh_object(study):
    """The newest mesh of the study (Generate Mesh's, else the last solve's): FreeCAD's mesh
    object (its FemMesh has the nodes and elements), or None."""
    for link in ("SimMeshRun", "SimRun"):
        run = run_of(study, link)
        if run is None:
            continue
        for obj in run.Group:
            if obj.Name.startswith("SimMesh") and hasattr(obj, "FemMesh"):
                return obj
    return None


def mesh_summary(study):
    """The statistics of the newest mesh ({} without one): nodes, elements, smallest /
    largest element edge (mm), worst aspect ratio, how many elements are over the study's
    aspect ratio limit, the mesher (gmsh / netgen), its size and order, and whether it is out
    of date ("stale")."""
    data = bodies.load_meta(study, MESH_PROP)
    if data:
        data["stale"] = data.get("signature") != mesh_signature(study)
    return data


def mesh_signature(study):
    """A fingerprint of what the mesh depends on: the bodies' shapes and places, the mesh
    settings and the local mesh controls."""
    h = hashlib.sha1()
    for body in study_bodies(study):
        h.update(json.dumps(_shape_key(body)).encode())
    h.update(json.dumps(settings(study)["mesh"], sort_keys=True).encode())
    h.update(json.dumps(settings(study)["contact_tolerance"]).encode())
    for item in items(study, "mesh"):
        h.update(json.dumps(_item_key(item), sort_keys=True).encode())
    return h.hexdigest()


def _shape_key(body):
    """What of a body the results depend on: its size, its box, where its material lies
    (centre of mass) and how it is turned (its place in the design, its component's too).
    The size and the box alone missed changes that keep them: a hole moved along a plate, a
    square bar turned a quarter about its axis (its loaded top face then a side): the results
    stayed "in date"."""
    try:
        shape = bodies.global_shape(body, copy=False)
        box = shape.BoundBox
        key = [
            body.Name,
            round(shape.Volume, 4),
            round(shape.Area, 4),
            len(shape.Faces),
            round(box.XMin, 4),
            round(box.YMin, 4),
            round(box.ZMin, 4),
            round(box.XMax, 4),
            round(box.YMax, 4),
            round(box.ZMax, 4),
        ]
    except Exception:
        return [body.Name, "?"]
    try:
        # (a body's shape is often a compound, which has no centre of mass of its own)
        # (each property is worked out again at every read: read each once)
        solids = shape.Solids
        if len(solids) == 1:  # (the usual body: no volumes to weigh)
            c = solids[0].CenterOfMass
            middle = [c.x, c.y, c.z]
        else:
            parts = [(solid.CenterOfMass, solid.Volume) for solid in solids]
            total = sum(w for _c, w in parts) or 1.0
            middle = [sum(getattr(c, a) * w for c, w in parts) / total for a in "xyz"]
        if solids:
            key.append([round(c, 4) + 0.0 for c in middle])
    except Exception:
        key.append("?")
    try:
        place = body.getGlobalPlacement()
    except Exception:
        place = getattr(body, "Placement", None)
    if place is not None:
        key.append([round(v, 6) + 0.0 for v in place.toMatrix().A])
    return key


# -- results ---------------------------------------------------------------------------------------
class Results:
    """The results of a study's last solve, node by node (lists in the same order as
    `node_ids`): coordinates, displacement vectors, every stress, the safety factor."""

    def __init__(self, result):
        self.result = result
        self.node_ids = list(result.NodeNumbers)
        mesh = result.Mesh.FemMesh if result.Mesh is not None else None
        nodes = mesh.Nodes if mesh is not None else {}
        self.points = [nodes.get(n) for n in self.node_ids]
        self.mesh = mesh

    def values(self, key):
        r = self.result
        if key == "von_mises":
            return list(r.vonMises)
        if key == "principal_1":
            return list(r.PrincipalMax)
        if key == "principal_3":
            return list(r.PrincipalMin)
        if key in ("sxx", "syy", "szz", "sxy", "syz", "szx"):
            name = {"sxx": "XX", "syy": "YY", "szz": "ZZ", "sxy": "XY", "syz": "YZ", "szx": "XZ"}[
                key
            ]
            return list(getattr(r, "NodeStress" + name))
        if key == "displacement":
            return list(r.DisplacementLengths)
        if key in ("dx", "dy", "dz"):
            index = "xyz".index(key[1])
            return [v[index] for v in r.DisplacementVectors]
        if key == "safety":
            return list(r.UserDefined)
        if key == "strain":
            return _equivalent_strain(r)
        raise SimulationError("Unknown result %r." % key)

    def displacements(self):
        return list(self.result.DisplacementVectors)


def _equivalent_strain(r):
    out = []
    for exx, eyy, ezz, exy, eyz, exz in zip(
        r.NodeStrainXX,
        r.NodeStrainYY,
        r.NodeStrainZZ,
        r.NodeStrainXY,
        r.NodeStrainYZ,
        r.NodeStrainXZ,
    ):
        # von Mises equivalent strain (engineering shear strains from CalculiX's tensor)
        a = (exx - eyy) ** 2 + (eyy - ezz) ** 2 + (ezz - exx) ** 2
        b = 6.0 * (exy**2 + eyz**2 + exz**2)
        out.append((2.0 / 3.0) * ((a + b) / 2.0) ** 0.5)
    return out


def result_object(study):
    run = run_of(study)
    if run is None:
        return None
    for obj in run.Group:
        if obj.isDerivedFrom("Fem::FemResultObject"):
            return obj
    return None


def results(study):
    """The Results of the study's last solve, or None when it has not been solved (or its
    results were not kept in the file: results_dropped())."""
    obj = result_object(study)
    return Results(obj) if obj is not None and _has_data(obj) else None


def _has_data(result):
    try:
        mesh = result.Mesh.FemMesh if result.Mesh is not None else None
        return len(result.NodeNumbers) > 1 and mesh is not None and mesh.NodeCount > 0
    except Exception:
        return False


def results_dropped(study):
    """True when the study was solved but its coloured results are not here: the design was
    saved with Keep results in the file off (its numbers, summary(), are kept). Solve again
    to see them."""
    if not summary(study):
        return False
    obj = result_object(study)
    return obj is None or not _has_data(obj)


# What a solve adds to the design file: the meshes and the results (about 10 MB for 25 000
# nodes). With the study setting keep_results off they are left out of the file (FreeCAD's
# Transient status: the objects stay, empty after reopening; the summary's numbers stay).
def _heavy_properties(obj):
    out = []
    for prop in obj.PropertiesList:
        try:
            kind = obj.getTypeIdOfProperty(prop)
        except Exception:
            continue
        if prop in ("FemMesh", "Data"):
            out.append(prop)
        elif obj.isDerivedFrom("Fem::FemResultObject") and (
            "FloatList" in kind or "VectorList" in kind or "IntegerList" in kind
        ):
            out.append(prop)
    return out


def apply_keep_results(study):
    """Mark the study's meshes and results as saved or not saved with the design, as its
    keep_results setting says."""
    keep = bool(settings(study)["keep_results"])
    for link in ("SimRun", "SimMeshRun"):
        run = run_of(study, link)
        if run is None:
            continue
        for obj in _run_members(run):
            for prop in _heavy_properties(obj):
                try:
                    obj.setPropertyStatus(prop, "-Transient" if keep else "Transient")
                except Exception:
                    pass


def summary(study):
    """The summary of the last solve ({} when the study was never solved)."""
    return bodies.load_meta(study, RESULT_PROP)


def signature(study):
    """A fingerprint of everything a solve depends on: the bodies' shapes and places, the
    study's settings and materials, and its items. A study whose fingerprint differs from the
    one saved at its last solve is out of date."""
    h = hashlib.sha1()
    for body in study_bodies(study):
        h.update(json.dumps(_shape_key(body)).encode())
        name, props, _source = study_material(study, body)
        h.update(json.dumps([name, props], sort_keys=True, default=str).encode())
    data = dict(study_data(study))
    # (whether the results are kept in the file changes nothing they say)
    data["settings"] = {k: v for k, v in data["settings"].items() if k != "keep_results"}
    h.update(json.dumps(data, sort_keys=True).encode())
    for item in items(study):
        h.update(json.dumps(_item_key(item), sort_keys=True).encode())
    return h.hexdigest()


def _item_key(item):
    """What of an item a solve depends on (its kind, options, picks; not the shapes its picks
    remember, which are refreshed at every solve)."""
    data = {k: v for k, v in item_data(item).items() if k != "sigs"}
    refs = [(o.Name, s) for o, s in _picks(item.References)]
    return [data, refs, bool(item.Suppressed)]


def out_of_date(study):
    done = summary(study)
    return bool(done) and done.get("signature") != signature(study)


def body_key(study, body):
    """The key of `body` in the result summary's "bodies": its label, with its component's
    label (or its name) added when another body of the study has the same label (two
    components' "Body1")."""
    return _body_keys(study_bodies(study)).get(body.Name, body.Label)


def _body_keys(found):
    """{body name: summary key} for the bodies `found` (see body_key)."""
    unique = []
    for b in found:
        if b not in unique:
            unique.append(b)
    count = {}
    for b in unique:
        count[b.Label] = count.get(b.Label, 0) + 1
    out = {}
    for b in unique:
        if count[b.Label] == 1:
            out[b.Name] = b.Label
            continue
        try:
            parent = b.getParentGeoFeatureGroup()
        except Exception:
            parent = None
        out[b.Name] = "%s (%s)" % (b.Label, parent.Label if parent is not None else b.Name)
    seen = {}
    for name, key in out.items():
        seen.setdefault(key, []).append(name)
    for key, names in seen.items():
        if len(names) > 1:  # (the same label in components of the same label)
            for name in names:
                out[name] = "%s (%s)" % (key, name)
    return out


def _finish(study, result, mesh_obj, owners, job, reactions=None):
    """Safety factors into the result, and the study's result summary."""
    data = study_data(study)
    basis = data["settings"]["safety_basis"]
    mesh = mesh_obj.FemMesh
    model = mesh_obj.Shape.Shape if mesh_obj.Shape is not None else None
    node_ids = list(result.NodeNumbers)
    position = {n: i for i, n in enumerate(node_ids)}
    strengths = [None] * len(node_ids)
    per_body = {}
    grouped = getattr(job, "_solid_nodes", None) or {}
    keys = _body_keys(owners)
    if model is not None:
        for index, (solid, body) in enumerate(zip(model.Solids, owners)):
            name, props, _source = study_material(study, body)
            s = core.strength(props, basis)
            nodes = grouped.get(index + 1)
            if nodes is None:
                if len(owners) == 1:
                    nodes = list(mesh.Nodes)  # (one body: every node is its)
                else:
                    try:
                        nodes = mesh.getNodesBySolid(solid)
                    except Exception:
                        nodes = []
            key = keys.get(body.Name, body.Label)
            per_body.setdefault(
                key, {"nodes": set(), "strength": s, "material": name, "name": body.Name}
            )
            per_body[key]["nodes"].update(nodes)
            for n in nodes:
                i = position.get(n)
                if i is None:
                    continue
                if s is not None and (strengths[i] is None or s < strengths[i]):
                    strengths[i] = s
    vm = list(result.vonMises)
    lengths = list(result.DisplacementLengths)  # (read once: each read copies every value)
    # Fusion: yield strength / von Mises, or ultimate tensile strength / 1st principal stress
    # (in compression the 3rd when it is the larger in size: simulation_core.ultimate_stresses)
    if basis == "yield":
        divided = vm
    else:
        divided = core.ultimate_stresses(list(result.PrincipalMax), list(result.PrincipalMin))
    safety = []
    for s, v in zip(strengths, divided):
        if s is None:
            safety.append(float("nan"))
        else:
            safety.append(core.safety_factors([v], s, core.SAFETY_CAP)[0])
    result.UserDefined = safety
    stats = {}
    res = Results(result)
    for key, _title, _unit in core.RESULTS:
        try:
            values = res.values(key)
        except Exception:
            continue
        st = _fast_stats(values)
        if st["count"]:
            st["min_at"] = _point(res.points, st["min_index"])
            st["max_at"] = _point(res.points, st["max_index"])
            stats[key] = st
    bodies_out = {}
    for label, entry in per_body.items():
        idx = [position[n] for n in entry["nodes"] if n in position]
        if not idx:
            continue
        sf = [safety[i] for i in idx if safety[i] == safety[i]]
        bodies_out[label] = {
            "name": entry["name"],
            "material": entry["material"],
            "von_mises_max": max(vm[i] for i in idx),
            "displacement_max": max(lengths[i] for i in idx),
            "safety_min": min(sf) if sf else None,
        }
    out = {
        "solved": time.strftime("%Y-%m-%d %H:%M:%S"),
        # (taken when the solve started: a design changed while it ran is out of date)
        "signature": (
            job._fingerprints[0] if getattr(job, "_fingerprints", None) else signature(study)
        ),
        "mesh": {
            "nodes": mesh.NodeCount,
            "elements": mesh.VolumeCount,
            "size": (
                _global_size(study, mesh_obj.Shape.Shape) if mesh_obj.Shape is not None else None
            ),
            "order": data["settings"]["mesh"]["order"],
        },
        "stats": stats,
        "bodies": bodies_out,
        "safety_basis": basis,
        "reactions": reactions or {},
        "notes": list(job.notes),
        "results_kept": bool(data["settings"]["keep_results"]),
        "adaptive": (
            {
                "result": data["settings"]["adaptive"]["result"],
                "passes": list(job.passes),
            }
            if job.passes
            else None
        ),
        "seconds": round(time.time() - job.started, 2),
        "timings": {k: round(v, 3) for k, v in job.timings.items()},
    }
    if job.mesh_info:
        out["mesh"].update(
            {
                k: job.mesh_info.get(k)
                for k in ("smallest", "largest", "worst_aspect", "over_limit", "mesher")
            }
        )
    _save(study, RESULT_PROP, out)
    log(
        "simulation %s solved: %d nodes, max von Mises %s MPa, max displacement %s mm"
        % (
            study.Label,
            mesh.NodeCount,
            core.fmt(stats.get("von_mises", {}).get("max")),
            core.fmt(stats.get("displacement", {}).get("max")),
        )
    )
    return out


def _point(points, index):
    try:
        p = points[index]
        return [round(p.x, 4), round(p.y, 4), round(p.z, 4)]
    except Exception:
        return None

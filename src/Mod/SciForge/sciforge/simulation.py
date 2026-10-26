# SPDX-License-Identifier: LGPL-2.1-or-later
"""Simulation studies in a design (Fusion's Simulation workspace, Static Stress), the document
side: no Qt. The rules (settings, kinds, units, safety factor, colours, pre-check) are in
simulation_core.py; the dialogs in simulation_ui.py; the results display in
simulation_results_ui.py. Spec: docs/sciforge/parity/simulation.md.

How a study is kept (saved with the design, never a timeline step, never in the browser's
design folders):

- A **study** is an App::FeaturePython (SciForgeType "SimStudy", proxy StudyProxy) holding its
  type, settings and study materials as JSON (`SciForgeSimStudy`), the bodies it simulates
  (`SimBodies`; empty = every solid body shown when it solves), and a summary of its last
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
    Stress"; `study_bodies` (default: every solid body shown when it solves)."""
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
    return copy


def _save(obj, prop, data):
    bodies.save_meta(obj, prop, data)


def study_bodies(study):
    """The solid bodies the study simulates, in the design's order."""
    doc = study.Document
    chosen = [b for b in (getattr(study, "SimBodies", None) or []) if bodies.has_solid(b)]
    if chosen:
        return sorted(chosen, key=lambda b: b.ID)
    return bodies.solid_bodies(doc, visible_only=True)


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
    _save(obj, ITEM_PROP, {"category": category, "kind": kind, "options": opts})
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
    data["options"] = new_opts
    _save(item, ITEM_PROP, data)
    if suppressed is not None:
        item.Suppressed = bool(suppressed)
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
        if sub and sub not in grouped[obj.Name][1]:
            grouped[obj.Name][1].append(sub)
    return [(grouped[n][0], grouped[n][1]) for n in order]


def lost_items(study):
    """Items whose picks are gone (deleted geometry): the pre-check refuses them."""
    lost = []
    for item in items(study):
        if item.Suppressed:
            continue
        picks = _picks(item.References)
        if not picks:
            lost.append(item)
            continue
        for obj, sub in picks:
            try:
                if not bodies.alive(obj):
                    lost.append(item)
                    break
                if not sub:  # a whole body (a local mesh control)
                    if not bodies.has_solid(obj):
                        lost.append(item)
                        break
                    continue
                element = bodies.global_shape(obj, copy=False).getElement(sub.split(".")[-1])
                if element is None or element.isNull():
                    lost.append(item)
                    break
            except Exception:
                lost.append(item)
                break
    return lost


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
def _gap(a, b, tol):
    """The distance between two shapes, or None when their boxes are farther apart than
    `tol` (the cheap test first)."""
    box = a.BoundBox
    box.enlarge(tol)
    if not box.intersect(b.BoundBox):
        return None
    try:
        return a.distToShape(b)[0]
    except Exception:
        return None


def contacts(study):
    """Fusion's automatic contacts: [(body, body, "bonded")] of the study's bodies that touch
    or are closer than the contact tolerance (they are glued when the study solves)."""
    tol = float(settings(study)["contact_tolerance"])
    found = study_bodies(study)
    shapes = [(b, bodies.global_shape(b, copy=False)) for b in found]
    out = []
    for i, (a, sa) in enumerate(shapes):
        for b, sb in shapes[i + 1 :]:
            gap = _gap(sa, sb, tol)
            if gap is not None and gap <= tol + 1e-9:
                out.append((a, b, "bonded"))
    return out


def overlaps(study):
    """[(body, body, volume mm3)] of the study's bodies that overlap."""
    found = study_bodies(study)
    shapes = [(b, bodies.global_shape(b, copy=False)) for b in found]
    out = []
    for i, (a, sa) in enumerate(shapes):
        for b, sb in shapes[i + 1 :]:
            if not sa.BoundBox.intersect(sb.BoundBox):
                continue
            try:
                volume = sa.common(sb).Volume
            except Exception:
                continue
            if volume > 1e-6 * max(1.0, min(sa.Volume, sb.Volume)):
                out.append((a, b, volume))
    return out


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
    if len(found) > 1:
        try:
            touching = contacts(study)
            summary["overlaps"] = [(a.Label, b.Label, v) for a, b, v in overlaps(study)]
        except Exception as exc:
            warn("simulation pre-check: %s" % exc)
            touching = []
    else:
        touching = []
    if found and any(not c[2] for c in summary["constraints"]):
        summary["loose"] = [b.Label for b in loose_bodies(study, touching)]
    checks = core.precheck(summary)
    for label in summary.get("unbuilt", []):
        checks.append(("error", "%s is not in SciForge yet: suppress or delete it." % label))
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
        fused, _history = first.generalFuse(rest, tol)
    except Exception as exc:
        raise SimulationError("The bodies could not be joined for the mesh: %s" % exc)
    solids = list(fused.Solids)
    owners = []
    for solid in solids:
        centre = solid.CenterOfMass
        owner = None
        for body, piece in pieces:
            try:
                if piece.isInside(centre, 1e-6, True):
                    owner = body
                    break
            except Exception:
                continue
        if owner is None:  # a thin piece whose centre falls outside: the nearest body
            owner = min(pieces, key=lambda p: p[1].distToShape(Part.Vertex(centre))[0])[0]
        owners.append(owner)
    return Part.makeCompound(solids), owners


def _element(obj, sub):
    return bodies.global_shape(obj, copy=False).getElement(sub.split(".")[-1])


def _model_element(model, sub):
    """A sub-element of the model shape by name, solids too ("Solid2")."""
    if sub.startswith("Solid"):
        return model.Solids[int(sub[5:]) - 1]
    return model.getElement(sub)


def _probe_points(face):
    """A few points inside a face: points at chosen spots of its parameter range that lie on
    the face (not in a hole of it), else its centre of mass."""
    pts = []
    try:
        u0, u1, v0, v1 = face.ParameterRange
        for fu, fv in ((0.5, 0.5), (0.31, 0.43), (0.69, 0.57), (0.43, 0.69), (0.57, 0.31)):
            u, v = u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv
            if face.isPartOfDomain(u, v):
                pts.append(face.valueAt(u, v))
            if len(pts) >= 3:
                break
    except Exception:
        pass
    if not pts:
        pts.append(face.CenterOfMass)
    return pts


def map_picks(item, model, owners=None):
    """The model's sub-elements ("Face12", "Edge3", "Vertex5", "Solid2") that lie on the
    item's picks (a whole-body pick: the model solids that body owns)."""
    import Part

    names = []
    for obj, sub in _picks(item.References):
        if not sub:
            body = obj if bodies.is_body(obj) else bodies.body_of(obj)
            for i, owner in enumerate(owners or [], 1):
                if owner is obj or owner is body:
                    names.append("Solid%d" % i)
            continue
        try:
            element = _element(obj, sub)
        except Exception:
            continue
        if element is None or element.isNull():
            continue
        kind = _element_kind(sub)
        box = element.BoundBox
        box.enlarge(GEOMETRY_TOL * 10)
        if kind == "faces":
            for i, face in enumerate(model.Faces, 1):
                if not box.intersect(face.BoundBox):
                    continue
                ok = True
                for p in _probe_points(face):
                    if element.distToShape(Part.Vertex(p))[0] > GEOMETRY_TOL:
                        ok = False
                        break
                if ok:
                    names.append("Face%d" % i)
        elif kind == "edges":
            for i, edge in enumerate(model.Edges, 1):
                if not box.intersect(edge.BoundBox):
                    continue
                mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
                ends = [v.Point for v in edge.Vertexes]
                if all(
                    element.distToShape(Part.Vertex(p))[0] <= GEOMETRY_TOL for p in [mid] + ends
                ):
                    names.append("Edge%d" % i)
        elif kind == "vertices":
            for i, vertex in enumerate(model.Vertexes, 1):
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
        for item in items(study, "mesh" if mesh_only else None):
            if item.Suppressed:
                continue
            found = map_picks(item, model_shape, owners)
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
            mesh.CoherenceMesh = True
        if straight and "SecondOrderLinear" in mesh.PropertiesList:
            mesh.SecondOrderLinear = True
        elif opts["mesh"]["order"] == "parabolic" and opts["mesh"]["curved"]:
            # curved elements whose mid-side nodes are moved onto a hole's wall can turn
            # inside out where the elements are large: Gmsh straightens them as needed
            if "HighOrderOptimize" in mesh.PropertiesList:
                mesh.HighOrderOptimize = "Optimization"
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
    """The mesh's nodes and the lookups the solver cards need, made once per solve."""

    def __init__(self, femmesh):
        from femmesh import meshtools

        self.femmesh = femmesh
        self.nodes = femmesh.Nodes
        self._elements = None
        self._meshtools = meshtools

    @property
    def elements(self):
        if self._elements is None:
            self._elements = self._meshtools.get_femelement_table(self.femmesh)
        return self._elements

    def nodes_of(self, model, sub):
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

    def face_weights(self, face):
        """{node: area share} of a model face (FreeCAD's consistent shares for a uniform
        load: on a 6-node triangle the corners get 0, the mid-side nodes a third each)."""
        mt = self._meshtools
        table = mt.get_ref_facenodes_table(self.femmesh, self.elements, face)
        if not table:
            return {}
        return mt.get_ref_shape_node_sum_geom_table(mt.get_ref_facenodes_areas(self.nodes, table))

    def edge_weights(self, edge):
        mt = self._meshtools
        table = mt.get_ref_edgenodes_table(self.femmesh, self.elements, edge)
        if not table:
            return {}
        return mt.get_ref_shape_node_sum_geom_table(mt.get_ref_edgenodes_lengths(self.nodes, table))

    def point(self, node):
        p = self.nodes[node]
        return (p.x, p.y, p.z)


def _face_normal_at(face, point):
    """The outward normal of a face at (near) a point."""
    try:
        u, v = face.Surface.parameter(App.Vector(*point))
        n = face.normalAt(u, v)
        return (n.x, n.y, n.z)
    except Exception:
        n = face.normalAt(*_middle_uv(face))
        return (n.x, n.y, n.z)


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
        face = _model_element(model, sub)
        for node, w in mesh.face_weights(face).items():
            weights[node] = weights.get(node, 0.0) + w
            owner.setdefault(node, sub)
    if not faces:
        for sub in edges:
            for node, w in mesh.edge_weights(_model_element(model, sub)).items():
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
        groups = []  # (direction, {node: weight}, share of the total)
        if opts.get("direction") == "normal":
            if not faces:
                raise SimulationError(
                    "%s: a force along the normal needs faces; pick faces or give a direction."
                    % item.Label
                )
            areas = [_model_element(model, s).Area for s in faces]
            total = sum(areas) or 1.0
            for sub, area in zip(faces, areas):
                face = _model_element(model, sub)
                n = face.normalAt(*_middle_uv(face))
                # a positive force pushes into the face (against its outward normal)
                direction = (-n.x, -n.y, -n.z)
                weights, _owner = _weights_on(mesh, model, [sub])
                share = 1.0 if opts.get("per_entity") else area / total
                groups.append((direction, weights, share))
        else:
            direction = core.unit_vector(opts.get("vector") or [0, 0, -1])
            picks = faces or edges
            if picks:
                if opts.get("per_entity"):
                    for sub in picks:
                        weights, _owner = _weights_on(mesh, model, [sub])
                        groups.append((direction, weights, 1.0))
                else:
                    weights, _owner = _weights_on(mesh, model, picks)
                    groups.append((direction, weights, 1.0))
            if vertices:
                count = len(vertices)
                for sub in vertices:
                    weights = {n: 1.0 for n in mesh.nodes_of(model, sub)}
                    share = 1.0 if opts.get("per_entity") else 1.0 / count
                    groups.append((direction, weights, share))
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
        sets = [[s] for s in faces] if opts.get("per_entity") else [faces]
        for group in sets:
            weights, _owner = _weights_on(mesh, model, group)
            nodes = sorted(weights)
            if not nodes:
                continue
            if opts.get("direction") == "normal":
                face = _model_element(model, group[0])
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
            nodes.update(mesh.femmesh.getNodesBySolid(solids[i]))
        if nodes & held_nodes:
            continue
        rows += core.three_two_one([(n, mesh.point(n)) for n in sorted(nodes)])
    return rows


def _solver_cards(study, model, femmesh, subs):
    """The constraints, loads and reaction outputs SciForge writes into CalculiX's input:
    {"model": lines before *STEP, "step": lines inside the step, "reactions": {set name: item
    label}, "notes": [sentences]}."""
    mesh = _MeshData(femmesh)
    rows, reactions, notes = [], {}, []
    held = set()
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
    return {
        "model": model_lines,
        "step": step_lines,
        "reactions": reactions,
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


# -- the mesh: Gmsh's size fields, Netgen when Gmsh fails, statistics ------------------------------
def _size_fields(study, model, owners, subs, global_size):
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
    if not finals:
        return []
    n += 1
    lines += [
        "Field[%d] = Min;" % n,
        "Field[%d].FieldsList = {%s};" % (n, ", ".join(str(f) for f in finals)),
        "Background Field = %d;" % n,
    ]
    return ["// SciForge: local mesh controls"] + lines + [""]


def _write_fields(geo_path, lines):
    if not lines:
        return
    with open(geo_path, encoding="utf-8") as handle:
        text = handle.read()
    marker = "// optimize the mesh"
    if marker not in text:
        marker = "Mesh  3;"
    text = text.replace(marker, "\n".join(lines) + "\n" + marker, 1)
    with open(geo_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _gmsh_problem(output, model, owners):
    """A sentence about what Gmsh could not mesh, naming the bodies of the surfaces it
    reported (Gmsh numbers the model's faces in order)."""
    import re

    errors = [line.strip() for line in (output or "").splitlines() if "Error" in line]
    numbers = []
    for line in errors:
        for match in re.finditer(r"[Ss]urface[s]?\s+(\d+)", line):
            numbers.append(int(match.group(1)))
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


def _mesh_stats(femmesh, limit):
    """{"nodes", "elements", "smallest", "largest", "worst_aspect", "over_limit", "sampled"}
    of a volume mesh (element edge lengths and aspect ratios from the corner nodes; a big
    mesh is measured on an even sample of its elements)."""
    nodes = femmesh.Nodes
    volumes = list(femmesh.Volumes)
    step = max(1, len(volumes) // 40000)
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
    for folder in ("bin", ""):
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
        self._netgen_out = None
        self._gmsh_problem = None
        self._straight = False  # mesh again with straight-sided elements (bad curved ones)

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
                self._after_background()
                return self.state
            if self._cancel:
                return self._stop("cancelled", "Cancelled.")
            getattr(self, "_stage_" + self.stage)()
        except SimulationError as exc:
            return self._stop("failed", str(exc))
        except Exception as exc:
            warn("simulation: %s" % exc)
            return self._stop("failed", "The solve failed: %s" % exc)
        return self.state

    def wait(self, timeout=None):
        """Run to the end on this thread (scripts, tests, the AI)."""
        end = None if timeout is None else time.time() + timeout
        while self.poll() == "running":
            if end is not None and time.time() > end:
                self.cancel()
                self.poll()
                return self._stop("failed", "The solve took longer than %d s." % timeout)
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
        t = time.time()
        shape, self._owners = build_model(self.study)
        self._model_shape = shape
        self._analysis, self._model, self._mesh, self._subs = _make_run(
            self.study, shape, self._owners, self.mesh_only, self._straight
        )
        self.timings["model"] = time.time() - t
        self.stage, self.message = "mesh", "Meshing"
        self._start_mesh()

    def _start_mesh(self):
        from femmesh.gmshtools import GmshTools

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
        size = _global_size(self.study, self._model_shape)
        _write_fields(
            tools.temp_file_geo,
            _size_fields(self.study, self._model_shape, self._owners, self._subs, size),
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
                    size=float(size),
                    smallest=float(smallest),
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
            self.stage, self.message = "results", "Reading the results"
            self._stage_results()

    def _after_mesh(self):
        t = time.time()
        if self.mesher == "gmsh":
            tools = self._mesh_tools
            made = os.path.isfile(tools.temp_file_mesh) and os.path.getsize(tools.temp_file_mesh)
            failed = not made or any(
                line.lstrip().startswith("Error") for line in self._output.splitlines()
            )
            if failed:
                self._gmsh_problem = _gmsh_problem(self._output, self._model_shape, self._owners)
                self._start_netgen()
                return
            tools.read_and_set_new_mesh()
        else:
            if not (self._netgen_out and os.path.isfile(self._netgen_out)):
                raise SimulationError(
                    "%s Netgen could not mesh it either. %s"
                    % (self._gmsh_problem or "The mesh could not be made.", MESH_ADVICE)
                )
            import Fem

            self._mesh.FemMesh = Fem.read(self._netgen_out)
            self.notes.append(
                "Gmsh could not mesh the model, so Netgen made the mesh (%s)."
                % (self._gmsh_problem or "")
            )
        # FreeCAD 1.1's Gmsh run names a group after every solid, face and edge; with any
        # group in the mesh, the solver input looks for groups named after the materials,
        # finds none and reports an error before searching the mesh itself. SciForge does
        # not use the groups: drop them, so the search runs straight away.
        mesh = self._mesh.FemMesh
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
                "size": _global_size(self.study, self._model_shape),
                "order": settings(self.study)["mesh"]["order"],
                "signature": mesh_signature(self.study),
                "made": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self.timings["mesh_stats"] = time.time() - t
        if self.mesh_only:
            _close_open_transaction(self.doc)
            _remove_run(self.study, "SimMeshRun")
            self.study.SimMeshRun = self._analysis
            _save(self.study, MESH_PROP, self.mesh_info)
            self.summary = dict(self.mesh_info)
            self._analysis = None  # (kept)
            return self._stop("done", "Done")
        self.stage, self.message = "input", "Writing the solver input"
        self._stage_input()

    def _stage_input(self):
        t = time.time()
        from femmesh import meshsetsgetter
        from femsolver.calculix import writer
        from femtools import membertools

        solver = next(o for o in self._analysis.Group if o.Name.startswith("SimSolver"))
        getter = meshsetsgetter.MeshSetsGetter(
            self._analysis, solver, self._mesh, membertools.AnalysisMember(self._analysis)
        )
        getter.get_mesh_sets()
        w = writer.FemInputWriterCcx(
            self._analysis, solver, self._mesh, getter.member, self.work, getter.mat_geo_sets
        )
        path = w.write_solver_input()
        if not path or not os.path.isfile(path):
            raise SimulationError("The solver input could not be written.")
        cards = _solver_cards(self.study, self._model_shape, self._mesh.FemMesh, self._subs)
        _inject(path, cards)
        self._reactions = cards["reactions"]
        self.notes += cards["notes"]
        self._input = os.path.splitext(os.path.basename(path))[0]
        self.timings["input"] = time.time() - t
        self.stage, self.message = "solve", "Solving"
        env = dict(os.environ)
        if not env.get("OMP_NUM_THREADS"):
            env["OMP_NUM_THREADS"] = str(max(1, (os.cpu_count() or 2) - 1))
        self._background([_binary("ccx"), "-i", self._input], "solve", env=env)

    def _stage_results(self):
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
        importCcxFrdResults.importFrd(frd, self._analysis, "Sim")
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
            for name, label in self._reactions.items():
                if name.upper() in printed:
                    fx, fy, fz = printed[name.upper()]
                    reactions[label] = {
                        "x": fx,
                        "y": fy,
                        "z": fz,
                        "total": (fx * fx + fy * fy + fz * fz) ** 0.5,
                    }
        self.timings["results"] = time.time() - t
        _close_open_transaction(self.doc)
        self.summary = _finish(self.study, result, self._mesh, self._owners, self, reactions)
        _remove_run(self.study, "SimRun")
        _remove_run(self.study, "SimMeshRun")
        self.study.SimRun = self._analysis
        _save(self.study, MESH_PROP, self.mesh_info)
        self._analysis = None  # (kept)
        self._stop("done", "Done")

    # -- helpers
    def _background(self, command, stage, env=None):
        self.stage = stage
        self._output, self._returncode, self._run_error = "", None, None
        t = time.time()

        def work():
            try:
                self._process = subprocess.Popen(
                    command,
                    cwd=self.work,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    **_no_window(),
                )
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
        if state != "done":
            log("simulation %s: %s" % (state, message))
        if self._analysis is not None:  # a run that did not make it: nothing left behind
            try:
                _remove_objects(self.doc, list(reversed(_run_members(self._analysis))))
            except Exception:
                pass
            self._analysis = None
        shutil.rmtree(self.work, ignore_errors=True)
        return state


MESH_ADVICE = (
    "Try a larger Average Element Size in the mesh settings, or look for tiny gaps, slivers "
    "and very short edges in the model."
)


def _no_window():
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW: no console flashes up
    return {}


def _last_lines(text, count=4):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " ".join(lines[-count:])


def _solver_failure(output):
    """CalculiX's complaint as a sentence a person can act on."""
    text = (output or "").lower()
    if "zero pivot" in text or "singular" in text or "numerically singular" in text:
        return (
            "The model is not held enough: a part can still move or spin freely. Add constraints "
            "so every body is held in X, Y and Z (a Fixed face is the simplest), or switch on "
            "Remove rigid body modes if the loads balance each other."
        )
    if "nonpositive jacobian" in text or "negative jacobian" in text:
        return "The mesh has distorted elements: make the Average Element Size smaller."
    if (
        "dependent dof" in text
        or "is used as dependent" in text
        or "mpc" in text
        and "error" in text
    ):
        return (
            "Two constraints hold the same corner or edge in ways that cannot both be true: "
            "suppress one of them, or move one to a different face."
        )
    if "not enough memory" in text or "allocation" in text and "fail" in text:
        return (
            "The computer ran out of memory for this mesh: make the Average Element Size "
            "larger, or use local mesh controls only where the stress matters."
        )
    if "material" in text and ("not defined" in text or "no elastic" in text):
        return "A body has no usable material: check the study materials."
    return "CalculiX could not solve the study. %s" % _last_lines(output)


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
        refs = [(o.Name, s) for o, s in _picks(item.References)]
        h.update(
            json.dumps([item_data(item), refs, bool(item.Suppressed)], sort_keys=True).encode()
        )
    return h.hexdigest()


def _shape_key(body):
    try:
        shape = bodies.global_shape(body, copy=False)
        box = shape.BoundBox
        return [
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
    """The Results of the study's last solve, or None when it has not been solved."""
    obj = result_object(study)
    return Results(obj) if obj is not None else None


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
    h.update(json.dumps(study_data(study), sort_keys=True).encode())
    for item in items(study):
        refs = [(o.Name, s) for o, s in _picks(item.References)]
        h.update(
            json.dumps([item_data(item), refs, bool(item.Suppressed)], sort_keys=True).encode()
        )
    return h.hexdigest()


def out_of_date(study):
    done = summary(study)
    return bool(done) and done.get("signature") != signature(study)


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
    if model is not None:
        for index, (solid, body) in enumerate(zip(model.Solids, owners)):
            name, props, _source = study_material(study, body)
            s = core.strength(props, basis)
            try:
                nodes = mesh.getNodesBySolid(solid)
            except Exception:
                nodes = []
            per_body.setdefault(body.Label, {"nodes": set(), "strength": s, "material": name})
            per_body[body.Label]["nodes"].update(nodes)
            for n in nodes:
                i = position.get(n)
                if i is None:
                    continue
                if s is not None and (strengths[i] is None or s < strengths[i]):
                    strengths[i] = s
    vm = list(result.vonMises)
    # Fusion: yield strength / von Mises, or ultimate tensile strength / 1st principal stress
    divided = vm if basis == "yield" else list(result.PrincipalMax)
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
        st = core.stats(values)
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
            "material": entry["material"],
            "von_mises_max": max(vm[i] for i in idx),
            "displacement_max": max(result.DisplacementLengths[i] for i in idx),
            "safety_min": min(sf) if sf else None,
        }
    out = {
        "solved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signature": signature(study),
        "mesh": {
            "nodes": mesh.NodeCount,
            "elements": mesh.VolumeCount,
            "size": (
                core.element_size(_bbox(mesh_obj.Shape.Shape), data["settings"]["mesh"]["size_pct"])
                if mesh_obj.Shape is not None
                else None
            ),
            "order": data["settings"]["mesh"]["order"],
        },
        "stats": stats,
        "bodies": bodies_out,
        "safety_basis": basis,
        "reactions": reactions or {},
        "notes": list(job.notes),
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

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
  design coordinates; touching bodies are split where they meet so the mesh is shared and they
  are glued, Fusion's bonded contacts), FreeCAD's Gmsh mesh, CalculiX solver, materials and
  constraints made from the study's items (picks found again on the model by their geometry),
  and the results CalculiX gives back (a Fem::FemResultObject; the safety factor at every node
  is kept in its UserDefined list). A new solve replaces the run.

Solving: `solve(study)` does everything and waits (scripts, the AI, tests); `Job(study)` does
the same in stages so a dialog stays responsive: model, mesh, input, solver and results, with
the slow programs (Gmsh, CalculiX) in a background thread and everything that touches the
document on the caller's thread (`Job.poll()` from a timer), and `Job.cancel()`.
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
        bodies.add_prop(obj, "App::PropertyLinkListHidden", "SimBodies", "SciForge")
        bodies.add_prop(obj, "App::PropertyLinkHidden", "SimRun", "SciForge")

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
    while any(label.startswith("%s %d" % (stem, n)) for label in taken):
        n += 1
    return n


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
    doc.removeObject(study.Name)


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
    number = _label_number([i.Label for i in items(study) if i is not obj], info["title"])
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


# -- pre-check -------------------------------------------------------------------------------------
def precheck(study):
    """[(level, sentence)] of simulation_core.precheck for this study as it is now."""
    data = study_data(study)
    found = study_bodies(study)
    summary = {
        "bodies": [b.Label for b in found],
        "materials": {},
        "constraints": [],
        "loads": [],
        "gravity": bool(data["settings"]["gravity"]["on"]),
        "safety_basis": data["settings"]["safety_basis"],
        "lost": [i.Label for i in lost_items(study)],
    }
    for body in found:
        name, props, _source = study_material(study, body)
        summary["materials"][body.Label] = (name, props)
    for item in items(study):
        d = item_data(item)
        row = (d["kind"], len(_picks(item.References)), bool(item.Suppressed))
        summary["constraints" if d["category"] == "constraint" else "loads"].append(row)
        if not item.Suppressed and not core.kind_info(d["category"], d["kind"]).get("built"):
            summary.setdefault("unbuilt", []).append(item.Label)
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
    Several solids are split where they touch (FreeCAD's general fuse), so the mesh is shared
    there and they are glued (Fusion's bonded contacts)."""
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


def map_picks(item, model):
    """The model's sub-elements ("Face12"...) that lie on the item's picks."""
    import Part

    names = []
    for obj, sub in _picks(item.References):
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
def run_of(study):
    run = getattr(study, "SimRun", None)
    return run if bodies.alive(run) else None


def _remove_run(study):
    run = run_of(study)
    if run is None:
        return
    doc = study.Document
    members = list(getattr(run, "Group", []) or [])
    study.SimRun = None
    for obj in members + [run]:
        try:
            if doc.getObject(obj.Name) is not None:
                doc.removeObject(obj.Name)
        except Exception:
            pass


def _hide(obj):
    try:
        obj.Visibility = False
        if App.GuiUp and obj.ViewObject is not None:
            obj.ViewObject.Visibility = False
    except Exception:
        pass


def _make_run(study, model_shape, owners):
    """A fresh hidden FEM analysis for `study` with model, solver, materials, mesh object and
    the constraints and loads. Returns (analysis, model feature, mesh object)."""
    import ObjectsFem

    doc = study.Document
    _remove_run(study)
    data = study_data(study)
    opts = data["settings"]
    analysis = ObjectsFem.makeAnalysis(doc, "SimRun")
    bodies.mark(analysis, RUN)
    bodies.hide_from_timeline(analysis)
    analysis.Label = "%s run" % study.Label
    study.SimRun = analysis

    model = doc.addObject("Part::Feature", "SimModel")
    bodies.mark(model, MODEL)
    bodies.hide_from_timeline(model)
    model.Shape = model_shape
    _hide(model)
    analysis.addObject(model)

    solver = ObjectsFem.makeSolverCalculiX(doc, "SimSolver")
    solver.AnalysisType = "static"
    if "GeometricalNonlinearity" in solver.PropertiesList:
        solver.GeometricalNonlinearity = "linear"
    analysis.addObject(solver)

    # one FreeCAD material per distinct study material, on the model's solids it is for
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
        card_data.update(
            {
                "Name": name,
                "YoungsModulus": "%r MPa" % props["youngs_mpa"],
                "PoissonRatio": "%r" % props["poisson"],
                "Density": "%r kg/m^3" % (props.get("density") or 7850.0),
            }
        )
        mat.Material = card_data
        if len(groups) > 1:
            mat.References = [(model, solid_names)]
        analysis.addObject(mat)

    mesh = ObjectsFem.makeMeshGmsh(doc, "SimMesh")
    mesh.Shape = model
    size = core.element_size(_bbox(model_shape), opts["mesh"]["size_pct"])
    mesh.CharacteristicLengthMax = "%r mm" % size
    mesh.CharacteristicLengthMin = "%r mm" % (size * opts["mesh"]["min_pct"] / 100.0)
    mesh.ElementOrder = "2nd" if opts["mesh"]["order"] == "parabolic" else "1st"
    if "SecondOrderLinear" in mesh.PropertiesList:
        mesh.SecondOrderLinear = not opts["mesh"]["curved"]
    if "MeshSizeFromCurvature" in mesh.PropertiesList:
        turn = max(float(opts["mesh"]["max_turn"]), 5.0)
        mesh.MeshSizeFromCurvature = int(round(360.0 / turn))
    if "CoherenceMesh" in mesh.PropertiesList:
        mesh.CoherenceMesh = True
    _hide(mesh)
    analysis.addObject(mesh)

    for item in items(study):
        if item.Suppressed:
            continue
        for fem in _fem_objects(doc, item, model, model_shape):
            analysis.addObject(fem)
    if opts["gravity"]["on"]:
        gravity = ObjectsFem.makeConstraintSelfWeight(doc, "SimGravity")
        gravity.GravityAcceleration = "%r mm/s^2" % float(opts["gravity"]["g"])
        gravity.GravityDirection = App.Vector(*core.unit_vector(opts["gravity"]["direction"]))
        analysis.addObject(gravity)
    for obj in analysis.Group:
        bodies.hide_from_timeline(obj)
        _hide(obj)
    return analysis, model, mesh


def _bbox(shape):
    b = shape.BoundBox
    return (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)


def _fem_objects(doc, item, model, model_shape):
    """FreeCAD FEM constraint objects for one study item (several for a normal force on faces
    that face different ways)."""
    import ObjectsFem

    data = item_data(item)
    category, kind, opts = (
        data["category"],
        data["kind"],
        core.options(data["category"], data["kind"], data["options"]),
    )
    info = core.kind_info(category, kind)
    if not info.get("built"):
        raise SimulationError("%s is not in SciForge yet." % info["title"])
    subs = map_picks(item, model_shape)
    if not subs:
        raise SimulationError("%s lost what it was on: edit it and pick again." % item.Label)
    out = []
    if category == "constraint" and kind == "fixed":
        if all(opts.get(a) for a in ("x", "y", "z")):
            fixed = ObjectsFem.makeConstraintFixed(doc, "SimFixed")
            fixed.References = [(model, subs)]
            out.append(fixed)
        else:
            disp = ObjectsFem.makeConstraintDisplacement(doc, "SimFixedAxes")
            disp.References = [(model, subs)]
            for axis in ("x", "y", "z"):
                held = bool(opts.get(axis))
                setattr(disp, "%sFree" % axis, not held)
                setattr(disp, "%sFix" % axis, held)
            out.append(disp)
    elif category == "load" and kind == "pressure":
        pressure = ObjectsFem.makeConstraintPressure(doc, "SimPressure")
        pressure.References = [(model, subs)]
        pressure.Pressure = "%r MPa" % abs(float(opts["magnitude"]))
        # FreeCAD's pressure pushes into the face; a negative size or Flip pulls
        pressure.Reversed = bool(opts.get("flip")) != (float(opts["magnitude"]) < 0)
        out.append(pressure)
    elif category == "load" and kind == "force":
        out.extend(_forces(doc, item, model, model_shape, subs, opts))
    return out


def _direction(doc, force, vector):
    """Point a FreeCAD force along `vector`. FreeCAD works out a force's direction from an edge
    (its Direction) on every recompute, so a vector set directly does not last: a hidden line
    along the vector is that edge."""
    import Part

    line = doc.addObject("Part::Feature", "SimDirection")
    bodies.mark(line, HELPER)
    bodies.hide_from_timeline(line)
    line.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(vector))
    _hide(line)
    force.Direction = (line, ["Edge1"])
    force.Reversed = False
    return line


def _forces(doc, item, model, model_shape, subs, opts):
    import ObjectsFem

    magnitude = float(opts["magnitude"])
    if opts.get("flip"):
        magnitude = -magnitude
    out = []
    if opts.get("direction") == "normal":
        faces = [s for s in subs if s.startswith("Face")]
        if not faces:
            raise SimulationError(
                "%s: a force along the normal needs faces; pick faces or give a direction."
                % item.Label
            )
        # one FreeCAD force per face (each pushes along its own normal), the total shared by
        # area unless every pick gets the whole force (per_entity)
        areas = [model_shape.getElement(s).Area for s in faces]
        total = sum(areas) or 1.0
        for sub, area in zip(faces, areas):
            face = model_shape.getElement(sub)
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            share = magnitude if opts.get("per_entity") else magnitude * area / total
            force = ObjectsFem.makeConstraintForce(doc, "SimForce")
            force.References = [(model, [sub])]
            force.Force = "%r N" % abs(share)
            # a positive force pushes into the face (against its outward normal)
            out.append(force)
            out.append(_direction(doc, force, normal * (-1.0 if share > 0 else 1.0)))
        return out
    vector = App.Vector(*core.unit_vector(opts.get("vector") or [0, 0, -1]))
    count = len(subs) if opts.get("per_entity") else 1
    force = ObjectsFem.makeConstraintForce(doc, "SimForce")
    force.References = [(model, subs)]
    force.Force = "%r N" % (abs(magnitude) * count)
    out.append(force)
    out.append(_direction(doc, force, vector * (1.0 if magnitude > 0 else -1.0)))
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


# -- solving ---------------------------------------------------------------------------------------
STAGES = ("model", "mesh", "input", "solve", "results")


class Job:
    """One solve of a study, in stages. Call poll() repeatedly (a timer every 100-200 ms)
    until done; everything that touches the document runs inside poll() on the caller's
    thread, Gmsh and CalculiX run in a background thread. cancel() stops it.

    state: "running" | "done" | "failed" | "cancelled"; stage: one of STAGES; message: what
    it is doing (or why it failed); summary: the result summary once done."""

    def __init__(self, study):
        self.study = study
        self.doc = study.Document
        self.state = "running"
        self.stage = "model"
        self.message = "Preparing the model"
        self.summary = None
        self.started = time.time()
        self.work = tempfile.mkdtemp(prefix="sciforge_sim_")
        self._thread = None
        self._process = None
        self._output = ""
        self._failed = None
        self._cancel = False
        self._mesh_tools = None
        self._analysis = self._model = self._mesh = None
        self._owners = []
        self._input = None
        self.timings = {}

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
                if self._failed:
                    return self._stop("failed", self._failed)
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
        return STAGES.index(self.stage) / float(len(STAGES))

    # -- stages (main thread)
    def _stage_model(self):
        checks = precheck(self.study)
        errors = [text for level, text in checks if level == "error"]
        if errors:
            raise SimulationError(" ".join(errors))
        t = time.time()
        shape, self._owners = build_model(self.study)
        self._analysis, self._model, self._mesh = _make_run(self.study, shape, self._owners)
        self.doc.recompute()
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
        self._mesh_tools = tools
        self._background([tools.gmsh_bin, "-", tools.temp_file_geo], "mesh")

    def _after_background(self):
        if self.stage == "mesh":
            t = time.time()
            tools = self._mesh_tools
            if not os.path.isfile(tools.temp_file_mesh):
                raise SimulationError(
                    "The mesh could not be made. Try a larger Average Element Size in the mesh "
                    "settings, or check the model for tiny gaps and slivers. %s"
                    % _last_lines(self._output)
                )
            tools.read_and_set_new_mesh()
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
                    "The mesh has no solid elements: the model may not be a closed solid."
                )
            self.timings["mesh_read"] = time.time() - t
            self.stage, self.message = "input", "Writing the solver input"
            self._stage_input()
        elif self.stage == "solve":
            self.stage, self.message = "results", "Reading the results"
            self._stage_results()

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
        self._input = os.path.splitext(os.path.basename(path))[0]
        self.timings["input"] = time.time() - t
        self.stage, self.message = "solve", "Solving"
        env = dict(os.environ)
        env["OMP_NUM_THREADS"] = str(max(1, (os.cpu_count() or 2) - 1))
        self._background([_binary("ccx"), "-i", self._input], "solve", env=env)

    def _stage_results(self):
        t = time.time()
        frd = os.path.join(self.work, self._input + ".frd")
        if not os.path.isfile(frd) or os.path.getsize(frd) == 0:
            raise SimulationError(_solver_failure(self._output))
        from feminout import importCcxFrdResults

        before = set(o.Name for o in self.doc.Objects)
        importCcxFrdResults.importFrd(frd, self._analysis, "Sim")
        made = [o for o in self.doc.Objects if o.Name not in before]
        result = next((o for o in made if o.isDerivedFrom("Fem::FemResultObject")), None)
        if result is None:
            raise SimulationError(_solver_failure(self._output))
        for obj in made:
            bodies.hide_from_timeline(obj)
            _hide(obj)
        self.timings["results"] = time.time() - t
        self.summary = _finish(self.study, result, self._mesh, self._owners, self)
        self._stop("done", "Done")

    # -- helpers
    def _background(self, command, stage, env=None):
        self.stage = stage
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
                if self._process.returncode not in (0, None) and not self._cancel:
                    if stage == "mesh":
                        self._failed = (
                            "The mesh could not be made. Try a larger Average Element Size, or "
                            "check the model for tiny gaps and slivers. %s"
                            % _last_lines(self._output)
                        )
                    else:
                        self._failed = _solver_failure(self._output)
            except Exception as exc:
                self._failed = "Could not run %s: %s" % (os.path.basename(command[0]), exc)
            finally:
                self._process = None
                self.timings[stage] = time.time() - t

        self._thread = threading.Thread(target=work, name="SciForge %s" % stage, daemon=True)
        self._thread.start()

    def _stop(self, state, message):
        self.state, self.message = state, message
        if state != "done":
            log("simulation %s: %s" % (state, message))
        shutil.rmtree(self.work, ignore_errors=True)
        return state


def _no_window():
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW: no console flashes up
    return {}


def _last_lines(text, count=4):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " ".join(lines[-count:])


def _solver_failure(output):
    text = (output or "").lower()
    if "zero pivot" in text or "singular" in text or "numerically singular" in text:
        return (
            "The model is not held enough: a part can still move or spin freely. Add constraints "
            "so every body is held in X, Y and Z (a Fixed face is the simplest)."
        )
    if "nonpositive jacobian" in text or "negative jacobian" in text:
        return "The mesh has distorted elements: make the Average Element Size smaller."
    return "CalculiX could not solve the study. %s" % _last_lines(output)


def solve(study, timeout=None):
    """Solve a study and wait. Returns the result summary; raises SimulationError with a
    plain sentence when it cannot."""
    job = Job(study)
    state = job.wait(timeout)
    if state != "done":
        raise SimulationError(job.message)
    return job.summary


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
        try:
            shape = bodies.global_shape(body, copy=False)
            box = shape.BoundBox
            parts = [
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
            parts = [body.Name, "?"]
        h.update(json.dumps(parts).encode())
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


def _finish(study, result, mesh_obj, owners, job):
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
        "seconds": round(time.time() - job.started, 2),
        "timings": {k: round(v, 3) for k, v in job.timings.items()},
    }
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

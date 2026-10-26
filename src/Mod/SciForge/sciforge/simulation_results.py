# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab of a Static Stress study, the document side (no Qt): a study's results as
arrays ready to draw (node places, the outer surface of the mesh, displacements, every result's
values), the numbers the legend and Results Details show, and the report.

Nothing here changes the document: the results come from the engine (simulation.results /
summary, the study's last solve) and everything made from them is kept in memory only. The
rules are simulation_results_core.py; the display and the commands simulation_results_ui.py.
Spec: docs/sciforge/parity/simulation.md, section "Results".
"""

import base64
import os
import time

import FreeCAD as App

from . import simulation, warn
from . import simulation_core as sim
from . import simulation_results_core as core

SimulationError = sim.SimulationError
_CACHE = {}  # (document, study) -> ResultData of its last solve


class ResultData:
    """A study's last results in arrays (numpy). points: (n, 3) node places in design
    coordinates, in the result's node order; tets: (m, 4 or 10) node indices of the
    tetrahedra; surface: simulation_results_core.surface() of them; displacement: (n, 3)."""

    def __init__(self, study):
        import numpy as np

        results = simulation.results(study)
        if results is None:
            raise SimulationError(core.NO_RESULTS)
        self.study = study
        self.results = results
        self.result = results.result
        self.stamp = stamp(study)
        mesh = results.mesh
        if mesh is None:
            raise SimulationError("The results have no mesh: solve the study again.")
        index = {n: i for i, n in enumerate(results.node_ids)}
        points = []
        for p in results.points:
            points.append((p.x, p.y, p.z) if p is not None else (0.0, 0.0, 0.0))
        self.points = np.asarray(points, dtype=float).reshape((-1, 3))
        tets = []
        width = None
        for element in mesh.Volumes:
            nodes = mesh.getElementNodes(element)
            if width is None:
                width = 10 if len(nodes) >= 10 else 4
            if len(nodes) < 4:
                continue
            row = [index.get(n, -1) for n in nodes[:width]]
            if len(row) == width and min(row) >= 0:
                tets.append(row)
        self.tets = np.asarray(tets, dtype=np.int64).reshape((-1, width or 4))
        self.surface = core.surface(self.points, self.tets)
        vectors = list(self.result.DisplacementVectors)
        if len(vectors) == len(self.points):
            self.displacement = np.asarray([(v.x, v.y, v.z) for v in vectors], dtype=float)
        else:
            self.displacement = np.zeros_like(self.points)
        self.max_displacement = (
            float(np.linalg.norm(self.displacement, axis=1).max()) if len(self.points) else 0.0
        )
        if len(self.points):
            span = self.points.max(axis=0) - self.points.min(axis=0)
            self.diagonal = float(np.linalg.norm(span))
        else:
            self.diagonal = 0.0
        self._values = {}
        self._straight = None

    def values(self, key):
        """numpy array of a result at every node (NaN where there is none)."""
        import numpy as np

        if key not in self._values:
            try:
                raw = self.results.values(key)
            except Exception as exc:
                raise SimulationError("No %s in these results: %s" % (sim.result_title(key), exc))
            out = np.asarray([float("nan") if v is None else float(v) for v in raw], dtype=float)
            if len(out) != len(self.points):
                raise SimulationError(
                    "The %s values do not match the mesh: solve the study again."
                    % sim.result_title(key)
                )
            self._values[key] = out
        return self._values[key]

    def stats(self, key):
        """{"min", "max", "min_index", "max_index", "min_at", "max_at"} of a result: the
        engine's summary when it has it (the numbers Results Details and the report show),
        worked out from the values otherwise."""
        done = simulation.summary(self.study).get("stats", {}).get(key)
        values = self.values(key)
        if done and done.get("count"):
            out = dict(done)
        else:
            out = sim.stats([None if v != v else v for v in values.tolist()])
            out["min_at"] = self.place(out["min_index"])
            out["max_at"] = self.place(out["max_index"])
        return out

    def place(self, index):
        try:
            if index is None or index < 0:
                return None
            return [float(c) for c in self.points[int(index)]]
        except Exception:
            return None

    def deformed(self, factor):
        """(n, 3) node places with the displacement drawn `factor` times."""
        return self.points + float(factor) * self.displacement

    def straight(self):
        """The mesh as straight tetrahedra (for a slice)."""
        if self._straight is None:
            self._straight = core.straight_tets(self.tets)
        return self._straight


def stamp(study):
    """What identifies a study's last solve: a new solve gives a new stamp."""
    obj = simulation.result_object(study)
    done = simulation.summary(study)
    return (
        getattr(obj, "ID", None),
        done.get("solved"),
        done.get("seconds"),
        (done.get("mesh") or {}).get("nodes"),
    )


def data(study, fresh=False):
    """The study's ResultData (kept until the study is solved again); raises SimulationError
    when it has no results."""
    key = (study.Document.Name, study.Name)
    current = stamp(study)
    found = _CACHE.get(key)
    if fresh or found is None or found.stamp != current:
        _CACHE.pop(key, None)
        found = ResultData(study)
        _CACHE[key] = found
    return found


def forget(doc_name=None):
    """Drop the kept results of a document (all documents when None)."""
    for key in list(_CACHE):
        if doc_name is None or key[0] == doc_name:
            _CACHE.pop(key, None)


def has_results(study):
    try:
        return study is not None and simulation.result_object(study) is not None
    except Exception:
        return False


def out_of_date(study):
    try:
        return bool(simulation.out_of_date(study))
    except Exception as exc:
        warn("results: could not check whether the study changed: %s" % exc)
        return False


# -- what Results Details and the report show ------------------------------------------------------
def body_rows(study):
    """Per body: {"body", "material", "basis", "strength", "von_mises_max", "safety_min",
    "displacement_max"} (the solve's numbers, and the strength the safety factor divides)."""
    done = simulation.summary(study)
    basis = done.get("safety_basis") or simulation.settings(study)["safety_basis"]
    per_body = done.get("bodies") or {}
    rows = []
    found = {b.Label: b for b in simulation.study_bodies(study)}
    for label, entry in per_body.items():
        strength = None
        material = entry.get("material")
        body = found.get(label)
        if body is not None:
            try:
                name, props, _source = simulation.study_material(study, body)
                strength = sim.strength(props, basis)
            except Exception:
                strength = None
        rows.append(
            {
                "body": label,
                "material": material,
                "basis": basis,
                "strength": strength,
                "von_mises_max": entry.get("von_mises_max"),
                "safety_min": entry.get("safety_min"),
                "displacement_max": entry.get("displacement_max"),
            }
        )
    return rows


def min_safety(study):
    stats = simulation.summary(study).get("stats", {}).get("safety") or {}
    value = stats.get("min")
    return value if isinstance(value, (int, float)) else None


def reactions(study):
    """The reaction force at each constraint, {label: (fx, fy, fz)} in N, when the engine
    worked them out at the solve (summary "reactions"); None when it did not."""
    found = simulation.summary(study).get("reactions")
    if not found:
        return None
    out = {}
    try:
        items = found.items() if isinstance(found, dict) else found
        for label, vector in items:
            if isinstance(vector, dict):
                vector = (vector.get("x", 0.0), vector.get("y", 0.0), vector.get("z", 0.0))
            out[str(label)] = tuple(float(c) for c in list(vector)[:3])
    except Exception as exc:
        warn("results: reaction forces unreadable: %s" % exc)
        return None
    return out or None


def _picks_text(item):
    parts = []
    try:
        for obj, subs in item.References or []:
            subs = [subs] if isinstance(subs, str) else list(subs or [])
            parts.append("%s: %s" % (obj.Label, ", ".join(subs) if subs else "whole body"))
    except Exception:
        pass
    return "; ".join(parts) or "-"


def report_data(study, title=None, author="", images=(), lower=None, upper=None):
    """The dict simulation_results_core.report_html() turns into the report."""
    from . import __version__

    done = simulation.summary(study)
    settings = simulation.settings(study)
    mesh = settings["mesh"]
    gravity = settings["gravity"]
    basis = settings["safety_basis"]
    rows = [
        ("Average element size", "%s %% of the model size" % core.fmt(mesh["size_pct"])),
        ("Element order", "Parabolic" if mesh["order"] == "parabolic" else "Linear"),
        ("Curved elements", "Yes" if mesh["curved"] else "No"),
        (
            "Gravity",
            (
                "On, %s m/s2 along %s" % (core.fmt(gravity["g"] / 1000.0), gravity["direction"])
                if gravity["on"]
                else "Off"
            ),
        ),
        ("Safety factor based on", "Yield strength" if basis == "yield" else "Ultimate strength"),
        ("Contacts", "Bonded, %s mm tolerance" % core.fmt(settings["contact_tolerance"])),
    ]
    materials = []
    for body in simulation.study_bodies(study):
        try:
            name, props, source = simulation.study_material(study, body)
        except Exception:
            continue
        label = name + (" (study only)" if source == "study" else "")
        materials.append(
            (
                body.Label,
                label,
                core.fmt_plain(props.get("youngs_mpa")),
                core.fmt_plain(props.get("poisson")),
                core.fmt_plain(props.get("density")),
                core.fmt_plain(props.get("yield_mpa")),
                core.fmt_plain(props.get("ultimate_mpa")),
                "Yield strength" if basis == "yield" else "Ultimate tensile strength",
            )
        )
    constraints, loads = [], []
    for item in simulation.items(study):
        info = simulation.item_data(item)
        try:
            title_kind = sim.kind_info(info["category"], info["kind"])["title"]
            detail = sim.describe(info["category"], info["kind"], info["options"])
        except Exception:
            title_kind, detail = info.get("kind", "?"), ""
        if item.Suppressed:
            detail += " (suppressed)"
        row = (item.Label, title_kind, _picks_text(item), detail)
        (constraints if info["category"] == "constraint" else loads).append(row)
    mesh_done = done.get("mesh") or {}
    mesh_rows = [
        ("Nodes", mesh_done.get("nodes", "-")),
        ("Elements", mesh_done.get("elements", "-")),
        ("Average element size (mm)", core.fmt(mesh_done.get("size"))),
        ("Element order", "Parabolic" if mesh_done.get("order") == "parabolic" else "Linear"),
    ]
    results = []
    stats = done.get("stats") or {}
    for key in core.result_keys():
        st = stats.get(key)
        if not st:
            continue
        results.append((key, st.get("min"), st.get("max"), sim.result_unit(key)))
    bodies_rows = []
    for row in body_rows(study):
        bodies_rows.append(
            (
                row["body"],
                row["material"],
                core.fmt(row["strength"]),
                core.fmt(row["von_mises_max"]),
                core.fmt(row["safety_min"]),
                core.fmt(row["displacement_max"]),
            )
        )
    lower, upper = core.targets(lower, upper)
    notes = []
    if done.get("solved"):
        notes.append(
            "Solved on this computer by CalculiX (mesh by Gmsh) on %s in %s s."
            % (done["solved"], core.fmt(done.get("seconds")))
        )
    return {
        "title": title or "%s report" % study.Label,
        "author": author,
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "version": __version__,
        "design": study.Document.Label,
        "study": study.Label,
        "study_type": sim.study_type_title(simulation.study_data(study).get("type")),
        "settings": rows,
        "materials": materials,
        "constraints": constraints,
        "loads": loads,
        "contacts": "Bodies that touch are bonded (glued) automatically.",
        "mesh": mesh_rows,
        "results": results,
        "bodies": bodies_rows,
        "verdict": core.verdict(min_safety(study), lower, upper),
        "out_of_date": out_of_date(study),
        "images": list(images),
        "notes": notes,
    }


def image_source(path):
    """A picture file as a data: URL (the report is one file that can be mailed)."""
    with open(path, "rb") as handle:
        return "data:image/png;base64," + base64.b64encode(handle.read()).decode("ascii")


def write_report(study, path, title=None, author="", images=(), lower=None, upper=None):
    """Write the study's report to `path` (HTML). images: [(caption, png file)]. Returns the
    path."""
    if not has_results(study):
        raise SimulationError(core.NO_RESULTS)
    embedded = []
    for caption, png in images:
        try:
            embedded.append((caption, image_source(png)))
        except Exception as exc:
            warn("report: picture %s left out: %s" % (caption, exc))
    text = core.report_html(report_data(study, title, author, embedded, lower, upper))
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def default_report_path(study):
    """Next to the design file when it was saved, else in the home folder."""
    doc = study.Document
    folder = os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~")
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in study.Label).strip()
    return os.path.join(folder, "%s - %s.html" % (doc.Label, safe or "Study"))


def is_gui():
    return bool(App.GuiUp)

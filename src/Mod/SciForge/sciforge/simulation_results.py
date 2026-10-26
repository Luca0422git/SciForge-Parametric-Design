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
_STRAIN = ("strain_1", "strain_3", "exx", "eyy", "ezz")


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
        self._stats = {}
        self._straight = None
        self._boxes = None
        self._tet_bodies = None
        self._bodies = None
        self._subsets = {}  # tuple of body indices shown -> (rows, surface, straight)

    def values(self, key):
        """numpy array of a result at every node (NaN where there is none)."""
        import numpy as np

        if key not in self._values:
            try:
                if key in _STRAIN:
                    raw = self._strain(key)
                else:
                    raw = self.results.values(key)
            except Exception as exc:
                raise SimulationError("No %s in these results: %s" % (core.result_name(key), exc))
            out = np.asarray([float("nan") if v is None else float(v) for v in raw], dtype=float)
            if len(out) != len(self.points):
                raise SimulationError(
                    "The %s values do not match the mesh: solve the study again."
                    % sim.result_title(key)
                )
            self._values[key] = out
        return self._values[key]

    def _strain(self, key):
        """Strain components and principal strains from the solve's strain tensor (CalculiX's
        E, as FreeCAD reads it): normal strains as they are, principal ones its eigenvalues."""
        import numpy as np

        r = self.result
        comps = [
            np.asarray(list(getattr(r, "NodeStrain" + c)), dtype=float)
            for c in ("XX", "YY", "ZZ", "XY", "YZ", "XZ")
        ]
        if key == "exx":
            return comps[0].tolist()
        if key == "eyy":
            return comps[1].tolist()
        if key == "ezz":
            return comps[2].tolist()
        largest, smallest = core.principal(*comps)
        return (largest if key == "strain_1" else smallest).tolist()

    def stats(self, key):
        """{"min", "max", "min_index", "max_index", "min_at", "max_at"} of a result: the
        engine's summary when it has it (the numbers Results Details and the report show),
        worked out from the values otherwise. Kept once worked out (these results do not
        change: a new solve makes a new ResultData)."""
        if key in self._stats:
            return dict(self._stats[key])
        done = simulation.summary(self.study).get("stats", {}).get(key)
        values = self.values(key)
        if done and done.get("count"):
            out = dict(done)
        else:
            out = sim.stats([None if v != v else v for v in values.tolist()])
            out["min_at"] = self.place(out["min_index"])
            out["max_at"] = self.place(out["max_index"])
        self._stats[key] = dict(out)
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

    def bodies(self):
        """The bodies these results are of (the solve's per-body rows; a body hidden since is
        still one of them: the engine's study_bodies() leaves hidden bodies out)."""
        if self._bodies is None:
            found = []
            try:
                doc = self.study.Document
                for label in simulation.summary(self.study).get("bodies") or {}:
                    for obj in doc.getObjectsByLabel(label):
                        if hasattr(obj, "Shape") and obj not in found:
                            found.append(obj)
                            break
                if not found:
                    found = list(simulation.study_bodies(self.study))
            except Exception:
                found = []
            self._bodies = found
        return self._bodies

    def tet_bodies(self):
        """Per tetrahedron the index (into bodies()) of the body it lies in, -1 when none was
        found: its centre tested in each body's shape (worked out once, on first use; one body:
        no test)."""
        import numpy as np

        if self._tet_bodies is not None:
            return self._tet_bodies
        owners = np.full(len(self.tets), -1, dtype=np.int64)
        found = self.bodies()
        if len(found) <= 1 or not len(self.tets):
            owners[:] = 0 if found else -1
            self._tet_bodies = owners
            return owners
        from . import bodies as body_tools

        centres = self.points[self.tets[:, :4]].mean(axis=1)
        size = float(self.diagonal or 1.0)
        for k, body in enumerate(found):
            try:
                shape = body_tools.global_shape(body, copy=False)
                box = shape.BoundBox
            except Exception:
                continue
            pad = 1e-6 * size
            near = np.flatnonzero(
                (owners < 0)
                & (centres[:, 0] >= box.XMin - pad)
                & (centres[:, 0] <= box.XMax + pad)
                & (centres[:, 1] >= box.YMin - pad)
                & (centres[:, 1] <= box.YMax + pad)
                & (centres[:, 2] >= box.ZMin - pad)
                & (centres[:, 2] <= box.ZMax + pad)
            )
            for i in near.tolist():
                try:
                    if shape.isInside(App.Vector(*centres[i]), pad, True):
                        owners[i] = k
                except Exception:
                    continue
        self._tet_bodies = owners
        return owners

    def subset(self, shown):
        """(tetrahedron rows, surface, straight tetrahedra) of the bodies `shown` (indices into
        bodies()); the elements of no body found count as shown."""
        import numpy as np

        key = tuple(sorted(int(k) for k in shown))
        if key not in self._subsets:
            owners = self.tet_bodies()
            rows = np.flatnonzero(np.isin(owners, list(key)) | (owners < 0))
            tets = self.tets[rows]
            self._subsets[key] = (rows, core.surface(self.points, tets), core.straight_tets(tets))
        return self._subsets[key]

    def locate(self, point):
        """Where a point of the unloaded part lies in the mesh: (straight tetrahedron row,
        barycentric weights) or None outside it (Point Probes)."""
        if self._boxes is None:
            self._boxes = core.tet_boxes(self.points, self.straight())
        return core.locate(self.points, self.straight(), point, self._boxes)

    def at(self, where, key):
        """A result's value at locate()'s place (NaN where it has none)."""
        return float(core.at_point(self.values(key), self.straight(), where))

    def moved(self, where):
        """The displacement (x, y, z) at locate()'s place."""
        return core.at_point(self.displacement, self.straight(), where)


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
    """True when the study's last results are here to show (solved, and kept with the design
    if it was reopened: sim-core's keep_results)."""
    try:
        if study is None or simulation.result_object(study) is None:
            return False
        return not results_dropped(study)
    except Exception:
        return False


def results_dropped(study):
    """Solved, but its results were not saved with the design (the study's Keep results
    setting off): only the numbers are left; solve again to see them."""
    dropped = getattr(simulation, "results_dropped", None)
    try:
        return bool(dropped(study)) if dropped is not None else False
    except Exception:
        return False


DROPPED = (
    "The results of this study were not kept with the design (Study Settings: Keep results "
    "in the file): solve it again to see them."
)


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


def reaction_places(study):
    """{constraint label: (x, y, z)} the middle of the faces each constraint holds, in design
    coordinates (where Reaction Force puts its tags)."""
    from . import bodies as body_tools

    out = {}
    for item in simulation.items(study):
        try:
            if simulation.item_data(item).get("category") != "constraint" or item.Suppressed:
                continue
            points = []
            for obj, subs in item.References or []:
                subs = [subs] if isinstance(subs, str) else list(subs or [])
                shape = body_tools.global_shape(obj, copy=False)
                for sub in subs or []:
                    try:
                        points.append(shape.getElement(sub).CenterOfMass)
                    except Exception:
                        continue
                if not subs:
                    points.append(shape.CenterOfMass)
            if points:
                n = float(len(points))
                out[item.Label] = (
                    sum(p.x for p in points) / n,
                    sum(p.y for p in points) / n,
                    sum(p.z for p in points) / n,
                )
        except Exception:
            continue
    return out


def _picks_text(item):
    parts = []
    try:
        for obj, subs in item.References or []:
            subs = [subs] if isinstance(subs, str) else list(subs or [])
            parts.append("%s: %s" % (obj.Label, ", ".join(subs) if subs else "whole body"))
    except Exception:
        pass
    return "; ".join(parts) or "-"


def report_data(study, title=None, author="", images=(), lower=None, upper=None, unit_of=None):
    """The dict simulation_results_core.report_html() turns into the report. unit_of(result)
    gives the unit of the results table (the legend's), else SciForge's own (mm, MPa)."""
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
        unit = unit_of(key) if unit_of is not None else None
        if unit is None or not core.unit_ok(key, unit):
            results.append((key, st.get("min"), st.get("max"), sim.result_unit(key)))
        else:
            results.append(
                (key, core.convert(st.get("min"), unit), core.convert(st.get("max"), unit), unit)
            )
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


IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def image_source(path):
    """A picture file as a data: URL (the report is one file that can be mailed)."""
    kind = IMAGE_TYPES.get(os.path.splitext(str(path))[1].lower(), "image/png")
    with open(path, "rb") as handle:
        return "data:%s;base64,%s" % (kind, base64.b64encode(handle.read()).decode("ascii"))


def write_report(
    study,
    path,
    title=None,
    author="",
    images=(),
    lower=None,
    upper=None,
    cover=None,
    more=(),
    unit_of=None,
):
    """Write the study's report to `path` (HTML). images: [(caption, png file)]; cover: the
    report's own fields {"summary", "logo" and "picture" (image files), "project",
    "approver", "revision"}; more: [(another study, its images)] in the same report. Returns
    the path."""
    entries = [(study, images)] + list(more)
    studies = []
    for one, pictures in entries:
        if not has_results(one):
            raise SimulationError("%s: %s" % (one.Label, core.NO_RESULTS))
        embedded = []
        for caption, png in pictures:
            try:
                embedded.append((caption, image_source(png)))
            except Exception as exc:
                warn("report: picture %s left out: %s" % (caption, exc))
        studies.append(report_data(one, title, author, embedded, lower, upper, unit_of))
    data = dict(studies[0])
    data["studies"] = studies
    cover = dict(cover or {})
    for key in ("summary", "project", "approver", "revision"):
        if cover.get(key):
            data[key] = str(cover[key])
    for key, name in (("logo", "logo"), ("picture", "cover picture")):
        if cover.get(key):
            try:
                data[key] = image_source(cover[key])
            except Exception as exc:
                warn("report: %s left out: %s" % (name, exc))
    text = core.report_html(data)
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


def design_length_unit(doc):
    """The design's length unit (Document Settings > Units): "mm", "cm", "m", "in" or "ft"."""
    try:
        from . import browser_core

        schema = doc.getEnumerationsOfProperty("UnitSystem").index(doc.UnitSystem)
        return browser_core.unit_label(schema) or "mm"
    except Exception:
        return "mm"


def default_animation_path(study):
    """Like the report: next to the design file when it was saved, else in the home folder."""
    return default_report_path(study)[: -len(".html")] + " animation.gif"


def is_gui():
    return bool(App.GuiUp)

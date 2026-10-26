# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's RESULTS tab of a Static Stress study (SIMULATION workspace): the results shown on the
model, the legend, the deformation scale and animation, min / max tags, surface probes, slice
plane, display options, Results Details, the report and Finish Results. Owner: builder
sim-results (beta 3). Spec: docs/sciforge/parity/simulation.md, section "Results"; Fusion's
behaviour with sources: docs/sciforge/dev/research/fusion-simulation.md, section 5.

How it works: the results show while the SIMULATION workspace's RESULTS tab is the one selected
(a watcher on the ribbon's pages); show(study) is how a finished solve (sim-ui's Solve dialog)
brings them up. While they show, the design's bodies are hidden on the 3D view only (their Coin
switch, never their Visibility property: nothing lands in the undo history, the file or the
study's out-of-date fingerprint), and SciForge's own Coin nodes draw the result
(simulation_results_view.ResultDisplay). Leaving the RESULTS tab (SETUP, Finish Results, the
DESIGN workspace, another document) takes all of it away and shows the bodies again.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import commands, log, simulation, ui_icon_path, warn
from . import simulation_results as results_data
from . import simulation_results_core as core
from . import simulation_results_view as view_mod
from .compat import QtCore, QtWidgets

RESULTS_TAB = "sim_results"
SETUP_TAB = "sim_setup"
SESSIONS = {}  # document name -> Session
ACTIVE = {"session": None}
WATCH = {"ribbon": None, "area": None, "observer": None, "timer": None, "syncing": False}
# sim-ui's Solve command (the first one that exists): Solve Again on out-of-date results
SOLVE_COMMANDS = ("SciForge_SimSolve", "SciForge_SimulationSolve", "SciForge_StudySolve")


def _ribbon():
    try:
        from . import shell

        return shell.ribbon()
    except Exception:
        return None


def _sim_on():
    try:
        from . import simulation_ui

        return bool(simulation_ui.active())
    except Exception:
        return False


def _current_tab(ribbon):
    try:
        return ribbon.current_tab()
    except Exception:
        return None


def _doc(name):
    try:
        return App.getDocument(name)
    except Exception:
        return None


# -- which study ---------------------------------------------------------------------------------
def studies_with_results(doc):
    if doc is None:
        return []
    return [s for s in simulation.studies(doc) if results_data.has_results(s)]


def _ui_active_study(doc):
    """sim-ui's active study of `doc` (the one the SETUP commands work on), or None."""
    try:
        from . import simulation_ui

        fn = getattr(simulation_ui, "active_study", None)
        return fn(doc) if fn is not None else None
    except Exception:
        return None


def active_study(doc):
    """The study whose results the RESULTS tab shows for `doc`: sim-ui's active study (Fusion's
    RESULTS tab belongs to the active study), else the one shown last, else the newest study
    with results."""
    if doc is None:
        return None
    study = _ui_active_study(doc)
    if study is not None:
        return study
    session = SESSIONS.get(doc.Name)
    if session is not None and session.study is not None:
        return session.study
    found = studies_with_results(doc)
    return found[-1] if found else None


# -- entry points --------------------------------------------------------------------------------
def show(study):
    """Show a study's results: the SIMULATION workspace, its RESULTS tab, the safety factor
    first (Fusion). sim-ui's Solve dialog calls this when a solve ends. Returns True when the
    results show."""
    try:
        if study is None or not simulation.is_study(study):
            return False
        if not results_data.has_results(study):
            commands.tell(core.NO_RESULTS)
            return False
        doc = study.Document
        if _ui_active_study(doc) is not study:
            try:
                from . import simulation_ui

                simulation_ui.set_active_study(study)
            except Exception:
                pass
        session = SESSIONS.get(doc.Name)
        if session is not None and session.study_name != study.Name:
            session.deactivate()
            session = None
        if session is None:
            session = Session(study)
            SESSIONS[doc.Name] = session
        ensure_watch()
        _select_results_tab()
        sync()
        return session.active
    except Exception as exc:
        warn("results: %s" % exc)
        return False


def _select_results_tab():
    ribbon = _ribbon()
    if ribbon is None:
        return
    if not _sim_on():
        try:
            from . import simulation_ui

            simulation_ui.enter_workspace(RESULTS_TAB)
        except Exception as exc:
            warn("results: the simulation workspace did not open: %s" % exc)
    if RESULTS_TAB in getattr(ribbon, "tab_buttons", {}):
        ribbon.tab_buttons[RESULTS_TAB].setVisible(True)
        if _current_tab(ribbon) != RESULTS_TAB:
            ribbon.select_tab(RESULTS_TAB)


def current():
    """The Session whose results are on the screen now, or None."""
    session = ACTIVE["session"]
    return session if session is not None and session.active else None


def is_shown():
    return current() is not None


def finish():
    """Finish Results: back to the SETUP tab, the bodies shown again (Fusion)."""
    try:
        ribbon = _ribbon()
        session = current()
        if session is not None:
            session.deactivate()
        if ribbon is not None and SETUP_TAB in getattr(ribbon, "page_index", {}):
            ribbon.select_tab(SETUP_TAB)
        sync()
        log("results finished")
    except Exception as exc:
        warn("Finish Results: %s" % exc)


def hide():
    """Take the results off the screen (sim-ui calls it when the workspace is left): the
    bodies show again."""
    try:
        session = ACTIVE["session"]
        if session is not None:
            session.deactivate()
        ACTIVE["session"] = None
    except Exception as exc:
        warn("results: %s" % exc)


def hide_all():
    """Take every result display away (SciForge switched off, tests)."""
    for session in list(SESSIONS.values()):
        try:
            session.deactivate()
        except Exception as exc:
            warn("results: %s" % exc)
    ACTIVE["session"] = None


def wanted():
    """The Session that should be on the screen now (or None): the SIMULATION workspace is on,
    its RESULTS tab is the one selected, and the active study of the design in front has
    results."""
    ribbon = _ribbon()
    if ribbon is None or not _sim_on() or _current_tab(ribbon) != RESULTS_TAB:
        return None
    doc = App.ActiveDocument
    if doc is None:
        return None
    study = active_study(doc)
    session = SESSIONS.get(doc.Name)
    if session is not None and (
        study is None or session.study is not study or not results_data.has_results(session.study)
    ):
        session.deactivate()
        SESSIONS.pop(doc.Name, None)
        session = None
    if study is None or not results_data.has_results(study):
        return None
    if session is None:
        session = Session(study)
        SESSIONS[doc.Name] = session
    return session


def sync():
    """Put the screen in step: the results of the design in front while its RESULTS tab is
    selected, nothing (and the bodies shown) otherwise."""
    if WATCH["syncing"]:
        return
    WATCH["syncing"] = True
    try:
        want = wanted()
        shown = ACTIVE["session"]
        if shown is not None and shown is not want:
            shown.deactivate()
            ACTIVE["session"] = None
        if want is not None:
            try:
                want.activate()
                ACTIVE["session"] = want
            except results_data.SimulationError as exc:
                want.deactivate()
                commands.tell(str(exc))
        refresh_tab()
    except Exception as exc:
        warn("results: %s" % exc)
    finally:
        WATCH["syncing"] = False


def refresh_tab():
    """Fusion shows the RESULTS tab once the study has results."""
    ribbon = _ribbon()
    if ribbon is None or RESULTS_TAB not in getattr(ribbon, "tab_buttons", {}):
        return
    try:
        sim_mode = _sim_on() and bool(getattr(ribbon, "_sim_mode", True))
        drawing = bool(getattr(ribbon, "_drawing_mode", False))
        study = active_study(App.ActiveDocument)
        has = study is not None and results_data.has_results(study)
        visible = sim_mode and not drawing and has
        button = ribbon.tab_buttons[RESULTS_TAB]
        if button.isVisible() != visible:
            button.setVisible(visible)
        if not visible and sim_mode and not drawing and _current_tab(ribbon) == RESULTS_TAB:
            ribbon.select_tab(SETUP_TAB)
    except Exception as exc:
        warn("results tab: %s" % exc)


# -- watching the ribbon, the documents and the views ----------------------------------------------
def ensure_watch():
    """Follow the ribbon's tab changes, document changes and the active window (idempotent:
    the ribbon can be made again)."""
    try:
        ribbon = _ribbon()
        if ribbon is not None and WATCH["ribbon"] is not ribbon:
            ribbon.pages.currentChanged.connect(_tab_changed)
            WATCH["ribbon"] = ribbon
        area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        if area is not None and WATCH["area"] is not area:
            area.subWindowActivated.connect(lambda *_a: QtCore.QTimer.singleShot(0, sync))
            WATCH["area"] = area
        if WATCH["observer"] is None:
            WATCH["observer"] = _DocWatch()
            App.addDocumentObserver(WATCH["observer"])
    except Exception as exc:
        warn("results: %s" % exc)


def _tab_changed(_index):
    QtCore.QTimer.singleShot(0, sync)


def _poll_watch():
    """Started once at import: hooks the watcher up as soon as the ribbon exists."""
    try:
        if _ribbon() is not None:
            ensure_watch()
            if WATCH["timer"] is not None and WATCH["ribbon"] is not None:
                WATCH["timer"].setInterval(3000)  # (a new ribbon is hooked up again)
    except Exception as exc:
        warn("results: %s" % exc)


class _DocWatch:
    """What changes the results on the screen: a recompute or undo (the design may have changed:
    out of date), the study or its run deleted, the document closed."""

    def slotRecomputedDocument(self, doc):
        _later(doc, "status")

    def slotUndoDocument(self, doc):
        _later(doc, "sync")

    def slotRedoDocument(self, doc):
        _later(doc, "sync")

    def slotDeletedObject(self, obj):
        try:
            if simulation.is_study(obj) or simulation.is_simulation_object(obj):
                _later(obj.Document, "sync")
        except Exception:
            pass

    def slotDeletedDocument(self, doc):
        try:
            name = doc.Name
        except Exception:
            return
        session = SESSIONS.pop(name, None)
        if session is not None:
            session.drop()
            if ACTIVE["session"] is session:
                ACTIVE["session"] = None
        results_data.forget(name)


_PENDING = {"status": set(), "sync": False, "armed": False}


def _later(doc, what):
    try:
        name = doc.Name
    except Exception:
        return
    if what == "status":
        _PENDING["status"].add(name)
    else:
        _PENDING["sync"] = True
    if not _PENDING["armed"]:
        _PENDING["armed"] = True
        QtCore.QTimer.singleShot(80, _run_later)


def _run_later():
    _PENDING["armed"] = False
    names, _PENDING["status"] = _PENDING["status"], set()
    again, _PENDING["sync"] = _PENDING["sync"], False
    try:
        if again:
            sync()
        session = current()
        if session is not None and session.doc_name in names:
            session.refresh_status()
    except Exception as exc:
        warn("results: %s" % exc)


# -- one study's results on the screen -------------------------------------------------------------
class Session:
    """The results of one study as shown (display-only state: the result, unit, scale, options,
    probes and slice live here, never in the document)."""

    def __init__(self, study):
        self.doc_name = study.Document.Name
        self.study_name = study.Name
        self.result = core.DEFAULT_RESULT
        self.units = {}  # result kind -> unit chosen in the legend
        self.deformation = core.DEFORMATION_DEFAULT
        self.mesh = False
        self.ghost = False
        self.loads = False
        self.minmax = True
        self.banded = False
        self.bands = False  # the safety factor target bands
        self.targets = core.DEFAULT_TARGETS
        self.probes = []  # {"node": index} or {"point": (x, y, z), "values": {...}}
        self.slice = None  # {"axis": "x"|"y"|"z", "offset": mm, "flip": bool, "style": ...}
        self.anim = {
            "shown": False,
            "playing": False,
            "step": 0,
            "speed": 1.0,
            "frames": 20,
            "mode": "loop",
        }
        self.data = None
        self.display = None
        self.view = None
        self.gl = None
        self.legend = None
        self.tags = None
        self.bar = None
        self.hidden = {}
        self.active = False
        self.out_of_date = False
        self.legend_info = None
        self.tag_list = []
        self._camera = None
        self._ticks = 0
        self._timer = None
        self._anim_timer = None
        self._glyphs_before = None
        self.panels = []

    # -- the study
    @property
    def doc(self):
        return _doc(self.doc_name)

    @property
    def study(self):
        doc = self.doc
        obj = doc.getObject(self.study_name) if doc is not None else None
        return obj if obj is not None and simulation.is_study(obj) else None

    # -- on and off the screen
    def activate(self):
        study = self.study
        if study is None:
            raise results_data.SimulationError("The study is gone.")
        stamp = results_data.stamp(study)
        if self.data is None or self.data.stamp != stamp:
            self._rebuild(study)
        gui = Gui.getDocument(self.doc_name)
        gl = view_mod.gl_widget_of(self.doc_name)
        if self.active and gl is not None and gl is self.gl:
            self.refresh_status()
            return
        if self.active:
            self.deactivate()
        self.view = gui.ActiveView
        self.gl = gl
        self.display.attach(self.view)
        self._hide_design()
        if gl is not None:
            self.legend = view_mod.Legend(
                gl,
                {
                    "result": self.set_result,
                    "unit": self.set_unit,
                    "details": open_details,
                    "solve": solve_again,
                },
            )
            self.tags = view_mod.TagLayer(gl, self.view)
        self.active = True
        self.refresh_status(apply=False)
        self.apply()
        if self.anim["shown"]:
            self._show_bar()
        self._timer = QtCore.QTimer()
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        log("results shown: %s, %s" % (study.Label, core.result_name(self.result)))

    def _rebuild(self, study):
        was = self.active
        if was:
            self.deactivate()
        self.data = results_data.data(study)
        self.display = view_mod.ResultDisplay(self.data)
        self.probes = []
        if self.slice is not None:
            self.slice = dict(self.slice)

    def deactivate(self):
        self.stop_animation(keep_bar=True)
        for panel in list(self.panels):
            try:
                panel.close()
            except Exception:
                pass
        self.panels = []
        if self._timer is not None:
            try:
                self._timer.stop()
            except RuntimeError:
                pass
            self._timer = None
        for widget in (self.legend, self.tags, self.bar):
            if widget is None:
                continue
            try:
                if hasattr(widget, "remove"):
                    widget.remove()
                else:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            except RuntimeError:
                pass
        self.legend = self.tags = self.bar = None
        if self.display is not None:
            self.display.detach()
        self._show_design()
        self._restore_glyphs()
        was = self.active
        self.active = False
        self.gl = None
        self.view = None
        if ACTIVE["session"] is self:
            ACTIVE["session"] = None
        if was:
            log("results hidden")

    def drop(self):
        """The document closed: forget everything (its views are gone)."""
        try:
            if self._timer is not None:
                self._timer.stop()
            if self._anim_timer is not None:
                self._anim_timer.stop()
        except RuntimeError:
            pass
        self._timer = self._anim_timer = None
        self.hidden = {}
        self.active = False

    # -- the design, hidden on the view only
    def _hide_design(self):
        doc = self.doc
        if doc is None:
            return
        for obj in doc.Objects:
            try:
                vo = obj.ViewObject
                if vo is None or simulation.is_simulation_object(obj):
                    continue
                switch = vo.SwitchNode
                which = switch.whichChild.getValue()
                if which != -1:
                    self.hidden[obj.Name] = which
                    switch.whichChild = -1
            except Exception:
                continue

    def _keep_design_hidden(self):
        doc = self.doc
        if doc is None:
            return
        for name in list(self.hidden):
            obj = doc.getObject(name)
            try:
                if obj is None or obj.ViewObject is None:
                    self.hidden.pop(name, None)
                    continue
                switch = obj.ViewObject.SwitchNode
                which = switch.whichChild.getValue()
                if which != -1:  # FreeCAD showed it again (a display mode change...)
                    self.hidden[name] = which
                    switch.whichChild = -1
            except Exception:
                self.hidden.pop(name, None)

    def _show_design(self):
        doc = self.doc
        hidden, self.hidden = self.hidden, {}
        if doc is None:
            return
        for name, which in hidden.items():
            obj = doc.getObject(name)
            try:
                if obj is None or obj.ViewObject is None:
                    continue
                vo = obj.ViewObject
                if not vo.Visibility:
                    continue  # hidden by the person meanwhile: stays hidden
                if vo.SwitchNode.whichChild.getValue() == -1:
                    vo.SwitchNode.whichChild = which
            except Exception:
                continue

    def design_hidden(self):
        """Names of the objects hidden on the view while the results show."""
        return sorted(self.hidden)

    # -- what is drawn
    def unit(self, result=None):
        result = result or self.result
        kind = core.kind_of(result)
        unit = self.units.get(kind)
        return unit if unit is not None and core.unit_ok(result, unit) else core.base_unit(result)

    def factor(self, key=None):
        data = self.data
        return core.deformation_factor(
            key or self.deformation, data.max_displacement, data.diagonal
        )

    def apply(self):
        """Draw the chosen result with the chosen options (colours, shape, legend, tags)."""
        if self.display is None or self.data is None:
            return
        np = view_mod._np()
        values = self.data.values(self.result)
        stats = self.data.stats(self.result)
        lo, hi, reverse = core.scale(self.result, stats.get("min"), stats.get("max"))
        surface_values = values[self.display.nodes]
        self.display.set_positions(_positions(np, surface_values, lo, hi, reverse))
        bands = self.result == "safety" and self.bands
        self.display.set_texture(
            core.texture_rows(targets=self.targets) if bands else core.texture_rows(self.banded)
        )
        if not self.anim["playing"]:
            self.display.set_factor(self.factor())
        self.display.set_mesh(self.mesh)
        self.display.set_ghost(self.ghost and self.factor() != 0.0)
        self._apply_slice()
        info = core.legend(
            self.result,
            stats,
            self.unit(),
            banded=self.banded,
            targets=self.targets if bands else None,
        )
        info["targets"] = self.targets
        self.legend_info = info
        if self.legend is not None and view_mod._alive(self.legend):
            self.legend.fill(info, self._study_text(), self.out_of_date, self._deform_text())
        self.update_tags()
        self._glyphs()
        self._redraw()

    def _study_text(self):
        study = self.study
        return study.Label if study is not None else ""

    def _deform_text(self):
        name = core.deformation_name(self.deformation)
        f = self.factor()
        if self.deformation == "undeformed":
            return "Deformation: Undeformed"
        if self.deformation == "actual":
            return "Deformation: Actual (true size)"
        return "Deformation: %s (shown %s x)" % (name, core.fmt(f, 3))

    def update_tags(self):
        tags = []
        np = view_mod._np()
        if self.data is not None and self.display is not None:
            values = self.data.values(self.result)
            stats = self.data.stats(self.result)
            lo, hi, reverse = core.scale(self.result, stats.get("min"), stats.get("max"))
            unit = self.unit()
            if self.minmax:
                for kind in ("max", "min"):
                    index = stats.get("%s_index" % kind)
                    if index is None or index < 0:
                        continue
                    value = stats.get(kind)
                    tags.append(
                        {
                            "kind": kind,
                            "node": int(index),
                            "value": value,
                            "point": tuple(float(c) for c in self.display.node_place(int(index))),
                            "text": "%s: %s"
                            % (
                                "Max" if kind == "max" else "Min",
                                core.with_unit(core.convert(value, unit), unit),
                            ),
                            "colour": core.map_colour(core.position(value, lo, hi, reverse)),
                        }
                    )
            for probe in self.probes:
                if "node" in probe:
                    index = probe["node"]
                    value = float(values[index])
                    point = tuple(float(c) for c in self.display.node_place(index))
                else:
                    value = probe.get("values", {}).get(self.result)
                    point = probe["point"]
                    if value is None:
                        continue
                if value != value:
                    text = "-"
                else:
                    text = core.with_unit(core.convert(value, unit), unit)
                tags.append(
                    {
                        "kind": "probe",
                        "node": probe.get("node"),
                        "value": value,
                        "point": point,
                        "text": text,
                        "colour": core.map_colour(core.position(value, lo, hi, reverse)),
                    }
                )
        del np
        self.tag_list = tags
        if self.tags is not None and view_mod._alive(self.tags):
            self.tags.set_tags(tags)

    def _redraw(self):
        try:
            if self.view is not None:
                self.view.redraw()
        except Exception:
            pass

    def refresh_status(self, apply=True):
        """Out of date or not (the design or the study changed after the solve)."""
        study = self.study
        if study is None:
            return
        before = self.out_of_date
        self.out_of_date = results_data.out_of_date(study)
        if apply and before != self.out_of_date and self.legend_info is not None:
            if self.legend is not None and view_mod._alive(self.legend):
                self.legend.fill(
                    self.legend_info, self._study_text(), self.out_of_date, self._deform_text()
                )

    # -- the choices
    def set_result(self, key):
        if key not in core.result_keys():
            return
        self.result = key
        self.apply()
        log("results: %s" % core.result_name(key))

    def set_unit(self, unit):
        if not core.unit_ok(self.result, unit):
            return
        self.units[core.kind_of(self.result)] = unit
        self.apply()

    def set_deformation(self, key):
        if key not in [k for k, _n in core.deformations()]:
            return
        self.deformation = key
        if self.anim["playing"]:
            self.anim["step"] = 0
        self.apply()
        log("results: deformation %s" % core.deformation_name(key))

    def set_option(self, name, on):
        setattr(self, name, bool(on))
        self.apply()

    # -- probes
    def add_probe_at(self, x, y):
        """A surface probe where the Coin pixel (x, y) meets the result (the nearest node of
        the face it meets; on the slice's cut face, the value there). Returns the probe or
        None."""
        if self.display is None or self.view is None:
            return None
        np = view_mod._np()
        origin, direction = view_mod.ray_coin(self.view, x, y)
        pts = self.display.surface_points()
        tris = self.display.triangles
        if self.display.clipped() and self.slice is not None:
            origin_p, normal = slice_plane(self)
            keep = (pts[tris].mean(axis=1) - np.asarray(origin_p)) @ np.asarray(normal) >= -1e-6
            index_map = np.flatnonzero(keep)
            tris = tris[keep]
        else:
            index_map = None
        best = None
        if self.slice is None or self.slice.get("style") != "slice":
            hit = core.ray_hit(origin, direction, pts, tris)
            if hit is not None:
                best = ("surface", hit)
        cap = self.display.cap_points
        if len(cap) and self.display.cap_shown():
            cap_tris = np.arange(len(cap)).reshape((-1, 3))
            hit = core.ray_hit(origin, direction, cap, cap_tris)
            if hit is not None and (best is None or hit[0] < best[1][0] - 1e-9):
                best = ("cap", hit)
        if best is None:
            return None
        where, (t, tri, weights) = best
        if where == "surface":
            tri_index = int(index_map[tri]) if index_map is not None else int(tri)
            corners = self.display.triangles[tri_index]
            point = np.asarray(origin) + t * np.asarray(direction)
            local = core.nearest(pts, point, candidates=corners)
            probe = {"node": int(self.display.nodes[local])}
        else:
            point = np.asarray(origin) + t * np.asarray(direction)
            probe = {"point": tuple(float(c) for c in point), "values": {}}
            probe["values"] = self._cap_values_at(point)
        self.probes.append(probe)
        self.update_tags()
        self._redraw()
        return probe

    def _cap_values_at(self, point):
        """Every result's value at a point of the slice (interpolated in the mesh)."""
        out = {}
        np = view_mod._np()
        data = self.data
        origin_p, normal = slice_plane(self)
        deformed = data.deformed(self.display.factor)
        tets = data.straight()
        for key in core.result_keys():
            try:
                values = data.values(key)
            except Exception:
                continue
            tris, vals = core.cut(deformed, values, tets, origin_p, normal)
            if not tris:
                continue
            arr = np.asarray(tris, dtype=float)
            hit = core.ray_hit(
                np.asarray(point) + np.asarray(normal) * 1e-3,
                -np.asarray(normal),
                arr.reshape((-1, 3)),
                np.arange(len(arr) * 3).reshape((-1, 3)),
            )
            if hit is None:
                continue
            _t, tri, w = hit
            v = vals[tri]
            out[key] = float(w[0] * v[0] + w[1] * v[1] + w[2] * v[2])
        return out

    def clear_probes(self):
        self.probes = []
        self.update_tags()
        self._redraw()

    # -- slice plane
    def set_slice(self, spec):
        self.slice = dict(spec) if spec else None
        self.apply()

    def _apply_slice(self):
        display = self.display
        if self.slice is None:
            display.set_clip(None, None)
            display.set_cap([], [], [])
            display.part_switch.whichChild = display.coin.SO_SWITCH_ALL
            return
        origin, normal = slice_plane(self)
        style = self.slice.get("style", "clip")
        display.set_clip(origin, normal)
        if style == "slice":
            display.part_switch.whichChild = display.coin.SO_SWITCH_NONE
        else:
            display.part_switch.whichChild = display.coin.SO_SWITCH_ALL
        self._cut(origin, normal)

    def _cut(self, origin, normal):
        np = view_mod._np()
        data = self.data
        values = data.values(self.result)
        stats = data.stats(self.result)
        lo, hi, reverse = core.scale(self.result, stats.get("min"), stats.get("max"))
        tris, vals = core.cut(
            data.deformed(self.display.factor), values, data.straight(), origin, normal
        )
        flat_vals = np.asarray(vals, dtype=float).ravel() if vals else np.zeros(0)
        positions = _positions(np, flat_vals, lo, hi, reverse) if len(flat_vals) else []
        self.display.set_cap(tris, flat_vals, positions)

    # -- animation
    def toggle_animation(self):
        if self.anim["shown"]:
            self.close_animation()
        else:
            self.anim["shown"] = True
            self._show_bar()
            self.play()

    def _show_bar(self):
        if self.gl is None or (self.bar is not None and view_mod._alive(self.bar)):
            return
        self.bar = view_mod.AnimationBar(
            self.gl,
            {
                "toggle": lambda: self.stop_animation() if self.anim["playing"] else self.play(),
                "speed": self._set_speed,
                "frames": self._set_frames,
                "mode": self._set_mode,
                "close": self.close_animation,
            },
            self.anim["speed"],
            self.anim["frames"],
            self.anim["mode"],
        )
        self.bar.set_playing(self.anim["playing"])

    def play(self):
        if self.display is None:
            return
        self.anim["playing"] = True
        self.anim["step"] = 0
        if self._anim_timer is None:
            self._anim_timer = QtCore.QTimer()
            self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.setInterval(
            core.animation_interval_ms(self.anim["speed"], self.anim["frames"])
        )
        self._anim_timer.start()
        if self.bar is not None and view_mod._alive(self.bar):
            self.bar.set_playing(True)
        log("results: animation playing")

    def stop_animation(self, keep_bar=False):
        if self._anim_timer is not None:
            try:
                self._anim_timer.stop()
            except RuntimeError:
                pass
        was = self.anim["playing"]
        self.anim["playing"] = False
        if was and self.display is not None and self.data is not None:
            self.display.set_factor(self.factor())
            if self.slice is not None:
                self._apply_slice()
            self.update_tags()
            self._redraw()
        if self.bar is not None and view_mod._alive(self.bar):
            self.bar.set_playing(False)
        del keep_bar

    def close_animation(self):
        self.stop_animation()
        self.anim["shown"] = False
        if self.bar is not None:
            try:
                self.bar.remove()
            except RuntimeError:
                pass
        self.bar = None

    def _set_speed(self, speed):
        self.anim["speed"] = float(speed)
        if self._anim_timer is not None:
            self._anim_timer.setInterval(
                core.animation_interval_ms(self.anim["speed"], self.anim["frames"])
            )

    def _set_frames(self, frames):
        self.anim["frames"] = int(frames)
        self.anim["step"] = 0
        self._set_speed(self.anim["speed"])

    def _set_mode(self, mode):
        self.anim["mode"] = mode
        self.anim["step"] = 0

    def _animate(self):
        try:
            if not self.active or self.display is None:
                self.stop_animation()
                return
            full = self.factor()
            if full == 0.0:
                full = self.factor("adjusted")  # Undeformed chosen: animate Adjusted
            frames, mode = self.anim["frames"], self.anim["mode"]
            fraction = core.animation_fraction(self.anim["step"], frames, mode)
            self.display.set_factor(full * fraction)
            if self.slice is not None and len(self.data.tets) <= 20000:
                self._apply_slice()
            self.update_tags()
            if core.animation_done(self.anim["step"], frames, mode):
                self.anim["playing"] = False
                self._anim_timer.stop()
                if self.bar is not None and view_mod._alive(self.bar):
                    self.bar.set_playing(False)
            self.anim["step"] += 1
            self._redraw()
        except Exception as exc:
            self.stop_animation()
            warn("results animation: %s" % exc)

    # -- the periodic check
    def _tick(self):
        try:
            if not self.active:
                return
            if self.gl is not None and not view_mod._alive(self.gl):
                QtCore.QTimer.singleShot(0, sync)
                return
            key = view_mod.camera_key(self.view, self.gl) if self.gl is not None else None
            if key != self._camera:
                self._camera = key
                if self.tags is not None and view_mod._alive(self.tags):
                    self.tags.relayout()
            self._ticks += 1
            if self._ticks % 6 == 0:
                self._keep_design_hidden()
        except Exception as exc:
            warn("results: %s" % exc)

    # -- glyphs (sim-ui's loads and constraints on the model)
    def _glyphs(self):
        """Fusion's results show without the setup's glyphs unless asked (Loads and
        Constraints): sim-ui's simulation_glyphs.set_visible."""
        module = _glyph_module()
        if module is None:
            return
        try:
            if self._glyphs_before is None:
                self._glyphs_before = bool(module.visible())
            module.set_visible(bool(self.loads))
        except Exception as exc:
            warn("results: loads and constraints: %s" % exc)

    def _restore_glyphs(self):
        module = _glyph_module()
        before, self._glyphs_before = self._glyphs_before, None
        if module is None or before is None:
            return
        try:
            module.set_visible(before)
        except Exception as exc:
            warn("results: loads and constraints: %s" % exc)


def _glyph_module():
    try:
        from . import simulation_glyphs

        if hasattr(simulation_glyphs, "set_visible") and hasattr(simulation_glyphs, "visible"):
            return simulation_glyphs
    except Exception:
        pass
    return None


def glyphs_available():
    return _glyph_module() is not None


def _positions(np, values, lo, hi, reverse):
    """Colour map positions (None for no value) of an array of values."""
    values = np.asarray(values, dtype=float)
    if lo is None or hi is None or hi - lo <= 1e-300:
        t = np.zeros(len(values))
    else:
        t = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
    if reverse:
        t = 1.0 - t
    return [None if v != v else float(p) for v, p in zip(values.tolist(), t.tolist())]


AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def slice_plane(session):
    """(origin, normal) of a session's slice (the normal points to the half kept)."""
    spec = session.slice or {}
    axis = spec.get("axis", "x")
    normal = AXES.get(axis, AXES["x"])
    if spec.get("flip"):
        normal = tuple(-c for c in normal)
    origin = [0.0, 0.0, 0.0]
    origin["xyz".index(axis)] = float(spec.get("offset", 0.0))
    return tuple(origin), normal


# -- what the commands open ----------------------------------------------------------------------
def open_details():
    try:
        from . import simulation_results_panels as panels

        session = current()
        if session is None:
            commands.tell(core.NO_RESULTS)
            return
        panels.details(session)
    except Exception as exc:
        warn("Results Details: %s" % exc)


def solve_again():
    """Solve the study again (out-of-date results): sim-ui's Solve when it is there, else a
    solve here with its progress in the legend."""
    try:
        session = current()
        if session is None:
            return
        available = set(Gui.listCommands())
        for name in SOLVE_COMMANDS:
            if name in available:
                Gui.runCommand(name)
                return
        from . import simulation_results_panels as panels

        panels.solve_here(session)
    except Exception as exc:
        warn("Solve: %s" % exc)


# -- commands ------------------------------------------------------------------------------------
def _shown():
    return current() is not None


def deformation_is(key):
    session = current()
    if session is None:
        return key == core.DEFORMATION_DEFAULT
    return session.deformation == key


def deform_undeformed():
    return deformation_is("undeformed")


def deform_actual():
    return deformation_is("actual")


def deform_adjusted_half():
    return deformation_is("adjusted_half")


def deform_adjusted():
    return deformation_is("adjusted")


def deform_adjusted_2():
    return deformation_is("adjusted_2")


def deform_adjusted_5():
    return deformation_is("adjusted_5")


def mesh_on():
    session = current()
    return bool(session and session.mesh)


def ghost_on():
    session = current()
    return bool(session and session.ghost)


def loads_on():
    session = current()
    return bool(session and session.loads)


def minmax_on():
    session = current()
    return session is None or bool(session.minmax)


def animation_on():
    session = current()
    return bool(session and session.anim["shown"])


class _ResultsCommand:
    """A RESULTS tab command: active while results show."""

    menu = ""
    tip = ""
    icon = "workspace_simulation"

    def GetResources(self):
        return {"MenuText": self.menu, "ToolTip": self.tip, "Pixmap": ui_icon_path(self.icon)}

    def IsActive(self):
        return _shown()

    def Activated(self):
        try:
            session = current()
            if session is None:
                commands.tell(core.NO_RESULTS)
                return
            self.run(session)
        except Exception as exc:
            warn("%s: %s" % (self.menu, exc))

    def run(self, session):
        pass


def _deform_command(key, icon):
    class DeformCommand(_ResultsCommand):
        menu = core.deformation_name(key)

        def run(self, session):
            session.set_deformation(key)

    DeformCommand.icon = icon
    DeformCommand.tip = {
        "undeformed": "Show the results on the shape the part has without the loads",
        "actual": "Show the bend at its true size",
        "adjusted_half": "Exaggerate the bend half as much as Adjusted",
        "adjusted": "Exaggerate the bend so the largest movement is 5 % of the model size",
        "adjusted_2": "Exaggerate the bend twice as much as Adjusted",
        "adjusted_5": "Exaggerate the bend five times as much as Adjusted",
    }[key]
    return DeformCommand


class AnimateCommand(_ResultsCommand):
    menu = "Animate"
    tip = "Play the part bending from its unloaded shape to its loaded one (again to stop)"
    icon = "simr_animate"

    def run(self, session):
        session.toggle_animation()


class DetailsCommand(_ResultsCommand):
    menu = "Results Details"
    tip = "What the results mean: the lowest safety factor against your target, per body"
    icon = "simr_details"

    def run(self, session):
        open_details()


class ReportCommand(_ResultsCommand):
    menu = "Report"
    tip = "Write the study's setup, results and pictures to an HTML report"
    icon = "simr_report"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.report(session)


class _ToggleCommand(_ResultsCommand):
    option = ""

    def run(self, session):
        session.set_option(self.option, not getattr(session, self.option))
        log("results: %s %s" % (self.menu, "on" if getattr(session, self.option) else "off"))


class MeshCommand(_ToggleCommand):
    menu = "Show Mesh"
    tip = "Show the mesh's element edges on the result"
    icon = "simr_mesh"
    option = "mesh"


class UndeformedCommand(_ToggleCommand):
    menu = "Undeformed Model"
    tip = "Show the part's unloaded shape, see-through, around the bent result"
    icon = "simr_ghost"
    option = "ghost"


class LoadsCommand(_ToggleCommand):
    menu = "Loads and Constraints"
    tip = "Show the loads and constraints on the result"
    icon = "simr_loads"
    option = "loads"

    def IsActive(self):
        return _shown() and glyphs_available()


class MinMaxCommand(_ToggleCommand):
    menu = "Show Min/Max"
    tip = "Tags at the places of the lowest and the highest value"
    icon = "simr_minmax"
    option = "minmax"


class ProbesCommand(_ResultsCommand):
    menu = "Surface Probes"
    tip = "Click on the result to read its value there (as many as you like)"
    icon = "simr_probe"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.probes(session)


class SliceCommand(_ResultsCommand):
    menu = "Slice Plane"
    tip = "Cut the result with a plane to see inside it"
    icon = "simr_slice"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.slice_panel(session)


class ReactionsCommand(_ResultsCommand):
    menu = "Reaction Force"
    tip = "The force each constraint takes to hold the part"
    icon = "simr_reaction"

    def IsActive(self):
        session = current()
        return session is not None and results_data.reactions(session.study) is not None

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.reactions(session)


class FinishCommand(_ResultsCommand):
    menu = "Finish Results"
    tip = "Back to the study's setup (the bodies show again)"
    icon = "simr_finish"

    def run(self, session):
        finish()


COMMANDS = {
    "SciForge_SimResultsAnimate": AnimateCommand,
    "SciForge_SimResultsDetails": DetailsCommand,
    "SciForge_SimResultsReport": ReportCommand,
    "SciForge_SimResultsUndeformed": _deform_command("undeformed", "simr_deform_none"),
    "SciForge_SimResultsActual": _deform_command("actual", "simr_deform_actual"),
    "SciForge_SimResultsAdjustedHalf": _deform_command("adjusted_half", "simr_deform_half"),
    "SciForge_SimResultsAdjusted": _deform_command("adjusted", "simr_deform_adjusted"),
    "SciForge_SimResultsAdjusted2": _deform_command("adjusted_2", "simr_deform_x2"),
    "SciForge_SimResultsAdjusted5": _deform_command("adjusted_5", "simr_deform_x5"),
    "SciForge_SimResultsMesh": MeshCommand,
    "SciForge_SimResultsGhost": UndeformedCommand,
    "SciForge_SimResultsLoads": LoadsCommand,
    "SciForge_SimResultsMinMax": MinMaxCommand,
    "SciForge_SimResultsProbes": ProbesCommand,
    "SciForge_SimResultsSlice": SliceCommand,
    "SciForge_SimResultsReactions": ReactionsCommand,
    "SciForge_SimResultsFinish": FinishCommand,
}


try:  # hook the tab watcher up once the ribbon exists (this module loads before it)
    if App.GuiUp:
        WATCH["timer"] = QtCore.QTimer()
        WATCH["timer"].setInterval(1000)
        WATCH["timer"].timeout.connect(_poll_watch)
        WATCH["timer"].start()
except Exception as exc:  # noqa: BLE001
    warn("results: %s" % exc)

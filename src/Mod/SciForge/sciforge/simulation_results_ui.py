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
COMPARE = {"session": None}  # RESULT TOOLS > Compare while it shows (CompareSession)
WATCH = {
    "ribbon": None,
    "area": None,
    "observer": None,
    "timer": None,
    "syncing": False,
    "shown_again": True,  # something may have shown a hidden object again (checked soon)
}
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
            dropped = results_data.results_dropped(study)
            commands.tell(results_data.DROPPED if dropped else core.NO_RESULTS)
            return False
        doc = study.Document
        if App.ActiveDocument is not doc:
            # another design is in front (its solve ended meanwhile): its RESULTS tab shows them
            # when it is in front again
            session = SESSIONS.get(doc.Name)
            if session is not None and session.study_name != study.Name:
                session.deactivate()
                SESSIONS.pop(doc.Name, None)
            return False
        if _ui_active_study(doc) is not study:
            try:
                from . import simulation_ui

                simulation_ui.set_active_study(study)
            except Exception:
                pass
        compare = COMPARE["session"]
        if compare is not None and compare.doc_name == doc.Name:
            # (a solve ended while Compare showed: its study's results take the view)
            COMPARE["session"] = None
            compare.deactivate()
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
        compare, COMPARE["session"] = COMPARE["session"], None
        if compare is not None:
            compare.deactivate()
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
        compare = COMPARE["session"]
        if compare is not None:
            ribbon = _ribbon()
            here = (
                ribbon is not None
                and _sim_on()
                and _current_tab(ribbon) == RESULTS_TAB
                and App.ActiveDocument is not None
                and App.ActiveDocument.Name == compare.doc_name
                and compare.alive()
            )
            if here:
                shown = ACTIVE["session"]
                if shown is not None:
                    shown.deactivate()
                    ACTIVE["session"] = None
                compare.activate()
                refresh_tab()
                return
            compare.deactivate()
            COMPARE["session"] = None
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


def _hide_again(session):
    """Objects shown again under the results hidden again: every object of the design when
    the document observer saw one made or shown, else the next few hidden ones in turn."""
    if WATCH["shown_again"]:
        WATCH["shown_again"] = False
        Session._keep_design_hidden(session)
    else:
        Session._keep_design_hidden(session, part=60)


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

    def slotChangedDocument(self, doc, prop):
        try:
            if prop == "UnitSystem":  # Document Settings > Units: the legend follows
                _later(doc, "units")
        except Exception:
            pass

    def slotDeletedObject(self, obj):
        try:
            if simulation.is_study(obj) or simulation.is_simulation_object(obj):
                _later(obj.Document, "sync")
        except Exception:
            pass

    # what may show a hidden object again while the results show: an object made or brought
    # back by Undo, a Visibility switched on (the results' timer then hides the design again;
    # a display mode change, which tells only the Gui side, is found by the timer's look at a
    # few hidden objects in turn;
    # a Gui document observer made FreeCAD fail to create FEM objects: "Cannot add static
    # property")
    def slotCreatedObject(self, _obj):
        WATCH["shown_again"] = True

    def slotChangedObject(self, _obj, prop):
        if prop == "Visibility":
            WATCH["shown_again"] = True

    def slotDeletedDocument(self, doc):
        try:
            name = doc.Name
        except Exception:
            return
        try:
            session = SESSIONS.pop(name, None)
            if session is not None:
                if ACTIVE["session"] is session:
                    ACTIVE["session"] = None
                session.drop()
            compare = COMPARE["session"]
            if compare is not None and compare.doc_name == name:
                COMPARE["session"] = None
                try:
                    if compare._timer is not None:
                        compare._timer.stop()
                except RuntimeError:
                    pass
                compare.active = False
            results_data.forget(name)
        except Exception as exc:
            warn("results: %s" % exc)


_PENDING = {"status": set(), "units": set(), "sync": False, "armed": False}


def _later(doc, what):
    try:
        name = doc.Name
    except Exception:
        return
    if what in ("status", "units"):
        _PENDING[what].add(name)
    else:
        _PENDING["sync"] = True
    if not _PENDING["armed"]:
        _PENDING["armed"] = True
        QtCore.QTimer.singleShot(80, _run_later)


def _run_later():
    _PENDING["armed"] = False
    names, _PENDING["status"] = _PENDING["status"], set()
    units, _PENDING["units"] = _PENDING["units"], set()
    again, _PENDING["sync"] = _PENDING["sync"], False
    try:
        if again:
            sync()
        session = current()
        if session is not None and session.doc_name in names:
            session.refresh_status()
        if session is not None and session.doc_name in units:
            session.apply()
            session._panels_follow()
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
        self.ranges = {}  # result key -> (lo, hi) set in Legend Min/Max (base unit)
        self.grey_outside = False  # values beyond the legend's range drawn grey
        self.targets = core.DEFAULT_TARGETS
        self.probes = []  # {"node": index} or {"point": (x, y, z), "values": {...}}
        self.points = []  # Point Probes: {"at": (x, y, z) on the unloaded part, "where": ...}
        self.hover = None  # the probe under the mouse while a probe tool is open (not kept)
        self.slice = None  # {"axis": "x"|"y"|"z", "offset": mm, "flip": bool, "style": ...}
        self.iso_on = False  # the iso-surface of the result shown
        self.iso_levels = {}  # result key -> the iso-surface's value (base unit)
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
        self.reaction_tags = False  # Reaction Force's tags at the constraints (window open)
        self.shown_bodies = None  # indices of the study's bodies drawn (None: all of them)
        self._shown_key = None
        self._extreme_cache = None

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
        for view in _views_of(gui, self.view):  # (every pane of Multiple Views)
            self.display.attach(view)
        self._hide_design()
        if gl is not None:
            self.legend = view_mod.Legend(
                gl,
                {
                    "result": self.set_result,
                    "unit": self.set_unit,
                    "details": open_details,
                    "solve": solve_again,
                    "banded": lambda on: self.set_option("banded", on),
                    "range": open_range,
                    "span": lambda lo, hi: self.set_range((lo, hi)),
                    "span_reset": lambda: self.set_range(None),
                    "grey": lambda on: self.set_option("grey_outside", on),
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
        self.shown_bodies = self._bodies_shown()
        self._shown_key = self._visibility_key()
        self.display = self._new_display()
        self.probes = []
        for point in self.points:  # (kept: they are places of the part, found in the new mesh)
            point.pop("where", None)
        if self.slice is not None:
            self.slice = dict(self.slice)

    # -- the bodies shown (Fusion: hide a body in the browser to see the results inside)
    def _visibility_key(self):
        if self.data is None or self.doc is None:
            return None
        key = []
        for number, body in enumerate(self.data.bodies()):
            try:
                name = body.Name
            except Exception:  # deleted since the solve: its results stay drawn
                key.append(("#%d" % number, True))
                continue
            try:
                key.append((name, bool(body.ViewObject.Visibility)))
            except Exception:
                key.append((name, True))
        return tuple(key)

    def _bodies_shown(self):
        """Indices (into the study's bodies) of the ones whose eye is on; None when all are."""
        key = self._visibility_key() or ()
        shown = [k for k, (_name, visible) in enumerate(key) if visible]
        return None if len(shown) == len(key) else shown

    def _new_display(self):
        if self.shown_bodies is None:
            return view_mod.ResultDisplay(self.data)
        _rows, surface, _straight = self.data.subset(self.shown_bodies)
        return view_mod.ResultDisplay(self.data, surface)

    def straight(self):
        """The straight tetrahedra of the bodies shown (slices and iso-surfaces)."""
        if self.shown_bodies is None:
            return self.data.straight()
        return self.data.subset(self.shown_bodies)[2]

    def element_count(self):
        if self.shown_bodies is None:
            return len(self.data.tets)
        return len(self.data.subset(self.shown_bodies)[0])

    def _follow_bodies(self):
        """A body's eye switched in the browser: its results go (or come back)."""
        key = self._visibility_key()
        if key == self._shown_key or self.data is None:
            return
        self._shown_key = key
        shown = self._bodies_shown()
        if shown == self.shown_bodies:
            return
        self.shown_bodies = shown
        old = self.display
        views = list(old.views) if old is not None else []
        if old is not None:
            old.detach()
        self.display = self._new_display()
        for view in views:
            self.display.attach(view)
        self.apply()
        labels = {}
        for body in self.data.bodies():
            try:
                labels[body.Name] = body.Label
            except Exception:
                continue
        names = [labels.get(n, n) for n, visible in key if visible]
        log("results: bodies shown %s" % (", ".join(names) if names else "none"))

    def deactivate(self):
        self.stop_animation(keep_bar=True)
        for panel in list(self.panels):
            try:
                panel.close()
            except Exception:
                pass
        self.panels = []
        try:  # its windows go with it (Results Details, Solver Data...)
            from . import simulation_results_panels as panels

            panels.close_all(self)
        except Exception as exc:
            warn("results: %s" % exc)
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
                if vo is None:
                    continue
                # (a simulation object shown on SETUP too: the mesh sim-ui's Show Mesh draws)
                switch = vo.SwitchNode
                which = switch.whichChild.getValue()
                if which != -1:
                    self.hidden[obj.Name] = which
                    switch.whichChild = -1
            except Exception:
                continue

    def _keep_design_hidden(self, part=None):
        """What FreeCAD shows again while the results show (a display mode change, a body
        brought back by Undo, a new object) is hidden again; deleted objects are forgotten.
        part: look at only that many of the hidden objects, the next ones in turn (the
        periodic look: a design of 800 objects took 56 ms each time); None: every object of
        the design (the document observer said something was made or shown)."""
        doc = self.doc
        if doc is None:
            return
        if part is None:
            for name in list(self.hidden):
                if doc.getObject(name) is None:
                    self.hidden.pop(name, None)
            Session._hide_design(self)  # (Compare's session borrows it too)
            return
        names = sorted(self.hidden)
        if not names:
            return
        start = getattr(self, "_hide_cursor", 0) % len(names)
        for name in (names[start:] + names[:start])[:part]:
            obj = doc.getObject(name)
            try:
                if obj is None or obj.ViewObject is None:
                    self.hidden.pop(name, None)
                    continue
                switch = obj.ViewObject.SwitchNode
                which = switch.whichChild.getValue()
                if which != -1:  # (shown again: a display mode change...)
                    self.hidden[name] = which
                    switch.whichChild = -1
            except Exception:
                self.hidden.pop(name, None)
        self._hide_cursor = start + part

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
        """The unit a result is shown in: the one chosen in the legend, else the design's
        (Document Settings > Units: an inch design shows inches and psi)."""
        result = result or self.result
        kind = core.kind_of(result)
        unit = self.units.get(kind)
        if unit is not None and core.unit_ok(result, unit):
            return unit
        doc = self.doc
        length = results_data.design_length_unit(doc) if doc is not None else "mm"
        return core.design_unit(result, length)

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
        lo, hi, reverse = self.scale()
        surface_values = values[self.display.nodes]
        self.display.set_positions(_positions(np, surface_values, lo, hi, reverse, self._grey()))
        bands = self.result == "safety" and self.bands
        self.display.set_texture(
            core.texture_rows(targets=self.targets) if bands else core.texture_rows(self.banded)
        )
        if not self.anim["playing"]:
            self.display.set_factor(self.factor())
        self.display.set_mesh(self.mesh)
        self.display.set_ghost(self.ghost and self.factor() != 0.0)
        self._apply_slice()
        self._apply_iso()
        info = core.legend(
            self.result,
            stats,
            self.unit(),
            banded=self.banded,
            targets=self.targets if bands else None,
            span=self.ranges.get(self.result),
        )
        info["targets"] = self.targets
        info["grey"] = self._grey()
        if self.result == "safety":
            info["verdict"] = core.short_verdict(
                results_data.min_safety(self.study), self.targets[0], self.targets[1]
            )
        self.legend_info = info
        if self.legend is not None and view_mod._alive(self.legend):
            self.legend.fill(info, self._study_text(), self.out_of_date, self._deform_text())
        self.update_tags()
        self._glyphs()
        self._redraw()

    def _grey(self):
        """Values beyond the legend's range grey (not for the safety factor)."""
        return bool(self.grey_outside) and self.result != "safety"

    def scale(self, result=None):
        """(lo, hi, reverse) of the colours of a result as drawn: its own min .. max (the
        safety factor 0 .. 15), or the range set in Legend Min/Max."""
        result = result or self.result
        stats = self.data.stats(result)
        lo, hi, reverse = core.scale(result, stats.get("min"), stats.get("max"))
        span = self.ranges.get(result)
        if span is not None and result != "safety":
            lo, hi = core.span_ok(span, lo, hi)
        return lo, hi, reverse

    def set_range(self, span):
        """Legend Min/Max: the colours of the result shown run over `span` (lo, hi in the
        base unit); None goes back to the result's own min and max."""
        if self.result == "safety":
            return
        if span is None:
            self.ranges.pop(self.result, None)
        else:
            self.ranges[self.result] = core.span_ok(span)
        self.apply()
        log("results: legend range %s" % ("reset" if span is None else "set"))

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
        return "Deformation: %s (%s x)" % (name, core.fmt(f, 3))

    def update_tags(self):
        tags = []
        np = view_mod._np()
        if self.data is not None and self.display is not None:
            values = self.data.values(self.result)
            stats = self.data.stats(self.result)
            lo, hi, reverse = self.scale()
            unit = self.unit()
            if self.minmax:
                extremes = self._extremes(np, values, stats)
                for kind in ("max", "min"):
                    index, value = extremes[kind]
                    if index is None or index < 0:
                        continue
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
                tag = self._probe_tag(probe, values, unit, (lo, hi, reverse))
                if tag is not None:
                    tags.append(tag)
            for number, point in enumerate(self.points, 1):
                tags.append(self._point_tag(point, "P%d: " % number, unit, (lo, hi, reverse)))
            if self.reaction_tags:
                tags.extend(self._reaction_tags())
            hover = self.hover
            if hover is not None:
                if "at" in hover:
                    tag = self._point_tag(hover, "", unit, (lo, hi, reverse))
                else:
                    tag = self._probe_tag(hover, values, unit, (lo, hi, reverse))
                if tag is not None:
                    tag["kind"] = "hover"
                    tags.append(tag)
            if self.display.clipped() and self.slice is not None:
                tags = self._tags_kept(np, tags)
        del np
        self.tag_list = tags
        if self.tags is not None and view_mod._alive(self.tags):
            self.tags.set_tags(tags)

    def _extremes(self, np, values, stats):
        """{"min": (node, value), "max": (node, value)} of the result drawn: the result's own, or
        with a body's eye off those of the bodies shown (a tag never points at a hidden body;
        the legend keeps the whole study's range)."""
        out = {kind: (stats.get("%s_index" % kind), stats.get(kind)) for kind in ("min", "max")}
        if self.shown_bodies is None or self.data is None:
            return out
        key = (tuple(self.shown_bodies), self.result, self.data.stamp)
        if self._extreme_cache is not None and self._extreme_cache[0] == key:
            return self._extreme_cache[1]
        rows = self.data.subset(self.shown_bodies)[0]
        nodes = np.unique(self.data.tets[rows].reshape(-1))
        found = np.asarray(values, dtype=float)[nodes]
        ok = np.isfinite(found)
        if ok.any():
            nodes, found = nodes[ok], found[ok]
            low, high = int(np.argmin(found)), int(np.argmax(found))
            out = {
                "min": (int(nodes[low]), float(found[low])),
                "max": (int(nodes[high]), float(found[high])),
            }
        elif not len(nodes):  # (every body's eye off: nothing drawn, no tag)
            out = {"min": (None, None), "max": (None, None)}
        self._extreme_cache = (key, out)
        return out

    def _tags_kept(self, np, tags):
        """The tags on the half of the result the slice keeps (the others would float where the
        part is cut away)."""
        origin, normal = slice_plane(self)
        n = np.asarray(normal, dtype=float)
        o = np.asarray(origin, dtype=float) + np.asarray(self.display.offset, dtype=float)
        tol = 1e-6 * float(self.data.diagonal or 1.0)
        return [t for t in tags if float((np.asarray(t["point"], dtype=float) - o) @ n) >= -tol]

    def _probe_tag(self, probe, values, unit, scale):
        """The tag of a surface probe ({"node"} or a point of the cut face with its values)."""
        lo, hi, reverse = scale
        if "node" in probe:
            index = probe["node"]
            value = float(values[index])
            point = tuple(float(c) for c in self.display.node_place(index))
        else:
            value = probe.get("values", {}).get(self.result)
            point = probe["point"]
            if value is None:
                return None
        text = "-" if value != value else core.with_unit(core.convert(value, unit), unit)
        return {
            "kind": "probe",
            "node": probe.get("node"),
            "value": value,
            "point": point,
            "text": text,
            "colour": core.map_colour(core.position(value, lo, hi, reverse)),
        }

    def _reaction_tags(self):
        """Reaction Force: a tag at each constraint with the force it takes (total, N)."""
        study = self.study
        found = results_data.reactions(study) if study is not None else None
        if not found:
            return []
        places = results_data.reaction_places(study)
        out = []
        for label, (fx, fy, fz) in sorted(found.items()):
            place = places.get(label)
            if place is None:
                continue
            total = (fx * fx + fy * fy + fz * fz) ** 0.5
            point = [a + b for a, b in zip(place, self.display.offset)]
            out.append(
                {
                    "kind": "reaction",
                    "value": total,
                    "point": tuple(float(c) for c in point),
                    "text": "%s: %s N" % (label, core.fmt(total)),
                    "colour": (0.55, 0.78, 1.0),
                }
            )
        return out

    def _point_tag(self, point, prefix, unit, scale):
        """The tag of a Point Probe (`prefix`: its name)."""
        lo, hi, reverse = scale
        value = self.point_value(point)
        if value is None:
            text, colour = prefix + "outside the part", core.NO_VALUE
        elif value != value:
            text, colour = prefix + "-", core.NO_VALUE
        else:
            text = prefix + core.with_unit(core.convert(value, unit), unit)
            colour = core.map_colour(core.position(value, lo, hi, reverse))
        return {
            "kind": "point",
            "value": value,
            "point": tuple(float(c) for c in self.point_place(point)),
            "text": text,
            "colour": colour,
        }

    def set_hover(self, x=None, y=None, inside=False):
        """The value under the Coin pixel (x, y) while a probe tool is open (Fusion shows it as
        the mouse moves; a click places the probe): `inside` for Point Probes. None (or off
        the result) takes it away."""
        hover = None
        if x is not None and self.display is not None and self.view is not None:
            if inside:
                rest = self.pick_rest_point(x, y)
                hover = {"at": tuple(float(c) for c in rest)} if rest is not None else None
            else:
                hover = self.probe_at(x, y)
        if hover is None and self.hover is None:
            return
        self.hover = hover
        self.update_tags()

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
        self._panels_follow()
        log("results: %s" % core.result_name(key))

    def set_unit(self, unit):
        if not core.unit_ok(self.result, unit):
            return
        self.units[core.kind_of(self.result)] = unit
        self.apply()
        self._panels_follow()

    def _panels_follow(self):
        """The open probe and iso-surface panels show the result (and unit) now chosen."""
        for panel in list(self.panels):
            follow = getattr(panel, "result_changed", None)
            if follow is None:
                continue
            try:
                follow()
            except Exception as exc:
                warn("results: %s" % exc)

    def set_deformation(self, key):
        if key not in [k for k, _n in core.deformations()]:
            return
        self.deformation = key
        if self.anim["playing"]:
            self.anim["step"] = 0
        self.apply()
        self._panels_follow()
        log("results: deformation %s" % core.deformation_name(key))

    def set_option(self, name, on):
        setattr(self, name, bool(on))
        self.apply()

    # -- probes
    def add_probe_at(self, x, y):
        """A surface probe where the Coin pixel (x, y) meets the result (the nearest node of
        the face it meets; on the slice's cut face, the value there). Returns the probe or
        None."""
        probe = self.probe_at(x, y)
        if probe is None:
            return None
        self.probes.append(probe)
        self.update_tags()
        self._redraw()
        return probe

    def remove_probe(self, index):
        if 0 <= index < len(self.probes):
            del self.probes[index]
            self.update_tags()
            self._redraw()

    def probe_at(self, x, y):
        """The surface probe the Coin pixel (x, y) would place (not kept), or None."""
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
            rest = self.display.cap_rest[3 * tri : 3 * tri + 3]
            probe["values"] = self._values_at(np.asarray(weights) @ rest)
        return probe

    def _values_at(self, rest):
        """Every result's value at a point of the unloaded part (interpolated in the mesh)."""
        out = {}
        where = self.data.locate(rest)
        if where is None:
            return out
        for key in core.result_keys():
            try:
                out[key] = self.data.at(where, key)
            except Exception:
                continue
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
        """The slice plane: "clip" cuts the result away on one side and colours the cut face;
        "slice" shows the cut face inside the whole result drawn see-through."""
        display = self.display
        if self.slice is None:
            display.set_clip(None, None)
            display.set_cap([], [], [])
        else:
            origin, normal = slice_plane(self)
            if self.slice.get("style", "clip") == "slice":
                display.set_clip(None, None)
            else:
                display.set_clip(origin, normal)
            self._cut(origin, normal)
        display.set_see_through(self.see_through())

    def see_through(self):
        """The result is drawn see-through around a slice shown alone or an iso-surface."""
        alone = self.slice is not None and self.slice.get("style", "clip") == "slice"
        return bool(alone or self.iso_on)

    def _cut(self, origin, normal):
        np = view_mod._np()
        data = self.data
        values = data.values(self.result)
        lo, hi, reverse = self.scale()
        tris, vals, carried, owners = core.cut(
            data.deformed(self.display.factor),
            values,
            self.straight(),
            origin,
            normal,
            carry=np.hstack([data.points, data.displacement]),
            owners=True,
        )
        rest = carried[:, :, :3] if carried is not None else None
        flat_vals = vals.ravel()
        positions = (
            _positions(np, flat_vals, lo, hi, reverse, self._grey()) if len(flat_vals) else []
        )
        self.display.set_cap(tris, flat_vals, positions, normal, rest=rest)
        lines = (self.slice or {}).get("lines")
        self.display.set_cap_lines(
            core.cut_lines(tris, owners, self.element_count()) if lines and len(tris) else []
        )
        if (self.slice or {}).get("vectors") and len(tris):
            # the displacement's arrows, coloured like the result where they stand
            centres = tris.mean(axis=1)
            moved = carried[:, :, 3:].mean(axis=1)
            middle = vals.mean(axis=1)
            chosen, segments, arrow = core.vector_arrows(
                centres, moved, normal, 0.04 * data.diagonal, 0.035 * data.diagonal
            )
            colours = []
            if len(chosen):
                at = _positions(np, middle[chosen], lo, hi, reverse, self._grey())
                per_arrow = [core.map_colour(t) if t is not None else core.NO_VALUE for t in at]
                colours = [per_arrow[a] for a in arrow]
            self.display.set_vectors(segments, colours, len(chosen))
        else:
            self.display.set_vectors([])

    # -- iso-surface
    def iso_level(self, result=None):
        """The iso-surface's value for a result (base unit): the one set, else half way
        between the result's lowest and highest."""
        result = result or self.result
        level = self.iso_levels.get(result)
        if level is None:
            lo, hi, _reverse = self.scale(result)
            stats = self.data.stats(result)
            low = stats.get("min") if stats.get("min") is not None else lo
            high = stats.get("max") if stats.get("max") is not None else hi
            if result == "safety":
                high = min(high, hi)
            level = core.iso_default(low, high)
        return float(level)

    def set_iso(self, level):
        """The iso-surface at `level` (base unit) of the result shown; None takes it away."""
        if level is None:
            self.iso_on = False
        else:
            self.iso_on = True
            self.iso_levels[self.result] = float(level)
        self.apply()

    def _apply_iso(self):
        display = self.display
        if not self.iso_on:
            display.set_iso([])
            display.set_see_through(self.see_through())
            return
        data = self.data
        level = self.iso_level()
        tris, _vals, rest = core.iso_surface(
            data.deformed(display.factor),
            data.values(self.result),
            self.straight(),
            level,
            carry=data.points,
        )
        lo, hi, reverse = self.scale()
        colour = core.map_colour(core.position(level, lo, hi, reverse), self.banded)
        display.set_iso(tris, colour, rest=rest)
        display.set_see_through(self.see_through())

    # -- point probes (Fusion: values inside the part, placed on a visible surface - the result,
    # a slice's cut face or the iso-surface - then moved by their X, Y, Z)
    def pick_rest_point(self, x, y):
        """Where the Coin pixel (x, y) meets what is drawn (a slice's cut face or the
        iso-surface first when the result is see-through), as a point of the unloaded part;
        None when it meets nothing."""
        if self.display is None or self.view is None:
            return None
        np = view_mod._np()
        display = self.display
        origin, direction = view_mod.ray_coin(self.view, x, y)
        hits = []  # (distance, rest point)
        for shown, pts, rest in (
            (display.cap_shown(), display.cap_points, display.cap_rest),
            (display.iso_shown(), display.iso_points, display.iso_rest),
        ):
            if not shown or not len(pts):
                continue
            hit = core.ray_hit(origin, direction, pts, np.arange(len(pts)).reshape((-1, 3)))
            if hit is not None:
                t, tri, weights = hit
                hits.append((t, np.asarray(weights) @ rest[3 * tri : 3 * tri + 3]))
        if not hits or not display.see_through():
            pts = display.surface_points()
            tris = display.triangles
            if display.clipped() and self.slice is not None:
                origin_p, normal = slice_plane(self)
                keep = (pts[tris].mean(axis=1) - np.asarray(origin_p)) @ np.asarray(normal) >= -1e-6
                tris = tris[keep]
            hit = core.ray_hit(origin, direction, pts, tris)
            if hit is not None:
                t, tri, weights = hit
                corners = display.nodes[tris[tri]]
                hits.append((t, np.asarray(weights) @ self.data.points[corners]))
        if not hits:
            return None
        return min(hits, key=lambda h: h[0])[1]

    def add_point_at(self, x, y):
        """A Point Probe where the Coin pixel (x, y) meets what is drawn, or None."""
        rest = self.pick_rest_point(x, y)
        if rest is None:
            return None
        return self.add_point(rest)

    def add_point(self, at):
        point = {"at": tuple(float(c) for c in at)}
        self.points.append(point)
        self.update_tags()
        self._redraw()
        return point

    def move_point(self, index, at):
        """Point Probe `index` to (x, y, z) of the unloaded part (its X, Y, Z typed)."""
        if not 0 <= index < len(self.points):
            return
        self.points[index] = {"at": tuple(float(c) for c in at)}
        self.update_tags()
        self._redraw()

    def remove_point(self, index):
        if 0 <= index < len(self.points):
            del self.points[index]
            self.update_tags()
            self._redraw()

    def clear_points(self):
        self.points = []
        self.update_tags()
        self._redraw()

    def point_where(self, point):
        if "where" not in point:
            point["where"] = self.data.locate(point["at"]) if self.data is not None else None
        return point["where"]

    def point_value(self, point, key=None):
        """A Point Probe's value of a result (base unit; NaN where it has none), None when it
        is outside the part."""
        where = self.point_where(point)
        if where is None:
            return None
        return self.data.at(where, key or self.result)

    def point_place(self, point):
        """Where a Point Probe is drawn now (it moves with the part as it is drawn bent)."""
        np = view_mod._np()
        at = np.asarray(point["at"], dtype=float)
        where = self.point_where(point)
        offset = self.display.offset if self.display is not None else 0.0
        if where is None or self.display is None:
            return at + offset
        return at + self.display.factor * self.data.moved(where) + offset

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
                "save": self._save_animation,
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
            if self.iso_on:
                self._apply_iso()
            self.update_tags()
            self._redraw()
        if self.bar is not None and view_mod._alive(self.bar):
            self.bar.set_playing(False)
        del keep_bar

    def _save_animation(self):
        from . import simulation_results_panels as panels

        panels.save_animation_dialog(self)

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
            if self.iso_on and len(self.data.tets) <= 20000:
                self._apply_iso()
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
                _hide_again(self)
                self._follow_bodies()
            if _picking_dialog_open():
                # a command that picks faces of the design (a load or constraint edited from the
                # browser, Local Mesh Control, Measure) opened: the model is needed, back to
                # SETUP
                log("results put away: a command needs the model")
                QtCore.QTimer.singleShot(0, _to_setup)
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


def _picking_dialog_open():
    """A task dialog that picks on the design (pickpanel.PickPanel, Measure) is open, not one
    of ours: the design's bodies are needed, and they are hidden on RESULTS."""
    try:
        from . import pickpanel, taskui

        current = taskui.current()
        if current is None:
            return False
        if isinstance(current, pickpanel.PickPanel):
            return True
        try:
            from . import measure_ui

            return isinstance(current, measure_ui.MeasurePanel)
        except Exception:
            return False
    except Exception:
        return False


def _to_setup():
    try:
        ribbon = _ribbon()
        if ribbon is not None and _current_tab(ribbon) == RESULTS_TAB:
            ribbon.select_tab(SETUP_TAB)
            commands.tell("This command works on the model: the results are put away (RESULTS).")
        sync()
    except Exception as exc:
        warn("results: %s" % exc)


def _views_of(gui, active):
    """The 3D views of a design, the active one first."""
    views = [active]
    try:
        for view in gui.mdiViewsOfType("Gui::View3DInventor"):
            if view is not active and hasattr(view, "getSceneGraph"):
                views.append(view)
    except Exception:
        pass
    return views


def glyphs_available():
    return _glyph_module() is not None


def _positions(np, values, lo, hi, reverse, grey_outside=False):
    """Colour map positions (None for no value, drawn grey) of an array of values; with
    `grey_outside` the values beyond lo .. hi have none either."""
    values = np.asarray(values, dtype=float)
    if lo is None or hi is None or hi - lo <= 1e-300:
        t = np.zeros(len(values))
        grey_outside = False
    else:
        raw = (values - lo) / (hi - lo)
        t = np.clip(raw, 0.0, 1.0)
    if reverse:
        t = 1.0 - t
    if grey_outside:
        with np.errstate(invalid="ignore"):
            outside = (raw < -1e-9) | (raw > 1.0 + 1e-9)
        return [
            None if v != v or out else float(p)
            for v, p, out in zip(values.tolist(), t.tolist(), outside.tolist())
        ]
    return [None if v != v else float(p) for v, p in zip(values.tolist(), t.tolist())]


AXES = core.SLICE_AXES


def slice_plane(session):
    """(origin, normal) of a session's slice (the normal points to the half kept)."""
    return core.slice_plane(session.slice)


def face_at(session, x, y):
    """The outward normal (on the unloaded part) of the result's face under the Coin pixel
    (x, y), or None (Slice Plane: parallel to a face clicked)."""
    display = session.display
    if display is None or session.view is None:
        return None
    np = view_mod._np()
    origin, direction = view_mod.ray_coin(session.view, x, y)
    pts = display.surface_points()
    tris = display.triangles
    if display.clipped() and session.slice is not None:
        origin_p, normal = slice_plane(session)
        keep = (pts[tris].mean(axis=1) - np.asarray(origin_p)) @ np.asarray(normal) >= -1e-6
        tris = tris[keep]
    hit = core.ray_hit(origin, direction, pts, tris)
    if hit is None:
        return None
    corners = session.data.points[display.nodes[tris[hit[1]]]]
    normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    length = float(np.linalg.norm(normal))
    if length < 1e-12:
        return None
    normal = normal / length
    normal[np.abs(normal) < 1e-9] = 0.0
    return tuple(float(c) for c in normal)


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


def open_range():
    try:
        from . import simulation_results_panels as panels

        session = current()
        if session is None:
            commands.tell(core.NO_RESULTS)
            return
        if session.result == "safety":
            commands.tell(
                "The safety factor's legend always runs from 0 to 15: choose another result to "
                "set its range."
            )
            return
        panels.legend_range(session)
    except Exception as exc:
        warn("Legend Min/Max: %s" % exc)


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


def compare_on():
    session = COMPARE["session"]
    return session is not None and session.active


def start_compare(studies):
    """Compare: the studies' results in split views (one pane each), on one colour scale (2 to 4
    studies of the design in front, each with results)."""
    try:
        studies = [s for s in studies if results_data.has_results(s)][: core.COMPARE_MOST]
        if len(studies) < 2:
            commands.tell("Compare needs two studies with results: solve another study first.")
            return False
        old = COMPARE["session"]
        if old is not None:
            old.deactivate()
        COMPARE["session"] = CompareSession(studies)
        ensure_watch()
        _select_results_tab()
        sync()
        log("results: compare %d studies" % len(studies))
        return compare_on()
    except Exception as exc:
        warn("Compare: %s" % exc)
        return False


def finish_compare():
    try:
        session, COMPARE["session"] = COMPARE["session"], None
        if session is not None:
            session.deactivate()
        sync()
        log("results: compare finished")
    except Exception as exc:
        warn("Compare: %s" % exc)


class CompareSession:
    """Several studies' results at once (Fusion's Compare): the 3D view split in panes, one
    study in each (two side by side; three or four in four panes), their cameras turning
    together; one colour scale for all of them (the same colour is the same value), the same
    deformation scale (the largest movement of them all drawn at Adjusted's size, so a bigger
    bend looks bigger), a tag with each study's name, min and max. When the view cannot be split
    the studies lie side by side in the one view. No probes or slices meanwhile (Fusion's
    Compare has none either)."""

    LAYOUTS = {2: "Two Views Horizontal", 3: "Multiple Views", 4: "Multiple Views"}

    def __init__(self, studies):
        self.doc_name = studies[0].Document.Name
        self.study_names = [s.Name for s in studies]
        self.result = core.DEFAULT_RESULT
        self.units = {}
        self.deformation = core.DEFORMATION_DEFAULT
        self.mesh = False
        self.loads = False  # (the setup's glyphs stay off, as on the results)
        self.items = []  # [{"study", "data", "display"}]
        self.active = False
        self.view = None
        self.gl = None
        self.legend = None
        self.tags = None
        self.hidden = {}
        self.legend_info = None
        self.tag_list = []
        self._timer = None
        self._camera = None
        self._ticks = 0
        self._glyphs_before = None
        self.panes = []  # [{"view", "gl", "sub", "tags", "camera", "key", "note"}]
        self.split = False
        self._layout_before = None
        self._cameras_before = None

    def alive(self):
        doc = _doc(self.doc_name)
        if doc is None:
            return False
        for name in self.study_names:
            study = doc.getObject(name)
            if study is None or not results_data.has_results(study):
                return False
        return True

    def studies(self):
        doc = _doc(self.doc_name)
        return [doc.getObject(n) for n in self.study_names] if doc is not None else []

    def _panes_alive(self):
        return bool(self.panes) and all(
            p["gl"] is not None and view_mod._alive(p["gl"]) for p in self.panes
        )

    def activate(self):
        gl = view_mod.gl_widget_of(self.doc_name)
        if self.active and gl is not None and self._panes_alive():
            if any(p["gl"] is gl for p in self.panes):
                return
        if self.active and self.split and not self._panes_alive() and self._single_chosen():
            # (Navigation bar > Viewports > Single View: the person wants one view)
            log("results: one view chosen: Compare ends")
            QtCore.QTimer.singleShot(0, finish_compare)
            return
        if self.active:
            self.deactivate()
        doc = _doc(self.doc_name)
        gui = Gui.getDocument(doc.Name)
        self.items = []
        boxes = []
        for study in self.studies():
            data = results_data.data(study)
            display = view_mod.ResultDisplay(data)
            pts = data.points
            boxes.append(tuple(pts.min(axis=0)) + tuple(pts.max(axis=0)))
            try:
                stale = bool(results_data.out_of_date(study))
            except Exception:
                stale = False
            self.items.append(
                {"study": study, "data": data, "display": display, "pane": None, "stale": stale}
            )
        try:
            camera = gui.ActiveView.getCamera()  # (the panes start from the view's camera)
        except Exception:
            camera = None
        panes = self._split(gui)
        self.split = bool(panes)
        if self.split:
            for item, pane in zip(self.items, panes):
                item["display"].attach(pane["view"])
                item["pane"] = pane
            if camera:
                try:
                    panes[0]["view"].setCamera(camera)
                except Exception:
                    pass
        else:  # (one view: the studies side by side, across the way they are thinnest)
            axis = core.compare_axis(boxes)
            for item, shift in zip(self.items, core.compare_offsets(boxes, axis=axis)):
                offset = [0.0, 0.0, 0.0]
                offset[axis] = shift
                item["display"].set_offset(offset)
            gl = view_mod.gl_widget_of(self.doc_name)  # (a failed split may have changed it)
            panes = [{"view": gui.ActiveView, "gl": gl, "sub": None}]
            for item in self.items:
                item["display"].attach(panes[0]["view"])
                item["pane"] = panes[0]
        self.panes = panes
        self.view, self.gl = panes[0]["view"], panes[0]["gl"]
        Session._hide_design(self)
        if self.gl is not None:
            self.legend = view_mod.Legend(
                self.gl,
                {
                    "result": self.set_result,
                    "unit": self.set_unit,
                    "details": open_details,
                    "solve": solve_again,
                    "banded": lambda on: None,
                    "range": open_range,
                    "finish_compare": finish_compare,
                },
            )
            self.legend.details_button.setEnabled(False)
            self.legend.options_button.setEnabled(False)
        for number, pane in enumerate(self.panes):
            pane["tags"] = (
                view_mod.TagLayer(pane["gl"], pane["view"]) if pane["gl"] is not None else None
            )
            pane["note"] = None
            if self.split and number >= len(self.items) and pane["gl"] is not None:
                pane["note"] = view_mod.PaneNote(
                    pane["gl"], "Compare: %d studies (this view stays empty)" % len(self.items)
                )
        self.tags = self.panes[0].get("tags")
        self.active = True
        self.apply()
        try:
            self.view.fitAll()
        except Exception:
            pass
        self._follow_camera(0)
        self._timer = QtCore.QTimer()
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        log(
            "results: comparing %s%s"
            % (
                ", ".join(i["study"].Label for i in self.items),
                " (%s)" % self._layout_name() if self.split else " (side by side)",
            )
        )

    def _layout_name(self):
        return self.LAYOUTS.get(len(self.items), "Multiple Views")

    def _split(self, gui):
        """Fusion's Compare splits the canvas: the design's 3D view in panes (Navigation bar >
        Viewports' layouts), one study in each. [{"view", "gl", "sub"}] in the panes' order,
        or None when it cannot be split."""
        try:
            from . import viewports_ui
        except Exception:
            return None
        name = self._layout_name()
        try:
            mdi = viewports_ui.area()
            if mdi is None:
                return None
            if self._layout_before is None:
                self._layout_before = viewports_ui.current()
            if viewports_ui.current() != name and not viewports_ui.set_layout(name):
                return None
            subs = viewports_ui.panes()
            if len(subs) < len(self.items):
                self._layout_back(viewports_ui)
                return None
            panes = []
            for sub in subs:
                mdi.setActiveSubWindow(sub)
                gl = None
                for widget in sub.findChildren(QtWidgets.QWidget):
                    if widget.metaObject().className() == "QOpenGLWidget":
                        gl = widget
                        break
                panes.append({"view": gui.ActiveView, "gl": gl, "sub": sub})
            mdi.setActiveSubWindow(subs[0])
            if len({id(p["gl"]) for p in panes}) != len(panes) or any(
                p["gl"] is None for p in panes
            ):
                self._layout_back(viewports_ui)
                return None
            if self._cameras_before is None and self._layout_before == name:
                # (the person's own panes: their cameras come back after Compare)
                self._cameras_before = [p["view"].getCamera() for p in panes]
            return panes
        except Exception as exc:
            warn("Compare: the view could not be split: %s" % exc)
            try:
                self._layout_back(viewports_ui)
            except Exception:
                pass
            return None

    def _layout_back(self, viewports_ui):
        """The layout there was before Compare, when splitting failed half way (the studies
        then lie side by side in one view)."""
        before, self._layout_before, self._cameras_before = self._layout_before, None, None
        if before is not None and viewports_ui.current() != before:
            viewports_ui.set_layout(before, quiet=True)

    def _single_chosen(self):
        try:
            from . import viewports_ui

            return viewports_ui.is_single()
        except Exception:
            return False

    def _unsplit(self):
        """The view as it was before Compare (its layout, or its panes' cameras)."""
        before, cameras = self._layout_before, self._cameras_before
        self._layout_before = self._cameras_before = None
        if before is None:
            return
        try:
            from . import viewports_ui

            if viewports_ui.current() != before:
                viewports_ui.set_layout(before, quiet=True)
            elif cameras:
                for pane, camera in zip(self.panes, cameras):
                    try:
                        pane["view"].setCamera(camera)
                    except Exception:
                        continue
        except Exception as exc:
            warn("Compare: %s" % exc)

    def _follow_camera(self, lead):
        """Every pane takes pane `lead`'s camera (the panes turn together)."""
        if not self.panes:
            return
        source = self.panes[lead]["view"]
        for number, pane in enumerate(self.panes):
            if number != lead and self.split:
                view_mod.copy_camera(source, pane["view"])
        for pane in self.panes:
            key = view_mod.camera_key(pane["view"], pane["gl"]) if pane["gl"] is not None else None
            pane["camera"] = key[:5] if key else None
            pane["key"] = key

    def deactivate(self):
        if self._timer is not None:
            try:
                self._timer.stop()
            except RuntimeError:
                pass
            self._timer = None
        widgets = [self.legend]
        for pane in self.panes:
            widgets += [pane.get("tags"), pane.get("note")]
        for widget in widgets:
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
        self.legend = self.tags = None
        for item in self.items:
            item["display"].detach()
        self.items = []
        Session._show_design(self)
        Session._restore_glyphs(self)
        if self.split:
            self._unsplit()
        self.panes = []
        self.split = False
        self.active = False
        self.gl = None
        self.view = None

    # what Session's helpers need
    @property
    def doc(self):
        return _doc(self.doc_name)

    def unit(self, result=None):
        return Session.unit(self, result)

    def factor(self, key=None):
        """The same scale for every study: Adjusted draws the largest movement of them all at
        5 % of the largest model."""
        biggest = max(i["data"].max_displacement for i in self.items)
        diagonal = max(i["data"].diagonal for i in self.items)
        return core.deformation_factor(key or self.deformation, biggest, diagonal)

    def scale(self):
        stats = core.combined_stats([i["data"].stats(self.result) for i in self.items])
        return stats, core.scale(self.result, stats.get("min"), stats.get("max"))

    def apply(self):
        if not self.items:
            return
        np = view_mod._np()
        stats, (lo, hi, reverse) = self.scale()
        factor = self.factor()
        for item in self.items:
            display = item["display"]
            values = item["data"].values(self.result)
            display.set_positions(_positions(np, values[display.nodes], lo, hi, reverse))
            display.set_texture(core.texture_rows())
            display.set_factor(factor)
            display.set_mesh(self.mesh)
        info = core.legend(self.result, stats, self.unit())
        info["targets"] = core.DEFAULT_TARGETS
        self.legend_info = info
        if self.legend is not None and view_mod._alive(self.legend):
            self.legend.fill(
                info,
                "Compare: %d studies, one colour scale" % len(self.items),
                False,
                "Deformation: %s, the same for every study"
                % core.deformation_name(self.deformation),
            )
            self.legend.compare_button.show()
        self.update_tags()
        Session._glyphs(self)
        for pane in self.panes or [{"view": self.view}]:
            try:
                pane["view"].redraw()
            except Exception:
                pass

    def update_tags(self):
        tags = []
        stats_all, (lo, hi, reverse) = self.scale()
        unit = self.unit()
        for item in self.items:
            data, display = item["data"], item["display"]
            st = data.stats(self.result)
            top = data.points[:, 2].max()
            centre = data.points.mean(axis=0)
            shift = [float(c) for c in display.offset]
            point = (
                float(centre[0]) + shift[0],
                float(centre[1]) + shift[1],
                float(top) + shift[2],
            )
            text = "%s   min %s   max %s%s" % (
                item["study"].Label,
                core.with_unit(core.convert(st.get("min"), unit), unit),
                core.with_unit(core.convert(st.get("max"), unit), unit),
                "   (out of date)" if item.get("stale") else "",
            )
            tags.append(
                {
                    "kind": "max",
                    "node": None,
                    "value": st.get("max"),
                    "point": point,
                    "text": text,
                    "colour": core.map_colour(core.position(st.get("max"), lo, hi, reverse)),
                    "study": item["study"].Name,
                }
            )
        self.tag_list = tags
        for pane in self.panes:
            layer = pane.get("tags")
            if layer is None or not view_mod._alive(layer):
                continue
            mine = [
                tag
                for item, tag in zip(self.items, tags)
                if item.get("pane") is pane or not self.split
            ]
            layer.set_tags(mine)

    def set_result(self, key):
        if key in core.result_keys():
            self.result = key
            self.apply()

    def set_unit(self, unit):
        if core.unit_ok(self.result, unit):
            self.units[core.kind_of(self.result)] = unit
            self.apply()

    def set_deformation(self, key):
        self.deformation = key
        self.apply()

    def set_option(self, name, on):
        if name == "mesh":
            self.mesh = bool(on)
            self.apply()

    def _tick(self):
        try:
            if not self.active or self.gl is None:
                return
            if not self._panes_alive():
                if self.split and self._single_chosen():
                    # (Navigation bar > Viewports > Single View: the person wants one view)
                    log("results: one view chosen: Compare ends")
                    QtCore.QTimer.singleShot(0, finish_compare)
                else:
                    QtCore.QTimer.singleShot(0, sync)
                return
            keys = [view_mod.camera_key(p["view"], p["gl"]) for p in self.panes]
            if self.split:  # one pane turned: the others follow
                active = view_mod.gl_widget_of(self.doc_name)
                moved = [
                    n
                    for n, (pane, key) in enumerate(zip(self.panes, keys))
                    if key is not None and key[:5] != pane.get("camera")
                ]
                if moved:
                    lead = moved[0]
                    for n in moved:
                        if self.panes[n]["gl"] is active:
                            lead = n
                    self._follow_camera(lead)
                    for pane in self.panes:
                        pane["key"] = None  # (their tags are laid out again below)
                    keys = [view_mod.camera_key(p["view"], p["gl"]) for p in self.panes]
            for pane, key in zip(self.panes, keys):
                if key != pane.get("key"):
                    pane["key"] = key
                    layer = pane.get("tags")
                    if layer is not None and view_mod._alive(layer):
                        layer.relayout()
            self._ticks += 1
            if self._ticks % 6 == 0:
                _hide_again(self)
        except Exception as exc:
            warn("Compare: %s" % exc)


def deformation_is(key):
    session = COMPARE["session"] if compare_on() else current()
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
    session = COMPARE["session"] if compare_on() else current()
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


def comparing():
    return compare_on()


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

    in_compare = False  # also works on Compare's studies

    def IsActive(self):
        if compare_on():
            return self.in_compare
        return _shown()

    def Activated(self):
        try:
            if compare_on():
                if self.in_compare:
                    self.run(COMPARE["session"])
                else:
                    commands.tell("Finish Compare first (the button under the legend).")
                return
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
        in_compare = True

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


class RangeCommand(_ResultsCommand):
    menu = "Legend Min/Max"
    tip = "Set the values the legend's colours run between (not for the safety factor)"
    icon = "simr_range"

    def IsActive(self):
        session = current()
        return session is not None and session.result != "safety"

    def run(self, session):
        open_range()


class CompareCommand(_ResultsCommand):
    menu = "Compare"
    tip = "Two to four studies of this design in split views, on one colour scale (again to finish)"
    icon = "simr_compare"
    in_compare = True

    def IsActive(self):
        if compare_on():
            return True
        doc = App.ActiveDocument
        return _shown() and len(studies_with_results(doc)) >= 2

    def run(self, session):
        if compare_on():
            finish_compare()
            return
        from . import simulation_results_panels as panels

        panels.compare(session)


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
    in_compare = True


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


class PointProbesCommand(_ResultsCommand):
    menu = "Point Probes"
    tip = (
        "Values inside the part: click the result, a slice's cut face or the iso-surface, "
        "then type X, Y, Z to move the probe"
    )
    icon = "simr_point_probe"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.point_probes(session)


class IsoCommand(_ResultsCommand):
    menu = "Iso-surface"
    tip = "The surface inside the part where the result shown has one value"
    icon = "simr_iso"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.iso_panel(session)


class SolverDataCommand(_ResultsCommand):
    menu = "Solver Data"
    tip = "How the study was solved: time taken, the mesh and its quality, the solver's messages"
    icon = "simr_solver_data"

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.solver_data(session)


class ConvergenceCommand(_ResultsCommand):
    menu = "Convergence Plot"
    tip = (
        "How the result settled solve after solve while adaptive mesh refinement made the mesh "
        "finer"
    )
    icon = "simr_convergence"

    def IsActive(self):
        if compare_on():
            return False
        session = current()
        if session is None or session.study is None:
            return False
        try:
            adaptive = simulation.summary(session.study).get("adaptive") or {}
            return bool(adaptive.get("passes"))
        except Exception:
            return False

    def run(self, session):
        from . import simulation_results_panels as panels

        panels.convergence_plot(session)


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
    "SciForge_SimResultsCompare": CompareCommand,
    "SciForge_SimResultsRange": RangeCommand,
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
    "SciForge_SimResultsPointProbes": PointProbesCommand,
    "SciForge_SimResultsIso": IsoCommand,
    "SciForge_SimResultsSolverData": SolverDataCommand,
    "SciForge_SimResultsConvergence": ConvergenceCommand,
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

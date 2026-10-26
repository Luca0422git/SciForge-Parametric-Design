# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's SIMULATION workspace (Static Stress): entering and leaving it, and the commands of
its SETUP tab. Owner: builder sim-ui (beta 3). The engine is simulation.py (builder sim-core),
the RESULTS tab simulation_results_ui.py (builder sim-results). Spec:
docs/sciforge/parity/simulation.md "Setup"; Fusion's behaviour with sources:
docs/sciforge/dev/research/fusion-simulation.md.

The workspace (research 1): picked from the workspace drop-down (Design / Simulation /
Drawing). In SIMULATION the ribbon shows SETUP and RESULTS instead of the design's tabs, the
timeline is hidden, the browser shows the study tree (simulation_browser.py), the loads and
constraints are drawn on the model (simulation_glyphs.py) and the Pre-check button shows the
active study's traffic light. Each open design remembers its own workspace: switching to
another design's tab shows that design's workspace; closing a design forgets it. Entering
ends the command or sketch that is open and clears the selection; a design without a study
opens Fusion's New Study dialog, else its last active study is the active one again.

Dialogs: simulation_dialogs.py (New Study, Settings, Study Materials, contacts, Load Case
Attributes, Pre-check, gravity), simulation_panels.py (Structural Constraints / Loads, picks on
the model), simulation_solve_dialog.py (Solve and its progress, Generate Mesh).
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import log, ui_icon_path, warn
from .compat import QtCore, QtWidgets

STATE = {
    "on": False,  # the ribbon shows the SIMULATION workspace now
    "docs": {},  # document name -> True while that design is in the SIMULATION workspace
    "active": {},  # document name -> name of its active study
    "timeline": False,  # the timeline was shown when the workspace hid it
    "connected": False,
    "watch": None,
    "timer": None,
    "light": None,  # (document, study, state) shown on the Pre-check button
    "light_key": None,
    "glyph_key": None,
    "dof": False,  # DOF View is on (SETUP > DISPLAY)
    "held": [],  # the design's shortcuts switched off while SIMULATION shows
}


def _ribbon():
    try:
        from . import shell

        return shell.ribbon()
    except Exception:
        return None


def _doc():
    return App.ActiveDocument


def active():
    """True while the SIMULATION workspace is shown."""
    return bool(STATE["on"])


def in_workspace(doc=None):
    """True when `doc` (the active design) is in the SIMULATION workspace."""
    doc = doc or _doc()
    return bool(doc is not None and STATE["docs"].get(doc.Name))


# -- the active study --------------------------------------------------------------------------
def active_study(doc=None):
    """The design's active study (the one the SETUP commands work on), or None: the one made
    or activated last, else the newest."""
    from . import simulation

    doc = doc or _doc()
    if doc is None:
        return None
    try:
        found = simulation.studies(doc)
    except Exception:
        return None
    name = STATE["active"].get(doc.Name)
    for study in found:
        if study.Name == name:
            return study
    return found[-1] if found else None


def set_active_study(study):
    """Make `study` the active one (Fusion: double-click a study in the browser)."""
    if study is None:
        return
    try:
        STATE["active"][study.Document.Name] = study.Name
        log("active study: %s" % study.Label)
        _setup_tab_without_results(study)
        from . import simulation_solve_dialog

        shown = simulation_solve_dialog.MESH["shown"]
        if shown is not None and shown != (study.Document.Name, study.Name):
            simulation_solve_dialog.hide_mesh()  # (another study's mesh)
    except Exception as exc:
        warn("active study: %s" % exc)
    refresh()


def _setup_tab_without_results(study):
    """A study without results made active while the RESULTS tab is in front (a new or cloned
    study): Fusion shows its SETUP tab."""
    from . import simulation

    ribbon = _ribbon()
    if ribbon is None or not STATE["on"] or not in_workspace(study.Document):
        return
    if ribbon.current_tab() == "sim_results" and not simulation.summary(study):
        ribbon.set_simulation_mode(True, "sim_setup")


def require_study(doc=None):
    """The active study, or None after telling the person to make one first."""
    from . import commands

    study = active_study(doc)
    if study is None:
        commands.tell("Make a study first: STUDY > New Simulation Study.")
    return study


# -- entering and leaving ----------------------------------------------------------------------
def _finish_open():
    """Fusion: switching workspace ends the command in progress (a sketch is finished)."""
    from . import commands

    if not commands.finish_open_dialog():
        return False
    try:
        gdoc = Gui.ActiveDocument
        if gdoc is not None and gdoc.getInEdit() is not None:
            commands.leave_edit()
    except Exception as exc:
        warn("simulation workspace: %s" % exc)
    return True


def enter_workspace(tab=None):
    """Switch the active design to the SIMULATION workspace (the workspace menu's Simulation).
    Without a study, Fusion's New Study dialog opens."""
    try:
        from . import commands

        doc = _doc()
        if doc is None:
            commands.tell("Open a design first: the Simulation workspace works on a design.")
            return False
        if not _finish_open():
            return False
        try:
            Gui.Selection.clearSelection()
        except Exception:
            pass
        _from_drawing(doc)
        _connect()
        STATE["docs"][doc.Name] = True
        _apply(True, tab)
        if active_study(doc) is None:
            QtCore.QTimer.singleShot(0, _new_study_on_entry)
        return True
    except Exception as exc:
        warn("simulation workspace: %s" % exc)
        return False


def _from_drawing(doc):
    """Simulation picked while a drawing's tab is in front: the design's own 3D view comes to
    the front first (the workspace works on the model)."""
    try:
        from . import drawing_ui

        if drawing_ui.is_on():
            drawing_ui.show_design(doc)
            drawing_ui.sync_mode()
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


def _new_study_on_entry():
    try:
        if in_workspace() and active_study() is None:
            from . import simulation_dialogs

            simulation_dialogs.open_new_study()
    except Exception as exc:
        warn("new study: %s" % exc)


def leave_workspace():
    """Back to the DESIGN workspace (the workspace menu's Design). Studies and results stay
    in the design."""
    try:
        doc = _doc()
        if doc is not None and not STATE["docs"].get(doc.Name) and not STATE["on"]:
            return True
        if not _finish_open():
            return False
        if doc is not None:
            STATE["docs"][doc.Name] = False
        try:
            Gui.Selection.clearSelection()
        except Exception:
            pass
        _apply(False)
        return True
    except Exception as exc:
        warn("simulation workspace: %s" % exc)
        return False


def _results_hide():
    """The RESULTS display (sim-results) put away: the design's bodies shown again."""
    try:
        from . import simulation_results_ui as results
    except Exception:
        return
    for name in ("hide", "leave_workspace"):
        fn = getattr(results, name, None)
        if fn is not None:
            try:
                fn()
            except Exception as exc:
                warn("results display: %s" % exc)
            return


def _apply(on, tab=None):
    """Show the workspace `on` for the active design: ribbon tabs, timeline, browser, glyphs."""
    ribbon = _ribbon()
    was = STATE["on"]
    STATE["on"] = bool(on)
    if ribbon is not None and hasattr(ribbon, "set_simulation_mode"):
        try:
            ribbon.set_simulation_mode(bool(on), tab)
        except Exception as exc:
            warn("simulation ribbon: %s" % exc)
    _timeline(on)
    _hold_design_keys(on)
    if not on:
        _results_hide()
        STATE["dof"] = False  # (DOF View is a SIMULATION display: off when it is left)
        try:  # the mesh Generate Mesh showed is a SIMULATION display: not over the design
            from . import simulation_solve_dialog

            simulation_solve_dialog.hide_mesh()
        except Exception as exc:
            warn("simulation mesh: %s" % exc)
    try:
        from . import simulation_glyphs

        if on:
            simulation_glyphs.set_dof(STATE["dof"])
            simulation_glyphs.refresh(_doc(), active_study(), force=True)
        else:
            simulation_glyphs.set_dof(False)
            simulation_glyphs.clear()
    except Exception as exc:
        warn("simulation glyphs: %s" % exc)
    if on:
        _start_timer()
    else:
        _stop_timer()
    STATE["light_key"] = None
    refresh_light()
    _refresh_browser()
    if was != STATE["on"]:
        doc = _doc()
        log(
            "%s workspace%s"
            % ("simulation" if on else "design", (": %s" % doc.Label) if doc is not None else "")
        )


# Keys that change the design (Fusion's design shortcuts do nothing in Simulation): Press
# Pull, Extrude, Fillet, Hole, Move, Joint, Appearance, copy / paste, Compute All, Delete and
# the sketch tools. Delete made a Delete Face step from a face picked in the view (or deleted
# a body DOF View had selected); the browser takes Del itself, so a study item is still
# deleted there.
DESIGN_KEYS = (
    "Del",
    "Backspace",
    "Q",
    "E",
    "F",
    "H",
    "M",
    "J",
    "A",
    "Ctrl+C",
    "Ctrl+V",
    "Ctrl+B",
    "D",
    "L",
    "C",
    "R",
    "T",
    "X",
    "O",
    "P",
)


def _hold_design_keys(on):
    """In SIMULATION the design's keys are off (Fusion does not change the design from
    Simulation); they are on again when it is left."""
    try:
        from . import shortcuts

        if on:
            for key in DESIGN_KEYS:
                entry = shortcuts._bound.get(shortcuts.normalise(key))
                if entry is not None and entry[1].isEnabled():
                    entry[1].setEnabled(False)
                    STATE["held"].append(entry[1])
        else:
            held, STATE["held"] = STATE["held"], []
            for shortcut in held:
                try:
                    shortcut.setEnabled(True)
                except RuntimeError:
                    pass  # (rebound meanwhile: the new one is on)
    except Exception as exc:
        warn("simulation workspace: keys: %s" % exc)


def open_marking_menu(global_pos):
    """The right-click marking menu with the SETUP commands (ribbon_config.SIM_MARKING_MENU
    and SIM_MARKING_LIST) instead of the design's."""
    from . import marking_menu, recent, ribbon_config as cfg

    ring, listing, last = cfg.MARKING_MENU, cfg.MARKING_LIST, recent.last

    def simulation_last():
        # Repeat offers the last SETUP command only (not a design command run before)
        found = last()
        return found if found and str(found[0]).startswith("SciForge_Sim") else None

    cfg.MARKING_MENU, cfg.MARKING_LIST = cfg.SIM_MARKING_MENU, cfg.SIM_MARKING_LIST
    recent.last = simulation_last
    try:
        return marking_menu.open_at(global_pos)
    finally:
        cfg.MARKING_MENU, cfg.MARKING_LIST, recent.last = ring, listing, last


def _timeline(on):
    """Fusion's Simulation workspace has no timeline: hidden while it shows, back after."""
    try:
        from . import shell, timeline_ui

        dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "SciForgeTimelineDock")
        if on:
            if dock is not None and dock.isVisible():
                STATE["timeline"] = True
                timeline_ui.hide()
        elif STATE["timeline"]:
            STATE["timeline"] = False
            if shell.is_on():
                drawing = False
                try:
                    from . import drawing_ui

                    drawing = drawing_ui.is_on()
                except Exception:
                    pass
                if not drawing:
                    timeline_ui.show()
    except Exception as exc:
        warn("simulation workspace timeline: %s" % exc)


def _refresh_browser():
    try:
        from . import browser_ui

        widget = browser_ui.widget()
        if widget is not None:
            widget.refresh(force=True)
    except Exception as exc:
        warn("simulation browser: %s" % exc)


def sync():
    """The active design changed (another tab, a design closed): show its own workspace."""
    try:
        want = in_workspace()
        _finish_sim_dialog()
        if want != STATE["on"]:
            _apply(want)
        elif want:
            refresh()
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


def _finish_sim_dialog():
    """A SETUP dialog of another design ends when its design is no longer in front."""
    try:
        from . import taskui

        current = taskui.current()
        if current is not None and getattr(current, "simulation_dialog", False):
            if current.doc is not _doc():
                current.finish()
    except Exception as exc:
        warn("simulation dialog: %s" % exc)


def refresh():
    """After a setup change: the browser, the glyphs and the Pre-check light again."""
    if not STATE["on"]:
        return
    STATE["light_key"] = None
    STATE["glyph_key"] = None
    try:
        from . import simulation_glyphs

        simulation_glyphs.refresh(_doc(), active_study(), force=True)
    except Exception as exc:
        warn("simulation glyphs: %s" % exc)
    refresh_light()
    _refresh_browser()


# -- following the documents -------------------------------------------------------------------
class _Watch:
    """A design closed: forget its workspace and active study, show the next design's."""

    def slotDeletedDocument(self, doc):
        try:
            name = doc.Name
            STATE["docs"].pop(name, None)
            STATE["active"].pop(name, None)
            QtCore.QTimer.singleShot(50, sync)
        except Exception as exc:
            warn("simulation workspace: %s" % exc)

    def slotActivateDocument(self, doc):
        QtCore.QTimer.singleShot(0, sync)


def _window_changed(sub=None):
    if sub is None:
        return
    QtCore.QTimer.singleShot(0, sync)


def _connect():
    if STATE["connected"]:
        return
    try:
        area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        if area is not None:
            area.subWindowActivated.connect(_window_changed)
        STATE["watch"] = _Watch()
        App.addDocumentObserver(STATE["watch"])
        STATE["connected"] = True
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


def _start_timer():
    if STATE["timer"] is None:
        timer = QtCore.QTimer()
        timer.setInterval(500)
        timer.timeout.connect(_tick)
        STATE["timer"] = timer
    if not STATE["timer"].isActive():
        STATE["timer"].start()


def _stop_timer():
    if STATE["timer"] is not None:
        STATE["timer"].stop()


def _tick():
    """While the workspace shows: the glyphs follow edits and the zoom, the Pre-check light
    follows the study (only after something changed: doc_epoch)."""
    try:
        if not STATE["on"]:
            return
        from . import doc_epoch, shell, simulation_glyphs

        if not shell.is_on():
            # SciForge's interface is off (FreeCAD's own workbench): no glyphs in its view
            if simulation_glyphs.STATE["root"] is not None:
                simulation_glyphs.clear()
            STATE["glyph_key"] = None
            return
        if doc_epoch.busy():
            return
        doc = _doc()
        if doc is None or not in_workspace(doc):
            QtCore.QTimer.singleShot(0, sync)
            return
        study = active_study(doc)
        key = (doc_epoch.key(), study.Name if study is not None else None)
        simulation_glyphs.follow_zoom()
        if key != STATE["glyph_key"]:
            STATE["glyph_key"] = key
            simulation_glyphs.refresh(doc, study)
        if not STATE.get("light_slow"):
            refresh_light()
    except Exception as exc:
        warn("simulation workspace: %s" % exc)


# -- the Pre-check light (Fusion: the toolbar icon is a traffic light, research 3.9) ------------
def precheck_state(study):
    """(light, [(level, sentence)]) of a study (light None without a study)."""
    from . import simulation, simulation_setup_core as score

    if study is None:
        return None, []
    try:
        checks = score.ordered_checks(simulation.precheck(study))
    except Exception as exc:
        return "red", [("error", "The study could not be checked: %s" % exc)]
    return score.light(checks), checks


def refresh_light():
    """The Pre-check button's icon and tooltip show the active study's state."""
    try:
        from . import doc_epoch, simulation_setup_core as score

        doc = _doc()
        study = active_study(doc) if STATE["on"] else None
        key = (doc_epoch.key(), study.Name if study is not None else None, STATE["on"])
        if key == STATE["light_key"]:
            return
        STATE["light_key"] = key
        import time

        started = time.perf_counter()
        state, checks = precheck_state(study) if STATE["on"] else (None, [])
        # a pre-check that takes long (many bodies: contacts, overlaps) is not redone after
        # every change, only after a SETUP command (refresh()) and on Pre-check
        STATE["light_slow"] = time.perf_counter() - started > 0.3
        STATE["light"] = (doc.Name if doc else None, study.Name if study else None, state)
        ribbon = _ribbon()
        if ribbon is None:
            return
        from . import ui_icon

        icon = score.light_icon(state)
        lines = [score.light_text(state)] + [text for _level, text in checks]
        for button in ribbon.findChildren(QtWidgets.QToolButton):
            if button.objectName() == "SciForgeBig_Pre-check":
                button.setIcon(ui_icon(icon))
                button.setProperty("sciforgeIcon", icon)
                button.setProperty("simLight", state or "")
                button.setToolTip("Pre-check\n" + "\n".join(lines))
    except Exception as exc:
        warn("pre-check light: %s" % exc)


def light():
    """The Pre-check light shown now: "green" / "yellow" / "red" / None (tests)."""
    value = STATE.get("light")
    return value[2] if value else None


# -- results hand-over ---------------------------------------------------------------------------
def show_results(study):
    """A solve ended: the results show (sim-results' simulation_results_ui.show(study) when it
    is there, else the RESULTS tab is selected). Only when the design is in front in the
    SIMULATION workspace: a person who went on working in DESIGN (or in another design) while
    it solved is not taken away from it; they are told where the results are."""
    try:
        if study is None:
            return
        doc = study.Document
        if not (STATE["on"] and in_workspace(doc) and App.ActiveDocument is doc):
            STATE["active"][doc.Name] = study.Name
            from . import commands

            commands.tell(
                "%s is solved: its results are in Workspace > Simulation, RESULTS tab."
                % study.Label
            )
            return
        set_active_study(study)
        try:
            from . import simulation_results_ui as results
        except Exception:
            results = None
        shown = False
        if results is not None and hasattr(results, "show"):
            try:
                results.show(study)
                shown = True
            except Exception as exc:
                warn("results display: %s" % exc)
        ribbon = _ribbon()
        if not shown and ribbon is not None and in_workspace(study.Document):
            ribbon.set_simulation_mode(True, "sim_results")
    except Exception as exc:
        warn("results: %s" % exc)


def open_results(study):
    """A person asked to see a study's results (its row in Job Status double-clicked): its
    design comes to the front in SIMULATION and the results show. (The end of a solve does not
    take a person away from their work: show_results.) Returns True when they show."""
    try:
        from . import bodies

        if study is None or not bodies.alive(study):
            return False
        doc = study.Document
        if App.ActiveDocument is not doc:
            from . import drawing_ui

            drawing_ui.show_design(doc)
        if App.ActiveDocument is not doc:
            show_results(study)  # (says where they are)
            return False
        if not (STATE["on"] and in_workspace(doc)):
            set_active_study(study)
            if not enter_workspace("sim_results"):
                return False
        show_results(study)
        return True
    except Exception as exc:
        warn("results: %s" % exc)
        return False


# -- commands ------------------------------------------------------------------------------------
def _run(fn, *args):
    try:
        fn(*args)
    except Exception as exc:
        warn("simulation: %s" % exc)


def _setup_active():
    return App.ActiveDocument is not None and in_workspace()


class _SetupCommand:
    """A SETUP command: active in the SIMULATION workspace."""

    TEXT = ""
    TIP = ""
    ICON = "workspace_simulation"

    def GetResources(self):
        return {"MenuText": self.TEXT, "ToolTip": self.TIP, "Pixmap": ui_icon_path(self.ICON)}

    def IsActive(self):
        return _setup_active()

    def Activated(self):
        _run(self.run)

    def run(self):
        pass


class NewStudyCommand(_SetupCommand):
    TEXT = "New Simulation Study"
    TIP = "Make a new study of the design: pick the study type (Static Stress)"
    ICON = "sim_new_study"

    def IsActive(self):
        return App.ActiveDocument is not None

    def run(self):
        from . import simulation_dialogs

        if not in_workspace():
            if not enter_workspace():
                return
            if active_study() is None:
                return  # entering opens New Study by itself
        simulation_dialogs.open_new_study()


class StudyMaterialsCommand(_SetupCommand):
    TEXT = "Study Materials"
    TIP = "The material of each body for this study, and what its safety factor is based on"
    ICON = "sim_materials"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.open_materials(study)


class ConstraintsCommand(_SetupCommand):
    TEXT = "Structural Constraints"
    TIP = "Hold the model where it is fixed, pinned or supported"
    ICON = "sim_constraints"

    def run(self):
        from . import simulation_panels

        study = require_study()
        if study is not None:
            simulation_panels.open_item(study, "constraint")


class LoadsCommand(_SetupCommand):
    TEXT = "Structural Loads"
    TIP = "Push, pull or twist the model: force, pressure, moment"
    ICON = "sim_loads"

    def run(self):
        from . import simulation_panels

        study = require_study()
        if study is not None:
            simulation_panels.open_item(study, "load")


def dof_on():
    """True while DOF View is on (the menu's tick)."""
    return bool(STATE["dof"] and STATE["on"])


def gravity_on():
    """True when the active study has gravity on (the menu's tick)."""
    try:
        from . import simulation

        study = active_study()
        return bool(study is not None and simulation.settings(study)["gravity"]["on"])
    except Exception:
        return False


class GravityCommand(_SetupCommand):
    TEXT = "Toggle Gravity On/Off"
    TIP = "Switch the weight of the bodies on or off for this study (off by default)"
    ICON = "sim_gravity"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.toggle_gravity(study)


class AutoContactsCommand(_SetupCommand):
    TEXT = "Automatic Contacts"
    TIP = "Find the bodies that touch: they are bonded (glued) when the study solves"
    ICON = "sim_contacts"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.open_contacts(study)


class ContactManagerCommand(_SetupCommand):
    TEXT = "Contact Manager"
    TIP = "The list of the bodies bonded together in this study"
    ICON = "sim_contact_manager"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.open_contact_manager(study)


class DOFViewCommand(_SetupCommand):
    TEXT = "DOF View"
    TIP = "On / off: arrows show how the bodies that are not held yet could still move"
    ICON = "sim_dof"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.dof_view(study)


class SettingsCommand(_SetupCommand):
    TEXT = "Settings"
    TIP = "Study Settings: general, mesh, adaptive refinement"
    ICON = "sim_settings"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.open_settings(study)


class LocalMeshCommand(_SetupCommand):
    TEXT = "Local Mesh Control"
    TIP = "Smaller mesh elements on picked faces or edges"
    ICON = "sim_local_mesh"

    def run(self):
        from . import simulation_panels

        study = require_study()
        if study is not None:
            simulation_panels.open_local_mesh(study)


class AttributesCommand(_SetupCommand):
    TEXT = "Load Case Attributes"
    TIP = "Every constraint and load of the study with where it is and how big"
    ICON = "sim_attributes"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            simulation_dialogs.open_attributes(study)


class PrecheckCommand(_SetupCommand):
    TEXT = "Pre-check"
    TIP = "Check the study before solving: what is missing or may be wrong"
    ICON = "sim_precheck"

    def run(self):
        from . import simulation_dialogs

        study = require_study()
        if study is not None:
            STATE["light_key"] = None
            refresh_light()
            simulation_dialogs.open_precheck(study)


class SolveCommand(_SetupCommand):
    TEXT = "Solve"
    TIP = "Solve the studies on this computer (CalculiX)"
    ICON = "sim_solve"

    def run(self):
        from . import simulation_solve_dialog

        if require_study() is not None:
            simulation_solve_dialog.open_solve()


class GenerateMeshCommand(_SetupCommand):
    TEXT = "Generate Mesh"
    TIP = "Make the mesh now and show it on the model (it is made at solve time otherwise)"
    ICON = "sim_mesh"

    def run(self):
        from . import simulation_solve_dialog

        study = require_study()
        if study is not None:
            simulation_solve_dialog.generate_mesh(study)


class JobStatusCommand(_SetupCommand):
    TEXT = "Job Status"
    TIP = (
        "The solve running now with its stages and Cancel, and this session's earlier solves "
        "and meshes (double-click a solved one to see its results)"
    )
    ICON = "sim_job_status"

    def run(self):
        from . import simulation_solve_dialog

        simulation_solve_dialog.show_status()


class ShowMeshCommand(_SetupCommand):
    TEXT = "Show Mesh"
    TIP = "Show or hide the mesh made by Generate Mesh on the model"
    ICON = "sim_mesh"

    def run(self):
        from . import simulation_solve_dialog

        simulation_solve_dialog.toggle_mesh()


COMMANDS = {
    "SciForge_SimNewStudy": NewStudyCommand,
    "SciForge_SimStudyMaterials": StudyMaterialsCommand,
    "SciForge_SimConstraints": ConstraintsCommand,
    "SciForge_SimLoads": LoadsCommand,
    "SciForge_SimGravity": GravityCommand,
    "SciForge_SimAutoContacts": AutoContactsCommand,
    "SciForge_SimContactManager": ContactManagerCommand,
    "SciForge_SimDOFView": DOFViewCommand,
    "SciForge_SimSettings": SettingsCommand,
    "SciForge_SimLocalMesh": LocalMeshCommand,
    "SciForge_SimAttributes": AttributesCommand,
    "SciForge_SimPrecheck": PrecheckCommand,
    "SciForge_SimSolve": SolveCommand,
    "SciForge_SimGenerateMesh": GenerateMeshCommand,
    "SciForge_SimJobStatus": JobStatusCommand,
    "SciForge_SimShowMesh": ShowMeshCommand,
}

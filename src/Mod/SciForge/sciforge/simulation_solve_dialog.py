# SPDX-License-Identifier: LGPL-2.1-or-later
"""SETUP > SOLVE: Fusion's Solve dialog and its progress (Job Status), and Generate Mesh.

Fusion solves Static Stress only on Autodesk's cloud since 2022 (research 3.10); SciForge solves
on this computer, which the dialog says. The Solve dialog lists the design's studies with their
pre-check light, ticks the active one and names the count on its button ("Solve 1 Study"); a
study whose pre-check is red is refused with its sentences. The progress window shows each
study with its stages (preparing the model, meshing, writing the solver input, solving, reading
the results), the elapsed time and Cancel, which works at any stage. The solve runs as
simulation.Job polled by a QTimer: Gmsh and CalculiX run in a background thread, so the window
stays usable; the stages that touch the design wait while a command's dialog is open (its undo
step must not take the solve's objects), and a solve never lands in the undo history. When it
ends the results show (simulation_ui.show_results hands over to the RESULTS tab).

Generate Mesh runs the same job up to the mesh and shows it on the model.
"""

import time

import FreeCAD as App
import FreeCADGui as Gui

from . import bodies, log, ui_icon, warn
from . import simulation_setup_core as score
from .compat import QtCore, QtWidgets
from .simulation_dialogs import FocusBack

RUN = {
    "queue": [],  # studies waiting
    "job": None,  # the Job running now
    "study": None,
    "kind": None,  # "solve" | "mesh"
    "started": None,
    "signature": None,  # the study's fingerprint when its solve started
    "timer": None,
    "status": None,  # the progress window
    "results": {},  # study name -> "done" / "failed" / "cancelled" / message, this run
    "last_done": None,
    "waiting": False,  # a command's dialog is open: the job waits
}
MESH = {"shown": None}  # (document, study) whose mesh is shown on the model


def _sim():
    from . import simulation

    return simulation


def _ui():
    from . import simulation_ui

    return simulation_ui


def solving(study=None):
    """True while a solve (or Generate Mesh) runs, for `study` when given."""
    if RUN["job"] is None and not RUN["queue"]:
        return False
    if study is None:
        return True
    names = [s.Name for s in RUN["queue"] if bodies.alive(s)]
    current = RUN["study"]
    if current is not None and bodies.alive(current):
        names.append(current.Name)
    return bodies.alive(study) and study.Name in names


# -- Solve dialog ---------------------------------------------------------------------------------
def _status_text(study):
    sim = _sim()
    try:
        if sim.summary(study):
            return "Out of date" if sim.out_of_date(study) else "Solved"
    except Exception:
        pass
    return "Not solved"


class SolveDialog(FocusBack, QtWidgets.QDialog):
    """Fusion's Solve dialog (research 3.10), solving on this computer."""

    def __init__(self, doc):
        super().__init__(Gui.getMainWindow())
        self.doc = doc
        self.setObjectName("SciForgeSimSolve")
        self.setWindowTitle("Solve")
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Studies to solve"))
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setObjectName("SciForgeSimSolveStudies")
        self.table.setHorizontalHeaderLabels(["Study", "Pre-check", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.studies = _sim().studies(doc)
        active = _ui().active_study(doc)
        self.table.setRowCount(len(self.studies))
        self.lights = {}
        for row, study in enumerate(self.studies):
            item = QtWidgets.QTableWidgetItem(study.Label)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if study is active else QtCore.Qt.Unchecked)
            self.table.setItem(row, 0, item)
            state, checks = _ui().precheck_state(study)
            self.lights[study.Name] = (state, checks)
            light = QtWidgets.QTableWidgetItem(
                ui_icon(score.light_icon(state)),
                {"green": "Ready", "yellow": "Check", "red": "Cannot solve"}.get(state, ""),
            )
            light.setToolTip("\n".join(text for _l, text in checks) or score.light_text(state))
            self.table.setItem(row, 1, light)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(_status_text(study)))
        self.table.resizeColumnsToContents()
        self.table.itemChanged.connect(lambda *_a: self._count())
        layout.addWidget(self.table)
        where = QtWidgets.QLabel(
            "Solves on this computer (Gmsh meshes, CalculiX solves): no account, no cloud, no "
            "tokens. The window stays usable while it solves; Cancel stops it at any time."
        )
        where.setObjectName("SciForgeSimSolveWhere")
        where.setWordWrap(True)
        where.setStyleSheet("color: #9aa7b4;")
        layout.addWidget(where)
        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("SciForgeSimSolveMessage")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #ff8a80;")
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.go = QtWidgets.QPushButton("Solve")
        self.go.setObjectName("SciForgeSimSolveGo")
        self.go.setDefault(True)
        self.go.clicked.connect(self._solve)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("SciForgeSimSolveCancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.go)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.resize(560, 300)
        self._count()

    def chosen(self):
        out = []
        for row, study in enumerate(self.studies):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == QtCore.Qt.Checked:
                out.append(study)
        return out

    def _count(self):
        count = len(self.chosen())
        self.go.setText(score.solve_button_text(count))
        self.go.setEnabled(count > 0)

    def _solve(self):
        try:
            chosen = self.chosen()
            refused = []
            for study in chosen:
                state, checks = _ui().precheck_state(study)
                if state == "red":
                    refused.append(
                        "%s cannot solve: %s"
                        % (study.Label, " ".join(t for level, t in checks if level == "error"))
                    )
            if refused:
                self.message.setText("\n".join(refused))
                return
            self.accept()
            start(chosen, "solve")
        except Exception as exc:
            warn("solve: %s" % exc)


def open_solve():
    from . import commands

    doc = App.ActiveDocument
    if doc is None:
        return None
    if not commands.finish_open_dialog():
        return None
    if solving():
        show_status()
        commands.tell("A solve is running: its progress is shown (Cancel stops it).")
        return RUN["status"]
    dialog = SolveDialog(doc)
    dialog.show()
    return _keep(dialog)


_KEPT = []


def _keep(dialog):
    _KEPT[:] = [d for d in _KEPT if _alive(d)] + [dialog]
    return dialog


def _alive(widget):
    try:
        widget.isVisible()
        return True
    except RuntimeError:
        return False


def solve_dialog():
    """The Solve dialog that is open, or None (tests)."""
    for dialog in _KEPT:
        if _alive(dialog) and dialog.isVisible() and isinstance(dialog, SolveDialog):
            return dialog
    return None


# -- running jobs ---------------------------------------------------------------------------------
def start(studies, kind="solve"):
    """Solve `studies` one after another (or mesh one: kind "mesh"), showing the progress."""
    from . import commands

    studies = [s for s in studies if bodies.alive(s)]
    if not studies:
        return False
    if solving():
        commands.tell("A solve is running: wait for it or cancel it.")
        return False
    if not commands.finish_open_dialog():
        return False
    hide_mesh()
    RUN["queue"] = list(studies)
    RUN["kind"] = kind
    RUN["results"] = {}
    RUN["last_done"] = None
    show_status()
    if RUN["timer"] is None:
        timer = QtCore.QTimer()
        timer.setInterval(150)
        timer.timeout.connect(_poll)
        RUN["timer"] = timer
    if _next() is None:  # no job could start (each study's reason is in the progress window)
        _finish_all()
        return False
    RUN["timer"].start()
    return True


def _make_job(study, kind):
    return _sim().Job(study, mesh_only=(kind == "mesh"))


def _next():
    """Start the next study of the queue (None when the queue is empty)."""
    sim = _sim()
    while RUN["queue"]:
        study = RUN["queue"].pop(0)
        if not bodies.alive(study):
            continue
        RUN["study"] = study
        RUN["started"] = time.time()
        try:
            RUN["signature"] = sim.signature(study)
        except Exception:
            RUN["signature"] = None
        try:
            RUN["job"] = _make_job(study, RUN["kind"])
        except Exception as exc:
            RUN["job"] = None
            RUN["results"][study.Name] = ("failed", str(exc))
            continue
        log("%s %s" % ("meshing" if RUN["kind"] == "mesh" else "solving", study.Label))
        _update_status()
        return study
    RUN["job"] = None
    RUN["study"] = None
    return None


def _dialog_open(doc):
    """A command's dialog of the design is open (its undo step must not take the solve's
    objects): the job waits for it."""
    try:
        if Gui.Control.activeDialog():
            return True
        return bool(getattr(doc, "HasPendingTransaction", False))
    except Exception:
        return False


def _drain():
    """Jobs cancelled because their study or design went: polled until their thread ends, so
    the solver is stopped and their temporary folder removed (nothing of the design is
    touched: the job is cancelled)."""
    left = []
    for job in RUN.get("draining", []):
        try:
            if job.poll() == "running":
                left.append(job)
        except Exception:
            pass
    RUN["draining"] = left
    if not left and RUN["job"] is None and RUN["timer"] is not None and not RUN["queue"]:
        RUN["timer"].stop()


def _poll():
    try:
        if RUN.get("draining"):
            _drain()
        job = RUN["job"]
        if job is None:
            if RUN["study"] is not None or RUN["queue"]:
                _finish_all()
            return
        study = RUN["study"]
        if study is None or not bodies.alive(study):
            job.cancel()
            RUN.setdefault("draining", []).append(job)
            RUN["job"] = None
            _after(None, "cancelled", "The study is gone.")
            return
        thread = job._thread
        running_alone = thread is not None and thread.is_alive()
        waiting = not running_alone and not job._cancel and _dialog_open(study.Document)
        RUN["waiting"] = waiting
        if not waiting:
            state = job.poll()
        else:
            state = job.state
        _update_status()
        if state != "running":
            RUN["job"] = None
            notes = list(getattr(job, "notes", None) or [])
            message = job.message
            if state == "done" and RUN["kind"] == "mesh" and isinstance(job.summary, dict):
                info = job.summary
                if info.get("nodes"):
                    message = "Mesh made: %s nodes, %s elements." % (
                        info.get("nodes"),
                        info.get("elements"),
                    )
            if notes:
                message = (message + " " if message else "") + " ".join(notes)
            _after(study, state, message)
    except Exception as exc:
        warn("solve: %s" % exc)
        RUN["job"] = None
        RUN["queue"] = []
        _finish_all()


def _after(study, state, message):
    """One study's job ended."""
    sim = _sim()
    if study is not None:
        RUN["results"][study.Name] = (state, message)
        if state == "done":
            if RUN["kind"] == "mesh":
                show_mesh(study)
            else:
                _keep_out_of_date(study)
                loose = loose_result(study)
                if loose:
                    state, message = "suspect", loose
                    RUN["results"][study.Name] = (state, message)
                    log("%s: %s" % (study.Label, loose))
                else:
                    RUN["last_done"] = study
            log("%s %s" % (study.Label, "meshed" if RUN["kind"] == "mesh" else "solved"))
        try:
            sim.summary(study)
        except Exception:
            pass
    _update_status()
    if _next() is None:
        _finish_all()


def model_size(study):
    """The diagonal of the study's bodies (mm)."""
    box = None
    for body in _sim().study_bodies(study):
        b = bodies.global_shape(body, copy=False).BoundBox
        if box is None:
            box = b
        else:
            box.add(b)
    return box.DiagonalLength if box is not None else 0.0


def loose_result(study):
    """A sentence when a solve "worked" but the model moved further than half its own size:
    it was not held enough (a part could still turn about a held edge or slide), CalculiX
    found a mechanism instead of an error, and the numbers mean nothing. None otherwise."""
    try:
        data = _sim().summary(study) or {}
        moved = (data.get("stats", {}).get("displacement", {}) or {}).get("max")
        size = model_size(study)
        if moved is None or size <= 0 or moved <= 0.5 * size:
            return None
        from . import simulation_core as core

        return (
            "Solved, but the model moved %s mm, more than half its own size (%s mm): it is not "
            "held enough (a part can still turn or slide about what holds it). Check the "
            "constraints (DOF View), then solve again: these results are not meaningful."
            % (core.fmt(moved, 3), core.fmt(size, 3))
        )
    except Exception:
        return None


def _keep_out_of_date(study):
    """The design or the study changed while it solved: the results are of the setup the solve
    started from, so they show as out of date."""
    sim = _sim()
    try:
        started = RUN["signature"]
        data = sim.summary(study)
        if started and data and data.get("signature") != started:
            data["signature"] = started
            bodies.save_meta(study, sim.RESULT_PROP, data)
    except Exception as exc:
        warn("solve: %s" % exc)


def _finish_all():
    timer = RUN["timer"]
    if timer is not None and not RUN.get("draining"):
        timer.stop()
    RUN["job"] = None
    RUN["study"] = None
    RUN["queue"] = []
    RUN["waiting"] = False
    _update_status(final=True)
    _ui().refresh()
    done = RUN["last_done"]
    RUN["last_done"] = None
    if done is not None and bodies.alive(done) and RUN["kind"] == "solve":
        _ui().show_results(done)


def cancel():
    """Cancel the solve running now and the ones waiting (Fusion: Cancel in Job Status)."""
    RUN["queue"] = []
    job = RUN["job"]
    if job is not None:
        job.cancel()
        log("solve cancelled")
    _update_status()


# -- progress window (Fusion's Job Status, research 3.10) ----------------------------------------
STATUS_ICONS = {
    "done": "sim_stage_done",
    "running": "sim_stage_running",
    "waiting": "sim_stage_waiting",
    "failed": "sim_stage_failed",
    "cancelled": "sim_stage_failed",
}


class StatusDialog(FocusBack, QtWidgets.QDialog):
    def __init__(self):
        super().__init__(Gui.getMainWindow())
        self.setObjectName("SciForgeSimJobStatus")
        self.setWindowTitle("Job Status")
        layout = QtWidgets.QVBoxLayout(self)
        self.title = QtWidgets.QLabel("")
        self.title.setObjectName("SciForgeSimJobTitle")
        self.title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title)
        self.stages = QtWidgets.QListWidget()
        self.stages.setObjectName("SciForgeSimJobStages")
        self.stages.setMinimumHeight(130)
        layout.addWidget(self.stages)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setObjectName("SciForgeSimJobProgress")
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)
        self.elapsed = QtWidgets.QLabel("")
        self.elapsed.setObjectName("SciForgeSimJobElapsed")
        layout.addWidget(self.elapsed)
        self.studies = QtWidgets.QListWidget()
        self.studies.setObjectName("SciForgeSimJobStudies")
        self.studies.setMaximumHeight(90)
        layout.addWidget(self.studies)
        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("SciForgeSimJobMessage")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setObjectName("SciForgeSimJobCancel")
        self.cancel_button.clicked.connect(cancel)
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.setObjectName("SciForgeSimJobClose")
        self.close_button.clicked.connect(self.hide)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.resize(460, 380)


def show_status():
    dialog = RUN["status"]
    if dialog is None or not _alive(dialog):
        dialog = StatusDialog()
        RUN["status"] = dialog
    dialog.show()
    dialog.raise_()
    _update_status()
    return dialog


def status_dialog():
    dialog = RUN["status"]
    return dialog if dialog is not None and _alive(dialog) else None


def _update_status(final=False):
    dialog = status_dialog()
    if dialog is None:
        return
    try:
        job = RUN["job"]
        study = RUN["study"]
        stages = [k for k, _w in score.STAGE_WORDS]
        if RUN["kind"] == "mesh":
            stages = ["model", "mesh"]
        if job is not None and study is not None:
            what = "Meshing" if RUN["kind"] == "mesh" else "Solving"
            dialog.title.setText("%s %s on this computer" % (what, study.Label))
            rows = score.stage_rows(job.stage, job.state, stages)
            dialog.elapsed.setText(
                "Elapsed: %s" % score.elapsed_text(time.time() - (RUN["started"] or time.time()))
            )
            done = sum(1 for r in rows if r[2] == "done")
            dialog.bar.setValue(int(100.0 * done / max(len(rows), 1)))
            note = job.message
            if RUN["waiting"]:
                note = "Waiting for the open command to finish (OK or Cancel), then it goes on."
            dialog.message.setStyleSheet("")
            dialog.message.setText(note)
            _fill_stages(dialog, rows)
            dialog.cancel_button.setEnabled(True)
        elif final or job is None:
            dialog.cancel_button.setEnabled(False)
            results = RUN["results"]
            failed = [(n, r) for n, r in results.items() if r[0] != "done"]
            if failed:
                name, (state, message) = failed[-1]
                study = App.ActiveDocument.getObject(name) if App.ActiveDocument else None
                label = study.Label if study is not None else name
                dialog.title.setText("%s: %s" % (label, score.STATE_WORDS.get(state, state)))
                dialog.message.setStyleSheet(
                    "color: #ff8a80;" if state in ("failed", "suspect") else ""
                )
                dialog.message.setText(message or "")
                dialog.bar.setValue(0)
            elif results:
                dialog.title.setText("Done")
                dialog.message.setStyleSheet("")
                said = " ".join(m for _state, m in results.values() if m and m != "Done")
                dialog.message.setText(
                    (said + " " if said else "")
                    + (
                        "The mesh is shown on the model."
                        if RUN["kind"] == "mesh"
                        else "The results are shown (RESULTS tab)."
                    )
                )
                dialog.bar.setValue(100)
                rows = score.stage_rows("results", "done", stages)
                _fill_stages(dialog, rows)
        _fill_studies(dialog)
    except RuntimeError:
        pass
    except Exception as exc:
        warn("job status: %s" % exc)


def _fill_stages(dialog, rows):
    if dialog.stages.count() != len(rows):
        dialog.stages.clear()
        for _key, words, _status in rows:
            dialog.stages.addItem(words)
    for i, (_key, words, status) in enumerate(rows):
        item = dialog.stages.item(i)
        item.setText("%s  (%s)" % (words, score.STATE_WORDS.get(status, status).lower()))
        item.setIcon(ui_icon(STATUS_ICONS.get(status, "sim_stage_waiting")))
        item.setData(QtCore.Qt.UserRole, status)


def _fill_studies(dialog):
    rows = []
    for name, (state, _message) in RUN["results"].items():
        obj = App.ActiveDocument.getObject(name) if App.ActiveDocument else None
        rows.append(
            "%s: %s" % (obj.Label if obj is not None else name, score.STATE_WORDS.get(state, state))
        )
    if RUN["study"] is not None and bodies.alive(RUN["study"]):
        rows.append("%s: running" % RUN["study"].Label)
    for study in RUN["queue"]:
        if bodies.alive(study):
            rows.append("%s: waiting" % study.Label)
    if [dialog.studies.item(i).text() for i in range(dialog.studies.count())] != rows:
        dialog.studies.clear()
        dialog.studies.addItems(rows)


def stage_states():
    """[(stage, status)] shown in the progress window (tests)."""
    dialog = status_dialog()
    if dialog is None:
        return []
    out = []
    for i in range(dialog.stages.count()):
        item = dialog.stages.item(i)
        out.append((item.text(), item.data(QtCore.Qt.UserRole)))
    return out


def last_results():
    """{study name: (state, message)} of the last run (tests)."""
    return dict(RUN["results"])


# -- Generate Mesh --------------------------------------------------------------------------------
def generate_mesh(study):
    """SETUP > SOLVE > Generate Mesh (and the browser's Mesh row): the mesh made now (the
    engine's mesh-only job: no constraints or loads needed) and shown on the model."""
    from . import commands, simulation_dialogs

    if study is None or simulation_dialogs._busy(study):
        return False
    if not commands.finish_open_dialog():
        return False
    return start([study], "mesh")


def mesh_object(study):
    """The study's newest mesh object (Generate Mesh's, else the last solve's), or None."""
    try:
        return _sim().mesh_object(study) if study is not None else None
    except Exception:
        return None


def show_mesh(study):
    """The study's mesh drawn on the model (its faces with the element edges)."""
    try:
        mesh = mesh_object(study)
        if mesh is None or mesh.ViewObject is None:
            return False
        hide_mesh()
        vobj = mesh.ViewObject
        try:
            # the element edges over the model's own faces (mesh faces drawn at the same
            # place as the body's would flicker through them)
            modes = list(vobj.listDisplayModes())
            vobj.DisplayMode = "Wireframe" if "Wireframe" in modes else modes[0]
        except Exception:
            pass
        vobj.Visibility = True
        MESH["shown"] = (study.Document.Name, study.Name)
        log("mesh of %s shown" % study.Label)
        return True
    except Exception as exc:
        warn("mesh display: %s" % exc)
        return False


def hide_mesh():
    """The mesh shown by Generate Mesh hidden again."""
    shown, MESH["shown"] = MESH["shown"], None
    if shown is None:
        return
    try:
        doc = App.getDocument(shown[0])
        study = doc.getObject(shown[1]) if doc is not None else None
        mesh = mesh_object(study) if study is not None else None
        if mesh is not None and mesh.ViewObject is not None:
            mesh.ViewObject.Visibility = False
    except Exception:
        pass


def mesh_shown():
    """True while Generate Mesh's mesh is shown on the model (the menu's tick)."""
    return MESH["shown"] is not None


def toggle_mesh():
    """SETUP > DISPLAY > Show Mesh: the active study's mesh on the model, or not."""
    from . import commands

    if mesh_shown():
        hide_mesh()
        return False
    study = _ui().active_study()
    if study is None:
        return False
    if mesh_object(study) is None:
        commands.tell("No mesh yet: SOLVE > Generate Mesh makes it.")
        return False
    return show_mesh(study)

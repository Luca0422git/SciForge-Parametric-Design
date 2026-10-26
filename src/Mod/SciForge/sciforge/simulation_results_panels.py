# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's dialogs: Surface Probes and Slice Plane (task panels with Close / OK,
nothing to undo: they only change what is drawn), Results Details, Report, Reaction Force, and
the solve run from out-of-date results when sim-ui's Solve command is not there. The controller
is simulation_results_ui.py; the rules simulation_results_core.py.
"""

import os
import tempfile

import FreeCAD as App
import FreeCADGui as Gui

from . import log, simulation, taskui, ui_icon, warn
from . import simulation_core as sim
from . import simulation_results as results_data
from . import simulation_results_core as core
from .compat import QtCore, QtGui, QtWidgets

OPEN = {"details": None, "report": None, "reactions": None, "solve": None}

PANEL_STYLE = """
QLabel[role="dim"] { color: #c3cad4; }
QLabel[role="warning"] { color: #ffcc66; }
"""


def _finish_open():
    from . import commands

    return commands.finish_open_dialog()


def _main():
    return Gui.getMainWindow()


# -- Surface Probes --------------------------------------------------------------------------------
class ProbePanel:
    """Surface Probes: each click on the result adds a probe (a tag with the value there) until
    Close; Clear All removes them. The probes stay on the result after Close (Fusion)."""

    title = "Surface Probes"

    def __init__(self, session):
        self.session = session
        self._closed = False
        self._press = None
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("SciForgeSimProbes")
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(ui_icon("simr_probe"))
        self.form.setStyleSheet(PANEL_STYLE)
        box = QtWidgets.QVBoxLayout(self.form)
        hint = QtWidgets.QLabel(
            "Click on the result to read the value there. Each click adds a probe; they show "
            "the result chosen in the legend."
        )
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.listing = QtWidgets.QListWidget()
        self.listing.setObjectName("SciForgeSimProbeList")
        box.addWidget(self.listing)
        self.clear_button = QtWidgets.QPushButton("Clear All")
        self.clear_button.setObjectName("SciForgeSimProbeClear")
        self.clear_button.clicked.connect(self.clear)
        box.addWidget(self.clear_button)
        self.callbacks = []
        try:
            view = session.view
            self.callbacks.append(
                ("SoMouseButtonEvent", view.addEventCallback("SoMouseButtonEvent", self._mouse))
            )
        except Exception as exc:
            warn("Surface Probes: clicks unavailable: %s" % exc)
        self._guards = []
        try:
            from . import preview

            self._guards = [preview.EscapeCancels(self)]
        except Exception as exc:
            warn("Surface Probes: keys unavailable: %s" % exc)
        session.panels.append(self)
        taskui.set_current(self)
        self.refresh()

    def _mouse(self, info):
        try:
            if self._closed or info.get("Button") != "BUTTON1":
                return
            x, y = info.get("Position", (0, 0))
            if info.get("State") == "DOWN":
                self._press = (x, y)
                return
            if info.get("State") != "UP" or self._press is None:
                return
            px, py = self._press
            self._press = None
            if abs(px - x) > 4 or abs(py - y) > 4:
                return  # a drag (orbit, pan, box): not a probe
            QtCore.QTimer.singleShot(0, lambda: self._probe(x, y))
        except Exception as exc:
            warn("Surface Probes: %s" % exc)

    def _probe(self, x, y):
        try:
            if self._closed:
                return
            probe = self.session.add_probe_at(x, y)
            if probe is None:
                return
            self.refresh()
            log("results: probe added")
        except Exception as exc:
            warn("Surface Probes: %s" % exc)

    def refresh(self):
        self.listing.clear()
        for tag in self.session.tag_list:
            if tag.get("kind") == "probe":
                self.listing.addItem(tag.get("text", ""))
        self.clear_button.setEnabled(bool(self.session.probes))

    def clear(self):
        try:
            self.session.clear_probes()
            self.refresh()
        except Exception as exc:
            warn("Surface Probes: %s" % exc)

    # task dialog
    def getStandardButtons(self):
        buttons = QtWidgets.QDialogButtonBox.Close
        return getattr(buttons, "value", buttons)

    def accept(self):
        return self.close()

    def reject(self):
        return self.close()

    def finish(self):
        self.close()

    def close(self):
        if self._closed:
            return True
        self._closed = True
        for kind, callback in self.callbacks:
            try:
                self.session.view.removeEventCallback(kind, callback)
            except Exception:
                pass
        self.callbacks = []
        for guard in self._guards:
            try:
                guard.remove()
            except Exception:
                pass
        self._guards = []
        if self in self.session.panels:
            self.session.panels.remove(self)
        if taskui.current() is self:
            taskui.set_current(None)
        try:
            Gui.Control.closeDialog()
        except Exception:
            pass
        return True


def probes(session):
    if not _finish_open():
        return None
    panel = ProbePanel(session)
    Gui.Control.showDialog(panel)
    log("Surface Probes started")
    return panel


# -- Slice Plane -----------------------------------------------------------------------------------
class SlicePanel:
    """Slice Plane: a plane across X, Y or Z cuts the result; the cut face is coloured with the
    result inside the part. Style: cut the result away on one side, or show the slice alone
    (the whole result see-through around it). OK keeps it, Cancel / Esc puts back what was
    there, Remove Slice takes it away."""

    title = "Slice Plane"

    def __init__(self, session):
        self.session = session
        self._closed = False
        self.before = dict(session.slice) if session.slice else None
        data = session.data
        self.low = data.points.min(axis=0) if len(data.points) else [0.0, 0.0, 0.0]
        self.high = data.points.max(axis=0) if len(data.points) else [1.0, 1.0, 1.0]
        spec = dict(session.slice) if session.slice else None
        if spec is None:
            centre = [(float(a) + float(b)) / 2.0 for a, b in zip(self.low, self.high)]
            spec = {"axis": "x", "offset": centre[0], "flip": False, "style": "clip"}
        self.spec = spec
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("SciForgeSimSlice")
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(ui_icon("simr_slice"))
        layout = QtWidgets.QFormLayout(self.form)
        self.axis_box = QtWidgets.QComboBox()
        self.axis_box.setObjectName("SciForgeSimSliceAxis")
        for key, name in (
            ("x", "Across X (YZ plane)"),
            ("y", "Across Y (XZ plane)"),
            ("z", "Across Z (XY plane)"),
        ):
            self.axis_box.addItem(name, key)
        self.axis_box.setCurrentIndex(max(0, self.axis_box.findData(spec["axis"])))
        self.axis_box.currentIndexChanged.connect(self._axis_changed)
        layout.addRow("Plane", self.axis_box)
        self.offset = QtWidgets.QDoubleSpinBox()
        self.offset.setObjectName("SciForgeSimSliceOffset")
        self.offset.setDecimals(3)
        self.offset.setSuffix(" mm")
        self.offset.setKeyboardTracking(False)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setObjectName("SciForgeSimSliceSlider")
        self.slider.setRange(0, 1000)
        self._set_range()
        self.offset.setValue(float(spec["offset"]))
        self._sync_slider()
        self.offset.valueChanged.connect(self._offset_changed)
        self.slider.valueChanged.connect(self._slider_moved)
        layout.addRow("Position", self.offset)
        layout.addRow("", self.slider)
        self.flip = QtWidgets.QCheckBox("Flip (keep the other side)")
        self.flip.setObjectName("SciForgeSimSliceFlip")
        self.flip.setChecked(bool(spec.get("flip")))
        self.flip.toggled.connect(self._changed)
        layout.addRow("", self.flip)
        self.style_box = QtWidgets.QComboBox()
        self.style_box.setObjectName("SciForgeSimSliceStyle")
        self.style_box.addItem("Cut the result away", "clip")
        self.style_box.addItem("Slice alone", "slice")
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(spec.get("style", "clip"))))
        self.style_box.currentIndexChanged.connect(self._changed)
        layout.addRow("Style", self.style_box)
        self.remove_button = QtWidgets.QPushButton("Remove Slice")
        self.remove_button.setObjectName("SciForgeSimSliceRemove")
        self.remove_button.clicked.connect(self.remove)
        layout.addRow("", self.remove_button)
        self._guards = []
        try:
            from . import preview

            self._guards = [preview.EscapeCancels(self)]
        except Exception as exc:
            warn("Slice Plane: keys unavailable: %s" % exc)
        session.panels.append(self)
        taskui.set_current(self)
        self._changed()

    def _range(self):
        i = "xyz".index(self.spec["axis"])
        return float(self.low[i]), float(self.high[i])

    def _set_range(self):
        lo, hi = self._range()
        pad = max((hi - lo) * 0.02, 1e-3)
        self.offset.blockSignals(True)
        self.offset.setRange(lo - pad, hi + pad)
        self.offset.setSingleStep(max((hi - lo) / 50.0, 0.01))
        self.offset.blockSignals(False)

    def _sync_slider(self):
        lo, hi = self._range()
        span = hi - lo if hi > lo else 1.0
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(1000 * (self.offset.value() - lo) / span)))
        self.slider.blockSignals(False)

    def _axis_changed(self, _index):
        self.spec["axis"] = self.axis_box.currentData()
        self._set_range()
        lo, hi = self._range()
        self.offset.blockSignals(True)
        self.offset.setValue((lo + hi) / 2.0)
        self.offset.blockSignals(False)
        self._sync_slider()
        self._changed()

    def _offset_changed(self, _value):
        self._sync_slider()
        self._changed()

    def _slider_moved(self, value):
        lo, hi = self._range()
        self.offset.blockSignals(True)
        self.offset.setValue(lo + (hi - lo) * value / 1000.0)
        self.offset.blockSignals(False)
        self._changed()

    def _changed(self, *_args):
        try:
            if self._closed:
                return
            self.spec = {
                "axis": self.axis_box.currentData(),
                "offset": float(self.offset.value()),
                "flip": bool(self.flip.isChecked()),
                "style": self.style_box.currentData(),
            }
            self.session.set_slice(self.spec)
        except Exception as exc:
            warn("Slice Plane: %s" % exc)

    def remove(self):
        try:
            self.session.set_slice(None)
            self.before = None
            self._close_dialog()
            log("results: slice removed")
        except Exception as exc:
            warn("Slice Plane: %s" % exc)

    # task dialog
    def getStandardButtons(self):
        buttons = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        return getattr(buttons, "value", buttons)

    def accept(self):
        log("results: slice plane %s at %s mm" % (self.spec["axis"], core.fmt(self.spec["offset"])))
        return self._close_dialog()

    def reject(self):
        try:
            self.session.set_slice(self.before)
        except Exception as exc:
            warn("Slice Plane: %s" % exc)
        return self._close_dialog()

    def finish(self):
        self.accept()

    def close(self):
        self._close_dialog()

    def _close_dialog(self):
        if self._closed:
            return True
        self._closed = True
        for guard in self._guards:
            try:
                guard.remove()
            except Exception:
                pass
        self._guards = []
        if self in self.session.panels:
            self.session.panels.remove(self)
        if taskui.current() is self:
            taskui.set_current(None)
        try:
            Gui.Control.closeDialog()
        except Exception:
            pass
        return True


def slice_panel(session):
    if not _finish_open():
        return None
    panel = SlicePanel(session)
    Gui.Control.showDialog(panel)
    log("Slice Plane started")
    return panel


# -- Results Details -------------------------------------------------------------------------------
class DetailsDialog(QtWidgets.QDialog):
    """Results Details (Fusion opens it from the legend): the lowest safety factor against the
    targets in a sentence with advice, the targets (and their bands on the model), per body the
    material, its strength, the highest stress, the lowest safety factor and the largest
    movement, every result's min and max, the limits of the study, the deformation scale."""

    def __init__(self, session):
        super().__init__(_main())
        self.setObjectName("SciForgeSimDetails")
        self.session = session
        self.setWindowTitle("Results Details")
        self.setModal(False)
        self.setMinimumWidth(620)
        self.setStyleSheet(PANEL_STYLE)
        box = QtWidgets.QVBoxLayout(self)
        self.headline = QtWidgets.QLabel("")
        self.headline.setObjectName("SciForgeSimVerdict")
        self.headline.setWordWrap(True)
        box.addWidget(self.headline)
        self.advice = QtWidgets.QLabel("")
        self.advice.setObjectName("SciForgeSimAdvice")
        self.advice.setWordWrap(True)
        box.addWidget(self.advice)
        self.stale = QtWidgets.QLabel(core.OUT_OF_DATE)
        self.stale.setObjectName("SciForgeSimDetailsOutOfDate")
        self.stale.setProperty("role", "warning")
        self.stale.setWordWrap(True)
        box.addWidget(self.stale)

        targets = QtWidgets.QHBoxLayout()
        targets.addWidget(QtWidgets.QLabel("Safety factor target:"))
        self.lower = QtWidgets.QDoubleSpinBox()
        self.lower.setObjectName("SciForgeSimTargetLower")
        self.upper = QtWidgets.QDoubleSpinBox()
        self.upper.setObjectName("SciForgeSimTargetUpper")
        for spin in (self.lower, self.upper):
            spin.setRange(0.01, sim.SAFETY_CAP)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
            spin.setKeyboardTracking(False)
        self.lower.setValue(session.targets[0])
        self.upper.setValue(session.targets[1])
        targets.addWidget(QtWidgets.QLabel("lower"))
        targets.addWidget(self.lower)
        targets.addWidget(QtWidgets.QLabel("upper"))
        targets.addWidget(self.upper)
        self.bands = QtWidgets.QCheckBox("Show the target bands on the model")
        self.bands.setObjectName("SciForgeSimTargetBands")
        self.bands.setChecked(bool(session.bands))
        targets.addWidget(self.bands)
        targets.addStretch(1)
        box.addLayout(targets)
        self.lower.valueChanged.connect(self._targets_changed)
        self.upper.valueChanged.connect(self._targets_changed)
        self.bands.toggled.connect(self._targets_changed)

        box.addWidget(QtWidgets.QLabel("Per body"))
        self.bodies = QtWidgets.QTableWidget(0, 6)
        self.bodies.setObjectName("SciForgeSimDetailsBodies")
        self.bodies.setHorizontalHeaderLabels(
            [
                "Body",
                "Material",
                "Strength (MPa)",
                "Max von Mises (MPa)",
                "Min safety factor",
                "Max displacement (mm)",
            ]
        )
        self.bodies.verticalHeader().setVisible(False)
        self.bodies.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        box.addWidget(self.bodies)
        box.addWidget(QtWidgets.QLabel("Every result"))
        self.results = QtWidgets.QTableWidget(0, 4)
        self.results.setObjectName("SciForgeSimDetailsResults")
        self.results.setHorizontalHeaderLabels(["Result", "Min", "Max", "Unit"])
        self.results.verticalHeader().setVisible(False)
        self.results.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        box.addWidget(self.results)
        self.mesh = QtWidgets.QLabel("")
        self.mesh.setProperty("role", "dim")
        self.mesh.setWordWrap(True)
        box.addWidget(self.mesh)
        limits = QtWidgets.QLabel(core.LIMITS)
        limits.setProperty("role", "dim")
        limits.setWordWrap(True)
        box.addWidget(limits)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(QtWidgets.QLabel("Deformation scale"))
        self.deformation = QtWidgets.QComboBox()
        self.deformation.setObjectName("SciForgeSimDetailsDeformation")
        for key, name in core.deformations():
            self.deformation.addItem(name, key)
        self.deformation.setCurrentIndex(max(0, self.deformation.findData(session.deformation)))
        self.deformation.currentIndexChanged.connect(self._deformation_changed)
        bottom.addWidget(self.deformation)
        bottom.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.setObjectName("SciForgeSimDetailsClose")
        close.setAutoDefault(False)  # Enter in a target field takes the value, not Close
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        box.addLayout(bottom)
        self.fill()

    def fill(self):
        session = self.session
        study = session.study
        if study is None:
            return
        lower, upper = session.targets
        state, head, advice = core.verdict(results_data.min_safety(study), lower, upper)
        self.state = state
        colours = {"below": "#7a2b2b", "meets": "#6b5520", "above": "#24476e", "none": "#4b5262"}
        self.headline.setText(head)
        self.headline.setStyleSheet(
            "QLabel { background: %s; color: #ffffff; padding: 8px; border-radius: 4px; "
            "font-weight: bold; }" % colours.get(state, "#3b4250")
        )
        self.advice.setText("\n".join("- " + a for a in advice))
        self.stale.setVisible(results_data.out_of_date(study))
        rows = results_data.body_rows(study)
        self.bodies.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = (
                row["body"],
                row["material"] or "-",
                "%s (%s)"
                % (core.fmt(row["strength"]), "yield" if row["basis"] == "yield" else "ultimate"),
                core.fmt(row["von_mises_max"]),
                core.fmt(row["safety_min"]),
                core.fmt(row["displacement_max"]),
            )
            for c, text in enumerate(cells):
                self.bodies.setItem(r, c, QtWidgets.QTableWidgetItem(str(text)))
        self.bodies.resizeColumnsToContents()
        stats = simulation.summary(study).get("stats") or {}
        keys = [k for k in core.result_keys() if k in stats]
        self.results.setRowCount(len(keys))
        for r, key in enumerate(keys):
            unit = session.unit(key)
            st = stats[key]
            cells = (
                core.result_name(key),
                core.fmt(core.convert(st.get("min"), unit)),
                core.fmt(core.convert(st.get("max"), unit)),
                unit or "-",
            )
            for c, text in enumerate(cells):
                self.results.setItem(r, c, QtWidgets.QTableWidgetItem(str(text)))
        self.results.resizeColumnsToContents()
        done = simulation.summary(study)
        mesh = done.get("mesh") or {}
        self.mesh.setText(
            "Mesh: %s nodes, %s elements (%s), average size %s mm. Solved %s in %s s."
            % (
                mesh.get("nodes", "-"),
                mesh.get("elements", "-"),
                "parabolic" if mesh.get("order") == "parabolic" else "linear",
                core.fmt(mesh.get("size")),
                done.get("solved", "-"),
                core.fmt(done.get("seconds")),
            )
        )

    def _targets_changed(self, *_args):
        try:
            lower, upper = core.targets(self.lower.value(), self.upper.value())
            self.session.targets = (lower, upper)
            self.session.bands = bool(self.bands.isChecked())
            if self.session.active:
                self.session.apply()
            self.fill()
        except Exception as exc:
            warn("Results Details: %s" % exc)

    def _deformation_changed(self, _index):
        try:
            key = self.deformation.currentData()
            if key and self.session.active:
                self.session.set_deformation(key)
        except Exception as exc:
            warn("Results Details: %s" % exc)

    def closeEvent(self, event):
        OPEN["details"] = None
        super().closeEvent(event)


def details(session):
    dialog = OPEN.get("details")
    try:
        if dialog is not None and dialog.isVisible() and dialog.session is session:
            dialog.fill()
            dialog.raise_()
            return dialog
        if dialog is not None:
            dialog.close()
    except RuntimeError:
        pass
    dialog = DetailsDialog(session)
    OPEN["details"] = dialog
    dialog.show()
    log("Results Details opened")
    return dialog


# -- Reaction Force --------------------------------------------------------------------------------
class ReactionsDialog(QtWidgets.QDialog):
    """The force each constraint takes to hold the part (as the solve worked it out)."""

    def __init__(self, session, found):
        super().__init__(_main())
        self.setObjectName("SciForgeSimReactions")
        self.setWindowTitle("Reaction Force")
        box = QtWidgets.QVBoxLayout(self)
        table = QtWidgets.QTableWidget(len(found), 5)
        table.setObjectName("SciForgeSimReactionTable")
        table.setHorizontalHeaderLabels(["Constraint", "X (N)", "Y (N)", "Z (N)", "Total (N)"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for r, (label, (fx, fy, fz)) in enumerate(sorted(found.items())):
            total = (fx * fx + fy * fy + fz * fz) ** 0.5
            for c, text in enumerate(
                (label, core.fmt(fx), core.fmt(fy), core.fmt(fz), core.fmt(total))
            ):
                table.setItem(r, c, QtWidgets.QTableWidgetItem(text))
        table.resizeColumnsToContents()
        box.addWidget(table)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        box.addWidget(close)
        self.table = table


def reactions(session):
    found = results_data.reactions(session.study)
    if not found:
        from . import commands

        commands.tell("This solve has no reaction forces: solve the study again.")
        return None
    dialog = ReactionsDialog(session, found)
    OPEN["reactions"] = dialog
    dialog.show()
    return dialog


# -- Report ----------------------------------------------------------------------------------------
PICTURES = ("safety", "von_mises", "displacement")


class ReportDialog(QtWidgets.QDialog):
    """Report (Fusion: RESULT TOOLS > Report): a title, an author, pictures or not, where to
    write it; Save, or Save and Open in the web browser."""

    def __init__(self, session):
        super().__init__(_main())
        self.setObjectName("SciForgeSimReport")
        self.session = session
        self.setWindowTitle("Report")
        self.setMinimumWidth(520)
        study = session.study
        layout = QtWidgets.QFormLayout(self)
        self.title_field = QtWidgets.QLineEdit("%s report" % study.Label)
        self.title_field.setObjectName("SciForgeSimReportTitle")
        layout.addRow("Title", self.title_field)
        self.author_field = QtWidgets.QLineEdit("")
        self.author_field.setObjectName("SciForgeSimReportAuthor")
        layout.addRow("Author", self.author_field)
        self.pictures = QtWidgets.QCheckBox(
            "Pictures of the safety factor, stress and " "displacement"
        )
        self.pictures.setObjectName("SciForgeSimReportPictures")
        self.pictures.setChecked(True)
        layout.addRow("", self.pictures)
        row = QtWidgets.QHBoxLayout()
        self.path_field = QtWidgets.QLineEdit(results_data.default_report_path(study))
        self.path_field.setObjectName("SciForgeSimReportPath")
        row.addWidget(self.path_field, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addRow("File", row)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        layout.addRow("", self.message)
        buttons = QtWidgets.QHBoxLayout()
        self.save_button = QtWidgets.QPushButton("Save")
        self.save_button.setObjectName("SciForgeSimReportSave")
        self.save_button.setDefault(True)  # Enter saves
        self.save_button.clicked.connect(lambda: self._save(False))
        self.open_button = QtWidgets.QPushButton("Save and Open")
        self.open_button.setObjectName("SciForgeSimReportOpen")
        self.open_button.clicked.connect(lambda: self._save(True))
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("SciForgeSimReportCancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(cancel)
        layout.addRow(buttons)
        self.written = None

    def _browse(self):
        try:
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save the report", self.path_field.text(), "Web page (*.html)"
            )
            if path:
                if not path.lower().endswith((".html", ".htm")):
                    path += ".html"
                self.path_field.setText(path)
        except Exception as exc:
            warn("Report: %s" % exc)

    def _save(self, open_after):
        path = self.path_field.text().strip()
        if not path:
            self.message.setText("Choose where to save the report.")
            return
        if not path.lower().endswith((".html", ".htm")):
            path += ".html"
        try:
            self.written = write(
                self.session,
                path,
                self.title_field.text().strip(),
                self.author_field.text().strip(),
                self.pictures.isChecked(),
            )
        except Exception as exc:
            self.message.setText("The report could not be saved: %s" % exc)
            log("report not saved: %s" % exc)
            return
        if open_after:
            try:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.written))
            except Exception as exc:
                warn("Report: could not open it: %s" % exc)
        self.accept()

    def done(self, code):
        OPEN["report"] = None
        super().done(code)


def report(session):
    dialog = ReportDialog(session)
    OPEN["report"] = dialog
    dialog.show()
    log("Report opened")
    return dialog


def write(session, path, title="", author="", pictures=True, size=(900, 600)):
    """Write the session's study report (with pictures of the results drawn now)."""
    study = session.study
    images = []
    folder = tempfile.mkdtemp(prefix="sciforge_report_")
    try:
        if pictures and session.active and session.view is not None:
            images = _pictures(session, folder, size)
        results_data.write_report(
            study,
            path,
            title or None,
            author,
            images,
            session.targets[0],
            session.targets[1],
        )
    finally:
        for name in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
        try:
            os.rmdir(folder)
        except OSError:
            pass
    log("report written: %s" % path)
    return path


def _pictures(session, folder, size):
    """A picture of each result in PICTURES (the view as it is, with the legend drawn in)."""
    out = []
    keep = session.result
    playing = session.anim["playing"]
    if playing:
        session.stop_animation()
    try:
        for key in PICTURES:
            try:
                session.set_result(key)
                QtWidgets.QApplication.processEvents()
                path = os.path.join(folder, "%s.png" % key)
                session.view.saveImage(path, size[0], size[1], "Current")
                if os.path.isfile(path):
                    _draw_legend(path, session.legend_info)
                    out.append((core.result_name(key), path))
            except Exception as exc:
                warn("report: picture of %s left out: %s" % (core.result_name(key), exc))
    finally:
        session.set_result(keep)
        if playing:
            session.play()
    return out


def _draw_legend(path, info):
    """Paint the legend (colour bar, values, the result's name) on a picture."""
    if not info:
        return
    image = QtGui.QImage(path)
    if image.isNull():
        return
    painter = QtGui.QPainter(image)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        height = min(260, image.height() - 60)
        left, top = 16, 40
        painter.fillRect(
            QtCore.QRectF(left - 8, top - 30, 170, height + 50), QtGui.QColor(43, 49, 59, 220)
        )
        painter.setPen(QtGui.QColor(245, 245, 245))
        title = info["title"] + (" (%s)" % info["unit"] if info.get("unit") else "")
        painter.drawText(QtCore.QPointF(left, top - 12), title)
        for i in range(height):
            t = 1.0 - (i + 0.5) / height
            if info.get("reverse"):
                t = 1.0 - t
            colour = core.map_colour(t, info.get("banded"))
            painter.fillRect(QtCore.QRectF(left, top + i, 16, 1.2), QtGui.QColor.fromRgbF(*colour))
        for _value, text, pos in info.get("ticks", []):
            y = top + height - pos * height
            painter.drawText(QtCore.QPointF(left + 24, y + 4), text)
        painter.drawText(QtCore.QPointF(left, top + height + 16), "Min %s" % info["min_text"])
    finally:
        painter.end()
    image.save(path)


# -- solving out-of-date results here (no Solve dialog of sim-ui) ----------------------------------
class _SolveHere:
    def __init__(self, session):
        self.session = session
        self.study = session.study
        self.job = simulation.Job(self.study)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._say("Solving: %s" % self.job.message)

    def _say(self, text):
        legend = self.session.legend
        try:
            if legend is not None:
                legend.warning.setText(text)
                legend.warning.setVisible(True)
                legend.solve_button.setEnabled(False)
        except RuntimeError:
            pass

    def _poll(self):
        try:
            state = self.job.poll()
            if state == "running":
                self._say("Solving: %s" % self.job.message)
                return
            self.timer.stop()
            OPEN["solve"] = None
            legend = self.session.legend
            try:
                if legend is not None:
                    legend.warning.setText(core.OUT_OF_DATE)
                    legend.solve_button.setEnabled(True)
            except RuntimeError:
                pass
            if state == "done":
                from . import simulation_results_ui as ui

                ui.show(self.study)
                self.session.refresh_status()
                if self.session.active:
                    self.session.apply()
            else:
                from . import commands

                commands.tell(self.job.message)
        except Exception as exc:
            self.timer.stop()
            OPEN["solve"] = None
            warn("Solve: %s" % exc)


def solve_here(session):
    if OPEN.get("solve") is not None:
        return OPEN["solve"]
    OPEN["solve"] = _SolveHere(session)
    return OPEN["solve"]


def close_all():
    for key in ("details", "report", "reactions"):
        dialog = OPEN.get(key)
        if dialog is None:
            continue
        try:
            dialog.close()
        except RuntimeError:
            pass
        OPEN[key] = None


def is_gui():
    return bool(App.GuiUp)

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's dialogs: Surface Probes, Point Probes, Slice Plane and Iso-surface (task
panels with Close / OK, nothing to undo: they only change what is drawn), Results Details,
Report, Reaction Force, Solver Data, and the solve run from out-of-date results when sim-ui's
Solve command is not there. The controller
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

OPEN = {
    "details": None,
    "report": None,
    "reactions": None,
    "solve": None,
    "range": None,
    "compare": None,
    "solver": None,
}

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

    def result_changed(self):  # (the legend's result or unit changed)
        self.refresh()

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
    """Slice Plane: a plane across X, Y or Z, or parallel to a face clicked on the result, cuts
    the result; the cut face is coloured with the result inside the part. Style: cut the
    result away on one side, or show the slice alone (the whole result see-through around it).
    OK keeps it, Cancel / Esc puts back what was there, Remove Slice takes it away."""

    title = "Slice Plane"

    def __init__(self, session):
        self.session = session
        self._closed = False
        self.before = dict(session.slice) if session.slice else None
        self._press = None
        data = session.data
        self.points = data.points
        self.low = data.points.min(axis=0) if len(data.points) else [0.0, 0.0, 0.0]
        self.high = data.points.max(axis=0) if len(data.points) else [1.0, 1.0, 1.0]
        spec = dict(session.slice) if session.slice else None
        if spec is None:
            centre = [(float(a) + float(b)) / 2.0 for a, b in zip(self.low, self.high)]
            spec = {"axis": "x", "offset": centre[0], "flip": False, "style": "clip"}
        self.spec = spec
        self.face_normal = spec.get("normal") if spec.get("axis") == "face" else None
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("SciForgeSimSlice")
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(ui_icon("simr_slice"))
        layout = QtWidgets.QFormLayout(self.form)
        hint = QtWidgets.QLabel(
            "Pick a direction, or click a flat face of the result to cut parallel to it. Drag "
            "the arrow or type the position to move the cut."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)
        self.axis_box = QtWidgets.QComboBox()
        self.axis_box.setObjectName("SciForgeSimSliceAxis")
        for key, name in (
            ("x", "Across X (YZ plane)"),
            ("y", "Across Y (XZ plane)"),
            ("z", "Across Z (XY plane)"),
        ):
            self.axis_box.addItem(name, key)
        if self.face_normal is not None:
            self.axis_box.addItem(self.FACE_ITEM, "face")
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
        self.callbacks = []
        try:
            self.callbacks.append(
                (
                    "SoMouseButtonEvent",
                    session.view.addEventCallback("SoMouseButtonEvent", self._mouse),
                )
            )
        except Exception as exc:
            warn("Slice Plane: clicks unavailable: %s" % exc)
        session.panels.append(self)
        taskui.set_current(self)
        self.arrow = None
        self._changed()
        self._make_arrow()

    FACE_ITEM = "Parallel to the face clicked"

    # a click on a face of the result: the plane parallel to it
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
                return  # a drag (orbit, pan, the arrow): not a pick
            QtCore.QTimer.singleShot(0, lambda: self._face_clicked(x, y))
        except Exception as exc:
            warn("Slice Plane: %s" % exc)

    def _face_clicked(self, x, y):
        try:
            if self._closed:
                return
            from . import simulation_results_ui as results_ui

            outward = results_ui.face_at(self.session, x, y)
            if outward is None:
                return
            spec = core.face_slice(outward, self.points, self.style_box.currentData())
            if spec is None:
                return
            self.use(spec)
            log("results: slice plane parallel to the face clicked")
        except Exception as exc:
            warn("Slice Plane: %s" % exc)

    def use(self, spec):
        """Show a slice spec in the fields (and apply it)."""
        if spec.get("axis") == "face":
            self.face_normal = tuple(spec["normal"])
            if self.axis_box.findData("face") < 0:
                self.axis_box.blockSignals(True)
                self.axis_box.addItem(self.FACE_ITEM, "face")
                self.axis_box.blockSignals(False)
        self.spec = dict(spec)
        for widget in (self.axis_box, self.flip, self.offset):
            widget.blockSignals(True)
        try:
            self.axis_box.setCurrentIndex(max(0, self.axis_box.findData(spec["axis"])))
            self.flip.setChecked(bool(spec.get("flip")))
            self._set_range()
            self.offset.setValue(float(spec["offset"]))
        finally:
            for widget in (self.axis_box, self.flip, self.offset):
                widget.blockSignals(False)
        self._sync_slider()
        self._changed()
        self._make_arrow()

    # the drag arrow on the plane (Fusion's slice plane manipulator)
    def _make_arrow(self):
        self._drop_arrow()
        try:
            lo, _hi = self._range()
            n = core.slice_normal(self.spec)
            centre = [(float(a) + float(b)) / 2.0 for a, b in zip(self.low, self.high)]
            along = sum(c * k for c, k in zip(centre, n))
            base = [c + (lo - along) * k for c, k in zip(centre, n)]
            self.arrow = taskui.ArrowDragger(
                App.Vector(*base),
                App.Vector(*n),
                float(self.offset.value()) - lo,
                on_drag=self._dragged,
                on_release=self._dragged,
            )
        except Exception as exc:
            self.arrow = None
            warn("Slice Plane: no drag arrow: %s" % exc)

    def _drop_arrow(self):
        arrow, self.arrow = getattr(self, "arrow", None), None
        if arrow is not None:
            try:
                arrow.remove()
            except Exception:
                pass

    def _dragged(self, distance):
        try:
            if self._closed:
                return
            lo, _hi = self._range()
            self.offset.setValue(lo + float(distance))
        except Exception as exc:
            warn("Slice Plane: %s" % exc)

    def _follow_arrow(self):
        arrow = getattr(self, "arrow", None)
        if arrow is None:
            return
        try:
            lo, _hi = self._range()
            want = float(self.offset.value()) - lo
            if abs(arrow.distance() - want) > 1e-9:
                arrow.set_distance(want)
        except Exception:
            pass

    def _range(self):
        return core.slice_range(self.spec, self.points)

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
        if self.spec["axis"] == "face":
            self.spec["normal"] = self.face_normal
        self._set_range()
        lo, hi = self._range()
        self.offset.blockSignals(True)
        self.offset.setValue((lo + hi) / 2.0)
        self.offset.blockSignals(False)
        self._sync_slider()
        self._changed()
        self._make_arrow()

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
            if self.spec["axis"] == "face":
                self.spec["normal"] = tuple(self.face_normal)
            self.session.set_slice(self.spec)
            self._follow_arrow()
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
        try:
            before = self.offset.value()
            self.offset.interpretText()  # a position typed and not yet taken
            if self.offset.value() != before:
                self._changed()
        except Exception as exc:
            warn("Slice Plane: %s" % exc)
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
        self._drop_arrow()
        for kind, callback in getattr(self, "callbacks", []):
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


def slice_panel(session):
    if not _finish_open():
        return None
    panel = SlicePanel(session)
    Gui.Control.showDialog(panel)
    log("Slice Plane started")
    return panel


# -- Point Probes ----------------------------------------------------------------------------------
def _length(text):
    """mm from what was typed in a coordinate cell ("12.5", "12.5 mm", "0.5 in"); None when it
    is not a length."""
    text = str(text).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        quantity = App.Units.Quantity(text)
        if quantity.Unit != App.Units.Quantity("1 mm").Unit:
            return None
        return float(quantity.getValueAs("mm"))
    except Exception:
        return None


class PointProbePanel:
    """Point Probes (Fusion): values inside the part. A click on the result, on a slice's cut
    face or on the iso-surface puts a probe there; its X, Y, Z (on the unloaded part, in mm)
    can then be typed to move it anywhere inside. The probes stay after Close."""

    title = "Point Probes"
    COLUMNS = ("Probe", "X (mm)", "Y (mm)", "Z (mm)", "Value")

    def __init__(self, session):
        self.session = session
        self._closed = False
        self._press = None
        self._filling = False
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("SciForgeSimPointProbes")
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(ui_icon("simr_point_probe"))
        self.form.setStyleSheet(PANEL_STYLE)
        box = QtWidgets.QVBoxLayout(self.form)
        hint = QtWidgets.QLabel(
            "Click on the result to put a probe there: on a Slice Plane's cut face or an "
            "Iso-surface it lands inside the part. Type X, Y and Z to move a probe anywhere "
            "inside (places on the unloaded part)."
        )
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setObjectName("SciForgeSimPointTable")
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._edited)
        box.addWidget(self.table)
        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("SciForgeSimPointMessage")
        self.message.setProperty("role", "warning")
        self.message.setWordWrap(True)
        box.addWidget(self.message)
        row = QtWidgets.QHBoxLayout()
        self.remove_button = QtWidgets.QPushButton("Remove")
        self.remove_button.setObjectName("SciForgeSimPointRemove")
        self.remove_button.clicked.connect(self.remove)
        self.clear_button = QtWidgets.QPushButton("Clear All")
        self.clear_button.setObjectName("SciForgeSimPointClear")
        self.clear_button.clicked.connect(self.clear)
        row.addWidget(self.remove_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        box.addLayout(row)
        self.callbacks = []
        try:
            view = session.view
            self.callbacks.append(
                ("SoMouseButtonEvent", view.addEventCallback("SoMouseButtonEvent", self._mouse))
            )
        except Exception as exc:
            warn("Point Probes: clicks unavailable: %s" % exc)
        self._guards = []
        try:
            from . import preview

            self._guards = [preview.EscapeCancels(self)]
        except Exception as exc:
            warn("Point Probes: keys unavailable: %s" % exc)
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
            warn("Point Probes: %s" % exc)

    def _probe(self, x, y):
        try:
            if self._closed:
                return
            point = self.session.add_point_at(x, y)
            if point is None:
                return
            self.refresh()
            self.table.selectRow(len(self.session.points) - 1)
            log("results: point probe added")
        except Exception as exc:
            warn("Point Probes: %s" % exc)

    def refresh(self):
        session = self.session
        unit = session.unit()
        self._filling = True
        try:
            self.table.setRowCount(len(session.points))
            for r, point in enumerate(session.points):
                value = session.point_value(point)
                if value is None:
                    shown = "outside the part"
                elif value != value:
                    shown = "-"
                else:
                    shown = core.with_unit(core.convert(value, unit), unit)
                cells = ["P%d" % (r + 1)] + [core.fmt_mm(c) for c in point["at"]] + [shown]
                for c, text in enumerate(cells):
                    item = QtWidgets.QTableWidgetItem(text)
                    flags = item.flags()
                    if c in (1, 2, 3):
                        item.setFlags(flags | QtCore.Qt.ItemIsEditable)
                    else:
                        item.setFlags(flags & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(r, c, item)
            self.table.resizeColumnsToContents()
        finally:
            self._filling = False
        self.remove_button.setEnabled(bool(session.points))
        self.clear_button.setEnabled(bool(session.points))

    def result_changed(self):  # (the legend's result or unit changed)
        self.refresh()

    def _edited(self, item):
        if self._filling or self._closed:
            return
        try:
            r, c = item.row(), item.column()
            if c not in (1, 2, 3) or r >= len(self.session.points):
                return
            value = _length(item.text())
            if value is None:
                self.message.setText("Type a length for %s, such as 12.5 or 0.5 in." % "XYZ"[c - 1])
                self.refresh()
                return
            at = list(self.session.points[r]["at"])
            at[c - 1] = value
            self.session.move_point(r, at)
            outside = self.session.point_value(self.session.points[r]) is None
            self.message.setText(
                "P%d is outside the part: it shows no value there." % (r + 1) if outside else ""
            )
            QtCore.QTimer.singleShot(0, self._refresh_later)  # (not while the cell is edited)
        except Exception as exc:
            warn("Point Probes: %s" % exc)

    def _refresh_later(self):
        try:
            if not self._closed:
                self.refresh()
        except Exception as exc:
            warn("Point Probes: %s" % exc)

    def remove(self):
        try:
            rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
            if not rows and self.session.points:
                rows = [len(self.session.points) - 1]
            for r in rows:
                self.session.remove_point(r)
            self.message.setText("")
            self.refresh()
        except Exception as exc:
            warn("Point Probes: %s" % exc)

    def clear(self):
        try:
            self.session.clear_points()
            self.message.setText("")
            self.refresh()
        except Exception as exc:
            warn("Point Probes: %s" % exc)

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


def point_probes(session):
    if not _finish_open():
        return None
    panel = PointProbePanel(session)
    Gui.Control.showDialog(panel)
    log("Point Probes started")
    return panel


# -- Iso-surface -----------------------------------------------------------------------------------
class IsoPanel:
    """Iso-surface: the surface inside the part where the result shown in the legend has one
    value, in that value's legend colour, with the result drawn see-through around it. The
    value is typed or slid between the result's lowest and highest; changing the result in
    the legend moves the surface to that result. OK keeps it, Cancel / Esc puts back what was
    there, Remove Iso-surface takes it away."""

    title = "Iso-surface"
    STEPS = 1000

    def __init__(self, session):
        self.session = session
        self._closed = False
        self.before = (session.iso_on, dict(session.iso_levels))
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("SciForgeSimIso")
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(ui_icon("simr_iso"))
        self.form.setStyleSheet(PANEL_STYLE)
        layout = QtWidgets.QFormLayout(self.form)
        self.result_label = QtWidgets.QLabel("")
        self.result_label.setObjectName("SciForgeSimIsoResult")
        layout.addRow("Result", self.result_label)
        self.value = QtWidgets.QDoubleSpinBox()
        self.value.setObjectName("SciForgeSimIsoValue")
        self.value.setDecimals(4)
        self.value.setKeyboardTracking(False)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setObjectName("SciForgeSimIsoSlider")
        self.slider.setRange(0, self.STEPS)
        layout.addRow("Value", self.value)
        layout.addRow("", self.slider)
        self.span_label = QtWidgets.QLabel("")
        self.span_label.setProperty("role", "dim")
        self.span_label.setWordWrap(True)
        layout.addRow(self.span_label)
        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("SciForgeSimIsoMessage")
        self.message.setProperty("role", "warning")
        self.message.setWordWrap(True)
        layout.addRow(self.message)
        self.remove_button = QtWidgets.QPushButton("Remove Iso-surface")
        self.remove_button.setObjectName("SciForgeSimIsoRemove")
        self.remove_button.clicked.connect(self.remove)
        layout.addRow("", self.remove_button)
        self.value.valueChanged.connect(self._value_changed)
        self.slider.valueChanged.connect(self._slider_moved)
        self._guards = []
        try:
            from . import preview

            self._guards = [preview.EscapeCancels(self)]
        except Exception as exc:
            warn("Iso-surface: keys unavailable: %s" % exc)
        session.panels.append(self)
        taskui.set_current(self)
        self.result_changed()
        self._apply()

    # the result shown (the legend may change it while the panel is open)
    def result_changed(self):
        session = self.session
        self.key = session.result
        self.unit = session.unit()
        lo, hi, _reverse = session.scale()
        stats = session.data.stats(self.key)
        low = stats.get("min") if stats.get("min") is not None else lo
        high = stats.get("max") if stats.get("max") is not None else hi
        if self.key == "safety":
            high = min(high, hi)
        self.low, self.high = float(low), float(high)
        if self.high <= self.low:
            self.high = self.low + 1e-9
        self.result_label.setText(core.result_name(self.key))
        factor = core.convert(1.0, self.unit) or 1.0
        self.value.blockSignals(True)
        self.value.setRange(
            min(self.low, self.high) * factor - abs(self.high - self.low) * factor,
            max(self.low, self.high) * factor + abs(self.high - self.low) * factor,
        )
        self.value.setSingleStep(max(abs(self.high - self.low) * factor / 50.0, 1e-6))
        self.value.setSuffix(" " + self.unit if self.unit else "")
        self.value.setValue(core.convert(session.iso_level(self.key), self.unit))
        self.value.blockSignals(False)
        self.span_label.setText(
            "%s runs from %s to %s."
            % (
                core.result_name(self.key),
                core.with_unit(core.convert(self.low, self.unit), self.unit),
                core.with_unit(core.convert(self.high, self.unit), self.unit),
            )
        )
        self._sync_slider()

    def _base(self, value):
        factor = core.convert(1.0, self.unit) or 1.0
        return float(value) / factor

    def _sync_slider(self):
        level = self._base(self.value.value())
        t = (level - self.low) / (self.high - self.low)
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(min(max(t, 0.0), 1.0) * self.STEPS)))
        self.slider.blockSignals(False)

    def _value_changed(self, _value):
        self._sync_slider()
        self._apply()

    def _slider_moved(self, step):
        level = self.low + (self.high - self.low) * step / float(self.STEPS)
        self.value.blockSignals(True)
        self.value.setValue(core.convert(level, self.unit))
        self.value.blockSignals(False)
        self._apply()

    def _apply(self):
        try:
            if self._closed:
                return
            if self.session.result != self.key:
                self.result_changed()
            self.session.set_iso(self._base(self.value.value()))
            empty = not self.session.display.iso_shown()
            self.message.setText(
                "Nothing in the part is at this value: pick one between the lowest and the "
                "highest."
                if empty
                else ""
            )
        except Exception as exc:
            warn("Iso-surface: %s" % exc)

    def remove(self):
        try:
            self.session.set_iso(None)
            self.before = (False, dict(self.session.iso_levels))
            self._close_dialog()
            log("results: iso-surface removed")
        except Exception as exc:
            warn("Iso-surface: %s" % exc)

    # task dialog
    def getStandardButtons(self):
        buttons = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        return getattr(buttons, "value", buttons)

    def accept(self):
        try:
            before = self.value.value()
            self.value.interpretText()  # a value typed and not yet taken
            if self.value.value() != before:
                self._apply()
            log(
                "results: iso-surface of %s at %s"
                % (
                    core.result_name(self.key),
                    core.with_unit(self.value.value(), self.unit),
                )
            )
        except Exception as exc:
            warn("Iso-surface: %s" % exc)
        return self._close_dialog()

    def reject(self):
        try:
            on, levels = self.before
            self.session.iso_levels = dict(levels)
            self.session.iso_on = on
            self.session.apply()
        except Exception as exc:
            warn("Iso-surface: %s" % exc)
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


def iso_panel(session):
    if not _finish_open():
        return None
    panel = IsoPanel(session)
    Gui.Control.showDialog(panel)
    log("Iso-surface started")
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


# -- Compare ---------------------------------------------------------------------------------------
class CompareDialog(QtWidgets.QDialog):
    """Compare: tick 2 to 4 of the design's studies with results."""

    def __init__(self, session):
        super().__init__(_main())
        self.setObjectName("SciForgeSimCompare")
        self.setWindowTitle("Compare")
        self.session = session
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Studies to compare (2 to %d):" % core.COMPARE_MOST))
        self.listing = QtWidgets.QListWidget()
        self.listing.setObjectName("SciForgeSimCompareStudies")
        from . import simulation_results_ui as ui

        self.studies = ui.studies_with_results(session.doc)
        current = session.study
        for study in self.studies:
            item = QtWidgets.QListWidgetItem(study.Label)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            ticked = study is current or len(self.studies) <= 2
            item.setCheckState(QtCore.Qt.Checked if ticked else QtCore.Qt.Unchecked)
            self.listing.addItem(item)
        self.listing.itemChanged.connect(lambda *_a: self._count())
        layout.addWidget(self.listing)
        note = QtWidgets.QLabel(
            "The studies show side by side on one colour scale: the same colour is the same "
            "value in every study."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.go = QtWidgets.QPushButton("Compare")
        self.go.setObjectName("SciForgeSimCompareGo")
        self.go.setDefault(True)
        self.go.clicked.connect(self._go)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("SciForgeSimCompareCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.go)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._count()

    def chosen(self):
        out = []
        for row, study in enumerate(self.studies):
            item = self.listing.item(row)
            if item is not None and item.checkState() == QtCore.Qt.Checked:
                out.append(study)
        return out

    def _count(self):
        count = len(self.chosen())
        self.go.setEnabled(2 <= count <= core.COMPARE_MOST)
        self.go.setText("Compare %d Studies" % count if count else "Compare")

    def _go(self):
        try:
            chosen = self.chosen()
            self.accept()
            from . import simulation_results_ui as ui

            ui.start_compare(chosen)
        except Exception as exc:
            warn("Compare: %s" % exc)

    def done(self, code):
        OPEN["compare"] = None
        super().done(code)


def compare(session):
    dialog = CompareDialog(session)
    OPEN["compare"] = dialog
    dialog.show()
    log("Compare opened")
    return dialog


# -- Legend Min/Max --------------------------------------------------------------------------------
class RangeDialog(QtWidgets.QDialog):
    """Legend Min/Max (Fusion's legacy legend range): the values the colours run between, in the
    legend's unit; values beyond them take the end colours. Reset goes back to the result's own
    min and max. Not for the safety factor (Fusion offers none for it)."""

    def __init__(self, session):
        super().__init__(_main())
        self.setObjectName("SciForgeSimRange")
        self.session = session
        self.setWindowTitle("Legend Min/Max")
        self.unit = session.unit()
        key = session.result
        stats = session.data.stats(key)
        lo, hi, _reverse = session.scale()
        layout = QtWidgets.QFormLayout(self)
        layout.addRow(QtWidgets.QLabel(core.result_name(key)))
        self.low = QtWidgets.QDoubleSpinBox()
        self.low.setObjectName("SciForgeSimRangeMin")
        self.high = QtWidgets.QDoubleSpinBox()
        self.high.setObjectName("SciForgeSimRangeMax")
        span = max(abs(stats.get("max") or 0.0), abs(stats.get("min") or 0.0), 1e-9) * 10.0
        for spin in (self.low, self.high):
            spin.setDecimals(6)
            spin.setRange(-core.convert(span, self.unit), core.convert(span, self.unit))
            spin.setKeyboardTracking(False)
            spin.setSuffix(" " + self.unit if self.unit else "")
        self.low.setValue(core.convert(lo, self.unit))
        self.high.setValue(core.convert(hi, self.unit))
        layout.addRow("Min", self.low)
        layout.addRow("Max", self.high)
        own = QtWidgets.QLabel(
            "The result runs from %s to %s."
            % (
                core.with_unit(core.convert(stats.get("min"), self.unit), self.unit),
                core.with_unit(core.convert(stats.get("max"), self.unit), self.unit),
            )
        )
        own.setWordWrap(True)
        layout.addRow(own)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        layout.addRow(self.message)
        buttons = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton("Reset")
        reset.setObjectName("SciForgeSimRangeReset")
        reset.setAutoDefault(False)
        reset.clicked.connect(self._reset)
        ok = QtWidgets.QPushButton("OK")
        ok.setObjectName("SciForgeSimRangeOK")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("SciForgeSimRangeCancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addRow(buttons)

    def _base(self, value):
        factor = core.convert(1.0, self.unit) or 1.0
        return float(value) / factor

    def _ok(self):
        try:
            for spin in (self.low, self.high):
                spin.interpretText()  # what was typed and not yet taken (no Enter, no Tab)
            lo, hi = self.low.value(), self.high.value()
            if abs(hi - lo) < 1e-12:
                self.message.setText("Min and Max must differ.")
                return
            self.session.set_range((self._base(lo), self._base(hi)))
            self.accept()
        except Exception as exc:
            warn("Legend Min/Max: %s" % exc)

    def _reset(self):
        try:
            self.session.set_range(None)
            self.accept()
        except Exception as exc:
            warn("Legend Min/Max: %s" % exc)

    def done(self, code):
        OPEN["range"] = None
        super().done(code)


def legend_range(session):
    dialog = RangeDialog(session)
    OPEN["range"] = dialog
    dialog.show()
    log("Legend Min/Max opened")
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


# -- Solver Data -----------------------------------------------------------------------------------
class SolverDataDialog(QtWidgets.QDialog):
    """Solver Data (Fusion: INSPECT > Solver Data): how the study was solved - when, how long
    each step took, the mesh the solver worked on (nodes, elements, their quality), the
    adaptive mesh refinement's solves, and the solver's messages."""

    def __init__(self, session):
        super().__init__(_main())
        self.setObjectName("SciForgeSimSolverData")
        self.session = session
        study = session.study
        self.setWindowTitle("Solver Data")
        self.setMinimumWidth(480)
        self.setStyleSheet(PANEL_STYLE)
        box = QtWidgets.QVBoxLayout(self)
        heading = QtWidgets.QLabel(study.Label if study is not None else "")
        heading.setObjectName("SciForgeSimSolverStudy")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        box.addWidget(heading)
        self.rows = core.solver_rows(
            simulation.summary(study) if study is not None else {},
            _mesh_summary(study),
        )
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setObjectName("SciForgeSimSolverTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["", ""])
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        for section, items in self.rows:
            top = QtWidgets.QTreeWidgetItem([section, ""])
            bold = top.font(0)
            bold.setBold(True)
            top.setFont(0, bold)
            self.tree.addTopLevelItem(top)
            top.setFirstColumnSpanned(True)
            for name, value in items:
                child = QtWidgets.QTreeWidgetItem([name, value] if name else [value, ""])
                top.addChild(child)
                if not name:  # a message: the whole width
                    child.setFirstColumnSpanned(True)
                    child.setToolTip(0, value)
            top.setExpanded(True)
        self.tree.resizeColumnToContents(0)
        lines = sum(1 + len(items) for _section, items in self.rows)
        row = self.tree.sizeHintForRow(0) if lines else 20
        self.tree.setMinimumHeight(min(600, max(200, (row + 2) * (lines + 1))))
        box.addWidget(self.tree)
        if not self.rows:
            box.addWidget(QtWidgets.QLabel("This study has no solver data: solve it again."))
        stale = QtWidgets.QLabel(core.OUT_OF_DATE)
        stale.setProperty("role", "warning")
        stale.setWordWrap(True)
        stale.setVisible(study is not None and results_data.out_of_date(study))
        box.addWidget(stale)
        row = QtWidgets.QHBoxLayout()
        copy = QtWidgets.QPushButton("Copy")
        copy.setObjectName("SciForgeSimSolverCopy")
        copy.setAutoDefault(False)
        copy.setToolTip("Copy the solver data as text (to paste it in a message or a note)")
        copy.clicked.connect(self.copy)
        row.addWidget(copy)
        row.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.setObjectName("SciForgeSimSolverClose")
        close.clicked.connect(self.close)
        row.addWidget(close)
        box.addLayout(row)

    def text(self):
        study = self.session.study
        head = study.Label if study is not None else ""
        return (head + "\n" if head else "") + core.solver_text(self.rows)

    def copy(self):
        try:
            QtWidgets.QApplication.clipboard().setText(self.text())
            log("results: solver data copied")
        except Exception as exc:
            warn("Solver Data: %s" % exc)

    def closeEvent(self, event):
        OPEN["solver"] = None
        super().closeEvent(event)


def _mesh_summary(study):
    """The mesh statistics, when they are the solved mesh's (a mesh made again since, with
    Generate Mesh, is another mesh)."""
    if study is None:
        return {}
    try:
        stats = simulation.mesh_summary(study) or {}
        solved = simulation.summary(study).get("mesh") or {}
    except Exception:
        return {}
    same = stats.get("nodes") == solved.get("nodes") and stats.get("elements") == solved.get(
        "elements"
    )
    return stats if same and not stats.get("stale") else {}


def solver_data(session):
    dialog = OPEN.get("solver")
    try:
        if dialog is not None:
            dialog.close()
    except RuntimeError:
        pass
    dialog = SolverDataDialog(session)
    OPEN["solver"] = dialog
    dialog.show()
    log("Solver Data opened")
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
    """A picture of each result in PICTURES (the camera as it is, the whole part: no slice or
    iso-surface meanwhile; the legend drawn in)."""
    out = []
    keep = session.result
    playing = session.anim["playing"]
    if playing:
        session.stop_animation()
    inside = (session.slice, session.iso_on)
    session.slice, session.iso_on = None, False
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
        session.slice, session.iso_on = inside
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
            if info.get("bands"):  # the safety factor target bands
                value = (i + 0.5) / height * (info.get("hi") or sim.SAFETY_CAP)
                value = (info.get("hi") or sim.SAFETY_CAP) - value
                lower, upper = info.get("targets") or core.DEFAULT_TARGETS
                colour = core.BAND_COLOURS[core.target_band(value, lower, upper)]
            else:
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
    for key in ("details", "report", "reactions", "range"):
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

# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SETUP tab's dialogs that do not pick on the model (simulation_panels.py has those):
New Study (Fusion's study types, Static Stress available), Study Settings (General, Mesh,
Adaptive Mesh Refinement, Contacts), Study Materials (a row per body, "(Same as Model)", the
safety factor's basis, the properties used), Automatic Contacts and the Contact Manager (bodies
that touch are bonded), Load Case Attributes, the Pre-check list, gravity on / off, DOF View.

Every change is one undo step (the task panels open it, the New Study dialog opens its own);
Cancel and Esc leave nothing behind. Fusion's behaviour with sources:
docs/sciforge/dev/research/fusion-simulation.md (sections 2, 3.3, 3.6, 3.9, 3.11).
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import bodies, log, ui_icon, warn
from . import simulation_core as core
from . import simulation_setup_core as score
from .compat import QtCore, QtWidgets
from .taskui import Panel

OPEN = {"new_study": None, "dialogs": []}  # the open windows (tests, and to keep them alive)
NOTE_STYLE = "color: #9aa7b4;"
ERROR_STYLE = "color: #ff8a80;"


def _sim():
    from . import simulation

    return simulation


def _ui():
    from . import simulation_ui

    return simulation_ui


def _keep(dialog):
    OPEN["dialogs"] = [d for d in OPEN["dialogs"] if _alive(d)] + [dialog]
    return dialog


def _alive(widget):
    try:
        widget.isVisible()
        return True
    except RuntimeError:
        return False


def _transaction(doc, name, change):
    """Run `change()` as one undo step `name`; False (nothing kept) when it raises."""
    doc.openTransaction(name)
    try:
        change()
    except Exception:
        doc.abortTransaction()
        _close_active()
        raise
    doc.commitTransaction()
    _close_active()
    return True


def _close_active():
    try:
        App.closeActiveTransaction()
    except Exception:
        pass


def give_back_focus():
    """A SciForge window closed: the main window becomes the active one again, so its keys
    (Esc, Enter, Ctrl+Z over the 3D view) work at once (without a window manager, as on some
    Linux desktops and under xvfb, nobody else does it)."""

    def run():
        try:
            main = Gui.getMainWindow()
            if QtWidgets.QApplication.activeModalWidget() is None:
                main.activateWindow()
        except Exception:
            pass

    QtCore.QTimer.singleShot(0, run)


class FocusBack:
    """Mixin for SciForge's dialogs: closing one gives the main window the keyboard back."""

    def hideEvent(self, event):
        give_back_focus()
        super().hideEvent(event)


def _note(text, style=NOTE_STYLE):
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(style)
    return label


class _SimPanel(Panel):
    """A SETUP task dialog: one undo step, Esc cancels, Enter is OK."""

    simulation_dialog = True

    def __init__(self, doc, transaction):
        super().__init__(doc, transaction)
        self._keys = []
        try:
            from . import preview

            self._keys = [preview.EscapeCancels(self), preview.EnterFinishes(self)]
        except Exception as exc:
            warn("%s: keys unavailable: %s" % (self.title, exc))

    def cleanup(self):
        for key in self._keys:
            try:
                key.remove()
            except Exception:
                pass
        self._keys = []
        super().cleanup()

    def accept(self):
        if getattr(self, "_closed", False):
            return True
        try:
            problem = self.apply()
        except core.SimulationError as exc:
            problem = str(exc)
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))
            problem = "This could not be kept: %s" % exc
        if problem:
            self.message.setStyleSheet(ERROR_STYLE)
            self.message.setText(problem)
            return False
        done = super().accept()
        _ui().refresh()
        return done

    def reject(self):
        done = super().reject()
        _ui().refresh()
        return done

    def apply(self):
        """Make the change (inside the dialog's undo step); a sentence when it cannot."""
        return None


# -- New Study ----------------------------------------------------------------------------------
STUDY_ICONS = {"static_stress": "sim_static_stress"}


class NewStudyDialog(FocusBack, QtWidgets.QDialog):
    """Fusion's New Study: the study types as pictures, the one picked described in big on the
    right with a Settings gear, Create Study. Only Static Stress is available; every other type
    is shown greyed with "Not in SciForge yet" (research 2.1, 2.2)."""

    def __init__(self, doc):
        super().__init__(Gui.getMainWindow())
        self.doc = doc
        self.study = None
        self.settings = core.settings()  # what the gear changed before the study exists
        self.setObjectName("SciForgeSimNewStudy")
        self.setWindowTitle("New Study")
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        outer = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        outer.addLayout(row, 1)
        self.types = QtWidgets.QListWidget()
        self.types.setObjectName("SciForgeSimStudyTypes")
        self.types.setViewMode(QtWidgets.QListView.IconMode)
        self.types.setIconSize(QtCore.QSize(48, 48))
        self.types.setGridSize(QtCore.QSize(124, 96))
        self.types.setMovement(QtWidgets.QListView.Static)
        self.types.setResizeMode(QtWidgets.QListView.Adjust)
        self.types.setWordWrap(True)
        self.types.setMinimumSize(400, 330)
        for key, title, available, text in score.study_rows():
            item = QtWidgets.QListWidgetItem(
                ui_icon(STUDY_ICONS.get(key, "sim_study_other")), title
            )
            item.setData(QtCore.Qt.UserRole, key)
            item.setToolTip(text)
            if not available:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled & ~QtCore.Qt.ItemIsSelectable)
            self.types.addItem(item)
        self.types.currentItemChanged.connect(lambda *_a: self._picked())
        self.types.itemDoubleClicked.connect(lambda *_a: self.create())
        row.addWidget(self.types, 1)
        side = QtWidgets.QVBoxLayout()
        head = QtWidgets.QHBoxLayout()
        self.picture = QtWidgets.QLabel()
        self.picture.setFixedSize(96, 96)
        head.addWidget(self.picture)
        head.addStretch(1)
        self.gear = QtWidgets.QToolButton()
        self.gear.setObjectName("SciForgeSimNewStudySettings")
        self.gear.setIcon(ui_icon("sim_settings"))
        self.gear.setIconSize(QtCore.QSize(20, 20))
        self.gear.setToolTip("Study Settings (mesh, contacts) for the new study")
        self.gear.clicked.connect(self._settings)
        head.addWidget(self.gear, 0, QtCore.Qt.AlignTop)
        side.addLayout(head)
        self.title = QtWidgets.QLabel()
        self.title.setStyleSheet("font-size: 15px; font-weight: bold;")
        side.addWidget(self.title)
        self.text = QtWidgets.QLabel()
        self.text.setWordWrap(True)
        side.addWidget(self.text)
        side.addWidget(_note(score.LIMITS))
        side.addStretch(1)
        row.addLayout(side, 1)
        buttons = QtWidgets.QHBoxLayout()
        self.message = _note("", ERROR_STYLE)
        buttons.addWidget(self.message, 1)
        self.create_button = QtWidgets.QPushButton("Create Study")
        self.create_button.setObjectName("SciForgeSimCreateStudy")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self.create)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("SciForgeSimNewStudyCancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.create_button)
        buttons.addWidget(cancel)
        outer.addLayout(buttons)
        self.resize(760, 430)
        self.types.setCurrentRow(0)
        self._picked()

    def kind(self):
        item = self.types.currentItem()
        return item.data(QtCore.Qt.UserRole) if item is not None else None

    def _picked(self):
        try:
            item = self.types.currentItem()
            if item is None:
                return
            key = item.data(QtCore.Qt.UserRole)
            rows = {r[0]: r for r in score.study_rows()}
            _key, title, available, text = rows.get(key, (key, key, False, ""))
            self.title.setText(title)
            self.text.setText(text)
            self.picture.setPixmap(ui_icon(STUDY_ICONS.get(key, "sim_study_other")).pixmap(96, 96))
            self.create_button.setEnabled(bool(available))
            self.gear.setEnabled(bool(available))
        except Exception as exc:
            warn("new study: %s" % exc)

    def _settings(self):
        try:
            dialog = SettingsDialog(self, self.settings)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                self.settings = dialog.values()
        except Exception as exc:
            warn("study settings: %s" % exc)

    def create(self):
        try:
            kind = self.kind()
            if kind is None or not core.study_type_available(kind):
                self.message.setText(core.NOT_AVAILABLE)
                return
            doc = self.doc
            made = {}

            def change():
                made["study"] = _sim().create_study(doc, kind)
                _sim().set_settings(made["study"], self.settings)

            _transaction(doc, "New Simulation Study", change)
            self.study = made["study"]
            log("new study: %s" % self.study.Label)
            self.accept()
            _ui().set_active_study(self.study)
        except core.SimulationError as exc:
            self.message.setText(str(exc))
        except Exception as exc:
            warn("new study: %s" % exc)
            self.message.setText("The study could not be made: %s" % exc)

    def done(self, result):
        OPEN["new_study"] = None
        super().done(result)


def open_new_study():
    """Fusion's New Study dialog for the active design."""
    from . import commands

    doc = App.ActiveDocument
    if doc is None:
        commands.tell("Open a design first.")
        return None
    if not commands.finish_open_dialog():
        return None
    current = OPEN["new_study"]
    if current is not None and _alive(current) and current.isVisible():
        current.raise_()
        return current
    dialog = NewStudyDialog(doc)
    OPEN["new_study"] = dialog
    dialog.show()
    return dialog


def new_study_dialog():
    """The New Study dialog that is open, or None (tests)."""
    dialog = OPEN["new_study"]
    return dialog if dialog is not None and _alive(dialog) and dialog.isVisible() else None


# -- Study Settings -----------------------------------------------------------------------------
def _spin(name, low, high, value, decimals=1, suffix="", step=1.0, tip=""):
    box = QtWidgets.QDoubleSpinBox()
    box.setObjectName(name)
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    if suffix:
        box.setSuffix(suffix)
    box.setValue(float(value))
    if tip:
        box.setToolTip(tip)
    return box


# Adaptive refinement is wired in the engine when simulation_core says so (sim-core).
def _adaptive_built():
    """True once the engine runs adaptive refinement (sim-core's Job._adapt)."""
    try:
        return hasattr(_sim().Job, "_adapt") and hasattr(core, "adaptive_plan")
    except Exception:
        return False


ADAPTIVE_RESULT_NAMES = (
    ("von_mises", "Von Mises Stress"),
    ("displacement", "Displacement"),
    ("principal_1", "1st Principal Stress"),
    ("principal_3", "3rd Principal Stress"),
)


class SettingsForm(QtWidgets.QTabWidget):
    """Fusion's Study Settings tabs (research 2.3): General, Mesh, Adaptive Mesh Refinement,
    Contacts. What SciForge's mesher or solver cannot do is shown greyed with the reason."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("SciForgeSimSettingsTabs")
        self.base = core.settings(settings)
        mesh = self.base["mesh"]
        # General
        general = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(general)
        self.rigid = QtWidgets.QCheckBox("Remove rigid body modes")
        self.rigid.setObjectName("SciForgeSimRigidModes")
        self.rigid.setChecked(bool(self.base.get("remove_rigid", False)))
        self.rigid.setEnabled("remove_rigid" in core.DEFAULT_SETTINGS)
        self.rigid.setToolTip(
            "Only for a model held by nothing whose loads balance exactly (they sum to zero): "
            "SciForge then holds each free piece just enough. With constraints, leave it off."
        )
        form.addRow(self.rigid)
        self.keep = QtWidgets.QCheckBox("Keep the results in the design file")
        self.keep.setObjectName("SciForgeSimKeepResults")
        self.keep.setChecked(bool(self.base.get("keep_results", True)))
        self.keep.setEnabled("keep_results" in core.DEFAULT_SETTINGS)
        self.keep.setToolTip(
            "Off: only the summary is saved and the coloured results need a new solve after "
            "the design is opened again (a fine mesh can add many MB to the file)"
        )
        form.addRow(self.keep)
        form.addRow(_note(score.LIMITS))
        self.addTab(general, "General")
        # Mesh
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.size_kind = QtWidgets.QComboBox()
        self.size_kind.setObjectName("SciForgeSimMeshSizeKind")
        self.size_kind.addItem("Model based (% of model size)", "pct")
        self.size_kind.addItem("Absolute value (mm)", "mm")
        self.size_kind.setCurrentIndex(1 if float(mesh.get("size_mm") or 0) > 0 else 0)
        self.size_kind.currentIndexChanged.connect(self._size_kind_changed)
        form.addRow("Average Element Size", self.size_kind)
        self.size = _spin(
            "SciForgeSimMeshSize",
            0.5,
            50.0,
            mesh["size_pct"],
            1,
            " %",
            tip="The average element length as a share of the model's size (its diagonal)",
        )
        form.addRow("Size (% of model size)", self.size)
        self.size_mm = _spin(
            "SciForgeSimMeshSizeMM",
            0.05,
            10000.0,
            float(mesh.get("size_mm") or 0) or 2.0,
            2,
            " mm",
            0.5,
            "The average element length",
        )
        form.addRow("Size (mm)", self.size_mm)
        self.per_part = QtWidgets.QCheckBox("Scale Mesh Size Per Part")
        self.per_part.setObjectName("SciForgeSimMeshPerPart")
        self.per_part.setChecked(bool(mesh.get("scale_per_part")))
        self.per_part.setToolTip("Each body's elements sized from its own size, not the model's")
        form.addRow(self.per_part)
        self.order = QtWidgets.QComboBox()
        self.order.setObjectName("SciForgeSimMeshOrder")
        self.order.addItem("Parabolic", "parabolic")
        self.order.addItem("Linear", "linear")
        self.order.setCurrentIndex(0 if mesh["order"] == "parabolic" else 1)
        self.order.currentIndexChanged.connect(self._order_changed)
        form.addRow("Element Order", self.order)
        self.curved = QtWidgets.QCheckBox("Create Curved Mesh Elements")
        self.curved.setObjectName("SciForgeSimMeshCurved")
        self.curved.setChecked(bool(mesh["curved"]))
        form.addRow(self.curved)
        self.turn = _spin("SciForgeSimMeshTurn", 5.0, 90.0, mesh["max_turn"], 0, " deg")
        form.addRow("Max. Turn Angle on Curves", self.turn)
        self.ratio = _spin(
            "SciForgeSimMeshRatio",
            1.05,
            10.0,
            mesh.get("adjacent_ratio", 1.5),
            2,
            step=0.1,
            tip="How fast the elements may grow from small (local controls) to large",
        )
        form.addRow("Max. Adjacent Mesh Size Ratio", self.ratio)
        self.aspect = _spin(
            "SciForgeSimMeshAspect",
            1.5,
            1000.0,
            mesh.get("aspect_ratio", 10.0),
            1,
            tip="Elements stretched more than this are counted in the mesh statistics",
        )
        form.addRow("Max. Aspect Ratio", self.aspect)
        self.minimum = _spin("SciForgeSimMeshMin", 1.0, 100.0, mesh["min_pct"], 0, " %")
        form.addRow("Minimum Element Size (% of average size)", self.minimum)
        self.addTab(page, "Mesh")
        self._order_changed()
        self._size_kind_changed()
        # Adaptive Mesh Refinement
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        self.adaptive = QtWidgets.QComboBox()
        self.adaptive.setObjectName("SciForgeSimAdaptive")
        for label, key in (
            ("None", "none"),
            ("Low", "low"),
            ("Medium", "medium"),
            ("High", "high"),
            ("Custom", "custom"),
        ):
            self.adaptive.addItem(label, key)
        adaptive = self.base.get("adaptive") or {}
        index = self.adaptive.findData(adaptive.get("level", "none"))
        self.adaptive.setCurrentIndex(max(index, 0))
        self.adaptive.setEnabled(_adaptive_built())
        self.adaptive.currentIndexChanged.connect(self._adaptive_changed)
        form.addRow("Refinement", self.adaptive)
        self.passes = _spin(
            "SciForgeSimAdaptivePasses",
            1,
            10,
            adaptive.get("passes", 4),
            0,
            tip="The most solves, the first one included",
        )
        form.addRow("Number of refinements", self.passes)
        self.converge = _spin(
            "SciForgeSimAdaptiveTolerance",
            0.1,
            50.0,
            adaptive.get("tolerance", 5.0),
            1,
            " %",
            tip="It stops when the result changes by less than this between two solves",
        )
        form.addRow("Results convergence tolerance", self.converge)
        self.portion = _spin(
            "SciForgeSimAdaptivePortion",
            1.0,
            100.0,
            adaptive.get("portion", 10.0),
            0,
            " %",
            tip="The share of the elements made smaller at each pass",
        )
        form.addRow("Portion of elements to refine", self.portion)
        self.judge = QtWidgets.QComboBox()
        self.judge.setObjectName("SciForgeSimAdaptiveResult")
        for key, label in ADAPTIVE_RESULT_NAMES:
            self.judge.addItem(label, key)
        index = self.judge.findData(adaptive.get("result", "von_mises"))
        self.judge.setCurrentIndex(max(index, 0))
        form.addRow("Result to watch", self.judge)
        self._adaptive_changed()
        if not _adaptive_built():
            form.addRow(
                _note(
                    "Not in SciForge yet: make the Average Element Size smaller, or use Local "
                    "Mesh Control where the stress matters."
                )
            )
        self.addTab(page, "Adaptive Mesh Refinement")
        # Contacts
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        kind = QtWidgets.QComboBox()
        kind.setObjectName("SciForgeSimContactType")
        types = getattr(core, "CONTACT_TYPES", None) or (
            ("bonded", "Bonded", True),
            ("separation", "Separation", False),
            ("sliding", "Sliding", False),
            ("rough", "Rough", False),
            ("offset_bonded", "Offset Bonded", False),
        )
        refused = getattr(
            core, "CONTACT_NOT_AVAILABLE", "Not in SciForge yet: bodies that touch are bonded"
        )
        for key, title, available in types:
            kind.addItem(title, key)
            item = kind.model().item(kind.count() - 1)
            if not available:
                item.setEnabled(False)
                item.setToolTip(refused)
        form.addRow("Automatic Contacts", kind)
        self.tolerance = _spin(
            "SciForgeSimContactTolerance",
            0.0,
            10.0,
            self.base["contact_tolerance"],
            3,
            " mm",
            0.05,
        )
        form.addRow("Contact Detection Tolerance", self.tolerance)
        self.addTab(page, "Contacts")

    def _order_changed(self, *_a):
        self.curved.setEnabled(self.order.currentData() == "parabolic")

    def _adaptive_changed(self, *_a):
        """Fusion: the numbers are typed for Custom; a named level brings its own."""
        level = self.adaptive.currentData()
        built = _adaptive_built()
        custom = built and level == "custom"
        for widget in (self.passes, self.converge, self.portion):
            widget.setEnabled(custom)
        self.judge.setEnabled(built and level != "none")
        plan = None
        try:
            if built and level not in ("none", "custom"):
                plan = core.adaptive_plan({"level": level})
        except Exception:
            plan = None
        if plan is not None:
            for widget, value in zip((self.passes, self.converge, self.portion), plan):
                widget.setValue(float(value))

    def _size_kind_changed(self, *_a):
        absolute = self.size_kind.currentData() == "mm"
        self.size.setEnabled(not absolute)
        self.size_mm.setEnabled(absolute)

    def values(self):
        out = core.settings(self.base)
        absolute = self.size_kind.currentData() == "mm"
        out["mesh"].update(
            {
                "size_pct": float(self.size.value()),
                "order": self.order.currentData(),
                "curved": bool(self.curved.isChecked()),
                "max_turn": float(self.turn.value()),
                "min_pct": float(self.minimum.value()),
                "scale_per_part": bool(self.per_part.isChecked()),
            }
        )
        if "size_mm" in out["mesh"]:
            out["mesh"]["size_mm"] = float(self.size_mm.value()) if absolute else 0.0
        if "adjacent_ratio" in out["mesh"]:
            out["mesh"]["adjacent_ratio"] = float(self.ratio.value())
        if "aspect_ratio" in out["mesh"]:
            out["mesh"]["aspect_ratio"] = float(self.aspect.value())
        out["contact_tolerance"] = float(self.tolerance.value())
        if "remove_rigid" in out:
            out["remove_rigid"] = bool(self.rigid.isChecked())
        if "keep_results" in out:
            out["keep_results"] = bool(self.keep.isChecked())
        if _adaptive_built() and isinstance(out.get("adaptive"), dict):
            out["adaptive"]["level"] = self.adaptive.currentData()
            out["adaptive"]["result"] = self.judge.currentData()
            if self.adaptive.currentData() == "custom":
                out["adaptive"]["passes"] = int(self.passes.value())
                out["adaptive"]["tolerance"] = float(self.converge.value())
                out["adaptive"]["portion"] = float(self.portion.value())
        return out


class SettingsDialog(FocusBack, QtWidgets.QDialog):
    """Study Settings opened from the New Study dialog's gear (before the study exists)."""

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setObjectName("SciForgeSimSettingsDialog")
        self.setWindowTitle("Study Settings")
        layout = QtWidgets.QVBoxLayout(self)
        self.form = SettingsForm(settings, self)
        layout.addWidget(self.form)
        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def values(self):
        return self.form.values()


class SettingsPanel(_SimPanel):
    title = "Study Settings"
    icon = "sim_settings"
    last = None

    def __init__(self, doc, study):
        super().__init__(doc, "Study Settings")
        SettingsPanel.last = self
        self.study = study
        self.form.setObjectName("SciForgeSimSettings")
        self.tabs = SettingsForm(_sim().settings(study))
        self.layout.addRow(QtWidgets.QLabel(study.Label))
        self.layout.addRow(self.tabs)
        self.finish_layout()

    def apply(self):
        if not bodies.alive(self.study):
            return "The study is gone (undone or deleted)."
        _sim().set_settings(self.study, self.tabs.values())
        log("study settings of %s changed" % self.study.Label)
        return None


def _show_panel(panel):
    Gui.Control.showDialog(panel)
    return panel


def open_settings(study):
    from . import commands

    if not commands.finish_open_dialog() or _busy(study):
        return None
    return _show_panel(SettingsPanel(study.Document, study))


def _busy(study):
    """True (and the person told) while `study` is being solved: its setup waits."""
    try:
        from . import commands, simulation_solve_dialog

        if simulation_solve_dialog.solving(study):
            commands.tell(
                "%s is being solved: wait for the solve to end (or cancel it) before changing "
                "its setup." % study.Label
            )
            return True
    except Exception:
        pass
    return False


# -- Study Materials ----------------------------------------------------------------------------
SAME = "(Same as Model)"


def _material_rows():
    """[(label, key)] of the materials a study can use: SciForge's library and the user's."""
    from . import material

    rows = []
    try:
        for entry in material.entries():
            rows.append((entry["label"], entry["key"]))
        for entry in material.user_entries():
            rows.append((entry["label"], entry["key"]))
    except Exception as exc:
        warn("materials: %s" % exc)
    return rows


def _props_text(name, props, basis):
    """Lines of the properties a stress study uses, saying which ones SciForge filled in."""
    filled = set(props.get("filled") or [])
    lines = ["Material: %s" % name]
    rows = (
        ("youngs_mpa", "Young's Modulus", "MPa"),
        ("poisson", "Poisson's Ratio", ""),
        ("density", "Density", "kg/m^3"),
        ("yield_mpa", "Yield Strength", "MPa"),
        ("ultimate_mpa", "Ultimate Tensile Strength", "MPa"),
    )
    for key, label, unit in rows:
        value = props.get(key)
        if value is None or value != value:
            text = "%s: none" % label
        else:
            text = "%s: %s%s" % (label, core.fmt(value), (" " + unit) if unit else "")
        if key in filled:
            text += "  (FreeCAD's card has none: SciForge filled in a typical value)"
        lines.append(text)
    if core.strength(props, basis) is None:
        lines.append(
            "No %s strength: the safety factor cannot be shown for this body."
            % ("yield" if basis == "yield" else "ultimate tensile")
        )
    return "\n".join(lines)


class MaterialsPanel(_SimPanel):
    """Fusion's Study Materials (research 3.3): one row per body, the study material
    "(Same as Model)" by default (the body's own physical material) or another one for this
    study only, the safety factor's basis, and the properties the solve uses."""

    title = "Study Materials"
    icon = "sim_materials"
    last = None

    def __init__(self, doc, study):
        super().__init__(doc, "Study Materials")
        MaterialsPanel.last = self
        self.study = study
        self.form.setObjectName("SciForgeSimMaterials")
        sim = _sim()
        self.bodies = bodies.solid_bodies(doc)
        chosen = {b.Name for b in sim.study_bodies(study)}
        self.choices = _material_rows()
        self.table = QtWidgets.QTableWidget(len(self.bodies), 4)
        self.table.setObjectName("SciForgeSimMaterialsTable")
        self.table.setHorizontalHeaderLabels(
            ["Body", "In Study", "Model Material", "Study Material"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.combos = []
        self.ticks = []
        data = sim.study_data(study)
        for row, body in enumerate(self.bodies):
            item = QtWidgets.QTableWidgetItem(body.Label)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, item)
            tick = QtWidgets.QCheckBox()
            tick.setObjectName("SciForgeSimInStudy_%s" % body.Name)
            tick.setChecked(body.Name in chosen)
            tick.setToolTip("Untick to leave this body out of the study")
            tick.toggled.connect(lambda _on, r=row: self._row_changed(r))
            self.table.setCellWidget(row, 1, tick)
            self.ticks.append(tick)
            name, _props = sim.model_material(body)
            model = QtWidgets.QTableWidgetItem(name)
            model.setFlags(model.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 2, model)
            combo = QtWidgets.QComboBox()
            combo.setObjectName("SciForgeSimStudyMaterial_%s" % body.Name)
            combo.addItem(SAME, None)
            for label, key in self.choices:
                combo.addItem(label, key)
            key = data["materials"].get(body.Name)
            index = combo.findData(key) if key else 0
            combo.setCurrentIndex(max(index, 0))
            combo.currentIndexChanged.connect(lambda _i, r=row: self._row_changed(r))
            self.table.setCellWidget(row, 3, combo)
            self.combos.append(combo)
        self.table.resizeColumnsToContents()
        self.table.setMinimumHeight(60 + 28 * min(len(self.bodies), 6))
        self.table.currentCellChanged.connect(lambda r, *_a: self._show_props(r))
        self.table.cellDoubleClicked.connect(lambda r, *_a: self._show_props(r))
        self.layout.addRow(self.table)
        self.basis = QtWidgets.QComboBox()
        self.basis.setObjectName("SciForgeSimSafetyBasis")
        self.basis.addItem("Yield Strength", "yield")
        self.basis.addItem("Ultimate Tensile Strength", "ultimate")
        self.basis.setCurrentIndex(0 if data["settings"]["safety_basis"] == "yield" else 1)
        self.basis.setToolTip(
            "Yield strength / von Mises stress (Fusion's default), or ultimate tensile strength / "
            "1st principal stress"
        )
        self.basis.currentIndexChanged.connect(lambda *_a: self._show_props(self._row()))
        self.layout.addRow("Safety Factor", self.basis)
        self.props = QtWidgets.QLabel()
        self.props.setObjectName("SciForgeSimMaterialProps")
        self.props.setWordWrap(True)
        self.props.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.layout.addRow(self.props)
        self.layout.addRow(
            _note(
                "A study material is for this study only: the body's own material in the "
                "design does not change. " + score.LIMITS
            )
        )
        self.finish_layout()
        if self.bodies:
            self.table.selectRow(0)
            self._show_props(0)
        else:
            self.message.setText("The design has no solid body to simulate.")

    def _row(self):
        row = self.table.currentRow()
        return row if row >= 0 else 0

    def _key(self, row):
        return self.combos[row].currentData()

    def _row_changed(self, row):
        self.table.selectRow(row)
        self._show_props(row)

    def _show_props(self, row):
        try:
            if row is None or row < 0 or row >= len(self.bodies):
                return
            body = self.bodies[row]
            key = self._key(row)
            sim = _sim()
            if key:
                from . import material

                name, props = sim.card(material.material_of(material.entry(key)))
            else:
                name, props = sim.model_material(body)
            text = _props_text(name, props, self.basis.currentData())
            if not self.ticks[row].isChecked():
                text = "%s is left out of this study.\n" % body.Label + text
            self.props.setText(text)
        except Exception as exc:
            self.props.setText("")
            warn("study materials: %s" % exc)

    def apply(self):
        if not bodies.alive(self.study):
            return "The study is gone (undone or deleted)."
        ticked = [b for b, t in zip(self.bodies, self.ticks) if t.isChecked()]
        if self.bodies and not ticked:
            return "Keep at least one body in the study."
        sim = _sim()
        for body, combo in zip(self.bodies, self.combos):
            sim.set_study_material(self.study, body, combo.currentData())
        shown = {b.Name for b in bodies.solid_bodies(self.doc, visible_only=True)}
        names = {b.Name for b in ticked}
        current = list(getattr(self.study, "SimBodies", None) or [])
        if not current and names == shown:
            pass  # every body shown: the study keeps following the design (empty list)
        elif [b.Name for b in current] != [b.Name for b in ticked]:
            self.study.SimBodies = ticked
        sim.set_settings(self.study, {"safety_basis": self.basis.currentData()})
        log("study materials of %s changed" % self.study.Label)
        return None


def open_materials(study):
    from . import commands

    if not commands.finish_open_dialog() or _busy(study):
        return None
    return _show_panel(MaterialsPanel(study.Document, study))


# -- gravity ------------------------------------------------------------------------------------
def toggle_gravity(study):
    """Fusion's Toggle Gravity On / Off (gravity is off in a new study, research 3.5)."""
    from . import commands

    if not commands.finish_open_dialog() or _busy(study):
        return None
    sim = _sim()
    on = not sim.settings(study)["gravity"]["on"]
    _transaction(
        study.Document,
        "Gravity %s" % ("On" if on else "Off"),
        lambda: sim.set_settings(study, {"gravity": {"on": on}}),
    )
    commands.tell("Gravity %s for %s." % ("on" if on else "off", study.Label))
    _ui().refresh()
    return on


# -- contacts -----------------------------------------------------------------------------------
def contact_pairs(study, tolerance=None):
    """[(body, body, gap mm)] of the study's bodies that touch (within `tolerance`, the study's
    contact tolerance by default): Fusion makes them bonded contacts at solve time."""
    sim = _sim()
    if tolerance is None:
        tolerance = float(sim.settings(study)["contact_tolerance"])
    found = sim.study_bodies(study)
    shapes = []
    for body in found:
        try:
            shapes.append((body, bodies.global_shape(body, copy=False)))
        except Exception:
            continue
    pairs = []
    for i, (a, sa) in enumerate(shapes):
        box = sa.BoundBox
        box.enlarge(tolerance + 1e-6)
        for b, sb in shapes[i + 1 :]:
            if not box.intersect(sb.BoundBox):
                continue
            try:
                gap = sa.distToShape(sb)[0]
            except Exception:
                continue
            if gap <= tolerance + 1e-9:
                pairs.append((a, b, gap))
    return pairs


class ContactsPanel(_SimPanel):
    """Fusion's Automatic Contacts (research 3.6): the Contact Detection Tolerance and
    Generate, which lists the bodies close enough to be bonded."""

    title = "Automatic Contacts"
    icon = "sim_contacts"
    last = None

    def __init__(self, doc, study):
        super().__init__(doc, "Automatic Contacts")
        ContactsPanel.last = self
        self.study = study
        self.form.setObjectName("SciForgeSimContacts")
        settings = _sim().settings(study)
        self.tolerance = QtWidgets.QDoubleSpinBox()
        self.tolerance.setObjectName("SciForgeSimContactsTolerance")
        self.tolerance.setRange(0.0, 10.0)
        self.tolerance.setDecimals(3)
        self.tolerance.setSingleStep(0.05)
        self.tolerance.setSuffix(" mm")
        self.tolerance.setValue(float(settings["contact_tolerance"]))
        self.layout.addRow("Contact Detection Tolerance", self.tolerance)
        kind = QtWidgets.QComboBox()
        kind.setObjectName("SciForgeSimContactsType")
        kind.addItem("Bonded")
        kind.setEnabled(False)
        kind.setToolTip(
            "Bodies that touch are bonded (glued); the other types are not in " "SciForge yet"
        )
        self.layout.addRow("Contact Type", kind)
        self.generate = QtWidgets.QPushButton("Generate")
        self.generate.setObjectName("SciForgeSimContactsGenerate")
        self.generate.clicked.connect(self._generate)
        self.layout.addRow(self.generate)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setObjectName("SciForgeSimContactsTable")
        self.table.setHorizontalHeaderLabels(["Body 1", "Body 2", "Gap"])
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(120)
        self.layout.addRow(self.table)
        self.layout.addRow(
            _note(
                "Bodies closer than the tolerance are bonded (glued together) when the study "
                "solves; bodies farther apart are not joined."
            )
        )
        self.finish_layout()
        self.pairs = []

    def _generate(self):
        try:
            self.pairs = contact_pairs(self.study, float(self.tolerance.value()))
            self.table.setRowCount(len(self.pairs))
            for row, (a, b, gap) in enumerate(self.pairs):
                for col, text in enumerate((a.Label, b.Label, "%s mm" % core.fmt(gap, 3))):
                    item = QtWidgets.QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(row, col, item)
            self.message.setStyleSheet(NOTE_STYLE)
            self.message.setText(
                "%d bonded contact%s." % (len(self.pairs), "" if len(self.pairs) == 1 else "s")
                if self.pairs
                else "No bodies touch within this tolerance."
            )
        except Exception as exc:
            warn("automatic contacts: %s" % exc)

    def apply(self):
        if not bodies.alive(self.study):
            return "The study is gone (undone or deleted)."
        _sim().set_settings(self.study, {"contact_tolerance": float(self.tolerance.value())})
        return None


def open_contacts(study):
    from . import commands

    if not commands.finish_open_dialog() or _busy(study):
        return None
    return _show_panel(ContactsPanel(study.Document, study))


class _TableDialog(FocusBack, QtWidgets.QDialog):
    pass


def _table_dialog(name, title, headers, rows, note=""):
    dialog = _TableDialog(Gui.getMainWindow())
    dialog.setObjectName(name)
    dialog.setWindowTitle(title)
    layout = QtWidgets.QVBoxLayout(dialog)
    table = QtWidgets.QTableWidget(len(rows), len(headers))
    table.setObjectName(name + "Table")
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, QtWidgets.QTableWidgetItem(str(text)))
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table)
    if note:
        layout.addWidget(_note(note))
    close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.resize(560, 300)
    dialog.show()
    return _keep(dialog)


def open_contact_manager(study):
    """Fusion's Contact Manager (research 3.6), read only: the bonded pairs by bodies."""
    rows = [
        (a.Label, b.Label, "Bonded (automatic)", "%s mm" % core.fmt(gap, 3))
        for a, b, gap in contact_pairs(study)
    ]
    return _table_dialog(
        "SciForgeSimContactManager",
        "Contact Manager",
        ["Body 1", "Body 2", "Type", "Gap"],
        rows,
        "Bodies that touch are bonded when the study solves. Separation, sliding and the "
        "other contact types are not in SciForge yet."
        + ("" if rows else " No bodies of this study touch."),
    )


# -- Load Case Attributes ------------------------------------------------------------------------
def _where(item):
    sim = _sim()
    counts = {}
    for obj, sub in sim._picks(item.References):
        name = sub.split(".")[-1]
        kind = (
            "face" if name.startswith("Face") else ("edge" if name.startswith("Edge") else "corner")
        )
        key = (obj.Label, kind)
        counts[key] = counts.get(key, 0) + 1
    parts = []
    for (label, kind), n in counts.items():
        parts.append("%s: %d %s%s" % (label, n, kind, "" if n == 1 else "s"))
    return "; ".join(parts) or "nothing"


def _direction_text(data):
    opts = core.options(data["category"], data["kind"], data["options"])
    if data["category"] != "load":
        return ""
    if opts.get("direction") == "normal":
        return "Normal to the faces" + (" (flipped)" if opts.get("flip") else "")
    vector = opts.get("vector")
    if vector:
        try:
            v = core.unit_vector(vector)
            if opts.get("flip"):
                v = [-c for c in v]
            return "(%s)" % ", ".join(core.fmt(c, 3) for c in v)
        except Exception:
            return ""
    return "Into the faces" if not opts.get("flip") else "Out of the faces"


def attribute_rows(study):
    """[(name, type, location, size, direction, status)] of every constraint and load."""
    sim = _sim()
    lost = {i.Name for i in sim.lost_items(study)}
    rows = []
    for item in sim.items(study):
        data = sim.item_data(item)
        if data["category"] not in ("constraint", "load"):
            continue  # (local mesh controls are not in the load case)
        try:
            info = core.kind_info(data["category"], data["kind"])
            title = info["title"]
            size = core.describe(data["category"], data["kind"], data["options"])
        except Exception:
            title, size = data["kind"], ""
        status = (
            "Suppressed" if item.Suppressed else ("Lost its faces" if item.Name in lost else "OK")
        )
        rows.append(
            (
                item.Label,
                title,
                _where(item),
                size if data["category"] == "load" else size.replace(title, "").strip(" ()") or "-",
                _direction_text(data),
                status,
            )
        )
    gravity = sim.settings(study)["gravity"]
    if gravity.get("on"):
        rows.append(
            (
                "Gravity",
                "Gravity",
                "Every body",
                "%s m/s^2" % core.fmt(gravity["g"] / 1000.0),
                "(%s)" % ", ".join(core.fmt(c, 3) for c in gravity["direction"]),
                "OK",
            )
        )
    return rows


def open_attributes(study):
    """Fusion's Load Case Attributes (research 3.11): every load and constraint with where
    it is, its size, its direction and whether it is placed correctly."""
    return _table_dialog(
        "SciForgeSimAttributes",
        "Load Case Attributes: %s" % study.Label,
        ["Name", "Type", "Location", "Magnitude", "Direction", "Status"],
        attribute_rows(study),
    )


# -- Pre-check ----------------------------------------------------------------------------------
class PrecheckDialog(FocusBack, QtWidgets.QDialog):
    """Fusion's Pre-check list (research 3.9): the traffic light and what may be missing."""

    def __init__(self, study):
        super().__init__(Gui.getMainWindow())
        self.study = study
        self.setObjectName("SciForgeSimPrecheck")
        self.setWindowTitle("Pre-check: %s" % study.Label)
        layout = QtWidgets.QVBoxLayout(self)
        state, checks = _ui().precheck_state(study)
        self.state = state
        self.checks = checks
        head = QtWidgets.QHBoxLayout()
        picture = QtWidgets.QLabel()
        picture.setPixmap(ui_icon(score.light_icon(state)).pixmap(32, 32))
        head.addWidget(picture)
        title = QtWidgets.QLabel(score.light_text(state))
        title.setObjectName("SciForgeSimPrecheckTitle")
        title.setStyleSheet("font-weight: bold;")
        head.addWidget(title, 1)
        layout.addLayout(head)
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("SciForgeSimPrecheckList")
        for level, text in checks:
            item = QtWidgets.QListWidgetItem(
                ui_icon("sim_precheck_error" if level == "error" else "sim_precheck_warn"), text
            )
            item.setToolTip(text)
            self.list.addItem(item)
        self.list.setWordWrap(True)
        if not checks:
            self.list.addItem("Nothing is missing.")
        layout.addWidget(self.list)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.solve = QtWidgets.QPushButton("Solve")
        self.solve.setObjectName("SciForgeSimPrecheckSolve")
        self.solve.setEnabled(state != "red")
        self.solve.clicked.connect(self._solve)
        close = QtWidgets.QPushButton("Close")
        close.setObjectName("SciForgeSimPrecheckClose")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.solve)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.resize(520, 260)

    def _solve(self):
        try:
            self.accept()
            from . import simulation_solve_dialog

            simulation_solve_dialog.open_solve()
        except Exception as exc:
            warn("pre-check: %s" % exc)


def open_precheck(study):
    dialog = PrecheckDialog(study)
    dialog.show()
    log("pre-check of %s: %s" % (study.Label, dialog.state))
    return _keep(dialog)


# -- DOF View -----------------------------------------------------------------------------------
def free_bodies(study):
    """Bodies of the study that nothing holds: no constraint on them, and not touching a held
    body (through other bodies) (Fusion's DOF View shows these, research 3.8)."""
    return list(_sim().loose_bodies(study))


def dof_view(study):
    """Selects the bodies that could still move and says which they are."""
    from . import commands

    free = free_bodies(study)
    try:
        Gui.Selection.clearSelection()
        for body in free:
            Gui.Selection.addSelection(body.Document.Name, body.Name)
    except Exception:
        pass
    if free:
        commands.tell(
            "Not held yet (selected): %s. Add a constraint on them or let them touch a held "
            "body." % ", ".join(b.Label for b in free)
        )
    else:
        commands.tell("Every body of %s is held." % study.Label)
    return free

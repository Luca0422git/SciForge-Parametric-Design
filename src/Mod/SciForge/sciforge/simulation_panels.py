# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SETUP dialogs that pick on the model: Fusion's Structural Constraints and Structural
Loads (one dialog each, a Type drop-down, research 3.4 and 3.5), Edit Gravity, and Local Mesh
Control when the engine has it.

Picking works like in every SciForge command (pickpanel.PickPanel): a click on a face, edge or
corner of a body of the study adds it, a click on a picked one drops it, and only what the
chosen type can take lights up under the mouse (Pin: round faces; Frictionless and Pressure:
faces; Fixed and Force: faces, edges and corners). The glyphs of what the dialog would make are
drawn while picking (simulation_glyphs.preview). Types Fusion has that SciForge cannot solve
yet are listed greyed, with the reason. OK keeps the constraint or load as one undo step,
Cancel / Esc leave nothing, Ctrl+Z cancels the dialog.
"""

import FreeCADGui as Gui

from . import bodies, commands, hole_common, log, pickpanel, warn
from . import simulation_core as core
from . import simulation_setup_core as score
from .compat import QtCore, QtWidgets

ERROR_STYLE = "color: #ff8a80;"
HINT_STYLE = "color: #b8c4d0;"


def _sim():
    from . import simulation

    return simulation


def _ui():
    from . import simulation_ui

    return simulation_ui


def _glyphs():
    from . import simulation_glyphs

    return simulation_glyphs


class _Gate:
    """FreeCAD names the top object and a path ("Body.Pad.Face6"): the panel is asked about
    the element itself."""

    def __init__(self, panel):
        self.panel = panel

    def allow(self, doc, obj, sub):
        try:
            panel = self.panel
            if panel is None or panel._closed or obj is None:
                return True
            from .construct_ui import _resolve_gate

            leaf, short = _resolve_gate(obj, sub)
            return bool(panel.allow(leaf, short))
        except Exception:
            return False


def element_kind(short):
    name = (short or "").split(".")[-1]
    for prefix, kind in (("Face", "faces"), ("Edge", "edges"), ("Vertex", "vertices")):
        if name.startswith(prefix):
            return kind
    return None


def surface_kind(obj, short):
    """ "plane" / "cylinder" / ... of a face (None when it is not one)."""
    try:
        face = obj.Shape.getElement(short)
        return face.Surface.TypeId.split("::")[-1].lower().replace("geom", "")
    except Exception:
        return None


def body_pick(obj, short):
    """(body, element name of the body's own shape) for what was clicked on `obj` (a step of
    the body, usually its Tip), or None."""
    body = bodies.body_of(obj)
    if body is None or not short:
        return None
    tip = getattr(body, "Tip", None)
    if obj is body or obj is tip:
        return body, short
    try:
        item = obj.Shape.getElement(short)
        shape = body.Shape
    except Exception:
        return None
    kind = element_kind(short)
    if kind == "faces":
        name = pickpanel.match_face(tip, obj, short) if tip is not None else None
        return (body, name) if name else None
    elements = shape.Edges if kind == "edges" else shape.Vertexes
    prefix = "Edge" if kind == "edges" else "Vertex"
    for i, other in enumerate(elements, 1):
        try:
            if other.isSame(item):
                return body, "%s%d" % (prefix, i)
            if kind == "vertices" and (other.Point - item.Point).Length < 1e-6:
                return body, "%s%d" % (prefix, i)
            if kind == "edges" and abs(other.Length - item.Length) < 1e-6:
                if (other.CenterOfMass - item.CenterOfMass).Length < 1e-6:
                    return body, "%s%d" % (prefix, i)
        except Exception:
            continue
    return None


def _pick_normal(picks):
    """The outward normal (x, y, z) at the middle of the first picked face, or None."""
    for obj, sub in picks:
        if not sub or not sub.startswith("Face"):
            continue
        try:
            face = bodies.global_shape(obj, copy=False).getElement(sub)
            u0, u1, v0, v1 = face.ParameterRange
            n = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            return [n.x, n.y, n.z]
        except Exception:
            continue
    return None


def doc_units(doc):
    """{family: unit} the design's value fields show: Fusion's Simulation follows the
    document's units (N, MPa, mm in a metric design; lbf, psi, in in an inch design)."""
    try:
        from . import browser_ui

        return score.unit_set(browser_ui.units(doc))
    except Exception:
        return score.unit_set("mm")


def _digits(family, shown):
    """Significant figures a field shows: 6 in the engine's own unit, 4 once converted (22.48
    lbf, 0.126 in); the exact value is kept while the text is not changed (_value)."""
    return 6 if score.unit_factor(family, shown) == 1.0 else 4


def _number_field(name, value, family, tip="", shown=None):
    """A value field: `value` in the engine's unit, shown in `shown` (a unit typed with the
    number wins; a bare number is in the unit shown)."""
    field = QtWidgets.QLineEdit()
    field.setObjectName("SciForgeSim_" + name)
    field.setProperty("family", family)
    field.setProperty("shown", shown or "")
    _put(field, value)
    if tip:
        field.setToolTip(tip)
    return field


def _value(field):
    """A field's value in the engine's unit (SimulationError with a sentence when it is not).
    A text left as it was shown gives back the exact value (an OK without a change changes
    nothing, even when the field rounds a converted unit)."""
    exact = field.property("exact")
    if exact is not None and field.text() == field.property("exact_text"):
        return float(exact)
    return score.parse_quantity(
        field.text(), field.property("family") or "number", shown=field.property("shown") or None
    )


def _put(field, value, digits=None):
    """Show `value` (the engine's unit) in a field, in the unit the field shows."""
    family = field.property("family") or "number"
    shown = field.property("shown") or None
    text = score.format_quantity(
        value, family, digits if digits is not None else _digits(family, shown), shown
    )
    field.setText(text)
    try:
        field.setProperty("exact", float(value))
        field.setProperty("exact_text", text)
    except (TypeError, ValueError):
        field.setProperty("exact", None)


# An on / off button must look on when it is on (the theme draws push buttons alike either
# way): blue with white text, like Fusion's toggles. Written with the dark look's colours (the
# theme's style sheet hook swaps them in the light look).
TOGGLE_STYLE = (
    "QPushButton:checked { background: #2f7fd1; color: white; border: 1px solid #3fa9f5; }"
)


def _toggle(name, text, on, tip=""):
    button = QtWidgets.QPushButton(text)
    button.setObjectName("SciForgeSim_" + name)
    button.setCheckable(True)
    button.setChecked(bool(on))
    button.setStyleSheet(TOGGLE_STYLE)
    if tip:
        button.setToolTip(tip)
    return button


# Types Fusion lists that SciForge does not build (research 9.2): shown greyed in the Type list.
LATER = {
    "constraint": (
        (
            "Remote",
            "remote",
            "Not in SciForge yet: hold the faces themselves (Fixed, Pin or Frictionless).",
        ),
    ),
    "load": (
        (
            "Remote Moment",
            "remote_moment",
            "Not in SciForge yet: a Moment on the faces, or a Remote Force at a point.",
        ),
        (
            "Hydrostatic Pressure",
            "hydrostatic",
            "Not in SciForge yet: a Pressure is the same everywhere on its faces.",
        ),
    ),
}

TITLES = {
    "constraint": "Structural Constraints",
    "load": "Structural Loads",
    "mesh": "Local Mesh Control",
}
ICONS = {"constraint": "sim_constraints", "load": "sim_loads", "mesh": "sim_local_mesh"}


def _table(category):
    tables = getattr(core, "TABLES", None) or {"constraint": core.CONSTRAINTS, "load": core.LOADS}
    return tables[category]


def _global_size(study):
    """The study's average element size (mm), as its next mesh will use it."""
    try:
        sim = _sim()
        box = None
        for body in sim.study_bodies(study):
            b = bodies.global_shape(body, copy=False).BoundBox
            if box is None:
                box = b
            else:
                box.add(b)
        if box is None:
            return 1.0
        mesh = sim.settings(study)["mesh"]
        bbox = (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)
        try:
            return core.element_size(bbox, mesh["size_pct"], mesh.get("size_mm", 0.0))
        except TypeError:
            return core.element_size(bbox, mesh["size_pct"])
    except Exception:
        return 1.0


TOGGLE_TEXT = {
    "x": ("Ux", "Hold the movement along X"),
    "y": ("Uy", "Hold the movement along Y"),
    "z": ("Uz", "Hold the movement along Z"),
    "radial": ("Radial", "The hole keeps its size and place across the axis"),
    "axial": ("Axial", "No sliding along the axis"),
    "tangential": ("Tangential", "No turning about the axis (off: the part may turn)"),
}
KIND_NOTES = {
    "frictionless": "The faces cannot move through themselves; they may slide along them (a "
    "support without friction, a symmetry plane).",
    "pin": "Round faces only. Fusion's default holds Radial and Axial and lets the part turn "
    "(Tangential off).",
    "fixed": "Faces, edges or corners. Untick directions to let it slide that way (a roller).",
    "displacement": "Moves the picks by the given lengths (a direction left off is free).",
    "force": "On several faces the force is shared by their area, unless Force Per Entity.",
    "pressure": "Always at right angles to the faces; positive pushes into them.",
    "moment": "Turns the picked faces about the axis (right-hand rule).",
    "bearing": "Pushes on the round face like a shaft in a hole, only on the side it presses.",
    "remote_force": "A force acting at a point away from the model, carried to the faces.",
    "local": "Smaller (or larger) elements on the picked faces, edges or bodies, blending into "
    "the study's size. The mesh is made again by Generate Mesh or the next solve.",
}


class ItemPanel(pickpanel.PickPanel):
    """Fusion's Structural Constraints / Structural Loads dialog (and Edit of one)."""

    simulation_dialog = True
    last = None

    def __init__(self, doc, study, category, item=None, kind=None, initial=()):
        self.title = TITLES.get(category, "Structural Loads")
        self.icon = ICONS.get(category, "sim_loads")
        transaction = ("Edit %s" % item.Label) if item is not None else self.title
        super().__init__(doc, transaction)
        ItemPanel.last = self
        sim = _sim()
        self.study = study
        self.category = category
        self.item = item
        self.editing = item is not None
        self.made = None
        table = _table(category)
        self.whole = False  # Local Mesh Control's Body Selection: a click picks the body
        if item is not None:
            data = sim.item_data(item)
            self.kind = data["kind"]
            self.opts = core.options(category, self.kind, data["options"])
            self.picks = [(o, s) for o, s in sim._picks(item.References)]
            self.whole = any(not sub for _o, sub in self.picks)
        else:
            built = [k for k, info in table.items() if info.get("built")]
            self.kind = kind if kind in table and table[kind].get("built") else built[0]
            self.opts = core.options(category, self.kind)
            if category == "mesh":
                self.opts["size"] = round(_global_size(study), 3)
            self.picks = []
        self.study_names = {b.Name for b in sim.study_bodies(study)}
        self.units = doc_units(doc)
        self.form.setObjectName("SciForgeSimItemPanel")
        rows = []
        for key, info in table.items():
            tip = "" if info.get("built") else "%s is not in SciForge yet." % info["title"]
            rows.append((info["title"], key, bool(info.get("built")), tip))
        for title, key, tip in LATER.get(category, ()):
            if key not in table:  # Fusion lists them; greyed, with the reason (research 9.2)
                rows.append((title, key, False, tip))
        self.type_box = pickpanel.combo(rows, self.kind)
        self.type_box.setObjectName("SciForgeSimItemType")
        self.type_box.setEnabled(not self.editing)
        if self.editing:
            self.type_box.setToolTip(
                "The type of an existing one stays; delete it and make a new one"
            )
        self.type_box.currentIndexChanged.connect(self._type_changed)
        self.layout.addRow("Type", self.type_box)
        self.select = hole_common.SelectionField(self, 0, "Select")
        self.select.button.setObjectName("SciForgeSimItemSelect")
        self.select.clear.setObjectName("SciForgeSimItemClear")
        self.layout.addRow("Targets", self.select.widget)
        if "bodies" in self.info()["targets"]:
            self.body_mode = QtWidgets.QPushButton("Body Selection")
            self.body_mode.setObjectName("SciForgeSim_body_selection")
            self.body_mode.setCheckable(True)
            self.body_mode.setChecked(self.whole)
            self.body_mode.setStyleSheet(TOGGLE_STYLE)
            self.body_mode.setToolTip("On: a click picks a whole body; off: faces and edges")
            self.body_mode.toggled.connect(self._body_mode)
            self.layout.addRow(self.body_mode)
        self.options_box = QtWidgets.QWidget()
        self.options_layout = QtWidgets.QFormLayout(self.options_box)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addRow(self.options_box)
        self.fields = {}
        self.finish_layout()
        self._build_options()
        self.start_picking()
        self.select.set_active(True)
        for obj, short, _point in initial or ():
            if self.allow(obj, short):
                found = body_pick(obj, short)
                if found is not None and found not in self.picks:
                    self.picks.append(found)
        self._sync()
        self._update_text()
        self.schedule()

    # -- picking -------------------------------------------------------------------------------
    def start_picking(self):
        super().start_picking()
        try:
            if self.gate is not None:
                hole_common.remove_gate(self.gate)
            self.gate = _Gate(self)
            Gui.Selection.addSelectionGate(self.gate)
        except Exception as exc:
            warn("%s: selection filter unavailable: %s" % (self.title, exc))

    def info(self):
        return core.kind_info(self.category, self.kind)

    def allow(self, obj, short):
        if obj is None or not short:
            return False
        body = bodies.body_of(obj)
        if body is None or body.Name not in self.study_names:
            return False
        if self.whole:
            return True  # Body Selection: any element stands for its body
        kind = element_kind(short)
        info = self.info()
        if kind is None or kind not in info["targets"]:
            return False
        if kind == "faces" and info.get("faces") in ("round", "flat"):
            want = "cylinder" if info["faces"] == "round" else "plane"
            if surface_kind(obj, short) != want:
                return False
        return True

    def _pick_of(self, obj, short):
        if self.whole:
            body = bodies.body_of(obj)
            return (body, "") if body is not None else None
        return body_pick(obj, short)

    def _body_mode(self, on):
        try:
            self.whole = bool(on)
            self.picks = [p for p in self.picks if bool(p[1]) != self.whole]
            self._sync()
            self._update_text()
            self.schedule()
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))

    def picks_changed(self, added, dropped):
        changed = False
        for obj, short, _point in dropped:
            if self.whole and short:
                continue  # (a face's selection put back by the sync: not the body's pick)
            found = self._pick_of(obj, short)
            if found is not None and found in self.picks:
                self.picks.remove(found)
                changed = True
        for obj, short, _point in added:
            if not self.allow(obj, short):
                continue
            found = self._pick_of(obj, short)
            if found is None:
                continue
            if found in self.picks:
                self.picks.remove(found)
            else:
                self.picks.append(found)
            changed = True
        if changed:
            self._update_text()
        return changed

    def shown(self):
        grouped = {}
        order = []
        for body, sub in self.picks:
            if not bodies.alive(body):
                continue
            if not sub:
                grouped[body.Name] = (body, [])
                order.append(body.Name)
                continue
            target = getattr(body, "Tip", None) or body
            if target.Name not in grouped:
                grouped[target.Name] = (target, [])
                order.append(target.Name)
            grouped[target.Name][1].append(sub)
        return [grouped[n] for n in order]

    def activate(self, _index):
        self.select.set_active(True)

    def clear_field(self, _index):
        try:
            self.picks = []
            self._sync()
            self._update_text()
            self.schedule()
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))

    def _update_text(self):
        counts = {}
        for _body, sub in self.picks:
            kind = element_kind(sub) or ("bodies" if not sub else "faces")
            counts[kind] = counts.get(kind, 0) + 1
        if not counts:
            self.select.set_text(None)
        else:
            words = {"faces": "face", "edges": "edge", "vertices": "corner", "bodies": "body"}
            self.select.set_text(
                ", ".join(
                    "%d %s%s" % (n, words[k], "" if n == 1 else "s") for k, n in counts.items()
                )
            )
        per = self.fields.get("per_entity")
        if per is not None:
            per.setEnabled(len(self.picks) > 1)

    # -- the type and its options --------------------------------------------------------------
    def _type_changed(self, *_a):
        try:
            key = self.type_box.currentData()
            info = core.kind_info(self.category, key)
            if not info.get("built"):
                return
            self.kind = key
            self.opts = core.options(self.category, key)
            # picks the new type cannot take are dropped (Fusion keeps what still fits)
            keep = []
            for body, sub in self.picks:
                tip = getattr(body, "Tip", None) or body
                if self.allow(tip, sub):
                    keep.append((body, sub))
            self.picks = keep
            self._build_options()
            self._sync()
            self._update_text()
            self.schedule()
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))

    def _clear_options(self):
        while self.options_layout.count():
            child = self.options_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.fields = {}
        self.rows = {}

    def _build_options(self):
        self._clear_options()
        opts = self.opts
        kind = self.kind
        form = self.options_layout
        unit_family = {"pressure": "pressure", "moment": "moment"}.get(kind, "force")
        if self.category == "constraint":
            toggles = [k for k in ("x", "y", "z", "radial", "axial", "tangential") if k in opts]
            if kind == "displacement":
                for axis in ("x", "y", "z"):
                    value = opts.get(axis)
                    tick = QtWidgets.QCheckBox("U%s" % axis)
                    tick.setObjectName("SciForgeSim_%s_on" % axis)
                    tick.setChecked(value is not None)
                    field = _number_field(
                        axis, value or 0.0, "length", shown=self.units.get("length")
                    )
                    field.setEnabled(value is not None)
                    tick.toggled.connect(lambda on, f=field: (f.setEnabled(on), self.schedule()))
                    field.editingFinished.connect(self._value_typed)
                    row = QtWidgets.QHBoxLayout()
                    row.addWidget(tick)
                    row.addWidget(field, 1)
                    holder = QtWidgets.QWidget()
                    holder.setLayout(row)
                    form.addRow(holder)
                    self.fields[axis] = (tick, field)
            elif toggles:
                holder = QtWidgets.QWidget()
                row = QtWidgets.QHBoxLayout(holder)
                row.setContentsMargins(0, 0, 0, 0)
                for key in toggles:
                    text, tip = TOGGLE_TEXT.get(key, (key.title(), ""))
                    button = _toggle(key, text, opts.get(key), tip)
                    button.toggled.connect(lambda _on: self.schedule())
                    row.addWidget(button)
                    self.fields[key] = button
                form.addRow("Directions" if kind == "fixed" else "Hold", holder)
        elif self.category == "mesh":
            size = float(opts.get("size", 1.0))
            self.global_size = max(_global_size(self.study), 0.05)
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setObjectName("SciForgeSim_size_slider")
            slider.setRange(1, 20)
            slider.setValue(max(1, min(20, int(round(20.0 * size / self.global_size)))))
            slider.setToolTip("Fine (left) to Coarse (right): the share of the study's size")
            field = _number_field(
                "size", size, "length", "The element size on the picks", self.units.get("length")
            )
            slider.valueChanged.connect(lambda v, f=field: self._slider_moved(v, f))
            field.editingFinished.connect(self._value_typed)
            holder = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QtWidgets.QLabel("Fine"))
            row.addWidget(slider, 1)
            row.addWidget(QtWidgets.QLabel("Coarse"))
            form.addRow(holder)
            form.addRow("Length", field)
            self.fields["size"] = field
            self.fields["size_slider"] = slider
        else:
            if "direction" in opts:
                box = QtWidgets.QComboBox()
                box.setObjectName("SciForgeSim_direction")
                box.addItem("Normal", "normal")
                box.addItem("Vector", "vector")
                box.setCurrentIndex(0 if opts.get("direction") == "normal" else 1)
                box.currentIndexChanged.connect(self._direction_changed)
                form.addRow("Direction Type", box)
                self.fields["direction"] = box
            self.rows = {}  # field key -> its row (shown or hidden with the direction type)
            if "magnitude" in opts:
                field = _number_field(
                    "magnitude",
                    opts.get("magnitude", 0.0),
                    unit_family,
                    "The size of the load",
                    self.units.get(unit_family),
                )
                field.editingFinished.connect(self._value_typed)
                self._row(form, "magnitude", "Magnitude", field)
            if kind == "force" and "direction" in opts:
                # Fusion's Vector direction for a force: its X, Y and Z parts (N)
                parts = score.components_of(opts.get("magnitude", 100.0), opts.get("vector"))
                for axis, value in zip(("fx", "fy", "fz"), parts):
                    field = _number_field(
                        axis,
                        value,
                        "force",
                        "The force along %s" % axis[1].upper(),
                        self.units.get("force"),
                    )
                    field.editingFinished.connect(self._value_typed)
                    self._row(form, axis, "F%s" % axis[1], field)
            elif "vector" in opts:
                vector = opts.get("vector") or [0.0, 0.0, -1.0]
                for axis, value in zip(("x", "y", "z"), vector):
                    field = _number_field("v" + axis, value, "number")
                    field.editingFinished.connect(self._value_typed)
                    self._row(
                        form,
                        "v" + axis,
                        ("Axis %s" if kind == "moment" else "Direction %s") % axis.upper(),
                        field,
                    )
            self._show_direction_rows()
            if "point" in opts:
                for axis, value in zip(("x", "y", "z"), opts.get("point") or [0, 0, 0]):
                    field = _number_field(
                        "p" + axis, value, "length", shown=self.units.get("length")
                    )
                    field.editingFinished.connect(self._value_typed)
                    form.addRow("Point %s" % axis.upper(), field)
                    self.fields["p" + axis] = field
            if "flip" in opts:
                flip = _toggle(
                    "flip", "Flip Direction", opts.get("flip"), "Turn the load the other way round"
                )
                flip.toggled.connect(lambda _on: self.schedule())
                form.addRow(flip)
                self.fields["flip"] = flip
            if "per_entity" in opts:
                what = "Force" if kind == "force" else self.info()["title"]
                per = QtWidgets.QCheckBox("%s Per Entity" % what)
                per.setObjectName("SciForgeSim_per_entity")
                per.setChecked(bool(opts.get("per_entity")))
                per.setToolTip(
                    "Off: the value is shared by the picks (by face area or edge length). On: "
                    "every pick gets the whole value (3 faces at 100 N make 300 N)."
                )
                per.toggled.connect(lambda _on: self.schedule())
                form.addRow(per)
                self.fields["per_entity"] = per
        note = KIND_NOTES.get(kind)
        if note:
            label = QtWidgets.QLabel(note)
            label.setWordWrap(True)
            label.setStyleSheet(HINT_STYLE)
            form.addRow(label)
        self._update_text()

    def _slider_moved(self, value, field):
        try:
            size = self.global_size * value / 20.0
            _put(field, size, 4)
            self.schedule()
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))

    def _row(self, form, key, text, field):
        """A row of a label and a field that can be hidden as a whole."""
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel(text)
        label.setMinimumWidth(70)
        row.addWidget(label)
        row.addWidget(field, 1)
        form.addRow(holder)
        self.fields[key] = field
        self.rows[key] = holder

    def _vector_mode(self):
        box = self.fields.get("direction")
        if box is None:
            return "vector" if "vector" in self.opts else None
        return box.currentData()

    def _show_direction_rows(self):
        mode = self._vector_mode()
        components = all(k in self.rows for k in ("fx", "fy", "fz"))
        for key, holder in getattr(self, "rows", {}).items():
            if key == "magnitude":
                holder.setVisible(not (components and mode == "vector"))
            elif key in ("fx", "fy", "fz"):
                holder.setVisible(mode == "vector")
            elif key in ("vx", "vy", "vz"):
                holder.setVisible(mode != "normal")

    def _direction_changed(self, *_a):
        """Normal / Vector: the rows of the other one show, the values carried over (a force
        typed as a size becomes its X, Y, Z parts along the direction, and back)."""
        try:
            mode = self._vector_mode()
            if all(k in self.fields for k in ("fx", "fy", "fz", "magnitude")):
                if mode == "vector":
                    size = _value(self.fields["magnitude"])
                    vector = self.opts.get("vector") or [0.0, 0.0, -1.0]
                    if self.picks and self.opts.get("direction") == "normal":
                        normal = _pick_normal(self.picks)
                        if normal is not None:
                            vector = [-c for c in normal]
                    for key, value in zip(("fx", "fy", "fz"), score.components_of(size, vector)):
                        _put(self.fields[key], value)
                else:
                    parts = [_value(self.fields[k]) for k in ("fx", "fy", "fz")]
                    try:
                        size, _unit = score.force_from_components(*parts)
                        _put(self.fields["magnitude"], size)
                    except core.SimulationError:
                        pass
            self.opts["direction"] = mode
            self._show_direction_rows()
            self.schedule()
        except core.SimulationError as exc:
            self.say(str(exc), error=True)
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))

    def _value_typed(self):
        """A value was typed (Enter or Tab): the preview follows."""
        self.schedule()

    def read_options(self, lenient=False):
        """(options, sentence or None) from the fields."""
        opts = dict(self.opts)
        try:
            for key in ("x", "y", "z", "radial", "axial", "tangential"):
                widget = self.fields.get(key)
                if isinstance(widget, QtWidgets.QPushButton):
                    opts[key] = bool(widget.isChecked())
            if self.kind == "displacement":
                for axis in ("x", "y", "z"):
                    tick, field = self.fields[axis]
                    opts[axis] = _value(field) if tick.isChecked() else None
            box = self.fields.get("direction")
            if box is not None:
                opts["direction"] = box.currentData()
            components = all(k in self.fields for k in ("fx", "fy", "fz"))
            if components and opts.get("direction") == "vector":
                parts = [_value(self.fields[k]) for k in ("fx", "fy", "fz")]
                opts["magnitude"], opts["vector"] = score.force_from_components(*parts)
            elif "magnitude" in self.fields:
                opts["magnitude"] = _value(self.fields["magnitude"])
            if all(("v" + a) in self.fields for a in "xyz") and opts.get("direction") != "normal":
                opts["vector"] = [_value(self.fields["v" + a]) for a in "xyz"]
            if all(("p" + a) in self.fields for a in "xyz"):
                opts["point"] = [_value(self.fields["p" + a]) for a in "xyz"]
            if "flip" in self.fields:
                opts["flip"] = bool(self.fields["flip"].isChecked())
            if "per_entity" in self.fields:
                opts["per_entity"] = bool(self.fields["per_entity"].isChecked())
            if "size" in self.fields:
                opts["size"] = _value(self.fields["size"])
        except core.SimulationError as exc:
            if lenient:
                return opts, str(exc)
            return opts, str(exc)
        return core.options(self.category, self.kind, opts), None

    # -- preview and checks --------------------------------------------------------------------
    def _preview(self):
        opts, problem = self.read_options(lenient=True)
        count = _glyphs().preview(self.doc, self.category, self.kind, opts, self.picks)
        if problem:
            self.say(problem, error=True)
            return
        problems = (
            core.check(self.category, self.kind, opts, _sim().describe_picks(self.picks))
            if self.picks
            else []
        )
        if problems:
            self.say(" ".join(problems), error=True)
        elif not self.picks:
            words = " / ".join(
                {"faces": "faces", "edges": "edges", "vertices": "corners", "bodies": "bodies"}[t]
                for t in self.info()["targets"]
            )
            self.say("Click the %s to put the %s on." % (words, self.info()["title"]))
        else:
            self.say("")
        return count

    def say(self, text, error=False):
        try:
            self.message.setStyleSheet(ERROR_STYLE if error else HINT_STYLE)
            self.message.setText(text)
        except RuntimeError:
            pass

    def feature(self):
        return None

    # -- OK / Cancel ---------------------------------------------------------------------------
    def accept(self):
        if self._closed:
            return True
        try:
            if not bodies.alive(self.study):
                self.say("The study is gone (undone or deleted).", error=True)
                return False
            opts, problem = self.read_options()
            if problem:
                self.say(problem, error=True)
                return False
            sim = _sim()
            problems = core.check(self.category, self.kind, opts, sim.describe_picks(self.picks))
            if problems:
                self.say(" ".join(problems), error=True)
                return False
            if self.editing:
                if not bodies.alive(self.item):
                    self.say("It is gone (undone or deleted).", error=True)
                    return False
                sim.update_item(self.item, refs=list(self.picks), opts=opts)
                self.made = self.item
            else:
                self.made = sim.add_item(
                    self.study, self.category, self.kind, list(self.picks), opts
                )
            _keep_whole_bodies(self.made, self.picks)
        except core.SimulationError as exc:
            self.say(str(exc), error=True)
            return False
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))
            self.say("It could not be kept: %s" % exc, error=True)
            return False
        label = self.made.Label
        self.finish_ok()
        log("%s %s" % ("edited" if self.editing else "added", label))
        _ui().refresh()
        return True

    def reject(self):
        done = super().reject()
        _ui().refresh()
        return done

    def cleanup(self):
        try:
            _glyphs().clear_preview()
        except Exception:
            pass
        super().cleanup()


def _keep_whole_bodies(item, picks):
    """A whole-body pick (Local Mesh Control's Body Selection) is kept as (body, ""): the
    engine's list of links dropped a body with no element (simulation._link_list), so the
    control lost what it was on. (Reported to sim-core; harmless once it keeps them.)"""
    if not any(not sub for _obj, sub in picks):
        return
    stored = [(o, s) for o, s in _sim()._picks(item.References)]
    if sorted((o.Name, s) for o, s in stored) == sorted((o.Name, s) for o, s in picks):
        return
    item.References = [(o, s) for o, s in picks]


def _initial_picks(doc):
    try:
        return [p for p in hole_common.picks(doc) if p[1]]
    except Exception:
        return []


def open_item(study, category, item=None, kind=None):
    """Structural Constraints / Structural Loads for `study` (Edit when `item` is given)."""
    from . import simulation_dialogs

    doc = study.Document
    initial = _initial_picks(doc) if item is None else ()
    if not commands.finish_open_dialog() or simulation_dialogs._busy(study):
        return None
    try:
        panel = ItemPanel(doc, study, category, item=item, kind=kind, initial=initial)
    except Exception as exc:
        warn("%s: %s" % (category, exc))
        return None
    Gui.Control.showDialog(panel)
    return panel


def edit_item(item):
    """Edit a constraint or load (browser: double-click or Edit)."""
    sim = _sim()
    study = sim.study_of(item)
    if study is None:
        return None
    data = sim.item_data(item)
    info = core.kind_info(data["category"], data["kind"])
    if not info.get("built"):
        commands.tell("%s is not in SciForge yet: suppress or delete it." % info["title"])
        return None
    return open_item(study, data["category"], item=item)


# -- Edit Gravity -------------------------------------------------------------------------------
class GravityPanel(pickpanel.PickPanel):
    """Fusion's Edit Gravity (research 3.5): on or off, the direction by Normal (a picked flat
    face or straight edge, Flip) or by Vector, and the magnitude (standard gravity)."""

    simulation_dialog = True
    title = "Edit Gravity"
    icon = "sim_gravity"
    last = None

    def __init__(self, doc, study):
        super().__init__(doc, "Edit Gravity")
        GravityPanel.last = self
        self.study = study
        sim = _sim()
        gravity = sim.settings(study)["gravity"]
        self.direction = list(gravity.get("direction") or [0.0, 0.0, -1.0])
        self.pick = None  # (obj, short) of the face or edge giving the direction
        self.study_names = {b.Name for b in sim.study_bodies(study)}
        self.form.setObjectName("SciForgeSimGravity")
        self.on = QtWidgets.QCheckBox("Gravity")
        self.on.setObjectName("SciForgeSim_gravity_on")
        self.on.setChecked(bool(gravity.get("on")))
        self.layout.addRow(self.on)
        self.kind = QtWidgets.QComboBox()
        self.kind.setObjectName("SciForgeSim_gravity_direction")
        self.kind.addItem("Vector", "vector")
        self.kind.addItem("Normal", "normal")
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.layout.addRow("Direction Type", self.kind)
        self.select = hole_common.SelectionField(self, 0, "Select a flat face or straight edge")
        self.select.button.setObjectName("SciForgeSimGravitySelect")
        self.layout.addRow("Direction", self.select.widget)
        self.fields = {}
        for axis, value in zip("xyz", self.direction):
            field = _number_field("g" + axis, value, "number")
            field.editingFinished.connect(lambda: self.schedule())
            self.layout.addRow(axis.upper(), field)
            self.fields[axis] = field
        self.flip = _toggle("gravity_flip", "Flip Direction", False)
        self.flip.toggled.connect(lambda _on: self.schedule())
        self.layout.addRow(self.flip)
        self.magnitude = _number_field(
            "g", gravity.get("g", 9806.65), "acceleration", shown=doc_units(doc)["acceleration"]
        )
        self.layout.addRow("Magnitude", self.magnitude)
        note = QtWidgets.QLabel(
            "Every body of the study weighs on the model (its material's density)."
        )
        note.setWordWrap(True)
        note.setStyleSheet(HINT_STYLE)
        self.layout.addRow(note)
        self.finish_layout()
        self.start_picking()
        self._kind_changed()

    def start_picking(self):
        super().start_picking()
        try:
            if self.gate is not None:
                hole_common.remove_gate(self.gate)
            self.gate = _Gate(self)
            Gui.Selection.addSelectionGate(self.gate)
        except Exception as exc:
            warn("%s: selection filter unavailable: %s" % (self.title, exc))

    def _kind_changed(self, *_a):
        normal = self.kind.currentData() == "normal"
        self.select.widget.setEnabled(normal)
        self.select.set_active(normal)
        for field in self.fields.values():
            field.setEnabled(not normal)
        self.schedule()

    def allow(self, obj, short):
        if self.kind.currentData() != "normal" or obj is None or not short:
            return False
        body = bodies.body_of(obj)
        if body is None:
            return False
        kind = element_kind(short)
        if kind == "faces":
            return surface_kind(obj, short) == "plane"
        if kind == "edges":
            try:
                return "Line" in obj.Shape.getElement(short).Curve.TypeId
            except Exception:
                return False
        return False

    def picks_changed(self, added, dropped):
        if added:
            obj, short, _point = added[-1]
            if self.allow(obj, short):
                self.pick = (obj, short)
                self.select.set_text("%s %s" % (obj.Label, short))
                return True
        if dropped and self.pick is not None:
            for obj, short, _p in dropped:
                if (obj, short) == self.pick:
                    self.pick = None
                    self.select.set_text(None)
                    return True
        return False

    def shown(self):
        if self.pick is None:
            return []
        return [(self.pick[0], [self.pick[1]])]

    def activate(self, _index):
        self.select.set_active(True)

    def clear_field(self, _index):
        self.pick = None
        self.select.set_text(None)
        self._sync()
        self.schedule()

    def read(self):
        """(settings for "gravity", sentence or None)."""
        try:
            if self.kind.currentData() == "normal":
                if self.pick is None:
                    return None, "Pick a flat face or a straight edge for the direction."
                obj, short = self.pick
                element = bodies.global_shape(obj, copy=False).getElement(short)
                if short.startswith("Face"):
                    u0, u1, v0, v1 = element.ParameterRange
                    d = element.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0) * -1.0
                else:
                    a, b = element.Vertexes[0].Point, element.Vertexes[-1].Point
                    d = b - a
                direction = [d.x, d.y, d.z]
            else:
                direction = [_value(self.fields[a]) for a in "xyz"]
            direction = core.unit_vector(direction)
            if self.flip.isChecked():
                direction = [-c for c in direction]
            g = _value(self.magnitude)  # (mm/s^2; a bare number is in the unit shown)
            if g <= 0:
                return None, "Gravity needs a magnitude above 0."
            return {"on": bool(self.on.isChecked()), "direction": direction, "g": g}, None
        except core.SimulationError as exc:
            return None, str(exc)

    def _preview(self):
        values, problem = self.read()
        self.message.setStyleSheet(ERROR_STYLE if problem else HINT_STYLE)
        self.message.setText(problem or "")

    def feature(self):
        return None

    def accept(self):
        if self._closed:
            return True
        values, problem = self.read()
        if problem:
            self.message.setStyleSheet(ERROR_STYLE)
            self.message.setText(problem)
            return False
        if not bodies.alive(self.study):
            self.message.setText("The study is gone (undone or deleted).")
            return False
        try:
            _sim().set_settings(self.study, {"gravity": values})
        except core.SimulationError as exc:
            self.message.setStyleSheet(ERROR_STYLE)
            self.message.setText(str(exc))
            return False
        except Exception as exc:
            warn("%s: %s" % (self.title, exc))
            self.message.setStyleSheet(ERROR_STYLE)
            self.message.setText("It could not be kept: %s" % exc)
            return False
        self.finish_ok()
        _ui().refresh()
        return True

    def reject(self):
        done = super().reject()
        _ui().refresh()
        return done


def open_gravity(study):
    from . import simulation_dialogs

    if not commands.finish_open_dialog() or simulation_dialogs._busy(study):
        return None
    panel = GravityPanel(study.Document, study)
    Gui.Control.showDialog(panel)
    return panel


# -- Local Mesh Control -------------------------------------------------------------------------
def open_local_mesh(study, item=None):
    """Fusion's Local Mesh Control (research 3.7): smaller elements on picked faces, edges or
    whole bodies (one size per control), blending into the study's size."""
    if "mesh" not in getattr(core, "TABLES", {}):
        commands.tell(
            "Local Mesh Control is not in SciForge yet: make the Average Element Size smaller "
            "in Settings > Mesh."
        )
        return None
    return open_item(study, "mesh", item=item, kind="local")

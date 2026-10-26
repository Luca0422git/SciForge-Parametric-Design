# SPDX-License-Identifier: LGPL-2.1-or-later
"""The browser in the SIMULATION workspace (Fusion's study tree, research 4): the simulation
model with the design's bodies, and under it each study with its Study Materials, Load Case
(Constraints, Loads, Gravity), Contacts, Mesh and Results. browser_ui.py asks this module for
the tree, the right-click menu, a double-click, Delete and a rename of a simulation row
(the hooks are marked "SIMULATION workspace" there); the tree's shape is
simulation_setup_core.tree (unit tested).

Right-click (simulation_setup_core.MENUS): a study: Activate, Settings, Clone Study, Rename,
Delete; a constraint or load: Edit, Suppress / Unsuppress, Rename, Delete; Gravity: Edit
Gravity, Toggle Gravity Off; Contacts: Automatic Contacts, Contact Manager; Mesh: Generate Mesh,
Mesh Settings, Local Mesh Control; Results: Show Results, Solve; a body: Show / Hide, Exclude
from Study / Include in Study. Double-click: a study becomes the active one, a constraint or
load opens its dialog, Study Materials / Gravity / Contacts / Mesh / Results open theirs.
Every change is one undo step.
"""

import FreeCADGui as Gui

from . import bodies, commands, log, ui_icon, warn
from . import simulation_core as core
from . import simulation_setup_core as score
from .compat import QtCore, QtWidgets


def _sim():
    from . import simulation

    return simulation


def _ui():
    from . import simulation_ui

    return simulation_ui


def is_sim(node):
    return bool(node) and str(node.get("kind", "")).startswith("sim_")


def _item_row(item, lost):
    sim = _sim()
    data = sim.item_data(item)
    try:
        info = core.kind_info(data["category"], data["kind"])
        built = bool(info.get("built"))
        text = core.describe(data["category"], data["kind"], data["options"])
    except Exception:
        built, text = False, data.get("kind", "")
    return {
        "name": item.Name,
        "label": item.Label,
        "category": data["category"],
        "kind": data["kind"],
        "suppressed": bool(item.Suppressed),
        "lost": item.Name in lost,
        "unbuilt": not built,
        "describe": text,
    }


def _study_row(study):
    sim = _sim()
    lost = {i.Name for i in sim.lost_items(study)}
    constraints, loads = [], []
    for item in sim.items(study):
        row = _item_row(item, lost)
        (constraints if row["category"] == "constraint" else loads).append(row)
    settings = sim.settings(study)
    gravity = settings["gravity"]
    summary = sim.summary(study)
    solved = bool(summary) and sim.result_object(study) is not None
    mesh = settings["mesh"]
    mesh_text = "Average element size %s %% of the model size, %s elements; made when it solves" % (
        core.fmt(mesh["size_pct"]),
        mesh["order"],
    )
    info = (summary or {}).get("mesh") or {}
    if solved and info.get("nodes"):
        mesh_text = "%s nodes, %s elements (%s)" % (
            info.get("nodes"),
            info.get("elements"),
            info.get("order", mesh["order"]),
        )
    try:
        from . import simulation_solve_dialog

        made = simulation_solve_dialog.mesh_object(study)
        if not solved and made is not None and made.FemMesh.NodeCount:
            mesh_text = "%d nodes, %d elements (Generate Mesh)" % (
                made.FemMesh.NodeCount,
                made.FemMesh.VolumeCount,
            )
    except Exception:
        pass
    results_text = "Double-click to show the results"
    stats = (summary or {}).get("stats") or {}
    if stats.get("safety", {}).get("min") is not None:
        results_text = "Lowest safety factor %s; double-click to show the results" % core.fmt(
            stats["safety"]["min"], 3
        )
    return {
        "name": study.Name,
        "label": study.Label,
        "type": sim.study_data(study).get("type"),
        "constraints": constraints,
        "loads": loads,
        "gravity": bool(gravity.get("on")),
        "gravity_text": "Gravity %s m/s^2 along (%s)"
        % (
            core.fmt(gravity["g"] / 1000.0),
            ", ".join(core.fmt(c, 3) for c in gravity.get("direction") or []),
        ),
        "mesh_text": mesh_text,
        "solved": solved,
        "out_of_date": solved and sim.out_of_date(study),
        "results_text": results_text,
        "contacts_text": "Bodies closer than %s mm are bonded (glued) when it solves"
        % core.fmt(settings["contact_tolerance"]),
    }


def tree(doc):
    """The SIMULATION browser's tree of the design (browser_core's node format)."""
    from . import browser_ui

    sim = _sim()
    active = _ui().active_study(doc)
    studies = []
    for study in sim.studies(doc):
        try:
            studies.append(_study_row(study))
        except Exception as exc:
            warn("simulation browser: %s: %s" % (study.Label, exc))
    in_study = set()
    if active is not None:
        in_study = {b.Name for b in sim.study_bodies(active)}
    model = []
    for body in bodies.solid_bodies(doc):
        try:
            visible = bool(body.ViewObject.Visibility) if body.ViewObject is not None else None
        except Exception:
            visible = None
        model.append(
            {
                "name": body.Name,
                "label": body.Label,
                "visible": visible,
                "in_study": active is None or body.Name in in_study,
            }
        )
    return score.tree(
        doc.Label,
        browser_ui.units(doc),
        studies,
        active.Name if active is not None else None,
        model,
        browser_ui.saved_views(doc),
    )


def starts_open(key):
    """Rows that start open (the user's own opening and closing is remembered first)."""
    if key in score.OPEN_KEYS or key.startswith(score.OPEN_PREFIXES):
        return True
    if key.startswith("sim_study:"):
        study = _ui().active_study()
        return study is not None and key == "sim_study:" + study.Name
    return False


def _object(doc, node):
    name = node.get("object") or node.get("study")
    return doc.getObject(name) if doc is not None and name else None


def _study_of(doc, node):
    name = node.get("study") or (node.get("object") if node.get("kind") == "sim_study" else None)
    obj = doc.getObject(name) if doc is not None and name else None
    return obj if obj is not None and _sim().is_study(obj) else None


def selection(doc, node):
    """[(object, [element names])] a click on a row selects in the 3D view: a body, or the
    faces / edges / corners a constraint or load is on (Fusion lights them up)."""
    if node.get("kind") == "sim_body":
        obj = _object(doc, node)
        return [(obj, [])] if obj is not None else []
    if node.get("kind") != "sim_item":
        return []
    item = doc.getObject(node["object"]) if doc is not None else None
    if item is None:
        return []
    out = {}
    order = []
    for obj, sub in _sim()._picks(item.References):
        if not sub or not bodies.alive(obj):
            continue
        target = getattr(obj, "Tip", None) or obj
        if target.Name not in out:
            out[target.Name] = (target, [])
            order.append(target.Name)
        out[target.Name][1].append(sub)
    return [out[n] for n in order]


# -- actions ---------------------------------------------------------------------------------------
def _transaction(doc, name, change):
    from . import simulation_dialogs

    return simulation_dialogs._transaction(doc, name, change)


def _busy(study):
    from . import simulation_dialogs

    return simulation_dialogs._busy(study)


def activate(doc, study):
    if study is None:
        return
    _ui().set_active_study(study)


def suppress(doc, item):
    if item is None or not commands.finish_open_dialog():
        return
    study = _sim().study_of(item)
    if study is not None and _busy(study):
        return
    on = not bool(item.Suppressed)
    # (not update_item: it checks the picks again, and a lost one can still be suppressed)
    _transaction(
        doc,
        "%s %s" % ("Suppress" if on else "Unsuppress", item.Label),
        lambda: setattr(item, "Suppressed", on),
    )
    _ui().refresh()


def delete(widget, nodes):
    """Delete studies, constraints and loads (one undo step)."""
    doc = widget._doc
    if doc is None or not commands.finish_open_dialog():
        return
    sim = _sim()
    targets = []
    for node in nodes:
        obj = _object(doc, node)
        if obj is None:
            continue
        if node["kind"] == "sim_study" and sim.is_study(obj):
            targets.append(("study", obj))
        elif node["kind"] == "sim_item" and sim.is_item(obj):
            targets.append(("item", obj))
    if not targets:
        return
    for _kind, obj in targets:
        study = obj if _kind == "study" else sim.study_of(obj)
        if study is not None and _busy(study):
            return
    names = ", ".join(obj.Label for _k, obj in targets)
    Gui.Selection.clearSelection()

    def change():
        for kind, obj in targets:
            if not bodies.alive(obj):
                continue
            if kind == "study":
                sim.delete_study(obj)
            else:
                sim.delete_item(obj)

    _transaction(doc, "Delete %s" % names if len(targets) == 1 else "Delete", change)
    log("deleted %s" % names)
    _ui().refresh()


def rename(widget, node, text):
    doc = widget._doc
    obj = _object(doc, node) if node["kind"] in ("sim_study", "sim_item") else None
    if node["kind"] == "sim_document" and doc is not None:
        doc.Label = text
        return
    if obj is None or text == obj.Label:
        return
    _transaction(doc, "Rename", lambda: setattr(obj, "Label", text))
    _ui().refresh()


def clone_study(doc, study):
    """Fusion's Clone Study (research 4): a copy with the same settings, materials,
    constraints and loads, and no results."""
    if study is None or not commands.finish_open_dialog():
        return None
    sim = _sim()
    made = {}

    def change():
        data = sim.study_data(study)
        copy = sim.create_study(doc, data.get("type", "static_stress"))
        copy_data = sim.study_data(copy)
        copy_data["settings"] = data["settings"]
        copy_data["materials"] = dict(data.get("materials") or {})
        bodies.save_meta(copy, sim.STUDY_PROP, copy_data)
        chosen = list(getattr(study, "SimBodies", None) or [])
        if chosen:
            copy.SimBodies = chosen
        for item in sim.items(study):
            d = sim.item_data(item)
            new = doc.addObject("App::FeaturePython", "SimItem")
            sim.ItemProxy(new)
            bodies.mark(new, sim.ITEM)
            bodies.hide_from_timeline(new)
            new.SimStudy = copy
            new.References = item.References
            new.Label = item.Label
            bodies.save_meta(new, sim.ITEM_PROP, d)
            new.Suppressed = bool(item.Suppressed)
        made["study"] = copy

    _transaction(doc, "Clone Study", change)
    log("cloned %s as %s" % (study.Label, made["study"].Label))
    _ui().set_active_study(made["study"])
    return made["study"]


def set_in_study(doc, body, include):
    """Exclude a body from the active study or take it back in (its SimBodies list)."""
    study = _ui().active_study(doc)
    if study is None or body is None or _busy(study):
        return
    if not commands.finish_open_dialog():
        return
    sim = _sim()
    current = [b for b in sim.study_bodies(study)]
    if include:
        if body not in current:
            current.append(body)
    else:
        current = [b for b in current if b is not body]
        if not current:
            commands.tell("Keep at least one body in the study.")
            return
    _transaction(
        doc,
        "%s %s" % ("Include" if include else "Exclude", body.Label),
        lambda: setattr(study, "SimBodies", sorted(current, key=lambda b: b.ID)),
    )
    _ui().refresh()


def _show_results(study):
    if study is None:
        return
    _ui().show_results(study)


def _later(fn, *args):
    def run():
        try:
            fn(*args)
        except Exception as exc:
            warn("simulation browser: %s" % exc)

    QtCore.QTimer.singleShot(0, run)


def handlers(widget, node):
    """{menu entry: function} for a simulation row."""
    from . import simulation_dialogs, simulation_panels, simulation_solve_dialog

    doc = widget._doc
    obj = _object(doc, node)
    study = _study_of(doc, node)
    return {
        "Activate": lambda: activate(doc, study),
        "Settings": lambda: simulation_dialogs.open_settings(study),
        "Mesh Settings": lambda: _settings_on(study, "Mesh"),
        "Clone Study": lambda: clone_study(doc, study),
        "Rename": lambda key=node["key"]: widget._rename_key(key),
        "Delete": lambda: delete(widget, [node]),
        "Study Materials": lambda: simulation_dialogs.open_materials(study),
        "Load Case Attributes": lambda: simulation_dialogs.open_attributes(study),
        "Structural Constraints": lambda: simulation_panels.open_item(study, "constraint"),
        "Structural Loads": lambda: simulation_panels.open_item(study, "load"),
        "Edit Constraint": lambda: simulation_panels.edit_item(obj),
        "Edit Load": lambda: simulation_panels.edit_item(obj),
        "Edit Local Mesh Control": lambda: simulation_panels.edit_item(obj),
        "Suppress": lambda: suppress(doc, obj),
        "Unsuppress": lambda: suppress(doc, obj),
        "Edit Gravity": lambda: simulation_panels.open_gravity(study),
        "Toggle Gravity Off": lambda: simulation_dialogs.toggle_gravity(study),
        "Automatic Contacts": lambda: simulation_dialogs.open_contacts(study),
        "Contact Manager": lambda: simulation_dialogs.open_contact_manager(study),
        "Generate Mesh": lambda: simulation_solve_dialog.generate_mesh(study),
        "Local Mesh Control": lambda: simulation_panels.open_local_mesh(study),
        "Show Results": lambda: _show_results(study),
        "Solve": lambda: (_ui().set_active_study(study), simulation_solve_dialog.open_solve()),
        "Show/Hide": lambda: widget._set_visible(node, not node["visible"]),
        "Exclude from Study": lambda: set_in_study(doc, obj, False),
        "Include in Study": lambda: set_in_study(doc, obj, True),
    }


def _settings_on(study, tab):
    from . import simulation_dialogs

    panel = simulation_dialogs.open_settings(study)
    if panel is not None:
        for i in range(panel.tabs.count()):
            if panel.tabs.tabText(i) == tab:
                panel.tabs.setCurrentIndex(i)


def build_menu(widget, item, node):
    """The right-click menu of a simulation row (None when it has no entry)."""
    entries = score.menu_for(node)
    if not entries:
        return None
    menu = QtWidgets.QMenu(widget)
    menu.setObjectName("SciForgeBrowserMenu")
    widget._handlers = {}
    table = handlers(widget, node)
    if node.get("kind") == "sim_item" and _object(widget._doc, node) is None:
        return None
    added = False
    for entry in entries:
        if entry == "-":
            if added:
                menu.addSeparator()
            continue
        text = entry
        if entry == "Show/Hide":
            if node.get("visible") is None:
                continue
            text = "Hide" if node["visible"] else "Show"
        action = (
            menu.addAction(ui_icon("delete"), text) if entry == "Delete" else menu.addAction(text)
        )
        widget._handlers[action] = table.get(entry)
        if entry.startswith("Edit ") or entry in ("Activate", "Study Materials", "Show Results"):
            font = action.font()
            font.setBold(True)
            action.setFont(font)
        added = True
    return menu if added else None


def double_clicked(widget, node):
    """Fusion: double-click activates a study; on a constraint or load it opens its dialog."""
    from . import simulation_dialogs, simulation_panels

    doc = widget._doc
    kind = node.get("kind")
    study = _study_of(doc, node)
    obj = _object(doc, node)
    if kind == "sim_study":
        _later(activate, doc, study)
    elif kind == "sim_item" and obj is not None:
        _later(simulation_panels.edit_item, obj)
    elif kind == "sim_materials":
        _later(simulation_dialogs.open_materials, study)
    elif kind == "sim_gravity":
        _later(simulation_panels.open_gravity, study)
    elif kind == "sim_contacts":
        _later(simulation_dialogs.open_contact_manager, study)
    elif kind == "sim_mesh":
        _later(_settings_on, study, "Mesh")
    elif kind == "sim_results":
        _later(_show_results, study)
    elif kind == "sim_loadcase":
        _later(simulation_dialogs.open_attributes, study)


RENAMABLE = ("sim_study", "sim_item", "sim_document")

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real-input helpers for the RESULTS tab scenarios (scenarios/simres_*.py, builder
sim-results). Kept outside scenarios/ because every file there runs as a scenario.

The parts and their studies are made by script and solved with the engine
(simulation.solve) in the setup step, as the brief allows; everything after that acts like a
person: the workspace button's menu, the ribbon's RESULTS tab and its buttons and menus, the
legend's drop-downs and buttons, clicks on the result in the 3D view, the dialogs' fields."""

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import widget_input as w

V = App.Vector
OUT = os.environ.get("SCIFORGE_SMOKE_OUT") or App.getUserAppDataDir()


def _process():
    QtWidgets.QApplication.processEvents()


# -- parts and studies ----------------------------------------------------------------------------
def beam(doc, label="Beam", size=(100.0, 10.0, 10.0), at=(0.0, 0.0, 0.0)):
    """A steel cantilever (a box body) of `size` at `at`."""
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = label
    box = body.newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = size
    box.Placement = App.Placement(V(*at), App.Rotation())
    body.Tip = box
    doc.recompute()
    return body


def face_at_x(body, x):
    for i, face in enumerate(body.Shape.Faces, 1):
        c = face.CenterOfMass
        if abs(c.x - x) < 1e-6 and "Plane" in face.Surface.TypeId:
            return "Face%d" % i
    return None


def cantilever_study(doc, body, force=100.0, label=None):
    """A Static Stress study: the beam fixed at its x = min end, `force` N down at the other."""
    from sciforge import simulation

    box = body.Shape.BoundBox
    study = simulation.create_study(doc, label=label)
    simulation.add_item(study, "constraint", "fixed", [(body, face_at_x(body, box.XMin))])
    simulation.add_item(
        study,
        "load",
        "force",
        [(body, face_at_x(body, box.XMax))],
        {"magnitude": float(force), "direction": "vector", "vector": [0.0, 0.0, -1.0]},
    )
    return study


def solve(study):
    from sciforge import simulation

    return simulation.solve(study, timeout=240)


def new_solved_beam(name="SimResBeam", force=100.0):
    """A step: a new design with a solved cantilever study (in the DESIGN workspace)."""

    def new_solved_beam():
        Gui.activateWorkbench("SciForgeWorkbench")
        doc = App.newDocument(name)
        body = beam(doc)
        study = cantilever_study(doc, body, force)
        solve(study)
        h.fit()

    new_solved_beam.__name__ = "new_solved_beam_" + name
    return new_solved_beam


def doc():
    return App.ActiveDocument


def body(label="Beam"):
    for obj in doc().Objects:
        if obj.TypeId == "PartDesign::Body" and obj.Label == label:
            return obj
    return None


def study(doc_=None):
    from sciforge import simulation

    found = simulation.studies(doc_ or doc())
    return found[-1] if found else None


def summary():
    from sciforge import simulation

    return simulation.summary(study())


def stats(key):
    return summary().get("stats", {}).get(key, {})


# -- workspace, ribbon, tabs ----------------------------------------------------------------------
def ribbon_ui():
    from sciforge import shell

    return shell.ribbon()


def workspace(label):
    from SciForgeTests.gui import drawing_input as d

    return d.workspace(label)


def tab_visible(tab_id):
    button = ribbon_ui().tab_buttons.get(tab_id)
    return button is not None and button.isVisible()


def current_tab():
    return ribbon_ui().current_tab()


def click_tab(tab_id):
    """Click a ribbon tab (SETUP / RESULTS) like a person."""
    button = ribbon_ui().tab_buttons.get(tab_id)
    if button is None or not button.isVisible():
        h.check("tab %s can be clicked" % tab_id, False)
        return False
    w.click(button)
    return True


def menu(group, label):
    from SciForgeTests.gui import sketch_input

    return sketch_input.menu_item(group, label)


def big(label):
    return h.ribbon(label)


def close_new_study_dialog():
    """sim-ui opens Fusion's New Study dialog when the workspace opens on a design without a
    study; the RESULTS scenarios start from a solved study, so this is a no-op then."""
    try:
        from sciforge import simulation_dialogs

        dialog = simulation_dialogs.new_study_dialog()
        if dialog is not None:
            dialog.reject()
    except Exception:
        pass


# -- the results on the screen --------------------------------------------------------------------
def results_ui():
    from sciforge import simulation_results_ui

    return simulation_results_ui


def results_core():
    from sciforge import simulation_results_core

    return simulation_results_core


def session():
    return results_ui().current()


def legend():
    s = session()
    return s.legend if s is not None else None


def legend_widget(name, kind=QtWidgets.QWidget):
    lg = legend()
    return lg.findChild(kind, name) if lg is not None else None


def choose_result(group, component=None):
    """Pick a result in the legend's drop-downs (Fusion's result type, then its component)."""
    box = legend_widget("SciForgeSimResultGroup", QtWidgets.QComboBox)
    if box is None:
        h.check("the legend's result drop-down", False)
        return False
    ok = ui.choose(box, group)
    if component:
        part = legend_widget("SciForgeSimResultComponent", QtWidgets.QComboBox)
        ok = ok and part is not None and ui.choose(part, component)
    return ok


def choose_unit(unit):
    box = legend_widget("SciForgeSimResultUnit", QtWidgets.QComboBox)
    return box is not None and ui.choose(box, unit)


def legend_text(name):
    label = legend_widget(name, QtWidgets.QLabel)
    return label.text() if label is not None else ""


def node_colours():
    """{node index: (r, g, b)} as drawn now (read back from the Coin texture coordinates)."""
    from sciforge import simulation_results_core as core

    s = session()
    return {n: core.map_colour(t) for n, t in s.display.node_positions().items()}


def colours_where(test):
    """The colours of the surface nodes whose undeformed place passes test(x, y, z)."""
    s = session()
    pts = s.data.points
    return [c for n, c in node_colours().items() if test(*pts[n])]


def mean(colours):
    if not colours:
        return (0.0, 0.0, 0.0)
    return tuple(sum(c[k] for c in colours) / len(colours) for k in range(3))


def drawn_place(node):
    """Where node `node` is drawn now (read back from the Coin coordinates)."""
    s = session()
    k = list(s.display.nodes).index(node)
    p = s.display.coords.point.getValues()[k]
    return (p[0], p[1], p[2])


def free_end_node():
    """The surface node farthest along X at the top centre (the free end)."""
    s = session()
    pts = s.data.points
    best = None
    for n in s.display.nodes.tolist():
        p = pts[n]
        key = (round(p[0], 6), -abs(p[1] - 5.0), p[2])
        if best is None or key > best[0]:
            best = (key, n)
    return best[1]


def tags(kind=None):
    s = session()
    if s is None:
        return []
    return [t for t in s.tag_list if kind is None or t["kind"] == kind]


def design_switches(label="Beam"):
    """whichChild of the body's Coin switch (-1 = hidden on the view)."""
    b = body(label)
    return b.ViewObject.SwitchNode.whichChild.getValue()


def result_root_in_view():
    from sciforge import simulation_results_view as view_mod

    graph = Gui.ActiveDocument.ActiveView.getSceneGraph()
    for i in range(graph.getNumChildren()):
        node = graph.getChild(i)
        try:
            if node.getName() == view_mod.ROOT_NAME:
                return True
        except Exception:
            continue
    return False


def task_panel():
    from sciforge import taskui

    return taskui.current()


def panel_field(name, kind=QtWidgets.QWidget):
    current = task_panel()
    form = getattr(current, "form", None)
    return form.findChild(kind, name) if form is not None else None


def esc():
    h.press(QtCore.Qt.Key_Escape)


def click_widget(widget):
    if widget is None:
        return False
    w.click(widget)
    return True


def dialog(name):
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == name and widget.isVisible():
            return widget
    return None


def undo_count():
    return doc().UndoCount


def modified():
    return bool(Gui.getDocument(doc().Name).Modified)


def wait_until(test, name="wait", seconds=60):
    """A step that comes back every 300 ms until test() is true (at most `seconds`)."""
    import time

    state = {"start": None}

    def step():
        if state["start"] is None:
            state["start"] = time.time()
        try:
            done = test()
        except Exception:
            done = False
        if not done and time.time() - state["start"] < seconds:
            h.state["queue"].insert(0, step)

    step.__name__ = name
    step.wait_ms = 300
    return step

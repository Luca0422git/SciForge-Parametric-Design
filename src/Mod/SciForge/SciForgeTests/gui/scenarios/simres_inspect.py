# SPDX-License-Identifier: LGPL-2.1-or-later
"""Solver Data, Iso-surface and Point Probes with real clicks (builder sim-results), on a solved
steel cantilever (100 x 10 x 10 mm, 100 N down at the tip).

A  INSPECT > Solver Data: the solve (when, how long, each step) and the mesh (the nodes and
   elements of the solve, degrees of freedom 3 x nodes, parabolic elements, the mesher); Copy
   puts it on the clipboard as text; Close.
B  Legend > Stress, INSPECT > Iso-surface: the surface where the von Mises stress is half way
   between its lowest and highest, in that value's legend colour, the result see-through around
   it; a typed value (75 % of the highest) moves it towards the support (every point of it at
   that stress); keys on the slider move the value; the legend's Displacement moves the surface
   to that result; a value above the highest finds nothing and says so; Cancel puts back what
   was there (no iso-surface); again on Stress, OK keeps it.
C  INSPECT > Point Probes: a click on the iso-surface puts a probe inside the part reading the
   iso-surface's value; typing a node's X, Y, Z moves it there (the node's own value, drawn
   where the node is drawn); X = 150 is outside the part and says so; back inside; a click on
   the beam's top face adds a second probe; Remove takes the first away; DEFORMATION > Actual
   moves the tag with the part; Close keeps the probes.
D  Iso-surface again, Remove Iso-surface: gone, the result solid again.
E  Slice Plane (OK at the middle), Point Probes: a click on the cut face puts a probe on the
   plane, inside the part; Clear All; Close; Slice Plane > Remove Slice.
F  Nothing in the undo history, the design not modified; Finish Results takes the tags away.
G  RESULTS again, INSPECT > Measure: it works on the model, so SETUP comes back with the beam
   shown and Measure open; Esc closes it.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

V = App.Vector
state = {}


def setup():
    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimResInspect")
    body = s.beam(doc)
    study = s.cantilever_study(doc, body, 100.0)
    s.solve(study)
    h.fit()


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def results_check():
    h.check("results shown", s.session() is not None)
    state["undo"] = s.undo_count()
    state["modified"] = s.modified()


# -- A Solver Data
def a_solver():
    s.menu("INSPECT", "Solver Data")


def a_solver_check():
    dialog = s.dialog("SciForgeSimSolverData")
    h.check("Solver Data open", dialog is not None)
    if dialog is None:
        return
    tree = dialog.findChild(QtWidgets.QTreeWidget, "SciForgeSimSolverTree")
    rows = s.tree_rows(tree)
    h.check("the solve and the mesh", "Solve" in rows and "Mesh" in rows, list(rows))
    mesh = s.summary().get("mesh", {})
    nodes, elements = int(mesh.get("nodes", 0)), int(mesh.get("elements", 0))
    got = rows.get("Mesh", {})
    h.check(
        "the solve's nodes and elements",
        got.get("Nodes") == "{:,}".format(nodes) and got.get("Elements") == "{:,}".format(elements),
        (got, nodes, elements),
    )
    h.check(
        "degrees of freedom: 3 per node",
        got.get("Degrees of freedom") == "{:,}".format(3 * nodes),
        got.get("Degrees of freedom"),
    )
    h.check(
        "parabolic elements, the mesher",
        got.get("Element order", "").startswith("Parabolic") and bool(got.get("Mesher")),
        got,
    )
    solve = rows.get("Solve", {})
    h.check(
        "when and how long",
        bool(solve.get("Solved")) and solve.get("Time taken", "").endswith(" s"),
        solve,
    )
    h.check("each step timed", "Solving (CalculiX)" in solve, list(solve))
    QtWidgets.QApplication.clipboard().setText("")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimSolverCopy"))


def a_copy_check():
    text = QtWidgets.QApplication.clipboard().text()
    nodes = int(s.summary().get("mesh", {}).get("nodes", 0))
    h.check("Copy: the data as text", "Nodes: {:,}".format(nodes) in text, text[:200])
    dialog = s.dialog("SciForgeSimSolverData")
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimSolverClose"))


def a_close_check():
    h.check("Solver Data closed", s.dialog("SciForgeSimSolverData") is None)


# -- B Iso-surface
def b_stress():
    s.choose_result("Stress")


def b_iso():
    s.menu("INSPECT", "Iso-surface")


def _iso_values(key):
    """The result's value at (up to 60 of) the iso-surface's points (interpolated in the mesh
    at their places on the unloaded part)."""
    sess = s.session()
    rest = sess.display.iso_rest
    out = []
    for p in rest[:: max(1, len(rest) // 60)]:
        where = sess.data.locate(p)
        out.append(None if where is None else sess.data.at(where, key))
    return out


def _close(a, b, span):
    return a is not None and b is not None and abs(a - b) <= 1e-6 * max(abs(span), 1e-12)


def b_iso_check():
    sess = s.session()
    panel = s.task_panel()
    h.check("Iso-surface open", panel is not None and panel.title == "Iso-surface")
    st = sess.data.stats("von_mises")
    span = st["max"] - st["min"]
    level = (st["min"] + st["max"]) / 2.0
    state["vm"] = (st["min"], st["max"])
    value = s.panel_field("SciForgeSimIsoValue", QtWidgets.QDoubleSpinBox)
    h.check(
        "half way between the lowest and the highest stress",
        value is not None and abs(value.value() - level) < 1e-3 and value.suffix() == " MPa",
        (value.value() if value else None, level),
    )
    h.check("the iso-surface drawn", sess.display.iso_shown() and len(sess.display.iso_points))
    h.check("the result see-through around it", sess.display.see_through())
    values = _iso_values("von_mises")
    h.check(
        "every point of it at that stress",
        values and all(_close(v, level, span) for v in values),
        values[:6],
    )
    core = s.results_core()
    lo, hi, reverse = sess.scale()
    want = core.map_colour(core.position(level, lo, hi, reverse))
    got = sess.display.iso_colour()
    h.check(
        "in the legend's colour of that value",
        all(abs(a - b) < 2e-3 for a, b in zip(got, want)),
        (got, want),
    )
    state["iso_x"] = float(sess.display.iso_rest[:, 0].max())
    ui.type_into(value, "%.4f" % (st["min"] + 0.75 * span))


def b_type_check():
    sess = s.session()
    lo, hi = state["vm"]
    level = lo + 0.75 * (hi - lo)
    h.check("the typed value taken", abs(sess.iso_level() - level) < 1e-3, sess.iso_level())
    values = _iso_values("von_mises")
    h.check(
        "the surface moved to that stress",
        values and all(_close(v, sess.iso_level(), hi - lo) for v in values),
        values[:6],
    )
    far = float(sess.display.iso_rest[:, 0].max()) if len(sess.display.iso_rest) else None
    h.check(
        "nearer the support (the stress is highest there)",
        far is not None and far < state["iso_x"],
        (far, state["iso_x"]),
    )
    slider = s.panel_field("SciForgeSimIsoSlider", QtWidgets.QSlider)
    state["slider"] = slider.value()
    from SciForgeTests.gui import widget_input as wi

    for _ in range(3):
        wi.key(slider, QtCore.Qt.Key_PageDown)


def b_slider_check():
    sess = s.session()
    slider = s.panel_field("SciForgeSimIsoSlider", QtWidgets.QSlider)
    lo, hi = state["vm"]
    level = lo + (hi - lo) * slider.value() / 1000.0
    h.check("the slider moved", slider.value() != state["slider"], slider.value())
    h.check("the value follows the slider", abs(sess.iso_level() - level) < 1e-6 * (hi - lo))
    value = s.panel_field("SciForgeSimIsoValue", QtWidgets.QDoubleSpinBox)
    h.check("the value field too", abs(value.value() - level) < 1e-3, (value.value(), level))
    s.choose_result("Displacement")


def b_displacement_check():
    sess = s.session()
    core = s.results_core()
    label = s.panel_field("SciForgeSimIsoResult", QtWidgets.QLabel)
    h.check(
        "the panel follows the legend",
        label is not None and label.text() == core.result_name(sess.result),
        (label.text() if label else None, sess.result),
    )
    st = sess.data.stats(sess.result)
    values = _iso_values(sess.result)
    h.check(
        "the surface is the displacement's now",
        values and all(_close(v, sess.iso_level(), st["max"] - st["min"]) for v in values),
        values[:6],
    )
    value = s.panel_field("SciForgeSimIsoValue", QtWidgets.QDoubleSpinBox)
    h.check("in mm", value.suffix() == " mm", value.suffix())
    ui.type_into(value, "%.4f" % (st["max"] * 3.0))


def b_too_high_check():
    sess = s.session()
    message = s.panel_field("SciForgeSimIsoMessage", QtWidgets.QLabel)
    h.check("nothing above the highest", not sess.display.iso_shown())
    h.check("it says so", message is not None and "Nothing" in message.text(), message.text())
    h.task_button("Cancel")


def b_cancel_check():
    sess = s.session()
    h.check("Cancel closed it", s.task_panel() is None)
    h.check("no iso-surface (as before)", not sess.iso_on and not sess.display.iso_shown())
    h.check("the result solid again", not sess.display.see_through())
    s.choose_result("Stress")


def b_again():
    s.menu("INSPECT", "Iso-surface")


def b_ok():
    h.task_button("OK")


def b_ok_check():
    sess = s.session()
    h.check("OK closed it", s.task_panel() is None)
    h.check("the iso-surface stays", sess.iso_on and sess.display.iso_shown())


# -- C Point Probes
def c_points():
    s.menu("INSPECT", "Point Probes")


def _table():
    return s.panel_field("SciForgeSimPointTable", QtWidgets.QTableWidget)


def _iso_centre():
    import numpy as np

    tris = s.session().display.iso_points.reshape((-1, 3, 3))
    area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    return V(*tris[int(np.argmax(area))].mean(axis=0))


def c_hover():
    panel = s.task_panel()
    h.check("Point Probes open", panel is not None and panel.title == "Point Probes")
    h.move(h.screen_point(_iso_centre()))


c_hover.wait_ms = 400


def c_hover_check():
    sess = s.session()
    hover = s.tags("hover")
    lo, hi = state["vm"]
    h.check(
        "over the iso-surface: its value under the mouse",
        len(hover) == 1 and _close(hover[0]["value"], sess.iso_level(), hi - lo),
        hover,
    )
    h.check("nothing placed yet", not sess.points)


def c_click_iso():
    h.click(_iso_centre())


def c_click_iso_check():
    sess = s.session()
    table = _table()
    h.check("a probe", len(sess.points) == 1 and table.rowCount() == 1, sess.points)
    if not sess.points:
        return
    lo, hi = state["vm"]
    value = sess.point_value(sess.points[0])
    h.check(
        "on the iso-surface: its value",
        _close(value, sess.iso_level(), hi - lo),
        (value, sess.iso_level()),
    )
    tag = s.tags("point")
    h.check("its tag", len(tag) == 1 and tag[0]["text"].startswith("P1: "), tag)
    h.check("listed with its place", table.item(0, 1).text() not in ("", "-"))
    # a node inside the beam's middle: its own value is what a probe there must read
    pts = sess.data.points
    best = None
    for n in range(len(pts)):
        d = float(((pts[n] - (50.0, 5.0, 5.0)) ** 2).sum())
        if best is None or d < best[0]:
            best = (d, n)
    state["node"] = best[1]
    state["node_at"] = [float(c) for c in pts[best[1]]]
    s.edit_cell(table, 0, 1, "%.6f" % state["node_at"][0])


def c_type_y():
    s.edit_cell(_table(), 0, 2, "%.6f" % state["node_at"][1])


def c_type_z():
    s.edit_cell(_table(), 0, 3, "%.6f mm" % state["node_at"][2])


def c_typed_check():
    sess = s.session()
    point = sess.points[0] if sess.points else None
    h.check(
        "moved to the typed place",
        point is not None and all(abs(a - b) < 1e-5 for a, b in zip(point["at"], state["node_at"])),
        (point, state["node_at"]),
    )
    if point is None:
        return
    node = state["node"]
    want = float(sess.data.values("von_mises")[node])
    got = sess.point_value(point)
    h.check("the node's own stress there", got is not None and abs(got - want) < 1e-6, (got, want))
    tag = s.tags("point")[0]
    drawn = sess.display.node_place(node)
    h.check(
        "drawn where the node is drawn (bent with the part)",
        all(abs(a - b) < 1e-4 for a, b in zip(tag["point"], drawn)),
        (tag["point"], list(drawn)),
    )
    table = _table()
    h.check("the table shows its value", table.item(0, 4).text().endswith("MPa"))
    s.edit_cell(table, 0, 1, "150")


def c_outside_check():
    sess = s.session()
    message = s.panel_field("SciForgeSimPointMessage", QtWidgets.QLabel)
    h.check("outside the part: no value", sess.point_value(sess.points[0]) is None)
    h.check("it says so", "outside" in message.text(), message.text())
    h.check("the tag too", s.tags("point")[0]["text"] == "P1: outside the part", s.tags("point"))
    h.check("the table too", _table().item(0, 4).text() == "outside the part")
    s.edit_cell(_table(), 0, 1, "%.6f" % state["node_at"][0])


def c_back_check():
    sess = s.session()
    h.check("back inside", sess.point_value(sess.points[0]) is not None)
    message = s.panel_field("SciForgeSimPointMessage", QtWidgets.QLabel)
    h.check("the message gone", message.text() == "", message.text())
    panel = s.task_panel()
    grips = getattr(panel, "grips", [])
    h.check("the probe's grips: X, Y and Z arrows", len(grips) == 3)
    if len(grips) != 3:
        return
    from SciForgeTests.gui import arrow_input as ai

    state["before_grip"] = tuple(sess.points[0]["at"])
    start = ai.head_point(grips[0])
    h.drag_points(start, start + V(10, 0, 0))


c_back_check.wait_ms = 900


def c_grip_check():
    sess = s.session()
    at = sess.points[0]["at"]
    before = state.get("before_grip")
    moved = at[0] - before[0] if before else None
    h.check("dragging the X grip moves it along X", moved is not None and 4.0 < moved < 16.0, moved)
    h.check(
        "only along X",
        before is not None and abs(at[1] - before[1]) < 1e-9 and abs(at[2] - before[2]) < 1e-9,
        (at, before),
    )
    h.check("the table follows", _table().item(0, 1).text() == s.results_core().fmt_mm(at[0]))
    grips = getattr(s.task_panel(), "grips", [])
    h.check(
        "the grips stand at its new place",
        len(grips) == 3
        and all(
            abs(a - b) < 1e-6
            for a, b in zip(
                (grips[0].origin.x, grips[0].origin.y, grips[0].origin.z),
                sess.point_place(sess.points[0]),
            )
        ),
    )
    # the top face near the free end, where it is drawn (bent), away from the iso-surface
    h.click(V(*sess.point_place({"at": (90.0, 5.0, 10.0)})))


def c_top_check():
    sess = s.session()
    h.check("a second probe", len(sess.points) == 2, sess.points)
    if len(sess.points) < 2:
        return
    at = sess.points[1]["at"]
    h.check(
        "on the top face, near the tip",
        abs(at[2] - 10.0) < 1e-4 and abs(at[0] - 90.0) < 3.0,
        at,
    )
    texts = [t["text"] for t in s.tags("point")]
    h.check("two tags", len(texts) == 2 and texts[1].startswith("P2: "), texts)
    layer = sess.tags
    layer.repaint()
    boxes = [b for b in getattr(layer, "boxes", []) if b is not None]
    h.check(
        "no two tags' boxes overlap",
        len(boxes) >= 3
        and not any(a.intersects(b) for i, a in enumerate(boxes) for b in boxes[i + 1 :]),
        [(b.x(), b.y(), b.width(), b.height()) for b in boxes],
    )
    state["second_at"] = at
    table = _table()
    from SciForgeTests.gui import widget_input as wi

    wi.click(table.viewport(), table.visualItemRect(table.item(0, 0)).center())


def c_remove():
    panel = s.task_panel()
    s.click_widget(panel.form.findChild(QtWidgets.QPushButton, "SciForgeSimPointRemove"))


def c_remove_check():
    sess = s.session()
    h.check(
        "Remove took the selected one away",
        len(sess.points) == 1 and sess.points[0]["at"] == state["second_at"],
        sess.points,
    )
    h.check("renumbered", s.tags("point")[0]["text"].startswith("P1: "))
    s.menu("DEFORMATION", "Actual")


def c_actual_check():
    import numpy as np

    sess = s.session()
    point = sess.points[0]
    where = sess.data.locate(point["at"])
    want = np.asarray(point["at"]) + sess.data.moved(where)
    tag = s.tags("point")[0]
    h.check(
        "the tag moved with the part (Actual)",
        abs(sess.display.factor - 1.0) < 1e-12
        and all(abs(a - b) < 1e-6 for a, b in zip(tag["point"], want)),
        (tag["point"], list(want)),
    )
    h.task_button("Close")


def c_close_check():
    sess = s.session()
    h.check("Close: the dialog closed", s.task_panel() is None)
    h.check("the probe stays", len(sess.points) == 1 and len(s.tags("point")) == 1)
    s.menu("DEFORMATION", "Adjusted")


# -- D Iso-surface removed
def d_iso():
    s.menu("INSPECT", "Iso-surface")


def d_remove():
    s.click_widget(s.panel_field("SciForgeSimIsoRemove", QtWidgets.QPushButton))


def d_check():
    sess = s.session()
    h.check("Remove Iso-surface closed the dialog", s.task_panel() is None)
    h.check("no iso-surface", not sess.iso_on and not sess.display.iso_shown())
    h.check("the result solid again", not sess.display.see_through())


# -- E a probe on a slice's cut face
def e_slice():
    s.big("Slice Plane")


def e_flip():
    """Keep the half whose cut face looks at the camera (Flip when the kept half hides it)."""
    from sciforge import simulation_results_ui as ui

    sess = s.session()
    _origin, normal = ui.slice_plane(sess)
    look = Gui.ActiveDocument.ActiveView.getViewDirection()
    if look.x * normal[0] + look.y * normal[1] + look.z * normal[2] < 0:
        s.click_widget(s.panel_field("SciForgeSimSliceFlip", QtWidgets.QCheckBox))


def e_slice_ok():
    h.task_button("OK")


def e_points():
    sess = s.session()
    h.check("the slice cuts the result", sess.display.cap_shown())
    state["slice_x"] = float(sess.slice["offset"])
    s.menu("INSPECT", "Point Probes")


def e_click_cut():
    import numpy as np

    sess = s.session()
    tris = sess.display.cap_points.reshape((-1, 3, 3))
    area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    h.click(V(*tris[int(np.argmax(area))].mean(axis=0)))


def e_click_cut_check():
    sess = s.session()
    h.check("a probe on the cut face", len(sess.points) == 2, sess.points)
    if len(sess.points) < 2:
        return
    point = sess.points[1]
    drawn = sess.point_place(point)
    h.check(
        "on the slice plane (where it is drawn)",
        abs(drawn[0] - state["slice_x"]) < 1e-5,
        (list(drawn), state["slice_x"]),
    )
    at = point["at"]
    h.check(
        "inside the part (not on its outside faces)",
        0.01 < at[1] < 9.99 and 0.01 < at[2] < 9.99 and sess.point_value(point) is not None,
        at,
    )
    s.click_widget(s.panel_field("SciForgeSimPointClear", QtWidgets.QPushButton))


def e_clear_check():
    sess = s.session()
    h.check("Clear All", not sess.points and not s.tags("point") and _table().rowCount() == 0)
    h.task_button("Close")


def e_unslice():
    s.big("Slice Plane")


def e_remove_slice():
    s.click_widget(s.panel_field("SciForgeSimSliceRemove", QtWidgets.QPushButton))


def e_check():
    sess = s.session()
    h.check("the slice removed", sess.slice is None and not sess.display.cap_shown())


# -- F display only
def f_check():
    h.check("nothing in the undo history", s.undo_count() == state["undo"])
    h.check("the design not modified", s.modified() == state["modified"])
    s.big("Finish Results")


def f_finish_check():
    h.check("Finish Results: back to SETUP", s.session() is None)
    h.check("no results left on the view", not s.result_root_in_view())


def g_results():
    s.click_tab("sim_results")


def g_measure():
    h.check("results shown again", s.session() is not None)
    s.menu("INSPECT", "Measure")


g_measure.wait_ms = 600


def g_measure_check():
    from sciforge import measure_ui, taskui

    h.check("Measure open", isinstance(taskui.current(), measure_ui.MeasurePanel))
    h.check("SETUP in front: the model is needed", s.current_tab() == "sim_setup", s.current_tab())
    h.check("the results put away", s.session() is None)
    h.check("the beam shown", s.design_switches() != -1)
    s.esc()


def g_esc_check():
    from sciforge import taskui

    h.check("Esc closed Measure", taskui.current() is None)


h.run(
    "simres_inspect",
    [
        setup,
        enter,
        results,
        results_check,
        a_solver,
        a_solver_check,
        a_copy_check,
        a_close_check,
        b_stress,
        b_iso,
        b_iso_check,
        b_type_check,
        b_slider_check,
        b_displacement_check,
        b_too_high_check,
        b_cancel_check,
        b_again,
        b_ok,
        b_ok_check,
        c_points,
        c_hover,
        c_hover_check,
        c_click_iso,
        c_click_iso_check,
        c_type_y,
        c_type_z,
        c_typed_check,
        c_outside_check,
        c_back_check,
        c_grip_check,
        c_top_check,
        c_remove,
        c_remove_check,
        c_actual_check,
        c_close_check,
        d_iso,
        d_remove,
        d_check,
        e_slice,
        e_flip,
        e_slice_ok,
        e_points,
        e_click_cut,
        e_click_cut_check,
        e_clear_check,
        e_unslice,
        e_remove_slice,
        e_check,
        f_check,
        f_finish_check,
        g_results,
        g_measure,
        g_measure_check,
        g_esc_check,
    ],
)

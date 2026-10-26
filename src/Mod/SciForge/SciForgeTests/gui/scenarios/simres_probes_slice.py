# SPDX-License-Identifier: LGPL-2.1-or-later
"""Surface Probes and Slice Plane with real clicks (builder sim-results), on a solved steel
cantilever (100 x 10 x 10 mm, 100 N at the tip).

A  INSPECT > Surface Probes: a click on the result's top face reads the value of the node under
   the mouse (a tag on the model and a line in the dialog); a second click adds a second probe;
   the legend's Stress makes the probes read the stress there; Clear All removes them; Close.
   Esc in the dialog closes it and keeps the probes.
B  Slice Plane: the result is cut across X at the middle and the cut face is coloured with the
   values inside (each between the result's min and max); Across Y at 2 mm puts the cut face on
   that plane; Flip keeps the other half; a probe click on the cut face reads the value inside;
   Slice alone shows the cut face inside the whole result drawn see-through; OK keeps it.
C  Slice Plane again, Cancel: the slice stays as it was; again, Remove Slice: the result is whole.
D  A click on empty space with Surface Probes open adds nothing.
"""

import FreeCAD as App
from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

V = App.Vector
state = {}


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def results_check():
    h.check("results shown", s.session() is not None)


def _node_near(x, y, z):
    sess = s.session()
    pts = sess.data.points
    best = None
    for n in sess.display.nodes.tolist():
        d = sum((pts[n][k] - c) ** 2 for k, c in enumerate((x, y, z)))
        if best is None or d < best[0]:
            best = (d, n)
    return best[1]


def a_probes():
    s.big("Surface Probes")


def a_probes_check():
    panel = s.task_panel()
    h.check("Surface Probes open", panel is not None and panel.title == "Surface Probes")


def a_click_top():
    sess = s.session()
    node = _node_near(50.0, 5.0, 10.0)
    state["node1"] = node
    h.click(V(*sess.display.node_place(node)))


def a_click_top_check():
    sess = s.session()
    probes = s.tags("probe")
    h.check("one probe", len(probes) == 1, probes)
    if not probes:
        return
    node = state["node1"]
    h.check(
        "the probe reads the node under the mouse",
        probes[0]["node"] == node,
        (probes[0]["node"], node),
    )
    value = float(sess.data.values("safety")[node])
    h.check("its safety factor", abs(probes[0]["value"] - value) < 1e-9, (probes[0], value))
    listing = s.panel_field("SciForgeSimProbeList", QtWidgets.QListWidget)
    h.check("listed in the dialog", listing is not None and listing.count() == 1)


def a_click_front():
    sess = s.session()
    node = _node_near(80.0, 0.0, 5.0)
    state["node2"] = node
    h.click(V(*sess.display.node_place(node)))


def a_click_front_check():
    probes = s.tags("probe")
    h.check("two probes", len(probes) == 2, probes)
    if len(probes) == 2:
        h.check("the second at the front face's node", probes[1]["node"] == state["node2"])


def a_stress():
    s.choose_result("Stress")


def a_stress_check():
    sess = s.session()
    probes = s.tags("probe")
    vm = sess.data.values("von_mises")
    h.check(
        "the probes read the stress now",
        len(probes) == 2
        and abs(probes[0]["value"] - float(vm[state["node1"]])) < 1e-9
        and probes[0]["text"].endswith("MPa"),
        probes,
    )


def a_clear():
    panel = s.task_panel()
    s.click_widget(panel.form.findChild(QtWidgets.QPushButton, "SciForgeSimProbeClear"))


def a_clear_check():
    h.check("Clear All removed the probes", not s.tags("probe") and not s.session().probes)


def a_close():
    h.task_button("Close")


def a_close_check():
    h.check("dialog closed", s.task_panel() is None)


def a_esc_open():
    s.big("Surface Probes")


def a_esc_click():
    sess = s.session()
    h.click(V(*sess.display.node_place(state["node1"])))


def a_esc():
    s.esc()


def a_esc_check():
    h.check("Esc closed Surface Probes", s.task_panel() is None)
    h.check("the probe stays (Fusion)", len(s.tags("probe")) == 1, s.tags("probe"))


def b_slice():
    s.big("Slice Plane")


def b_slice_check():
    sess = s.session()
    panel = s.task_panel()
    h.check("Slice Plane open", panel is not None and panel.title == "Slice Plane")
    h.check("cut across X", sess.slice is not None and sess.slice["axis"] == "x", sess.slice)
    h.check("at the middle", sess.slice is not None and abs(sess.slice["offset"] - 50.0) < 1e-6)
    h.check("the result is clipped", sess.display.clipped())
    h.check("the cut face is drawn", sess.display.cap_shown() and len(sess.display.cap_points))
    vm = s.stats("von_mises")
    vals = sess.display.cap_values
    h.check(
        "the cut face's values lie inside the result's range",
        len(vals) and vals.min() >= vm["min"] - 1e-6 and vals.max() <= vm["max"] + 1e-6,
        (vals.min() if len(vals) else None, vals.max() if len(vals) else None),
    )
    xs = sess.display.cap_points[:, 0]
    h.check("on the plane x = 50", abs(xs.min() - 50) < 1e-6 and abs(xs.max() - 50) < 1e-6)


def b_axis_y():
    ui.choose(s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox), "Across Y (XZ plane)")
    # Tab away from the field (Enter would be the dialog's OK, as in Fusion's dialogs)
    ui.type_into(s.panel_field("SciForgeSimSliceOffset", QtWidgets.QDoubleSpinBox), "2")


def b_axis_y_check():
    sess = s.session()
    h.check(
        "across Y at 2 mm",
        sess.slice["axis"] == "y" and abs(sess.slice["offset"] - 2) < 1e-6,
        sess.slice,
    )
    ys = sess.display.cap_points[:, 1] if len(sess.display.cap_points) else None
    h.check(
        "the cut face lies on y = 2",
        ys is not None and abs(ys.min() - 2) < 1e-6 and abs(ys.max() - 2) < 1e-6,
    )


def b_axis_x_flip():
    ui.choose(s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox), "Across X (YZ plane)")
    s.click_widget(s.panel_field("SciForgeSimSliceFlip", QtWidgets.QCheckBox))


def b_axis_x_flip_check():
    sess = s.session()
    h.check("flipped", sess.slice["flip"] is True, sess.slice)
    from sciforge import simulation_results_ui as ui_mod

    _origin, normal = ui_mod.slice_plane(sess)
    h.check(
        "keeps the held half (normal -X)", normal == (-1.0, -0.0, -0.0) or normal[0] == -1.0, normal
    )


def b_cap_probe():
    sess = s.session()
    s.big("Surface Probes")
    pts = sess.display.cap_points
    centre = pts[0:3].mean(axis=0)
    state["cap_point"] = tuple(float(c) for c in centre)
    h.click(V(*state["cap_point"]))


def b_cap_probe_check():
    sess = s.session()
    probes = [t for t in s.tags("probe") if t.get("node") is None]
    h.check("a probe on the cut face", len(probes) == 1, s.tags("probe"))
    if probes:
        vm = s.stats("von_mises")
        value = probes[0]["value"]
        h.check("its value inside the range", vm["min"] - 1e-6 <= value <= vm["max"] + 1e-6, value)
        h.check(
            "where the cut face was clicked",
            max(abs(a - b) for a, b in zip(probes[0]["point"], state["cap_point"])) < 0.5,
            (probes[0]["point"], state["cap_point"]),
        )
    h.task_button("Close")


def b_slice_alone():
    s.big("Slice Plane")
    ui.choose(s.panel_field("SciForgeSimSliceStyle", QtWidgets.QComboBox), "Slice alone")


def b_slice_alone_check():
    sess = s.session()
    h.check("slice alone", sess.slice["style"] == "slice", sess.slice)
    h.check("the whole result see-through around it", sess.display.see_through())
    h.check("not clipped", not sess.display.clipped())
    h.check("the cut face drawn", sess.display.cap_shown())


def b_ok():
    h.task_button("OK")


def b_ok_check():
    sess = s.session()
    h.check("OK keeps the slice", sess.slice is not None and sess.slice["style"] == "slice")
    h.check("dialog closed", s.task_panel() is None)
    state["kept"] = dict(sess.slice)


def c_cancel():
    s.big("Slice Plane")
    ui.choose(s.panel_field("SciForgeSimSliceStyle", QtWidgets.QComboBox), "Cut the result away")


def c_cancel_press():
    h.task_button("Cancel")


def c_cancel_check():
    sess = s.session()
    h.check("Cancel puts the slice back as it was", sess.slice == state["kept"], sess.slice)
    h.check("see-through again (slice alone)", sess.display.see_through())


def c_remove():
    s.big("Slice Plane")
    s.click_widget(s.panel_field("SciForgeSimSliceRemove", QtWidgets.QPushButton))


def c_remove_check():
    sess = s.session()
    h.check("no slice", sess.slice is None)
    h.check("not clipped", not sess.display.clipped())
    h.check("no cut face", not sess.display.cap_shown())
    h.check("the whole result drawn, opaque", not sess.display.see_through())
    h.check("no undeformed ghost", not sess.display.ghost_shown())
    h.check("dialog closed", s.task_panel() is None)


def d_empty():
    s.big("Surface Probes")
    state["count"] = len(s.tags("probe"))
    h.click_empty()


def d_empty_check():
    h.check("a click on empty space adds no probe", len(s.tags("probe")) == state["count"])
    h.task_button("Close")


h.run(
    "simres_probes_slice",
    [
        s.new_solved_beam("SimResProbes"),
        enter,
        results,
        results_check,
        a_probes,
        a_probes_check,
        a_click_top,
        a_click_top_check,
        a_click_front,
        a_click_front_check,
        a_stress,
        a_stress_check,
        a_clear,
        a_clear_check,
        a_close,
        a_close_check,
        a_esc_open,
        a_esc_click,
        a_esc,
        a_esc_check,
        b_slice,
        b_slice_check,
        b_axis_y,
        b_axis_y_check,
        b_axis_x_flip,
        b_axis_x_flip_check,
        b_cap_probe,
        b_cap_probe_check,
        b_slice_alone,
        b_slice_alone_check,
        b_ok,
        b_ok_check,
        c_cancel,
        c_cancel_press,
        c_cancel_check,
        c_remove,
        c_remove_check,
        d_empty,
        d_empty_check,
    ],
)

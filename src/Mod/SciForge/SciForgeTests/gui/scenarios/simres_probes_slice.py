# SPDX-License-Identifier: LGPL-2.1-or-later
"""Surface Probes and Slice Plane with real clicks (builder sim-results), on a solved steel
cantilever (100 x 10 x 10 mm, 100 N at the tip).

A  INSPECT > Surface Probes: the mouse over the result shows the value under it (a lighter tag
   that follows the mouse and goes away off the model); a click on the result's top face reads
   the value of the node under the mouse (a tag on the model and a line in the dialog); a
   second click adds a second probe; Remove takes the one chosen in the list away;
   the legend's Stress makes the probes read the stress there; Clear All removes them; Close.
   Esc in the dialog closes it and keeps the probes.
B  Slice Plane: the result is cut across X at the middle and the cut face is coloured with the
   values inside (each between the result's min and max); Mesh lines on the cut draws where
   the plane crosses the elements (on the plane, more than the outline), and goes again;
   Displacement arrows on the cut: arrows standing on the plane, pointing down (the beam bends
   down), and go again;
   dragging the plane's arrow moves the cut along X; Across Y at 2 mm puts the cut face on
   that plane; Flip keeps the other half; a probe click on the cut face reads the value inside;
   Slice alone shows the cut face inside the whole result drawn see-through; OK keeps it.
C  Slice Plane again, Cancel: the slice stays as it was; again, Remove Slice: the result is whole.
D  A click on empty space with Surface Probes open adds nothing.
E  Slice Plane, a click on the beam's top face: the cut is parallel to it (across Z) half way
   down, the half under it kept, so the cut face looks at whoever clicked; OK; Remove Slice.
F  A wedge (a sloped face, solved): Slice Plane, a click on the sloped face: the cut is
   parallel to that face ("Parallel to the face clicked"), the cut face lies on the plane and
   the drag arrow points along the face's normal; the design's construction plane (tilted 30
   degrees) in the Plane list: the cut on it; OK.
"""

import FreeCAD as App
import FreeCADGui as Gui
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


def a_hover():
    sess = s.session()
    node = _node_near(50.0, 5.0, 10.0)
    state["node1"] = node
    h.move(h.screen_point(V(*sess.display.node_place(node))))


a_hover.wait_ms = 400


def a_hover_check():
    sess = s.session()
    hover = s.tags("hover")
    h.check("the value under the mouse shows", len(hover) == 1, s.tags())
    if hover:
        value = float(sess.data.values("safety")[state["node1"]])
        h.check("the node's value", abs(hover[0]["value"] - value) < 1e-9, (hover, value))
    h.check("no probe placed by a move", not s.tags("probe"))
    h.move(h._empty_spot(h.gl_widget()))


a_hover_check.wait_ms = 400


def a_hover_away_check():
    h.check("off the model: gone", not s.tags("hover"), s.tags("hover"))


def a_click_top():
    sess = s.session()
    h.click(V(*sess.display.node_place(state["node1"])))


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
    # Remove with nothing chosen in the list takes the newest away; a third click puts it back
    s.click_widget(s.panel_field("SciForgeSimProbeRemove", QtWidgets.QPushButton))


def a_remove_check():
    probes = s.tags("probe")
    h.check(
        "Remove took the newest probe away",
        len(probes) == 1 and probes[0]["node"] == state["node1"],
        probes,
    )
    listing = s.panel_field("SciForgeSimProbeList", QtWidgets.QListWidget)
    h.check("the list follows", listing.count() == 1)
    sess = s.session()
    h.click(V(*sess.display.node_place(state["node2"])))


def a_again_check():
    h.check("the second probe again", len(s.tags("probe")) == 2, s.tags("probe"))


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


def b_lines():
    s.click_widget(s.panel_field("SciForgeSimSliceLines", QtWidgets.QCheckBox))


def b_lines_check():
    sess = s.session()
    display = sess.display
    h.check("mesh lines on the cut", display.cap_lines_shown() and sess.slice.get("lines"))
    pts = display.cap_line_coords.point.getValues()
    xs = [p[0] for p in pts]
    h.check("on the plane x = 50", xs and max(abs(x - 50.0) for x in xs) < 1e-4)
    h.check(
        "the elements' edges, not only the outline",
        display.cap_line_count > 4,
        display.cap_line_count,
    )
    s.click_widget(s.panel_field("SciForgeSimSliceLines", QtWidgets.QCheckBox))


def b_lines_off_check():
    h.check("mesh lines off again", not s.session().display.cap_lines_shown())
    s.click_widget(s.panel_field("SciForgeSimSliceVectors", QtWidgets.QCheckBox))


def b_vectors_check():
    sess = s.session()
    display = sess.display
    h.check("displacement arrows on the cut", display.vectors_shown() and display.vector_count > 3)
    shafts = display.vector_segments[: display.vector_count]
    feet_x = shafts[:, 0, 0] if len(shafts) else []
    h.check(
        "standing on the plane x = 50",
        len(feet_x) and max(abs(x - 50.0) for x in feet_x) < 1e-4,
    )
    down = (shafts[:, 1] - shafts[:, 0])[:, 2] if len(shafts) else []
    h.check("pointing down, as the beam bends", len(down) and (down < 0).all(), list(down)[:5])
    s.click_widget(s.panel_field("SciForgeSimSliceVectors", QtWidgets.QCheckBox))


def b_vectors_off_check():
    h.check("the arrows off again", not s.session().display.vectors_shown())


def b_drag():
    from SciForgeTests.gui import arrow_input as ai

    panel = s.task_panel()
    arrow = getattr(panel, "arrow", None)
    h.check("a drag arrow on the plane", arrow is not None)
    if arrow is None:
        return
    state["offset0"] = panel.offset.value()
    start = ai.head_point(arrow)
    h.drag_points(start, start + V(20, 0, 0))


b_drag.wait_ms = 900


def b_drag_check():
    sess = s.session()
    panel = s.task_panel()
    moved = panel.offset.value() - state["offset0"]
    h.check("dragging the arrow moves the plane along X", 8.0 < moved < 32.0, moved)
    h.check("the slice follows", abs(sess.slice["offset"] - panel.offset.value()) < 1e-9)
    xs = sess.display.cap_points[:, 0] if len(sess.display.cap_points) else None
    h.check(
        "the cut face at the new place",
        xs is not None and abs(xs.mean() - panel.offset.value()) < 1e-6,
    )


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


def e_slice():
    s.big("Slice Plane")


def e_click_top():
    sess = s.session()
    h.click(V(*sess.point_place({"at": (60.0, 5.0, 10.0)})))


def e_click_top_check():
    sess = s.session()
    h.check(
        "parallel to the top face: across Z, half way down",
        sess.slice is not None
        and sess.slice["axis"] == "z"
        and abs(sess.slice["offset"] - 5.0) < 1e-6,
        sess.slice,
    )
    h.check("the half under it kept (Flip)", sess.slice is not None and sess.slice["flip"])
    zs = sess.display.cap_points[:, 2] if len(sess.display.cap_points) else None
    h.check(
        "the cut face on z = 5",
        zs is not None and abs(zs.min() - 5.0) < 1e-6 and abs(zs.max() - 5.0) < 1e-6,
    )
    box = s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox)
    flip = s.panel_field("SciForgeSimSliceFlip", QtWidgets.QCheckBox)
    h.check(
        "the dialog says so",
        box.currentText() == "Across Z (XY plane)" and flip.isChecked(),
        box.currentText(),
    )
    h.task_button("OK")


def e_remove():
    s.big("Slice Plane")
    s.click_widget(s.panel_field("SciForgeSimSliceRemove", QtWidgets.QPushButton))


def e_remove_check():
    h.check("no slice", s.session().slice is None)


def f_wedge():
    """A wedge 100 long, 10 deep and 10 high whose side towards the camera slopes (from x = 60
    to x = 100 across its depth); fixed at x = 0, pushed down (-Z) on the sloped face."""
    from sciforge import simulation

    doc = App.newDocument("SimResWedge")
    h.fit()
    look = Gui.ActiveDocument.ActiveView.getViewDirection()
    toward_minus_y = look.y > 0  # the camera sees the -Y side
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Wedge"
    wedge = body.newObject("PartDesign::AdditiveWedge", "Wedge")
    wedge.Ymin, wedge.Ymax, wedge.Zmin, wedge.Zmax = 0.0, 10.0, 0.0, 10.0
    wedge.Z2min, wedge.Z2max, wedge.Xmin, wedge.X2min = 0.0, 10.0, 0.0, 0.0
    # the base (y = 0) and the top (y = 10) rectangles: the shorter one makes the slope
    wedge.Xmax, wedge.X2max = (60.0, 100.0) if toward_minus_y else (100.0, 60.0)
    body.Tip = wedge
    doc.recompute()
    sloped = None
    for i, face in enumerate(body.Shape.Faces, 1):
        n = face.normalAt(0, 0)
        if abs(n.x) > 0.1 and abs(n.y) > 0.1:
            sloped = "Face%d" % i
            state["slope_normal"] = (n.x, n.y, n.z)
    h.check("the wedge has a sloped face", sloped is not None)
    study = simulation.create_study(doc)
    simulation.add_item(study, "constraint", "fixed", [(body, s.face_at_x(body, 0.0))])
    simulation.add_item(
        study,
        "load",
        "force",
        [(body, sloped)],
        {"magnitude": 100.0, "direction": "vector", "vector": [0.0, 0.0, -1.0]},
    )
    # a construction plane through (50, 5, 5), tilted 30 degrees about X
    plane = body.newObject("PartDesign::Plane", "DatumPlane")
    plane.Label = "Tilted Plane"
    plane.MapMode = "Deactivated"
    plane.Placement = App.Placement(App.Vector(50, 5, 5), App.Rotation(App.Vector(1, 0, 0), 30))
    doc.recompute()
    s.solve(study)
    h.fit()


def f_enter():
    s.workspace("Simulation")


def f_results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def f_slice():
    h.check("the wedge's results shown", s.session() is not None)
    s.big("Slice Plane")


def f_click_slope():
    sess = s.session()
    # the middle of the sloped face (x 80, y 5, z 5), where it is drawn
    h.click(V(*sess.point_place({"at": (80.0, 5.0, 5.0)})))


def f_click_slope_check():
    import numpy as np

    sess = s.session()
    spec = sess.slice or {}
    h.check("parallel to the face clicked", spec.get("axis") == "face", spec)
    if spec.get("axis") != "face":
        return
    outward = np.asarray(state["slope_normal"])
    keep = np.asarray(spec["normal"])
    h.check(
        "its normal is the sloped face's (pointing into the part)",
        np.allclose(keep, -outward / np.linalg.norm(outward), atol=1e-6),
        (keep, outward),
    )
    pts = sess.display.cap_points
    along = pts @ keep if len(pts) else None
    h.check(
        "the cut face lies on the plane",
        along is not None and float(np.abs(along - spec["offset"]).max()) < 1e-6,
    )
    box = s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox)
    h.check("the dialog says so", box.currentText() == "Parallel to the face clicked")
    arrow = getattr(s.task_panel(), "arrow", None)
    h.check(
        "the drag arrow along the face's normal",
        arrow is not None
        and np.allclose((arrow.direction.x, arrow.direction.y, arrow.direction.z), keep, atol=1e-6),
    )
    ui.choose(s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox), "On Tilted Plane")


def f_plane_check():
    import numpy as np

    sess = s.session()
    spec = sess.slice or {}
    n = np.array([0.0, -np.sin(np.radians(30)), np.cos(np.radians(30))])
    h.check(
        "the cut on the construction plane",
        spec.get("axis") == "face" and np.allclose(spec.get("normal"), n, atol=1e-9),
        spec,
    )
    h.check("through its place", abs(spec.get("offset", 0) - float(n @ (50, 5, 5))) < 1e-9)
    pts = sess.display.cap_points
    h.check(
        "the cut face lies on it",
        len(pts) and float(np.abs(pts @ n - float(n @ (50, 5, 5))).max()) < 1e-6,
    )
    box = s.panel_field("SciForgeSimSliceAxis", QtWidgets.QComboBox)
    h.check("the dialog says so", box.currentText() == "On Tilted Plane", box.currentText())
    h.task_button("OK")


def f_ok_check():
    sess = s.session()
    h.check("OK keeps it", sess.slice is not None and sess.slice["axis"] == "face")
    h.check("dialog closed", s.task_panel() is None)


h.run(
    "simres_probes_slice",
    [
        s.new_solved_beam("SimResProbes"),
        enter,
        results,
        results_check,
        a_probes,
        a_probes_check,
        a_hover,
        a_hover_check,
        a_hover_away_check,
        a_click_top,
        a_click_top_check,
        a_click_front,
        a_click_front_check,
        a_remove_check,
        a_again_check,
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
        b_lines,
        b_lines_check,
        b_lines_off_check,
        b_vectors_check,
        b_vectors_off_check,
        b_drag,
        b_drag_check,
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
        e_slice,
        e_click_top,
        e_click_top_check,
        e_remove,
        e_remove_check,
        f_wedge,
        f_enter,
        f_results,
        f_slice,
        f_click_slope,
        f_click_slope_check,
        f_plane_check,
        f_ok_check,
    ],
)

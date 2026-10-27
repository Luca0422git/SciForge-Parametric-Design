# SPDX-License-Identifier: LGPL-2.1-or-later
"""The RESULTS tab's deformation scale, animation and display options with real clicks (builder
sim-results), on a solved steel cantilever (100 x 10 x 10 mm, 100 N at the tip).

A  DEFORMATION > Actual: the beam is drawn with its true displacement (each node moved by the
   solve's displacement); > Adjusted x 5: five times Adjusted (the largest movement drawn at 25 %
   of the model size); > Undeformed: the nodes where they are without the load; > Adjusted again
   (the menu's tick follows).
B  Animate: the animation bar shows and the beam bends back and forth; Stop holds it at the
   chosen scale; 2x and Mirror Loop, Play again; Save... writes an animated GIF (one picture
   per step, up and back down, the part bending from one to the next) and an animated WebP,
   and the animation plays on; Close takes the bar away.
C  Show Mesh on and off (the element edges), DISPLAY > Undeformed Model (the see-through
   unloaded shape) on and off, INSPECT > Show Min/Max off (no tags) and on again.
D  Results Details: the target bands ticked colour the safety factor in three bands (and the
   legend shows them), a lower target typed changes the sentence; Close.
E  Animating, a click on SETUP stops it all and shows the beam; back on RESULTS the result is
   still, at its scale.
"""

from PySide import QtWidgets

from SciForgeTests.gui import dialog_input as ui
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as s

state = {}


def enter():
    s.workspace("Simulation")


def results():
    s.close_new_study_dialog()
    s.click_tab("sim_results")


def results_check():
    sess = s.session()
    h.check("results shown", sess is not None)
    state["node"] = s.free_end_node()
    state["adjusted"] = sess.factor("adjusted")


def _expected(node, factor):
    sess = s.session()
    p = sess.data.points[node]
    d = sess.data.displacement[node]
    return tuple(float(p[k] + factor * d[k]) for k in range(3))


def _close(a, b, tol=1e-3):
    return max(abs(x - y) for x, y in zip(a, b)) < tol


def a_actual():
    s.menu("DEFORMATION", "Actual")


def a_actual_check():
    sess = s.session()
    node = state["node"]
    h.check("Actual chosen", sess.deformation == "actual", sess.deformation)
    h.check("drawn 1 x", abs(sess.display.factor - 1.0) < 1e-12, sess.display.factor)
    drawn = s.drawn_place(node)
    h.check(
        "the free end moved by its true displacement",
        _close(drawn, _expected(node, 1.0)),
        (drawn, _expected(node, 1.0)),
    )
    h.check("the menu ticks Actual", s.results_ui().deform_actual())


def a_x5():
    s.menu("DEFORMATION", "Adjusted x 5")


def a_x5_check():
    sess = s.session()
    node = state["node"]
    factor = sess.display.factor
    h.check("five times Adjusted", abs(factor - 5 * state["adjusted"]) < 1e-9, factor)
    largest = factor * sess.data.max_displacement
    h.check(
        "largest movement drawn at 25 % of the model size",
        abs(largest - 0.25 * sess.data.diagonal) < 1e-6,
        (largest, sess.data.diagonal),
    )
    h.check("nodes drawn moved", _close(s.drawn_place(node), _expected(node, factor)))
    h.check("legend says so", "Adjusted x 5" in sess.legend.deform_label.text())


def a_undeformed():
    s.menu("DEFORMATION", "Undeformed")


def a_undeformed_check():
    sess = s.session()
    node = state["node"]
    h.check("Undeformed: drawn 0 x", sess.display.factor == 0.0)
    h.check("node at its unloaded place", _close(s.drawn_place(node), _expected(node, 0.0)))


def a_adjusted():
    s.menu("DEFORMATION", "Adjusted")


def a_adjusted_check():
    sess = s.session()
    h.check("Adjusted again", sess.deformation == "adjusted" and s.results_ui().deform_adjusted())
    h.check("Adjusted factor", abs(sess.display.factor - state["adjusted"]) < 1e-9)


def b_animate():
    s.big("Animate")


b_animate.wait_ms = 900


def b_animate_check():
    sess = s.session()
    bar = sess.bar
    h.check("animation bar shown", bar is not None and bar.isVisible())
    h.check("playing", sess.anim["playing"])
    state["f1"] = sess.display.factor
    h.check("the menu ticks Animate", s.results_ui().animation_on())


b_animate_check.wait_ms = 450


def b_moving():
    sess = s.session()
    f2 = sess.display.factor
    h.check(
        "the beam moves while it plays",
        abs(f2 - state["f1"]) > 1e-9 and 0.0 <= f2 <= state["adjusted"] + 1e-9,
        (state["f1"], f2),
    )


def b_stop():
    s.click_widget(s.session().bar.findChild(QtWidgets.QToolButton, "SciForgeSimPlay"))


def b_stop_check():
    sess = s.session()
    h.check("stopped", not sess.anim["playing"])
    h.check("held at the chosen scale", abs(sess.display.factor - state["adjusted"]) < 1e-9)
    h.check("button says Play", sess.bar.play_button.text() == "Play")


def b_options():
    bar = s.session().bar
    ui.choose(bar.findChild(QtWidgets.QComboBox, "SciForgeSimSpeed"), "2x")
    ui.choose(bar.findChild(QtWidgets.QComboBox, "SciForgeSimPlayMode"), "Mirror Loop")
    s.click_widget(bar.findChild(QtWidgets.QToolButton, "SciForgeSimPlay"))


b_options.wait_ms = 600


def b_options_check():
    sess = s.session()
    h.check("2x speed", sess.anim["speed"] == 2.0, sess.anim)
    h.check("mirror loop", sess.anim["mode"] == "mirror", sess.anim)
    h.check("playing again", sess.anim["playing"])


def b_save():
    s.click_widget(s.session().bar.findChild(QtWidgets.QToolButton, "SciForgeSimAnimationSave"))


def _save_as(name):
    import os

    dialog = s.dialog("SciForgeSimSaveAnimation")
    h.check("Save Animation open", dialog is not None)
    if dialog is None:
        return None
    path = os.path.join(s.OUT, name)
    if os.path.exists(path):
        os.remove(path)
    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimAnimationPath"), path)
    s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimAnimationSaveFile"))
    return path


def b_save_gif():
    state["gif"] = _save_as("simres-beam-animation.gif")


def _frames(path):
    from PIL import Image, ImageChops

    with Image.open(path) as image:
        count = getattr(image, "n_frames", 1)
        size = image.size
        image.seek(0)
        first = image.convert("RGB")
        image.seek(count // 2)
        middle = image.convert("RGB")
    moved = ImageChops.difference(first, middle).getbbox() is not None
    return count, size, moved


def b_save_gif_check():
    import os

    path = state.get("gif")
    h.check("the GIF written", path is not None and os.path.isfile(path), path)
    if not path or not os.path.isfile(path):
        return
    count, size, moved = _frames(path)
    want = len(s.results_core().animation_cycle(20, "mirror"))
    h.check("one picture per step, up and back down", count == want, (count, want))
    h.check("a picture of the 3D view", size[0] >= 320 and size[1] >= 200, size)
    h.check("the part bends from one picture to the next", moved)
    h.check("the dialog closed", s.dialog("SciForgeSimSaveAnimation") is None)
    sess = s.session()
    h.check("the animation plays on", sess.anim["playing"])
    s.click_widget(sess.bar.findChild(QtWidgets.QToolButton, "SciForgeSimAnimationSave"))


def b_save_webp():
    state["webp"] = _save_as("simres-beam-animation.webp")


def b_save_webp_check():
    import os

    from PIL import features

    path = state.get("webp")
    if not features.check("webp"):
        h.check("WebP: not in this Pillow (GIF only)", True)
        return
    h.check("the WebP written", path is not None and os.path.isfile(path), path)
    if path and os.path.isfile(path):
        count, _size, moved = _frames(path)
        h.check("its pictures", count == len(s.results_core().animation_cycle(20, "mirror")))
        h.check("bending", moved)


def b_close():
    s.click_widget(s.session().bar.findChild(QtWidgets.QToolButton, "SciForgeSimAnimationClose"))


def b_close_check():
    sess = s.session()
    h.check("bar closed", sess.bar is None and not sess.anim["shown"])
    h.check("not playing", not sess.anim["playing"])
    h.check("held at the chosen scale", abs(sess.display.factor - state["adjusted"]) < 1e-9)


def c_mesh_on():
    s.big("Show Mesh")


def c_mesh_on_check():
    sess = s.session()
    h.check("mesh edges shown", sess.display.mesh_shown() and s.results_ui().mesh_on())
    h.check(
        "every surface element edge drawn",
        sess.display.mesh_switch.getChild(0).getChild(3).coordIndex.getNum() > 100,
    )


def c_mesh_off():
    s.big("Show Mesh")


def c_mesh_off_check():
    h.check("mesh edges hidden again", not s.session().display.mesh_shown())


def c_ghost():
    s.menu("DISPLAY", "Undeformed Model")


def c_ghost_check():
    sess = s.session()
    h.check("undeformed model shown", sess.display.ghost_shown() and s.results_ui().ghost_on())
    pts = sess.display.ghost_coords.point.getValues()
    k = list(sess.display.nodes).index(state["node"])
    h.check("at the unloaded places", _close(tuple(pts[k]), _expected(state["node"], 0.0)))


def c_ghost_off():
    s.menu("DISPLAY", "Undeformed Model")


def c_ghost_off_check():
    h.check("undeformed model hidden again", not s.session().display.ghost_shown())


def c_minmax_off():
    s.menu("INSPECT", "Show Min/Max")


def c_minmax_off_check():
    h.check("no min / max tags", not s.tags("min") and not s.tags("max"))
    h.check("the menu unticks it", not s.results_ui().minmax_on())


def c_minmax_on():
    s.menu("INSPECT", "Show Min/Max")


def c_minmax_on_check():
    h.check("min / max tags back", len(s.tags("min")) == 1 and len(s.tags("max")) == 1)


def d_details():
    s.big("Results Details")


def d_bands():
    dialog = s.dialog("SciForgeSimDetails")
    h.check("Results Details open", dialog is not None)
    if dialog is None:
        return
    state["before"] = dialog.headline.text()
    box = dialog.findChild(QtWidgets.QCheckBox, "SciForgeSimTargetBands")
    s.click_widget(box)
    s.type_enter(dialog.findChild(QtWidgets.QDoubleSpinBox, "SciForgeSimTargetLower"), "4")


def d_bands_check():
    sess = s.session()
    dialog = s.dialog("SciForgeSimDetails")
    h.check("target bands on", sess.bands)
    h.check("lower target 4", abs(sess.targets[0] - 4.0) < 1e-9, sess.targets)
    h.check("legend shows the bands", bool(sess.legend_info.get("bands")))
    sf = s.stats("safety")["min"]
    text = dialog.headline.text() if dialog is not None else ""
    if sf < 4.0:
        h.check("below the new target", text.startswith("Below"), text)
    else:
        h.check("meets the new target", text.startswith("Meets"), text)
    h.check("the sentence changed", text != state["before"] or sf >= 4.0, text)


def d_close():
    dialog = s.dialog("SciForgeSimDetails")
    if dialog is not None:
        s.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimDetailsClose"))


def e_animate():
    s.big("Animate")


e_animate.wait_ms = 500


def e_setup():
    s.click_tab("sim_setup")


def e_setup_check():
    sess = s.results_ui().SESSIONS.get(s.doc().Name)
    h.check("SETUP selected", s.current_tab() == "sim_setup")
    h.check("results put away", s.session() is None and not s.result_root_in_view())
    h.check("the animation stopped", sess is not None and not sess.anim["playing"])
    h.check("the beam shows", s.design_switches() != -1)


def e_back():
    s.click_tab("sim_results")


e_back.wait_ms = 900


def e_back_check():
    sess = s.session()
    h.check("results again", sess is not None)
    if sess is None:
        return
    h.check("still, not playing", not sess.anim["playing"])
    h.check("at the chosen scale", abs(sess.display.factor - state["adjusted"]) < 1e-9)
    h.check("the bar is back to restart it", sess.bar is not None and sess.bar.isVisible())


h.run(
    "simres_deformation",
    [
        s.new_solved_beam("SimResDeform"),
        enter,
        results,
        results_check,
        a_actual,
        a_actual_check,
        a_x5,
        a_x5_check,
        a_undeformed,
        a_undeformed_check,
        a_adjusted,
        a_adjusted_check,
        b_animate,
        b_animate_check,
        b_moving,
        b_stop,
        b_stop_check,
        b_options,
        b_options_check,
        b_save,
        b_save_gif,
        b_save_gif_check,
        b_save_webp,
        b_save_webp_check,
        b_close,
        b_close_check,
        c_mesh_on,
        c_mesh_on_check,
        c_mesh_off,
        c_mesh_off_check,
        c_ghost,
        c_ghost_check,
        c_ghost_off,
        c_ghost_off_check,
        c_minmax_off,
        c_minmax_off_check,
        c_minmax_on,
        c_minmax_on_check,
        d_details,
        d_bands,
        d_bands_check,
        d_close,
        e_animate,
        e_setup,
        e_setup_check,
        e_back,
        e_back_check,
    ],
)

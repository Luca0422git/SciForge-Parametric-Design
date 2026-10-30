# SPDX-License-Identifier: LGPL-2.1-or-later
"""Speed on a 306-face part (sim QA): a 200 x 200 x 6 plate with 100 chamfered holes (each
hole a wall and two chamfers), made by script; every step after it real input. Each check
names the time measured (the report lists them); the limits are generous, the numbers are
what matters.

A  Workspace > Simulation, New Study: how long the workspace and the Pre-check light take.
B  Structural Constraints: Fixed on the plate's front side face (a click), OK; Structural
   Loads: Pressure 0.1 MPa on the top face (one face with 100 holes in it), OK: how long each
   dialog takes to open and to preview.
C  Solve: how long it takes, and the longest moment the window did not answer (a 50 ms timer
   counts the gaps) while it ran.
D  The RESULTS tools on the big result: Stress, Surface Probes (a click), Show Mesh on and off,
   Slice Plane (open, OK, removed), Animate (on 2 s, off), Report (saved): each one's time.
"""

import os
import tempfile
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as rs
from SciForgeTests.gui import simsetup_steps as s

state = {"times": {}}


class Heartbeat:
    """The longest gap between the ticks of a 50 ms timer: how long the window did not
    answer."""

    def __init__(self):
        self.last = time.time()
        self.worst = 0.0
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    def tick(self):
        now = time.time()
        self.worst = max(self.worst, now - self.last)
        self.last = now

    def stop(self):
        self.timer.stop()
        return self.worst


def timed(name, fn):
    start = time.time()
    fn()
    QtWidgets.QApplication.processEvents()
    took = time.time() - start
    state["times"][name] = took
    return took


def plate():
    import Part

    V = App.Vector
    tools = []
    for i in range(10):
        for j in range(10):
            x, y = 10.0 + 20.0 * i, 10.0 + 20.0 * j
            hole = Part.makeCylinder(3.0, 6.0, V(x, y, 0))
            top = Part.makeCone(3.0, 4.0, 1.0, V(x, y, 5.0))
            bottom = Part.makeCone(4.0, 3.0, 1.0, V(x, y, 0.0))
            tools.append(hole.fuse([top, bottom]))
    return Part.makeBox(200, 200, 6).cut(Part.Compound(tools))


def setup():
    from SciForgeTests.headless import sim_benchmarks as sb

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimQASpeed")
    body = sb.make_body(doc, plate(), "Plate")
    state["faces"] = len(body.Shape.Faces)
    h.fit()


# -- A ------------------------------------------------------------------------------------------
def a_enter():
    h.check("the plate has 300+ faces (%d)" % state["faces"], state["faces"] >= 300)
    took = timed("enter SIMULATION", lambda: s.workspace("Simulation"))
    h.check("A Workspace > Simulation: %.2f s" % took, took < 10.0)


def a_create():
    dialog = s.new_study_dialog()
    took = timed("New Study", lambda: s.click_widget(dialog.create_button if dialog else None))
    h.check("A Create Study and the Pre-check light: %.2f s" % took, took < 10.0, s.light())


# -- B ------------------------------------------------------------------------------------------
def b_constraint():
    took = timed("Structural Constraints opens", lambda: h.ribbon("Structural Constraints"))
    h.check("B Structural Constraints opens: %.2f s" % took, took < 5.0)


def b_pick():
    body = s.body("Plate")
    front = s.face_named(
        body, lambda f: "Plane" in f.Surface.TypeId and abs(f.CenterOfMass.y) < 1e-6
    )
    state["front"] = front
    state["t_pick"] = time.time()
    s.click_face(body, front)


def b_preview():
    took = time.time() - state["t_pick"]
    state["times"]["Fixed pick and preview"] = took
    h.check("B the pick previews: %.2f s" % took, s.preview_count() > 0, s.preview_count())
    took = timed("Fixed OK", s.ok)
    h.check("B OK: %.2f s" % took, took < 10.0)


def b_load():
    took = timed("Structural Loads opens", lambda: h.ribbon("Structural Loads"))
    h.check("B Structural Loads opens: %.2f s" % took, took < 5.0)


def b_pressure():
    p = s.item_panel()
    if p is not None and p.type_box.currentText() != "Pressure":
        from SciForgeTests.gui import dialog_input as ui

        ui.choose(p.type_box, "Pressure")


def b_top():
    body = s.body("Plate")
    top = s.face_named(
        body, lambda f: "Plane" in f.Surface.TypeId and abs(f.CenterOfMass.z - 6) < 1e-6
    )
    state["t_pick"] = time.time()
    s.click_face(body, top)


def b_top_value():
    took = time.time() - state["t_pick"]
    state["times"]["Pressure pick and preview"] = took
    h.check("B the top face (100 holes in it) previews: %.2f s" % took, s.preview_count() > 0)
    s.type_in("SciForgeSim_magnitude", "0.1 MPa")


def b_ok():
    took = timed("Pressure OK", s.ok)
    h.check("B OK: %.2f s" % took, took < 10.0)
    h.check("B the light is green", s.light() == "green", s.light())


# -- C ------------------------------------------------------------------------------------------
def c_solve():
    h.ribbon("Solve")


def c_go():
    dialog = s.solve_dialog()
    if h.check("C the Solve dialog", dialog is not None):
        state["beat"] = Heartbeat()
        state["t_solve"] = time.time()
        s.click_widget(dialog.go)


def c_done():
    took = time.time() - state["t_solve"]
    worst = state["beat"].stop()
    state["times"]["solve"] = took
    state["times"]["longest pause during the solve"] = worst
    from sciforge import simulation_solve_dialog

    results = simulation_solve_dialog.last_results()
    h.check("C solved: %.1f s" % took, any(r[0] == "done" for r in results.values()), results)
    info = s.sim().mesh_summary(s.active_study()) or {}
    state["nodes"] = info.get("nodes")
    h.check("C the mesh: %s nodes, %s elements" % (info.get("nodes"), info.get("elements")), True)
    h.check("C the window answered all along (longest pause %.2f s)" % worst, worst < 10.0, worst)
    s.close_popup("SciForgeSimJobStatus")  # (the progress window, Esc)


# -- D ------------------------------------------------------------------------------------------
def d_stress():
    took = timed("RESULTS: Stress", lambda: rs.choose_result("Stress"))
    h.check("D Stress drawn: %.2f s" % took, took < 5.0)


def d_probes():
    took = timed("RESULTS: Surface Probes opens", lambda: rs.big("Surface Probes"))
    h.check("D Surface Probes opens: %.2f s" % took, took < 5.0)


def d_probe_click():
    sess = rs.session()
    node = sess.display.nodes.tolist()[len(sess.display.nodes) // 3]
    took = timed(
        "RESULTS: a probe click", lambda: h.click(App.Vector(*sess.display.node_place(node)))
    )
    h.check("D a probe click: %.2f s" % took, len(rs.tags("probe")) == 1, rs.tags("probe"))
    h.task_button("Close")
    h.check("D Surface Probes closed", not Gui.Control.activeDialog())


def d_mesh():
    took = timed("RESULTS: Show Mesh on", lambda: rs.menu("DISPLAY", "Show Mesh"))
    h.check("D Show Mesh on: %.2f s" % took, took < 8.0)


def d_mesh_off():
    took = timed("RESULTS: Show Mesh off", lambda: rs.menu("DISPLAY", "Show Mesh"))
    h.check("D Show Mesh off: %.2f s" % took, took < 8.0)


def d_slice():
    took = timed("RESULTS: Slice Plane opens", lambda: rs.big("Slice Plane"))
    h.check("D Slice Plane opens and cuts: %.2f s" % took, took < 10.0)


def d_slice_ok():
    took = timed("RESULTS: Slice Plane OK", lambda: h.task_button("OK"))
    h.check("D Slice Plane OK: %.2f s" % took, took < 10.0)


def d_slice_remove():
    rs.big("Slice Plane")


def d_slice_removed():
    button = s.panel_field("SciForgeSimSliceRemove", QtWidgets.QPushButton)
    if button is not None:
        took = timed("RESULTS: Remove Slice", lambda: rs.click_widget(button))
        h.check("D Remove Slice: %.2f s" % took, took < 10.0)
    elif s.task_panel() is not None:
        h.task_button("Cancel")


def d_animate():
    state["beat"] = Heartbeat()
    took = timed("RESULTS: Animate on", lambda: rs.big("Animate"))
    h.check("D Animate starts: %.2f s" % took, took < 10.0)


def d_animate_off():
    worst = state["beat"].stop()
    state["times"]["longest pause while animating"] = worst
    took = timed("RESULTS: Animate off", lambda: rs.big("Animate"))
    h.check("D Animate stops: %.2f s (longest pause while it played %.2f s)" % (took, worst), True)


def d_report():
    rs.big("Report")


def d_report_save():
    dialog = rs.dialog("SciForgeSimReport")
    if not h.check("D the Report dialog", dialog is not None):
        return
    path = os.path.join(tempfile.mkdtemp(prefix="sciforge-speed-"), "plate.html")
    state["report"] = path
    from SciForgeTests.gui import dialog_input as ui

    ui.type_into(dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath"), path)
    took = timed(
        "RESULTS: Report saved",
        lambda: rs.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave")),
    )
    h.check("D Report saved: %.2f s" % took, os.path.isfile(path), path)


def summary():
    for name, took in state["times"].items():
        print("[SciForge] sim_qa_speed time: %s %.2f s" % (name, took), flush=True)
    h.check("times: %s" % ", ".join("%s %.2f s" % kv for kv in state["times"].items()), True)


h.run(
    "sim_qa_speed",
    [
        setup,
        a_enter,
        a_create,
        b_constraint,
        b_pick,
        b_preview,
        b_load,
        b_pressure,
        b_top,
        b_top_value,
        b_ok,
        c_solve,
        c_go,
        s.wait_solved("wait_solved", 900),
        c_done,
        d_stress,
        d_probes,
        d_probe_click,
        d_mesh,
        d_mesh_off,
        d_slice,
        d_slice_ok,
        d_slice_remove,
        d_slice_removed,
        d_animate,
        d_animate_off,
        d_report,
        d_report_save,
        summary,
    ],
    paced_by="state",
)

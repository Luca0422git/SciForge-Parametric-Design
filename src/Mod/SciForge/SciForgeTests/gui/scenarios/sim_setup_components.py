# SPDX-License-Identifier: LGPL-2.1-or-later
"""An empty design and a design of components in the SIMULATION workspace (builder sim-ui),
with real clicks.

A  An empty design: Workspace > Simulation, Create Study: the study is made, the pre-check is
   red with "The study has no solid body to simulate."; Structural Loads finds nothing to pick
   and OK says it needs a pick; Esc.
B  A design of two components moved away from the origin (a plate component and a post
   component standing on it). Workspace > Simulation, Create Study.
C  Structural Constraints: a click on a face of the plate (inside its moved component) picks
   it; OK.
D  Structural Loads: a click on the post's top face (inside the other component); 300 N; OK.
E  Solve: done; both bodies have results (glued where the post stands on the plate); the
   glyphs stand where the components are (moved).
F  Clone Study; in the clone the Fixed holds only one straight edge of the plate (the model
   can still turn about it). Solve: no meaningless numbers are shown as results: the progress
   says the model is not held enough, and the RESULTS tab does not take over.
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simsetup_steps as s

V = App.Vector
state = {}


# -- A ------------------------------------------------------------------------------------------
def a_empty():
    Gui.activateWorkbench("SciForgeWorkbench")
    App.newDocument("SimEmpty")
    h.fit()
    s.workspace("Simulation")


def a_create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


def a_check():
    h.check("the study is made", len(s.studies()) == 1)
    h.check("pre-check red", s.light() == "red", s.light())
    from sciforge import simulation_ui

    _state, checks = simulation_ui.precheck_state(s.active_study())
    texts = [t for _l, t in checks]
    h.check("it says there is no body", any("no solid body" in t for t in texts), texts)
    h.ribbon("Structural Loads")


def a_ok():
    if not h.check("Structural Loads opened", s.item_panel() is not None):
        return
    s.ok()


def a_refused():
    p = s.item_panel()
    h.check("OK refused: still open", p is not None)
    h.check("it says a pick is needed", "needs at least one pick" in s.message(), s.message())
    s.esc()


def a_closed():
    h.check("Esc closed it", s.item_panel() is None)
    h.check("nothing made", not s.items())


# -- B ------------------------------------------------------------------------------------------
def b_design():
    from sciforge import components

    doc = App.newDocument("SimParts")
    plate_part = components.new_component(doc, "Plate")
    plate_body = components.new_body_in(doc, plate_part, "Body1")
    box = plate_body.newObject("PartDesign::AdditiveBox", "PlateBox")
    box.Length, box.Width, box.Height = 80.0, 50.0, 8.0
    plate_body.Tip = box
    post_part = components.new_component(doc, "Post")
    # (named apart: sim-core's result summary keys bodies by name, and two components'
    # first bodies are both "Body1" in Fusion's numbering: reported to sim-core)
    post_body = components.new_body_in(doc, post_part, "Post Body")
    post = post_body.newObject("PartDesign::AdditiveBox", "PostBox")
    post.Length, post.Width, post.Height = 20.0, 20.0, 30.0
    post.Placement.Base = V(30, 15, 8)
    post_body.Tip = post
    # both components moved: the study works in design coordinates
    plate_part.Placement.Base = V(100, 50, 0)
    post_part.Placement.Base = V(100, 50, 0)
    doc.recompute()
    state["plate"] = plate_body.Name
    state["post"] = post_body.Name
    h.fit()


def b_enter():
    h.check("the new design shows DESIGN", s.tab_visible("solid"))
    s.workspace("Simulation")


def b_create():
    dialog = s.new_study_dialog()
    if h.check("New Study opened", dialog is not None):
        s.click_widget(dialog.create_button)


def body(key):
    return App.ActiveDocument.getObject(state[key])


def global_face(b, test):
    from sciforge import bodies

    shape = bodies.global_shape(b)
    for i, face in enumerate(shape.Faces, 1):
        if test(face):
            return "Face%d" % i
    return None


def click_global(b, face_name):
    """Click a face of a body inside a moved component (aimed at its global place)."""
    from sciforge import bodies

    face = bodies.global_shape(b).getElement(face_name)
    tip = b.Tip
    for point in s._face_points(face):
        hit = h.under_mouse(point)
        if hit and hit[1] == face_name and hit[0] in (tip.Name, b.Name):
            h.click(point)
            return True
    h.check("face %s of %s can be clicked" % (face_name, b.Label), False)
    return False


# -- C ------------------------------------------------------------------------------------------
def c_constraint():
    h.check("the study made", len(s.studies()) == 1)
    h.ribbon("Structural Constraints")


def c_pick():
    plate = body("plate")
    names = s.side_faces(plate)
    face = None
    for name in names:
        if name == global_face(
            plate, lambda f: abs(f.BoundBox.ZMax - 8.0) < 1e-6 and abs(f.BoundBox.ZMin - 8.0) < 1e-6
        ):
            continue  # not the top: the post stands there
        from sciforge import bodies

        f = bodies.global_shape(plate).getElement(name)
        if any(h.under_mouse(p) and h.under_mouse(p)[1] == name for p in s._face_points(f)):
            face = name
            break
    state["plate_face"] = face
    if h.check("a side face of the plate is visible", face is not None):
        click_global(plate, face)


def c_ok():
    p = s.item_panel()
    if p is not None:
        h.check(
            "picked on the plate",
            [(b.Name, sub) for b, sub in p.picks] == [(state["plate"], state.get("plate_face"))],
            p.picks,
        )
    s.ok()


# -- D ------------------------------------------------------------------------------------------
def d_load():
    h.check("Fixed 1 made", [i.Label for i in s.items()] == ["Fixed 1"])
    h.ribbon("Structural Loads")


def d_pick():
    post = body("post")
    face = global_face(
        post, lambda f: abs(f.BoundBox.ZMin - 38.0) < 1e-6 and abs(f.BoundBox.ZMax - 38.0) < 1e-6
    )
    state["post_top"] = face
    click_global(post, face)
    s.type_in("SciForgeSim_magnitude", "300")
    s.ok()


# -- E ------------------------------------------------------------------------------------------
def e_solve():
    h.check("Force 1 made", [i.Label for i in s.items("load")] == ["Force 1"])
    counts = s.glyph_counts()
    h.check("glyphs drawn for both", len(counts) == 2 and all(counts.values()), counts)
    h.ribbon("Solve")


def e_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def e_check():
    summary = s.sim().summary(s.active_study())
    h.check("solved", bool(summary))
    h.check("both bodies have results", len(summary.get("bodies", {})) == 2, summary.get("bodies"))
    disp = summary.get("stats", {}).get("displacement", {})
    at = disp.get("max_at") or [0, 0, 0]
    h.check("the largest movement is where the components are (x > 100)", at[0] > 100.0, at)
    s.close_popup("SciForgeSimJobStatus")


# -- F ------------------------------------------------------------------------------------------
def f_clone():
    s.right_click_row("Study 1 - Static Stress", "Clone Study")


def f_edit():
    h.check(
        "SETUP in front for the clone (no results)", s.current_tab() == "sim_setup", s.current_tab()
    )
    clone = s.active_study()
    h.check("the clone is active", clone is not None and clone.Label.startswith("Study 2"))
    fixed = [i for i in s.items("constraint")]
    if h.check("its Fixed", len(fixed) == 1):
        state["fixed"] = fixed[0].Label
        s.double_click_row(fixed[0].Label)


def f_edge():
    p = s.item_panel()
    if not h.check("Edit Constraint opened", p is not None):
        return
    s.click_widget(p.select.clear)
    from sciforge import bodies

    plate = body("plate")
    shape = bodies.global_shape(plate)
    edge = None
    for e in shape.Edges:
        mid = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
        if abs(mid.z - 8.0) < 1e-6 and "Line" in e.Curve.TypeId and abs(mid.y - 50.0) < 1e-6:
            edge = mid
            break
    if h.check("a top edge of the plate", edge is not None):
        h.click_edge(edge)


def f_ok():
    p = s.item_panel()
    if p is not None:
        kinds = [sub[:4] for _b, sub in p.picks]
        h.check("one edge picked", kinds == ["Edge"], p.picks)
    s.ok()


def f_solve():
    h.ribbon("Solve")


def f_go():
    dialog = s.solve_dialog()
    if h.check("Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def f_check():
    status = s.status_dialog()
    text = status.message.text() if status is not None else ""
    h.check("it says the model is not held enough", "not held enough" in text, text)
    h.check("the RESULTS tab did not take over", s.current_tab() == "sim_setup", s.current_tab())
    s.close_popup("SciForgeSimJobStatus")


h.run(
    "sim_setup_components",
    [
        a_empty,
        a_create,
        a_check,
        a_ok,
        a_refused,
        a_closed,
        b_design,
        b_enter,
        b_create,
        c_constraint,
        c_pick,
        c_ok,
        d_load,
        d_pick,
        e_solve,
        e_go,
        s.wait_solved(),
        e_check,
        f_clone,
        f_edit,
        f_edge,
        f_ok,
        f_solve,
        f_go,
        s.wait_solved("wait_loose"),
        f_check,
    ],
)

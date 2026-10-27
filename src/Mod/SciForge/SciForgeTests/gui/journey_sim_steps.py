# SPDX-License-Identifier: LGPL-2.1-or-later
"""The SIMULATION journey (scenarios/journey_sim_bracket*.py, sim QA): an L-bracket for a robot,
designed and checked the way Luca would, only with real clicks and keys (code only reads the
results). Not a scenario (kept outside scenarios/).

The design (every number worked out by hand):
  Sketch on the front (XZ) plane, one closed line chain (grid 1 mm):
      (0,0) (60,0) (60,5) (5,5) (5,40) (0,40) back to (0,0); the arm's top line dimensioned 5.
      Profile area = 60 x 5 + 5 x 35 = 475 mm2.
  Extrude 40: V0 = 475 x 40 = 19000 mm3. Base plate 60 x 40 x 5, upright arm 5 thick, 40 high.
  Two bolt holes, Hole tool, diameter 6, through all, on the base's top face at x = 40, 10 mm
      either side of the middle: each removes pi x 3^2 x 5 = 141.372 mm3.
  Fillet radius 3 on the inside corner (the edge where the arm meets the base, 40 long): adds
      (r^2 - pi r^2 / 4) x 40 = (9 - 7.0686) x 40 = 77.256 mm3.
  V1 = 19000 - 282.743 + 77.256 = 18794.51 mm3.
  Physical material PLA (FreeCAD's PLA-Generic card): density 1240 kg/m3 -> 23.31 g,
      E = 3640 MPa, Poisson 0.36, yield strength 35.9 MPa (safety basis "Yield Strength").

The study: Fixed on the two hole walls; Force 50 N on the arm's top face (5 x 40 at z = 40),
  pointing across the arm (Direction Type Vector, Fx = -50 N: away from the holes).
  Why across and not straight down: down on an upright arm only squeezes it (F / A = 50 / 200 =
  0.25 MPa, and its thickness would hardly matter); a shelf bracket is loaded across its arm,
  which is what the hand formula M c / I is for (the bracket screwed to a wall: "down").

Hand estimates (beam theory):
  Arm bending at height z (above the base's top z = 5): M(z) = 50 (40 - z) N mm, the arm's
      section b = 40 (along Y), t = 5: I = b t^3 / 12 = 416.7 mm4, c = t / 2, sigma = M c / I =
      6 M / (b t^2). On the outer face (x = 0) at z = 15: M = 1250 N mm, sigma = 7.50 MPa.
      The probe reads von Mises at the node clicked; the band is 0.80 .. 1.10 of 6 M / (b t^2)
      at that node's height because: the arm is a wide plate (b / t = 8) so across most of its
      width the sideways stress nu sigma comes in (plane strain: von Mises = sigma
      sqrt(1 - nu + nu^2) = 0.88 sigma for nu = 0.36; 1.00 at the side edges), and a node's
      value is the mesh's average around it (second-order elements, about 2 mm here).
  Thicker arm (the timeline edit 5 -> 7): at the same height the stress drops as
      (t1 / t2)^2 = (5 / 7)^2 = 0.510 (band 0.45 .. 0.58: the node picked is the nearest one,
      the mesh differs a little).
  Base plate: the sideways force acts 37.5 mm above the plate's middle: M = 50 x 37.5 = 1875
      N mm all the way from the arm to the bolts; 6 M / (b h^2) = 11.25 MPa over the full 40 mm
      width, 16.1 MPa across the bolt line (40 - 2 x 6 = 28 mm left): the highest von Mises is
      there, raised by the holes (a hole in a bent plate roughly doubles it) and by the hole
      walls held rigid: expected 12 .. 60 MPa. It does not change with the arm's thickness.
  Safety factor = 35.9 MPa / highest von Mises (checked exactly against the numbers shown).
  Arm tip sideways movement: the arm alone F L^3 / (3 E I) = 50 x 35^3 / (3 x 3640 x 416.7) =
      0.47 mm, plus the base plate turning under M between the arm and the bolts (about
      M L / (E I) = 1875 x 35 / (3640 x 416.7) = 0.043 rad, x 37.5 mm = 1.6 mm): about 2.1 mm,
      less where the wide plate is stiffer: band 1.0 .. 3.2 mm.
  Reaction at the holes: exactly 50 N (along +X), whatever the mesh.
"""

import math
import os
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from SciForgeTests.gui import arrow_input as ai
from SciForgeTests.gui import bodies_steps as bs
from SciForgeTests.gui import harness as h
from SciForgeTests.gui import plane_input as pl
from SciForgeTests.gui import simres_steps as rs
from SciForgeTests.gui import simsetup_steps as ss
from SciForgeTests.gui import sketch_input as si
from SciForgeTests.gui import widget_input as w

V = App.Vector
S = {}

PROFILE = [(0, 0), (60, 0), (60, 5), (5, 5), (5, 40), (0, 40)]
AREA = 60 * 5 + 5 * 35  # 475
V0 = AREA * 40.0  # 19000
HOLE_D = 6.0
HOLE = math.pi * (HOLE_D / 2) ** 2 * 5.0  # 141.372
FILLET_R = 3.0
FILLET = (FILLET_R**2 - math.pi * FILLET_R**2 / 4.0) * 40.0  # 77.256
V1 = V0 - 2 * HOLE + FILLET  # 18794.51
PLA_DENSITY = 1.24e-3  # g / mm3
PLA_YIELD = 35.9
PLA_E = 3640.0
FORCE = 50.0
ARM_W = 40.0  # the arm's width along Y


def arm_sigma(z, t):
    """6 M / (b t^2) for the arm at height z (the force at z = 40)."""
    return 6.0 * FORCE * (40.0 - z) / (ARM_W * t * t)


def plate_sigma_full():
    return 6.0 * FORCE * 37.5 / (40.0 * 25.0)  # 11.25


def tip_estimate(t=5.0):
    i_arm = ARM_W * t**3 / 12.0
    arm = FORCE * 35.0**3 / (3 * PLA_E * i_arm)
    i_plate = 40.0 * 125.0 / 12.0
    turn = FORCE * 37.5 * 35.0 / (PLA_E * i_plate) * 37.5
    return arm + turn


def near(a, b, tol):
    return abs(a - b) <= tol


def step(fn, name, wait_ms=None):
    fn.__name__ = name
    if wait_ms is not None:
        fn.wait_ms = wait_ms
    return fn


def doc():
    return App.ActiveDocument


def body():
    return h.body()


def shape():
    b = body()
    return b.Shape if b is not None else None


def ymid():
    return S.get("ymid", -20.0)


def faces_where(test):
    sh = shape()
    out = []
    if sh is None:
        return out
    for i, f in enumerate(sh.Faces, 1):
        try:
            if test(f):
                out.append("Face%d" % i)
        except Exception:
            pass
    return out


def hole_walls():
    """The two bolt-hole walls: cylinders along Z (the fillet is a cylinder along Y)."""
    return faces_where(
        lambda f: "Cylinder" in f.Surface.TypeId
        and abs(abs(f.Surface.Axis.z) - 1.0) < 1e-6
        and abs(f.Surface.Radius - HOLE_D / 2) < 1e-6
    )


def arm_top():
    found = faces_where(
        lambda f: "Plane" in f.Surface.TypeId
        and abs(f.BoundBox.ZMin - 40.0) < 1e-6
        and abs(f.BoundBox.ZMax - 40.0) < 1e-6
    )
    return found[0] if found else None


def arm_thickness():
    """The arm's top face width along X (5, then 7 after the edit)."""
    name = arm_top()
    if name is None:
        return None
    return shape().getElement(name).BoundBox.XLength


# -- 1. the design -----------------------------------------------------------------------------
def design_steps(name):
    def new_design():
        from sciforge import grid_ui

        Gui.activateWorkbench("SciForgeWorkbench")
        App.newDocument(name)
        S.clear()
        S["doc"] = doc().Name
        grid_ui.put("Subdivisions", 10)  # 1 mm minor lines: the corners are on whole mm
        grid_ui.apply_subdivisions()
        h.fit()

    def create_sketch():
        h.ribbon("Create Sketch")

    def pick_front_plane():
        pl.click_square("XZ_Plane")

    def sketch_open():
        sk = h.in_sketch()
        S["sk"] = sk.Name if sk is not None else None
        h.check("1 a sketch opens on the front plane", sk is not None)
        h.press("l")

    def corner(k):
        def click():
            x, z = PROFILE[k % len(PROFILE)]
            si.click(V(x, 0, z))

        return step(click, "line_corner_%d" % k)

    def chain_done():
        h.press(QtCore.Qt.Key_Escape)
        sk = doc().getObject(S["sk"])
        lines = si.lines(sk)
        h.check("1 six lines in one chain", len(lines) == 6, len(lines))
        from sciforge import sketch_mode

        session = sketch_mode.current()
        h.check(
            "1 the L is one closed profile",
            session is not None and session.shading.count == 1,
            session.shading.count if session is not None else None,
        )

    def dim_key():
        h.press("d")

    def dim_arm_line():
        si.click(V(2.5, 0, 40))  # the arm's top line

    def dim_arm_place():
        si.click(V(2.5, 0, 47))

    def dim_arm_type():
        si.type_text("5")

    def dim_base_line():
        si.click(V(60, 0, 2.5))  # the base's end line

    def dim_base_place():
        si.click(V(67, 0, 2.5))

    def dim_base_type():
        si.type_text("5")

    def dim_done():
        h.press(QtCore.Qt.Key_Escape)
        sk = doc().getObject(S["sk"])
        dims = [
            i
            for i, c in enumerate(sk.Constraints)
            if c.Type in ("Distance", "DistanceX", "DistanceY") and near(c.Value, 5.0, 1e-9)
        ]
        h.check(
            "1 two dimensions of 5 (arm and base)", len(dims) == 2, [c.Type for c in sk.Constraints]
        )
        arm = [
            i for i in dims if abs(sk.Geometry[sk.Constraints[i].First].StartPoint.y - 40.0) < 1e-6
        ]
        h.check("1 one of them is the arm's top line", len(arm) == 1, dims)
        S["dim"] = arm[0] if arm else None
        lines = si.lines(sk)
        xs = sorted({round(c, 6) for _, g in lines for c in (g.StartPoint.x, g.EndPoint.x)})
        ys = sorted({round(c, 6) for _, g in lines for c in (g.StartPoint.y, g.EndPoint.y)})
        h.check("1 the corners where they were drawn (x 0, 5, 60)", xs == [0, 5, 60], xs)
        h.check("1 the corners where they were drawn (z 0, 5, 40)", ys == [0, 5, 40], ys)

    def finish_sketch():
        h.ribbon("Finish Sketch")

    def extrude():
        h.check("1 out of the sketch", h.in_sketch() is None)
        h.fit()
        h.press("e")

    def extrude_distance():
        h.check("2 the Extrude dialog", ai.give_distance("40"))

    def extrude_ok():
        h.task_button("OK")

    def extruded():
        v = h.solid_volume()
        h.check("2 V = 475 x 40 = 19000 mm3", near(v, V0, 1e-6), v)
        bb = shape().BoundBox
        h.check(
            "2 60 x 40 x 40 box",
            near(bb.XLength, 60, 1e-6)
            and near(bb.YLength, 40, 1e-6)
            and near(bb.ZLength, 40, 1e-6),
            bb,
        )
        S["ymid"] = (bb.YMin + bb.YMax) / 2.0
        S["holes_at"] = [V(40, ymid() - 10, 5), V(40, ymid() + 10, 5)]

    steps = [
        step(new_design, "new_design"),
        step(create_sketch, "create_sketch"),
        step(pick_front_plane, "pick_front_plane"),
        step(sketch_open, "sketch_open"),
    ]
    steps += [corner(k) for k in range(len(PROFILE) + 1)]
    steps += [
        step(chain_done, "chain_done"),
        step(dim_key, "dim_key"),
        step(dim_arm_line, "dim_arm_line"),
        step(dim_arm_place, "dim_arm_place"),
        step(dim_arm_type, "dim_arm_type"),
        step(dim_base_line, "dim_base_line"),
        step(dim_base_place, "dim_base_place"),
        step(dim_base_type, "dim_base_type"),
        step(dim_done, "dim_done"),
        step(finish_sketch, "finish_sketch"),
        step(extrude, "extrude"),
        step(extrude_distance, "extrude_distance"),
        step(extrude_ok, "extrude_ok"),
        step(extruded, "extruded"),
    ]
    for k in (0, 1):
        steps += hole_steps(k)
    steps += fillet_steps() + material_steps()
    return steps


def hole_panel():
    from SciForgeTests.gui import hole_steps

    return hole_steps.hole_panel()


def hole_steps(k):
    def start():
        Gui.Selection.clearSelection()
        h.fit()
        h.ribbon("Hole")

    def click_base():
        p = hole_panel()
        h.check("3 hole %d: the Hole dialog waits for a face" % (k + 1), p is not None)
        h.click(S["holes_at"][k])

    def place_x():
        from sciforge import hole

        from SciForgeTests.gui import hole_steps as hs

        p = hole_panel()
        if not h.check("3 hole %d previewed" % (k + 1), p is not None and p.target is not None):
            return
        sketch = hole.helper_sketch(p.target)
        local = sketch.getGlobalPlacement().inverse().multVec(S["holes_at"][k])
        S["hole_local"] = local
        hs.type_into(p.pos_x.widget, "%.3f" % local.x)

    def place_y():
        from SciForgeTests.gui import hole_steps as hs

        p = hole_panel()
        if p is not None and "hole_local" in S:
            hs.type_into(p.pos_y.widget, "%.3f" % S["hole_local"].y)

    def diameter():
        from SciForgeTests.gui import hole_steps as hs

        p = hole_panel()
        if p is not None:
            hs.type_into(p.diameter.widget, "6")

    def through():
        from SciForgeTests.gui import blend_steps

        p = hole_panel()
        if p is not None:
            blend_steps.choose(p.extent, "All")

    def ok():
        h.task_button("OK")

    def made():
        from SciForgeTests.gui import hole_steps as hs

        expect = V0 - (k + 1) * HOLE
        v = h.solid_volume()
        h.check(
            "3 hole %d through the 5 mm base: V = %.2f" % (k + 1, expect), near(v, expect, 1e-3), v
        )
        holes = hs.holes()
        if holes:
            c = hs.centre_of(holes[-1])
            h.check(
                "3 hole %d at x 40, 10 mm from the middle" % (k + 1),
                c is not None and (c - S["holes_at"][k]).Length < 1e-3,
                c,
            )

    return [
        step(start, "hole%d_start" % k),
        step(click_base, "hole%d_click" % k),
        step(place_x, "hole%d_x" % k),
        step(place_y, "hole%d_y" % k),
        step(diameter, "hole%d_diameter" % k),
        step(through, "hole%d_through" % k),
        step(ok, "hole%d_ok" % k),
        step(made, "hole%d_made" % k),
    ]


def fillet_steps():
    def start():
        Gui.Selection.clearSelection()
        h.fit()
        h.ribbon("Fillet")

    def click_corner():
        h.click_edge(V(5, ymid(), 5))

    def radius():
        from SciForgeTests.gui import blend_steps as b

        p = b.blend_panel()
        h.check("4 the inside corner picked", p is not None and len(p.refs) == 1, p and p.refs)
        if p is not None:
            b.type_into(p.radius.widget, "3")

    def ok():
        h.task_button("OK")

    def made():
        v = h.solid_volume()
        h.check("4 fillet r 3 adds (9 - 9 pi / 4) x 40: V = %.2f" % V1, near(v, V1, 1e-3), v)

    return [
        step(start, "fillet_start"),
        step(click_corner, "fillet_click"),
        step(radius, "fillet_radius"),
        step(ok, "fillet_ok"),
        step(made, "fillet_made"),
    ]


def material_steps():
    def start():
        h.click_empty()
        h.fit()
        bs.menu("MODIFY", "Physical Material")

    def pick_pla():
        p = bs.panel()
        if not h.check(
            "5 the Physical Material dialog", p is not None and p.title == "Physical Material"
        ):
            return
        item = p.item_for("PLA")
        if h.check("5 the library has PLA", item is not None):
            p.library.scrollToItem(item)
            w.click(p.library.viewport(), p.library.visualItemRect(item).center())

    def click_body():
        h.click(V(50, ymid(), 5))  # the base's top face, past the holes

    def ok():
        h.task_button("OK")

    def made():
        from sciforge import material

        b = body()
        h.check("5 the body is PLA", b.ShapeMaterial.Name == "PLA-Generic", b.ShapeMaterial.Name)
        # (the mass the dialog shows: material.mass; bodies.mass reads the body's own material
        # object, which marks the body as changed)
        grams = material.mass(b) * 1000.0
        h.check(
            "5 its mass 18794.5 mm3 x 1.24 g/cm3 = 23.31 g",
            near(grams, V1 * PLA_DENSITY, 0.01),
            grams,
        )

    return [
        step(start, "material_start"),
        step(pick_pla, "material_pla"),
        step(click_body, "material_body"),
        step(ok, "material_ok"),
        step(made, "material_made"),
    ]


# -- 2. the study ---------------------------------------------------------------------------------
def study_steps():
    def enter():
        ss.workspace("Simulation")

    def create():
        dialog = ss.new_study_dialog()
        h.check("6 New Study opens by itself", dialog is not None)
        ss.click_widget(dialog.create_button if dialog is not None else None)

    def materials():
        h.check("6 a study", len(ss.studies()) == 1, ss.studies())
        h.ribbon("Study Materials")

    def materials_check():
        p = ss.task_panel()
        if not h.check("7 Study Materials opens", p is not None and p.title == "Study Materials"):
            return
        table = p.table
        h.check("7 one row: the bracket", table.rowCount() == 1, table.rowCount())
        model = table.item(0, 2).text() if table.rowCount() else ""
        h.check("7 its model material is PLA (not FreeCAD's PLA-Generic)", model == "PLA", model)
        combo = p.combos[0] if p.combos else None
        h.check(
            "7 the study material is Same as Model",
            combo is not None and combo.currentData() is None,
            combo.currentText() if combo else None,
        )
        h.check("7 the safety factor uses the yield strength", p.basis.currentData() == "yield")
        text = p.props.text()
        S["props"] = text
        h.check("7 PLA's yield strength 35.9 MPa shown", "35.9" in text, text)
        h.check("7 its Young's modulus 3640 MPa shown", "3640" in text or "3.64" in text, text)

    def materials_close():
        ss.cancel()

    def constraint():
        h.check("7 Study Materials closed", ss.task_panel() is None)
        h.ribbon("Structural Constraints")

    def pick_holes():
        p = ss.item_panel()
        if not h.check("8 Structural Constraints opens", p is not None):
            return
        h.check("8 Fixed by default", p.type_box.currentText() == "Fixed", p.type_box.currentText())
        S["walls"] = hole_walls()
        h.check("8 two hole walls", len(S["walls"]) == 2, S["walls"])
        for face in S["walls"]:
            ss.click_face(body(), face)

    def constraint_ok():
        p = ss.item_panel()
        if p is not None:
            picked = sorted(sub for _b, sub in p.picks)
            h.check("8 both hole walls picked", picked == sorted(S["walls"]), picked)
        ss.ok()

    def load():
        found = ss.items("constraint")
        h.check("8 Fixed 1", [i.Label for i in found] == ["Fixed 1"], [i.Label for i in found])
        h.ribbon("Structural Loads")

    def pick_arm():
        p = ss.item_panel()
        if not h.check("9 Structural Loads opens", p is not None):
            return
        h.check("9 Force by default", p.type_box.currentText() == "Force")
        S["top"] = arm_top()
        ss.click_face(body(), S["top"])

    def vector():
        ss.choose("SciForgeSim_direction", "Vector")

    def components():
        ss.type_in("SciForgeSim_fx", "-50 N")
        ss.type_in("SciForgeSim_fy", "0")
        ss.type_in("SciForgeSim_fz", "0")

    def load_ok():
        p = ss.item_panel()
        if p is not None:
            h.check("9 the arm's top picked", [sub for _b, sub in p.picks] == [S["top"]], p.picks)
        ss.ok()

    def load_check():
        found = ss.items("load")
        h.check("9 Force 1", [i.Label for i in found] == ["Force 1"], [i.Label for i in found])
        if found:
            data = ss.sim().item_data(found[0])
            opts = data["options"]
            h.check("9 50 N", near(opts.get("magnitude", 0), 50.0, 1e-9), opts)
            vec = opts.get("vector") or [0, 0, 0]
            h.check("9 along -X", near(vec[0], -1.0, 1e-9) and near(vec[2], 0.0, 1e-9), opts)

    def precheck():
        h.ribbon("Pre-check")

    def precheck_check():
        h.check("10 Pre-check light green", ss.light() == "green", ss.light())
        dialog = ss.popup_named("SciForgeSimPrecheck")
        if h.check("10 the Pre-check list", dialog is not None):
            texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
            S["precheck"] = texts
            h.check("10 ready to solve", dialog.state == "green", texts)
            ss.close_popup("SciForgeSimPrecheck")

    def solve():
        h.ribbon("Solve")

    def solve_go():
        dialog = ss.solve_dialog()
        if h.check("11 the Solve dialog", dialog is not None):
            h.check("11 Solve 1 Study", dialog.go.text() == "Solve 1 Study", dialog.go.text())
            ss.click_widget(dialog.go)
            S["solve_started"] = __import__("time").time()

    def solved():
        study = ss.active_study()
        from sciforge import simulation_solve_dialog

        results = simulation_solve_dialog.last_results()
        h.check("11 the solve ended done", results.get(study.Name, ("?",))[0] == "done", results)
        h.check("11 the RESULTS tab shows", ss.current_tab() == "sim_results", ss.current_tab())
        h.check("11 not out of date", not ss.sim().out_of_date(study))
        h.check(
            "11 nothing of the solve in the undo history",
            not any("olve" in n for n in doc().UndoNames),
            doc().UndoNames,
        )
        S["solve_seconds"] = __import__("time").time() - S.get("solve_started", 0)
        ss.close_popup("SciForgeSimJobStatus")  # (the progress window, Esc)

    return [
        step(enter, "sim_enter"),
        step(create, "sim_create"),
        step(materials, "sim_materials"),
        step(materials_check, "sim_materials_check"),
        step(materials_close, "sim_materials_close"),
        step(constraint, "sim_constraint"),
        step(pick_holes, "sim_pick_holes"),
        step(constraint_ok, "sim_constraint_ok"),
        step(load, "sim_load"),
        step(pick_arm, "sim_pick_arm"),
        step(vector, "sim_vector"),
        step(components, "sim_components"),
        step(load_ok, "sim_load_ok"),
        step(load_check, "sim_load_check"),
        step(precheck, "sim_precheck"),
        step(precheck_check, "sim_precheck_check"),
        step(solve, "sim_solve"),
        step(solve_go, "sim_solve_go"),
        ss.wait_solved(),
        step(solved, "sim_solved"),
    ]


# -- 3. the results ------------------------------------------------------------------------------
def node_near(point):
    sess = rs.session()
    pts = sess.data.points
    best = None
    for n in sess.display.nodes.tolist():
        d = sum((pts[n][k] - c) ** 2 for k, c in enumerate(point))
        if best is None or d < best[0]:
            best = (d, n)
    return best[1] if best else None


def probe_steps(tag, z=15.0):
    """Surface Probes on the arm's inner face (it faces the holes and the default view) at
    height z (10 mm above the base by default), half way across: von Mises read there."""

    def stress():
        rs.choose_result("Stress")

    def open_probes():
        h.check("%s results shown" % tag, rs.session() is not None)
        rs.big("Surface Probes")

    def click():
        sess = rs.session()
        t = arm_thickness() or 5.0
        S["%s_t" % tag] = t
        node = node_near((t, ymid(), z))
        S["%s_aim" % tag] = node
        h.click(V(*sess.display.node_place(node)))

    def read():
        sess = rs.session()
        probes = rs.tags("probe")
        if not h.check("%s one probe" % tag, len(probes) == 1, probes):
            return
        node = probes[0]["node"]
        x, y, z = (float(c) for c in sess.data.points[node])
        S["%s_z" % tag] = z
        S["%s_value" % tag] = probes[0]["value"]
        t = S["%s_t" % tag]
        h.check(
            "%s the probe is on the arm's inner face, 5 .. 25 mm above the base" % tag,
            abs(x - t) < 0.05 and 10.0 <= z <= 30.0 and abs(y - ymid()) < 12.0,
            (x, y, z, node, S["%s_aim" % tag]),
        )
        h.check("%s it reads von Mises in MPa" % tag, probes[0]["text"].endswith("MPa"), probes[0])
        vm = float(sess.data.values("von_mises")[node])
        h.check("%s the node's own value" % tag, near(probes[0]["value"], vm, 1e-9), (probes, vm))

    def close():
        h.task_button("Close")

    def closed():
        h.check("%s Surface Probes closed" % tag, not Gui.Control.activeDialog())
        h.check("%s no value left following the mouse" % tag, not rs.tags("hover"), rs.tags())

    return [
        step(stress, "%s_stress" % tag),
        step(open_probes, "%s_probes" % tag),
        step(click, "%s_probe_click" % tag),
        step(read, "%s_probe_read" % tag),
        step(close, "%s_probe_close" % tag),
        step(closed, "%s_probe_closed" % tag),
    ]


def results_steps(report_dir):
    def safety():
        sess = rs.session()
        if not h.check("12 results shown", sess is not None):
            return
        h.check("12 on the safety factor", sess.result == "safety", sess.result)
        stats = rs.summary().get("stats", {})
        S["vm_max"] = stats.get("von_mises", {}).get("max", 0.0)
        S["sf_min"] = stats.get("safety", {}).get("min", 0.0)
        S["disp_max"] = stats.get("displacement", {}).get("max", 0.0)
        sf = PLA_YIELD / S["vm_max"] if S["vm_max"] else 0.0
        h.check(
            "12 safety factor = 35.9 / highest von Mises (%.3f)" % sf,
            near(S["sf_min"], min(sf, 15.0), 1e-3 * max(1.0, sf)),
            (S["sf_min"], S["vm_max"]),
        )
        h.check(
            "12 the legend's lowest value is that safety factor",
            near(sess.legend_info["min"], S["sf_min"], 1e-6),
            sess.legend_info,
        )

    def vm():
        rs.choose_result("Stress")

    def vm_check():
        sess = rs.session()
        h.check(
            "13 the legend's highest stress is the summary's",
            near(sess.legend_info["max"], S["vm_max"], 1e-6),
            (sess.legend_info, S["vm_max"]),
        )
        h.check(
            "13 highest von Mises %.1f MPa within 12 .. 60 (base plate at the bolts, see the "
            "steps file)" % S["vm_max"],
            12.0 <= S["vm_max"] <= 60.0,
            S["vm_max"],
        )
        where = (rs.summary().get("stats", {}).get("von_mises", {}) or {}).get("max_at")
        S["vm_max_at"] = where
        h.check(
            "13 it is in the base plate (z <= 5), not up the arm",
            where is not None and where[2] <= 5.0 + 1e-6,
            where,
        )

    def disp():
        rs.choose_result("Displacement")

    def disp_check():
        sess = rs.session()
        est = tip_estimate()
        h.check(
            "14 largest movement %.2f mm within 1.0 .. 3.2 (hand estimate %.2f)"
            % (S["disp_max"], est),
            1.0 <= S["disp_max"] <= 3.2,
            S["disp_max"],
        )
        h.check(
            "14 the legend shows it",
            near(sess.legend_info["max"], S["disp_max"], 1e-6),
            sess.legend_info,
        )
        where = (rs.summary().get("stats", {}).get("displacement", {}) or {}).get("max_at")
        h.check("14 at the top of the arm", where is not None and where[2] > 35.0, where)

    def minmax():
        tags = rs.tags("max") + rs.tags("min")
        h.check("15 Show Min/Max tags on the model", len(tags) >= 2, rs.tags())

    def deformation_actual():
        rs.menu("DEFORMATION", "Actual")

    def deformation_check():
        sess = rs.session()
        h.check("16 Actual: true size", near(sess.factor(), 1.0, 1e-12), sess.factor())
        rs.menu("DEFORMATION", "Adjusted")

    def deformation_adjusted():
        sess = rs.session()
        bb = shape().BoundBox
        size = bb.DiagonalLength
        expect = 0.05 * size / S["disp_max"] if S["disp_max"] else 0
        h.check(
            "16 Adjusted: the largest movement drawn as 5 % of the part's size",
            near(sess.factor(), expect, 0.2 * expect),
            (sess.factor(), expect),
        )

    def report():
        rs.big("Report")

    def report_write():
        dialog = rs.dialog("SciForgeSimReport")
        if not h.check("17 the Report dialog", dialog is not None):
            return
        path = os.path.join(report_dir, "bracket-report.html")
        S["report"] = path
        field = dialog.findChild(QtWidgets.QLineEdit, "SciForgeSimReportPath")
        if h.check("17 its file field", field is not None):
            si.type_into(field, path, enter=False)
        ss.click_widget(dialog.findChild(QtWidgets.QPushButton, "SciForgeSimReportSave"))

    def report_check():
        path = S.get("report")
        ok = path and os.path.isfile(path)
        h.check("17 the report is written", ok, path)
        if not ok:
            return
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        h.check("17 it names PLA", ">PLA<" in text and "PLA-Generic" not in text)
        h.check(
            "17 what the constraint and load are on, in plain words",
            "2 faces" in text and "1 face" in text and "Face1" not in text,
        )
        flat = text.replace(" ", "").replace("\n", "")
        h.check(
            "17 the reaction 50 N along X, 0 and 0 (no rounding noise)",
            "<td>Fixed1</td><td>50</td><td>0</td><td>0</td><td>50</td>" in flat,
            flat[flat.find("<td>Fixed1</td><td>50") - 10 : flat.find("<td>Fixed1</td><td>50") + 90],
        )
        from sciforge import simulation_core as core

        sf = core.fmt(S["sf_min"], 4)
        h.check("17 it gives the safety factor %s" % sf, sf in text, S["sf_min"])
        h.check("17 and the reaction 50 N", "<td>50</td>" in text.replace(" ", ""), path)
        h.check("17 it lists Fixed 1 and Force 1", "Fixed 1" in text and "Force 1" in text)
        h.check("17 the dialog closed after Save", rs.dialog("SciForgeSimReport") is None)

    steps = [
        step(safety, "res_safety"),
        step(vm, "res_vm"),
        step(vm_check, "res_vm_check"),
        step(disp, "res_disp"),
        step(disp_check, "res_disp_check"),
        step(minmax, "res_minmax"),
        step(deformation_actual, "res_def_actual"),
        step(deformation_check, "res_def_check"),
        step(deformation_adjusted, "res_def_adjusted"),
    ]
    steps += probe_steps("p1")
    steps += [
        step(probe_check_first, "res_probe_check"),
        step(report, "res_report"),
        step(report_write, "res_report_write", 500),
        step(report_check, "res_report_check", 1500),
    ]
    return steps


def probe_check_first():
    z = S.get("p1_z")
    value = S.get("p1_value")
    if z is None or value is None:
        h.check("18 a probe value", False)
        return
    hand = arm_sigma(z, 5.0)
    h.check(
        "18 von Mises on the arm's inner face, z %.2f: %.2f MPa vs M c / I = %.2f (band 0.80 .. "
        "1.10)" % (z, value, hand),
        0.80 * hand <= value <= 1.10 * hand,
        (value, hand),
    )


def report_folder():
    return tempfile.mkdtemp(prefix="sciforge-journey-sim-")


def nothing_touched(tag):
    """The design needs no recompute (FreeCAD's "touched" mark on no object)."""

    def fn():
        found = [o.Label for o in doc().Objects if "Touched" in (o.State or [])]
        h.check("%s: the design needs no recompute" % tag, not found, found)

    fn.__name__ = "nothing_touched_" + tag.split()[0]
    return fn


# -- 4. a thicker arm, from the timeline ---------------------------------------------------------
T2 = 7.0
V2 = (60 * 5 + T2 * 35) * 40.0 - 2 * HOLE + FILLET  # 21594.51


def edit_steps():
    def to_design():
        stats = rs.summary().get("stats", {})
        S["vm1"] = stats.get("von_mises", {}).get("max", 0.0)
        S["disp1"] = stats.get("displacement", {}).get("max", 0.0)
        S["undo_before_edit"] = len(doc().UndoNames)
        ss.workspace("Design")

    def edit_sketch():
        h.check("19 back in DESIGN", ss.current_tab() == "solid", ss.current_tab())
        si.timeline_double_click("Sketch 1")

    def double_click_dimension():
        sk = h.in_sketch()
        if not h.check(
            "19 the sketch opens from the timeline", sk is not None and sk.Name == S["sk"]
        ):
            return
        point = si.dimension_label(sk, S["dim"])
        h.move(h.screen_point(point + V(2, 1, 0)))
        h.move(h.screen_point(point))
        h.double_click(point)

    def type_seven():
        from sciforge import sketch_mode

        session = sketch_mode.current()
        h.check("19 the dimension's box opens", session is not None and session.editor is not None)
        si.type_text("7")

    def finish():
        h.ribbon("Finish Sketch")

    def thicker():
        h.check("19 out of the sketch", h.in_sketch() is None)
        h.check("19 the arm is 7 thick", near(arm_thickness() or 0, T2, 1e-6), arm_thickness())
        v = h.solid_volume()
        h.check("19 V = (300 + 7 x 35) x 40 - holes + fillet = %.2f" % V2, near(v, V2, 1e-3), v)
        from SciForgeTests.gui import hole_steps as hs

        centres = sorted(
            (round(c.x, 6), round(c.y, 6)) for c in (hs.centre_of(x) for x in hs.holes()) if c
        )
        want = sorted((40.0, round(p.y, 6)) for p in S["holes_at"])
        h.check("19 the holes stayed at x 40", centres == want, (centres, want))
        h.check(
            "19 the fillet followed the corner",
            len(hole_walls()) == 2 and fillet_at(T2),
            shape().Faces,
        )

    def to_sim():
        ss.workspace("Simulation")

    def stale():
        study = ss.active_study()
        h.check("20 the study is out of date", ss.sim().out_of_date(study))
        labels = ss.browser_labels()
        h.check("20 the browser's Results row says so", "Results (out of date)" in labels, labels)
        h.ribbon("Solve")

    def solve_go():
        dialog = ss.solve_dialog()
        if h.check("20 the Solve dialog", dialog is not None):
            ss.click_widget(dialog.go)

    def solved():
        study = ss.active_study()
        from sciforge import simulation_solve_dialog

        results = simulation_solve_dialog.last_results()
        h.check("20 solved again", results.get(study.Name, ("?",))[0] == "done", results)
        h.check("20 up to date", not ss.sim().out_of_date(study))
        stats = rs.summary().get("stats", {})
        S["vm2"] = stats.get("von_mises", {}).get("max", 0.0)
        S["sf2"] = stats.get("safety", {}).get("min", 0.0)
        S["disp2"] = stats.get("displacement", {}).get("max", 0.0)
        h.check(
            "20 the highest stress stays in the base plate (%.2f then %.2f MPa: the arm does "
            "not carry it)" % (S["vm1"] or 0, S["vm2"]),
            S["vm1"] and 0.75 <= S["vm2"] / S["vm1"] <= 1.25,
            (S["vm1"], S["vm2"]),
        )
        h.check(
            "20 the arm moves less (%.3f mm, was %.3f)" % (S["disp2"], S["disp1"]),
            S["disp2"] < S["disp1"],
        )
        ss.close_popup("SciForgeSimJobStatus")  # (the progress window, Esc)
        h.check(
            "20 the edit is one undo step, the solve none",
            not any("olve" in n for n in doc().UndoNames),
            doc().UndoNames,
        )

    return [
        step(to_design, "edit_to_design"),
        step(edit_sketch, "edit_sketch"),
        step(double_click_dimension, "edit_dimension"),
        step(type_seven, "edit_type_7"),
        step(finish, "edit_finish"),
        step(thicker, "edit_thicker"),
        step(to_sim, "edit_to_sim"),
        step(stale, "edit_stale"),
        step(solve_go, "edit_solve_go"),
        ss.wait_solved("wait_solved_2"),
        step(solved, "edit_solved"),
        nothing_touched("20 after the solve"),
    ]


def fillet_at(t):
    """The fillet's round face sits in the corner of an arm t thick (its axis at x t + 3)."""
    for name in faces_where(
        lambda f: "Cylinder" in f.Surface.TypeId and abs(abs(f.Surface.Axis.y) - 1.0) < 1e-6
    ):
        face = shape().getElement(name)
        c = face.Surface.Center
        if near(c.x, t + FILLET_R, 1e-6) and near(c.z, 5 + FILLET_R, 1e-6):
            return True
    return False


def ratio_check():
    z1, v1 = S.get("p1_z"), S.get("p1_value")
    z2, v2 = S.get("p2_z"), S.get("p2_value")
    if None in (z1, v1, z2, v2):
        h.check("21 two probe values", False, S)
        return
    # the same moment arm: compare the values per N mm of moment at each node's height
    ratio = (v2 / (40.0 - z2)) / (v1 / (40.0 - z1))
    h.check(
        "21 the arm's stress drops as (5 / 7)^2 = 0.510: %.3f (band 0.45 .. 0.58)" % ratio,
        0.45 <= ratio <= 0.58,
        (v1, z1, v2, z2),
    )
    hand = arm_sigma(z2, T2)
    h.check(
        "21 and matches M c / I for 7 mm: %.2f vs %.2f MPa (band 0.80 .. 1.10)" % (v2, hand),
        0.80 * hand <= v2 <= 1.10 * hand,
        (v2, hand),
    )


# -- 5. save, close, open again ------------------------------------------------------------------
def reopen_steps(folder):
    from SciForgeTests.gui import polish2_steps as p2
    from SciForgeTests.gui import versions_input as vi

    def ctrl_s():
        S["path"] = os.path.join(folder, "Robot bracket.FCStd")
        h.press(QtCore.Qt.Key_S, QtCore.Qt.ControlModifier)

    def save_dialog():
        if not h.check("22 the Save dialog (name and place)", vi.save_dialog() is not None):
            return
        vi.fill_save_dialog("Robot bracket", folder)
        vi.click_save()

    def saved():
        h.check("22 saved", os.path.isfile(S["path"]), os.listdir(folder))
        touched = [o.Label for o in doc().Objects if "Touched" in (o.State or [])]
        h.check("22 nothing left unsaved", not rs.modified(), touched)
        S["nodes2"] = len(rs.session().data.points) if rs.session() else None

    def close():
        S["name"] = doc().Name
        p2.close_tab(doc())

    def closed():
        h.check(
            "22 the design closed", S["name"] not in App.listDocuments(), list(App.listDocuments())
        )
        h.check("22 no results left on the screen", rs.session() is None)

    def reopen():
        App.openDocument(S["path"])
        h.fit()

    def reopened():
        h.check("23 it opens in DESIGN", ss.current_tab() == "solid", ss.current_tab())
        ss.workspace("Simulation")

    def results_back():
        rs.close_new_study_dialog()
        studies = ss.studies()
        h.check("23 the study came back", len(studies) == 1, studies)
        found = ss.items()
        h.check(
            "23 with Fixed 1 and Force 1",
            sorted(i.Label for i in found) == ["Fixed 1", "Force 1"],
            found,
        )
        h.check("23 not out of date", not ss.sim().out_of_date(ss.active_study()))
        rs.click_tab("sim_results")

    def same_numbers():
        sess = rs.session()
        if not h.check("23 the results show", sess is not None):
            return
        stats = rs.summary().get("stats", {})
        h.check(
            "23 the same highest stress",
            near(stats.get("von_mises", {}).get("max", 0), S["vm2"], 1e-9),
            (stats.get("von_mises"), S["vm2"]),
        )
        h.check(
            "23 the same safety factor", near(stats.get("safety", {}).get("min", 0), S["sf2"], 1e-9)
        )
        h.check("23 the same mesh", len(sess.data.points) == S["nodes2"], len(sess.data.points))

    return [
        step(ctrl_s, "save_ctrl_s"),
        step(save_dialog, "save_dialog", 800),
        rs.wait_until(lambda: os.path.isfile(S["path"]) and not rs.modified(), "wait_saved", 20),
        step(saved, "saved", 800),
        step(close, "close"),
        step(closed, "closed", 800),
        step(reopen, "reopen"),
        step(reopened, "reopened", 800),
        step(results_back, "results_back", 800),
        step(same_numbers, "same_numbers", 800),
    ]


# -- 6. the same 50 N straight down (as asked), in a cloned study ----------------------------------
def down_steps():
    """Clone Study, the clone's force turned to Normal (into the arm's top face: down), solved.
    Down on an upright arm squeezes it: F / A = 50 / (5 x 40) = 0.25 MPa in the arm (band 0.15 ..
    0.40: the probe's node and the load entering the base); the base plate still bends between
    the arm and the bolts with the same moment as across (50 N x 37.5 mm: its highest von Mises
    within 0.75 .. 1.25 of the across case); the reaction 50 N straight up."""

    def finish():
        S["vm_across"] = rs.summary().get("stats", {}).get("von_mises", {}).get("max", 0.0)
        S["first"] = ss.active_study().Name
        rs.big("Finish Results")

    def clone():
        h.check("24 back in SETUP", ss.current_tab() == "sim_setup", ss.current_tab())
        ss.right_click_row(ss.active_study().Label, "Clone Study")

    def cloned():
        found = ss.studies()
        h.check("24 Clone Study made a second study", len(found) == 2, [x.Label for x in found])
        clones = [x for x in found if x.Name != S["first"]]
        if not clones:
            return
        S["clone"] = clones[0].Name
        if ss.active_study().Name != S["clone"]:
            ss.right_click_row(clones[0].Label, "Activate")

    def edit():
        clone = doc().getObject(S.get("clone", ""))
        loads = ss.sim().items(clone, "load") if clone is not None else []
        if h.check("24 the clone has its own force", len(loads) == 1):
            ss.double_click_row(loads[0].Label)

    def normal():
        p = ss.item_panel()
        if h.check("24 its dialog opens", p is not None and p.editing):
            ss.choose("SciForgeSim_direction", "Normal")

    def magnitude():
        ss.type_in("SciForgeSim_magnitude", "50 N")

    def ok():
        ss.ok()

    def solve():
        clone = doc().getObject(S["clone"])
        data = ss.sim().item_data(ss.sim().items(clone, "load")[0])["options"]
        h.check(
            "24 Normal, 50 N",
            data.get("direction") == "normal" and near(data.get("magnitude", 0), 50, 1e-9),
            data,
        )
        h.ribbon("Solve")

    def go():
        dialog = ss.solve_dialog()
        if h.check("24 the Solve dialog", dialog is not None):
            ss.click_widget(dialog.go)

    def solved():
        clone = doc().getObject(S["clone"])
        done = ss.sim().summary(clone)
        h.check("24 the clone solved", bool(done) and not ss.sim().out_of_date(clone))
        reactions = done.get("reactions") or {}
        total = [r for r in reactions.values()]
        up = sum(r.get("z", 0.0) for r in total)
        h.check("24 the holes push back 50 N straight up", near(up, 50.0, 1e-3), reactions)
        ss.close_popup("SciForgeSimJobStatus")  # (the progress window, Esc)
        vm = done.get("stats", {}).get("von_mises", {}).get("max", 0.0)
        S["vm_down"] = vm
        ratio = vm / S["vm_across"] if S.get("vm_across") else 0
        h.check(
            "24 the base plate's highest stress like across (%.2f vs %.2f MPa: the same moment "
            "at the bolts)" % (vm, S.get("vm_across", 0)),
            0.75 <= ratio <= 1.25,
            (vm, S.get("vm_across")),
        )

    def probe_check():
        z, value = S.get("p3_z"), S.get("p3_value")
        h.check(
            "24 the arm is only squeezed: %.3f MPa at z %.1f vs F / A = 0.25 MPa (band 0.15 .. "
            "0.40)" % (value or 0, z or 0),
            value is not None and 0.15 <= value <= 0.40,
            (value, z),
        )

    return (
        [
            step(finish, "down_finish"),
            step(clone, "down_clone"),
            step(cloned, "down_cloned"),
            step(edit, "down_edit"),
            step(normal, "down_normal"),
            step(magnitude, "down_magnitude"),
            step(ok, "down_ok"),
            step(solve, "down_solve"),
            step(go, "down_go"),
            ss.wait_solved("wait_solved_down"),
            step(solved, "down_solved"),
        ]
        + probe_steps("p3", z=22.0)
        + [step(probe_check, "down_probe_check")]
    )

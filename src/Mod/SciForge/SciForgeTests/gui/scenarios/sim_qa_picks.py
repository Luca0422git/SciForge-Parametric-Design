# SPDX-License-Identifier: LGPL-2.1-or-later
"""Edges and corners picked with the mouse in SIMULATION (sim QA), on a steel beam 100 x 10 x 10
(the study made by script, every step after it real input).

A  Structural Constraints, Fixed: two edges of the end face at x = 0 (its top edge and its front
   edge) clicked: two edges picked, OK: "Fixed 1" on two edges.
B  Structural Loads, Force, Vector Fz -100 N: the free end's top front corner clicked: one
   corner picked, OK: "Force 1" on a corner.
C  Pre-check green (two edges that meet hold every way); Solve: done; the reaction at Fixed 1 is
   the 100 N the corner takes (statics: exact); the largest movement at that corner, more than
   the beam's F L^3 / 3 E I (0.2 mm: a corner load twists it and the edges hold less than a
   face).
"""

import FreeCAD as App
import FreeCADGui as Gui

from SciForgeTests.gui import harness as h
from SciForgeTests.gui import simres_steps as rs
from SciForgeTests.gui import simsetup_steps as s

V = App.Vector
state = {}


def setup():
    from sciforge import simulation

    Gui.activateWorkbench("SciForgeWorkbench")
    doc = App.newDocument("SimQAPicks")
    rs.beam(doc)
    simulation.create_study(doc)
    doc.recompute()
    h.fit()


def enter():
    s.workspace("Simulation")
    rs.close_new_study_dialog()


# -- A ------------------------------------------------------------------------------------------
def a_open():
    h.ribbon("Structural Constraints")


def a_top_edge():
    h.check("A Structural Constraints", s.item_panel() is not None)
    h.check("A the top edge clicked", h.click_edge(V(0.0, 5.0, 10.0)), h.state.get("last_click"))


def a_bottom_edge():
    h.check("A the front edge clicked", h.click_edge(V(0.0, 0.0, 5.0)), h.state.get("last_click"))


def a_ok():
    p = s.item_panel()
    picks = sorted(sub for _b, sub in p.picks) if p is not None else []
    h.check(
        "A two edges picked", len(picks) == 2 and all(x.startswith("Edge") for x in picks), picks
    )
    s.ok()


# -- B ------------------------------------------------------------------------------------------
def b_open():
    found = s.items("constraint")
    h.check("A Fixed 1 kept", [i.Label for i in found] == ["Fixed 1"], found)
    h.ribbon("Structural Loads")


def b_vector():
    s.choose("SciForgeSim_direction", "Vector")


def b_values():
    s.type_in("SciForgeSim_fx", "0")
    s.type_in("SciForgeSim_fy", "0")
    s.type_in("SciForgeSim_fz", "-100 N")


def b_corner():
    from SciForgeTests.gui import sketch_input as si

    si.click(V(100.0, 0.0, 10.0))


def b_ok():
    p = s.item_panel()
    picks = [sub for _b, sub in p.picks] if p is not None else []
    h.check("B one corner picked", len(picks) == 1 and picks[0].startswith("Vertex"), picks)
    s.ok()


# -- C ------------------------------------------------------------------------------------------
def c_precheck():
    found = s.items("load")
    h.check("B Force 1 kept", [i.Label for i in found] == ["Force 1"], found)
    h.ribbon("Pre-check")


def c_light():
    h.check("C the light is green", s.light() == "green", s.light())
    s.close_popup("SciForgeSimPrecheck")
    h.ribbon("Solve")


def c_go():
    dialog = s.solve_dialog()
    if h.check("C the Solve dialog", dialog is not None):
        s.click_widget(dialog.go)


def c_check():
    from sciforge import simulation_solve_dialog

    results = simulation_solve_dialog.last_results()
    h.check("C solved", any(r[0] == "done" for r in results.values()), results)
    summary = rs.summary()
    total = (summary.get("reactions") or {}).get("Fixed 1", {}).get("total")
    h.check("C the reaction is the 100 N", total is not None and abs(total - 100.0) < 1e-3, total)
    disp = summary.get("stats", {}).get("displacement", {})
    where = disp.get("max_at") or [0, 0, 0]
    h.check(
        "C the corner moves most (%.3f mm at %s)" % (disp.get("max", 0), where),
        abs(where[0] - 100.0) < 1e-6 and disp.get("max", 0) > 0.2,
        disp,
    )


h.run(
    "sim_qa_picks",
    [
        setup,
        enter,
        a_open,
        a_top_edge,
        a_bottom_edge,
        a_ok,
        b_open,
        b_vector,
        b_values,
        b_corner,
        b_ok,
        c_precheck,
        c_light,
        c_go,
        s.wait_solved(),
        c_check,
    ],
)
